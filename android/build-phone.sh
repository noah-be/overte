#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command_name="${1:-all}"

fail() {
    echo "error: $*" >&2
    exit 2
}

java_major() {
    "$1/bin/java" -version 2>&1 \
        | awk -F'[\".]' '/version/ { if ($2 == "1") print $3; else print $2; exit }'
}

find_compatible_jdk() {
    local candidate major
    for candidate in \
        "${JAVA_HOME:-}" \
        "${HOME}/Applications/android-studio/jbr" \
        "/opt/android-studio/jbr" \
        "/usr/lib/jvm/java-21-openjdk" \
        "/usr/lib/jvm/java-17-openjdk"; do
        [[ -n "$candidate" && -x "$candidate/bin/java" ]] || continue
        major="$(java_major "$candidate")"
        if [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 17 && major <= 21 )); then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

usage() {
    cat <<'EOF'
Usage: ./build-phone.sh [doctor|prepare|build|install|all|deploy|setup] [option]

  doctor   Check the shared Android/Pico development environment
  prepare  Stage the existing Android Conan and Qt dependencies
  build    Build the phoneInterface debug APK
  install  Install and start the existing APK on one connected Android device
  all      Prepare dependencies and build the APK (default)
  deploy   Prepare, build, install, and start the client
  setup    Download dependencies when requested, prepare, and build

The phone port intentionally shares the proven Qt/Conan Android toolchain with
the Pico build. Use `setup --download` on a new development machine.
EOF
}

prepare() {
    PICO_BUILD_JOBS="${PHONE_BUILD_JOBS:-$(nproc)}" \
        "$script_dir/build-pico.sh" prepare
}

build() {
    local jdk sdk
    jdk="$(find_compatible_jdk)" \
        || fail "a JDK between versions 17 and 21 was not found"
    sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    [[ -d "$sdk" ]] || fail "Android SDK was not found"
    JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" \
        CMAKE_BUILD_PARALLEL_LEVEL="${PHONE_BUILD_JOBS:-$(nproc)}" \
        "$script_dir/gradlew" \
        --settings-file "$script_dir/settings-phone.gradle" \
        :phoneInterface:assembleDebug
}

adb_command() {
    local sdk adb
    sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    adb="${PHONE_ADB:-$sdk/platform-tools/adb}"
    [[ -x "$adb" ]] || fail "ADB was not found"
    printf '%s\n' "$adb"
}

install_apk() {
    local adb apk serial_args=()
    adb="$(adb_command)"
    apk="$script_dir/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk"
    [[ -f "$apk" ]] || fail "APK does not exist; run ./build-phone.sh build first"
    [[ -z "${ANDROID_SERIAL:-}" ]] || serial_args=(-s "$ANDROID_SERIAL")
    "$adb" "${serial_args[@]}" install -r "$apk"
    "$adb" "${serial_args[@]}" shell am start \
        -n org.overte.phone/.PermissionsActivity
}

case "$command_name" in
    doctor) "$script_dir/build-pico.sh" doctor ;;
    prepare) prepare ;;
    build) build ;;
    install) install_apk ;;
    all) prepare; build ;;
    deploy) prepare; build; install_apk ;;
    setup)
        if [[ "${2:-}" == "--download" ]]; then
            "$script_dir/build-pico.sh" deps --download
        fi
        prepare
        build
        ;;
    help|-h|--help) usage ;;
    *) usage >&2; fail "unknown command: $command_name" ;;
esac
