#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jobs="${QUEST_BUILD_JOBS:-$(nproc)}"
command="${1:-build}"
quest_tmp_dir="${QUEST_TMPDIR:-$script_dir/.quest-tmp}"
mkdir -p "$quest_tmp_dir"
export TMPDIR="$quest_tmp_dir"

fail() { echo "error: $*" >&2; exit 1; }
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || fail "QUEST_BUILD_JOBS must be a positive integer"

usage() {
    cat <<'EOF'
Usage: ./build-quest.sh [doctor|deps|prepare|build|all] [--stacktrace]

Builds a debug-signed, sideloadable APK for Meta Quest without requiring a
connected headset. deps and prepare reuse the checksum-pinned Pico/OpenXR
dependency graph. A real Quest is still required for runtime acceptance tests.
EOF
}

case "$command" in
    doctor|deps|prepare)
        exec env PICO_BUILD_JOBS="$jobs" "$script_dir/build-pico.sh" "$@"
        ;;
    build)
        shift || true
        ;;
    all)
        shift || true
        env PICO_BUILD_JOBS="$jobs" "$script_dir/build-pico.sh" deps --download
        env PICO_BUILD_JOBS="$jobs" "$script_dir/build-pico.sh" prepare
        ;;
    help|-h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        fail "unsupported command: $command"
        ;;
esac

gradle_args=()
if [[ "${1:-}" == "--stacktrace" ]]; then
    gradle_args+=(--stacktrace)
    shift
fi
[[ $# -eq 0 ]] || fail "unsupported option: $1"

android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
java_home="${JAVA_HOME:-$HOME/Applications/android-studio/jbr}"
[[ -d "$android_sdk/platforms/android-36" ]] || fail "Android SDK 36 not found: $android_sdk"
[[ -x "$java_home/bin/java" ]] || fail "JDK 17-21 not found: $java_home"

export ANDROID_SDK_ROOT="$android_sdk"
export ANDROID_HOME="$android_sdk"
export JAVA_HOME="$java_home"

# Android's asset compressor can need several GiB of temporary space. Some
# development environments keep /tmp on a small, quota-limited tmpfs, so keep
# Quest packaging scratch data alongside the ignored Android build outputs.
PICO_BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs" \
    SHADERGEN_JOBS="${QUEST_SHADER_JOBS:-$jobs}" \
    "$script_dir/gradlew" --settings-file "$script_dir/settings-pico.gradle" \
    -Djava.io.tmpdir="$quest_tmp_dir" \
    -PQUEST_BUILD=true :picoInterface:assembleDebug --max-workers="$jobs" \
    "${gradle_args[@]}"

apk="$script_dir/apps/picoInterface/build/outputs/apk/debug/overte-quest-preview-debug.apk"
[[ -f "$apk" ]] || fail "expected APK was not produced: $apk"
build_tools="$(find "$android_sdk/build-tools" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
    | sort -V | tail -1)"
[[ -n "$build_tools" ]] || fail "Android SDK build tools were not found"
tools_dir="$android_sdk/build-tools/$build_tools"
report_dir="$script_dir/apps/picoInterface/build/reports/quest"
"$script_dir/ci/verify-quest-apk.py" "$apk" \
    --aapt "$tools_dir/aapt" --apksigner "$tools_dir/apksigner" \
    --zipalign "$tools_dir/zipalign" --output "$report_dir/verification.json"
"$script_dir/ci/analyze-apk-size.py" "$apk" \
    --output "$report_dir/size.md" --budget-mib "${QUEST_APK_BUDGET_MIB:-550}"
echo "Quest preview APK: $apk"
echo "Quest verification reports: $report_dir"
