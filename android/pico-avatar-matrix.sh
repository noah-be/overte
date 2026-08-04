#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/platform-tools/adb}"
PICO_SERIAL="${PICO_SERIAL:-192.168.188.75:5555}"
PACKAGE="org.overte.pico"
DURATION="${DURATION:-30}"
INTERVAL="${INTERVAL:-5}"
SETTLE="${SETTLE:-15}"
LOAD_WAIT="${LOAD_WAIT:-30}"
RESULT_DIR="${RESULT_DIR:-$SCRIPT_DIR/power-results/avatar-matrix-$(date -u +%Y%m%dT%H%M%SZ)}"
REPLICA_COUNTS=()

usage() {
    cat <<'EOF'
Usage: ./pico-avatar-matrix.sh [options]

Measure the already-running Pico client with repeated client-only avatar loads.
The current domain must contain at least one other avatar. The test rejects XR
focus loss or a change in the number of real template avatars and always clears
local replicas on exit. It does not capture screenshots or avatar identifiers.

Options:
  --replicas COUNT       Append a 0..50 replicas-per-template stage
  --duration SECONDS     Measurement duration per stage (default: 30)
  --interval SECONDS     Telemetry interval (default: 5)
  --settle SECONDS       Delay after each load becomes ready (default: 15)
  --load-wait SECONDS    Maximum wait for avatar population changes (default: 30)
  --result-dir DIR       Output directory
  -h, --help             Show this help

If --replicas is omitted, the sequence is: 0, 5, 0, 5.
Environment overrides: ADB_BIN, PICO_SERIAL, DURATION, INTERVAL, SETTLE,
LOAD_WAIT, and RESULT_DIR.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --replicas) [[ $# -ge 2 ]] || { echo "--replicas requires a value" >&2; exit 2; }; REPLICA_COUNTS+=("$2"); shift 2 ;;
        --duration) [[ $# -ge 2 ]] || { echo "--duration requires a value" >&2; exit 2; }; DURATION="$2"; shift 2 ;;
        --interval) [[ $# -ge 2 ]] || { echo "--interval requires a value" >&2; exit 2; }; INTERVAL="$2"; shift 2 ;;
        --settle) [[ $# -ge 2 ]] || { echo "--settle requires a value" >&2; exit 2; }; SETTLE="$2"; shift 2 ;;
        --load-wait) [[ $# -ge 2 ]] || { echo "--load-wait requires a value" >&2; exit 2; }; LOAD_WAIT="$2"; shift 2 ;;
        --result-dir) [[ $# -ge 2 ]] || { echo "--result-dir requires a value" >&2; exit 2; }; RESULT_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || { echo "duration must be a positive integer" >&2; exit 2; }
[[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]] || { echo "interval must be a positive integer" >&2; exit 2; }
[[ "$SETTLE" =~ ^[0-9]+$ ]] || { echo "settle must be a non-negative integer" >&2; exit 2; }
[[ "$LOAD_WAIT" =~ ^[1-9][0-9]*$ ]] || { echo "load wait must be a positive integer" >&2; exit 2; }
(( ${#REPLICA_COUNTS[@]} > 0 )) || REPLICA_COUNTS=(0 5 0 5)
for index in "${!REPLICA_COUNTS[@]}"; do
    count="${REPLICA_COUNTS[$index]}"
    [[ "$count" =~ ^[0-9]+$ ]] || { echo "replica counts must be integers from 0 through 50" >&2; exit 2; }
    count=$((10#$count))
    (( count <= 50 )) || { echo "replica counts must be integers from 0 through 50" >&2; exit 2; }
    REPLICA_COUNTS[$index]="$count"
done
[[ -x "$ADB_BIN" ]] || { echo "adb not executable: $ADB_BIN" >&2; exit 1; }

adb_shell() { "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"; }

foreground_package() {
    adb_shell dumpsys activity activities 2>/dev/null \
        | sed -n 's/.*mResumedActivity:.* u0 \([^/ ]*\).*/\1/p' \
        | head -n 1
}

validate_xr_focus() {
    local stage="$1" active_package boundary_ready guardian_vst current_pid
    active_package="$(foreground_package)"
    boundary_ready="$(adb_shell getprop sys.pxr.boundary.ready 2>/dev/null | tr -d '\r')"
    guardian_vst="$(adb_shell getprop sys.guardian.vst.status 2>/dev/null | tr -d '\r')"
    [[ "$active_package" == "$PACKAGE" ]] || {
        echo "Overte lost XR focus during $stage (active: ${active_package:-unknown})" >&2
        return 1
    }
    [[ "$boundary_ready" != "0" && "$guardian_vst" != "1" ]] || {
        echo "Pico Guardian/Seethrough is active during $stage" \
            "(boundary_ready=${boundary_ready:-unknown}, guardian_vst=${guardian_vst:-unknown})" >&2
        return 1
    }
    if [[ -n "${PID:-}" ]]; then
        current_pid="$(adb_shell pidof "$PACKAGE" 2>/dev/null | tr -d '\r')"
        [[ "$current_pid" == "$PID" ]] || {
            echo "Overte restarted during $stage (expected PID $PID, active: ${current_pid:-none})" >&2
            return 1
        }
    fi
}

read_avatar_status() {
    local status now
    status="$(adb_shell run-as "$PACKAGE" cat cache/avatar-status 2>/dev/null || true)"
    IFS='|' read -r AVATAR_EPOCH AVATAR_TOTAL AVATAR_REPLICATED AVATAR_TARGET \
        AVATAR_UPDATED AVATAR_NOT_UPDATED AVATAR_HEROES AVATAR_SIMULATION_MS <<<"$status"
    now="$(date +%s)"
    [[ "$AVATAR_EPOCH" =~ ^[0-9]+$ ]] &&
        (( now - AVATAR_EPOCH >= -5 && now - AVATAR_EPOCH <= 5 )) &&
        [[ "$AVATAR_TOTAL" =~ ^[0-9]+$ && "$AVATAR_REPLICATED" =~ ^[0-9]+$ &&
            "$AVATAR_TARGET" =~ ^[0-9]+$ && "$AVATAR_SIMULATION_MS" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

real_avatar_count() {
    printf '%s\n' "$((AVATAR_TOTAL - AVATAR_REPLICATED - 1))"
}

set_replicas() {
    local count="$1"
    PICO_SERIAL="$PICO_SERIAL" PACKAGE="$PACKAGE" \
        "$SCRIPT_DIR/pico-unattended-test.sh" replicas "$count" >/dev/null
}

wait_for_replica_load() {
    local count="$1" timeout="${2:-$LOAD_WAIT}" elapsed=0 real expected_replicated
    while (( elapsed < timeout )); do
        if read_avatar_status && [[ "$AVATAR_TARGET" == "$count" ]]; then
            real="$(real_avatar_count)"
            expected_replicated=$((real * count))
            if (( real > 0 && AVATAR_REPLICATED == expected_replicated )); then
                printf '%s\n' "$real"
                return 0
            fi
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "avatar load did not settle at $count replicas per real avatar" >&2
    return 1
}

"$ADB_BIN" -s "$PICO_SERIAL" get-state >/dev/null
adb_shell run-as "$PACKAGE" true >/dev/null 2>&1 || {
    echo "$PACKAGE must be installed as a debuggable app" >&2
    exit 1
}

mkdir -p "$RESULT_DIR"
RESULT_DIR="$(cd -- "$RESULT_DIR" && pwd)"
ORIGINAL_BRIGHTNESS="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_FAN_SPEED="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_TEST_MODE="$(adb_shell getprop debug.overte.test_mode 2>/dev/null | tr -d '\r')"

cleanup() {
    local cleanup_status cleanup_epoch cleanup_total cleanup_replicated cleanup_target cleanup_rest
    adb_shell setprop debug.overte.avatar_replicas "$(date +%s)\\|0" >/dev/null 2>&1 || true
    # Give the running app a chance to remove replicas before disabling a test
    # mode that was off when the matrix started.
    for _ in 1 2 3; do
        cleanup_status="$(adb_shell run-as "$PACKAGE" cat cache/avatar-status 2>/dev/null || true)"
        IFS='|' read -r cleanup_epoch cleanup_total cleanup_replicated cleanup_target cleanup_rest <<<"$cleanup_status"
        [[ "$cleanup_target" == "0" ]] && break
        sleep 1
    done
    adb_shell setprop debug.overte.test_mode "${ORIGINAL_TEST_MODE:-0}" >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_FAN_SPEED" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setfantestspeed "$ORIGINAL_FAN_SPEED" >/dev/null 2>&1 || true
    fi
    adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_BRIGHTNESS" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setbrightness "$ORIGINAL_BRIGHTNESS" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

validate_xr_focus "avatar matrix setup"
PID="$(adb_shell pidof "$PACKAGE" | tr -d '\r')"
[[ -n "$PID" ]] || { echo "$PACKAGE is not running" >&2; exit 1; }

adb_shell setprop debug.overte.test_mode 1 >/dev/null
set_replicas 0
REAL_TEMPLATES="$(wait_for_replica_load 0)"
(( REAL_TEMPLATES > 0 )) || { echo "the current domain has no other avatar template" >&2; exit 1; }

adb_shell gd32ipdclient_test setfantestmode 1 >/dev/null
adb_shell gd32ipdclient_test setfantestspeed 100 >/dev/null
adb_shell gd32ipdclient_test setbrightness 1 >/dev/null

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_commit=%s\n' "$(git -C "$SCRIPT_DIR/.." rev-parse HEAD)"
    printf 'serial=%s\npackage=%s\npid=%s\n' "$PICO_SERIAL" "$PACKAGE" "$PID"
    printf 'real_template_avatars=%s\nduration_s=%s\ninterval_s=%s\nsettle_s=%s\nload_wait_s=%s\n' \
        "$REAL_TEMPLATES" "$DURATION" "$INTERVAL" "$SETTLE" "$LOAD_WAIT"
    printf 'replica_sequence=%s\n' "${REPLICA_COUNTS[*]}"
} > "$RESULT_DIR/metadata.txt"
printf 'run,replicas_per_template,total_avatars,local_replicas,real_templates,mean_cpu_pct,mean_avatar_simulation_ms,mean_updated,mean_not_updated\n' \
    > "$RESULT_DIR/summary.csv"

run_number=0
for count in "${REPLICA_COUNTS[@]}"; do
    run_number=$((run_number + 1))
    label="r$(printf '%02d' "$run_number")-replicas-$count"
    output="$RESULT_DIR/$label"
    mkdir -p "$output"

    set_replicas "$count"
    loaded_real="$(wait_for_replica_load "$count")"
    [[ "$loaded_real" == "$REAL_TEMPLATES" ]] || {
        echo "real avatar template count changed before $label ($REAL_TEMPLATES -> $loaded_real)" >&2
        exit 1
    }
    sleep "$SETTLE"
    validate_xr_focus "$label warm-up"
    read_avatar_status || { echo "missing avatar status after $label warm-up" >&2; exit 1; }
    [[ "$(real_avatar_count)" == "$REAL_TEMPLATES" ]] || {
        echo "real avatar template count changed during $label warm-up" >&2
        exit 1
    }

    printf 'epoch,cpu_pct,total_avatars,local_replicas,real_templates,updated,not_updated,heroes,avatar_simulation_ms\n' \
        > "$output/telemetry.csv"
    elapsed=0
    while (( elapsed < DURATION )); do
        validate_xr_focus "$label measurement at ${elapsed}s"
        read_avatar_status || { echo "missing avatar status during $label" >&2; exit 1; }
        real="$(real_avatar_count)"
        [[ "$real" == "$REAL_TEMPLATES" && "$AVATAR_TARGET" == "$count" &&
            "$AVATAR_REPLICATED" == "$((real * count))" ]] || {
            echo "avatar population changed during $label" >&2
            exit 1
        }
        top_line="$(adb_shell top -b -n 1 -p "$PID" 2>/dev/null | tail -n 1 | tr -d '\r')"
        cpu="$(awk '{gsub(/%/, "", $9); print $9}' <<<"$top_line")"
        [[ "$cpu" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "invalid CPU sample during $label" >&2; exit 1; }
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$(date +%s)" "$cpu" "$AVATAR_TOTAL" \
            "$AVATAR_REPLICATED" "$real" "$AVATAR_UPDATED" "$AVATAR_NOT_UPDATED" "$AVATAR_HEROES" \
            "$AVATAR_SIMULATION_MS" >> "$output/telemetry.csv"
        sleep "$INTERVAL"
        elapsed=$((elapsed + INTERVAL))
    done

    validate_xr_focus "$label completion"
    read_avatar_status || { echo "missing avatar status after $label" >&2; exit 1; }
    real="$(real_avatar_count)"
    [[ "$real" == "$REAL_TEMPLATES" && "$AVATAR_TARGET" == "$count" &&
        "$AVATAR_REPLICATED" == "$((real * count))" ]] || {
        echo "avatar population changed before $label completion" >&2
        exit 1
    }

    read -r mean_cpu mean_simulation mean_updated mean_not_updated < <(awk -F, \
        'NR > 1 { cpu += $2; updated += $6; notUpdated += $7; sim += $9; n++ }
        END { if (n > 0) printf "%.3f %.3f %.3f %.3f\n", cpu / n, sim / n, updated / n, notUpdated / n; else exit 1 }' \
        "$output/telemetry.csv")
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$run_number" "$count" "$AVATAR_TOTAL" "$AVATAR_REPLICATED" \
        "$REAL_TEMPLATES" "$mean_cpu" "$mean_simulation" "$mean_updated" "$mean_not_updated" \
        >> "$RESULT_DIR/summary.csv"
    printf '%s mean_cpu=%s mean_avatar_simulation_ms=%s mean_updated=%s mean_not_updated=%s\n' \
        "$label" "$mean_cpu" "$mean_simulation" "$mean_updated" "$mean_not_updated"
done

printf 'replicas_per_template,total_avatars,runs,mean_cpu_pct,mean_avatar_simulation_ms,mean_updated,mean_not_updated\n' \
    > "$RESULT_DIR/aggregate.csv"
awk -F, 'NR > 1 {
    replicas = $2
    if (!(replicas in seen)) {
        seen[replicas] = 1
        order[++orderCount] = replicas
    }
    total[replicas] = $3
    runs[replicas]++
    cpu[replicas] += $6
    simulation[replicas] += $7
    updated[replicas] += $8
    notUpdated[replicas] += $9
}
END {
    for (i = 1; i <= orderCount; i++) {
        replicas = order[i]
        printf "%s,%s,%d,%.3f,%.3f,%.3f,%.3f\n", replicas, total[replicas], runs[replicas],
            cpu[replicas] / runs[replicas], simulation[replicas] / runs[replicas],
            updated[replicas] / runs[replicas], notUpdated[replicas] / runs[replicas]
    }
}' "$RESULT_DIR/summary.csv" >> "$RESULT_DIR/aggregate.csv"

echo "results=$RESULT_DIR"
