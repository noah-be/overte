#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_ARGS=("$@")
ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/platform-tools/adb}"
PICO_SERIAL="${PICO_SERIAL:-${ANDROID_SERIAL:-}}"
PACKAGE="org.overte.pico"
DURATION="${DURATION:-30}"
INTERVAL="${INTERVAL:-5}"
SETTLE="${SETTLE:-15}"
LOAD_WAIT="${LOAD_WAIT:-30}"
RESULT_DIR="${RESULT_DIR:-$SCRIPT_DIR/power-results/avatar-matrix-$(date -u +%Y%m%dT%H%M%SZ)}"
REPLICA_COUNTS=()
MATRIX_DOMAIN_ID=""
TEMPLATE_MODE="local"
EXPECTED_LOCAL_TEMPLATE="1"

usage() {
    cat <<'EOF'
Usage: ./pico-avatar-matrix.sh [options]

Measure the already-running Pico client with repeated client-only avatar loads.
By default, the domain must contain no other user: the tool creates one local
template from MyAvatar and removes it on exit. The test rejects XR focus loss
or any source-population change and never captures screenshots or avatar IDs.

Options:
  --replicas COUNT       Append a 0..50 replicas-per-template stage
  --duration SECONDS     Measurement duration per stage (default: 30)
  --interval SECONDS     Telemetry interval (default: 5)
  --settle SECONDS       Delay after each load becomes ready (default: 15)
  --load-wait SECONDS    Maximum wait for avatar population changes (default: 30)
  --result-dir DIR       Output directory
  --received-template    Use already-received avatars instead of a local template
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
        --received-template) TEMPLATE_MODE="received"; EXPECTED_LOCAL_TEMPLATE="0"; shift ;;
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
if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$SCRIPT_DIR/pico-device-lock.sh" run -- "$0" "${ORIGINAL_ARGS[@]}"
fi
[[ -x "$ADB_BIN" ]] || { echo "adb not executable: $ADB_BIN" >&2; exit 1; }
if [[ -z "$PICO_SERIAL" ]]; then
    mapfile -t pico_devices < <("$ADB_BIN" devices | awk '$2 == "device" { print $1 }')
    (( ${#pico_devices[@]} == 1 )) || {
        echo "expected exactly one authorized ADB device; set PICO_SERIAL or ANDROID_SERIAL" >&2
        exit 2
    }
    PICO_SERIAL="${pico_devices[0]}"
fi

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

validate_domain() {
    local stage="$1" status status_epoch connected domain_id now
    status="$(adb_shell run-as "$PACKAGE" cat cache/world-status 2>/dev/null | tr -d '\r' || true)"
    IFS='|' read -r status_epoch connected _ domain_id _ <<<"$status"
    now="$(date +%s)"
    [[ "$status_epoch" =~ ^[0-9]+$ ]] &&
        (( now - status_epoch >= -5 && now - status_epoch <= 5 )) &&
        [[ "$connected" == 1 ]] &&
        [[ "$domain_id" =~ ^\{?[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}\}?$ ]] &&
        [[ "$domain_id" != "{00000000-0000-0000-0000-000000000000}" &&
            "$domain_id" != "00000000-0000-0000-0000-000000000000" ]] || {
        echo "missing, stale, or disconnected world during $stage" >&2
        return 1
    }
    if [[ -z "$MATRIX_DOMAIN_ID" ]]; then
        MATRIX_DOMAIN_ID="$domain_id"
    elif [[ "$domain_id" != "$MATRIX_DOMAIN_ID" ]]; then
        echo "domain changed during $stage" >&2
        return 1
    fi
}

read_avatar_status() {
    local status now field_count
    status="$(adb_shell run-as "$PACKAGE" cat cache/avatar-status 2>/dev/null || true)"
    field_count="$(awk -F'|' '{ print NF }' <<<"$status")"
    IFS='|' read -r AVATAR_EPOCH AVATAR_TOTAL AVATAR_REPLICATED AVATAR_TARGET \
        AVATAR_UPDATED AVATAR_NOT_UPDATED AVATAR_HEROES AVATAR_SIMULATION_MS \
        AVATAR_PROCESSING_MS AVATAR_PRIORITY_BUILD_MS AVATAR_SORT_MS AVATAR_PRE_UPDATE_MS \
        AVATAR_STATE_POLL_MS AVATAR_ENSURE_SCENE_MS AVATAR_SCALE_ANIMATION_MS AVATAR_SIMULATE_MS \
        AVATAR_LOADED_OTHER AVATAR_LOADED_REPLICATED AVATAR_LOCAL_TEMPLATE AVATAR_TEMPLATE_REFRESHES \
        <<<"$status"
    now="$(date +%s)"
    [[ "$field_count" == "20" && "$AVATAR_EPOCH" =~ ^[0-9]+$ ]] &&
        (( now - AVATAR_EPOCH >= -5 && now - AVATAR_EPOCH <= 5 )) &&
        [[ "$AVATAR_TOTAL" =~ ^[0-9]+$ && "$AVATAR_REPLICATED" =~ ^[0-9]+$ &&
            "$AVATAR_TARGET" =~ ^[0-9]+$ && "$AVATAR_UPDATED" =~ ^[0-9]+$ &&
            "$AVATAR_NOT_UPDATED" =~ ^[0-9]+$ && "$AVATAR_HEROES" =~ ^[0-9]+$ &&
            "$AVATAR_SIMULATION_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_PROCESSING_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_PRIORITY_BUILD_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_SORT_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_PRE_UPDATE_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_STATE_POLL_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_ENSURE_SCENE_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_SCALE_ANIMATION_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_SIMULATE_MS" =~ ^[0-9]+([.][0-9]+)?$ &&
            "$AVATAR_LOADED_OTHER" =~ ^[0-9]+$ && "$AVATAR_LOADED_REPLICATED" =~ ^[0-9]+$ &&
            ( "$AVATAR_LOCAL_TEMPLATE" == "0" || "$AVATAR_LOCAL_TEMPLATE" == "1" ) &&
            "$AVATAR_TEMPLATE_REFRESHES" =~ ^[0-9]+$ ]] &&
        (( AVATAR_TOTAL >= AVATAR_REPLICATED + 1 && AVATAR_TARGET <= 50 &&
            AVATAR_LOADED_OTHER <= AVATAR_TOTAL - 1 &&
            AVATAR_LOADED_REPLICATED <= AVATAR_REPLICATED )) &&
        awk -v processing="$AVATAR_PROCESSING_MS" -v priority="$AVATAR_PRIORITY_BUILD_MS" \
            -v simulation="$AVATAR_SIMULATION_MS" -v pre="$AVATAR_PRE_UPDATE_MS" \
            -v state="$AVATAR_STATE_POLL_MS" -v scene="$AVATAR_ENSURE_SCENE_MS" \
            -v scale="$AVATAR_SCALE_ANIMATION_MS" 'BEGIN {
                totalError = processing - priority - simulation
                if (totalError < 0) totalError = -totalError
                preError = pre - state - scene - scale
                if (preError < 0) preError = -preError
                exit (totalError <= 0.02 && preError <= 0.02) ? 0 : 1
            }'
}

source_avatar_count() {
    printf '%s\n' "$((AVATAR_TOTAL - AVATAR_REPLICATED - 1))"
}

validate_template_refresh() {
    local stage="$1"
    if [[ "$EXPECTED_LOCAL_TEMPLATE" == "1" ]] && (( AVATAR_TEMPLATE_REFRESHES == 0 )); then
        echo "local avatar template did not refresh during $stage" >&2
        return 1
    fi
}

set_local_template() {
    local enabled="$1"
    PICO_SERIAL="$PICO_SERIAL" PACKAGE="$PACKAGE" \
        "$SCRIPT_DIR/pico-unattended-test.sh" avatar-template "$enabled" >/dev/null
}

set_replicas() {
    local count="$1"
    PICO_SERIAL="$PICO_SERIAL" PACKAGE="$PACKAGE" \
        "$SCRIPT_DIR/pico-unattended-test.sh" replicas "$count" >/dev/null
}

wait_for_replica_load() {
    local count="$1" timeout="${2:-$LOAD_WAIT}" elapsed=0 sources expected_replicated expected_loaded_other
    while (( elapsed < timeout )); do
        validate_domain "replica load" || return 1
        if read_avatar_status && [[ "$AVATAR_TARGET" == "$count" &&
                "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" ]]; then
            sources="$(source_avatar_count)"
            expected_replicated=$((sources * count))
            expected_loaded_other=$((sources + expected_replicated))
            if (( sources > 0 && AVATAR_REPLICATED == expected_replicated &&
                    AVATAR_LOADED_OTHER == expected_loaded_other &&
                    AVATAR_LOADED_REPLICATED == expected_replicated )); then
                printf '%s\n' "$sources"
                return 0
            fi
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "avatar load did not settle at $count replicas per source avatar" >&2
    return 1
}

"$ADB_BIN" -s "$PICO_SERIAL" get-state >/dev/null
adb_shell run-as "$PACKAGE" true >/dev/null 2>&1 || {
    echo "$PACKAGE must be installed as a debuggable app" >&2
    exit 1
}

if [[ -e "$RESULT_DIR" && ! -d "$RESULT_DIR" ]]; then
    echo "result path is not a directory: $RESULT_DIR" >&2
    exit 2
fi
if [[ -d "$RESULT_DIR" && -n "$(find "$RESULT_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "result directory is not empty: $RESULT_DIR" >&2
    exit 2
fi
mkdir -p "$RESULT_DIR"
RESULT_DIR="$(cd -- "$RESULT_DIR" && pwd)"
printf '%s\n' 'Avatar matrix did not complete; do not use partial results.' > "$RESULT_DIR/INVALID"
ORIGINAL_BRIGHTNESS="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_FAN_SPEED="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_TEST_MODE="$(adb_shell getprop debug.overte.test_mode 2>/dev/null | tr -d '\r')"

cleanup() {
    local cleanup_status cleanup_epoch cleanup_total cleanup_replicated cleanup_target cleanup_local_template
    adb_shell setprop debug.overte.avatar_replicas "$(date +%s)\\|0" >/dev/null 2>&1 || true
    adb_shell setprop debug.overte.avatar_local_template "$(date +%s)\\|0" >/dev/null 2>&1 || true
    # Give the running app a chance to remove replicas before disabling a test
    # mode that was off when the matrix started.
    for _ in 1 2 3; do
        cleanup_status="$(adb_shell run-as "$PACKAGE" cat cache/avatar-status 2>/dev/null || true)"
        IFS='|' read -r cleanup_epoch cleanup_total cleanup_replicated cleanup_target \
            _ _ _ _ _ _ _ _ _ _ _ _ _ _ cleanup_local_template <<<"$cleanup_status"
        [[ "$cleanup_target" == "0" && "$cleanup_local_template" == "0" ]] && break
        sleep 1
    done
    if [[ -z "$ORIGINAL_TEST_MODE" ]]; then
        adb_shell "setprop 'debug.overte.test_mode' ''" >/dev/null 2>&1 || true
    else
        adb_shell setprop debug.overte.test_mode "$ORIGINAL_TEST_MODE" >/dev/null 2>&1 || true
    fi
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
if [[ "$TEMPLATE_MODE" == "local" ]]; then
    set_local_template 1
else
    set_local_template 0
fi
validate_domain "avatar matrix setup"
SOURCE_TEMPLATES="$(wait_for_replica_load 0)"
read_avatar_status || { echo "missing avatar status after template setup" >&2; exit 1; }
if [[ "$TEMPLATE_MODE" == "local" ]]; then
    [[ "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" && "$SOURCE_TEMPLATES" == "1" ]] || {
        echo "local-template mode requires a domain with no received other avatars" >&2
        exit 1
    }
else
    [[ "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" ]] || { echo "local template did not clear" >&2; exit 1; }
fi

adb_shell gd32ipdclient_test setfantestmode 1 >/dev/null
adb_shell gd32ipdclient_test setfantestspeed 100 >/dev/null
adb_shell gd32ipdclient_test setbrightness 1 >/dev/null

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_commit=%s\n' "$(git -C "$SCRIPT_DIR/.." rev-parse HEAD)"
    printf 'package=%s\npid=%s\n' "$PACKAGE" "$PID"
    printf 'template_mode=%s\nsource_template_avatars=%s\nduration_s=%s\ninterval_s=%s\nsettle_s=%s\nload_wait_s=%s\n' \
        "$TEMPLATE_MODE" "$SOURCE_TEMPLATES" "$DURATION" "$INTERVAL" "$SETTLE" "$LOAD_WAIT"
    printf 'replica_sequence=%s\n' "${REPLICA_COUNTS[*]}"
} > "$RESULT_DIR/metadata.txt"
printf 'run,replicas_per_template,total_avatars,local_replicas,source_templates,mean_cpu_pct,mean_avatar_simulation_ms,mean_updated,mean_not_updated,mean_processing_ms,mean_priority_build_ms,mean_sort_ms,mean_pre_update_ms,mean_state_poll_ms,mean_ensure_scene_ms,mean_scale_animation_ms,mean_simulate_ms,mean_loaded_other,mean_loaded_replicated,mean_template_refreshes\n' \
    > "$RESULT_DIR/summary.csv"

run_number=0
for count in "${REPLICA_COUNTS[@]}"; do
    run_number=$((run_number + 1))
    label="r$(printf '%02d' "$run_number")-replicas-$count"
    output="$RESULT_DIR/$label"
    mkdir -p "$output"

    set_replicas "$count"
    loaded_sources="$(wait_for_replica_load "$count")"
    [[ "$loaded_sources" == "$SOURCE_TEMPLATES" ]] || {
        echo "source avatar template count changed before $label ($SOURCE_TEMPLATES -> $loaded_sources)" >&2
        exit 1
    }
    sleep "$SETTLE"
    validate_xr_focus "$label warm-up"
    validate_domain "$label warm-up"
    read_avatar_status || { echo "missing avatar status after $label warm-up" >&2; exit 1; }
    validate_template_refresh "$label warm-up"
    [[ "$(source_avatar_count)" == "$SOURCE_TEMPLATES" &&
        "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" ]] || {
        echo "source avatar template count changed during $label warm-up" >&2
        exit 1
    }
    [[ "$AVATAR_LOADED_OTHER" == "$((SOURCE_TEMPLATES * (count + 1)))" &&
        "$AVATAR_LOADED_REPLICATED" == "$((SOURCE_TEMPLATES * count))" ]] || {
        echo "avatar models became unloaded during $label warm-up" >&2
        exit 1
    }

    printf 'epoch,cpu_pct,total_avatars,local_replicas,source_templates,updated,not_updated,heroes,avatar_simulation_ms,processing_ms,priority_build_ms,sort_ms,pre_update_ms,state_poll_ms,ensure_scene_ms,scale_animation_ms,simulate_ms,loaded_other,loaded_replicated,template_refreshes\n' \
        > "$output/telemetry.csv"
    elapsed=0
    while (( elapsed < DURATION )); do
        validate_xr_focus "$label measurement at ${elapsed}s"
        validate_domain "$label measurement at ${elapsed}s"
        read_avatar_status || { echo "missing avatar status during $label" >&2; exit 1; }
        validate_template_refresh "$label measurement at ${elapsed}s"
        sources="$(source_avatar_count)"
        [[ "$sources" == "$SOURCE_TEMPLATES" && "$AVATAR_TARGET" == "$count" &&
            "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" &&
            "$AVATAR_REPLICATED" == "$((sources * count))" &&
            "$AVATAR_LOADED_OTHER" == "$((sources * (count + 1)))" &&
            "$AVATAR_LOADED_REPLICATED" == "$((sources * count))" ]] || {
            echo "avatar population changed during $label" >&2
            exit 1
        }
        top_line="$(adb_shell top -b -n 1 -p "$PID" 2>/dev/null | tail -n 1 | tr -d '\r')"
        cpu="$(awk '{gsub(/%/, "", $9); print $9}' <<<"$top_line")"
        [[ "$cpu" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "invalid CPU sample during $label" >&2; exit 1; }
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$(date +%s)" "$cpu" "$AVATAR_TOTAL" \
            "$AVATAR_REPLICATED" "$sources" "$AVATAR_UPDATED" "$AVATAR_NOT_UPDATED" "$AVATAR_HEROES" \
            "$AVATAR_SIMULATION_MS" "$AVATAR_PROCESSING_MS" "$AVATAR_PRIORITY_BUILD_MS" \
            "$AVATAR_SORT_MS" "$AVATAR_PRE_UPDATE_MS" "$AVATAR_STATE_POLL_MS" \
            "$AVATAR_ENSURE_SCENE_MS" "$AVATAR_SCALE_ANIMATION_MS" "$AVATAR_SIMULATE_MS" \
            "$AVATAR_LOADED_OTHER" "$AVATAR_LOADED_REPLICATED" "$AVATAR_TEMPLATE_REFRESHES" \
            >> "$output/telemetry.csv"
        sleep "$INTERVAL"
        elapsed=$((elapsed + INTERVAL))
    done

    validate_xr_focus "$label completion"
    validate_domain "$label completion"
    read_avatar_status || { echo "missing avatar status after $label" >&2; exit 1; }
    validate_template_refresh "$label completion"
    sources="$(source_avatar_count)"
    [[ "$sources" == "$SOURCE_TEMPLATES" && "$AVATAR_TARGET" == "$count" &&
        "$AVATAR_LOCAL_TEMPLATE" == "$EXPECTED_LOCAL_TEMPLATE" &&
        "$AVATAR_REPLICATED" == "$((sources * count))" &&
        "$AVATAR_LOADED_OTHER" == "$((sources * (count + 1)))" &&
        "$AVATAR_LOADED_REPLICATED" == "$((sources * count))" ]] || {
        echo "avatar population changed before $label completion" >&2
        exit 1
    }

    read -r mean_cpu mean_simulation mean_updated mean_not_updated mean_processing \
        mean_priority_build mean_sort mean_pre_update mean_state_poll mean_ensure_scene \
        mean_scale_animation mean_simulate mean_loaded_other mean_loaded_replicated mean_template_refreshes < <(awk -F, \
        'NR > 1 { cpu += $2; updated += $6; notUpdated += $7; sim += $9; processing += $10;
            priorityBuild += $11; sort += $12; preUpdate += $13; statePoll += $14;
            ensureScene += $15; scaleAnimation += $16; simulate += $17;
            loadedOther += $18; loadedReplicated += $19; templateRefreshes += $20; n++ }
        END { if (n > 0) printf "%.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f\n",
            cpu / n, sim / n, updated / n, notUpdated / n, processing / n, priorityBuild / n,
            sort / n, preUpdate / n, statePoll / n, ensureScene / n, scaleAnimation / n,
            simulate / n, loadedOther / n, loadedReplicated / n, templateRefreshes / n; else exit 1 }' \
        "$output/telemetry.csv")
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$run_number" "$count" "$AVATAR_TOTAL" "$AVATAR_REPLICATED" \
        "$SOURCE_TEMPLATES" "$mean_cpu" "$mean_simulation" "$mean_updated" "$mean_not_updated" \
        "$mean_processing" "$mean_priority_build" "$mean_sort" "$mean_pre_update" "$mean_state_poll" \
        "$mean_ensure_scene" "$mean_scale_animation" "$mean_simulate" \
        "$mean_loaded_other" "$mean_loaded_replicated" "$mean_template_refreshes" \
        >> "$RESULT_DIR/summary.csv"
    printf '%s mean_cpu=%s mean_avatar_simulation_ms=%s mean_updated=%s mean_not_updated=%s mean_loaded_other=%s mean_loaded_replicated=%s mean_template_refreshes=%s\n' \
        "$label" "$mean_cpu" "$mean_simulation" "$mean_updated" "$mean_not_updated" \
        "$mean_loaded_other" "$mean_loaded_replicated" "$mean_template_refreshes"
done

printf 'replicas_per_template,total_avatars,runs,mean_cpu_pct,mean_avatar_simulation_ms,mean_updated,mean_not_updated,mean_processing_ms,mean_priority_build_ms,mean_sort_ms,mean_pre_update_ms,mean_state_poll_ms,mean_ensure_scene_ms,mean_scale_animation_ms,mean_simulate_ms,mean_loaded_other,mean_loaded_replicated,mean_template_refreshes\n' \
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
    processing[replicas] += $10
    priorityBuild[replicas] += $11
    sort[replicas] += $12
    preUpdate[replicas] += $13
    statePoll[replicas] += $14
    ensureScene[replicas] += $15
    scaleAnimation[replicas] += $16
    simulate[replicas] += $17
    loadedOther[replicas] += $18
    loadedReplicated[replicas] += $19
    templateRefreshes[replicas] += $20
}
END {
    for (i = 1; i <= orderCount; i++) {
        replicas = order[i]
        printf "%s,%s,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n", replicas, total[replicas], runs[replicas],
            cpu[replicas] / runs[replicas], simulation[replicas] / runs[replicas],
            updated[replicas] / runs[replicas], notUpdated[replicas] / runs[replicas],
            processing[replicas] / runs[replicas], priorityBuild[replicas] / runs[replicas],
            sort[replicas] / runs[replicas], preUpdate[replicas] / runs[replicas],
            statePoll[replicas] / runs[replicas], ensureScene[replicas] / runs[replicas],
            scaleAnimation[replicas] / runs[replicas],
            simulate[replicas] / runs[replicas], loadedOther[replicas] / runs[replicas],
            loadedReplicated[replicas] / runs[replicas], templateRefreshes[replicas] / runs[replicas]
    }
}' "$RESULT_DIR/summary.csv" >> "$RESULT_DIR/aggregate.csv"

rm -f "$RESULT_DIR/INVALID"
echo "results=$RESULT_DIR"
