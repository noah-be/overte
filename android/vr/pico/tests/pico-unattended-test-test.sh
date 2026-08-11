#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONTROL_SCRIPT="$SCRIPT_DIR/../pico-unattended-test.sh"
MOCK_ADB="$SCRIPT_DIR/pico-mock-adb.sh"
PASSED=0
FAILED=0

run_case() {
    local name="$1" expected_code="$2" expected_text="$3" device_count="$4" serial="$5" status="$6"
    shift 6
    local output code
    set +e
    output="$(env ADB_BIN="$MOCK_ADB" MOCK_DEVICE_COUNT="$device_count" \
        MOCK_AVATAR_STATUS="$status" PICO_SERIAL="$serial" PICO_DEVICE_LOCK_HELD=1 \
        "$CONTROL_SCRIPT" "$@" 2>&1)"
    code=$?
    set -e
    if [[ "$code" == "$expected_code" && "$output" == *"$expected_text"* ]]; then
        PASSED=$((PASSED + 1))
        printf 'PASS %s\n' "$name"
    else
        FAILED=$((FAILED + 1))
        printf 'FAIL %s (exit=%s output=%q)\n' "$name" "$code" "$output" >&2
    fi
}

now="$(date +%s)"
valid_status="$now|2|0|0|1|0|0|1.000|1.200|0.200|0.000|0.100|0.040|0.050|0.010|1.000|1|0|1|42"
legacy_status="${valid_status%|42}"
stale_status="$((now - 20))|${valid_status#*|}"
invalid_refresh="${valid_status%|42}|invalid"
replica_status="$now|7|5|5|3|3|0|3.000|3.200|0.200|0.000|0.100|0.040|0.050|0.010|3.000|6|5|1|35"

run_case valid_status 0 'template_refreshes=42' 1 '' "$valid_status" avatar-status
run_case explicit_serial 0 'template_refreshes=42' 0 'mock-explicit' "$valid_status" avatar-status
run_case no_device 2 'expected exactly one authorized ADB device' 0 '' "$valid_status" avatar-status
run_case multiple_devices 2 'expected exactly one authorized ADB device' 2 '' "$valid_status" avatar-status
run_case legacy_schema 1 'missing or stale avatar status' 1 '' "$legacy_status" avatar-status
run_case stale_schema 1 'missing or stale avatar status' 1 '' "$stale_status" avatar-status
run_case invalid_refresh 1 'missing or stale avatar status' 1 '' "$invalid_refresh" avatar-status
run_case replicas_response 0 'target_per_avatar=5' 1 '' "$replica_status" replicas 5
run_case template_response 0 'local_template=1' 1 '' "$valid_status" avatar-template 1

printf 'Totals: %s passed, %s failed\n' "$PASSED" "$FAILED"
(( FAILED == 0 ))
