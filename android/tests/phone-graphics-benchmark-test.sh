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
+if [[ $1 == logcat && ${2:-} == -d ]]; then
+  printf 'I/OvertePhoneGraphics: profile_render_scale=0.5 profile_target_fps=30 profile_forward_msaa_samples=1 profile_haze=0 profile_local_lights=0\n'
+  case ${MOCK_RENDER_TIMING_MODE:-valid} in
+    valid) printf 'I/OvertePhoneGraphics: render_gpu_ms=7.25 render_batch_ms=1.50\n' ;;
+    malformed) printf 'I/OvertePhoneGraphics: render_gpu_ms=nan-private render_batch_ms=-1\n' ;;
+    missing) ;;
+  esac
+  case ${MOCK_OVERLAY_CACHE_MODE:-valid} in
+    valid) printf 'I/OvertePhoneGraphics: overlay_cache_enabled=1 overlay_cache_samples=600 overlay_cache_hits=450 overlay_cache_misses=150 overlay_cache_new_textures=149 overlay_cache_resizes=1\n' ;;
+    malformed) printf 'I/OvertePhoneGraphics: overlay_cache_enabled=1 overlay_cache_samples=600 overlay_cache_hits=500 overlay_cache_misses=200 overlay_cache_new_textures=private overlay_cache_resizes=1\n' ;;
+    missing) ;;
+  esac
+  case ${MOCK_MEMORY_MODE:-valid} in
+    valid) memory='memory_proc_valid=1 memory_rss_kib=123456 memory_data_kib=100000 memory_swap_kib=2345 memory_allocator_valid=1 memory_allocator_used_kib=77777 memory_allocator_free_kib=8888' ;;
+    malformed) memory='memory_proc_valid=1 memory_rss_kib=12x memory_data_kib=-1 memory_swap_kib=9223372036854775808 memory_allocator_valid=yes memory_allocator_used_kib=7.5 memory_allocator_free_kib=8' ;;
+    missing) memory='' ;;
+  esac
+  printf 'I/OvertePhoneGraphics: window_seconds=9.99 present_fps=1.00 new_frame_fps=1.00 inter_present_p50_ms=999.00 inter_present_p95_ms=999.00 inter_present_max_ms=999.00 memory_proc_valid=1 memory_rss_kib=1 memory_data_kib=1 memory_swap_kib=1 memory_allocator_valid=1 memory_allocator_used_kib=1 memory_allocator_free_kib=1\n'
+  case ${MOCK_FRAMEBUFFER_MODE:-valid} in
+    valid) framebuffer='framebuffer_primary_recreate_delta=2 framebuffer_primary_recreate_total=18446744073709551615 framebuffer_resolve_recreate_delta=1 framebuffer_resolve_recreate_total=42 framebuffer_primary_width=1458 framebuffer_primary_height=655 framebuffer_primary_samples=1 framebuffer_resolve_width=1458 framebuffer_resolve_height=655 framebuffer_resolve_samples=1 framebuffer_estimated_mib=10.93' ;;
+    malformed) framebuffer='framebuffer_primary_recreate_delta=43 framebuffer_primary_recreate_total=42 framebuffer_resolve_recreate_delta=-1 framebuffer_resolve_recreate_total=18446744073709551616 framebuffer_primary_width=0 framebuffer_primary_height=999999 framebuffer_primary_samples=65 framebuffer_resolve_width=12x framebuffer_resolve_height=655 framebuffer_resolve_samples=1 framebuffer_estimated_mib=nan-private' ;;
+    missing) framebuffer='' ;;
+  esac
+  case ${MOCK_GPU_MODE:-valid} in
+    valid) gpu='gpu_buffer_count=123 gpu_buffer_mib=45.50 gpu_texture_resident_count=7 gpu_texture_resident_mib=8.25 gpu_texture_framebuffer_count=9 gpu_texture_framebuffer_mib=10.75 gpu_texture_resource_count=321 texture_resource_mib=192.25 gpu_texture_external_count=2 gpu_texture_external_mib=3.50 texture_populated_mib=190.75 gpu_texture_pending_transfer_count=4 texture_pending_transfer_mib=1.50' ;;
+    malformed) gpu='gpu_buffer_count=-1 gpu_buffer_mib=nan-private gpu_texture_resident_count=7x gpu_texture_resident_mib=-8 gpu_texture_framebuffer_count=18446744073709551616 gpu_texture_framebuffer_mib=10.75 gpu_texture_resource_count=yes texture_resource_mib=192.25 gpu_texture_external_count=2 gpu_texture_external_mib=inf texture_populated_mib=190.75 gpu_texture_pending_transfer_count=4.5 texture_pending_transfer_mib=1.50' ;;
+    missing) gpu='' ;;
+  esac
+  case ${MOCK_TRASH_MODE:-valid} in
+    valid|mismatch) trash='gl_trash_buffer_enqueued_delta=10 gl_trash_buffer_cleaned_delta=8 gl_trash_buffer_backlog=2 gl_trash_texture_enqueued_delta=20 gl_trash_texture_cleaned_delta=19 gl_trash_texture_backlog=1 gl_trash_external_texture_enqueued_delta=3 gl_trash_external_texture_cleaned_delta=3 gl_trash_external_texture_backlog=0 gl_trash_framebuffer_enqueued_delta=4 gl_trash_framebuffer_cleaned_delta=4 gl_trash_framebuffer_backlog=0 gl_trash_buffer_bytes_enqueued_delta=1048576 gl_trash_buffer_bytes_cleaned_delta=524288 gl_trash_buffer_pending_mib=0.50' ;;
+    malformed) trash='gl_trash_buffer_enqueued_delta=-1 gl_trash_buffer_cleaned_delta=8 gl_trash_buffer_backlog=2 gl_trash_texture_enqueued_delta=20x gl_trash_texture_cleaned_delta=19 gl_trash_texture_backlog=1 gl_trash_external_texture_enqueued_delta=3 gl_trash_external_texture_cleaned_delta=18446744073709551616 gl_trash_external_texture_backlog=0 gl_trash_framebuffer_enqueued_delta=yes gl_trash_framebuffer_cleaned_delta=4 gl_trash_framebuffer_backlog=0 gl_trash_buffer_bytes_enqueued_delta=1048576 gl_trash_buffer_bytes_cleaned_delta=524288 gl_trash_buffer_pending_mib=nan-private' ;;
+    missing) trash='' ;;
+  esac
+  trash_window_id=7
+  [[ ${MOCK_TRASH_MODE:-valid} == mismatch ]] && trash_window_id=6
+  printf 'I/OvertePhoneGraphics: record=present window_id=7 window_seconds=10.02 present_fps=30.00 new_frame_fps=29.50 inter_present_p50_ms=33.20 inter_present_p95_ms=34.10 inter_present_max_ms=40.00 %s\n' "$gpu"
+  printf 'I/OvertePhoneGraphics: record=trash window_id=%s %s\n' "$trash_window_id" "$trash"
+  printf 'I/OvertePhoneGraphics: record=state window_id=7 %s %s\n' "$framebuffer" "$memory"
+  exit
+fi
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
grep -q '^overlay_cache_metrics_valid=1$' "$summary"
grep -q '^overlay_cache_enabled=1$' "$summary"
grep -q '^overlay_cache_samples=600$' "$summary"
grep -q '^overlay_cache_hits=450$' "$summary"
grep -q '^overlay_cache_misses=150$' "$summary"
grep -q '^overlay_cache_hit_percent=75.00$' "$summary"
grep -q '^overlay_cache_new_textures=149$' "$summary"
grep -q '^overlay_cache_resizes=1$' "$summary"
grep -q '^render_timing_metrics_valid=1$' "$summary"
grep -q '^render_gpu_ms=7.25$' "$summary"
grep -q '^render_batch_ms=1.50$' "$summary"
grep -q '^native_present_metrics_available=1$' "$summary"
grep -q '^native_present_fps=30.00$' "$summary"
grep -q '^native_present_window_seconds=10.02$' "$summary"
grep -q '^native_new_frame_fps=29.50$' "$summary"
grep -q '^native_inter_present_p95_ms=34.10$' "$summary"
grep -q '^gpu_live_metrics_valid=1$' "$summary"
grep -q '^gpu_buffer_count=123$' "$summary"
grep -q '^gpu_buffer_mib=45.50$' "$summary"
grep -q '^gpu_texture_resident_count=7$' "$summary"
grep -q '^gpu_texture_resident_mib=8.25$' "$summary"
grep -q '^gpu_texture_framebuffer_count=9$' "$summary"
grep -q '^gpu_texture_framebuffer_mib=10.75$' "$summary"
grep -q '^gpu_texture_resource_count=321$' "$summary"
grep -q '^texture_resource_mib=192.25$' "$summary"
grep -q '^gpu_texture_external_count=2$' "$summary"
grep -q '^gpu_texture_external_mib=3.50$' "$summary"
grep -q '^texture_populated_mib=190.75$' "$summary"
grep -q '^gpu_texture_pending_transfer_count=4$' "$summary"
grep -q '^texture_pending_transfer_mib=1.50$' "$summary"
grep -q '^gl_trash_metrics_valid=1$' "$summary"
grep -q '^gl_trash_buffer_enqueued_delta=10$' "$summary"
grep -q '^gl_trash_buffer_cleaned_delta=8$' "$summary"
grep -q '^gl_trash_buffer_backlog=2$' "$summary"
grep -q '^gl_trash_texture_backlog=1$' "$summary"
grep -q '^gl_trash_external_texture_backlog=0$' "$summary"
grep -q '^gl_trash_framebuffer_enqueued_delta=4$' "$summary"
grep -q '^gl_trash_buffer_bytes_enqueued_delta=1048576$' "$summary"
grep -q '^gl_trash_buffer_bytes_cleaned_delta=524288$' "$summary"
grep -q '^gl_trash_buffer_pending_mib=0.50$' "$summary"
grep -q '^memory_proc_valid=1$' "$summary"
grep -q '^memory_rss_kib=123456$' "$summary"
grep -q '^memory_data_kib=100000$' "$summary"
grep -q '^memory_swap_kib=2345$' "$summary"
grep -q '^memory_allocator_valid=1$' "$summary"
grep -q '^memory_allocator_used_kib=77777$' "$summary"
grep -q '^memory_allocator_free_kib=8888$' "$summary"
grep -q '^framebuffer_metrics_valid=1$' "$summary"
grep -q '^framebuffer_primary_recreate_delta=2$' "$summary"
grep -q '^framebuffer_primary_recreate_total=18446744073709551615$' "$summary"
grep -q '^framebuffer_resolve_recreate_delta=1$' "$summary"
grep -q '^framebuffer_resolve_recreate_total=42$' "$summary"
grep -q '^framebuffer_primary_width=1458$' "$summary"
grep -q '^framebuffer_primary_height=655$' "$summary"
grep -q '^framebuffer_primary_samples=1$' "$summary"
grep -q '^framebuffer_resolve_width=1458$' "$summary"
grep -q '^framebuffer_resolve_height=655$' "$summary"
grep -q '^framebuffer_resolve_samples=1$' "$summary"
grep -q '^framebuffer_estimated_mib=10.93$' "$summary"
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

malformed_report="$fixture/malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/malformed-exits" MOCK_MEMORY_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^memory_proc_valid=0$' "$malformed_report/summary.txt"
grep -q '^memory_rss_kib=unknown$' "$malformed_report/summary.txt"
grep -q '^memory_swap_kib=unknown$' "$malformed_report/summary.txt"
grep -q '^memory_allocator_valid=0$' "$malformed_report/summary.txt"
grep -q '^memory_allocator_used_kib=unknown$' "$malformed_report/summary.txt"

missing_report="$fixture/missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/missing-exits" MOCK_MEMORY_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^memory_proc_valid=0$' "$missing_report/summary.txt"
grep -q '^memory_rss_kib=unknown$' "$missing_report/summary.txt"
grep -q '^memory_allocator_valid=0$' "$missing_report/summary.txt"
grep -q '^memory_allocator_used_kib=unknown$' "$missing_report/summary.txt"
gpu_malformed_report="$fixture/gpu-malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/gpu-malformed-exits" MOCK_GPU_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$gpu_malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^gpu_live_metrics_valid=0$' "$gpu_malformed_report/summary.txt"
grep -q '^gpu_buffer_count=unknown$' "$gpu_malformed_report/summary.txt"
grep -q '^gpu_texture_resident_mib=unknown$' "$gpu_malformed_report/summary.txt"
grep -q '^gpu_texture_pending_transfer_count=unknown$' "$gpu_malformed_report/summary.txt"
grep -q '^texture_resource_mib=unknown$' "$gpu_malformed_report/summary.txt"

gpu_missing_report="$fixture/gpu-missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/gpu-missing-exits" MOCK_GPU_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$gpu_missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^gpu_live_metrics_valid=0$' "$gpu_missing_report/summary.txt"
grep -q '^gpu_texture_framebuffer_count=unknown$' "$gpu_missing_report/summary.txt"
grep -q '^gpu_texture_external_mib=unknown$' "$gpu_missing_report/summary.txt"
trash_malformed_report="$fixture/trash-malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/trash-malformed-exits" MOCK_TRASH_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$trash_malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^gl_trash_metrics_valid=0$' "$trash_malformed_report/summary.txt"
grep -q '^gl_trash_buffer_enqueued_delta=unknown$' "$trash_malformed_report/summary.txt"
grep -q '^gl_trash_external_texture_cleaned_delta=unknown$' "$trash_malformed_report/summary.txt"
grep -q '^gl_trash_buffer_pending_mib=unknown$' "$trash_malformed_report/summary.txt"

trash_missing_report="$fixture/trash-missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/trash-missing-exits" MOCK_TRASH_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$trash_missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^gl_trash_metrics_valid=0$' "$trash_missing_report/summary.txt"
grep -q '^gl_trash_texture_backlog=unknown$' "$trash_missing_report/summary.txt"
trash_mismatch_report="$fixture/trash-mismatch-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/trash-mismatch-exits" MOCK_TRASH_MODE=mismatch \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$trash_mismatch_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^gl_trash_metrics_valid=0$' "$trash_mismatch_report/summary.txt"
grep -q '^gl_trash_buffer_backlog=unknown$' "$trash_mismatch_report/summary.txt"
framebuffer_malformed_report="$fixture/framebuffer-malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/framebuffer-malformed-exits" MOCK_FRAMEBUFFER_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$framebuffer_malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^framebuffer_metrics_valid=0$' "$framebuffer_malformed_report/summary.txt"
grep -q '^framebuffer_primary_recreate_delta=unknown$' "$framebuffer_malformed_report/summary.txt"
grep -q '^framebuffer_primary_recreate_total=unknown$' "$framebuffer_malformed_report/summary.txt"
grep -q '^framebuffer_estimated_mib=unknown$' "$framebuffer_malformed_report/summary.txt"

framebuffer_missing_report="$fixture/framebuffer-missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/framebuffer-missing-exits" MOCK_FRAMEBUFFER_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$framebuffer_missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^framebuffer_metrics_valid=0$' "$framebuffer_missing_report/summary.txt"
grep -q '^framebuffer_primary_width=unknown$' "$framebuffer_missing_report/summary.txt"
grep -q '^framebuffer_resolve_samples=unknown$' "$framebuffer_missing_report/summary.txt"
overlay_cache_malformed_report="$fixture/overlay-cache-malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/overlay-cache-malformed-exits" MOCK_OVERLAY_CACHE_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$overlay_cache_malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^overlay_cache_metrics_valid=0$' "$overlay_cache_malformed_report/summary.txt"
grep -q '^overlay_cache_hits=unknown$' "$overlay_cache_malformed_report/summary.txt"
grep -q '^overlay_cache_new_textures=unknown$' "$overlay_cache_malformed_report/summary.txt"
overlay_cache_missing_report="$fixture/overlay-cache-missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/overlay-cache-missing-exits" MOCK_OVERLAY_CACHE_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$overlay_cache_missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^overlay_cache_metrics_valid=0$' "$overlay_cache_missing_report/summary.txt"
grep -q '^overlay_cache_enabled=unknown$' "$overlay_cache_missing_report/summary.txt"
render_timing_malformed_report="$fixture/render-timing-malformed-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/render-timing-malformed-exits" MOCK_RENDER_TIMING_MODE=malformed \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$render_timing_malformed_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^render_timing_metrics_valid=0$' "$render_timing_malformed_report/summary.txt"
grep -q '^render_gpu_ms=unknown$' "$render_timing_malformed_report/summary.txt"
render_timing_missing_report="$fixture/render-timing-missing-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/render-timing-missing-exits" MOCK_RENDER_TIMING_MODE=missing \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$render_timing_missing_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^render_timing_metrics_valid=0$' "$render_timing_missing_report/summary.txt"
grep -q '^render_batch_ms=unknown$' "$render_timing_missing_report/summary.txt"
if grep -Eqi 'phone-secret|private|serial|account|url|manufacturer|model|fingerprint|android_id|domain|12x|9223372036854775808' \
        "$malformed_report/summary.txt" "$missing_report/summary.txt" \
        "$gpu_malformed_report/summary.txt" "$gpu_missing_report/summary.txt" \
        "$trash_malformed_report/summary.txt" "$trash_missing_report/summary.txt" "$trash_mismatch_report/summary.txt" \
        "$framebuffer_malformed_report/summary.txt" "$framebuffer_missing_report/summary.txt" \
        "$overlay_cache_malformed_report/summary.txt" "$overlay_cache_missing_report/summary.txt" \
        "$render_timing_malformed_report/summary.txt" "$render_timing_missing_report/summary.txt"; then
    echo 'FAIL: malformed or identifying data escaped into aggregate report' >&2; exit 1
fi
printf 'Phone graphics benchmark harness checks passed.\n'
