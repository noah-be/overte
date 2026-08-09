#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
adb="$sdk/platform-tools/adb"
emulator="$sdk/emulator/emulator"
avd="${PHONE_EMULATOR_AVD:-overte_api35}"
command_name="${1:-all}"
state_dir="$script_dir/build/phone-emulator"
serial_file="$state_dir/serial"
pid_file="$state_dir/pid"
log_file="$state_dir/emulator.log"
gradle_tmp="$state_dir/gradle-tmp"

fail() { echo "error: $*" >&2; exit 2; }

java_major() {
    "$1/bin/java" -version 2>&1 \
        | awk -F'[".]' '/version/ { if ($2 == "1") print $3; else print $2; exit }'
}

find_jdk() {
    local candidate major
    for candidate in "${JAVA_HOME:-}" "$script_dir/pico-host-tools/jdk-21" \
            "${HOME}/Applications/android-studio/jbr" \
            "/usr/lib/jvm/java-21-openjdk" "/usr/lib/jvm/java-17-openjdk"; do
        [[ -n "$candidate" && -x "$candidate/bin/java" ]] || continue
        major="$(java_major "$candidate")"
        if [[ "$major" =~ ^(17|18|19|20|21)$ ]]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    return 1
}

running_serial() {
    local serial name
    while read -r serial state _; do
        [[ "$serial" == emulator-* && "$state" == device ]] || continue
        name="$($adb -s "$serial" emu avd name 2>/dev/null | tr -d '\r' | sed -n '1p')"
        if [[ "$name" == "$avd" ]]; then
            printf '%s\n' "$serial"
            return
        fi
    done < <("$adb" devices -l)
    return 1
}

doctor() {
    [[ -x "$adb" ]] || fail "ADB was not found: $adb"
    [[ -x "$emulator" ]] || fail "Android Emulator was not found: $emulator"
    "$emulator" -list-avds | grep -Fxq "$avd" || fail "AVD does not exist: $avd"
    "$emulator" -accel-check | grep -q 'is installed and usable' \
        || fail "hardware acceleration is not usable"
    local config="$HOME/.android/avd/${avd}.avd/config.ini"
    [[ -f "$config" ]] || fail "AVD configuration was not found: $config"
    grep -Eq '^abi.type=x86_64$' "$config" || fail "AVD must use x86_64"
    find_jdk >/dev/null || fail "JDK 17-21 was not found"
    echo "Phone emulator environment is ready: $avd"
}

start() {
    doctor
    mkdir -p -- "$state_dir"
    local serial
    if serial="$(running_serial)"; then
        printf '%s\n' "$serial" > "$serial_file"
        echo "Phone emulator is already running: $serial"
        return
    fi
    "$emulator" "@$avd" -no-window -no-audio -no-boot-anim \
        -gpu host -no-snapshot-save >"$log_file" 2>&1 &
    printf '%s\n' "$!" > "$pid_file"
    for _ in $(seq 1 120); do
        if serial="$(running_serial)"; then
            if [[ "$($adb -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; then
                printf '%s\n' "$serial" > "$serial_file"
                "$adb" -s "$serial" shell settings put global window_animation_scale 0
                "$adb" -s "$serial" shell settings put global transition_animation_scale 0
                "$adb" -s "$serial" shell settings put global animator_duration_scale 0
                echo "Phone emulator booted: $serial"
                return
            fi
        fi
        sleep 1
    done
    fail "emulator did not boot within 120 seconds; see $log_file"
}

build() {
    local jdk
    jdk="$(find_jdk)" || fail "JDK 17-21 was not found"
    mkdir -p -- "$gradle_tmp"
    [[ -f "$script_dir/conan/phone-emulator-x86_64-debug/.phone-emulator-dependencies.ready" ]] \
        || "$script_dir/prepare-phone-emulator-deps.sh"
    PHONE_EMULATOR_BUILD=1 JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" \
        TMPDIR="$gradle_tmp" JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$gradle_tmp ${JAVA_TOOL_OPTIONS:-}" \
        CMAKE_BUILD_PARALLEL_LEVEL="${PHONE_BUILD_JOBS:-$(nproc)}" \
        "$script_dir/gradlew" --settings-file "$script_dir/settings-phone.gradle" \
        :phoneInterface:assembleEmulator :phoneInterface:assembleEmulatorAndroidTest
}

test_emulator() {
    local jdk serial
    start
    serial="$(<"$serial_file")"
    jdk="$(find_jdk)" || fail "JDK 17-21 was not found"
    mkdir -p -- "$gradle_tmp"
    PHONE_EMULATOR_BUILD=1 JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" \
        TMPDIR="$gradle_tmp" JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$gradle_tmp ${JAVA_TOOL_OPTIONS:-}" \
        ANDROID_SERIAL="$serial" \
        "$script_dir/gradlew" --settings-file "$script_dir/settings-phone.gradle" \
        :phoneInterface:connectedEmulatorAndroidTest
}

stop() {
    local serial
    if serial="$(running_serial)"; then
        "$adb" -s "$serial" emu kill >/dev/null
        echo "Stopped phone emulator: $serial"
    else
        echo "Phone emulator is not running: $avd"
    fi
    rm -f -- "$serial_file" "$pid_file"
}

case "$command_name" in
    doctor) doctor ;;
    deps) "$script_dir/prepare-phone-emulator-deps.sh" ;;
    start) start ;;
    build) build ;;
    test) test_emulator ;;
    stop) stop ;;
    all) build; test_emulator ;;
    *) fail "usage: $0 [doctor|deps|start|build|test|stop|all]" ;;
esac
