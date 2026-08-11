#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCK_SCRIPT="$SCRIPT_DIR/../pico-device-lock.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pico-device-lock-test.XXXXXX")"
LOCK_FILE="$TEST_ROOT/device.lock"
READY_FILE="$TEST_ROOT/holder.ready"
DAEMON_PID_FILE="$TEST_ROOT/daemon.pid"
PASSED=0
FAILED=0

cleanup() {
    if [[ -n "${holder_pid:-}" ]]; then
        wait "$holder_pid" >/dev/null 2>&1 || true
    fi
    if [[ -s "$DAEMON_PID_FILE" ]]; then
        kill "$(<"$DAEMON_PID_FILE")" >/dev/null 2>&1 || true
    fi
    if [[ -d "$TEST_ROOT" && "$(basename -- "$TEST_ROOT")" == pico-device-lock-test.* ]]; then
        rm -rf -- "$TEST_ROOT"
    fi
}
trap cleanup EXIT

if PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
        | grep -Fq 'Pico headset is available'; then
    PASSED=$((PASSED + 1))
    echo 'PASS available_status'
else
    FAILED=$((FAILED + 1))
    echo 'FAIL available_status' >&2
fi

PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- \
    bash -c 'printf ready >"$1"; sleep 2' bash "$READY_FILE" &
holder_pid=$!
for _ in {1..40}; do
    [[ -e "$READY_FILE" ]] && break
    sleep 0.05
done
[[ -e "$READY_FILE" ]] || { echo 'FAIL holder_start' >&2; exit 1; }

set +e
busy_output="$(PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status 2>&1)"
busy_code=$?
set -e
if [[ "$busy_code" == 1 && "$busy_output" == *'Pico headset is in use:'* && \
      "$busy_output" == *'branch='* ]]; then
    PASSED=$((PASSED + 1))
    echo 'PASS busy_status'
else
    FAILED=$((FAILED + 1))
    printf 'FAIL busy_status (exit=%s output=%q)\n' "$busy_code" "$busy_output" >&2
fi

wait_output="$(PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- printf acquired 2>&1)"
if [[ "$wait_output" == *'Pico headset is in use; waiting:'* && \
      "$wait_output" == *acquired* ]]; then
    PASSED=$((PASSED + 1))
    echo 'PASS wait_then_acquire'
else
    FAILED=$((FAILED + 1))
    printf 'FAIL wait_then_acquire (output=%q)\n' "$wait_output" >&2
fi
wait "$holder_pid"
holder_pid=""

if [[ ! -e "${LOCK_FILE}.owner" ]] && \
   PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
        | grep -Fq 'Pico headset is available'; then
    PASSED=$((PASSED + 1))
    echo 'PASS release_and_metadata_cleanup'
else
    FAILED=$((FAILED + 1))
    echo 'FAIL release_and_metadata_cleanup' >&2
fi

PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- \
    bash -c 'sleep 10 </dev/null >/dev/null 2>&1 & printf "%s" "$!" >"$1"' bash "$DAEMON_PID_FILE"
if PICO_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
        | grep -Fq 'Pico headset is available'; then
    PASSED=$((PASSED + 1))
    echo 'PASS child_daemon_does_not_inherit_lock'
else
    FAILED=$((FAILED + 1))
    echo 'FAIL child_daemon_does_not_inherit_lock' >&2
fi

printf 'Totals: %s passed, %s failed\n' "$PASSED" "$FAILED"
(( FAILED == 0 ))
