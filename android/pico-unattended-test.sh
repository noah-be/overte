#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$SCRIPT_DIR/pico-device-lock.sh" run -- "$0" "$@"
fi
if [[ -z "${ADB_BIN:-}" ]]; then
    android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    ADB_BIN="${android_sdk}/platform-tools/adb"
fi

if [[ ! -x "$ADB_BIN" ]]; then
    echo "adb not found at ${ADB_BIN}; set ADB_BIN, ANDROID_SDK_ROOT, or ANDROID_HOME" >&2
    exit 2
fi
PICO_SERIAL="${PICO_SERIAL:-${ANDROID_SERIAL:-}}"
if [[ -z "$PICO_SERIAL" ]]; then
    mapfile -t pico_devices < <("$ADB_BIN" devices | awk '$2 == "device" { print $1 }')
    (( ${#pico_devices[@]} == 1 )) || {
        echo "expected exactly one authorized ADB device; set PICO_SERIAL or ANDROID_SERIAL" >&2
        exit 2
    }
    PICO_SERIAL="${pico_devices[0]}"
fi
# Navigate without an explicit pose so the domain's original spawn is used.
# Use the registered Places address, not a raw domain IP. The placename lookup
# carries the authoritative destination/spawn context used by the Places app.
TARGET="hifi://overte_hub/155.084,-98.5,-397.328"
TARGET_PLACE="overte_hub"
TEST_X="155.084"
TEST_Y="-98.5"
TEST_Z="-397.328"

adb_shell() {
    "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"
}

stop_autowalk() {
    local nonce="${1:-stop-$(date +%s%N)}"
    adb_shell setprop debug.overte.autowalk "${nonce}\\|0\\|0\\|0\\|0"
}

force_worn() {
    # Disable Pico's physical proximity check and keep both the Android display
    # and XR runtime in their worn/active state. The persist property survives
    # a reboot; the sys properties are deliberately refreshed for every run.
    adb_shell setprop persist.pvr.psensor_checkmode 0
    adb_shell setprop persist.pvr.sleep_by_static 0
    adb_shell setprop pvr.factorytest.never.sleep 1
    adb_shell setprop sys.pxr.psensor.status 1
    adb_shell setprop sys.pxr.screenstatus 1
    adb_shell setprop debug.overte.test_mode 1
    # Android debug properties survive app restarts. Replace any previous
    # locomotion command before Interface can replay it on a fresh launch.
    stop_autowalk "worn-$(date +%s%N)"
    adb_shell input keyevent KEYCODE_WAKEUP
}

safe_position() {
    # Return to the user-verified grounded test start. The requested Y is below
    # the avatar's final centre position; safe landing settles it on the nearby
    # collision surface at approximately (155.084, -97.403, -397.162).
    local nonce="${1:-$(date +%s)}"
    stop_autowalk "${nonce}-stop"
    adb_shell setprop debug.overte.teleport \
        "${nonce}\\|${TEST_X}\\|${TEST_Y}\\|${TEST_Z}"
}

set_avatar_replicas() {
    local count="$1"
    [[ "$count" =~ ^[0-9]+$ ]] && (( count <= 50 )) || {
        echo "replica count must be an integer from 0 through 50" >&2
        return 2
    }
    adb_shell setprop debug.overte.avatar_replicas "$(date +%s)\\|${count}"
}

set_local_avatar_template() {
    local enabled="$1"
    [[ "$enabled" == "0" || "$enabled" == "1" ]] || {
        echo "local avatar template state must be 0 or 1" >&2
        return 2
    }
    adb_shell setprop debug.overte.avatar_local_template "$(date +%s)\\|${enabled}"
}

get_fresh_avatar_status() {
    local status status_epoch field_count now
    status="$(adb_shell run-as org.overte.pico cat cache/avatar-status 2>/dev/null || true)"
    field_count="$(awk -F'|' '{ print NF }' <<<"$status")"
    IFS='|' read -r status_epoch _ <<<"$status"
    now="$(date +%s)"
    [[ "$field_count" == "20" && "$status_epoch" =~ ^[0-9]+$ ]] &&
        (( now - status_epoch >= -5 && now - status_epoch <= 5 )) || return 1
    printf '%s\n' "$status"
}

print_avatar_status() {
    local status status_epoch total replicated target updated not_updated heroes simulation_ms
    local processing_ms priority_build_ms sort_ms pre_update_ms state_poll_ms ensure_scene_ms
    local scale_animation_ms simulate_ms loaded_other loaded_replicated local_template template_refreshes now
    status="$(get_fresh_avatar_status || true)"
    IFS='|' read -r status_epoch total replicated target updated not_updated heroes simulation_ms \
        processing_ms priority_build_ms sort_ms pre_update_ms state_poll_ms ensure_scene_ms \
        scale_animation_ms simulate_ms loaded_other loaded_replicated local_template template_refreshes <<<"$status"
    now="$(date +%s)"
    if [[ ! "$status_epoch" =~ ^[0-9]+$ ]] ||
            (( now - status_epoch < -5 || now - status_epoch > 5 )) ||
            [[ "$local_template" != "0" && "$local_template" != "1" ]] ||
            [[ ! "$template_refreshes" =~ ^[0-9]+$ ]]; then
        echo "missing or stale avatar status: ${status:-missing}" >&2
        return 1
    fi
    printf 'avatars=%s replicated=%s target_per_avatar=%s updated=%s not_updated=%s heroes=%s simulation_ms=%s processing_ms=%s priority_build_ms=%s sort_ms=%s pre_update_ms=%s state_poll_ms=%s ensure_scene_ms=%s scale_animation_ms=%s simulate_ms=%s loaded_other=%s loaded_replicated=%s local_template=%s template_refreshes=%s\n' \
        "$total" "$replicated" "$target" "$updated" "$not_updated" "$heroes" "$simulation_ms" \
        "$processing_ms" "$priority_build_ms" "$sort_ms" "$pre_update_ms" "$state_poll_ms" \
        "$ensure_scene_ms" "$scale_animation_ms" "$simulate_ms" "$loaded_other" "$loaded_replicated" "$local_template" "$template_refreshes"
}

wait_for_world() {
    local timeout="${1:-60}" elapsed=0 status status_epoch connected place domain_id now
    while (( elapsed < timeout )); do
        status="$(adb_shell run-as org.overte.pico cat cache/world-status 2>/dev/null || true)"
        IFS='|' read -r status_epoch connected place domain_id _ <<<"$status"
        now="$(date +%s)"
        if [[ "$status_epoch" =~ ^[0-9]+$ ]] &&
            (( now - status_epoch >= -5 && now - status_epoch <= 5 )) &&
            [[ "$connected" == "1" && "${place,,}" == "$TARGET_PLACE" ]] &&
            [[ "$domain_id" =~ ^\{?[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}\}?$ ]] &&
            [[ "$domain_id" != "{00000000-0000-0000-0000-000000000000}" ]]; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "failed to verify connected world '$TARGET_PLACE' (status: ${status:-missing})" >&2
    return 1
}

verify_spawn() {
    # Collect several stationary samples and reject the run if the avatar did
    # not settle at the user-confirmed grounded position.
    local check_nonce="${1:-spawn}c"
    "$ADB_BIN" -s "$PICO_SERIAL" logcat -c
    safe_position "${1:-spawn}"
    sleep 5
    adb_shell setprop debug.overte.autowalk "${check_nonce}\\|0\\|0\\|0\\|5000"
    sleep 6
    local samples
    samples="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief | \
        sed -n 's/.*PICO_ADB_AUTOWALK_ACTIVE position (\([^,]*\), \([^,]*\), \([^)]*\)).*/\1 \2 \3/p')"
    if ! awk '
        BEGIN { n=0; minY=1e9; maxY=-1e9 }
        { x=$1; y=$2; z=$3; n++; if (n > 1 && y<minY) minY=y; if (n > 1 && y>maxY) maxY=y; lastX=x; lastY=y; lastZ=z }
        END {
            valid = n >= 3 && lastX > 154.75 && lastX < 155.55 &&
                    lastY > -97.60 && lastY < -97.20 &&
                    lastZ > -397.55 && lastZ < -396.70 &&
                    (maxY - minY) < 0.03;
            exit valid ? 0 : 1;
        }' <<<"$samples"; then
        echo "unsafe or unsettled original spawn; locomotion cancelled" >&2
        printf '%s\n' "$samples" >&2
        return 1
    fi
}

case "${1:-status}" in
    start)
        force_worn
        adb_shell am start -a android.intent.action.MAIN \
            -c android.intent.category.LAUNCHER \
            -c com.picovr.intent.category.VR \
            -n org.overte.pico/.PermissionsActivity
        ;;
    hub)
        force_worn
        nonce="${2:-$(date +%s)}"
        # Navigation and in-domain teleport are separate commands. Teleporting
        # alone would leave Interface in whichever domain was already open.
        adb_shell setprop debug.overte.navigate "${nonce}\\|${TARGET}"
        wait_for_world 60
        safe_position "$nonce"
        sleep 5
        status="$(adb_shell run-as org.overte.pico cat cache/world-status 2>/dev/null || true)"
        IFS='|' read -r status_epoch connected place domain_id x y z <<<"$status"
        if [[ "$connected" != "1" || "${place,,}" != "$TARGET_PLACE" ||
                "$domain_id" == "{00000000-0000-0000-0000-000000000000}" ]] ||
            ! awk -v x="$x" -v y="$y" -v z="$z" 'BEGIN {
                dx=x-155.084; dy=y-(-97.403); dz=z-(-397.162);
                exit (dx*dx + dy*dy + dz*dz <= 4.0) ? 0 : 1;
            }'; then
            echo "Hub world/position verification failed (status: ${status:-missing})" >&2
            exit 1
        fi
        echo "verified world=$place domain=$domain_id position=$x,$y,$z"
        ;;
    walk)
        force_worn
        nonce="${2:-$(date +%s)}"
        duration_ms="${3:-30000}"
        forward="${4:-0.75}"
        strafe="${5:-0.0}"
        turn="${6:-0.12}"
        verify_spawn "${nonce}-position"
        "$ADB_BIN" -s "$PICO_SERIAL" logcat -c
        # A completed or interrupted test must never leave the avatar somewhere
        # along the synthetic route. Restore the domain's original spawn on
        # normal exit as well as Ctrl-C/termination.
        trap 'safe_position "${nonce}-return"' EXIT INT TERM
        adb_shell setprop debug.overte.autowalk \
            "${nonce}\\|${forward}\\|${strafe}\\|${turn}\\|${duration_ms}"
        # Monitor the known Hub test route while it runs. A late collision or
        # streaming wave must not leave the avatar falling through geometry or
        # continuing inside an entity. Normal samples stay close to Y=-97..-99.
        elapsed_ms=0
        while (( elapsed_ms < duration_ms + 500 )); do
            sleep 1
            elapsed_ms=$((elapsed_ms + 1000))
            latest_y="$("$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief | \
                sed -n 's/.*PICO_ADB_AUTOWALK_ACTIVE position ([^,]*, \([^,]*\), [^)]*).*/\1/p' | tail -n 1)"
            if [[ -n "$latest_y" ]] && ! awk -v y="$latest_y" 'BEGIN { exit (y > -100.0 && y < -95.0) ? 0 : 1 }'; then
                echo "unsafe route height ${latest_y}; locomotion aborted" >&2
                adb_shell setprop debug.overte.autowalk "${nonce}-abort\\|0\\|0\\|0\\|0"
                break
            fi
        done
        safe_position "${nonce}-return"
        trap - EXIT INT TERM
        sleep 3
        ;;
    stop)
        nonce="${2:-$(date +%s)}"
        adb_shell setprop debug.overte.autowalk "${nonce}\\|0\\|0\\|0\\|0"
        ;;
    replicas)
        count="${2:-0}"
        [[ "$count" =~ ^[0-9]+$ ]] || {
            echo "replica count must be an integer from 0 through 50" >&2
            exit 2
        }
        count=$((10#$count))
        (( count <= 50 )) || {
            echo "replica count must be an integer from 0 through 50" >&2
            exit 2
        }
        force_worn
        set_avatar_replicas "$count"
        for attempt in {1..30}; do
            sleep 1
            status="$(get_fresh_avatar_status || true)"
            IFS='|' read -ra avatar_fields <<<"$status"
            target="${avatar_fields[3]:-}"
            if [[ "$target" == "$count" ]]; then
                print_avatar_status
                exit 0
            fi
        done
        echo "Interface did not apply avatar replica count $count" >&2
        exit 1
        ;;
    avatar-template)
        enabled="${2:-0}"
        force_worn
        set_local_avatar_template "$enabled"
        for attempt in {1..30}; do
            sleep 1
            status="$(get_fresh_avatar_status || true)"
            IFS='|' read -ra avatar_fields <<<"$status"
            active_template="${avatar_fields[18]:-}"
            if [[ "$active_template" == "$enabled" ]]; then
                print_avatar_status
                exit 0
            fi
        done
        echo "Interface did not apply local avatar template state $enabled" >&2
        exit 1
        ;;
    avatar-status)
        print_avatar_status
        ;;
    status)
        printf 'pid: '
        adb_shell pidof org.overte.pico || true
        printf 'proximity check: '
        adb_shell getprop persist.pvr.psensor_checkmode
        printf 'worn: '
        adb_shell getprop sys.pxr.psensor.status
        printf 'screen: '
        adb_shell getprop sys.pxr.screenstatus
        ;;
    *)
        printf 'usage: %s %s\n' "$0" \
            '{start|hub [nonce]|walk [nonce duration_ms forward strafe turn]|stop [nonce]|replicas [0..50]|avatar-template [0|1]|avatar-status|status}' >&2
        exit 2
        ;;
esac
