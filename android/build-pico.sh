#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
conan_home="${CONAN_HOME:-${HOME}/.conan2}"
jobs="${PICO_BUILD_JOBS:-$(nproc)}"
command_name="${1:-all}"

fail() {
    echo "error: $*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: ./build-pico.sh [prepare|build|all]

  prepare  Locate and stage the existing Conan/Qt dependencies
  build    Build the Pico debug APK
  all      Prepare dependencies and build the APK (default)

Detected paths can be overridden with ANDROID_SDK_ROOT, JAVA_HOME,
PICO_QT_SOURCE_DIR, PICO_QT_BUILD_DIR, PICO_TBB_PACKAGE_DIR,
PICO_DRACO_PACKAGE_DIR, and the PICO_* host-tool variables.
EOF
}

newest_match() {
    local pattern="$1"
    find "$conan_home/p/b" -maxdepth 7 -path "$pattern" -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | sed -n '1s/^[^ ]* //p'
}

newest_host_tool() {
    local pattern="$1" candidate
    while IFS= read -r candidate; do
        if file "$candidate" | grep -Eq 'x86-64|x86_64'; then
            echo "$candidate"
            return
        fi
    done < <(find "$conan_home/p/b" -maxdepth 7 -path "$pattern" \
        -type f -perm -u+x -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | sed 's/^[^ ]* //')
}

detect_sdk() {
    local candidate
    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "${HOME}/Android/Sdk"; do
        if [[ -n "$candidate" && -d "$candidate/platforms/android-36" ]]; then
            export ANDROID_SDK_ROOT="$candidate"
            export ANDROID_HOME="$candidate"
            return
        fi
    done
    fail "Android SDK 36 not found; set ANDROID_SDK_ROOT"
}

java_major() {
    "$1/bin/java" -version 2>&1 | sed -n '1s/.*version "\([0-9]*\).*/\1/p'
}

detect_jdk() {
    local candidate major
    for candidate in "${JAVA_HOME:-}" \
        "${HOME}/Applications/android-studio/jbr" \
        "/opt/android-studio/jbr"; do
        [[ -x "$candidate/bin/java" ]] || continue
        major="$(java_major "$candidate")"
        if [[ "$major" =~ ^[0-9]+$ && "$major" -ge 17 && "$major" -le 21 ]]; then
            export JAVA_HOME="$candidate"
            return
        fi
    done
    fail "a JDK between versions 17 and 21 was not found; set JAVA_HOME"
}

detect_dependencies() {
    local qt_build qt_source draco_package tbb_package

    qt_build="${PICO_QT_BUILD_DIR:-$(newest_match '*/qt*/b/build_folder/qtbase/lib/libQt5Core_arm64-v8a.so')}"
    [[ -n "$qt_build" ]] || fail "patched Qt build not found; set PICO_QT_BUILD_DIR"
    [[ "$qt_build" != *.so ]] || qt_build="${qt_build%/qtbase/lib/libQt5Core_arm64-v8a.so}"
    qt_source="${PICO_QT_SOURCE_DIR:-${qt_build%/build_folder}/qt5}"
    [[ -d "$qt_source" ]] || fail "matching Qt source not found; set PICO_QT_SOURCE_DIR"

    draco_package="${PICO_DRACO_PACKAGE_DIR:-$(newest_match '*/draco*/p/lib/libdraco.a')}"
    [[ -n "$draco_package" ]] || fail "Draco Conan package not found; set PICO_DRACO_PACKAGE_DIR"
    [[ "$draco_package" != *.a ]] || draco_package="${draco_package%/lib/libdraco.a}"

    tbb_package="${PICO_TBB_PACKAGE_DIR:-$(newest_match '*/onetb*/p/lib/libtbb.so')}"
    [[ -n "$tbb_package" ]] || fail "release TBB Conan package not found; set PICO_TBB_PACKAGE_DIR"
    [[ "$tbb_package" != *.so ]] || tbb_package="${tbb_package%/lib/libtbb.so}"
    file "$tbb_package/lib/libtbb.so" | grep -Eq 'ARM aarch64|ARM64' \
        || fail "TBB runtime is not Android ARM64: $tbb_package/lib/libtbb.so"

    export PICO_QT_BUILD_DIR="$qt_build"
    export PICO_QT_SOURCE_DIR="$qt_source"
    export PICO_DRACO_PACKAGE_DIR="$draco_package"
    export PICO_TBB_PACKAGE_DIR="$tbb_package"
    export PICO_GLSLANG_VALIDATOR="${PICO_GLSLANG_VALIDATOR:-$(newest_host_tool '*/glsl*/p/bin/glslang')}"
    export PICO_SCRIBE="${PICO_SCRIBE:-$(newest_host_tool '*/scrib*/p/tools/scribe')}"
    export PICO_SPIRV_CROSS="${PICO_SPIRV_CROSS:-$(newest_host_tool '*/spirv*/p/bin/spirv-cross')}"
    export PICO_SPIRV_OPT="${PICO_SPIRV_OPT:-$(newest_host_tool '*/spirv*/p/bin/spirv-opt')}"

    local tool
    for tool in PICO_GLSLANG_VALIDATOR PICO_SCRIBE PICO_SPIRV_CROSS PICO_SPIRV_OPT; do
        [[ -x "${!tool:-}" ]] || fail "host tool $tool not found; set it explicitly"
    done

    echo "Qt build: $PICO_QT_BUILD_DIR"
    echo "TBB package: $PICO_TBB_PACKAGE_DIR"
    echo "Draco package: $PICO_DRACO_PACKAGE_DIR"
}

prepare() {
    detect_dependencies
    PICO_BUILD_JOBS="$jobs" "$script_dir/prepare-pico-deps.sh"
}

build() {
    detect_sdk
    detect_jdk
    echo "Android SDK: $ANDROID_SDK_ROOT"
    echo "Java: $JAVA_HOME"
    CMAKE_BUILD_PARALLEL_LEVEL="$jobs" "$script_dir/gradlew" \
        --settings-file "$script_dir/settings-pico.gradle" \
        :picoInterface:assembleDebug --max-workers="$jobs"
    echo "APK: $script_dir/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk"
}

case "$command_name" in
    prepare) prepare ;;
    build) build ;;
    all) prepare; build ;;
    help|-h|--help) usage ;;
    *) usage >&2; fail "unknown command: $command_name" ;;
esac
