#!/usr/bin/env bash
set -Eeuo pipefail

readonly PACKAGE="org.overte.phone"
readonly ACTIVITY="org.overte.phone/.PermissionsActivity"
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly worktree_root="$(cd -- "$script_dir/../.." && pwd)"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: ANDROID_SERIAL=<serial> PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
       ./tests/phone-graphics-benchmark.sh [seconds]

Runs a graphics sampling pass on one explicitly named, authorized Android
phone. It never installs or builds software. Raw device output exists only in
a private /tmp directory and is deleted on exit. The persistent report contains
aggregate graphics, thermal, crash, and phone-profile values only.

Environment:
  PHONE_ADB                 ADB executable (otherwise resolved automatically)
  PHONE_BENCHMARK_REPORT    New or existing directory outside the worktree
  PHONE_BENCHMARK_INTERVAL  Thermal sampling interval in seconds (default: 5)
EOF
}

[[ "${1:-}" != --help && "${1:-}" != -h ]] || { usage; exit 0; }
if [[ "${PHONE_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$script_dir/../phone-device-lock.sh" run -- "$0" "$@"
fi
duration="${1:-30}"
interval="${PHONE_BENCHMARK_INTERVAL:-5}"
[[ "$duration" =~ ^[1-9][0-9]{0,3}$ ]] && ((10#$duration <= 3600)) || \
    die "duration must be an integer from 1 through 3600 seconds"
[[ "$interval" =~ ^[1-9][0-9]{0,2}$ ]] && ((10#$interval <= 300)) || \
    die "PHONE_BENCHMARK_INTERVAL must be an integer from 1 through 300 seconds"
[[ -n "${ANDROID_SERIAL:-}" ]] || die "ANDROID_SERIAL must explicitly name the test phone"
[[ "${PHONE_BENCHMARK_CONFIRM_NON_VR:-}" == YES ]] || \
    die "set PHONE_BENCHMARK_CONFIRM_NON_VR=YES after confirming the target is a non-VR phone"

find_adb() {
    local candidate
    for candidate in "${PHONE_ADB:-}" "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
        "${ANDROID_HOME:-}/platform-tools/adb" "${HOME}/Android/Sdk/platform-tools/adb"; do
        [[ -n "$candidate" && -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    command -v adb 2>/dev/null || die "ADB was not found"
}
ADB="$(find_adb)"
readonly ADB
adb_for() { "$ADB" -s "$ANDROID_SERIAL" "$@" 2>/dev/null; }
require_adb() {
    local phase="$1"
    shift
    adb_for "$@" || die "$phase failed"
}

authorized=0
while read -r serial state _; do
    [[ "$serial" == "$ANDROID_SERIAL" && "$state" == device ]] && authorized=$((authorized + 1))
done < <("$ADB" devices -l 2>/dev/null)
(( authorized == 1 )) || die "ANDROID_SERIAL must identify exactly one authorized device"

property() { adb_for shell getprop "$1" 2>/dev/null | tr -d '\r'; }
identity="$(property ro.product.manufacturer) $(property ro.product.brand) $(property ro.product.model) $(property ro.product.device)"
characteristics="$(property ro.build.characteristics)"
[[ ! "${identity,,}" =~ pico|bytedance ]] || die "refusing to benchmark a Pico/VR device"
qemu="$(property ro.kernel.qemu)"
abis="$(property ro.product.cpu.abilist)"
sdk="$(property ro.build.version.sdk)"
gles="$(property ro.opengles.version)"
features="$(adb_for shell pm list features | tr -d '\r')"
[[ "$qemu" != 1 ]] &&
    [[ ! "${characteristics,,}" =~ (^|,)(watch|tv|automotive|vr)(,|$) ]] &&
    [[ ",$abis," == *,arm64-v8a,* ]] &&
    [[ "$sdk" =~ ^[0-9]+$ ]] && ((10#$sdk >= 26)) &&
    [[ "$gles" =~ ^[0-9]+$ ]] && ((10#$gles >= 196610)) &&
    grep -Fxq 'feature:android.hardware.touchscreen' <<<"$features" ||
    die "ANDROID_SERIAL does not meet the physical Phone runtime contract"

if [[ -n "${PHONE_BENCHMARK_REPORT:-}" ]]; then
    report_is_temporary=0
    report_dir="$(realpath -m -- "$PHONE_BENCHMARK_REPORT" 2>/dev/null)" || \
        die "could not resolve benchmark report directory"
else
    report_is_temporary=1
    report_dir="$(mktemp -d /tmp/overte-phone-graphics-report.XXXXXXXX 2>/dev/null)" || \
        die "could not create temporary benchmark report directory"
fi
case "$report_dir/" in "$worktree_root/"*) die "refusing to write benchmark output inside the worktree" ;; esac
raw_dir=''
summary_tmp=''
package_started=0
report_published=0
cleanup() {
    local status=$?
    trap - EXIT
    if ((package_started == 1)); then
        adb_for shell am force-stop "$PACKAGE" >/dev/null || true
    fi
    [[ -z "$summary_tmp" ]] || rm -f -- "$summary_tmp" 2>/dev/null || true
    [[ -z "$raw_dir" ]] || rm -rf -- "$raw_dir" 2>/dev/null || true
    if ((report_is_temporary == 1 && report_published == 0)); then
        rm -rf -- "$report_dir" 2>/dev/null || true
    fi
    return "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p -- "$report_dir" 2>/dev/null || die "could not create benchmark report directory"
chmod 700 "$report_dir" 2>/dev/null || die "could not secure benchmark report directory"
summary="$report_dir/summary.txt"
[[ ! -L "$summary" ]] || die "refusing to overwrite a symlinked benchmark summary"
[[ ! -e "$summary" || -f "$summary" ]] || \
    die "refusing to overwrite a non-regular benchmark summary"

# Deliberately ignore TMPDIR: raw device text must have a short-lived /tmp home.
raw_dir="$(mktemp -d /tmp/overte-phone-graphics-raw.XXXXXXXX 2>/dev/null)" || \
    die "could not create private raw benchmark directory"
chmod 700 "$raw_dir" 2>/dev/null || die "could not secure private raw benchmark directory"

require_adb "graphics counter reset" shell dumpsys gfxinfo "$PACKAGE" reset >/dev/null
adb_for logcat -c >/dev/null 2>&1 || true
exit_info_before_valid=1
adb_for shell dumpsys activity exit-info "$PACKAGE" >"$raw_dir/exits-before.txt" || exit_info_before_valid=0
require_adb "Phone Activity start" shell am start -W -n "$ACTIVITY" >"$raw_dir/start.txt"
package_started=1
expected_pid=''
for _ in {1..10}; do
    expected_pid="$(adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
    [[ "$expected_pid" =~ ^[0-9]+$ ]] && break
    sleep 1
done
[[ "$expected_pid" =~ ^[0-9]+$ ]] || die "phone process did not start"

elapsed=0
stable_process=1
thermal_poll_count=0
: >"$raw_dir/thermal.txt"
while (( elapsed < duration )); do
    sample_for=$interval
    (( elapsed + sample_for <= duration )) || sample_for=$((duration - elapsed))
    sleep "$sample_for"
    elapsed=$((elapsed + sample_for))
    current_pid="$(adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
    if [[ "$current_pid" != "$expected_pid" ]]; then
        stable_process=0
        break
    fi
    { adb_for shell dumpsys thermalservice || true; } >>"$raw_dir/thermal.txt"
    thermal_poll_count=$((thermal_poll_count + 1))
done

require_adb "graphics frame statistics" shell dumpsys gfxinfo "$PACKAGE" framestats \
    >"$raw_dir/framestats.txt"
final_pid="$(adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
[[ "$final_pid" == "$expected_pid" ]] || stable_process=0
exit_info_after_valid=1
adb_for shell dumpsys activity exit-info "$PACKAGE" >"$raw_dir/exits.txt" || exit_info_after_valid=0
{ adb_for logcat -d --pid="$expected_pid" -v brief || true; } >"$raw_dir/logcat.txt"

awk -v duration="$elapsed" '
    BEGIN { frames=0; jank=0; total_ms=0; max_ms=0 }
    /^Flags,IntendedVsync,/ { header=1; next }
    /^---PROFILEDATA---/ { data=!data; next }
    data && /^[0-9]+,/ {
        n=split($0, f, ","); start=f[2]+0; finish=f[14]+0
        if (header && n >= 14 && f[1]+0 == 0 && finish > start) {
            ms=(finish-start)/1000000; frames++; total_ms+=ms
            values[frames]=ms; if (ms > 16.6667) jank++; if (ms > max_ms) max_ms=ms
        }
    }
    END {
        for (i=1;i<=frames;i++) for (k=i+1;k<=frames;k++) if (values[i]>values[k]) { t=values[i]; values[i]=values[k]; values[k]=t }
        p50=frames ? values[int((frames-1)*0.50)+1] : 0
        p90=frames ? values[int((frames-1)*0.90)+1] : 0
        p95=frames ? values[int((frames-1)*0.95)+1] : 0
        avg=frames ? total_ms/frames : 0; observed_fps=duration>0 ? frames/duration : 0
        printf "duration_seconds=%d\nframestats_valid=%d\nframes=%d\nobserved_frames_per_second=%.2f\naverage_frame_ms=%.2f\np50_frame_ms=%.2f\np90_frame_ms=%.2f\np95_frame_ms=%.2f\nmax_frame_ms=%.2f\njanky_frames=%d\njanky_percent=%.2f\n", duration,header?1:0,frames,observed_fps,avg,p50,p90,p95,max_ms,jank,frames?100*jank/frames:0
    }
' "$raw_dir/framestats.txt" >"$raw_dir/graphics.aggregate"

thermal_status="$(awk 'BEGIN{m=0} { l=tolower($0); if (match(l,/status[^0-9]*[0-9]+/)) {v=substr(l,RSTART,RLENGTH); sub(/.*[^0-9]/,"",v); if(v>m)m=v} } END{print m}' "$raw_dir/thermal.txt")"
crash_records_after="$(awk '{l=tolower($0); if(l ~ /reason=[[:space:]]*(4|5)[[:space:]]*\(/ || l ~ /reason=[[:space:]]*(crash|native_crash)/ || l ~ /reason_(crash|crash_native)/) n++} END{print n+0}' "$raw_dir/exits.txt")"
crash_records_before="$(awk '{l=tolower($0); if(l ~ /reason=[[:space:]]*(4|5)[[:space:]]*\(/ || l ~ /reason=[[:space:]]*(crash|native_crash)/ || l ~ /reason_(crash|crash_native)/) n++} END{print n+0}' "$raw_dir/exits-before.txt")"
exit_info_queries_valid=$((exit_info_before_valid && exit_info_after_valid))
crash_record_count_increased=0
if (( exit_info_queries_valid && crash_records_after > crash_records_before )); then
    crash_record_count_increased=1
fi
log_crashes="$(grep -Eic 'fatal exception|fatal signal|am_crash|crash_dump' "$raw_dir/logcat.txt" || true)"

# Profile values are a fixed allowlist; arbitrary log text can never reach the report.
profile_line="$(grep -E 'PHONE_GRAPHICS_PROFILE|OvertePhoneGraphics.*profile_render_scale=' "$raw_dir/logcat.txt" | tail -n 1 || true)"
profile_scale="$(sed -nE 's/.*(renderScale|profile_render_scale)[^0-9]*([0-9]+([.][0-9]+)?).*/\2/p' <<<"$profile_line")"
profile_fps="$(sed -nE 's/.*(targetFps|profile_target_fps)[^0-9]*([0-9]+).*/\2/p' <<<"$profile_line")"
profile_msaa="$(sed -nE 's/.*(forwardMsaaSamples|profile_forward_msaa_samples)[^0-9]*([0-9]+).*/\2/p' <<<"$profile_line")"
overlay_cache_line="$(grep 'OvertePhoneGraphics.*overlay_cache_enabled=' "$raw_dir/logcat.txt" | tail -n 1 || true)"
render_timing_line="$(grep 'OvertePhoneGraphics.*render_gpu_ms=' "$raw_dir/logcat.txt" | tail -n 1 || true)"
present_line="$(grep 'OvertePhoneGraphics.*present_fps=' "$raw_dir/logcat.txt" | tail -n 1 || true)"
present_window_id="$(grep -oE '(^|[[:space:]])window_id=(0|[1-9][0-9]*)' <<<"$present_line" | tail -n 1 | cut -d= -f2- || true)"
if [[ "$present_window_id" =~ ^(0|[1-9][0-9]*)$ ]]; then
    trash_line="$(grep -E "OvertePhoneGraphics.*record=trash.*window_id=${present_window_id}([[:space:]]|$)" "$raw_dir/logcat.txt" | tail -n 1 || true)"
    state_line="$(grep -E "OvertePhoneGraphics.*record=state.*window_id=${present_window_id}([[:space:]]|$)" "$raw_dir/logcat.txt" | tail -n 1 || true)"
else
    trash_line=''
    state_line=''
fi
extract_native_field() {
    local field="$1"
    local source_line="${2:-$present_line}"
    grep -oE "(^|[[:space:]])${field}=[^[:space:]]+" <<<"$source_line" | tail -n 1 | cut -d= -f2-
}
valid_nonnegative_int64() {
    local value="$1"
    [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]] || return 1
    (( ${#value} < 19 )) || {
        (( ${#value} == 19 )) && [[ "$value" < 9223372036854775807 || "$value" == 9223372036854775807 ]]
    }
}
valid_u64() {
    local value="$1"
    [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]] || return 1
    (( ${#value} < 20 )) || {
        (( ${#value} == 20 )) && [[ "$value" < 18446744073709551615 || "$value" == 18446744073709551615 ]]
    }
}
valid_u32() {
    local value="$1"
    [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]] || return 1
    (( ${#value} < 10 )) || {
        (( ${#value} == 10 )) && [[ "$value" < 4294967295 || "$value" == 4294967295 ]]
    }
}
u64_lte() {
    local left="$1" right="$2"
    (( ${#left} < ${#right} )) || { (( ${#left} == ${#right} )) && [[ "$left" < "$right" || "$left" == "$right" ]]; }
}
valid_bounded_uint() {
    local value="$1" maximum="$2"
    [[ "$value" =~ ^[1-9][0-9]*$ ]] && (( 10#$value <= maximum ))
}
valid_finite_decimal() {
    local value="$1"
    [[ "$value" =~ ^(0|[1-9][0-9]*)([.][0-9]+)?$ ]] &&
        awk -v value="$value" 'BEGIN { exit !(value + 0 <= 1048576) }'
}
native_window_seconds="$(sed -nE 's/.*window_seconds=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_fps="$(sed -nE 's/.*[[:space:]]present_fps=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_new_frame_fps="$(sed -nE 's/.*new_frame_fps=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_p50_ms="$(sed -nE 's/.*inter_present_p50_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_p95_ms="$(sed -nE 's/.*inter_present_p95_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_max_ms="$(sed -nE 's/.*inter_present_max_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
texture_resource_mib="$(extract_native_field texture_resource_mib || true)"
texture_populated_mib="$(extract_native_field texture_populated_mib || true)"
texture_pending_transfer_mib="$(extract_native_field texture_pending_transfer_mib || true)"
gpu_buffer_count="$(extract_native_field gpu_buffer_count || true)"
gpu_buffer_mib="$(extract_native_field gpu_buffer_mib || true)"
gpu_texture_resident_count="$(extract_native_field gpu_texture_resident_count || true)"
gpu_texture_resident_mib="$(extract_native_field gpu_texture_resident_mib || true)"
gpu_texture_framebuffer_count="$(extract_native_field gpu_texture_framebuffer_count || true)"
gpu_texture_framebuffer_mib="$(extract_native_field gpu_texture_framebuffer_mib || true)"
gpu_texture_resource_count="$(extract_native_field gpu_texture_resource_count || true)"
gpu_texture_external_count="$(extract_native_field gpu_texture_external_count || true)"
gpu_texture_external_mib="$(extract_native_field gpu_texture_external_mib || true)"
gpu_texture_pending_transfer_count="$(extract_native_field gpu_texture_pending_transfer_count || true)"
gl_trash_buffer_enqueued_delta="$(extract_native_field gl_trash_buffer_enqueued_delta "$trash_line" || true)"
gl_trash_buffer_cleaned_delta="$(extract_native_field gl_trash_buffer_cleaned_delta "$trash_line" || true)"
gl_trash_buffer_backlog="$(extract_native_field gl_trash_buffer_backlog "$trash_line" || true)"
gl_trash_texture_enqueued_delta="$(extract_native_field gl_trash_texture_enqueued_delta "$trash_line" || true)"
gl_trash_texture_cleaned_delta="$(extract_native_field gl_trash_texture_cleaned_delta "$trash_line" || true)"
gl_trash_texture_backlog="$(extract_native_field gl_trash_texture_backlog "$trash_line" || true)"
gl_trash_external_texture_enqueued_delta="$(extract_native_field gl_trash_external_texture_enqueued_delta "$trash_line" || true)"
gl_trash_external_texture_cleaned_delta="$(extract_native_field gl_trash_external_texture_cleaned_delta "$trash_line" || true)"
gl_trash_external_texture_backlog="$(extract_native_field gl_trash_external_texture_backlog "$trash_line" || true)"
gl_trash_framebuffer_enqueued_delta="$(extract_native_field gl_trash_framebuffer_enqueued_delta "$trash_line" || true)"
gl_trash_framebuffer_cleaned_delta="$(extract_native_field gl_trash_framebuffer_cleaned_delta "$trash_line" || true)"
gl_trash_framebuffer_backlog="$(extract_native_field gl_trash_framebuffer_backlog "$trash_line" || true)"
gl_trash_buffer_bytes_enqueued_delta="$(extract_native_field gl_trash_buffer_bytes_enqueued_delta "$trash_line" || true)"
gl_trash_buffer_bytes_cleaned_delta="$(extract_native_field gl_trash_buffer_bytes_cleaned_delta "$trash_line" || true)"
gl_trash_buffer_pending_mib="$(extract_native_field gl_trash_buffer_pending_mib "$trash_line" || true)"
memory_proc_flag="$(extract_native_field memory_proc_valid "$state_line" || true)"
memory_rss_kib="$(extract_native_field memory_rss_kib "$state_line" || true)"
memory_data_kib="$(extract_native_field memory_data_kib "$state_line" || true)"
memory_swap_kib="$(extract_native_field memory_swap_kib "$state_line" || true)"
memory_allocator_flag="$(extract_native_field memory_allocator_valid "$state_line" || true)"
memory_allocator_used_kib="$(extract_native_field memory_allocator_used_kib "$state_line" || true)"
memory_allocator_free_kib="$(extract_native_field memory_allocator_free_kib "$state_line" || true)"
framebuffer_primary_recreate_delta="$(extract_native_field framebuffer_primary_recreate_delta "$state_line" || true)"
framebuffer_primary_recreate_total="$(extract_native_field framebuffer_primary_recreate_total "$state_line" || true)"
framebuffer_resolve_recreate_delta="$(extract_native_field framebuffer_resolve_recreate_delta "$state_line" || true)"
framebuffer_resolve_recreate_total="$(extract_native_field framebuffer_resolve_recreate_total "$state_line" || true)"
framebuffer_primary_width="$(extract_native_field framebuffer_primary_width "$state_line" || true)"
framebuffer_primary_height="$(extract_native_field framebuffer_primary_height "$state_line" || true)"
framebuffer_primary_samples="$(extract_native_field framebuffer_primary_samples "$state_line" || true)"
framebuffer_resolve_width="$(extract_native_field framebuffer_resolve_width "$state_line" || true)"
framebuffer_resolve_height="$(extract_native_field framebuffer_resolve_height "$state_line" || true)"
framebuffer_resolve_samples="$(extract_native_field framebuffer_resolve_samples "$state_line" || true)"
framebuffer_estimated_mib="$(extract_native_field framebuffer_estimated_mib "$state_line" || true)"
overlay_cache_enabled="$(extract_native_field overlay_cache_enabled "$overlay_cache_line" || true)"
overlay_cache_samples="$(extract_native_field overlay_cache_samples "$overlay_cache_line" || true)"
overlay_cache_hits="$(extract_native_field overlay_cache_hits "$overlay_cache_line" || true)"
overlay_cache_misses="$(extract_native_field overlay_cache_misses "$overlay_cache_line" || true)"
overlay_cache_new_textures="$(extract_native_field overlay_cache_new_textures "$overlay_cache_line" || true)"
overlay_cache_resizes="$(extract_native_field overlay_cache_resizes "$overlay_cache_line" || true)"
render_gpu_ms="$(extract_native_field render_gpu_ms "$render_timing_line" || true)"
render_batch_ms="$(extract_native_field render_batch_ms "$render_timing_line" || true)"
render_timing_metrics_valid=0
if valid_finite_decimal "$render_gpu_ms" && valid_finite_decimal "$render_batch_ms"; then
    render_timing_metrics_valid=1
else
    render_gpu_ms=unknown; render_batch_ms=unknown
fi
overlay_cache_metrics_valid=0
overlay_cache_hit_percent=unknown
if [[ "$overlay_cache_enabled" =~ ^[01]$ ]] && valid_u32 "$overlay_cache_samples" &&
        valid_u32 "$overlay_cache_hits" && valid_u32 "$overlay_cache_misses" &&
        valid_u32 "$overlay_cache_new_textures" && valid_u32 "$overlay_cache_resizes" &&
        (( 10#$overlay_cache_hits + 10#$overlay_cache_misses == 10#$overlay_cache_samples )) &&
        (( 10#$overlay_cache_new_textures <= 10#$overlay_cache_misses )) &&
        (( 10#$overlay_cache_resizes <= 10#$overlay_cache_misses )); then
    overlay_cache_metrics_valid=1
    overlay_cache_hit_percent="$(awk -v hits="$overlay_cache_hits" -v samples="$overlay_cache_samples" \
        'BEGIN { printf "%.2f", samples ? 100 * hits / samples : 0 }')"
else
    overlay_cache_enabled=unknown; overlay_cache_samples=unknown; overlay_cache_hits=unknown
    overlay_cache_misses=unknown; overlay_cache_new_textures=unknown; overlay_cache_resizes=unknown
fi
memory_proc_valid=0
if [[ "$memory_proc_flag" == 1 ]] && valid_nonnegative_int64 "$memory_rss_kib" && \
        valid_nonnegative_int64 "$memory_data_kib" && valid_nonnegative_int64 "$memory_swap_kib"; then
    memory_proc_valid=1
else
    memory_rss_kib=unknown; memory_data_kib=unknown; memory_swap_kib=unknown
fi
memory_allocator_valid=0
if [[ "$memory_allocator_flag" == 1 ]] && valid_nonnegative_int64 "$memory_allocator_used_kib" && \
        valid_nonnegative_int64 "$memory_allocator_free_kib"; then
    memory_allocator_valid=1
else
    memory_allocator_used_kib=unknown; memory_allocator_free_kib=unknown
fi
framebuffer_metrics_valid=0
if valid_u64 "$framebuffer_primary_recreate_delta" && valid_u64 "$framebuffer_primary_recreate_total" &&
        valid_u64 "$framebuffer_resolve_recreate_delta" && valid_u64 "$framebuffer_resolve_recreate_total" &&
        u64_lte "$framebuffer_primary_recreate_delta" "$framebuffer_primary_recreate_total" &&
        u64_lte "$framebuffer_resolve_recreate_delta" "$framebuffer_resolve_recreate_total" &&
        valid_bounded_uint "$framebuffer_primary_width" 32768 &&
        valid_bounded_uint "$framebuffer_primary_height" 32768 &&
        valid_bounded_uint "$framebuffer_primary_samples" 64 &&
        valid_bounded_uint "$framebuffer_resolve_width" 32768 &&
        valid_bounded_uint "$framebuffer_resolve_height" 32768 &&
        valid_bounded_uint "$framebuffer_resolve_samples" 64 &&
        valid_finite_decimal "$framebuffer_estimated_mib"; then
    framebuffer_metrics_valid=1
else
    framebuffer_primary_recreate_delta=unknown; framebuffer_primary_recreate_total=unknown
    framebuffer_resolve_recreate_delta=unknown; framebuffer_resolve_recreate_total=unknown
    framebuffer_primary_width=unknown; framebuffer_primary_height=unknown; framebuffer_primary_samples=unknown
    framebuffer_resolve_width=unknown; framebuffer_resolve_height=unknown; framebuffer_resolve_samples=unknown
    framebuffer_estimated_mib=unknown
fi
gpu_live_metrics_valid=0
if valid_u32 "$gpu_buffer_count" && valid_finite_decimal "$gpu_buffer_mib" &&
        valid_u32 "$gpu_texture_resident_count" && valid_finite_decimal "$gpu_texture_resident_mib" &&
        valid_u32 "$gpu_texture_framebuffer_count" && valid_finite_decimal "$gpu_texture_framebuffer_mib" &&
        valid_u32 "$gpu_texture_resource_count" && valid_finite_decimal "$texture_resource_mib" &&
        valid_u32 "$gpu_texture_external_count" && valid_finite_decimal "$gpu_texture_external_mib" &&
        valid_finite_decimal "$texture_populated_mib" &&
        valid_u32 "$gpu_texture_pending_transfer_count" && valid_finite_decimal "$texture_pending_transfer_mib"; then
    gpu_live_metrics_valid=1
else
    gpu_buffer_count=unknown; gpu_buffer_mib=unknown
    gpu_texture_resident_count=unknown; gpu_texture_resident_mib=unknown
    gpu_texture_framebuffer_count=unknown; gpu_texture_framebuffer_mib=unknown
    gpu_texture_resource_count=unknown; texture_resource_mib=unknown
    gpu_texture_external_count=unknown; gpu_texture_external_mib=unknown
    texture_populated_mib=unknown
    gpu_texture_pending_transfer_count=unknown; texture_pending_transfer_mib=unknown
fi
gl_trash_metrics_valid=0
if valid_u64 "$gl_trash_buffer_enqueued_delta" && valid_u64 "$gl_trash_buffer_cleaned_delta" &&
        valid_u64 "$gl_trash_buffer_backlog" && valid_u64 "$gl_trash_texture_enqueued_delta" &&
        valid_u64 "$gl_trash_texture_cleaned_delta" && valid_u64 "$gl_trash_texture_backlog" &&
        valid_u64 "$gl_trash_external_texture_enqueued_delta" &&
        valid_u64 "$gl_trash_external_texture_cleaned_delta" && valid_u64 "$gl_trash_external_texture_backlog" &&
        valid_u64 "$gl_trash_framebuffer_enqueued_delta" && valid_u64 "$gl_trash_framebuffer_cleaned_delta" &&
        valid_u64 "$gl_trash_framebuffer_backlog" && valid_u64 "$gl_trash_buffer_bytes_enqueued_delta" &&
        valid_u64 "$gl_trash_buffer_bytes_cleaned_delta" && valid_finite_decimal "$gl_trash_buffer_pending_mib"; then
    gl_trash_metrics_valid=1
else
    gl_trash_buffer_enqueued_delta=unknown; gl_trash_buffer_cleaned_delta=unknown; gl_trash_buffer_backlog=unknown
    gl_trash_texture_enqueued_delta=unknown; gl_trash_texture_cleaned_delta=unknown; gl_trash_texture_backlog=unknown
    gl_trash_external_texture_enqueued_delta=unknown; gl_trash_external_texture_cleaned_delta=unknown
    gl_trash_external_texture_backlog=unknown
    gl_trash_framebuffer_enqueued_delta=unknown; gl_trash_framebuffer_cleaned_delta=unknown
    gl_trash_framebuffer_backlog=unknown; gl_trash_buffer_bytes_enqueued_delta=unknown
    gl_trash_buffer_bytes_cleaned_delta=unknown; gl_trash_buffer_pending_mib=unknown
fi
native_present_metrics_available=0
[[ -n "$native_present_fps" && -n "$native_new_frame_fps" && -n "$native_present_p95_ms" ]] && \
    native_present_metrics_available=1

require_adb "final Phone cleanup" shell am force-stop "$PACKAGE" >/dev/null
package_started=0
summary_tmp="$(mktemp "$report_dir/.summary.txt.XXXXXXXX" 2>/dev/null)" || \
    die "could not create aggregate benchmark summary"
if ! chmod 600 "$summary_tmp" 2>/dev/null; then
    rm -f -- "$summary_tmp" 2>/dev/null || true
    die "could not secure aggregate benchmark summary"
fi
{
    printf 'schema=overte-phone-graphics-aggregate-v1\n'
    printf 'cleanup_force_stopped=1\n'
    cat "$raw_dir/graphics.aggregate"
    printf 'stable_process=%s\n' "$stable_process"
    printf 'thermal_samples=%s\nmax_thermal_status=%s\nexit_info_queries_valid=%s\n' \
        "$thermal_poll_count" "$thermal_status" "$exit_info_queries_valid"
    printf 'crash_records_before=%s\ncrash_records_after=%s\ncrash_record_count_increased=%s\ncrash_log_matches=%s\n' \
        "$crash_records_before" "$crash_records_after" "$crash_record_count_increased" "$log_crashes"
    printf 'profile_viewport_scale=%s\nprofile_target_fps=%s\nprofile_forward_msaa_samples=%s\n' \
        "${profile_scale:-unknown}" "${profile_fps:-unknown}" "${profile_msaa:-unknown}"
    printf 'overlay_cache_metrics_valid=%s\noverlay_cache_enabled=%s\noverlay_cache_samples=%s\n' \
        "$overlay_cache_metrics_valid" "$overlay_cache_enabled" "$overlay_cache_samples"
    printf 'overlay_cache_hits=%s\noverlay_cache_misses=%s\noverlay_cache_hit_percent=%s\n' \
        "$overlay_cache_hits" "$overlay_cache_misses" "$overlay_cache_hit_percent"
    printf 'overlay_cache_new_textures=%s\noverlay_cache_resizes=%s\n' \
        "$overlay_cache_new_textures" "$overlay_cache_resizes"
    printf 'render_timing_metrics_valid=%s\nrender_gpu_ms=%s\nrender_batch_ms=%s\n' \
        "$render_timing_metrics_valid" "$render_gpu_ms" "$render_batch_ms"
    printf 'native_present_metrics_available=%s\nnative_present_fps=%s\nnative_new_frame_fps=%s\n' \
        "$native_present_metrics_available" "${native_present_fps:-unknown}" "${native_new_frame_fps:-unknown}"
    printf 'native_present_window_seconds=%s\nnative_present_window_scope=latest_complete\n' \
        "${native_window_seconds:-unknown}"
    printf 'native_inter_present_p50_ms=%s\nnative_inter_present_p95_ms=%s\nnative_inter_present_max_ms=%s\n' \
        "${native_present_p50_ms:-unknown}" "${native_present_p95_ms:-unknown}" "${native_present_max_ms:-unknown}"
    printf 'gpu_live_metrics_valid=%s\n' "$gpu_live_metrics_valid"
    printf 'gpu_buffer_count=%s\ngpu_buffer_mib=%s\n' "$gpu_buffer_count" "$gpu_buffer_mib"
    printf 'gpu_texture_resident_count=%s\ngpu_texture_resident_mib=%s\n' \
        "$gpu_texture_resident_count" "$gpu_texture_resident_mib"
    printf 'gpu_texture_framebuffer_count=%s\ngpu_texture_framebuffer_mib=%s\n' \
        "$gpu_texture_framebuffer_count" "$gpu_texture_framebuffer_mib"
    printf 'gpu_texture_resource_count=%s\ntexture_resource_mib=%s\n' \
        "$gpu_texture_resource_count" "$texture_resource_mib"
    printf 'gpu_texture_external_count=%s\ngpu_texture_external_mib=%s\n' \
        "$gpu_texture_external_count" "$gpu_texture_external_mib"
    printf 'texture_populated_mib=%s\ngpu_texture_pending_transfer_count=%s\ntexture_pending_transfer_mib=%s\n' \
        "$texture_populated_mib" "$gpu_texture_pending_transfer_count" "$texture_pending_transfer_mib"
    printf 'gl_trash_metrics_valid=%s\n' "$gl_trash_metrics_valid"
    printf 'gl_trash_buffer_enqueued_delta=%s\ngl_trash_buffer_cleaned_delta=%s\ngl_trash_buffer_backlog=%s\n' \
        "$gl_trash_buffer_enqueued_delta" "$gl_trash_buffer_cleaned_delta" "$gl_trash_buffer_backlog"
    printf 'gl_trash_texture_enqueued_delta=%s\ngl_trash_texture_cleaned_delta=%s\ngl_trash_texture_backlog=%s\n' \
        "$gl_trash_texture_enqueued_delta" "$gl_trash_texture_cleaned_delta" "$gl_trash_texture_backlog"
    printf 'gl_trash_external_texture_enqueued_delta=%s\ngl_trash_external_texture_cleaned_delta=%s\ngl_trash_external_texture_backlog=%s\n' \
        "$gl_trash_external_texture_enqueued_delta" "$gl_trash_external_texture_cleaned_delta" "$gl_trash_external_texture_backlog"
    printf 'gl_trash_framebuffer_enqueued_delta=%s\ngl_trash_framebuffer_cleaned_delta=%s\ngl_trash_framebuffer_backlog=%s\n' \
        "$gl_trash_framebuffer_enqueued_delta" "$gl_trash_framebuffer_cleaned_delta" "$gl_trash_framebuffer_backlog"
    printf 'gl_trash_buffer_bytes_enqueued_delta=%s\ngl_trash_buffer_bytes_cleaned_delta=%s\ngl_trash_buffer_pending_mib=%s\n' \
        "$gl_trash_buffer_bytes_enqueued_delta" "$gl_trash_buffer_bytes_cleaned_delta" "$gl_trash_buffer_pending_mib"
    printf 'memory_proc_valid=%s\nmemory_rss_kib=%s\nmemory_data_kib=%s\nmemory_swap_kib=%s\n' \
        "$memory_proc_valid" "$memory_rss_kib" "$memory_data_kib" "$memory_swap_kib"
    printf 'memory_allocator_valid=%s\nmemory_allocator_used_kib=%s\nmemory_allocator_free_kib=%s\n' \
        "$memory_allocator_valid" "$memory_allocator_used_kib" "$memory_allocator_free_kib"
    printf 'framebuffer_metrics_valid=%s\n' "$framebuffer_metrics_valid"
    printf 'framebuffer_primary_recreate_delta=%s\nframebuffer_primary_recreate_total=%s\n' \
        "$framebuffer_primary_recreate_delta" "$framebuffer_primary_recreate_total"
    printf 'framebuffer_resolve_recreate_delta=%s\nframebuffer_resolve_recreate_total=%s\n' \
        "$framebuffer_resolve_recreate_delta" "$framebuffer_resolve_recreate_total"
    printf 'framebuffer_primary_width=%s\nframebuffer_primary_height=%s\nframebuffer_primary_samples=%s\n' \
        "$framebuffer_primary_width" "$framebuffer_primary_height" "$framebuffer_primary_samples"
    printf 'framebuffer_resolve_width=%s\nframebuffer_resolve_height=%s\nframebuffer_resolve_samples=%s\n' \
        "$framebuffer_resolve_width" "$framebuffer_resolve_height" "$framebuffer_resolve_samples"
    printf 'framebuffer_estimated_mib=%s\n' "$framebuffer_estimated_mib"
} >"$summary_tmp" 2>/dev/null || {
    rm -f -- "$summary_tmp" 2>/dev/null || true
    die "could not write aggregate benchmark summary"
}
if ! mv -T -- "$summary_tmp" "$summary" 2>/dev/null; then
    rm -f -- "$summary_tmp" 2>/dev/null || true
    die "could not publish aggregate benchmark summary"
fi
summary_tmp=''
report_published=1
if ((report_is_temporary == 1)); then
    printf 'Aggregate benchmark report: %s\n' "$summary"
else
    printf 'Aggregate benchmark report written.\n'
fi
