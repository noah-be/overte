#!/usr/bin/env bash
set -Eeuo pipefail

readonly MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$MODULE_DIR/../lib/device-test.sh"

readonly DURATION="${DEVICE_TEST_IDLE_SECONDS:-300}"
readonly INTERVAL="${DEVICE_TEST_SAMPLE_SECONDS:-5}"
[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || fail "DEVICE_TEST_IDLE_SECONDS must be a positive integer"
[[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]] || fail "DEVICE_TEST_SAMPLE_SECONDS must be a positive integer"
((DURATION <= 7200)) || fail "DEVICE_TEST_IDLE_SECONDS must not exceed 7200"

require_installed_phone
start_phone || fail "launcher activity could not be started"
pid="$(wait_for_phone_pid 30)" || fail "application process did not start"
sleep "${DEVICE_TEST_IDLE_SETTLE_SECONDS:-3}"
activity_is_resumed || fail "PhoneInterfaceActivity is not resumed"

printf 'elapsed_seconds,pid,total_pss_kb,total_rss_kb\n' >"$DEVICE_TEST_ARTIFACT_DIR/process.csv"
started="$(date +%s)"
while :; do
    now="$(date +%s)"
    elapsed=$((now - started))
    ((elapsed < DURATION)) || break
    assert_same_pid "$pid" "idle soak after ${elapsed}s"
    read -r pss rss < <(adb_for shell dumpsys meminfo "$DEVICE_TEST_PACKAGE" | awk '
        /^TOTAL[[:space:]]/ { print $2 + 0, $3 + 0; found=1; exit }
        END { if (!found) print "0 0" }
    ')
    printf '%s,%s,%s,%s\n' "$elapsed" "$pid" "$pss" "$rss" >>"$DEVICE_TEST_ARTIFACT_DIR/process.csv"
    sleep "$INTERVAL"
done

assert_same_pid "$pid" "idle soak completion"
activity_is_resumed || fail "PhoneInterfaceActivity is not resumed after idle soak"
adb_for shell dumpsys meminfo "$DEVICE_TEST_PACKAGE" >"$DEVICE_TEST_ARTIFACT_DIR/meminfo-final.txt" 2>&1 || true
adb_for shell dumpsys gfxinfo "$DEVICE_TEST_PACKAGE" framestats >"$DEVICE_TEST_ARTIFACT_DIR/gfxinfo-final.txt" 2>&1 || true
printf 'pid=%s\nduration_seconds=%s\n' "$pid" "$DURATION" >"$DEVICE_TEST_ARTIFACT_DIR/metrics.env"
printf 'Application process remained stable for %s seconds.\n' "$DURATION"
