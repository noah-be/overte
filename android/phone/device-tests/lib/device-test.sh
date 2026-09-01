#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEVICE_TEST_ADB:?DEVICE_TEST_ADB is required}"
: "${DEVICE_TEST_SERIAL:?DEVICE_TEST_SERIAL is required}"
: "${DEVICE_TEST_ARTIFACT_DIR:?DEVICE_TEST_ARTIFACT_DIR is required}"

readonly DEVICE_TEST_PACKAGE="${DEVICE_TEST_PACKAGE:-org.overte.phone}"
readonly DEVICE_TEST_ACTIVITY="${DEVICE_TEST_ACTIVITY:-org.overte.phone/.PermissionsActivity}"

adb_for() {
    "$DEVICE_TEST_ADB" -s "$DEVICE_TEST_SERIAL" "$@"
}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

skip() {
    printf 'SKIP: %s\n' "$*"
    exit 77
}

phone_pid() {
    adb_for shell pidof -s "$DEVICE_TEST_PACKAGE" 2>/dev/null | tr -d '\r' || true
}

wait_for_phone_pid() {
    local attempt pid
    for attempt in $(seq 1 "${1:-20}"); do
        pid="$(phone_pid)"
        if [[ "$pid" =~ ^[0-9]+$ ]]; then
            printf '%s\n' "$pid"
            return 0
        fi
        sleep 1
    done
    return 1
}

assert_same_pid() {
    local expected="$1" phase="$2" observed
    observed="$(phone_pid)"
    [[ -n "$observed" ]] || fail "$phase: application process exited"
    [[ "$observed" == "$expected" ]] || fail "$phase: application process restarted"
}

activity_is_resumed() {
    adb_for shell dumpsys activity activities 2>/dev/null | grep -Eq \
        '(mResumedActivity|topResumedActivity).*org\.overte\.phone/(\.PhoneInterfaceActivity|org\.overte\.phone\.PhoneInterfaceActivity)'
}

activity_is_backgrounded() {
    local state
    state="$(adb_for shell dumpsys activity activities 2>/dev/null)" || return 1
    grep -Eq '(mResumedActivity|topResumedActivity)' <<<"$state" &&
        ! grep -Eq '(mResumedActivity|topResumedActivity).*org\.overte\.phone/' <<<"$state"
}

start_phone() {
    adb_for shell am start -W -n "$DEVICE_TEST_ACTIVITY" >/dev/null
}

require_installed_phone() {
    adb_for shell pm path "$DEVICE_TEST_PACKAGE" >/dev/null 2>&1 || \
        skip "$DEVICE_TEST_PACKAGE is not installed"
}
