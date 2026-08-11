#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
command_name="${1:-all}"
command_option="${2:-}"
jobs="${PHONE_BUILD_JOBS:-$(nproc)}"

fail() {
    echo "error: $*" >&2
    exit 2
}

[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || fail "PHONE_BUILD_JOBS must be a positive integer"

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
Usage: ./build-phone.sh [doctor|deps|prepare|build|install|all|deploy|setup] [option]

  doctor   Check the shared Android/Pico development environment
  deps     Install Phone dependencies; use --download for prebuilt artifacts
  prepare  Stage the existing Android Conan and Qt dependencies
  build [--stacktrace]
           Build the phoneInterface debug APK with optional Gradle diagnostics
  install  Install and start the existing APK on one connected Android device
  all      Prepare dependencies and build the APK (default)
  deploy   Prepare, build, install, and start the client
  setup    Download shared and Phone 16 KiB dependencies, prepare, and build

Phone builds require the verified 16 KiB dependency sentinel. For temporary
local migration work only, PHONE_ALLOW_LEGACY_4K_DEPS=1 enables the old graph.
Installation never uses ADB's implicit device. Set ANDROID_SERIAL, or connect
exactly one authorized non-Pico phone.

The phone port intentionally shares the proven Qt/Conan Android toolchain with
the Pico build. `setup --download` restores the shared artifacts followed by
the smaller Phone-specific 16 KiB delta on a new development machine.
EOF
}

download_prebuilt_dependencies() {
    local temp_root="${PHONE_PREBUILT_TMPDIR:-$script_dir/build/prebuilt-tmp}"
    local shared_conan_home="${PHONE_SHARED_CONAN_HOME:-${HOME}/.conan2}"
    # Phone dependency transport is deliberately independent from Pico release
    # assets. The versioned archive contains the complete pinned Phone graph.
    [[ ! -L "$temp_root" ]] || fail "Phone prebuilt temporary directory must not be a symlink"
    mkdir -p -- "$temp_root"
    [[ -d "$temp_root" && -w "$temp_root" ]] \
        || fail "Phone prebuilt temporary directory is not writable"
    CONAN_HOME="$shared_conan_home" TMPDIR="$temp_root" \
        PICO_PREBUILT_RESTORE_ONLY=1 \
        "$android_root/vr/pico/build.sh" deps --download
    "$script_dir/phone-prebuilt-16k-deps.sh" download
}

install_dependencies() {
    "$android_root/vr/pico/build.sh" deps
    "$script_dir/build-phone-qt-16k.sh"
    "$script_dir/prepare-phone-16k-conan-deps.sh"
}

is_android_arm64_draco_package() {
    local package_dir="$1" archive member
    archive="$package_dir/lib/libdraco.a"
    [[ -f "$archive" && -f "$package_dir/conaninfo.txt" ]] || return 1
    grep -Eq '^os=Android$' "$package_dir/conaninfo.txt" || return 1
    grep -Eq '^arch=armv8$' "$package_dir/conaninfo.txt" || return 1
    member="$(ar t "$archive" 2>/dev/null | sed -n '1p')"
    [[ -n "$member" ]] || return 1
    [[ "$(ar p "$archive" "$member" 2>/dev/null \
        | dd bs=1 skip=18 count=2 status=none \
        | od -An -tx1 | tr -d '[:space:]')" == b700 ]]
}

find_phone_draco_package() {
    local requested="${PICO_DRACO_PACKAGE_DIR:-}" package_dir archive
    if [[ -n "$requested" ]]; then
        is_android_arm64_draco_package "$requested" \
            || fail "PICO_DRACO_PACKAGE_DIR is not an Android ARM64 Draco package"
        printf '%s\n' "$requested"
        return
    fi

    while IFS= read -r -d '' archive; do
        package_dir="${archive%/lib/libdraco.a}"
        if is_android_arm64_draco_package "$package_dir"; then
            printf '%s\n' "$package_dir"
            return
        fi
    done < <(find "${CONAN_HOME:-${HOME}/.conan2}/p" \
        -path '*/p/lib/libdraco.a' -type f -print0 2>/dev/null | sort -z)
    fail "an Android ARM64 Draco Conan package was not found"
}

prepare() {
    local qt_dir="$android_root/common/conan/phone-16k-debug"
    local nonqt_dir="$android_root/common/conan/phone-nonqt-16k-debug"
    local ready_marker="$nonqt_dir/.phone-16k-dependencies.ready"
    "$android_root/phone/tests/verify-phone-16k-dependencies.sh" \
        "$qt_dir" "$nonqt_dir" "$ready_marker"
    local draco_package
    draco_package="$(find_phone_draco_package)"
    CONAN_HOME="${PHONE_SHARED_CONAN_HOME:-${HOME}/.conan2}" \
        PICO_DRACO_PACKAGE_DIR="$draco_package" \
        PICO_BUILD_JOBS="$jobs" \
        "$android_root/vr/pico/build.sh" prepare
}

doctor() {
    # Reuse the shared checker without leaking Pico-specific hand-off text into
    # the Phone entry point. pipefail preserves the checker's failure status.
    CONAN_HOME="${PHONE_SHARED_CONAN_HOME:-${HOME}/.conan2}" \
        "$android_root/vr/pico/build.sh" doctor | sed \
        -e 's/^Pico 4 build environment$/Android phone build environment (shared toolchain)/' \
        -e 's|^Next: ./build-pico.sh setup --download$|Next: follow ANDROID_PHONE_BUILD.md 16 KiB setup order; then ./build-phone.sh build|'
    printf '\nPhone dependency graph:\n'
    local qt_dir="$android_root/common/conan/phone-16k-debug"
    local nonqt_dir="$android_root/common/conan/phone-nonqt-16k-debug"
    local ready_marker="$nonqt_dir/.phone-16k-dependencies.ready"
    if [[ -f "$ready_marker" ]]; then
        if "$android_root/phone/tests/verify-phone-16k-dependencies.sh" \
                "$qt_dir" "$nonqt_dir" "$ready_marker" >/dev/null 2>&1; then
            printf '  [READY] verified 16 KiB dependency contents match the marker\n'
        else
            printf '  [STALE] 16 KiB dependency contents do not match the marker\n' >&2
            return 1
        fi
    else
        printf '  [SETUP] verified 16 KiB dependencies are not prepared yet\n'
    fi
}

build() {
    local option="${1:-}" jdk sdk gradle_jvm_args
    local build_tmp="${PHONE_BUILD_TMPDIR:-$script_dir/build/package-tmp}"
    local -a gradle_diagnostics=()
    if [[ "$option" == "--stacktrace" ]]; then
        gradle_diagnostics+=(--stacktrace)
    elif [[ -n "$option" ]]; then
        fail "unsupported build option: $option"
    fi
    jdk="$(find_compatible_jdk)" \
        || fail "a JDK between versions 17 and 21 was not found"
    sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    gradle_jvm_args="${PHONE_GRADLE_JVM_ARGS:--Xmx6g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8}"
    [[ -d "$sdk" ]] || fail "Android SDK was not found"
    [[ ! -L "$build_tmp" ]] || fail "Phone build temporary directory must not be a symlink"
    mkdir -p -- "$build_tmp"
    [[ -d "$build_tmp" && -w "$build_tmp" ]] \
        || fail "Phone build temporary directory is not writable"
    # AGP's incremental Zipflinger can retain multi-megabyte holes after a
    # native library changes. Recreate only generated APK packaging state;
    # keep the expensive CMake/Ninja object tree intact.
    local packaging_path
    for packaging_path in \
        "$script_dir/apps/phoneInterface/build/outputs/apk/debug" \
        "$script_dir/apps/phoneInterface/build/intermediates/apk/debug" \
        "$script_dir/apps/phoneInterface/build/intermediates/incremental/packageDebug"; do
        [[ ! -L "$packaging_path" ]] || fail "Phone packaging output must not be a symlink"
        if [[ -d "$packaging_path" ]]; then
            find "$packaging_path" -depth -delete
        fi
    done
    JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" TMPDIR="$build_tmp" \
        JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+${JAVA_TOOL_OPTIONS} }-Djava.io.tmpdir=$build_tmp" \
        PICO_BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs" \
        SHADERGEN_JOBS="$jobs" \
        "$android_root/common/gradlew" \
        "-Dorg.gradle.jvmargs=$gradle_jvm_args" \
        --settings-file "$script_dir/settings.gradle" \
        :phoneInterface:assembleDebug --max-workers="$jobs" "${gradle_diagnostics[@]}"
}

device_property() {
    "$1" -s "$2" shell getprop "$3" 2>/dev/null | tr -d '\r'
}

is_vr_device() {
    local adb="$1" serial="$2" identity characteristics
    identity="$(device_property "$adb" "$serial" ro.product.manufacturer) $(device_property "$adb" "$serial" ro.product.brand) $(device_property "$adb" "$serial" ro.product.model) $(device_property "$adb" "$serial" ro.product.device)"
    characteristics="$(device_property "$adb" "$serial" ro.build.characteristics)"
    [[ "${identity,,}" =~ pico|bytedance ]] || [[ "${characteristics,,}" =~ (^|,)vr(,|$) ]]
}

select_phone_serial() {
    local adb="$1" requested="${ANDROID_SERIAL:-}" serial state
    local -a authorized=() phones=()
    while read -r serial state _; do
        [[ -n "$serial" && "$serial" != "List" ]] || continue
        [[ "$state" == device ]] && authorized+=("$serial")
    done < <("$adb" devices -l)

    if [[ -n "$requested" ]]; then
        for serial in "${authorized[@]}"; do
            if [[ "$serial" == "$requested" ]]; then
                is_vr_device "$adb" "$serial" && fail "refusing to install the phone client on a Pico/VR device"
                printf '%s\n' "$serial"
                return
            fi
        done
        fail "ANDROID_SERIAL does not identify an authorized connected device"
    fi
    for serial in "${authorized[@]}"; do
        is_vr_device "$adb" "$serial" || phones+=("$serial")
    done
    ((${#phones[@]} == 1)) || fail "set ANDROID_SERIAL explicitly; found ${#phones[@]} unambiguous non-Pico phones"
    printf '%s\n' "${phones[0]}"
}

adb_command() {
    local sdk adb
    sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    adb="${PHONE_ADB:-$sdk/platform-tools/adb}"
    [[ -x "$adb" ]] || fail "ADB was not found"
    printf '%s\n' "$adb"
}

install_apk() {
    local adb apk serial
    if [[ "${PHONE_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
        exec "$script_dir/phone-device-lock.sh" run -- "$0" install
    fi
    adb="$(adb_command)"
    apk="${PHONE_APK:-$script_dir/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk}"
    [[ -f "$apk" ]] || fail "APK does not exist; run ./build-phone.sh build first"
    serial="$(select_phone_serial "$adb")"
    "$adb" -s "$serial" install -r "$apk"
    "$adb" -s "$serial" shell am start \
        -n org.overte.phone/.PermissionsActivity
}

case "$command_name" in
    doctor) doctor ;;
    deps)
        if [[ "${2:-}" == "--download" ]]; then
            download_prebuilt_dependencies
        elif [[ -z "${2:-}" ]]; then
            install_dependencies
        else
            fail "unsupported deps option: ${2:-}"
        fi
        ;;
    prepare) prepare ;;
    build) build "$command_option" ;;
    install) install_apk ;;
    all) prepare; build ;;
    deploy) prepare; build; install_apk ;;
    setup)
        doctor
        printf '\n'
        if [[ "${2:-}" == "--download" ]]; then
            download_prebuilt_dependencies
        elif [[ -z "${2:-}" ]]; then
            install_dependencies
        else
            fail "unsupported setup option: ${2:-}"
        fi
        prepare
        build
        ;;
    help|-h|--help) usage ;;
    *) usage >&2; fail "unknown command: $command_name" ;;
esac
