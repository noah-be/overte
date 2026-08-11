#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCK_SCRIPT="$SCRIPT_DIR/../phone-device-lock.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/phone-device-lock-test.XXXXXX")"
LOCK_FILE="$TEST_ROOT/device.lock"
READY_FILE="$TEST_ROOT/holder.ready"
DAEMON_PID_FILE="$TEST_ROOT/daemon.pid"
SIGNAL_CHILD_PID_FILE="$TEST_ROOT/signal-child.pid"

cleanup() {
    if [[ -n "${holder_pid:-}" ]]; then
        wait "$holder_pid" >/dev/null 2>&1 || true
    fi
    if [[ -s "$DAEMON_PID_FILE" ]]; then
        kill "$(<"$DAEMON_PID_FILE")" >/dev/null 2>&1 || true
    fi
    if [[ -s "$SIGNAL_CHILD_PID_FILE" ]]; then
        kill "$(<"$SIGNAL_CHILD_PID_FILE")" >/dev/null 2>&1 || true
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
grep -Fq 'phase=active' "${LOCK_FILE}.owner" || {
    echo 'FAIL: active Phone lock phase was not recorded' >&2
    exit 1
}

set +e
busy_output="$(PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status 2>&1)"
busy_code=$?
set -e
[[ "$busy_code" == 1 && "$busy_output" == *'Android phone is in use:'* && \
   "$busy_output" == *'branch='* ]] || {
    printf 'FAIL: busy status was not reported safely\n' >&2
    exit 1
}

for _ in {1..80}; do
    grep -Fq 'phase=cooldown' "${LOCK_FILE}.owner" 2>/dev/null && break
    sleep 0.025
done
grep -Fq 'phase=cooldown' "${LOCK_FILE}.owner" || {
    echo 'FAIL: Phone lock cooldown phase was not observable' >&2
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

set +e
PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- bash -c 'exit 23'
child_status=$?
set -e
[[ "$child_status" == 23 ]] || {
    echo 'FAIL: Phone lock did not preserve the child exit status' >&2
    exit 1
}

PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- sleep 0.2 &
holder_pid=$!
for _ in {1..40}; do
    [[ -s "${LOCK_FILE}.owner" ]] && break
    sleep 0.025
done
wait_output="$(PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" wait 2>&1)"
[[ "$wait_output" == *'Android phone is in use; waiting:'* &&
   "$wait_output" == *'Android phone is available'* ]] || {
    echo 'FAIL: Phone lock wait did not block and report availability' >&2
    exit 1
}
wait "$holder_pid"
holder_pid=""

for invalid in 'status extra' 'wait extra' 'run' 'run command' 'run --'; do
    read -r -a invalid_arguments <<<"$invalid"
    set +e
    PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" "${invalid_arguments[@]}" \
        >"$TEST_ROOT/invalid.out" 2>&1
    invalid_status=$?
    set -e
    [[ "$invalid_status" == 2 ]] || {
        printf 'FAIL: invalid Phone lock grammar was accepted: %s\n' "$invalid" >&2
        exit 1
    }
done

PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- \
    bash -c 'printf "%s" "$$" >"$1"; exec sleep 30' bash "$SIGNAL_CHILD_PID_FILE" &
holder_pid=$!
for _ in {1..40}; do
    [[ -s "$SIGNAL_CHILD_PID_FILE" ]] && break
    sleep 0.025
done
kill -TERM "$holder_pid"
kill -TERM "$(<"$SIGNAL_CHILD_PID_FILE")" >/dev/null 2>&1 || true
for _ in {1..40}; do
    grep -Fq 'phase=cooldown' "${LOCK_FILE}.owner" 2>/dev/null && break
    sleep 0.025
done
grep -Fq 'phase=cooldown' "${LOCK_FILE}.owner" || {
    echo 'FAIL: signaled Phone lock skipped its cooldown' >&2
    exit 1
}
set +e
wait "$holder_pid"
signal_status=$?
set -e
holder_pid=""
[[ "$signal_status" == 143 && ! -e "${LOCK_FILE}.owner" ]] || {
    echo 'FAIL: TERM did not normalize to 143 and clean Phone lock metadata' >&2
    exit 1
}

PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" run -- \
    bash -c 'sleep 15 </dev/null >/dev/null 2>&1 & printf "%s" "$!" >"$1"' \
    bash "$DAEMON_PID_FILE"
PHONE_DEVICE_LOCK_FILE="$LOCK_FILE" "$LOCK_SCRIPT" status \
    | grep -Fq 'Android phone is available' || {
        echo 'FAIL: child daemon inherited the Phone lock descriptor' >&2
        exit 1
    }

printf 'PASS: Android phone device lock serialization\n'
