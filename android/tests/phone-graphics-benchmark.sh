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
duration="${1:-30}"
interval="${PHONE_BENCHMARK_INTERVAL:-5}"
[[ "$duration" =~ ^[1-9][0-9]*$ ]] || die "duration must be a positive integer"
[[ "$interval" =~ ^[1-9][0-9]*$ ]] || die "PHONE_BENCHMARK_INTERVAL must be a positive integer"
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
adb_for() { "$ADB" -s "$ANDROID_SERIAL" "$@"; }

authorized=0
while read -r serial state _; do
    [[ "$serial" == "$ANDROID_SERIAL" && "$state" == device ]] && authorized=$((authorized + 1))
done < <("$ADB" devices -l)
(( authorized == 1 )) || die "ANDROID_SERIAL must identify exactly one authorized device"

property() { adb_for shell getprop "$1" 2>/dev/null | tr -d '\r'; }
identity="$(property ro.product.manufacturer) $(property ro.product.brand) $(property ro.product.model) $(property ro.product.device)"
characteristics="$(property ro.build.characteristics)"
[[ ! "${identity,,}" =~ pico|bytedance ]] || die "refusing to benchmark a Pico/VR device"
[[ ! "${characteristics,,}" =~ (^|,)vr(,|$) ]] || die "refusing to benchmark a VR-class device"

if [[ -n "${PHONE_BENCHMARK_REPORT:-}" ]]; then
    report_dir="$(realpath -m -- "$PHONE_BENCHMARK_REPORT")"
else
    report_dir="$(mktemp -d /tmp/overte-phone-graphics-report.XXXXXXXX)"
fi
case "$report_dir/" in "$worktree_root/"*) die "refusing to write benchmark output inside the worktree" ;; esac
mkdir -p -- "$report_dir"
chmod 700 "$report_dir"

# Deliberately ignore TMPDIR: raw device text must have a short-lived /tmp home.
raw_dir="$(mktemp -d /tmp/overte-phone-graphics-raw.XXXXXXXX)"
chmod 700 "$raw_dir"
cleanup() { rm -rf -- "$raw_dir"; }
trap cleanup EXIT INT TERM

adb_for shell dumpsys gfxinfo "$PACKAGE" reset >/dev/null
adb_for logcat -c >/dev/null 2>&1 || true
exit_info_before_valid=1
adb_for shell dumpsys activity exit-info "$PACKAGE" >"$raw_dir/exits-before.txt" || exit_info_before_valid=0
adb_for shell am start -W -n "$ACTIVITY" >"$raw_dir/start.txt"
expected_pid="$(adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r')"
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

adb_for shell dumpsys gfxinfo "$PACKAGE" framestats >"$raw_dir/framestats.txt"
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
present_line="$(grep 'OvertePhoneGraphics.*present_fps=' "$raw_dir/logcat.txt" | tail -n 1 || true)"
native_window_seconds="$(sed -nE 's/.*window_seconds=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_fps="$(sed -nE 's/.*[[:space:]]present_fps=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_new_frame_fps="$(sed -nE 's/.*new_frame_fps=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_p50_ms="$(sed -nE 's/.*inter_present_p50_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_p95_ms="$(sed -nE 's/.*inter_present_p95_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_max_ms="$(sed -nE 's/.*inter_present_max_ms=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
texture_resource_mib="$(sed -nE 's/.*texture_resource_mib=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
texture_populated_mib="$(sed -nE 's/.*texture_populated_mib=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
texture_pending_transfer_mib="$(sed -nE 's/.*texture_pending_transfer_mib=([0-9]+([.][0-9]+)?).*/\1/p' <<<"$present_line")"
native_present_metrics_available=0
[[ -n "$native_present_fps" && -n "$native_new_frame_fps" && -n "$native_present_p95_ms" ]] && \
    native_present_metrics_available=1

summary="$report_dir/summary.txt"
[[ ! -L "$summary" ]] || die "refusing to overwrite a symlinked benchmark summary"
summary_tmp="$(mktemp "$report_dir/.summary.txt.XXXXXXXX")"
chmod 600 "$summary_tmp"
{
    printf 'schema=overte-phone-graphics-aggregate-v1\n'
    cat "$raw_dir/graphics.aggregate"
    printf 'stable_process=%s\n' "$stable_process"
    printf 'thermal_samples=%s\nmax_thermal_status=%s\nexit_info_queries_valid=%s\n' \
        "$thermal_poll_count" "$thermal_status" "$exit_info_queries_valid"
    printf 'crash_records_before=%s\ncrash_records_after=%s\ncrash_record_count_increased=%s\ncrash_log_matches=%s\n' \
        "$crash_records_before" "$crash_records_after" "$crash_record_count_increased" "$log_crashes"
    printf 'profile_viewport_scale=%s\nprofile_target_fps=%s\nprofile_forward_msaa_samples=%s\n' \
        "${profile_scale:-unknown}" "${profile_fps:-unknown}" "${profile_msaa:-unknown}"
    printf 'native_present_metrics_available=%s\nnative_present_fps=%s\nnative_new_frame_fps=%s\n' \
        "$native_present_metrics_available" "${native_present_fps:-unknown}" "${native_new_frame_fps:-unknown}"
    printf 'native_present_window_seconds=%s\nnative_present_window_scope=latest_complete\n' \
        "${native_window_seconds:-unknown}"
    printf 'native_inter_present_p50_ms=%s\nnative_inter_present_p95_ms=%s\nnative_inter_present_max_ms=%s\n' \
        "${native_present_p50_ms:-unknown}" "${native_present_p95_ms:-unknown}" "${native_present_max_ms:-unknown}"
    printf 'texture_resource_mib=%s\ntexture_populated_mib=%s\ntexture_pending_transfer_mib=%s\n' \
        "${texture_resource_mib:-unknown}" "${texture_populated_mib:-unknown}" "${texture_pending_transfer_mib:-unknown}"
} >"$summary_tmp"
mv -T -- "$summary_tmp" "$summary"
printf 'Aggregate benchmark report: %s\n' "$summary"
