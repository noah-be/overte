#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
repo_root="$(cd -- "$android_root/.." && pwd)"
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
test_class="${PHONE_EMULATOR_TEST_CLASS:-}"
test_repetitions="${PHONE_EMULATOR_TEST_REPETITIONS:-1}"
lock_file="${PHONE_EMULATOR_LOCK_FILE:-${state_dir}.lock}"
lock_timeout="${PHONE_EMULATOR_LOCK_TIMEOUT_SECONDS:-600}"
emulator_profile="$android_root/common/conan/profiles/phone-emulator-x86_64"
emulator_dependencies="$android_root/common/conan/phone-emulator-x86_64-debug"
emulator_ready="$emulator_dependencies/.phone-emulator-dependencies.ready"
emulator_host_tools="$script_dir/pico-host-tools"
emulator_dependency_verifier="$script_dir/tests/verify-phone-emulator-dependencies.py"
emulator_conan_cache_root="${PHONE_EMULATOR_CONAN_CACHE_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/overte/android-phone-emulator-conan}"
emulator_conan_cache="$emulator_conan_cache_root/libnode-x86_64-conan.tgz"

fail() { echo "error: $*" >&2; exit 2; }

java_major() {
    "$1/bin/java" -version 2>&1 \
        | awk -F'[".]' '/version/ { if ($2 == "1") print $3; else print $2; exit }'
}

find_jdk() {
    local candidate major
    for candidate in "${JAVA_HOME:-}" "$android_root/vr/pico/pico-host-tools/jdk-21" \
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

setup_compiler_cache() {
    local ccache_bin cache_root
    ccache_bin="$(command -v ccache 2>/dev/null || true)"
    [[ -n "$ccache_bin" ]] || return
    cache_root="${XDG_CACHE_HOME:-${HOME}/.cache}"
    export PHONE_EMULATOR_CCACHE="$ccache_bin"
    export CCACHE_DIR="${PHONE_EMULATOR_CCACHE_DIR:-$cache_root/overte/android-phone-emulator-ccache}"
    export CCACHE_BASEDIR="$repo_root"
    export CCACHE_NOHASHDIR=true
    export CCACHE_COMPILERCHECK=content
    export CCACHE_NAMESPACE='overte-android-phone-emulator-x86_64-api26-ndk27.3-debug'
    mkdir -p -- "$CCACHE_DIR"
    "$ccache_bin" --max-size "${PHONE_EMULATOR_CCACHE_MAX_SIZE:-15G}" >/dev/null
}

write_emulator_ready_marker() {
    mkdir -p -- "$emulator_dependencies"
    printf 'abi=x86_64\nprofile=%s\n' \
        "$(sha256sum "$emulator_profile" | awk '{print $1}')" >"$emulator_ready.tmp"
    mv -- "$emulator_ready.tmp" "$emulator_ready"
}

emulator_dependencies_are_ready() {
    python3 "$emulator_dependency_verifier" "$emulator_dependencies" \
        "$emulator_profile" "$emulator_ready" "$emulator_host_tools" >/dev/null 2>&1
}

restore_emulator_dependency_cache() {
    [[ -f "$emulator_conan_cache" && ! -L "$emulator_conan_cache" ]] || return 1
    echo 'Restoring the persistent x86_64 Conan package cache...'
    conan cache restore "$emulator_conan_cache" >/dev/null 2>&1 || return 1
    conan install "$android_root/common/conan/conanfile-pico.py" \
        -of "$emulator_dependencies" -pr:h "$emulator_profile" -pr:b default \
        --build=never >/dev/null 2>&1 || return 1
    write_emulator_ready_marker
    emulator_dependencies_are_ready
}

ensure_emulator_dependencies() {
    emulator_dependencies_are_ready && return
    if restore_emulator_dependency_cache; then
        echo 'Phone emulator dependencies restored without recompilation.'
        return
    fi
    "$script_dir/prepare-phone-emulator-deps.sh"
    emulator_dependencies_are_ready \
        || fail 'prepared phone emulator dependencies failed verification'
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
    setup_compiler_cache
    mkdir -p -- "$gradle_tmp"
    ensure_emulator_dependencies
    PHONE_EMULATOR_BUILD=1 JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" \
        TMPDIR="$gradle_tmp" JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$gradle_tmp ${JAVA_TOOL_OPTIONS:-}" \
        CMAKE_BUILD_PARALLEL_LEVEL="${PHONE_BUILD_JOBS:-$(nproc)}" \
        "$android_root/common/gradlew" --settings-file "$script_dir/settings.gradle" \
        :phoneInterface:assembleEmulator :phoneInterface:assembleEmulatorAndroidTest
}

collect_test_diagnostics() {
    local serial="$1" attempt="$2" instrumentation_log="$3"
    local diagnostic_dir
    diagnostic_dir="$state_dir/diagnostics/run-$(date -u +%Y%m%dT%H%M%SZ)-$$/attempt-$attempt"
    mkdir -p -- "$diagnostic_dir"
    cp -- "$instrumentation_log" "$diagnostic_dir/instrumentation.log"
    "$adb" -s "$serial" logcat -d -v threadtime >"$diagnostic_dir/logcat.txt" 2>&1 || true
    "$adb" -s "$serial" logcat -b crash -d -v threadtime \
        >"$diagnostic_dir/native-crash-logcat.txt" 2>&1 || true
    "$adb" -s "$serial" shell dumpsys activity activities \
        >"$diagnostic_dir/activity.txt" 2>&1 || true
    "$adb" -s "$serial" shell dumpsys dropbox --print data_app_native_crash \
        >"$diagnostic_dir/native-crash-dropbox.txt" 2>&1 || true
    "$adb" -s "$serial" shell ls -la /data/tombstones \
        >"$diagnostic_dir/tombstones.txt" 2>&1 || true
    printf 'Phone emulator diagnostics: %s\n' "$diagnostic_dir" >&2
}

test_emulator() {
    local jdk serial attempt instrumentation_log
    local -a gradle_arguments
    [[ "$test_repetitions" =~ ^[0-9]+$ ]] && \
        (( 10#$test_repetitions >= 1 && 10#$test_repetitions <= 25 )) \
        || fail "PHONE_EMULATOR_TEST_REPETITIONS must be an integer from 1 through 25"
    if (( 10#$test_repetitions > 1 )) && [[ -z "$test_class" ]]; then
        fail "PHONE_EMULATOR_TEST_CLASS is required when repeating instrumentation"
    fi
    if [[ -n "$test_class" && ! "$test_class" =~ ^[A-Za-z_][A-Za-z0-9_.$]*(#[A-Za-z_][A-Za-z0-9_]*)?$ ]]; then
        fail "PHONE_EMULATOR_TEST_CLASS must be a fully-qualified class with an optional #method"
    fi
    start
    serial="$(<"$serial_file")"
    jdk="$(find_jdk)" || fail "JDK 17-21 was not found"
    setup_compiler_cache
    ensure_emulator_dependencies
    mkdir -p -- "$gradle_tmp"
    gradle_arguments=(--settings-file "$script_dir/settings.gradle")
    if [[ -n "$test_class" ]]; then
        gradle_arguments+=("-Pandroid.testInstrumentationRunnerArguments.class=$test_class")
    fi
    gradle_arguments+=(--rerun-tasks :phoneInterface:connectedEmulatorAndroidTest)
    for (( attempt = 1; attempt <= 10#$test_repetitions; ++attempt )); do
        instrumentation_log="$state_dir/instrumentation-attempt-$attempt.log"
        "$adb" -s "$serial" logcat -c >/dev/null 2>&1 || true
        printf 'Phone emulator instrumentation attempt %d/%d%s\n' \
            "$attempt" "$test_repetitions" "${test_class:+: $test_class}"
        if PHONE_EMULATOR_BUILD=1 JAVA_HOME="$jdk" ANDROID_SDK_ROOT="$sdk" \
                TMPDIR="$gradle_tmp" \
                JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$gradle_tmp ${JAVA_TOOL_OPTIONS:-}" \
                ANDROID_SERIAL="$serial" \
                "$android_root/common/gradlew" "${gradle_arguments[@]}" \
                >"$instrumentation_log" 2>&1; then
            cat -- "$instrumentation_log"
        else
            local status=$?
            cat -- "$instrumentation_log" >&2
            collect_test_diagnostics "$serial" "$attempt" "$instrumentation_log"
            return "$status"
        fi
    done
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

acquire_lifecycle_lock() {
    [[ "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]] \
        || fail "PHONE_EMULATOR_LOCK_TIMEOUT_SECONDS must be a non-negative number"
    mkdir -p -- "$(dirname -- "$lock_file")"
    [[ "${PHONE_EMULATOR_LOCK_HELD:-0}" == 1 ]] && return
    local status
    set +e
    PHONE_EMULATOR_LOCK_HELD=1 flock --close -E 75 -x -w "$lock_timeout" \
        "$lock_file" "$script_dir/phone-emulator-test.sh" "$@"
    status=$?
    set -e
    if (( status == 75 )); then
        fail "timed out waiting for phone emulator lifecycle lock"
    fi
    exit "$status"
}

case "$command_name" in
    doctor) ;;
    deps|start|build|test|stop|all) acquire_lifecycle_lock "$@" ;;
    *) fail "usage: $0 [doctor|deps|start|build|test|stop|all]" ;;
esac

case "$command_name" in
    doctor) doctor ;;
    deps) ensure_emulator_dependencies ;;
    start) start ;;
    build) build ;;
    test) test_emulator ;;
    stop) stop ;;
    all) build; test_emulator ;;
esac
