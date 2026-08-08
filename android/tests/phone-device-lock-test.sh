#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCK_SCRIPT="$SCRIPT_DIR/../phone-device-lock.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/phone-device-lock-test.XXXXXX")"
LOCK_FILE="$TEST_ROOT/device.lock"
READY_FILE="$TEST_ROOT/holder.ready"

cleanup() {
    if [[ -n "${holder_pid:-}" ]]; then
        wait "$holder_pid" >/dev/null 2>&1 || true
    fi
    if [[ -d "$TEST_ROOT" && "$(basename -- "$TEST_ROOT")" == phone-device-lock-test.* ]]; then
        rm -rf -- "$TEST_ROOT"
    fi
}
trap cleanup EXIT

PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
    | grep -Fq 'Android phone is available'

PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- \
    bash -c 'printf ready >"$1"; sleep 1' bash "$READY_FILE" &
holder_pid=$!
for _ in {1..40}; do
    [[ -e "$READY_FILE" ]] && break
    sleep 0.025
done
[[ -e "$READY_FILE" ]] || { echo 'FAIL: lock holder did not start' >&2; exit 1; }

set +e
busy_output="$(PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status 2>&1)"
busy_code=$?
set -e
[[ "$busy_code" == 1 && "$busy_output" == *'Android phone is in use:'* && \
   "$busy_output" == *'branch='* ]] || {
    printf 'FAIL: busy status was not reported safely\n' >&2
    exit 1
}

wait_output="$(PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- printf acquired 2>&1)"
[[ "$wait_output" == *'Android phone is in use; waiting:'* && \
   "$wait_output" == *acquired* ]] || {
    echo 'FAIL: waiting caller did not acquire the released lock' >&2
    exit 1
}
wait "$holder_pid"
holder_pid=""

[[ ! -e "${LOCK_FILE}.owner" ]]
PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
    | grep -Fq 'Android phone is available'

printf 'PASS: Android phone device lock serialization\n'
