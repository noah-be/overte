#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-graphics-harness-test.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM
report="$fixture/report"
mkdir "$fixture/private-tmp"
readonly real_mktemp="$(command -v mktemp)"
readonly real_sleep="$(command -v sleep)"
readonly real_chmod="$(command -v chmod)"
readonly real_rm="$(command -v rm)"
export PHONE_BENCHMARK_TEST_REAL_MKTEMP="$real_mktemp"
export PHONE_BENCHMARK_TEST_REAL_SLEEP="$real_sleep"
export PHONE_BENCHMARK_TEST_REAL_CHMOD="$real_chmod"
export PHONE_BENCHMARK_TEST_REAL_RM="$real_rm"
export PHONE_BENCHMARK_TEST_TMPDIR="$fixture/private-tmp"
export PHONE_BENCHMARK_TEST_MKTEMP_LOG="$fixture/mktemp-templates"
# The fixture supplies fake ADB and must never contend for the real shared
# device lock or its post-device cooldown.
export PHONE_DEVICE_LOCK_HELD=1

mkdir "$fixture/bin"
cat >"$fixture/bin/mktemp" <<'MOCK_MKTEMP'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_SUMMARY_MKTEMP_FAILURE:-0}" == 1 && "$*" == *'.summary.txt.'* ]]; then
    printf 'private summary allocation failure: %s\n' "$*" >&2
    exit 7
fi
args=()
for arg in "$@"; do
    if [[ "$arg" == /tmp/overte-phone-graphics-*.XXXXXXXX ]]; then
        printf '%s\n' "$arg" >>"$PHONE_BENCHMARK_TEST_MKTEMP_LOG"
        arg="$PHONE_BENCHMARK_TEST_TMPDIR/${arg##*/}"
    fi
    args+=("$arg")
done
exec "$PHONE_BENCHMARK_TEST_REAL_MKTEMP" "${args[@]}"
MOCK_MKTEMP
chmod +x "$fixture/bin/mktemp"
cat >"$fixture/bin/sleep" <<'MOCK_SLEEP'
#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${MOCK_SLEEP_SIGNAL:-}" ]]; then
    kill -s "$MOCK_SLEEP_SIGNAL" "$PPID"
    exec "$PHONE_BENCHMARK_TEST_REAL_SLEEP" 0.1
fi
exec "$PHONE_BENCHMARK_TEST_REAL_SLEEP" "$@"
MOCK_SLEEP
chmod +x "$fixture/bin/sleep"
cat >"$fixture/bin/chmod" <<'MOCK_CHMOD'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_SUMMARY_CHMOD_SIGNAL_TERM:-0}" == 1 && "$*" == *'.summary.txt.'* ]]; then
    kill -TERM "$PPID"
fi
if [[ "${MOCK_REPORT_CHMOD_FAILURE:-0}" == 1 && "$*" == *'overte-phone-graphics-report.'* ]]; then
    printf 'private report chmod failure: %s\n' "$*" >&2
    exit 8
fi
if [[ "${MOCK_RAW_CHMOD_FAILURE:-0}" == 1 && "$*" == *'overte-phone-graphics-raw.'* ]]; then
    printf 'private raw chmod failure: %s\n' "$*" >&2
    exit 9
fi
exec "$PHONE_BENCHMARK_TEST_REAL_CHMOD" "$@"
MOCK_CHMOD
chmod +x "$fixture/bin/chmod"
cat >"$fixture/bin/rm" <<'MOCK_RM'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_RAW_RM_FAILURE:-0}" == 1 && "$*" == *'overte-phone-graphics-raw.'* ]]; then
    "$PHONE_BENCHMARK_TEST_REAL_RM" "$@"
    printf 'private raw cleanup failure: %s\n' "$*" >&2
    exit 10
fi
exec "$PHONE_BENCHMARK_TEST_REAL_RM" "$@"
MOCK_RM
chmod +x "$fixture/bin/rm"
export PATH="$fixture/bin:$PATH"

sed 's/^+//' >"$fixture/adb" <<'MOCK'
+#!/usr/bin/env bash
+set -euo pipefail
+if [[ ${MOCK_PRIVATE_ADB_STDERR:-0} == 1 ]]; then
+  printf 'private adb transport: serial=phone-secret account=private@example.test\n' >&2
+fi
+if [[ ${1:-} == devices ]]; then printf 'List of devices attached\nphone-secret device product:private\n'; exit; fi
+[[ ${1:-} == -s && ${2:-} == phone-secret ]] || exit 90
+shift 2
+if [[ -n ${MOCK_ADB_COMMAND_LOG:-} ]]; then printf '%s\n' "$*" >>"$MOCK_ADB_COMMAND_LOG"; fi
+if [[ $1 == shell && $2 == dumpsys && $3 == gfxinfo && ${5:-} == reset &&
+      ${MOCK_GFX_RESET_FAILURE:-0} == 1 ]]; then
+  printf 'private reset failure for phone-secret\n' >&2; exit 11
+fi
+if [[ $1 == shell && $2 == dumpsys && $3 == gfxinfo && ${5:-} == framestats &&
+      ${MOCK_FRAMESTATS_ADB_FAILURE:-0} == 1 ]]; then
+  printf 'private framestats failure for phone-secret\n' >&2; exit 13
+fi
+if [[ $1 == shell && $2 == am && $3 == start && ${MOCK_START_FAILURE:-0} == 1 ]]; then
+  printf 'private Activity failure for phone-secret\n' >&2; exit 12
+fi
+if [[ $1 == shell && $2 == am && $3 == force-stop &&
+      ${MOCK_FINAL_CLEANUP_FAILURE:-0} == 1 ]]; then
+  printf 'private cleanup failure for phone-secret\n' >&2; exit 14
+fi
+if [[ $1 == shell && $2 == getprop ]]; then
+  case $3 in
+    ro.build.characteristics) printf '%s\n' "${MOCK_CHARACTERISTICS:-phone}" ;;
+    ro.kernel.qemu) printf '%s\n' "${MOCK_QEMU:-0}" ;;
+    ro.product.cpu.abilist) printf '%s\n' "${MOCK_ABIS:-arm64-v8a}" ;;
+    ro.build.version.sdk) printf '%s\n' "${MOCK_SDK:-36}" ;;
+    ro.opengles.version) printf '%s\n' "${MOCK_GLES:-196610}" ;;
+    *) printf '%s\n' "${MOCK_PRODUCT_IDENTITY:-Generic}" ;;
+  esac
+  exit
+fi
+if [[ $1 == shell && $2 == pm && $3 == list && $4 == features ]]; then
+  printf '%s\n' "${MOCK_FEATURES-feature:android.hardware.touchscreen}"; exit
+fi
+if [[ $1 == shell && $2 == pidof ]]; then
+  if [[ -n ${MOCK_PID_DELAY_FILE:-} ]]; then
+    delay_count=0; [[ -f $MOCK_PID_DELAY_FILE ]] && read -r delay_count <"$MOCK_PID_DELAY_FILE"
+    delay_count=$((delay_count + 1)); printf '%s\n' "$delay_count" >"$MOCK_PID_DELAY_FILE"
+    (( delay_count <= 2 )) && exit 1
+  fi
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
if PHONE_ADB="$fixture/adb" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    "$script_dir/phone-graphics-benchmark.sh" 3601 >"$fixture/long-duration.out" 2>&1; then
    echo 'FAIL: benchmark accepted an excessive duration' >&2; exit 1
fi
grep -Fxq 'ERROR: duration must be an integer from 1 through 3600 seconds' \
    "$fixture/long-duration.out"
if PHONE_ADB="$fixture/adb" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_INTERVAL=301 "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/long-interval.out" 2>&1; then
    echo 'FAIL: benchmark accepted an excessive sampling interval' >&2; exit 1
fi
grep -Fxq 'ERROR: PHONE_BENCHMARK_INTERVAL must be an integer from 1 through 300 seconds' \
    "$fixture/long-interval.out"
touch "$fixture/report-chmod-marker"
if PHONE_ADB="$fixture/adb" MOCK_REPORT_CHMOD_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/report-chmod.out" 2>&1; then
    echo 'FAIL: benchmark accepted insecure automatic report permissions' >&2; exit 1
fi
grep -Fxq 'ERROR: could not secure benchmark report directory' "$fixture/report-chmod.out"
! grep -Eq 'private report chmod failure|overte-phone-graphics-report[.]' \
    "$fixture/report-chmod.out"
if find /tmp -maxdepth 1 -type d -name 'overte-phone-graphics-report.*' \
        -newer "$fixture/report-chmod-marker" | grep -q .; then
    echo 'FAIL: report chmod failure retained an automatic report directory' >&2; exit 1
fi
touch "$fixture/raw-chmod-marker"
if PHONE_ADB="$fixture/adb" MOCK_RAW_CHMOD_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/raw-chmod.out" 2>&1; then
    echo 'FAIL: benchmark accepted insecure raw-report permissions' >&2; exit 1
fi
grep -Fxq 'ERROR: could not secure private raw benchmark directory' "$fixture/raw-chmod.out"
! grep -Eq 'private raw chmod failure|overte-phone-graphics-(raw|report)[.]' \
    "$fixture/raw-chmod.out"
if find /tmp -maxdepth 1 -type d \
        \( -name 'overte-phone-graphics-report.*' -o -name 'overte-phone-graphics-raw.*' \) \
        -newer "$fixture/raw-chmod-marker" | grep -q .; then
    echo 'FAIL: raw chmod failure retained a private directory' >&2; exit 1
fi
rejected_commands="$fixture/rejected-device-commands"
: >"$rejected_commands"
if PHONE_ADB="$fixture/adb" MOCK_QEMU=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES MOCK_ADB_COMMAND_LOG="$rejected_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/rejected-device.out" 2>&1; then
    echo 'FAIL: benchmark accepted an emulator target' >&2; exit 1
fi
grep -Fxq 'ERROR: ANDROID_SERIAL does not meet the physical Phone runtime contract' \
    "$fixture/rejected-device.out"
! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$rejected_commands"
pico_commands="$fixture/rejected-pico-commands"
: >"$pico_commands"
if PHONE_ADB="$fixture/adb" MOCK_PRODUCT_IDENTITY=Pico ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES MOCK_ADB_COMMAND_LOG="$pico_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/rejected-pico.out" 2>&1; then
    echo 'FAIL: benchmark accepted a Pico identity' >&2; exit 1
fi
grep -Fxq 'ERROR: refusing to benchmark a Pico/VR device' "$fixture/rejected-pico.out"
! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$pico_commands"
for contract_fixture in \
        'watch:MOCK_CHARACTERISTICS=watch' \
        'abi:MOCK_ABIS=x86_64' \
        'sdk:MOCK_SDK=25' \
        'gles:MOCK_GLES=196609' \
        'touch:MOCK_FEATURES='; do
    contract_name="${contract_fixture%%:*}"
    contract_override="${contract_fixture#*:}"
    contract_commands="$fixture/rejected-$contract_name-commands"
    : >"$contract_commands"
    if env "$contract_override" PHONE_ADB="$fixture/adb" ANDROID_SERIAL=phone-secret \
        PHONE_BENCHMARK_CONFIRM_NON_VR=YES MOCK_ADB_COMMAND_LOG="$contract_commands" \
        "$script_dir/phone-graphics-benchmark.sh" 1 \
        >"$fixture/rejected-$contract_name.out" 2>&1; then
        echo "FAIL: benchmark accepted invalid $contract_name device contract" >&2; exit 1
    fi
    grep -Fxq 'ERROR: ANDROID_SERIAL does not meet the physical Phone runtime contract' \
        "$fixture/rejected-$contract_name.out"
    ! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$contract_commands"
done
command_log="$fixture/commands"
: >"$command_log"

reset_failure_report="$fixture/reset-failure-report"
reset_failure_commands="$fixture/reset-failure-commands"
: >"$reset_failure_commands"
if PHONE_ADB="$fixture/adb" MOCK_GFX_RESET_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$reset_failure_report" \
    MOCK_ADB_COMMAND_LOG="$reset_failure_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/reset-failure.out" 2>&1; then
    echo 'FAIL: benchmark accepted a failed graphics reset' >&2; exit 1
fi
grep -Fxq 'ERROR: graphics counter reset failed' "$fixture/reset-failure.out"
! grep -Eq 'phone-secret|private reset failure' "$fixture/reset-failure.out"
! grep -Fq 'shell am start' "$reset_failure_commands"

start_failure_report="$fixture/start-failure-report"
start_failure_commands="$fixture/start-failure-commands"
: >"$start_failure_commands"
if PHONE_ADB="$fixture/adb" MOCK_START_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$start_failure_report" \
    MOCK_ADB_COMMAND_LOG="$start_failure_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/start-failure.out" 2>&1; then
    echo 'FAIL: benchmark accepted a failed Activity start' >&2; exit 1
fi
grep -Fxq 'ERROR: Phone Activity start failed' "$fixture/start-failure.out"
! grep -Eq 'phone-secret|private Activity failure' "$fixture/start-failure.out"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$start_failure_commands" || true)" -eq 0 ]]

touch "$fixture/automatic-failure-marker"
if PHONE_ADB="$fixture/adb" MOCK_START_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/automatic-failure.out" 2>&1; then
    echo 'FAIL: automatic-report benchmark accepted failed Activity start' >&2; exit 1
fi
if find /tmp -maxdepth 1 -type d -name 'overte-phone-graphics-report.*' \
        -newer "$fixture/automatic-failure-marker" | grep -q .; then
    echo 'FAIL: failed benchmark retained an automatic report directory' >&2; exit 1
fi

framestats_failure_report="$fixture/framestats-failure-report"
framestats_failure_commands="$fixture/framestats-failure-commands"
: >"$framestats_failure_commands"
if PHONE_ADB="$fixture/adb" MOCK_FRAMESTATS_ADB_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$framestats_failure_report" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$framestats_failure_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/framestats-failure.out" 2>&1; then
    echo 'FAIL: benchmark accepted unavailable frame statistics' >&2; exit 1
fi
grep -Fxq 'ERROR: graphics frame statistics failed' "$fixture/framestats-failure.out"
! grep -Eq 'phone-secret|private framestats failure' "$fixture/framestats-failure.out"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$framestats_failure_commands")" -eq 1 ]]
[[ ! -e "$framestats_failure_report/summary.txt" ]]

PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$report" PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$command_log" \
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
grep -q '^cleanup_force_stopped=1$' "$summary"
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

delayed_report="$fixture/delayed-start-report"
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/delayed-start-exits" \
    MOCK_PID_DELAY_FILE="$fixture/delayed-start-pid" ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$delayed_report" PHONE_BENCHMARK_INTERVAL=1 \
    "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null
grep -q '^stable_process=1$' "$delayed_report/summary.txt"
grep -q '^native_present_metrics_available=1$' "$summary"
grep -q '^native_present_fps=30.00$' "$summary"
grep -q '^native_present_window_seconds=10.02$' "$summary"
grep -q '^native_new_frame_fps=29.50$' "$summary"
grep -q '^native_inter_present_p95_ms=34.10$' "$summary"

private_stderr_report="$fixture/private-stderr-report"
if ! PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/private-stderr-exits" \
    MOCK_PRIVATE_ADB_STDERR=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$private_stderr_report" \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/private-stderr.out" 2>&1; then
    echo 'FAIL: private-stderr benchmark fixture failed' >&2; exit 1
fi
if grep -Eq 'phone-secret|private@example[.]test|private adb transport' \
        "$fixture/private-stderr.out"; then
    echo 'FAIL: raw ADB stderr escaped from benchmark' >&2; exit 1
fi
grep -Fxq 'Aggregate benchmark report written.' "$fixture/private-stderr.out"
! grep -Fq "$fixture" "$fixture/private-stderr.out"
grep -q '^stable_process=1$' "$private_stderr_report/summary.txt"

cleanup_failure_report="$fixture/cleanup-failure-report"
if ! PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/cleanup-failure-exits" \
    MOCK_RAW_RM_FAILURE=1 ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$cleanup_failure_report" PHONE_BENCHMARK_INTERVAL=1 \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/cleanup-failure.out" 2>&1; then
    echo 'FAIL: best-effort raw cleanup replaced successful benchmark status' >&2; exit 1
fi
grep -Fxq 'Aggregate benchmark report written.' "$fixture/cleanup-failure.out"
! grep -Eq 'private raw cleanup failure|overte-phone-graphics-raw[.]' \
    "$fixture/cleanup-failure.out"
grep -q '^schema=overte-phone-graphics-aggregate-v1$' \
    "$cleanup_failure_report/summary.txt"

final_cleanup_report="$fixture/final-cleanup-report"
final_cleanup_commands="$fixture/final-cleanup-commands"
: >"$final_cleanup_commands"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/final-cleanup-exits" \
    MOCK_FINAL_CLEANUP_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$final_cleanup_report" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$final_cleanup_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/final-cleanup.out" 2>&1; then
    echo 'FAIL: benchmark accepted failed final Phone cleanup' >&2; exit 1
fi
grep -Fxq 'ERROR: final Phone cleanup failed' "$fixture/final-cleanup.out"
! grep -Eq 'phone-secret|private cleanup failure' "$fixture/final-cleanup.out"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$final_cleanup_commands")" -eq 2 ]]
[[ ! -e "$final_cleanup_report/summary.txt" ]]

PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/temporary-report-exits" \
    ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_INTERVAL=1 "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/temporary-report.out"
temporary_summary="$(sed -n 's|^Aggregate benchmark report: \(.*[/]summary[.]txt\)$|\1|p' \
    "$fixture/temporary-report.out")"
[[ -n "$temporary_summary" && -f "$temporary_summary" ]]
grep -q '^schema=overte-phone-graphics-aggregate-v1$' "$temporary_summary"
temporary_report_dir="${temporary_summary%/summary.txt}"
[[ "$temporary_report_dir" == "$PHONE_BENCHMARK_TEST_TMPDIR"/overte-phone-graphics-report.* ]]
grep -Fxq '/tmp/overte-phone-graphics-report.XXXXXXXX' \
    "$PHONE_BENCHMARK_TEST_MKTEMP_LOG"
rm -rf -- "$temporary_report_dir"

summary_failure_report="$fixture/summary-failure-report"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/summary-failure-exits" \
    MOCK_SUMMARY_MKTEMP_FAILURE=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$summary_failure_report" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$fixture/summary-failure-commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 \
    >"$fixture/summary-failure.out" 2>&1; then
    echo 'FAIL: benchmark accepted aggregate-summary allocation failure' >&2; exit 1
fi
grep -Fxq 'ERROR: could not create aggregate benchmark summary' \
    "$fixture/summary-failure.out"
! grep -Fq 'private summary allocation failure' "$fixture/summary-failure.out"
! grep -Fq "$fixture" "$fixture/summary-failure.out"
[[ ! -e "$summary_failure_report/summary.txt" ]]
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$fixture/summary-failure-commands")" -eq 1 ]]
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
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$command_log")" -eq 1 ]]

signal_report="$fixture/signal-report"
signal_commands="$fixture/signal-commands"
: >"$signal_commands"
set +e
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/signal-exits" \
    MOCK_SLEEP_SIGNAL=TERM ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$signal_report" PHONE_BENCHMARK_INTERVAL=1 \
    MOCK_ADB_COMMAND_LOG="$signal_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 30 >"$fixture/signal.out" 2>&1
signal_status=$?
set -e
[[ "$signal_status" -eq 143 ]]
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$signal_commands")" -eq 1 ]]
[[ ! -e "$signal_report/summary.txt" ]]

interrupt_report="$fixture/interrupt-report"
interrupt_commands="$fixture/interrupt-commands"
: >"$interrupt_commands"
set +e
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/interrupt-exits" \
    MOCK_SLEEP_SIGNAL=INT ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$interrupt_report" PHONE_BENCHMARK_INTERVAL=1 \
    MOCK_ADB_COMMAND_LOG="$interrupt_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 30 >"$fixture/interrupt.out" 2>&1
interrupt_status=$?
set -e
[[ "$interrupt_status" -eq 130 ]]
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$interrupt_commands")" -eq 1 ]]
[[ ! -e "$interrupt_report/summary.txt" ]]

publish_signal_report="$fixture/publish-signal-report"
publish_signal_commands="$fixture/publish-signal-commands"
: >"$publish_signal_commands"
set +e
PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/publish-signal-exits" \
    MOCK_SUMMARY_CHMOD_SIGNAL_TERM=1 ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$publish_signal_report" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$publish_signal_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/publish-signal.out" 2>&1
publish_signal_status=$?
set -e
[[ "$publish_signal_status" -eq 143 ]]
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$publish_signal_commands")" -eq 1 ]]
[[ ! -e "$publish_signal_report/summary.txt" ]]
[[ -z "$(find "$publish_signal_report" -maxdepth 1 -name '.summary.txt.*' -print -quit)" ]]
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
private_report_file="$fixture/private-report-file"
printf 'not a directory\n' >"$private_report_file"
private_report_commands="$fixture/private-report-commands"
: >"$private_report_commands"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$private_report_file" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$private_report_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >"$fixture/private-report.out" 2>&1; then
    echo 'FAIL: benchmark accepted a file as report directory' >&2; exit 1
fi
grep -Fxq 'ERROR: could not create benchmark report directory' "$fixture/private-report.out"
! grep -Fq "$fixture" "$fixture/private-report.out"
! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$private_report_commands"
symlink_report="$fixture/symlink-report"
mkdir -p "$symlink_report"
protected="$fixture/protected"
printf 'do-not-overwrite\n' >"$protected"
ln -s "$protected" "$symlink_report/summary.txt"
symlink_commands="$fixture/symlink-commands"
: >"$symlink_commands"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT="$symlink_report" PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$symlink_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null 2>&1; then
    echo 'FAIL: benchmark overwrote a symlinked summary' >&2; exit 1
fi
grep -q '^do-not-overwrite$' "$protected"
! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$symlink_commands"

nonregular_report="$fixture/nonregular-report"
mkdir -p "$nonregular_report/summary.txt"
nonregular_commands="$fixture/nonregular-commands"
: >"$nonregular_commands"
if PHONE_ADB="$fixture/adb" MOCK_EXIT_COUNT_FILE="$fixture/exit-count" ANDROID_SERIAL=phone-secret \
    PHONE_BENCHMARK_CONFIRM_NON_VR=YES PHONE_BENCHMARK_REPORT="$nonregular_report" \
    PHONE_BENCHMARK_INTERVAL=1 MOCK_ADB_COMMAND_LOG="$nonregular_commands" \
    "$script_dir/phone-graphics-benchmark.sh" 1 >/dev/null 2>&1; then
    echo 'FAIL: benchmark accepted a non-regular summary target' >&2; exit 1
fi
! grep -Eq 'dumpsys gfxinfo|logcat -c|am start' "$nonregular_commands"

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
