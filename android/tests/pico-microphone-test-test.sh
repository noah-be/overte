#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONTROL_SCRIPT="$SCRIPT_DIR/../pico-microphone-test.sh"
MOCK_ADB="$SCRIPT_DIR/pico-microphone-mock-adb.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pico-microphone-test.XXXXXX")"
PASSED=0
FAILED=0

cleanup() {
    if [[ -d "$TEST_ROOT" && "$(basename -- "$TEST_ROOT")" == pico-microphone-test.* ]]; then
        rm -rf -- "$TEST_ROOT"
    fi
}
trap cleanup EXIT

run_failure_case() {
    local name="$1" expected_code="$2" expected_text="$3"
    shift 3
    local state_dir="$TEST_ROOT/$name" output code
    mkdir -p "$state_dir"
    set +e
    output="$(env ADB_BIN="$MOCK_ADB" MOCK_MIC_STATE_DIR="$state_dir" \
        PICO_DEVICE_LOCK_HELD=1 "$@" 2>&1)"
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

run_failure_case unsupported_source 2 'unsupported source' \
    "$CONTROL_SCRIPT" invalid 1 auto
run_failure_case invalid_duration 2 'duration must be a positive integer' \
    "$CONTROL_SCRIPT" mic 0 auto
run_failure_case invalid_fan 2 'fan speed must be auto' \
    "$CONTROL_SCRIPT" mic 1 101
run_failure_case unsafe_fan_off 2 '0% fan tests are limited to 5 seconds' \
    "$CONTROL_SCRIPT" mic 6 0
run_failure_case missing_playback 2 'playback WAV is not readable' \
    env PICO_MIC_PLAYBACK_WAV="$TEST_ROOT/missing.wav" "$CONTROL_SCRIPT" mic 10 auto
run_failure_case excessive_capture 2 'raw microphone capture is limited to 60 seconds' \
    env PICO_MIC_CAPTURE_OUTPUT="$TEST_ROOT/too-long.wav" "$CONTROL_SCRIPT" mic 61 auto

existing_output="$TEST_ROOT/existing.wav"
printf 'keep' >"$existing_output"
run_failure_case existing_capture 2 'capture output already exists' \
    env PICO_MIC_CAPTURE_OUTPUT="$existing_output" "$CONTROL_SCRIPT" mic 1 auto
[[ "$(<"$existing_output")" == keep ]] || {
    printf 'FAIL existing_capture overwrote its target\n' >&2
    FAILED=$((FAILED + 1))
}

run_failure_case multiple_devices 2 'expected exactly one authorized ADB device' \
    env MOCK_DEVICE_COUNT=2 "$CONTROL_SCRIPT" mic 1 auto
run_failure_case mismatched_android_source 1 'Android audio source mismatch' \
    env MOCK_AUDIO_SOURCE_MISMATCH=1 "$CONTROL_SCRIPT" voicecommunication 1 auto

success_state="$TEST_ROOT/success"
capture_output="$TEST_ROOT/capture.wav"
mkdir -p "$success_state"
set +e
success_output="$(env ADB_BIN="$MOCK_ADB" MOCK_MIC_STATE_DIR="$success_state" \
    PICO_MIC_CAPTURE_OUTPUT="$capture_output" \
    PICO_DEVICE_LOCK_FILE="$success_state/device.lock" \
    "$CONTROL_SCRIPT" voicecommunication 1 auto 2>&1)"
success_code=$?
set -e
expected_row='voicecommunication,7,VOICE_COMMUNICATION,1,1,1,0,1,1,ok,1,48000,2.000000,5.000000,100,30,0.300000,48000,48000,0,0,960,100,7000,45,65000,60000'
if [[ "$success_code" == 0 && "$success_output" == *"$expected_row"* && \
      "$success_output" == *"saved raw microphone capture: $capture_output"* && \
      -s "$capture_output" && "$(head -c 4 "$capture_output")" == RIFF ]]; then
    PASSED=$((PASSED + 1))
    printf 'PASS successful_capture_and_csv\n'
else
    FAILED=$((FAILED + 1))
    printf 'FAIL successful_capture_and_csv (exit=%s output=%q)\n' \
        "$success_code" "$success_output" >&2
fi

if [[ ! -e "$success_state/device.lock.owner" ]] && \
   grep -Fq 'setfantestmode 0' "$success_state/commands.log" && \
   grep -Fq "setprop debug.overte.audio_capture_seconds ''" "$success_state/commands.log" && \
   grep -Fq 'run-as org.overte.pico rm -f cache/pico-mic-input.wav' "$success_state/commands.log" && \
   grep -Fq 'am force-stop org.overte.pico' "$success_state/commands.log"; then
    PASSED=$((PASSED + 1))
    printf 'PASS cleanup_and_fan_restore\n'
else
    FAILED=$((FAILED + 1))
    printf 'FAIL cleanup_and_fan_restore\n' >&2
fi

printf 'Totals: %s passed, %s failed\n' "$PASSED" "$FAILED"
(( FAILED == 0 ))
