#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$SCRIPT_DIR/pico-device-lock.sh" run -- "$0" "$@"
fi

ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}/platform-tools/adb}"
PACKAGE="org.overte.pico"
ACTIVITY="$PACKAGE/.PermissionsActivity"
TARGET="hifi://overte_hub/155.084,-98.5,-397.328"
RUNS=5
TIMEOUT=120
SETTLE=8
POST_TIMEOUT=120
QUIET_SECONDS=10
OUTPUT=""

usage() {
    cat <<'EOF'
Usage: ./pico-world-loading-test.sh [options]

Measure verified overte_hub entry milestones on a Pico connected through WLAN ADB.

  --runs N       Number of cold-process runs (default: 5)
  --timeout SEC  Per-run world loading timeout (default: 120)
  --settle SEC   Local startup scene settling time (default: 8)
  --post-timeout SEC  Maximum observation after screen release (default: 120)
  --quiet SEC     Required seconds without loading activity (default: 10)
  --output FILE  CSV output (default: power-results/<timestamp>-world-loading.csv)
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --runs) RUNS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --settle) SETTLE="$2"; shift 2 ;;
        --post-timeout) POST_TIMEOUT="$2"; shift 2 ;;
        --quiet) QUIET_SECONDS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for value in "$RUNS" "$TIMEOUT" "$POST_TIMEOUT" "$QUIET_SECONDS"; do
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo "runs and timeout must be positive integers" >&2; exit 2; }
done
[[ "$SETTLE" =~ ^[0-9]+$ ]] || { echo "settle must be a non-negative integer" >&2; exit 2; }
[[ -x "$ADB_BIN" ]] || { echo "adb not found at $ADB_BIN" >&2; exit 2; }

if [[ -z "${PICO_SERIAL:-${ANDROID_SERIAL:-}}" ]]; then
    mapfile -t wlan_devices < <("$ADB_BIN" devices | awk '$2 == "device" && $1 ~ /:/ { print $1 }')
    (( ${#wlan_devices[@]} == 1 )) || {
        echo "expected exactly one authorized WLAN ADB device; set PICO_SERIAL" >&2
        exit 2
    }
    PICO_SERIAL="${wlan_devices[0]}"
else
    PICO_SERIAL="${PICO_SERIAL:-${ANDROID_SERIAL}}"
fi
[[ "$PICO_SERIAL" == *:* ]] || { echo "refusing non-WLAN ADB endpoint" >&2; exit 2; }

adb_shell() { "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"; }
fan_test_active=0
brightness_test_active=0
original_brightness=""
cleanup() {
    adb_shell setprop debug.overte.navigate '' >/dev/null 2>&1 || true
    adb_shell setprop debug.overte.test_mode '' >/dev/null 2>&1 || true
    if (( brightness_test_active )); then
        adb_shell gd32ipdclient_test setbrightness "$original_brightness" >/dev/null 2>&1 || true
        brightness_test_active=0
    fi
    if (( fan_test_active )); then
        adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
        fan_test_active=0
    fi
}
trap cleanup EXIT INT TERM

original_brightness="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null \
    | sed -n 's/.*GetBrightness = //p' | head -n 1)"
[[ "$original_brightness" =~ ^([0-9]|[1-9][0-9]|100)$ ]] || {
    echo "could not read Pico display brightness" >&2; exit 1;
}
brightness_output="$(adb_shell gd32ipdclient_test setbrightness 1 2>&1)"
[[ "$brightness_output" == *success* ]] || { echo "could not set brightness to 1%" >&2; exit 1; }
brightness_test_active=1
adb_shell gd32ipdclient_test setfantestmode 1 >/dev/null
fan_test_active=1
adb_shell gd32ipdclient_test setfantestspeed 100 >/dev/null
sleep 2
actual_brightness="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null \
    | sed -n 's/.*GetBrightness = //p' | head -n 1)"
actual_fan="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
    | sed -n 's/.*GetFanSpeed = //p' | head -n 1)"
[[ "$actual_brightness" == 1 && "$actual_fan" == 100 ]] || {
    echo "failed to verify brightness=1% and fan=100%" >&2; exit 1;
}
echo "test controls verified: brightness=1% fan=100%"

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="$SCRIPT_DIR/power-results/$(date -u +%Y%m%dT%H%M%SZ)-world-loading.csv"
fi
mkdir -p "$(dirname -- "$OUTPUT")"
[[ ! -e "$OUTPUT" ]] || { echo "refusing to overwrite $OUTPUT" >&2; exit 2; }
SAMPLES_OUTPUT="${OUTPUT%.csv}-samples.csv"
[[ ! -e "$SAMPLES_OUTPUT" ]] || { echo "refusing to overwrite $SAMPLES_OUTPUT" >&2; exit 2; }
printf '%s\n' 'run,started_epoch_ms,domain_connect_ms,first_world_data_ms,entity_sequence_complete_ms,safe_landing_complete_ms,gpu_ready_ms,physics_enabled_ms,playable_frame_ms,loading_screen_release_ms,postload_quiet_ms,total_settled_ms,domain_to_world_ms,world_to_sequence_ms,sequence_to_safe_landing_ms,safe_landing_to_gpu_ms,gpu_to_physics_ms,physics_to_playable_ms,playable_to_release_ms,tracked_entities,received_sequences,expected_sequences,recovery_attempts,gpu_fallback,presented_frames,manual_dismissal,domain_resets' > "$OUTPUT"
printf '%s\n' 'run,epoch_ms,elapsed_ms,loading_screen_visible,active_downloads,pending_downloads,processing_resources,pending_processing,atp_started,http_started,atp_success,http_success,atp_failed,http_failed,atp_bytes,http_bytes,entity_packets,entity_packet_bytes,running_interface_scripts,gpu_memory_bytes,tracked_entities,maximum_tracked_entities,physics_blocked_entities,visually_blocked_entities,received_sequences,expected_sequences,completion_received,full_scenes_received,entity_script_loads,entity_script_preloads_finished,active_script_resources,active_model_resources,active_texture_resources,active_audio_resources,active_other_resources,physics_enabled,safe_landing_complete_ms,gpu_ready_ms,physics_enabled_ms,playable_frame_ms,measurement_started_epoch_ms,domain_resets' > "$SAMPLES_OUTPUT"

collect_sample() {
    local run_number="$1" sample sample_fields
    sample="$(adb_shell run-as "$PACKAGE" cat cache/world-loading-sample 2>/dev/null | tr -d '\r' || true)"
    sample_fields="$(awk -F'|' '{ print NF }' <<< "$sample")"
    [[ "$sample_fields" == 41 ]] || return 1
    IFS='|' read -r sample_epoch sample_elapsed sample_screen sample_active sample_pending \
        sample_processing sample_pending_processing sample_atp_started sample_http_started \
        sample_atp_success sample_http_success sample_atp_failed sample_http_failed sample_atp_bytes \
        sample_http_bytes sample_entity_packets sample_entity_bytes sample_scripts sample_gpu \
        sample_tracked sample_max_tracked sample_physics_blocked sample_visually_blocked \
        sample_received_sequences sample_expected_sequences sample_completion sample_full_scenes \
        sample_entity_script_loads sample_entity_script_preloads sample_active_scripts sample_active_models \
        sample_active_textures sample_active_audio sample_active_other sample_physics_enabled \
        sample_safe_ms sample_gpu_ms sample_physics_ms sample_ready_ms sample_measurement_epoch \
        sample_domain_reconnects <<< "$sample"
    [[ "$sample_epoch" =~ ^[0-9]+$ && "$sample_epoch" -ge $((command_epoch_ms - 5000)) ]] || return 1
    if [[ "$sample_epoch" != "${last_sample_epoch:-}" ]]; then
        last_sample_epoch="$sample_epoch"
        printf '%s,%s\n' "$run_number" "${sample//|/,}" >> "$SAMPLES_OUTPUT"
        return 0
    fi
    return 1
}

for (( run=1; run<=RUNS; ++run )); do
    echo "world loading run $run/$RUNS"
    adb_shell am force-stop "$PACKAGE"
    adb_shell setprop debug.overte.test_mode 1
    adb_shell setprop persist.pvr.psensor_checkmode 0
    adb_shell setprop persist.pvr.sleep_by_static 0
    adb_shell setprop pvr.factorytest.never.sleep 1
    adb_shell setprop sys.pxr.psensor.status 1
    adb_shell setprop sys.pxr.screenstatus 1
    adb_shell input keyevent KEYCODE_WAKEUP
    adb_shell am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
        -c com.picovr.intent.category.VR -n "$ACTIVITY" >/dev/null

    started_wait=0
    until adb_shell pidof "$PACKAGE" >/dev/null 2>&1; do
        sleep 1
        started_wait=$((started_wait + 1))
        (( started_wait < 30 )) || { echo "app did not start" >&2; exit 1; }
    done
    sleep "$SETTLE"
    adb_shell run-as "$PACKAGE" rm -f cache/world-loading-status
    adb_shell run-as "$PACKAGE" rm -f cache/world-loading-sample
    nonce="$(date +%s%N)"
    command_epoch_ms="$(date +%s%3N)"
    last_sample_epoch=""
    adb_shell setprop debug.overte.navigate "${nonce}\\|${TARGET}"

    status=""
    for (( second=0; second<TIMEOUT; ++second )); do
        collect_sample "$run" || true
        status="$(adb_shell run-as "$PACKAGE" cat cache/world-loading-status 2>/dev/null | tr -d '\r' || true)"
        if [[ -n "$status" ]]; then
            IFS='|' read -r epoch domain world sequence safe gpu physics ready release \
                entities received expected recovery fallback frames dismissed reconnects <<< "$status"
            fields="$(awk -F'|' '{ print NF }' <<< "$status")"
            if [[ "$fields" == 17 && "$epoch" =~ ^[0-9]+$ && "$epoch" -ge $((command_epoch_ms - 5000)) ]]; then
                break
            fi
        fi
        sleep 1
    done
    [[ -n "$status" && "${fields:-0}" == 17 ]] || { echo "timed out waiting for loading telemetry" >&2; exit 1; }

    for value in "$domain" "$world" "$sequence" "$safe" "$gpu" "$physics" "$ready" "$release"; do
        [[ "$value" =~ ^[0-9]+$ ]] || { echo "invalid or missing milestone: $status" >&2; exit 1; }
    done
    (( domain <= world && world <= sequence && sequence <= safe && safe <= gpu && gpu <= physics && physics <= ready && ready <= release )) || {
        echo "out-of-order loading milestones: $status" >&2; exit 1;
    }
    world_status="$(adb_shell run-as "$PACKAGE" cat cache/world-status 2>/dev/null | tr -d '\r' || true)"
    IFS='|' read -r _ connected place domain_id _ <<< "$world_status"
    [[ "$connected" == 1 && "${place,,}" == overte_hub && -n "$domain_id" ]] || {
        echo "telemetry completed outside overte_hub: ${world_status:-missing}" >&2; exit 1;
    }

    quiet_samples=0
    quiet_at=-1
    last_activity_signature=""
    for (( second=0; second<POST_TIMEOUT; ++second )); do
        sleep 1
        if collect_sample "$run"; then
            activity_signature="$sample_atp_started:$sample_http_started:$sample_entity_packets:$sample_scripts:$sample_entity_script_loads:$sample_entity_script_preloads"
            if (( sample_active == 0 && sample_pending == 0 && sample_processing == 0 && sample_pending_processing == 0 )) &&
                    [[ "$activity_signature" == "$last_activity_signature" ]]; then
                quiet_samples=$((quiet_samples + 1))
            else
                quiet_samples=0
            fi
            last_activity_signature="$activity_signature"
            if (( quiet_samples >= QUIET_SECONDS )); then
                quiet_at="$sample_elapsed"
                break
            fi
        fi
    done
    postload_quiet_ms=-1
    if (( quiet_at >= 0 )); then
        postload_quiet_ms=$((quiet_at - release))
    else
        echo "warning: world did not reach a ${QUIET_SECONDS}s quiet state after ${POST_TIMEOUT}s" >&2
    fi

    printf '%s\n' "$run,$epoch,$domain,$world,$sequence,$safe,$gpu,$physics,$ready,$release,$postload_quiet_ms,$quiet_at,$((world-domain)),$((sequence-world)),$((safe-sequence)),$((gpu-safe)),$((physics-gpu)),$((ready-physics)),$((release-ready)),$entities,$received,$expected,$recovery,$fallback,$frames,$dismissed,$reconnects" >> "$OUTPUT"
done

cleanup
trap - EXIT INT TERM
echo "results=$OUTPUT"
echo "samples=$SAMPLES_OUTPUT"
