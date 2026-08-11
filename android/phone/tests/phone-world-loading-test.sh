#!/usr/bin/env bash
set -Eeuo pipefail

readonly PACKAGE="org.overte.phone"
readonly ACTIVITY="org.overte.phone/.PermissionsActivity"
readonly WARMUP_TARGET="file:///~/serverless/tutorial.json"
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly worktree_root="$(cd -- "$script_dir/../../.." && pwd)"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: ANDROID_SERIAL=<serial> PHONE_PERF_CONFIRM_NON_VR=YES \
  ./tests/phone-world-loading-test.sh --target overte://example.com [options]

Measures an online world load in the Overte Android Phone client. The script
does not build or install an APK. It launches org.overte.phone through its
public deep link and records one-second CPU, memory, network, thermal, battery,
and process samples plus Android frame statistics.

Options:
  --target URL       Required world URL with explicit /X,Y,Z spawn
  --runs N           Number of measured launches (default: 3)
  --duration SEC     Sample window after navigation (default: 60)
  --warmup SEC       Tutorial-world warm-up before recording (default: 5)
  --settle SEC       Delay between runs (default: 10)
  --output-dir DIR   New report directory outside the worktree
  --cold-cache       Delete only the app cache before every run (debug APK)
  --perfetto         Capture an Android system trace for every run
  --brightness N     Use fixed screen brightness 1–255 and restore afterwards
  --allocator-decay N  Android allocator decay: 0 immediate, 1 device default
  -h, --help         Show this help

Environment:
  PHONE_ADB          ADB executable (otherwise resolved automatically)
EOF
}

if [[ "${1:-}" != --help && "${1:-}" != -h && "${PHONE_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$script_dir/../phone-device-lock.sh" run -- "$0" "$@"
fi

RUNS=3
DURATION=60
WARMUP=5
SETTLE=10
TARGET=''
OUTPUT_DIR=''
COLD_CACHE=0
PERFETTO=0
FIXED_BRIGHTNESS=''
ALLOCATOR_DECAY=''
while (($#)); do
    case "$1" in
        --target) [[ $# -ge 2 ]] || die '--target requires a URL'; TARGET="$2"; shift 2 ;;
        --runs) [[ $# -ge 2 ]] || die '--runs requires a value'; RUNS="$2"; shift 2 ;;
        --duration) [[ $# -ge 2 ]] || die '--duration requires a value'; DURATION="$2"; shift 2 ;;
        --warmup) [[ $# -ge 2 ]] || die '--warmup requires a value'; WARMUP="$2"; shift 2 ;;
        --settle) [[ $# -ge 2 ]] || die '--settle requires a value'; SETTLE="$2"; shift 2 ;;
        --output-dir) [[ $# -ge 2 ]] || die '--output-dir requires a path'; OUTPUT_DIR="$2"; shift 2 ;;
        --cold-cache) COLD_CACHE=1; shift ;;
        --perfetto) PERFETTO=1; shift ;;
        --brightness) [[ $# -ge 2 ]] || die '--brightness requires a value'; FIXED_BRIGHTNESS="$2"; shift 2 ;;
        --allocator-decay) [[ $# -ge 2 ]] || die '--allocator-decay requires a value'; ALLOCATOR_DECAY="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
done
[[ -z "$FIXED_BRIGHTNESS" || "$FIXED_BRIGHTNESS" =~ ^[0-9]+$ && 10#$FIXED_BRIGHTNESS -ge 1 && 10#$FIXED_BRIGHTNESS -le 255 ]] || \
    die '--brightness must be an integer from 1 through 255'
[[ -z "$ALLOCATOR_DECAY" || "$ALLOCATOR_DECAY" == 0 || "$ALLOCATOR_DECAY" == 1 ]] || die '--allocator-decay must be 0 or 1'

[[ "$TARGET" =~ ^(overte|hifi)://[^[:space:]]+$ ]] || die '--target must be an overte:// or hifi:// URL without whitespace'
coordinate='-?[0-9]+([.][0-9]+)?'
[[ "$TARGET" =~ /${coordinate},${coordinate},${coordinate}(/${coordinate},${coordinate},${coordinate},${coordinate})?$ ]] || \
    die '--target must end in an explicit /X,Y,Z spawn position and optional /Qx,Qy,Qz,Qw orientation'
for pair in "runs:$RUNS:1:50" "duration:$DURATION:5:7200" "warmup:$WARMUP:0:600" "settle:$SETTLE:0:600"; do
    IFS=: read -r label value minimum maximum <<<"$pair"
    [[ "$value" =~ ^[0-9]+$ ]] && ((10#$value >= minimum && 10#$value <= maximum)) || \
        die "$label must be an integer from $minimum through $maximum"
done
[[ -n "${ANDROID_SERIAL:-}" ]] || die 'ANDROID_SERIAL must explicitly name the test phone'
[[ "${PHONE_PERF_CONFIRM_NON_VR:-}" == YES ]] || die 'set PHONE_PERF_CONFIRM_NON_VR=YES after confirming the target is a non-VR phone'

find_adb() {
    local candidate
    for candidate in "${PHONE_ADB:-}" "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
        "${ANDROID_HOME:-}/platform-tools/adb" "${HOME}/Android/Sdk/platform-tools/adb"; do
        [[ -n "$candidate" && -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    command -v adb 2>/dev/null || die 'ADB was not found'
}
ADB="$(find_adb)"
readonly ADB
IDENTIFY="$(command -v identify 2>/dev/null || true)"
[[ -x "$IDENTIFY" ]] || die 'ImageMagick identify is required for screenshot validation'
readonly IDENTIFY
CONVERT="$(command -v magick 2>/dev/null || command -v convert 2>/dev/null || true)"
[[ -x "$CONVERT" ]] || die 'ImageMagick magick or convert is required for screenshot validation'
readonly CONVERT
adb_for() { "$ADB" -s "$ANDROID_SERIAL" "$@" 2>/dev/null; }
adb_shell() { adb_for shell "$@"; }
phone_pid() { adb_shell pidof "$PACKAGE" | awk '{print $1}' | tr -d '\r'; }
enforce_brightness() {
    [[ -n "$FIXED_BRIGHTNESS" ]] || return 0
    local observed=''
    for _ in {1..5}; do
        adb_shell settings put system screen_brightness_mode 0 >/dev/null || true
        adb_shell settings put system screen_brightness "$FIXED_BRIGHTNESS" >/dev/null || true
        observed="$(adb_shell settings get system screen_brightness | tr -dc '0-9' || true)"
        [[ "$observed" == "$FIXED_BRIGHTNESS" ]] && return 0
        sleep 0.2
    done
    return 1
}

authorized=0
while read -r serial state _; do
    [[ "$serial" == "$ANDROID_SERIAL" && "$state" == device ]] && authorized=$((authorized + 1))
done < <("$ADB" devices -l 2>/dev/null)
((authorized == 1)) || die 'ANDROID_SERIAL must identify exactly one authorized device'

property() { adb_shell getprop "$1" | tr -d '\r'; }
identity="$(property ro.product.manufacturer) $(property ro.product.brand) $(property ro.product.model)"
characteristics="$(property ro.build.characteristics)"
qemu="$(property ro.kernel.qemu)"
[[ ! "${identity,,}" =~ pico|bytedance ]] || die 'refusing to test a Pico/VR device'
[[ "$qemu" != 1 && ! "${characteristics,,}" =~ (^|,)(watch|tv|automotive|vr)(,|$) ]] || \
    die 'target does not satisfy the physical Phone contract'
adb_shell pm path "$PACKAGE" >/dev/null || die "$PACKAGE is not installed"
uid="$(adb_shell dumpsys package "$PACKAGE" | sed -nE 's/^[[:space:]]*(userId|appId)=([0-9]+).*/\2/p' | head -n1 | tr -d '\r')"
if [[ ! "$uid" =~ ^[0-9]+$ ]]; then
    uid="$(adb_shell cmd package list packages -U "$PACKAGE" | sed -nE 's/.*[[:space:]]uid:([0-9]+).*/\1/p' | head -n1 | tr -d '\r')"
fi
[[ "$uid" =~ ^[0-9]+$ ]] || die "could not resolve $PACKAGE UID"

if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="/tmp/overte-phone-world-loading-$(date -u +%Y%m%dT%H%M%SZ)"
fi
OUTPUT_DIR="$(realpath -m -- "$OUTPUT_DIR")" || die 'could not resolve output directory'
case "$OUTPUT_DIR/" in "$worktree_root/"*) die 'report directory must be outside the worktree' ;; esac
[[ ! -e "$OUTPUT_DIR" ]] || die 'output directory already exists'
mkdir -m 700 -- "$OUTPUT_DIR" || die 'could not create output directory'
space_probe="$OUTPUT_DIR/.space-probe"
if command -v fallocate >/dev/null 2>&1; then
    fallocate -l 67108864 "$space_probe" 2>/dev/null || \
        die 'report filesystem has less than 64 MiB of quota/free space available'
    rm -f -- "$space_probe"
fi

cleanup() {
    local status=$?
    trap - EXIT INT TERM
    if [[ "${logcat_capture_pid:-}" =~ ^[0-9]+$ ]]; then
        kill "$logcat_capture_pid" >/dev/null 2>&1 || true
        wait "$logcat_capture_pid" >/dev/null 2>&1 || true
    fi
    adb_shell "setprop debug.overte.navigate ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.teleport ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.test_mode ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.malloc_trim ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.malloc_decay ''" >/dev/null 2>&1 || true
    if [[ -n "${original_brightness:-}" ]]; then
        adb_shell settings put system screen_brightness "$original_brightness" >/dev/null 2>&1 || true
        adb_shell settings put system screen_brightness_mode "${original_brightness_mode:-0}" >/dev/null 2>&1 || true
    fi
    adb_shell am force-stop "$PACKAGE" >/dev/null 2>&1 || true
    exit "$status"
}
trap cleanup EXIT INT TERM
logcat_capture_pid=''

csv_value() {
    local value="$1"
    value="${value//$'\r'/ }"
    value="${value//$'\n'/ }"
    value="${value//\"/\"\"}"
    printf '"%s"' "$value"
}
read_network() {
    local rx tx
    rx="$(adb_shell cat "/proc/uid_stat/$uid/tcp_rcv" 2>/dev/null | tr -dc '0-9' || true)"
    tx="$(adb_shell cat "/proc/uid_stat/$uid/tcp_snd" 2>/dev/null | tr -dc '0-9' || true)"
    if [[ ! "$rx" =~ ^[0-9]+$ || ! "$tx" =~ ^[0-9]+$ ]]; then
        read -r rx tx < <(adb_shell cat /proc/net/xt_qtaguid/stats 2>/dev/null | \
            awk -v uid="$uid" 'NR>1 && $4==uid {rx+=$6; tx+=$8} END {print rx+0, tx+0}' || printf '0 0\n')
    fi
    if [[ "${rx:-0}" == 0 && "${tx:-0}" == 0 ]]; then
        adb_shell dumpsys netstats --poll >/dev/null 2>&1 || true
        read -r rx tx < <(adb_shell dumpsys netstats detail 2>/dev/null | awk -v uid="$uid" '
            /^  ident=/ {selected=($0 ~ ("uid=" uid " "))}
            selected && /[[:space:]]rb=[0-9]+/ {
                for (i=1; i<=NF; i++) {
                    if ($i ~ /^rb=/) {sub(/^rb=/,"",$i); rx+=$i}
                    if ($i ~ /^tb=/) {sub(/^tb=/,"",$i); tx+=$i}
                }
            }
            END {print rx+0, tx+0}
        ' || printf '0 0\n')
    fi
    printf '%s %s\n' "${rx:-0}" "${tx:-0}"
}

printf 'run,start_epoch_ms,am_total_ms,pid,rx_start_bytes,tx_start_bytes,rx_end_bytes,tx_end_bytes,rx_delta_bytes,tx_delta_bytes,frames,janky_frames,janky_percent,max_pss_kb,max_rss_kb,mean_cpu_percent,max_cpu_percent,max_thermal_status,battery_drop_percent,process_stable,connection_error_dialog,screenshot_valid\n' >"$OUTPUT_DIR/runs.csv"

original_brightness="$(adb_shell settings get system screen_brightness | tr -dc '0-9' || true)"
original_brightness_mode="$(adb_shell settings get system screen_brightness_mode | tr -dc '0-9' || true)"
if [[ -n "$FIXED_BRIGHTNESS" ]]; then
    enforce_brightness || die 'could not enforce fixed brightness'
fi
brightness_start="$(adb_shell settings get system screen_brightness | tr -dc '0-9' || true)"
brightness_mode_start="$(adb_shell settings get system screen_brightness_mode | tr -dc '0-9' || true)"
if [[ -n "$ALLOCATOR_DECAY" ]]; then
    adb_shell setprop debug.overte.malloc_decay "$ALLOCATOR_DECAY" >/dev/null || die 'could not configure allocator decay'
else
    adb_shell "setprop debug.overte.malloc_decay ''" >/dev/null || die 'could not clear allocator decay override'
fi
device_csv="manufacturer,brand,model,device,android_sdk,build_fingerprint,adb_transport,uid,warmup_target,target,runs,duration_seconds,warmup_seconds,cold_cache,perfetto,fixed_brightness,screen_brightness_start,screen_brightness_mode_start\n"
device_csv+="$(csv_value "$(property ro.product.manufacturer)"),$(csv_value "$(property ro.product.brand)"),$(csv_value "$(property ro.product.model)"),$(csv_value "$(property ro.product.device)"),$(csv_value "$(property ro.build.version.sdk)"),$(csv_value "$(property ro.build.fingerprint)"),$(csv_value "$([[ "$ANDROID_SERIAL" == *:* ]] && printf wifi || printf usb)"),$uid,$(csv_value "$WARMUP_TARGET"),$(csv_value "$TARGET"),$RUNS,$DURATION,$WARMUP,$COLD_CACHE,$PERFETTO,${FIXED_BRIGHTNESS:-},${brightness_start:-0},${brightness_mode_start:-0}\n"
printf '%b' "$device_csv" >"$OUTPUT_DIR/device.csv"

for ((run=1; run<=RUNS; run++)); do
    printf 'run %d/%d\n' "$run" "$RUNS"
    run_dir="$OUTPUT_DIR/run-$run"
    mkdir -m 700 "$run_dir"
    adb_shell am force-stop "$PACKAGE" >/dev/null
    adb_shell setprop debug.overte.test_mode 1 >/dev/null || die 'could not enable Phone performance telemetry'
    adb_shell "setprop debug.overte.navigate ''" >/dev/null 2>&1 || true
    adb_shell "setprop debug.overte.teleport ''" >/dev/null 2>&1 || true
    adb_shell run-as "$PACKAGE" rm -f cache/world-status >/dev/null 2>&1 || true
    if ((COLD_CACHE)); then
        # Pass the complete command to the device shell. Otherwise adb shell
        # consumes the sh -c argument boundary and run-as executes a bare rm.
        adb_shell "run-as $PACKAGE sh -c 'rm -rf cache/*'" >/dev/null || \
            die '--cold-cache requires a debuggable APK with run-as support'
    fi
    adb_shell am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n "$ACTIVITY" >"$run_dir/am-warmup-start.txt" || die 'Phone warm-up launch failed'
    pid=''
    for _ in {1..20}; do
        pid="$(phone_pid || true)"
        [[ "$pid" =~ ^[0-9]+$ ]] && break
        sleep 1
    done
    [[ "$pid" =~ ^[0-9]+$ ]] || die 'Phone process did not start'
    warmup_nonce="$(date +%s%N)"
    adb_shell setprop debug.overte.navigate "${warmup_nonce}\\|${WARMUP_TARGET}" >/dev/null || \
        die 'could not request deterministic tutorial warm-up'
    warmup_ready=0
    for _ in {1..60}; do
        warmup_status="$(adb_shell run-as "$PACKAGE" cat cache/world-status 2>/dev/null | tr -d '\r\n' || true)"
        if [[ "$(awk -F'|' '{print NF}' <<<"$warmup_status")" == 15 ]] &&
                awk -F'|' '($11 + 0) > 1 { found=1 } END { exit !found }' <<<"$warmup_status"; then
            warmup_ready=1
            break
        fi
        sleep 1
    done
    ((warmup_ready == 1)) || die 'tutorial world did not become ready within 60 seconds'
    ((WARMUP == 0)) || sleep "$WARMUP"
    [[ "$(phone_pid || true)" == "$pid" ]] || die 'Phone process did not remain stable during warm-up'
    adb_shell "setprop debug.overte.navigate ''" >/dev/null 2>&1 || true

    adb_shell dumpsys gfxinfo "$PACKAGE" reset >/dev/null || true
    adb_for logcat -c >/dev/null || true
    adb_for logcat --pid="$pid" -v threadtime >"$run_dir/logcat.txt" &
    logcat_capture_pid=$!
    read -r rx_start tx_start < <(read_network)
    battery_start="$(adb_shell dumpsys battery | sed -nE 's/^[[:space:]]*level: ([0-9]+).*/\1/p' | head -n1)"

    trace_remote="/data/misc/perfetto-traces/overte-phone-world-$run.perfetto-trace"
    if ((PERFETTO)); then
        adb_shell perfetto --background -o "$trace_remote" -t "${DURATION}s" sched freq idle am wm gfx view binder_driver power >/dev/null || \
            die 'could not start Perfetto; retry without --perfetto or inspect device support'
    fi

    start_epoch_ms="$(date +%s%3N)"
    start_output="$(adb_shell am start -W -a android.intent.action.VIEW -c android.intent.category.BROWSABLE -d "$TARGET" -n "$ACTIVITY")" || die 'Phone deep-link navigation failed'
    printf '%s\n' "$start_output" >"$run_dir/am-navigation.txt"
    am_total_ms="$(sed -nE 's/^TotalTime: ([0-9]+).*/\1/p' <<<"$start_output" | tail -n1)"
    am_total_ms="${am_total_ms:-0}"
    printf 'epoch_ms,elapsed_ms,cpu_percent,pss_kb,rss_kb,swap_pss_kb,private_dirty_kb,private_clean_kb,rss_anon_kb,rss_file_kb,rss_shmem_kb,vm_swap_kb,rx_bytes,tx_bytes,thermal_status,battery_level,battery_status,battery_powered,battery_ac_powered,battery_usb_powered,battery_wireless_powered,battery_dock_powered,battery_charging_state,max_charging_current_uA,max_charging_voltage_uV,battery_current_uA,battery_voltage_uV,battery_charge_uAh,cpu_temp_mC,gpu_temp_mC,battery_temp_mC,skin_temp_mC,screen_brightness,screen_brightness_mode,display_brightness,wifi_rssi_dbm,wifi_link_speed_mbps,wifi_tx_link_speed_mbps,wifi_rx_link_speed_mbps,wifi_frequency_mhz\n' >"$run_dir/samples.csv"
    printf 'sample_epoch_ms,status_epoch_s,connected,place,domain_id,x,y,z,entity_server,entity_ping_ms,entity_in_kbps,entity_count,asset_server,active_downloads,pending_downloads,gpu_memory_bytes\n' >"$run_dir/world-status.csv"
    printf 'epoch_ms,elapsed_ms,dalvik_pss_kb,native_pss_kb,graphics_pss_kb,stack_pss_kb,shared_library_pss_kb,code_pss_kb,file_pss_kb,anonymous_pss_kb,other_pss_kb,threads,open_fds,cache_disk_kb\n' >"$run_dir/memory-detail.csv"
    printf 'epoch_ms,elapsed_ms,mapping_start,mapping_name,pss_kb\n' >"$run_dir/memory-mappings.csv"
    stable=1
    measurement_start_ms="$start_epoch_ms"
    measurement_deadline_ms=$((measurement_start_ms + DURATION * 1000))
    next_sample_ms="$measurement_start_ms"
    last_slow_sample_ms=-5000
    last_detail_sample_ms=-10000
    rx="$rx_start"; tx="$tx_start"; thermal=0; battery="$battery_start"; battery_status=0
    battery_powered=0; battery_ac_powered=0; battery_usb_powered=0
    battery_wireless_powered=0; battery_dock_powered=0; battery_charging_state=0
    max_charging_current=0; max_charging_voltage=0
    battery_current=0; battery_voltage=0; battery_charge=0
    cpu_temp=0; gpu_temp=0; battery_temp=0; skin_temp=0
    brightness="${brightness_start:-0}"; brightness_mode="${brightness_mode_start:-0}"; display_brightness=0
    wifi_rssi=0; wifi_link_speed=0; wifi_tx_link_speed=0; wifi_rx_link_speed=0; wifi_frequency=0
    target_path="${TARGET#*://}"; target_path="${target_path#*/}"; target_coordinates="${target_path%%/*}"
    IFS=',' read -r target_x target_y target_z <<<"$target_coordinates"
    if [[ ! "$target_x" =~ ^-?[0-9]+([.][0-9]+)?$ || ! "$target_y" =~ ^-?[0-9]+([.][0-9]+)?$ || ! "$target_z" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
        target_x=''; target_y=''; target_z=''
    fi
    last_spawn_correction_ms=-5000
    while (( $(date +%s%3N) < measurement_deadline_ms )); do
        sample_started_ms="$(date +%s%3N)"
        current_pid=''
        for _ in {1..3}; do
            current_pid="$(phone_pid || true)"
            [[ -n "$current_pid" ]] && break
            sleep 1
        done
        [[ "$current_pid" == "$pid" ]] || { stable=0; break; }
        cpu_sample_file="$run_dir/.cpu-sample"
        mem_sample_file="$run_dir/.mem-sample"
        (adb_shell top -b -n 1 -p "$pid" | awk -v pid="$pid" '$1==pid {print $9; exit}' >"$cpu_sample_file") &
        cpu_sample_pid=$!
        ({ adb_shell run-as "$PACKAGE" cat "/proc/$pid/smaps_rollup"; adb_shell cat "/proc/$pid/status"; } | awk '
            /^Pss:/ && !pss {pss=$2} /^Rss:/ && !rss {rss=$2} /^SwapPss:/ {swap_pss=$2}
            /^Private_Dirty:/ {private_dirty=$2} /^Private_Clean:/ {private_clean=$2}
            /^RssAnon:/ {rss_anon=$2} /^RssFile:/ {rss_file=$2} /^RssShmem:/ {rss_shmem=$2} /^VmSwap:/ {vm_swap=$2}
            END {print pss+0,rss+0,swap_pss+0,private_dirty+0,private_clean+0,rss_anon+0,rss_file+0,rss_shmem+0,vm_swap+0}
        ' >"$mem_sample_file") &
        mem_sample_pid=$!
        wait "$cpu_sample_pid" || true
        wait "$mem_sample_pid" || true
        cpu="$(tr -d '\r\n' <"$cpu_sample_file")"
        [[ "$cpu" =~ ^[0-9]+([.][0-9]+)?$ ]] || cpu=0
        mem="$(tr -d '\r' <"$mem_sample_file")"
        read -r pss rss swap_pss private_dirty private_clean rss_anon rss_file rss_shmem vm_swap <<<"$mem"
        if (( sample_started_ms - last_detail_sample_ms >= 10000 )); then
            detail_sample_file="$run_dir/.detail-sample"
            detail_epoch_ms="$(date +%s%3N)"
            detail_elapsed_ms="$((sample_started_ms - measurement_start_ms))"
            ({ adb_shell run-as "$PACKAGE" cat "/proc/$pid/smaps"; printf '__STATUS__\n'; adb_shell cat "/proc/$pid/status"; printf '__FDS__\n'; adb_shell "run-as $PACKAGE sh -c 'ls /proc/$pid/fd 2>/dev/null | wc -l'"; printf '__CACHE__\n'; adb_shell run-as "$PACKAGE" du -sk cache; } | awk -v mappings="$run_dir/memory-mappings.csv" -v epoch="$detail_epoch_ms" -v elapsed="$detail_elapsed_ms" '
                function flush() { if (!seen) return; p=map_pss+0; if (p >= 1024) { printable=name; if(printable=="")printable="[anonymous]"; gsub(/,/,"_",printable); print epoch "," elapsed "," start "," printable "," p >> mappings } if (name ~ /dalvik|\.art($| )/) dalvik+=p; else if (name ~ /\[heap\]|libc_malloc|scudo|GWP-ASan/) native+=p; else if (name ~ /dmabuf|kgsl|mali|gralloc|egl|GL/) graphics+=p; else if (name ~ /\[stack/) stack+=p; else if (name ~ /\.so($| )/) shared+=p; else if (name ~ /\.apk|\.dex|\.vdex|\.oat/) code+=p; else if (name ~ /^\//) file+=p; else if (name == "" || name ~ /^\[anon/) anonymous+=p; else other+=p; map_pss=0 }
                /^[0-9a-f]+-[0-9a-f]+ / { flush(); seen=1; start=$1; sub(/-.*/,"",start); name=""; for(i=6;i<=NF;i++) name=name (i==6?"":" ") $i; next }
                /^Pss:/ { map_pss=$2; next }
                /^__STATUS__$/ { flush(); seen=0; status=1; next }
                status && /^Threads:/ { threads=$2; next }
                /^__FDS__$/ { status=0; fds=1; next }
                fds && /^[0-9]+$/ { open_fds=$1; fds=0; next }
                /^__CACHE__$/ { cache=1; next }
                cache && /^[0-9]+/ { cache_kb=$1; cache=0 }
                END { flush(); print dalvik+0,native+0,graphics+0,stack+0,shared+0,code+0,file+0,anonymous+0,other+0,threads+0,open_fds+0,cache_kb+0 }
            ' >"$detail_sample_file") & detail_sample_pid=$!
            wait "$detail_sample_pid" || true
            read -r dalvik_pss native_pss graphics_pss stack_pss shared_pss code_pss file_pss anonymous_pss other_pss threads open_fds cache_disk_kb <"$detail_sample_file"
            printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$detail_epoch_ms" "$detail_elapsed_ms" "$dalvik_pss" "$native_pss" "$graphics_pss" "$stack_pss" "$shared_pss" "$code_pss" "$file_pss" "$anonymous_pss" "$other_pss" "$threads" "$open_fds" "$cache_disk_kb" >>"$run_dir/memory-detail.csv"
            last_detail_sample_ms="$sample_started_ms"
        fi
        if (( sample_started_ms - last_slow_sample_ms >= 5000 )); then
            if [[ -n "$FIXED_BRIGHTNESS" ]]; then
                enforce_brightness || { stable=0; break; }
            fi
            network_sample_file="$run_dir/.network-sample"
            thermal_sample_file="$run_dir/.thermal-sample"
            battery_sample_file="$run_dir/.battery-sample"
            display_sample_file="$run_dir/.display-sample"
            wifi_sample_file="$run_dir/.wifi-sample"
            power_sample_file="$run_dir/.power-sample"
            (read_network >"$network_sample_file") & network_sample_pid=$!
            (adb_shell dumpsys thermalservice | awk '
                /^Thermal Status:/ {global=$3}
                /Current temperatures from HAL:/ {hal=1; next}
                /Current cooling devices from HAL:/ {hal=0}
                hal && /Temperature{/ {
                    line=$0; sub(/.*mValue=/,"",line); value=line; sub(/,.*/,"",value)
                    line=$0; sub(/.*mType=/,"",line); type=line; sub(/,.*/,"",type)
                    milli=int(value*1000)
                    if(type==0 && milli>cpu)cpu=milli; if(type==1 && milli>gpu)gpu=milli
                    if(type==2 && milli>battery)battery=milli; if(type==3 && milli>skin)skin=milli
                }
                END {print global+0,cpu+0,gpu+0,battery+0,skin+0}
            ' >"$thermal_sample_file") & thermal_sample_pid=$!
            (adb_shell dumpsys battery | awk '
                /AC powered:/ {ac=($3=="true")}
                /USB powered:/ {usb=($3=="true")}
                /Wireless powered:/ {wireless=($3=="true")}
                /Dock powered:/ {dock=($3=="true")}
                /Max charging current:/ {max_current=$4}
                /Max charging voltage:/ {max_voltage=$4}
                /^[[:space:]]*status:/ {status=$2}
                /^[[:space:]]*level:/ {level=$2}
                /^[[:space:]]*Charging state:/ {charging_state=$3}
                END {print level+0,status+0,(ac||usb||wireless||dock),ac+0,usb+0,wireless+0,dock+0,charging_state+0,max_current+0,max_voltage+0}
            ' >"$battery_sample_file") & battery_sample_pid=$!
            (adb_shell 'printf "%s %s %s\n" "$(cat /sys/class/power_supply/battery/current_now 2>/dev/null || echo 0)" "$(cat /sys/class/power_supply/battery/voltage_now 2>/dev/null || echo 0)" "$(cat /sys/class/power_supply/battery/charge_counter 2>/dev/null || echo 0)"' >"$power_sample_file") & power_sample_pid=$!
            (adb_shell 'printf "%s %s " "$(settings get system screen_brightness)" "$(settings get system screen_brightness_mode)"; dumpsys display | sed -nE "s/^[[:space:]]*Display Brightness=([^[:space:]]+).*/\\1/p" | head -n1' >"$display_sample_file") & display_sample_pid=$!
            (adb_shell cmd wifi status | awk '/WifiInfo:/ {line=$0; r=line; sub(/.*RSSI: /,"",r); sub(/,.*/,"",r); l=line; sub(/.*Link speed: /,"",l); sub(/Mbps.*/,"",l); t=line; sub(/.*Tx Link speed: /,"",t); sub(/Mbps.*/,"",t); x=line; sub(/.*Rx Link speed: /,"",x); sub(/Mbps.*/,"",x); f=line; sub(/.*Frequency: /,"",f); sub(/MHz.*/,"",f); print r+0,l+0,t+0,x+0,f+0; exit}' >"$wifi_sample_file") & wifi_sample_pid=$!
            wait "$network_sample_pid" || true; wait "$thermal_sample_pid" || true
            wait "$battery_sample_pid" || true; wait "$power_sample_pid" || true
            wait "$display_sample_pid" || true; wait "$wifi_sample_pid" || true
            read -r rx tx <"$network_sample_file"
            read -r thermal cpu_temp gpu_temp battery_temp skin_temp <"$thermal_sample_file"
            read -r battery battery_status battery_powered battery_ac_powered battery_usb_powered battery_wireless_powered battery_dock_powered battery_charging_state max_charging_current max_charging_voltage <"$battery_sample_file"
            read -r battery_current battery_voltage battery_charge <"$power_sample_file"
            read -r brightness brightness_mode display_brightness <"$display_sample_file"
            read -r wifi_rssi wifi_link_speed wifi_tx_link_speed wifi_rx_link_speed wifi_frequency <"$wifi_sample_file"
            last_slow_sample_ms="$sample_started_ms"
        fi
        sample_epoch_ms="$(date +%s%3N)"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$sample_epoch_ms" "$((sample_epoch_ms - measurement_start_ms))" "${cpu:-0}" "${pss:-0}" "${rss:-0}" "${swap_pss:-0}" "${private_dirty:-0}" "${private_clean:-0}" "${rss_anon:-0}" "${rss_file:-0}" "${rss_shmem:-0}" "${vm_swap:-0}" \
            "$rx" "$tx" "${thermal:-0}" "${battery:-0}" "${battery_status:-0}" "${battery_powered:-0}" "${battery_ac_powered:-0}" "${battery_usb_powered:-0}" "${battery_wireless_powered:-0}" "${battery_dock_powered:-0}" "${battery_charging_state:-0}" "${max_charging_current:-0}" "${max_charging_voltage:-0}" "${battery_current:-0}" "${battery_voltage:-0}" "${battery_charge:-0}" "${cpu_temp:-0}" "${gpu_temp:-0}" "${battery_temp:-0}" "${skin_temp:-0}" "${brightness:-0}" "${brightness_mode:-0}" "${display_brightness:-0}" "${wifi_rssi:-0}" "${wifi_link_speed:-0}" "${wifi_tx_link_speed:-0}" "${wifi_rx_link_speed:-0}" "${wifi_frequency:-0}" >>"$run_dir/samples.csv"
        world_status="$(adb_shell run-as "$PACKAGE" cat cache/world-status 2>/dev/null | tr -d '\r\n' || true)"
        if [[ "$(awk -F'|' '{print NF}' <<<"$world_status")" == 15 ]]; then
            printf '%s,%s\n' "$sample_epoch_ms" "${world_status//|/,}" >>"$run_dir/world-status.csv"
            if [[ -n "$target_x" ]] && (( sample_started_ms - last_spawn_correction_ms >= 5000 )) &&
                    awk -F'|' -v x="$target_x" -v y="$target_y" -v z="$target_z" '
                        $2==1 && (sqrt(($5-x)^2)>5 || sqrt(($6-y)^2)>5 || sqrt(($7-z)^2)>5) { exit 0 }
                        { exit 1 }
                    ' <<<"$world_status"; then
                teleport_nonce="$(date +%s%N)"
                adb_shell "setprop debug.overte.teleport '${teleport_nonce}|${target_x}|${target_y}|${target_z}'" >/dev/null || true
                last_spawn_correction_ms="$sample_started_ms"
            fi
        fi
        next_sample_ms=$((next_sample_ms + 1000))
        now_ms="$(date +%s%3N)"
        if (( next_sample_ms > now_ms )); then
            sleep "$(awk -v ms="$((next_sample_ms - now_ms))" 'BEGIN {printf "%.3f", ms / 1000}')"
        else
            next_sample_ms="$now_ms"
        fi
    done
    adb_shell "setprop debug.overte.teleport ''" >/dev/null 2>&1 || true
    rm -f "$run_dir"/.*-sample
    kill "$logcat_capture_pid" >/dev/null 2>&1 || true
    wait "$logcat_capture_pid" >/dev/null 2>&1 || true
    logcat_capture_pid=''
    printf 'epoch_ms,script,total_heap_bytes,used_heap_bytes,available_bytes,used_global_handles_bytes\n' >"$run_dir/script-memory.csv"
    awk '/PHONE_PERF record=script_heap / {
        epoch=script=total=used=available=handles=""
        for(i=1;i<=NF;i++) {
            if($i ~ /^epoch_ms=/){sub(/^epoch_ms=/,"",$i);epoch=$i}
            else if($i ~ /^script=/){sub(/^script=/,"",$i);script=$i}
            else if($i ~ /^total_heap_bytes=/){sub(/^total_heap_bytes=/,"",$i);total=$i}
            else if($i ~ /^used_heap_bytes=/){sub(/^used_heap_bytes=/,"",$i);used=$i}
            else if($i ~ /^available_bytes=/){sub(/^available_bytes=/,"",$i);available=$i}
            else if($i ~ /^used_global_handles_bytes=/){sub(/^used_global_handles_bytes=/,"",$i);handles=$i}
        }
        if(epoch!="" && script!="") print epoch "," script "," total "," used "," available "," handles
    }' "$run_dir/logcat.txt" >>"$run_dir/script-memory.csv"

    adb_shell dumpsys gfxinfo "$PACKAGE" framestats >"$run_dir/gfxinfo.txt" || true
    adb_shell dumpsys meminfo "$PACKAGE" >"$run_dir/meminfo-final.txt" || true
    screenshot="$run_dir/final-overte-hub.png"
    screenshot_valid=0
    if adb_for exec-out screencap -p >"$screenshot"; then
        read -r screenshot_width screenshot_height screenshot_mean < <(
            "$IDENTIFY" -format '%w %h %[fx:mean]\n' "$screenshot" 2>/dev/null || printf '0 0 0\n'
        )
        central_lit_fraction="$($CONVERT "$screenshot" -crop '50%x70%+25%+0' +repage \
            -colorspace gray -threshold 20% -format '%[fx:mean]' info: 2>/dev/null || printf '0')"
        hub_warm_fraction="$($CONVERT "$screenshot" -crop '60%x70%+20%+30%' +repage -resize '25%' \
            -fx '((r>g*1.12)*(g>b*1.12)*(r>0.25))' -format '%[fx:mean]' info: 2>/dev/null || printf '0')"
        if [[ "$screenshot_width" =~ ^[1-9][0-9]*$ && "$screenshot_height" =~ ^[1-9][0-9]*$ ]] &&
                awk -v mean="${screenshot_mean:-0}" -v central="${central_lit_fraction:-0}" \
                    -v warm="${hub_warm_fraction:-0}" \
                    'BEGIN {exit !(mean >= 0.02 && central >= 0.20 && warm >= 0.08)}'; then
            screenshot_valid=1
        fi
    fi
    connection_error=0
    ui_dump="/sdcard/overte-phone-performance-ui.xml"
    if adb_shell uiautomator dump "$ui_dump" >/dev/null 2>&1; then
        if adb_shell cat "$ui_dump" 2>/dev/null | grep -Eiq 'unable to connect|connect to domain|connection (failed|error)'; then
            connection_error=1
        fi
        adb_shell rm -f "$ui_dump" >/dev/null 2>&1 || true
    fi
    read -r rx_end tx_end < <(read_network)
    battery_end="$(adb_shell dumpsys battery | sed -nE 's/^[[:space:]]*level: ([0-9]+).*/\1/p' | head -n1)"
    if ((PERFETTO)); then
        sleep 2
        trace_pulled=0
        for _ in {1..5}; do
            if adb_for pull "$trace_remote" "$run_dir/trace.perfetto-trace" >/dev/null &&
                    [[ -s "$run_dir/trace.perfetto-trace" ]]; then
                trace_pulled=1
                break
            fi
            sleep 2
        done
        ((trace_pulled == 1)) || rm -f "$run_dir/trace.perfetto-trace"
        adb_shell rm -f "$trace_remote" >/dev/null || true
    fi

    read -r frames janky < <(awk 'BEGIN{f=0;j=0;data=0} /^---PROFILEDATA---/{data=!data;next} data && /^[0-9]+,/ {n=split($0,a,","); if(n>=14 && a[1]+0==0 && a[14]>a[2]) {f++; if((a[14]-a[2])/1000000>16.6667)j++}} END{print f,j}' "$run_dir/gfxinfo.txt")
    read -r max_pss max_rss mean_cpu max_cpu max_thermal < <(awk -F, 'NR>1 {n++; cpu+=$3; if($3>mc)mc=$3; if($4>mp)mp=$4; if($5>mr)mr=$5; if($15>mt)mt=$15} END{printf "%d %d %.2f %.2f %d\n",mp,mr,n?cpu/n:0,mc,mt}' "$run_dir/samples.csv")
    rx_delta=$((rx_end >= rx_start ? rx_end-rx_start : 0)); tx_delta=$((tx_end >= tx_start ? tx_end-tx_start : 0))
    battery_drop=$(( ${battery_start:-0} >= ${battery_end:-0} ? ${battery_start:-0}-${battery_end:-0} : 0 ))
    janky_percent="$(awk -v f="$frames" -v j="$janky" 'BEGIN{printf "%.2f",f?100*j/f:0}')"
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$run" "$start_epoch_ms" "$am_total_ms" "$pid" "$rx_start" "$tx_start" "$rx_end" "$tx_end" "$rx_delta" "$tx_delta" "$frames" "$janky" "$janky_percent" "$max_pss" "$max_rss" "$mean_cpu" "$max_cpu" "$max_thermal" "$battery_drop" "$stable" "$connection_error" "$screenshot_valid" >>"$OUTPUT_DIR/runs.csv"
    adb_shell am force-stop "$PACKAGE" >/dev/null || true
    ((run == RUNS || SETTLE == 0)) || sleep "$SETTLE"
done

python3 "$script_dir/../tools/analyze-phone-world-loading.py" "$OUTPUT_DIR" | tee "$OUTPUT_DIR/summary.txt"
if [[ -n "$original_brightness" ]]; then
    adb_shell settings put system screen_brightness "$original_brightness" >/dev/null 2>&1 || true
    adb_shell settings put system screen_brightness_mode "${original_brightness_mode:-0}" >/dev/null 2>&1 || true
    original_brightness=''
fi
adb_shell "setprop debug.overte.navigate ''" >/dev/null 2>&1 || true
adb_shell "setprop debug.overte.test_mode ''" >/dev/null 2>&1 || true
adb_shell "setprop debug.overte.malloc_trim ''" >/dev/null 2>&1 || true
adb_shell "setprop debug.overte.malloc_decay ''" >/dev/null 2>&1 || true
trap - EXIT INT TERM
printf 'report=%s\n' "$OUTPUT_DIR"
