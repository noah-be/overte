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

Phone builds require the verified 16 KiB dependency sentinel. For temporary
local migration work only, PHONE_ALLOW_LEGACY_4K_DEPS=1 enables the old graph.
Installation never uses ADB's implicit device. Set ANDROID_SERIAL, or connect
exactly one authorized non-Pico phone.

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
    adb="$(adb_command)"
    apk="${PHONE_APK:-$script_dir/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk}"
    [[ -f "$apk" ]] || fail "APK does not exist; run ./build-phone.sh build first"
    serial="$(select_phone_serial "$adb")"
    "$adb" -s "$serial" install -r "$apk"
    "$adb" -s "$serial" shell am start \
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
