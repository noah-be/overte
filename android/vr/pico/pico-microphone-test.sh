#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${ADB_BIN:-}" ]]; then
    android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    ADB_BIN="${android_sdk}/platform-tools/adb"
fi

PICO_SERIAL="${PICO_SERIAL:-${ANDROID_SERIAL:-}}"
SOURCE="${1:-voicecommunication}"
DURATION="${2:-15}"
FAN_SPEED="${3:-50}"
MAX_START_CPU_TEMP="${PICO_MIC_MAX_START_CPU_MC:-72000}"
MAX_START_GPU_TEMP="${PICO_MIC_MAX_START_GPU_MC:-70000}"
PLAYBACK_FILE="${PICO_MIC_PLAYBACK_WAV:-}"
PLAYBACK_DELAY="${PICO_MIC_PLAYBACK_DELAY:-1}"
CAPTURE_OUTPUT="${PICO_MIC_CAPTURE_OUTPUT:-}"
PACKAGE="org.overte.pico"

case "$SOURCE" in
    voicecommunication)
        EXPECTED_AUDIO_SOURCE_ID=7
        EXPECTED_AUDIO_SOURCE_NAME=VOICE_COMMUNICATION
        ;;
    voicerecognition)
        EXPECTED_AUDIO_SOURCE_ID=6
        EXPECTED_AUDIO_SOURCE_NAME=VOICE_RECOGNITION
        ;;
    mic)
        EXPECTED_AUDIO_SOURCE_ID=1
        EXPECTED_AUDIO_SOURCE_NAME=MIC
        ;;
    camcorder)
        EXPECTED_AUDIO_SOURCE_ID=5
        EXPECTED_AUDIO_SOURCE_NAME=CAMCORDER
        ;;
    *) echo "unsupported source: $SOURCE" >&2; exit 2 ;;
esac
[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || { echo "duration must be a positive integer" >&2; exit 2; }
[[ "$FAN_SPEED" == auto || "$FAN_SPEED" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
    || { echo "fan speed must be auto or an integer from 0 through 100" >&2; exit 2; }
[[ "$MAX_START_CPU_TEMP" =~ ^[1-9][0-9]*$ ]] \
    || { echo "PICO_MIC_MAX_START_CPU_MC must be a positive integer" >&2; exit 2; }
[[ "$MAX_START_GPU_TEMP" =~ ^[1-9][0-9]*$ ]] \
    || { echo "PICO_MIC_MAX_START_GPU_MC must be a positive integer" >&2; exit 2; }
[[ "$PLAYBACK_DELAY" =~ ^[0-9]+$ ]] \
    || { echo "PICO_MIC_PLAYBACK_DELAY must be a non-negative integer" >&2; exit 2; }
if [[ -n "$PLAYBACK_FILE" ]]; then
    [[ -r "$PLAYBACK_FILE" ]] || { echo "playback WAV is not readable: $PLAYBACK_FILE" >&2; exit 2; }
    (( DURATION >= 10 )) || { echo "TTS playback tests require at least 10 seconds" >&2; exit 2; }
    command -v paplay >/dev/null || { echo "paplay is required for TTS playback tests" >&2; exit 2; }
fi
capture_requested=0
if [[ -n "$PLAYBACK_FILE" || -n "$CAPTURE_OUTPUT" ]]; then
    capture_requested=1
    (( DURATION <= 60 )) \
        || { echo "raw microphone capture is limited to 60 seconds" >&2; exit 2; }
fi
capture_partial=""
if [[ -n "$CAPTURE_OUTPUT" ]]; then
    capture_directory="$(dirname -- "$CAPTURE_OUTPUT")"
    [[ -d "$capture_directory" && -w "$capture_directory" ]] \
        || { echo "capture output directory is not writable: $capture_directory" >&2; exit 2; }
    [[ ! -e "$CAPTURE_OUTPUT" ]] \
        || { echo "capture output already exists: $CAPTURE_OUTPUT" >&2; exit 2; }
    capture_partial="${CAPTURE_OUTPUT}.part"
    [[ ! -e "$capture_partial" ]] \
        || { echo "capture output partial file already exists: $capture_partial" >&2; exit 2; }
fi
if [[ "$FAN_SPEED" == 0 && "$DURATION" -gt 5 ]]; then
    echo "0% fan tests are limited to 5 seconds because XR load can overheat the headset" >&2
    exit 2
fi
if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$SCRIPT_DIR/pico-device-lock.sh" run -- "$0" "$@"
fi
[[ -x "$ADB_BIN" ]] || { echo "adb not found at $ADB_BIN" >&2; exit 2; }
if [[ -z "$PICO_SERIAL" ]]; then
    mapfile -t pico_devices < <("$ADB_BIN" devices | awk '$2 == "device" { print $1 }')
    (( ${#pico_devices[@]} == 1 )) || {
        echo "expected exactly one authorized ADB device; set PICO_SERIAL or ANDROID_SERIAL" >&2
        exit 2
    }
    PICO_SERIAL="${pico_devices[0]}"
fi

adb_shell() {
    "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"
}

read_start_temperatures() {
    local fan_status
    fan_status="$(adb_shell dumpsys pxrfanservice 2>/dev/null)"
    start_cpu_temp="$(printf '%s\n' "$fan_status" \
        | awk '/^Cpu Temperature/ { for (i=1; i<=NF; i++) if ($i ~ /^temp=/) { sub(/^temp=/, "", $i); sub(/,.*/, "", $i); if ($i+0 > max) max=$i+0 } } END { print max+0 }')"
    start_gpu_temp="$(printf '%s\n' "$fan_status" \
        | awk '/^Gpu Temperature/ { for (i=1; i<=NF; i++) if ($i ~ /^temp=/) { sub(/^temp=/, "", $i); sub(/,.*/, "", $i); if ($i+0 > max) max=$i+0 } } END { print max+0 }')"
}

refresh_worn_state() {
    adb_shell setprop sys.pxr.psensor.status 1
    adb_shell setprop sys.pxr.screenstatus 1
}

force_worn() {
    adb_shell setprop persist.pvr.psensor_checkmode 0
    adb_shell setprop persist.pvr.sleep_by_static 0
    adb_shell setprop pvr.factorytest.never.sleep 1
    refresh_worn_state
    adb_shell setprop debug.overte.test_mode 1
    adb_shell setprop debug.overte.autowalk "mic-worn\|0\|0\|0\|0"
    adb_shell input keyevent KEYCODE_WAKEUP
}

fan_test_active=0
playback_pid=""

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
    return 1
}

cleanup() {
    if [[ -n "$playback_pid" ]]; then
        kill "$playback_pid" >/dev/null 2>&1 || true
        wait "$playback_pid" >/dev/null 2>&1 || true
    fi
    adb_shell input keyevent KEYCODE_HOME >/dev/null 2>&1 || true
    adb_shell am force-stop "$PACKAGE" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_input ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_trace ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.audio_capture_seconds ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.test_mode ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.autowalk ''" >/dev/null 2>&1 || true
    adb_shell run-as "$PACKAGE" rm -f cache/pico-mic-input.wav >/dev/null 2>&1 || true
    restore_fan || true
    if [[ -n "$capture_partial" ]]; then
        rm -f -- "$capture_partial"
    fi
}
trap cleanup EXIT INT TERM HUP

adb_shell input keyevent KEYCODE_HOME >/dev/null
adb_shell am force-stop "$PACKAGE"
sleep 1

if [[ "$FAN_SPEED" == auto ]]; then
    # Recover safely if a previous interrupted fixed-fan test left test mode on.
    fan_test_active=1
    restore_fan
else
    output="$(adb_shell gd32ipdclient_test setfantestmode 1 2>&1)"
    [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
    fan_test_active=1
    output="$(adb_shell gd32ipdclient_test setfantestspeed "$FAN_SPEED" 2>&1)"
    [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
    sleep 3
    actual_fan_speed="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
        | sed -n 's/.*GetFanSpeed = //p' | head -n 1 | tr -d '\r')"
    [[ "$actual_fan_speed" == "$FAN_SPEED" ]] \
        || { echo "requested fan duty $FAN_SPEED, got ${actual_fan_speed:-unknown}" >&2; exit 1; }
fi

read_start_temperatures
if [[ "$FAN_SPEED" != auto ]] \
    && (( start_cpu_temp > MAX_START_CPU_TEMP || start_gpu_temp > MAX_START_GPU_TEMP )); then
    for cooldown_attempt in {1..3}; do
        echo "headset is warm; cooldown $cooldown_attempt/3 at 100% fan for 10 seconds" >&2
        output="$(adb_shell gd32ipdclient_test setfantestspeed 100 2>&1)"
        [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
        sleep 10
        output="$(adb_shell gd32ipdclient_test setfantestspeed "$FAN_SPEED" 2>&1)"
        [[ "$output" == *success* ]] || { echo "$output" >&2; exit 1; }
        sleep 5
        actual_fan_speed="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
            | sed -n 's/.*GetFanSpeed = //p' | head -n 1 | tr -d '\r')"
        [[ "$actual_fan_speed" == "$FAN_SPEED" ]] \
            || { echo "fan did not settle back to duty $FAN_SPEED: ${actual_fan_speed:-unknown}" >&2; exit 1; }
        read_start_temperatures
        if (( start_cpu_temp <= MAX_START_CPU_TEMP && start_gpu_temp <= MAX_START_GPU_TEMP )); then
            break
        fi
    done
fi
if (( start_cpu_temp > MAX_START_CPU_TEMP || start_gpu_temp > MAX_START_GPU_TEMP )); then
    echo "headset is too warm to start: CPU ${start_cpu_temp}mC (limit ${MAX_START_CPU_TEMP}), GPU ${start_gpu_temp}mC (limit ${MAX_START_GPU_TEMP})" >&2
    exit 1
fi
echo "preflight temperatures: CPU ${start_cpu_temp}mC, GPU ${start_gpu_temp}mC" >&2

force_worn
adb_shell setprop debug.overte.audio_input "$SOURCE"
adb_shell setprop debug.overte.audio_trace 1
if (( capture_requested )); then
    adb_shell setprop debug.overte.audio_capture_seconds "$DURATION"
    adb_shell run-as "$PACKAGE" rm -f cache/pico-mic-input.wav
fi
"$ADB_BIN" -s "$PICO_SERIAL" logcat -c
adb_shell am start -a android.intent.action.MAIN \
    -c android.intent.category.LAUNCHER \
    -c com.picovr.intent.category.VR \
    -n "$PACKAGE/.PermissionsActivity" >/dev/null
refresh_worn_state

set +o pipefail
if (( capture_requested )); then
    ready_status=1
    for _ in {1..140}; do
        if adb_shell run-as "$PACKAGE" ls cache/pico-mic-input.wav >/dev/null 2>&1; then
            ready_status=0
            break
        fi
        sleep 0.25
    done
    ready_log="capture file for $SOURCE"
else
    ready_status=1
    for _ in {1..140}; do
        ready_log="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -t 250 -v brief -s Interface \
            | grep -Em1 "PICO_MIC_(INPUT device|INPUT_REUSED) \"$SOURCE\"" || true)"
        if [[ -n "$ready_log" ]]; then
            ready_status=0
            break
        fi
        sleep 0.25
    done
fi
set -o pipefail
(( ready_status == 0 )) && [[ -n "$ready_log" ]] \
    || { echo "microphone source did not become active: $SOURCE" >&2; exit 1; }

audio_source_id="unknown"
audio_source_name="unknown"
active_input=""
for _ in {1..20}; do
    audio_flinger="$(adb_shell dumpsys media.audio_flinger 2>/dev/null)"
    active_input="$(printf '%s\n' "$audio_flinger" | awk '
        /^Input thread / { active=1 }
        active && /^- Input thread / { active=0 }
        active { print }')"
    audio_source_id="$(printf '%s\n' "$active_input" \
        | sed -n 's/^  Audio source: \([0-9][0-9]*\).*/\1/p' | head -n 1)"
    audio_source_name="$(printf '%s\n' "$active_input" \
        | sed -n 's/^  Audio source: [0-9][0-9]* (\([^)]*\)).*/\1/p' | head -n 1)"
    if [[ "$audio_source_id" == "$EXPECTED_AUDIO_SOURCE_ID" ]]; then
        break
    fi
    sleep 0.25
done
[[ -n "$audio_source_id" ]] || audio_source_id="unknown"
[[ -n "$audio_source_name" ]] || audio_source_name="unknown"
if [[ "$audio_source_id" != "$EXPECTED_AUDIO_SOURCE_ID" ]]; then
    echo "Android audio source mismatch for $SOURCE: expected $EXPECTED_AUDIO_SOURCE_ID ($EXPECTED_AUDIO_SOURCE_NAME), got $audio_source_id ($audio_source_name)" >&2
    exit 1
fi

aec_enabled=0
noise_suppression_enabled=0
if printf '%s\n' "$active_input" | grep -Fq -- '- name: Acoustic Echo Canceler'; then
    aec_enabled=1
fi
if printf '%s\n' "$active_input" | grep -Fq -- '- name: Noise Suppression'; then
    noise_suppression_enabled=1
fi

measurement_marker="PICO_MIC_MEASUREMENT_START_${SOURCE}"
adb_shell log -t OverteMicTest "$measurement_marker"

if [[ -n "$PLAYBACK_FILE" ]]; then
    (
        sleep "$PLAYBACK_DELAY"
        paplay --volume=65536 "$PLAYBACK_FILE"
    ) &
    playback_pid=$!
fi

cpu_temp="$start_cpu_temp"
gpu_temp="$start_gpu_temp"
elapsed_seconds=0
status="ok"
measurement_start_seconds=$SECONDS
measurement_deadline=$((measurement_start_seconds + DURATION))
while (( SECONDS < measurement_deadline )); do
    sleep 1
    elapsed_seconds=$((SECONDS - measurement_start_seconds))
    if (( SECONDS >= measurement_deadline )); then
        break
    fi
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
elapsed_seconds=$((SECONDS - measurement_start_seconds))
if (( elapsed_seconds > DURATION )); then
    elapsed_seconds=$DURATION
fi
measurement_end_marker="PICO_MIC_MEASUREMENT_END_${SOURCE}"
adb_shell log -t OverteMicTest "$measurement_end_marker"

if [[ -n "$playback_pid" ]]; then
    if ! wait "$playback_pid"; then
        echo "host playback failed: $PLAYBACK_FILE" >&2
        exit 1
    fi
    playback_pid=""
fi

if [[ -n "$CAPTURE_OUTPUT" ]]; then
    capture_complete=1
    for _ in {1..40}; do
        if "$ADB_BIN" -s "$PICO_SERIAL" logcat -d -t 250 -v brief -s Interface \
                | grep -Fq 'PICO_MIC_CAPTURE_COMPLETE'; then
            capture_complete=0
            break
        fi
        sleep 0.25
    done
    (( capture_complete == 0 )) \
        || { echo "raw microphone capture did not complete" >&2; exit 1; }
    "$ADB_BIN" -s "$PICO_SERIAL" exec-out run-as "$PACKAGE" \
        cat cache/pico-mic-input.wav >"$capture_partial"
    [[ -s "$capture_partial" ]] \
        || { echo "raw microphone capture is empty" >&2; exit 1; }
    mv -- "$capture_partial" "$CAPTURE_OUTPUT"
    capture_partial=""
    echo "saved raw microphone capture: $CAPTURE_OUTPUT" >&2
fi

measurement_log="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief -s Interface OverteMicTest)"
measurement_log="$(printf '%s\n' "$measurement_log" | awk \
    -v start_marker="$measurement_marker" -v end_marker="$measurement_end_marker" '
    index($0, start_marker) { found=1; next }
    found && index($0, end_marker) { done=1; next }
    found && !done { print }
')"
later_input_starts="$(printf '%s\n' "$measurement_log" \
    | grep -Fc 'PICO_MIC_INPUT device' || true)"
startup_input_starts=$((later_input_starts + 1))
startup_input_reuses="$(printf '%s\n' "$measurement_log" \
    | grep -Fc 'PICO_MIC_INPUT_REUSED' || true)"
samples="$(printf '%s\n' "$measurement_log" \
    | grep -F "PICO_MIC_LEVEL device \"$SOURCE\"" || true)"
[[ -n "$samples" ]] || { echo "no microphone level samples captured" >&2; exit 1; }
gate_samples="$(printf '%s\n' "$measurement_log" \
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
transport_samples="$(printf '%s\n' "$measurement_log" \
    | grep -F 'PICO_MIC_TRANSPORT' || true)"
[[ -n "$transport_samples" ]] \
    || { echo "no microphone transport samples captured" >&2; exit 1; }
read -r captured_pcm_frames processed_pcm_frames dropped_pcm_frames \
    backlog_pcm_frames peak_backlog_pcm_frames transport_drains <<< \
    "$(printf '%s\n' "$transport_samples" | awk '
    {
        for (i=1; i<=NF; i++) {
            if ($i == "capturedFrames") captured += $(i+1);
            if ($i == "processedFrames") processed += $(i+1);
            if ($i == "droppedFrames") dropped += $(i+1);
            if ($i == "backlogFrames") backlog = $(i+1);
            if ($i == "peakBacklogFrames" && $(i+1) > peak_backlog) peak_backlog = $(i+1);
            if ($i == "drains") drains += $(i+1);
        }
    }
    END { print captured+0, processed+0, dropped+0, backlog+0, peak_backlog+0, drains+0 }')"

fan_rpm="$(adb_shell gd32ipdclient_test getfanrpm 2>/dev/null \
    | sed -n 's/.*GetFanRPM = //p' | head -n 1)"
fan_duty="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
    | sed -n 's/.*GetFanSpeed = //p' | head -n 1)"

printf '%s\n' "$samples" | awk -v source="$SOURCE" -v requested_duration="$DURATION" \
    -v elapsed="$elapsed_seconds" -v status="$status" \
    -v startup_input_starts="$startup_input_starts" -v startup_input_reuses="$startup_input_reuses" \
    -v audio_source_id="$audio_source_id" -v audio_source_name="$audio_source_name" \
    -v aec_enabled="$aec_enabled" -v ns_enabled="$noise_suppression_enabled" \
    -v fan_rpm="$fan_rpm" -v fan_duty="$fan_duty" \
    -v gate_blocks="$gate_blocks" -v gate_open_blocks="$gate_open_blocks" \
    -v captured_pcm_frames="$captured_pcm_frames" \
    -v processed_pcm_frames="$processed_pcm_frames" \
    -v dropped_pcm_frames="$dropped_pcm_frames" \
    -v backlog_pcm_frames="$backlog_pcm_frames" \
    -v peak_backlog_pcm_frames="$peak_backlog_pcm_frames" \
    -v transport_drains="$transport_drains" \
    -v cpu_temp="$cpu_temp" -v gpu_temp="$gpu_temp" '
    {
        for (i=1; i<=NF; i++) {
            if ($i == "frames") frames += $(i+1);
            if ($i == "mean") { level += $(i+1); n++ }
            if ($i == "peak" && $(i+1) > peak) peak = $(i+1);
        }
    }
    END {
        print "source,audio_source_id,audio_source_name,aec_enabled,noise_suppression_enabled,startup_input_starts,startup_input_reuses,requested_duration_s,elapsed_s,status,samples,frames,mean_level,max_peak,gate_blocks,gate_open_blocks,gate_open_ratio,captured_pcm_frames,processed_pcm_frames,dropped_pcm_frames,backlog_pcm_frames,peak_backlog_pcm_frames,transport_drains,fan_rpm,fan_duty,cpu_temp_max_mC,gpu_temp_max_mC";
        printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%d,%d,%.6f,%.6f,%d,%d,%.6f,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n",
            source, audio_source_id, audio_source_name, aec_enabled, ns_enabled,
            startup_input_starts, startup_input_reuses, requested_duration, elapsed, status,
            n, frames, n ? level/n : 0, peak,
            gate_blocks, gate_open_blocks, gate_blocks ? gate_open_blocks/gate_blocks : 0,
            captured_pcm_frames, processed_pcm_frames, dropped_pcm_frames,
            backlog_pcm_frames, peak_backlog_pcm_frames, transport_drains,
            fan_rpm, fan_duty, cpu_temp, gpu_temp;
    }'

[[ "$status" == "ok" ]]
