#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ADB_BIN:-}" ]]; then
    android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    ADB_BIN="${android_sdk}/platform-tools/adb"
fi

PICO_SERIAL="${PICO_SERIAL:-192.168.188.75:5555}"
SOURCE="${1:-voicecommunication}"
DURATION="${2:-15}"
FAN_SPEED="${3:-auto}"
PACKAGE="org.overte.pico"

case "$SOURCE" in
    voicecommunication|voicerecognition|mic|camcorder) ;;
    *) echo "unsupported source: $SOURCE" >&2; exit 2 ;;
esac
[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || { echo "duration must be a positive integer" >&2; exit 2; }
[[ "$FAN_SPEED" == auto || "$FAN_SPEED" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
    || { echo "fan speed must be auto or an integer from 0 through 100" >&2; exit 2; }
if [[ "$FAN_SPEED" == 0 && "$DURATION" -gt 5 ]]; then
    echo "0% fan tests are limited to 5 seconds because XR load can overheat the headset" >&2
    exit 2
fi
[[ -x "$ADB_BIN" ]] || { echo "adb not found at $ADB_BIN" >&2; exit 2; }

adb_shell() {
    "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"
}

fan_test_active=0

restore_fan() {
    local auto_state actual_state attempt
    (( fan_test_active == 1 )) || return 0
    adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
    for attempt in {1..10}; do
        auto_state="$(adb_shell dumpsys pxrfanservice 2>/dev/null \
            | sed -n 's/^mFanState=//p' | head -n 1 | tr -d '\r')"
        actual_state="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
            | sed -n 's/.*GetFanSpeed = //p' | head -n 1 | tr -d '\r')"
        if [[ -n "$auto_state" && "$actual_state" == "$auto_state" ]]; then
            echo "automatic fan control restored at duty $actual_state" >&2
            fan_test_active=0
            return 0
        fi
        if [[ "$auto_state" =~ ^([0-9]|[1-9][0-9]|100)$ ]]; then
            adb_shell gd32ipdclient_test setfanspeed "$auto_state" >/dev/null 2>&1 || true
        fi
        sleep 1
    done
    echo "warning: automatic fan control could not be verified" >&2
    fan_test_active=0
}

cleanup() {
    adb_shell input keyevent KEYCODE_HOME >/dev/null 2>&1 || true
    adb_shell am force-stop "$PACKAGE" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_input ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_trace ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_capture_seconds ''" >/dev/null 2>&1 || true
    restore_fan
}
trap cleanup EXIT INT TERM HUP

if [[ "$FAN_SPEED" != auto ]]; then
    output="$(adb_shell gd32ipdclient_test setfantestmode 1 2>&1)"
    [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
    fan_test_active=1
    output="$(adb_shell gd32ipdclient_test setfantestspeed "$FAN_SPEED" 2>&1)"
    [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
    sleep 3
fi

adb_shell input keyevent KEYCODE_HOME >/dev/null
adb_shell am force-stop "$PACKAGE"
sleep 1
adb_shell setprop debug.overte.audio_input "$SOURCE"
adb_shell setprop debug.overte.audio_trace 1
"$ADB_BIN" -s "$PICO_SERIAL" logcat -c
adb_shell am start -a android.intent.action.MAIN \
    -c android.intent.category.LAUNCHER \
    -n "$PACKAGE/.PermissionsActivity" >/dev/null

ready=0
for _ in {1..35}; do
    if "$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief \
        | grep -Fq "PICO_MIC_INPUT device \"$SOURCE\""; then
        ready=1
        break
    fi
    sleep 1
done
(( ready == 1 )) || { echo "microphone source did not become active: $SOURCE" >&2; exit 1; }

"$ADB_BIN" -s "$PICO_SERIAL" logcat -c

cpu_temp=0
gpu_temp=0
elapsed_seconds=0
status="ok"
for (( elapsed = 0; elapsed < DURATION; ++elapsed )); do
    sleep 1
    elapsed_seconds=$((elapsed + 1))
    fan_status="$(adb_shell dumpsys pxrfanservice 2>/dev/null)"
    current_cpu_temp="$(printf '%s\n' "$fan_status" \
        | awk '/^Cpu Temperature/ { for (i=1; i<=NF; i++) if ($i ~ /^temp=/) { sub(/^temp=/, "", $i); sub(/,.*/, "", $i); if ($i+0 > max) max=$i+0 } } END { print max+0 }')"
    current_gpu_temp="$(printf '%s\n' "$fan_status" \
        | awk '/^Gpu Temperature/ { for (i=1; i<=NF; i++) if ($i ~ /^temp=/) { sub(/^temp=/, "", $i); sub(/,.*/, "", $i); if ($i+0 > max) max=$i+0 } } END { print max+0 }')"
    if (( current_cpu_temp > cpu_temp )); then
        cpu_temp="$current_cpu_temp"
    fi
    if (( current_gpu_temp > gpu_temp )); then
        gpu_temp="$current_gpu_temp"
    fi
    if (( current_cpu_temp >= 90000 || current_gpu_temp >= 85000 )); then
        echo "temperature limit reached: CPU ${current_cpu_temp}mC, GPU ${current_gpu_temp}mC" >&2
        status="thermal_limit"
        break
    fi
done

samples="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief \
    | grep -F "PICO_MIC_LEVEL device \"$SOURCE\"" || true)"
[[ -n "$samples" ]] || { echo "no microphone level samples captured" >&2; exit 1; }
gate_samples="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief \
    | grep -F "PICO_MIC_GATE device \"$SOURCE\"" || true)"
[[ -n "$gate_samples" ]] || { echo "no microphone gate samples captured" >&2; exit 1; }
read -r gate_blocks gate_open_blocks <<< "$(printf '%s\n' "$gate_samples" | awk '
    {
        for (i=1; i<=NF; i++) {
            if ($i == "blocks") blocks += $(i+1);
            if ($i == "openBlocks") open_blocks += $(i+1);
        }
    }
    END { print blocks+0, open_blocks+0 }')"

fan_rpm="$(adb_shell gd32ipdclient_test getfanrpm 2>/dev/null \
    | sed -n 's/.*GetFanRPM = //p' | head -n 1)"
fan_duty="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
    | sed -n 's/.*GetFanSpeed = //p' | head -n 1)"

printf '%s\n' "$samples" | awk -v source="$SOURCE" -v requested_duration="$DURATION" \
    -v elapsed="$elapsed_seconds" -v status="$status" \
    -v fan_rpm="$fan_rpm" -v fan_duty="$fan_duty" \
    -v gate_blocks="$gate_blocks" -v gate_open_blocks="$gate_open_blocks" \
    -v cpu_temp="$cpu_temp" -v gpu_temp="$gpu_temp" '
    {
        for (i=1; i<=NF; i++) {
            if ($i == "frames") frames += $(i+1);
            if ($i == "mean") { level += $(i+1); n++ }
            if ($i == "peak" && $(i+1) > peak) peak = $(i+1);
        }
    }
    END {
        print "source,requested_duration_s,elapsed_s,status,samples,frames,mean_level,max_peak,gate_blocks,gate_open_blocks,gate_open_ratio,fan_rpm,fan_duty,cpu_temp_max_mC,gpu_temp_max_mC";
        printf "%s,%s,%s,%s,%d,%d,%.6f,%.6f,%d,%d,%.6f,%s,%s,%s,%s\n", source,
            requested_duration, elapsed, status, n, frames, n ? level/n : 0, peak,
            gate_blocks, gate_open_blocks, gate_blocks ? gate_open_blocks/gate_blocks : 0,
            fan_rpm, fan_duty, cpu_temp, gpu_temp;
    }'

[[ "$status" == "ok" ]]
