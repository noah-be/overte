#!/usr/bin/env bash
set -euo pipefail

ADB_BIN="${ADB_BIN:-/home/user/Android/Sdk/platform-tools/adb}"
PICO_SERIAL="${PICO_SERIAL:-192.168.188.75:5555}"
# Navigate without an explicit pose so the domain's original spawn is used.
# Use the registered Places address, not a raw domain IP. The placename lookup
# carries the authoritative destination/spawn context used by the Places app.
TARGET="hifi://overte_hub/155.084,-98.5,-397.328"
TEST_X="155.084"
TEST_Y="-98.5"
TEST_Z="-397.328"

adb_shell() {
    "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"
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
    adb_shell input keyevent KEYCODE_WAKEUP
}

safe_position() {
    # Return to the user-verified grounded test start. The requested Y is below
    # the avatar's final centre position; safe landing settles it on the nearby
    # collision surface at approximately (155.084, -97.403, -397.162).
    local nonce="${1:-$(date +%s)}"
    nonce="${nonce:0:8}"
    adb_shell setprop debug.overte.teleport \
        "${nonce}\\|${TEST_X}\\|${TEST_Y}\\|${TEST_Z}"
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
        adb_shell am start -W -a android.intent.action.MAIN \
            -c android.intent.category.LAUNCHER \
            -c com.picovr.intent.category.VR \
            -n org.overte.pico/.PermissionsActivity
        ;;
    hub)
        force_worn
        nonce="${2:-$(date +%s)}"
        safe_position "$nonce"
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
        echo "usage: $0 {start|hub [nonce]|walk [nonce duration_ms forward strafe turn]|stop [nonce]|status}" >&2
        exit 2
        ;;
esac
