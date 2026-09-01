#!/usr/bin/env bash
set -Eeuo pipefail

readonly MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$MODULE_DIR/../lib/device-test.sh"

readonly CYCLES="${DEVICE_TEST_LIFECYCLE_CYCLES:-10}"
[[ "$CYCLES" =~ ^[1-9][0-9]*$ ]] || fail "DEVICE_TEST_LIFECYCLE_CYCLES must be a positive integer"
((CYCLES <= 1000)) || fail "DEVICE_TEST_LIFECYCLE_CYCLES must not exceed 1000"

require_installed_phone
start_phone || fail "launcher activity could not be started"
pid="$(wait_for_phone_pid 30)" || fail "application process did not start"
sleep "${DEVICE_TEST_LIFECYCLE_SETTLE_SECONDS:-3}"

for ((cycle = 1; cycle <= CYCLES; cycle++)); do
    adb_for shell input keyevent KEYCODE_HOME >/dev/null || fail "cycle $cycle: Home failed"
    sleep 2
    assert_same_pid "$pid" "cycle $cycle background"
    activity_is_backgrounded || fail "cycle $cycle: activity did not enter background"
    start_phone || fail "cycle $cycle: foreground start failed"
    sleep 3
    assert_same_pid "$pid" "cycle $cycle foreground"
    activity_is_resumed || fail "cycle $cycle: activity did not resume"
    printf '%s,%s\n' "$cycle" "$(date -u +%FT%TZ)" >>"$DEVICE_TEST_ARTIFACT_DIR/cycles.csv"
done

printf 'pid=%s\ncycles_completed=%s\n' "$pid" "$CYCLES" >"$DEVICE_TEST_ARTIFACT_DIR/metrics.env"
printf 'Completed %s lifecycle cycles without a process restart.\n' "$CYCLES"
