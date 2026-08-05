#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_ARGS=("$@")
ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/platform-tools/adb}"
ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/ndk/27.3.13750724}"
PICO_SERIAL="${PICO_SERIAL:-${ANDROID_SERIAL:-}}"
PACKAGE="${PACKAGE:-org.overte.pico}"
DURATION="${DURATION:-30}"
FREQUENCY="${FREQUENCY:-99}"
WARMUP="${WARMUP:-20}"
LOAD_WAIT="${LOAD_WAIT:-25}"
PREPARE_SCENE="${PREPARE_SCENE:-1}"
CALL_GRAPH="${CALL_GRAPH:-none}"
BUILD_BINARY_CACHE="${BUILD_BINARY_CACHE:-0}"
EXPECTED_AVATAR_REPLICAS="${EXPECTED_AVATAR_REPLICAS:-}"
RESULT_DIR="${RESULT_DIR:-$SCRIPT_DIR/power-results/simpleperf-$(date -u +%Y%m%dT%H%M%SZ)}"
PROFILE_DOMAIN_ID=""
PROFILE_SOURCE_TEMPLATES=""
PROFILE_LOCAL_TEMPLATE=""

usage() {
    cat <<'EOF'
Usage: ./pico-simpleperf.sh [options]

Record a bounded CPU profile of the debuggable Pico Interface app. By default
the script cold-starts Interface, verifies the Overte Hub test position, waits
for the scene to settle, records a low-overhead leaf profile, and restores the
original fan and brightness controls on exit. A foreground/Guardian watchdog
rejects recordings that lose XR focus. The script does not capture screenshots.

Options:
  --duration SECONDS       Recording duration (default: 30)
  --frequency HZ           Maximum samples per second/event (default: 99)
  --warmup SECONDS         Settled-Hub delay before recording (default: 20)
  --result-dir DIR         Output directory
  --call-graph MODE        none or fp (default: none)
  --expect-avatar-replicas COUNT
                           Require 0..50 loaded replicas per source avatar
  --no-prepare             Profile the already-running app without navigation
  --binary-cache           Build a large host debug-symbol cache and report
  --no-binary-cache        Do not build the host cache (the default)
  -h, --help               Show this help

Environment overrides: ADB_BIN, ANDROID_NDK_HOME, PICO_SERIAL, PACKAGE,
DURATION, FREQUENCY, WARMUP, LOAD_WAIT, PREPARE_SCENE, CALL_GRAPH,
EXPECTED_AVATAR_REPLICAS, BUILD_BINARY_CACHE, and RESULT_DIR.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --duration) [[ $# -ge 2 ]] || { echo "--duration requires a value" >&2; exit 2; }; DURATION="$2"; shift 2 ;;
        --frequency) [[ $# -ge 2 ]] || { echo "--frequency requires a value" >&2; exit 2; }; FREQUENCY="$2"; shift 2 ;;
        --warmup) [[ $# -ge 2 ]] || { echo "--warmup requires a value" >&2; exit 2; }; WARMUP="$2"; shift 2 ;;
        --result-dir) [[ $# -ge 2 ]] || { echo "--result-dir requires a value" >&2; exit 2; }; RESULT_DIR="$2"; shift 2 ;;
        --call-graph) [[ $# -ge 2 ]] || { echo "--call-graph requires a value" >&2; exit 2; }; CALL_GRAPH="$2"; shift 2 ;;
        --expect-avatar-replicas) [[ $# -ge 2 ]] || { echo "--expect-avatar-replicas requires a value" >&2; exit 2; }; EXPECTED_AVATAR_REPLICAS="$2"; shift 2 ;;
        --no-prepare) PREPARE_SCENE=0; shift ;;
        --binary-cache) BUILD_BINARY_CACHE=1; shift ;;
        --no-binary-cache) BUILD_BINARY_CACHE=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$DURATION" =~ ^[1-9][0-9]*$ ]] || { echo "duration must be a positive integer" >&2; exit 2; }
[[ "$FREQUENCY" =~ ^[1-9][0-9]*$ ]] || { echo "frequency must be a positive integer" >&2; exit 2; }
[[ "$WARMUP" =~ ^[0-9]+$ ]] || { echo "warmup must be a non-negative integer" >&2; exit 2; }
[[ "$PREPARE_SCENE" == 0 || "$PREPARE_SCENE" == 1 ]] || { echo "PREPARE_SCENE must be 0 or 1" >&2; exit 2; }
[[ "$BUILD_BINARY_CACHE" == 0 || "$BUILD_BINARY_CACHE" == 1 ]] || { echo "BUILD_BINARY_CACHE must be 0 or 1" >&2; exit 2; }
[[ "$CALL_GRAPH" == none || "$CALL_GRAPH" == fp ]] || { echo "call graph must be none or fp" >&2; exit 2; }
if [[ -n "$EXPECTED_AVATAR_REPLICAS" ]]; then
    [[ "$EXPECTED_AVATAR_REPLICAS" =~ ^[0-9]+$ ]] || {
        echo "expected avatar replicas must be an integer from 0 through 50" >&2
        exit 2
    }
    EXPECTED_AVATAR_REPLICAS=$((10#$EXPECTED_AVATAR_REPLICAS))
    (( EXPECTED_AVATAR_REPLICAS <= 50 )) || {
        echo "expected avatar replicas must be an integer from 0 through 50" >&2
        exit 2
    }
fi
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

validate_prepared_world() {
    local stage="$1" status status_epoch connected place domain_id now
    [[ "$PREPARE_SCENE" == 1 ]] || return 0
    status="$(adb_shell run-as "$PACKAGE" cat cache/world-status 2>/dev/null | tr -d '\r' || true)"
    IFS='|' read -r status_epoch connected place domain_id _ <<<"$status"
    now="$(date +%s)"
    [[ "$status_epoch" =~ ^[0-9]+$ ]] &&
        (( now - status_epoch >= -5 && now - status_epoch <= 5 )) &&
        [[ "$connected" == 1 && "${place,,}" == overte_hub ]] &&
        [[ "$domain_id" =~ ^\{?[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}\}?$ ]] &&
        [[ "$domain_id" != "{00000000-0000-0000-0000-000000000000}" &&
            "$domain_id" != "00000000-0000-0000-0000-000000000000" ]] || {
        echo "prepared Hub world is missing, stale, or disconnected during $stage" >&2
        return 1
    }
    if [[ -z "$PROFILE_DOMAIN_ID" ]]; then
        PROFILE_DOMAIN_ID="$domain_id"
    elif [[ "$domain_id" != "$PROFILE_DOMAIN_ID" ]]; then
        echo "prepared Hub domain changed during $stage" >&2
        return 1
    fi
}

validate_avatar_load() {
    local stage="$1" status field_count status_epoch total replicated target now sources
    local expected_replicated loaded_other loaded_replicated local_template template_refreshes
    [[ -n "$EXPECTED_AVATAR_REPLICAS" ]] || return 0
    status="$(adb_shell run-as "$PACKAGE" cat cache/avatar-status 2>/dev/null | tr -d '\r' || true)"
    field_count="$(awk -F'|' '{ print NF }' <<<"$status")"
    IFS='|' read -r status_epoch total replicated target _ _ _ _ _ _ _ _ _ _ _ _ \
        loaded_other loaded_replicated local_template template_refreshes <<<"$status"
    now="$(date +%s)"
    [[ "$field_count" == 20 && "$status_epoch" =~ ^[0-9]+$ &&
        "$total" =~ ^[0-9]+$ && "$replicated" =~ ^[0-9]+$ &&
        "$target" =~ ^[0-9]+$ && "$loaded_other" =~ ^[0-9]+$ &&
        "$loaded_replicated" =~ ^[0-9]+$ &&
        ( "$local_template" == "0" || "$local_template" == "1" ) &&
        "$template_refreshes" =~ ^[0-9]+$ ]] &&
        (( now - status_epoch >= -5 && now - status_epoch <= 5 &&
            total >= replicated + 1 &&
            (local_template == 0 || template_refreshes > 0) )) || {
        echo "loaded avatar status is missing or invalid during $stage" >&2
        return 1
    }
    sources=$((total - replicated - 1))
    expected_replicated=$((sources * EXPECTED_AVATAR_REPLICAS))
    (( sources > 0 && target == EXPECTED_AVATAR_REPLICAS &&
        replicated == expected_replicated &&
        loaded_other == sources + expected_replicated &&
        loaded_replicated == expected_replicated )) || {
        echo "loaded avatar population changed during $stage" >&2
        return 1
    }
    if [[ -z "$PROFILE_SOURCE_TEMPLATES" ]]; then
        PROFILE_SOURCE_TEMPLATES="$sources"
    elif [[ "$sources" != "$PROFILE_SOURCE_TEMPLATES" ]]; then
        echo "source avatar population changed during $stage" >&2
        return 1
    fi
    if [[ -z "$PROFILE_LOCAL_TEMPLATE" ]]; then
        PROFILE_LOCAL_TEMPLATE="$local_template"
    elif [[ "$local_template" != "$PROFILE_LOCAL_TEMPLATE" ]]; then
        echo "local avatar template state changed during $stage" >&2
        return 1
    fi
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
        echo "Pico Guardian/Seethrough is active during $stage (boundary_ready=${boundary_ready:-unknown}, guardian_vst=${guardian_vst:-unknown})" >&2
        return 1
    }
    if [[ -n "${PID:-}" ]]; then
        current_pid="$(adb_shell pidof "$PACKAGE" 2>/dev/null | tr -d '\r')"
        [[ "$current_pid" == "$PID" ]] || {
            echo "Overte restarted during $stage (expected PID $PID, active: ${current_pid:-none})" >&2
            return 1
        }
    fi
    validate_prepared_world "$stage"
    validate_avatar_load "$stage"
}

"$ADB_BIN" -s "$PICO_SERIAL" get-state >/dev/null
adb_shell command -v simpleperf >/dev/null
adb_shell run-as "$PACKAGE" true >/dev/null 2>&1 || {
    echo "$PACKAGE must be installed as a debuggable app for simpleperf --app" >&2
    exit 1
}
INSTALLED_APK_PATH="$(adb_shell pm path "$PACKAGE" 2>/dev/null | sed -n 's/^package://p' | tr -d '\r' | head -n 1 || true)"
INSTALLED_APK_SHA256="$(adb_shell sha256sum "$INSTALLED_APK_PATH" 2>/dev/null | awk '{ print $1 }' | tr -d '\r' || true)"
[[ -n "$INSTALLED_APK_PATH" && "$INSTALLED_APK_SHA256" =~ ^[[:xdigit:]]{64}$ ]] || {
    echo "unable to fingerprint the installed $PACKAGE APK" >&2
    exit 1
}
GIT_TRACKED_STATE=clean
[[ -z "$(git -C "$SCRIPT_DIR/.." status --porcelain --untracked-files=no)" ]] || GIT_TRACKED_STATE=dirty

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
RECORD_FILE="$RESULT_DIR/perf.data"
REMOTE_FILE="/data/local/tmp/overte-simpleperf-$$.data"
ORIGINAL_BRIGHTNESS="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_FAN_SPEED="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_TEST_MODE="$(adb_shell getprop debug.overte.test_mode 2>/dev/null | tr -d '\r')"
FOCUS_MONITOR_PID=""
FOCUS_FAILURE_FILE="$RESULT_DIR/focus-error.txt"

stop_focus_monitor() {
    if [[ -n "$FOCUS_MONITOR_PID" ]]; then
        kill "$FOCUS_MONITOR_PID" >/dev/null 2>&1 || true
        wait "$FOCUS_MONITOR_PID" >/dev/null 2>&1 || true
        FOCUS_MONITOR_PID=""
    fi
}

cleanup() {
    stop_focus_monitor
    adb_shell "rm -f '$REMOTE_FILE'" >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_FAN_SPEED" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setfantestspeed "$ORIGINAL_FAN_SPEED" >/dev/null 2>&1 || true
    fi
    adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_BRIGHTNESS" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setbrightness "$ORIGINAL_BRIGHTNESS" >/dev/null 2>&1 || true
    fi
    if [[ -z "$ORIGINAL_TEST_MODE" ]]; then
        adb_shell "setprop 'debug.overte.test_mode' ''" >/dev/null 2>&1 || true
    else
        adb_shell setprop debug.overte.test_mode "$ORIGINAL_TEST_MODE" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

adb_shell gd32ipdclient_test setfantestmode 1 >/dev/null
adb_shell gd32ipdclient_test setfantestspeed 100 >/dev/null
adb_shell gd32ipdclient_test setbrightness 1 >/dev/null

if [[ "$PREPARE_SCENE" == 1 ]]; then
    adb_shell am force-stop "$PACKAGE"
    timeout 75 env PICO_SERIAL="$PICO_SERIAL" "$SCRIPT_DIR/pico-unattended-test.sh" start >/dev/null
    sleep "$LOAD_WAIT"
    hub_ok=0
    for attempt in 1 2 3; do
        if PICO_SERIAL="$PICO_SERIAL" "$SCRIPT_DIR/pico-unattended-test.sh" hub "simpleperf-$(date +%s)-$attempt"; then
            hub_ok=1
            break
        fi
        sleep 10
    done
    [[ "$hub_ok" == 1 ]] || { echo "unable to establish the verified Hub scene" >&2; exit 1; }
    sleep "$WARMUP"
fi

PID="$(adb_shell pidof "$PACKAGE" | tr -d '\r')"
[[ -n "$PID" ]] || { echo "$PACKAGE is not running" >&2; exit 1; }
validate_xr_focus "profile setup"

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_commit=%s\n' "$(git -C "$SCRIPT_DIR/.." rev-parse HEAD)"
    printf 'git_tracked_state=%s\ninstalled_apk_sha256=%s\n' "$GIT_TRACKED_STATE" "$INSTALLED_APK_SHA256"
    printf 'package=%s\npid=%s\n' "$PACKAGE" "$PID"
    printf 'duration_s=%s\nfrequency_hz=%s\ncall_graph=%s\n' "$DURATION" "$FREQUENCY" "$CALL_GRAPH"
    printf 'prepared_hub=%s\nwarmup_s=%s\n' "$PREPARE_SCENE" "$WARMUP"
    if [[ -n "$EXPECTED_AVATAR_REPLICAS" ]]; then
        printf 'expected_replicas_per_source=%s\nsource_avatars=%s\nlocal_avatar_template=%s\n' \
            "$EXPECTED_AVATAR_REPLICAS" "$PROFILE_SOURCE_TEMPLATES" "$PROFILE_LOCAL_TEMPLATE"
    fi
    printf 'device=%s\n' "$(adb_shell getprop ro.product.model | tr -d '\r')"
    printf 'build_fingerprint=%s\n' "$(adb_shell getprop ro.build.fingerprint | tr -d '\r')"
} > "$RESULT_DIR/metadata.txt"
adb_shell dumpsys battery > "$RESULT_DIR/battery-before.txt"

# `simpleperf --app` records in the app's run-as context, while its parent
# opens the output as shell. Pre-creating a shared writable file avoids a zero
# byte shell file or an app-side permission failure on non-rooted Pico builds.
adb_shell ": > '$REMOTE_FILE'; chmod 666 '$REMOTE_FILE'"
record_args=(record --app "$PACKAGE" --duration "$DURATION" -f "$FREQUENCY")
if [[ "$CALL_GRAPH" == fp ]]; then
    record_args+=(--call-graph fp)
fi
record_args+=(-o "$REMOTE_FILE")
printf 'simpleperf_command=' >> "$RESULT_DIR/metadata.txt"
printf '%q ' simpleperf "${record_args[@]}" >> "$RESULT_DIR/metadata.txt"
printf '\n' >> "$RESULT_DIR/metadata.txt"

monitor_xr_focus() {
    while true; do
        if ! validate_xr_focus "simpleperf recording" > "$FOCUS_FAILURE_FILE" 2>&1; then
            return
        fi
        sleep 1
    done
}

rm -f "$FOCUS_FAILURE_FILE"
monitor_xr_focus &
FOCUS_MONITOR_PID=$!
record_status=0
adb_shell simpleperf "${record_args[@]}" 2> "$RESULT_DIR/record-warnings.txt" || record_status=$?
stop_focus_monitor
if [[ ! -s "$FOCUS_FAILURE_FILE" ]]; then
    validate_xr_focus "profile completion" > "$FOCUS_FAILURE_FILE" 2>&1 || true
fi
if [[ -s "$FOCUS_FAILURE_FILE" ]]; then
    sed -n '1p' "$FOCUS_FAILURE_FILE" >&2
    echo "discarding invalid simpleperf recording" >&2
    exit 1
fi
rm -f "$FOCUS_FAILURE_FILE"
(( record_status == 0 )) || exit "$record_status"
"$ADB_BIN" -s "$PICO_SERIAL" pull "$REMOTE_FILE" "$RECORD_FILE" >/dev/null
[[ -s "$RECORD_FILE" ]] || { echo "simpleperf produced an empty record" >&2; exit 1; }

for sort_key in comm dso comm,dso,symbol; do
    report_name="${sort_key//,/-}"
    adb_shell simpleperf report -i "$REMOTE_FILE" --sort "$sort_key" \
        > "$RESULT_DIR/report-$report_name.txt" \
        2> "$RESULT_DIR/report-$report_name-warnings.txt"
done

if [[ "$CALL_GRAPH" == fp ]]; then
    adb_shell simpleperf report -i "$REMOTE_FILE" --children --sort comm,dso,symbol \
        > "$RESULT_DIR/report-callgraph-children.txt" \
        2> "$RESULT_DIR/report-callgraph-children-warnings.txt"
fi

HOST_SIMPLEPERF="$ANDROID_NDK_HOME/simpleperf/bin/linux/x86_64/simpleperf"
CACHE_BUILDER="$ANDROID_NDK_HOME/simpleperf/binary_cache_builder.py"
NATIVE_LIB_DIR="$SCRIPT_DIR/apps/picoInterface/build/intermediates/cmake/debug/obj/arm64-v8a"
if [[ "$BUILD_BINARY_CACHE" == 1 && -x "$HOST_SIMPLEPERF" && -f "$CACHE_BUILDER" && -d "$NATIVE_LIB_DIR" ]]; then
    (
        cd "$RESULT_DIR"
        ANDROID_SERIAL="$PICO_SERIAL" python3 "$CACHE_BUILDER" -i perf.data \
            -lib "$NATIVE_LIB_DIR" --disable_adb_root --ndk_path "$ANDROID_NDK_HOME" \
            --log warning > binary-cache.log 2>&1
        "$HOST_SIMPLEPERF" report -i perf.data --symfs binary_cache \
            --sort comm,dso,symbol > report-symbolized.txt 2> report-symbolized-warnings.txt
    )
fi

adb_shell dumpsys battery > "$RESULT_DIR/battery-after.txt"
adb_shell 'for z in /sys/class/thermal/thermal_zone*/type; do t=$(cat "$z"); case "$t" in cpu-*-usr|gpu*) printf "%s=" "$t"; cat "${z%/type}/temp";; esac; done' \
    > "$RESULT_DIR/thermals-after.txt"

echo "profile=$RECORD_FILE"
echo "reports=$RESULT_DIR"
