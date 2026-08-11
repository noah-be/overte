#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fixture="$(mktemp -d /tmp/overte-phone-world-loading-test.XXXXXXXX)"
trap 'rm -rf -- "$fixture"' EXIT INT TERM
mkdir "$fixture/bin"

cat >"$fixture/bin/adb" <<'ADB'
#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == devices ]]; then
    printf 'List of devices attached\nmock-phone device product:test model:Phone\n'
    exit 0
fi
[[ ${1:-} == -s && ${2:-} == mock-phone ]] || exit 90
shift 2
command="$*"
case "$command" in
    'exec-out screencap -p') printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkAQMAAABKLAcXAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURaBgMP///9XcAd8AAAABYktHRAH/Ai3eAAAAB3RJTUUH6ggJFhoJ5ykLsgAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyNi0wOC0wOVQyMjoyNjowOSswMDowMOtv0poAAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjYtMDgtMDlUMjI6MjY6MDkrMDA6MDCaMmomAAAAKHRFWHRkYXRlOnRpbWVzdGFtcAAyMDI2LTA4LTA5VDIyOjI2OjA5KzAwOjAwzSdL+QAAABRJREFUOMtjYBgFo2AUjIJRQE8AAAV4AAEpcbn8AAAAAElFTkSuQmCC' | base64 -d ;;
    'shell getprop ro.product.manufacturer') echo Generic ;;
    'shell getprop ro.product.brand') echo Test ;;
    'shell getprop ro.product.model') echo Phone ;;
    'shell getprop ro.product.device') echo phone ;;
    'shell getprop ro.build.characteristics') echo phone ;;
    'shell getprop ro.kernel.qemu') echo 0 ;;
    'shell getprop ro.build.version.sdk') echo 35 ;;
    'shell getprop ro.build.fingerprint') echo test/fingerprint ;;
    'shell settings get system screen_brightness') echo 128 ;;
    'shell settings get system screen_brightness_mode') echo 0 ;;
    'shell pm path org.overte.phone') echo package:/data/app/org.overte.phone/base.apk ;;
    'shell dumpsys package org.overte.phone') echo '  appId=10123' ;;
    'shell run-as org.overte.phone cat cache/world-status') echo '1786300000|1|test.example|12345678-1234-1234-1234-123456789abc|1.000|2.000|3.000|1|20|12.500|42|1|0|0|1048576' ;;
    'shell cat /proc/uid_stat/10123/tcp_rcv') echo 2097152 ;;
    'shell cat /proc/uid_stat/10123/tcp_snd') echo 1048576 ;;
    'shell dumpsys battery') printf '%s\n' '  AC powered: true' '  USB powered: false' '  Wireless powered: false' '  Dock powered: false' '  Max charging current: 2000000' '  Max charging voltage: 9000000' '  status: 2' '  level: 80' '  Charging state: 1' ;;
    'shell am start -W '*) printf 'Status: ok\nTotalTime: 321\n' ;;
    'shell pidof org.overte.phone') echo 4242 ;;
    'shell top -b -n 1 -p 4242') echo '4242 u0_a123 10 -10 3G 300M 200M S 25.0 3.0 0:01 org.overte.phone' ;;
    'shell run-as org.overte.phone cat /proc/4242/smaps_rollup') printf '%s\n' 'Rss: 307200 kB' 'Pss: 204800 kB' 'SwapPss: 1024 kB' 'Private_Dirty: 100000 kB' 'Private_Clean: 100000 kB' ;;
    'shell run-as org.overte.phone cat /proc/4242/smaps') printf '%s\n' '1000-2000 rw-p 0 00:00 0 [anon:libc_malloc]' 'Pss: 100 kB' '2000-3000 rw-p 0 00:00 0 [anon:dalvik-main space]' 'Pss: 200 kB' ;;
    'shell cat /proc/4242/status') printf '%s\n' 'RssAnon: 200000 kB' 'RssFile: 106000 kB' 'RssShmem: 1200 kB' 'VmSwap: 2048 kB' ;;
    "shell run-as org.overte.phone sh -c 'ls /proc/4242/fd 2>/dev/null | wc -l'") echo 42 ;;
    'shell run-as org.overte.phone du -sk cache') echo '4096 cache' ;;
    'shell dumpsys thermalservice') printf '%s\n' 'Thermal Status: 2' 'Current temperatures from HAL:' ' Temperature{mValue=42.0, mType=0, mName=BIG, mStatus=0}' ' Temperature{mValue=39.0, mType=1, mName=G3D, mStatus=0}' ' Temperature{mValue=33.0, mType=2, mName=battery, mStatus=0}' ' Temperature{mValue=35.0, mType=3, mName=skin, mStatus=0}' 'Current cooling devices from HAL:' ;;
    'shell printf "%s %s %s\n" "$(cat /sys/class/power_supply/battery/current_now 2>/dev/null || echo 0)" "$(cat /sys/class/power_supply/battery/voltage_now 2>/dev/null || echo 0)" "$(cat /sys/class/power_supply/battery/charge_counter 2>/dev/null || echo 0)"') echo '-100000 4100000 3000000' ;;
    'shell printf "%s %s " "$(settings get system screen_brightness)" "$(settings get system screen_brightness_mode)"; dumpsys display | sed -nE "s/^[[:space:]]*Display Brightness=([^[:space:]]+).*/\\1/p" | head -n1') echo '128 0 0.5' ;;
    'shell cmd wifi status') echo 'WifiInfo: RSSI: -55, Link speed: 600Mbps, Tx Link speed: 500Mbps, Rx Link speed: 700Mbps, Frequency: 5180MHz' ;;
    'shell for z in /sys/class/thermal/'*) echo '42000 39000' ;;
    'shell dumpsys gfxinfo org.overte.phone framestats')
        printf '%s\n' '---PROFILEDATA---' \
          'Flags,IntendedVsync,Vsync,OldestInputEvent,NewestInputEvent,HandleInputStart,AnimationStart,PerformTraversalsStart,DrawStart,FrameDeadline,FrameInterval,FrameStartTime,SyncQueued,FrameCompleted' \
          '0,1000000,0,0,0,0,0,0,0,0,0,0,0,11000000' \
          '0,20000000,0,0,0,0,0,0,0,0,0,0,0,50000000' '---PROFILEDATA---'
        ;;
    'shell dumpsys meminfo org.overte.phone') echo 'TOTAL PSS: 204800 TOTAL RSS: 307200' ;;
    'logcat --pid=4242 -v threadtime') printf '%s\n' 'I OvertePhoneGraphics: record=present window_id=1 window_seconds=10 present_fps=30 new_frame_fps=30 inter_present_p50_ms=33 inter_present_p95_ms=40 inter_present_max_ms=45 gpu_texture_resident_mib=1 texture_resource_mib=35' 'I OvertePhoneGraphics: render_gpu_ms=10 render_batch_ms=5' 'W Interface: PHONE_PERF record=script_heap epoch_ms=1786300000000 script=file%3A%2Ftest.js total_heap_bytes=1000 used_heap_bytes=500 available_bytes=2000 used_global_handles_bytes=10' ;;
    *) ;;
esac
ADB
chmod +x "$fixture/bin/adb"

report="$fixture/report"
if ! ANDROID_SERIAL=mock-phone PHONE_PERF_CONFIRM_NON_VR=YES PHONE_DEVICE_LOCK_HELD=1 \
        PHONE_ADB="$fixture/bin/adb" "$script_dir/phone-world-loading-test.sh" \
    --target overte://test.example/1,2,3 --runs 1 --duration 5 --warmup 0 --settle 0 \
        --output-dir "$report" >"$fixture/output.txt" 2>&1; then
    cat "$fixture/output.txt" >&2
    exit 1
fi

grep -Fq 'Overte Android Phone world-loading performance' "$report/summary.txt"
grep -Fq 'run 1:' "$report/summary.txt"
[[ "$(wc -l <"$report/run-1/samples.csv")" == 6 ]]
awk -F, 'NR==2 {exit !($1==1 && $3==321 && $4==4242 && $11==2 && $12==1 && $14==204800 && $16==25 && $18==2 && $20==1 && $22==1)}' "$report/runs.csv"
awk -F, 'NR==2 {exit !($6==1024 && $9==200000 && $15==2 && $18==1 && $19==1 && $23==1 && $24==2000000 && $29==42000 && $30==39000 && $33==128 && $34==0 && $35==0.5 && $36==-55 && $40==5180)}' "$report/run-1/samples.csv"
awk -F, 'NR==2 {exit !($3==200 && $4==100 && $12==0 && $13==42 && $14==4096)}' "$report/run-1/memory-detail.csv"
awk -F, 'NR==2 {exit !($1==1786300000000 && $3==1000 && $4==500 && $6==10)}' "$report/run-1/script-memory.csv"
identify "$report/run-1/final-overte-hub.png" >/dev/null
grep -Fq 'target' "$report/device.csv"
printf 'phone world-loading mock test passed\n'
