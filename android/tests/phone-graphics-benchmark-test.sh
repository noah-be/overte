#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fixture="$(mktemp -d /tmp/overte-phone-graphics-harness-test.XXXXXXXX)"
trap 'rm -rf -- "$fixture"' EXIT INT TERM
report="$fixture/report"

sed 's/^+//' >"$fixture/adb" <<'MOCK'
+#!/usr/bin/env bash
+set -euo pipefail
+if [[ ${1:-} == devices ]]; then printf 'List of devices attached\nphone-secret device product:private\n'; exit; fi
+[[ ${1:-} == -s && ${2:-} == phone-secret ]] || exit 90
+shift 2
+if [[ $1 == shell && $2 == getprop ]]; then
+  [[ $3 == ro.build.characteristics ]] && printf 'phone\n' || printf 'Generic\n'; exit
+fi
+if [[ $1 == shell && $2 == pidof ]]; then
+  if [[ -n ${MOCK_PID_CHANGE_FILE:-} ]]; then
+    count=0; [[ -f $MOCK_PID_CHANGE_FILE ]] && read -r count <"$MOCK_PID_CHANGE_FILE"
+    count=$((count + 1)); printf '%s\n' "$count" >"$MOCK_PID_CHANGE_FILE"
+    (( count > 1 )) && { printf '4343\n'; exit; }
+  fi
+  printf '4242\n'; exit
+fi
+if [[ $1 == shell && $2 == dumpsys && $3 == gfxinfo && ${5:-} == framestats ]]; then
+  [[ ${MOCK_INVALID_FRAMESTATS:-} == 1 ]] && { printf 'unsupported output\n'; exit; }
+  printf '%s\n' '---PROFILEDATA---' 'Flags,IntendedVsync,Vsync,OldestInputEvent,NewestInputEvent,HandleInputStart,AnimationStart,PerformTraversalsStart,DrawStart,FrameDeadline,FrameInterval,FrameStartTime,SyncQueued,FrameCompleted' '0,1000000,0,0,0,0,0,0,0,0,0,0,0,11000000' '1,12000000,0,0,0,0,0,0,0,0,0,0,0,900000000' '0,20000000,0,0,0,0,0,0,0,0,0,0,0,50000000' '---PROFILEDATA---'; exit
+fi
+if [[ $1 == shell && $2 == dumpsys && $3 == thermalservice ]]; then printf 'Thermal Status: 3 serial=phone-secret\n'; exit; fi
+if [[ $1 == shell && $2 == dumpsys && $3 == activity ]]; then
+  [[ ${MOCK_EXIT_INFO_FAIL:-} == 1 ]] && exit 1
+  count_file="${MOCK_EXIT_COUNT_FILE:?}"; count=0; [[ -f $count_file ]] && read -r count <"$count_file"
+  count=$((count + 1)); printf '%s\n' "$count" >"$count_file"
+  if (( count > 1 )); then printf 'reason=CRASH private-account@example.test\n'; fi
+  exit
+fi
+if [[ $1 == logcat && ${2:-} == -d ]]; then printf 'PHONE_GRAPHICS_PROFILE renderScale 0.5 targetFps 30 forwardMsaaSamples 1 url=https://private.example\n'; exit; fi
+exit 0
MOCK
chmod +x "$fixture/adb"

if PHONE_ADB="$fixture/adb" ANDROID_SERIAL=phone-secret "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null 2>&1; then
    echo 'FAIL: benchmark ran without explicit non-VR confirmation' >&2; exit 1
fi
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$report" PHONE_BENCHMARK_INTERVAL=1 \
    "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
summary="$report/summary.txt"
grep -q '^frames=2$' "$summary"
grep -q '^framestats_valid=1$' "$summary"
grep -q '^observed_frames_per_second=2.00$' "$summary"
grep -q '^janky_frames=1$' "$summary"
grep -q '^max_thermal_status=3$' "$summary"
grep -q '^exit_info_queries_valid=1$' "$summary"
grep -q '^crash_records_before=0$' "$summary"
grep -q '^crash_records_after=1$' "$summary"
grep -q '^crash_record_count_increased=1$' "$summary"
grep -q '^stable_process=1$' "$summary"
grep -q '^profile_viewport_scale=0.5$' "$summary"
[[ $(stat -c '%a' "$report") == 700 ]]
[[ $(stat -c '%a' "$summary") == 600 ]]
grep -q '^profile_target_fps=30$' "$summary"
if grep -Eqi 'phone-secret|private|serial|account|url|manufacturer|model|fingerprint|android_id|domain' "$summary"; then
    echo 'FAIL: identifying/raw data escaped into aggregate report' >&2; exit 1
fi
if find /tmp -maxdepth 1 -type d -name 'overte-phone-graphics-raw.*' -newer "$fixture/adb" | grep -q .; then
    echo 'FAIL: raw benchmark directory survived' >&2; exit 1
fi
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$script_dir/forbidden-report" "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null 2>&1; then
    echo 'FAIL: benchmark report was accepted inside worktree' >&2; exit 1
fi
[[ ! -e "$script_dir/forbidden-report" ]] || { echo 'FAIL: rejected report path was created' >&2; exit 1; }
symlink_report="$fixture/symlink-report"
mkdir -p "$symlink_report"
protected="$fixture/protected"
printf 'do-not-overwrite\n' >"$protected"
ln -s "$protected" "$symlink_report/summary.txt"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$symlink_report" PHONE_BENCHMARK_INTERVAL=1 \
    "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null 2>&1; then
    echo 'FAIL: benchmark overwrote a symlinked summary' >&2; exit 1
fi
grep -q '^do-not-overwrite$' "$protected"

unstable_report="$fixture/unstable-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/unstable-exits" MOCK_PID_CHANGE_FILE="$fixture/pid-count" \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$unstable_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 2 >/dev/null
grep -q '^stable_process=0$' "$unstable_report/summary.txt"

invalid_report="$fixture/invalid-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/invalid-exits" MOCK_INVALID_FRAMESTATS=1 MOCK_EXIT_INFO_FAIL=1 \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$invalid_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^framestats_valid=0$' "$invalid_report/summary.txt"
grep -q '^exit_info_queries_valid=0$' "$invalid_report/summary.txt"
printf 'Phone graphics benchmark harness checks passed.\n'
