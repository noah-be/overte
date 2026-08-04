#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/platform-tools/adb}"
ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/ndk/27.3.13750724}"
PICO_SERIAL="${PICO_SERIAL:-192.168.188.75:5555}"
PACKAGE="${PACKAGE:-org.overte.pico}"
DURATION="${DURATION:-30}"
FREQUENCY="${FREQUENCY:-99}"
WARMUP="${WARMUP:-20}"
LOAD_WAIT="${LOAD_WAIT:-25}"
PREPARE_SCENE="${PREPARE_SCENE:-1}"
CALL_GRAPH="${CALL_GRAPH:-none}"
BUILD_BINARY_CACHE="${BUILD_BINARY_CACHE:-0}"
RESULT_DIR="${RESULT_DIR:-$SCRIPT_DIR/power-results/simpleperf-$(date -u +%Y%m%dT%H%M%SZ)}"

usage() {
    cat <<'EOF'
Usage: ./pico-simpleperf.sh [options]

Record a bounded CPU profile of the debuggable Pico Interface app. By default
the script cold-starts Interface, verifies the Overte Hub test position, waits
for the scene to settle, records a low-overhead leaf profile, and restores the
original fan and brightness controls on exit. It does not capture screenshots.

Options:
  --duration SECONDS       Recording duration (default: 30)
  --frequency HZ           Maximum samples per second/event (default: 99)
  --warmup SECONDS         Settled-Hub delay before recording (default: 20)
  --result-dir DIR         Output directory
  --call-graph MODE        none or fp (default: none)
  --no-prepare             Profile the already-running app without navigation
  --binary-cache           Build a large host debug-symbol cache and report
  --no-binary-cache        Do not build the host cache (the default)
  -h, --help               Show this help

Environment overrides: ADB_BIN, ANDROID_NDK_HOME, PICO_SERIAL, PACKAGE,
DURATION, FREQUENCY, WARMUP, LOAD_WAIT, PREPARE_SCENE, CALL_GRAPH,
BUILD_BINARY_CACHE, and RESULT_DIR.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --duration) [[ $# -ge 2 ]] || { echo "--duration requires a value" >&2; exit 2; }; DURATION="$2"; shift 2 ;;
        --frequency) [[ $# -ge 2 ]] || { echo "--frequency requires a value" >&2; exit 2; }; FREQUENCY="$2"; shift 2 ;;
        --warmup) [[ $# -ge 2 ]] || { echo "--warmup requires a value" >&2; exit 2; }; WARMUP="$2"; shift 2 ;;
        --result-dir) [[ $# -ge 2 ]] || { echo "--result-dir requires a value" >&2; exit 2; }; RESULT_DIR="$2"; shift 2 ;;
        --call-graph) [[ $# -ge 2 ]] || { echo "--call-graph requires a value" >&2; exit 2; }; CALL_GRAPH="$2"; shift 2 ;;
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
[[ -x "$ADB_BIN" ]] || { echo "adb not executable: $ADB_BIN" >&2; exit 1; }

adb_shell() { "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"; }

"$ADB_BIN" -s "$PICO_SERIAL" get-state >/dev/null
adb_shell command -v simpleperf >/dev/null
adb_shell run-as "$PACKAGE" true >/dev/null 2>&1 || {
    echo "$PACKAGE must be installed as a debuggable app for simpleperf --app" >&2
    exit 1
}

mkdir -p "$RESULT_DIR"
RESULT_DIR="$(cd -- "$RESULT_DIR" && pwd)"
RECORD_FILE="$RESULT_DIR/perf.data"
REMOTE_FILE="/data/local/tmp/overte-simpleperf-$$.data"
ORIGINAL_BRIGHTNESS="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_FAN_SPEED="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"

cleanup() {
    adb_shell "rm -f '$REMOTE_FILE'" >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_FAN_SPEED" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setfantestspeed "$ORIGINAL_FAN_SPEED" >/dev/null 2>&1 || true
    fi
    adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_BRIGHTNESS" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setbrightness "$ORIGINAL_BRIGHTNESS" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

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

{
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'git_commit=%s\n' "$(git -C "$SCRIPT_DIR/.." rev-parse HEAD)"
    printf 'serial=%s\npackage=%s\npid=%s\n' "$PICO_SERIAL" "$PACKAGE" "$PID"
    printf 'duration_s=%s\nfrequency_hz=%s\ncall_graph=%s\n' "$DURATION" "$FREQUENCY" "$CALL_GRAPH"
    printf 'prepared_hub=%s\nwarmup_s=%s\n' "$PREPARE_SCENE" "$WARMUP"
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

adb_shell simpleperf "${record_args[@]}" 2> "$RESULT_DIR/record-warnings.txt"
"$ADB_BIN" -s "$PICO_SERIAL" pull "$REMOTE_FILE" "$RECORD_FILE" >/dev/null
[[ -s "$RECORD_FILE" ]] || { echo "simpleperf produced an empty record" >&2; exit 1; }

for sort_key in comm dso comm,dso,symbol; do
    report_name="${sort_key//,/-}"
    adb_shell simpleperf report -i "$REMOTE_FILE" --sort "$sort_key" \
        > "$RESULT_DIR/report-$report_name.txt" \
        2> "$RESULT_DIR/report-$report_name-warnings.txt"
done

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
