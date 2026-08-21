#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

# Preserve the caller's stdout for live progress even when an individual
# command's stdout is redirected or captured by command substitution.
exec 3>&1

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
readonly simulator_selector="$script_dir/../tools/select-simulator.py"
readonly screenshot_validator="$script_dir/../tools/validate-world-screenshot.py"
readonly world_validator="$script_dir/../tools/validate-world-runtime.py"
readonly entity_gate_validator="$script_dir/../tools/validate-entity-gate-log.py"
readonly first_person_script="$script_dir/ios-camera-first-person.js"
readonly timeout_grace_seconds=300
readonly live_update_interval_seconds=5

app_path="${1:-}"
bundle_id="${2:-}"
family="${3:-}"
scenario="${4:-}"
expected_domain="${5:-}"
output_dir="${6:-}"
default_runtime_timeout=120
[[ "$scenario" == serverless ]] && default_runtime_timeout=60
poll_timeout="${OVERTE_IOS_WORLD_TIMEOUT_SECONDS:-$default_runtime_timeout}"
poll_interval="${OVERTE_IOS_WORLD_POLL_SECONDS:-2}"
screenshot_settle="${OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS:-2}"
screenshot_wait="${OVERTE_IOS_WORLD_SCREENSHOT_WAIT_SECONDS:-30}"
# Once the source entity payload is present, a healthy client should advance
# through tree insertion and render handoff promptly. Boot and launch have
# separate watchdogs; use 60 seconds for local data and retain 120 seconds for
# domain/network variability.
entity_stall_timeout="${OVERTE_IOS_WORLD_ENTITY_STALL_TIMEOUT_SECONDS:-$default_runtime_timeout}"
# CoreSimulatorBridge itself retries app launches for 120 seconds. Keep the
# outer watchdog above that boundary so a large freshly installed app can
# finish LaunchServices registration and return either its PID or a causal
# launch error instead of being killed mid-handshake.
launch_timeout="${OVERTE_IOS_WORLD_LAUNCH_TIMEOUT_SECONDS:-180}"
# External macOS samplers can perturb or stall CoreSimulator. Keep the
# supplementary snapshot explicitly opt-in; in-process Vulkan breadcrumbs are
# the normal fail-closed diagnostic path.
stack_sample_delay="${OVERTE_IOS_WORLD_STACK_SAMPLE_SECONDS:-0}"
stack_symbol_bundle="${OVERTE_IOS_WORLD_SYMBOL_BUNDLE:-}"
crash_report_wait="${OVERTE_IOS_WORLD_CRASH_REPORT_WAIT_SECONDS:-20}"
diagnostics_dir="${OVERTE_IOS_WORLD_DIAGNOSTICS_DIR:-}"
mvk_trace_vulkan_calls="${OVERTE_IOS_WORLD_MVK_TRACE_VULKAN_CALLS:-}"
mvk_synchronous_queue_submits="${OVERTE_IOS_WORLD_MVK_SYNCHRONOUS_QUEUE_SUBMITS:-}"
render_diagnostic="${OVERTE_IOS_WORLD_RENDER_DIAGNOSTIC:-trace}"
camera_diagnostic=default
if [[ "$render_diagnostic" == camera-first-person ]]; then
    # Keep the preserved binary's renderer in trace mode while the harness
    # changes only the disposable simulator's camera-startup preferences.
    camera_diagnostic=first-person
    render_diagnostic=trace
fi
gpu_trace="${OVERTE_IOS_WORLD_GPU_TRACE:-0}"
capture_only="${OVERTE_IOS_WORLD_CAPTURE_ONLY:-0}"
camera_launch_arguments=()

[[ -d "$app_path" && "$app_path" == *.app ]] || {
    echo "usage: $0 APP_PATH BUNDLE_ID iphone|ipad serverless|online EXPECTED_DOMAIN|- OUTPUT_DIR" >&2
    exit 2
}
[[ "$bundle_id" =~ ^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$ ]] || {
    echo "invalid bundle identifier" >&2
    exit 2
}
[[ "$family" == iphone || "$family" == ipad ]] || {
    echo "family must be iphone or ipad" >&2
    exit 2
}
[[ "$scenario" == serverless || "$scenario" == online ]] || {
    echo "scenario must be serverless or online" >&2
    exit 2
}
[[ -n "$output_dir" ]] || { echo "output directory is required" >&2; exit 2; }
[[ "$poll_timeout" =~ ^[1-9][0-9]*$ ]] && ((10#$poll_timeout <= 1200)) || {
    echo "OVERTE_IOS_WORLD_TIMEOUT_SECONDS must be an integer from 1 through 1200" >&2
    exit 2
}
[[ "$poll_interval" =~ ^[1-9][0-9]*$ ]] && ((10#$poll_interval <= 30)) || {
    echo "OVERTE_IOS_WORLD_POLL_SECONDS must be an integer from 1 through 30" >&2
    exit 2
}
[[ "$screenshot_settle" =~ ^[0-9]+$ ]] && ((10#$screenshot_settle <= 30)) || {
    echo "OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS must be an integer from 0 through 30" >&2
    exit 2
}
[[ "$screenshot_wait" =~ ^[1-9][0-9]*$ ]] && ((10#$screenshot_wait <= 600)) || {
    echo "OVERTE_IOS_WORLD_SCREENSHOT_WAIT_SECONDS must be an integer from 1 through 600" >&2
    exit 2
}
[[ "$entity_stall_timeout" =~ ^[1-9][0-9]*$ ]] && ((10#$entity_stall_timeout <= 600)) || {
    echo "OVERTE_IOS_WORLD_ENTITY_STALL_TIMEOUT_SECONDS must be an integer from 1 through 600" >&2
    exit 2
}
[[ "$launch_timeout" =~ ^[0-9]+$ ]] && ((10#$launch_timeout >= 130 && 10#$launch_timeout <= 600)) || {
    echo "OVERTE_IOS_WORLD_LAUNCH_TIMEOUT_SECONDS must be an integer from 130 through 600" >&2
    exit 2
}
[[ "$stack_sample_delay" =~ ^[0-9]+$ ]] && ((10#$stack_sample_delay <= 1200)) || {
    echo "OVERTE_IOS_WORLD_STACK_SAMPLE_SECONDS must be an integer from 0 through 1200" >&2
    exit 2
}
[[ -z "$mvk_synchronous_queue_submits" || "$mvk_synchronous_queue_submits" == 0 || "$mvk_synchronous_queue_submits" == 1 ]] || {
    echo "OVERTE_IOS_WORLD_MVK_SYNCHRONOUS_QUEUE_SUBMITS must be 0 or 1" >&2
    exit 2
}
case "$render_diagnostic" in
    off|trace|cpu-cull-off|gpu-cull-off|depth-off|full-scissor|reset-format) ;;
    *)
        echo "OVERTE_IOS_WORLD_RENDER_DIAGNOSTIC is unsupported" >&2
        exit 2
        ;;
esac
[[ "$gpu_trace" == 0 || "$gpu_trace" == 1 ]] || {
    echo "OVERTE_IOS_WORLD_GPU_TRACE must be 0 or 1" >&2
    exit 2
}
[[ "$capture_only" == 0 || "$capture_only" == 1 ]] || {
    echo "OVERTE_IOS_WORLD_CAPTURE_ONLY must be 0 or 1" >&2
    exit 2
}
if [[ -n "$stack_symbol_bundle" ]]; then
    [[ "$stack_symbol_bundle" == /* && -d "$stack_symbol_bundle" && "$stack_symbol_bundle" == *.dSYM && \
        -f "$stack_symbol_bundle/Contents/Resources/DWARF/Overte" ]] || {
        echo "OVERTE_IOS_WORLD_SYMBOL_BUNDLE must name an absolute Overte dSYM bundle" >&2
        exit 2
    }
    case "$stack_symbol_bundle" in
        *$'\n'*|*$'\r'*|*'"'*|*'\\'*)
            echo "OVERTE_IOS_WORLD_SYMBOL_BUNDLE cannot be represented safely in LLDB" >&2
            exit 2
            ;;
    esac
fi
[[ "$crash_report_wait" =~ ^[0-9]+$ ]] && ((10#$crash_report_wait <= 60)) || {
    echo "OVERTE_IOS_WORLD_CRASH_REPORT_WAIT_SECONDS must be an integer from 0 through 60" >&2
    exit 2
}
[[ -z "$mvk_trace_vulkan_calls" || "$mvk_trace_vulkan_calls" =~ ^[0-6]$ ]] || {
    echo "OVERTE_IOS_WORLD_MVK_TRACE_VULKAN_CALLS must be empty or an integer from 0 through 6" >&2
    exit 2
}
for helper in "$timeout_runner" "$simulator_selector" "$screenshot_validator" "$world_validator" "$entity_gate_validator"; do
    [[ -f "$helper" ]] || { echo "iOS world test helper is unavailable" >&2; exit 2; }
done
[[ "$camera_diagnostic" != first-person || -f "$first_person_script" ]] || {
    echo "iOS first-person camera diagnostic script is unavailable" >&2
    exit 2
}

live_log() {
    # Keep the streamed CI status deliberately free of paths, URLs, bundle
    # identifiers and raw runtime markers.  The latter can contain domain and
    # session identifiers and remain confined to the existing diagnostics.
    printf 'OVERTE_IOS_WORLD_PROGRESS utc=%s family=%s scenario=%s %s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$family" "$scenario" "$*" >&3
}

if [[ "$scenario" == serverless ]]; then
    [[ "$expected_domain" == - ]] || { echo "serverless scenario requires '-' as domain" >&2; exit 2; }
    readonly destination="serverless_tutorial"
    readonly launch_url="file:///~/serverless/tutorial.json"
else
    [[ "$expected_domain" =~ ^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?$ ]] || {
        echo "online scenario requires the resolved domain UUID" >&2
        exit 2
    }
    readonly destination="overte_hub"
    readonly launch_url="hifi://overte_hub"
fi

mkdir -p "$output_dir"
readonly stem="${family}-${scenario}"
readonly screenshot="$output_dir/${stem}.png"
readonly screenshot_report="$output_dir/${stem}-screenshot.json"
readonly result="$output_dir/${stem}-runtime.json"
readonly failure_screenshot="$output_dir/${stem}-failure.png"
rm -f "$screenshot" "$screenshot_report" "$result" "$failure_screenshot"

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/overte-ios-world-smoke.XXXXXX")"
[[ -d "$temp_root" && "$temp_root" == */overte-ios-world-smoke.* ]] || {
    echo "could not create bounded simulator workspace" >&2
    exit 2
}
readonly temp_root
readonly device_list="$temp_root/devices.json"
readonly raw_log="$temp_root/process.log"
readonly log_snapshot="$temp_root/process-snapshot.log"
readonly marker_log="$temp_root/runtime-markers.log"
readonly app_stdout="$temp_root/application.stdout"
readonly app_stderr="$temp_root/application.stderr"
readonly runtime_log="$temp_root/runtime.log"
readonly process_state_log="$temp_root/process-samples.log"
readonly command_stderr="$temp_root/command.stderr"
readonly log_stream_stderr="$temp_root/log-stream.stderr"
readonly launch_marker="$temp_root/application-launch.marker"
readonly command_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-command-errors.log}"
readonly application_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-application.log}"
readonly process_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-process-samples.log}"
readonly postmortem_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-postmortem.log}"
readonly overte_crash_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-overte-crash-report.log}"
readonly simmetalhost_crash_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-simmetalhost-crash-report.log}"
readonly host_metal_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-host-metal.log}"
readonly mvk_dump_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-moltenvk-shaders}"
readonly gpu_trace_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}.gputrace}"

if [[ -n "$diagnostics_dir" ]]; then
    mkdir -p "$diagnostics_dir"
    rm -f "$command_diagnostics" "$application_diagnostics" "$process_diagnostics" \
        "$postmortem_diagnostics" "$overte_crash_diagnostics" \
        "$simmetalhost_crash_diagnostics" "$host_metal_diagnostics"
    [[ ! -e "$mvk_dump_diagnostics" ]] || {
        echo "MoltenVK diagnostic destination already exists" >&2
        exit 2
    }
    [[ ! -e "$gpu_trace_diagnostics" ]] || {
        echo "Metal GPU trace diagnostic destination already exists" >&2
        exit 2
    }
fi

# These files must exist before any fallible simulator operation because the
# EXIT trap preserves them even when discovery, boot or installation fails.
: > "$raw_log"
: > "$log_snapshot"
: > "$marker_log"
: > "$app_stdout"
: > "$app_stderr"
: > "$process_state_log"

active_udid=""
boot_requested=0
app_launched=0
app_installed=0
app_suspended=0
log_stream_pid=""
launch_pid=""
mvk_dump_root=""
gpu_trace_file=""
gpu_capture_triggered=0

run_bounded_with_grace() {
    local label="$1" seconds="$2" command_timeout_grace="$3"
    local status=0 command_pid heartbeat_pid
    local operation="${1// /_}"
    shift 3
    : > "$command_stderr"
    live_log "phase=command-start operation=$operation timeout_seconds=$seconds"
    "$timeout_runner" "$((10#$seconds + 10#$command_timeout_grace))" "$@" 2>"$command_stderr" &
    command_pid=$!
    python3 - "$command_pid" "$family" "$scenario" "$operation" \
        "$live_update_interval_seconds" >&3 <<'PY' &
import os
import sys
import time

pid = int(sys.argv[1])
family, scenario, operation = sys.argv[2:5]
interval = int(sys.argv[5])
elapsed = 0
while True:
    time.sleep(interval)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        raise SystemExit(0)
    elapsed += interval
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(
        f"OVERTE_IOS_WORLD_PROGRESS utc={timestamp} family={family} "
        f"scenario={scenario} phase=command-running operation={operation} "
        f"elapsed_seconds={elapsed}",
        flush=True,
    )
PY
    heartbeat_pid=$!
    if wait "$command_pid"; then
        status=0
    else
        status=$?
    fi
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    live_log "phase=command-finished operation=$operation result_status=$status"
    if ((status != 0)); then
        if [[ -n "$command_diagnostics" ]]; then
            {
                printf 'command_label=%s\ncommand_status=%s\n' "$label" "$status"
                if [[ -s "$command_stderr" ]]; then
                    cat "$command_stderr"
                else
                    printf 'command_stderr=empty\n'
                fi
                printf '%s\n' '---'
            } >> "$command_diagnostics"
            chmod 0600 "$command_diagnostics"
        fi
        echo "$label failed with status $status" >&2
    fi
    rm -f "$command_stderr"
    return "$status"
}

run_bounded() {
    run_bounded_with_grace "$1" "$2" "$timeout_grace_seconds" "${@:3}"
}

run_strict_bounded() {
    run_bounded_with_grace "$1" "$2" 0 "${@:3}"
}

sleep_until_next_live_update() {
    local now remaining delay=$((10#$poll_interval))
    now="$(date +%s)"
    remaining=$((next_live_update - now))
    if ((remaining > 0 && remaining < delay)); then
        delay=$remaining
    fi
    sleep "$delay"
}

get_application_data_container() {
    local attempt candidate="" status=1
    for attempt in 1 2 3; do
        status=0
        candidate="$(run_bounded "application data container attempt $attempt" 20 \
            xcrun simctl get_app_container "$active_udid" "$bundle_id" data)" || status=$?
        if ((status == 0)) && [[ -n "$candidate" && "$candidate" == /* && -d "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        if ((status == 0)); then
            status=1
            echo "application data container attempt $attempt returned an invalid path" >&2
        fi
        if ((attempt < 3)); then
            sleep "$attempt"
        fi
    done
    return "$status"
}

stop_log_stream() {
    local status=0
    [[ -n "$log_stream_pid" ]] || return 0
    if kill -0 "$log_stream_pid" 2>/dev/null; then
        kill -TERM "$log_stream_pid" 2>/dev/null || true
    fi
    wait "$log_stream_pid" 2>/dev/null || status=$?
    log_stream_pid=""
    rm -f "$log_stream_stderr"
    # SIGTERM is the expected way to stop the bounded stream after the runtime
    # gates have been observed. Its status must not replace the test result.
    return 0
}

preserve_failure_application_log() {
    [[ -n "$application_diagnostics" ]] || return 0
    local source label size
    {
        printf '%s\n' '=== retained acceptance markers ==='
        cat "$marker_log" 2>/dev/null || true
        grep -Eh 'OVERTE_IOS_(WORLD_DIAGNOSTIC|ENTITY_TRACE|VULKAN_FATAL|VULKAN_DEBUG|VULKAN_PIPELINE_CONTEXT|VULKAN_PIPELINE_CREATE|VULKAN_PRESENT)' \
            "$log_snapshot" "$raw_log" "$app_stdout" "$app_stderr" 2>/dev/null | tail -c 131072 || true
        for source in "$log_snapshot" "$raw_log" "$app_stdout" "$app_stderr"; do
            case "$source" in
                "$log_snapshot") label="bounded unified-log snapshot" ;;
                "$raw_log") label="unified lifecycle log" ;;
                "$app_stdout") label="application stdout" ;;
                *) label="application stderr" ;;
            esac
            size="$(wc -c < "$source" | tr -d '[:space:]')"
            printf '=== %s bytes=%s ===\n' "$label" "$size"
            if ((size <= 524288)); then
                cat "$source"
            else
                head -c 262144 "$source"
                printf '\n=== %s middle omitted ===\n' "$label"
                tail -c 262144 "$source"
            fi
        done
    } > "$application_diagnostics"
    chmod 0600 "$application_diagnostics"
}

record_process_state() {
    [[ -n "$launch_pid" ]] || return 0
    {
        printf 'utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        # Deliberately omit args and environment.  They can contain URLs,
        # signing values or tokens; comm plus resource counters is sufficient
        # to prove whether the launched PID is the app and whether it advances.
        ps -p "$launch_pid" -o pid=,ppid=,state=,etime=,time=,rss=,%cpu=,comm= \
            2>/dev/null || printf 'process_state=unavailable\n'
        printf '%s\n' '---'
    } >> "$process_state_log"
    chmod 0600 "$process_state_log"
}

process_is_running() {
    [[ -n "$launch_pid" ]] || return 1
    local state
    kill -0 "$launch_pid" 2>/dev/null || return 1
    state="$(ps -p "$launch_pid" -o state= 2>/dev/null || true)"
    [[ -n "$state" && "$state" != *Z* ]]
}

pause_application_for_screenshot() {
    ((app_launched)) && [[ -n "$launch_pid" ]] || return 1
    kill -0 "$launch_pid" 2>/dev/null || return 1
    kill -STOP "$launch_pid" 2>/dev/null || return 1
    app_suspended=1
    # Let already-submitted Metal work settle while preserving the last
    # presented framebuffer. This keeps simctl's screenshot service responsive
    # when the Vulkan present thread would otherwise continuously submit work.
    sleep 1
}

resume_application_after_screenshot() {
    ((app_suspended)) || return 0
    kill -CONT "$launch_pid" 2>/dev/null || true
    app_suspended=0
}

capture_startup_stack() {
    [[ -n "$launch_pid" ]] || return 0
    local sample_tool sample_output="$temp_root/startup.sample" status=0
    if [[ -n "$stack_symbol_bundle" ]]; then
        rm -f "$sample_output"
        {
            printf 'stack_sample_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
            printf 'stack_snapshot_tool=lldb\n'
        } >> "$process_state_log"
        "$timeout_runner" 320 xcrun lldb \
            --no-lldbinit --no-use-colors --batch --attach-pid "$launch_pid" \
            -o 'settings set auto-confirm true' \
            -o "target symbols add \"$stack_symbol_bundle\"" \
            -o 'thread list' \
            -o 'thread backtrace all -c 64' \
            -o 'script print("OVERTE_IOS_STACK_SNAPSHOT_COMPLETE")' \
            -o 'process detach' > "$sample_output" 2>&1 || status=$?
        # A timeout or failed debugger detach must not leave the application
        # suspended and turn a diagnostic failure into a renderer hang.
        kill -CONT "$launch_pid" 2>/dev/null || true
        {
            if [[ -s "$sample_output" ]]; then
                tail -c 2097152 "$sample_output"
            else
                printf 'stack_sample_output=empty\n'
            fi
            printf 'stack_sample_status=%s\n---\n' "$status"
        } >> "$process_state_log"
        # Simulator LLDB can block in attach before producing any thread
        # output. In that case, use macOS' non-debugger sampler as a bounded
        # fallback. This is diagnostic-only and must not change world-test
        # acceptance or leave the app suspended.
        if ((status != 0)); then
            sample_tool="$(command -v sample || true)"
            if [[ -n "$sample_tool" ]]; then
                local fallback_output="$temp_root/startup-sample-fallback.txt" fallback_status=0
                rm -f "$fallback_output"
                {
                    printf 'stack_snapshot_fallback_tool=sample\n'
                    "$timeout_runner" 315 "$sample_tool" "$launch_pid" 1 1 \
                        -file "$fallback_output" || fallback_status=$?
                    if [[ -s "$fallback_output" ]]; then
                        tail -c 2097152 "$fallback_output"
                    else
                        printf 'stack_snapshot_fallback_output=empty\n'
                    fi
                    printf 'stack_snapshot_fallback_status=%s\n---\n' "$fallback_status"
                } >> "$process_state_log" 2>&1
                rm -f "$fallback_output"
            fi
        fi
        rm -f "$sample_output"
        chmod 0600 "$process_state_log"
        return 0
    fi
    sample_tool="$(command -v sample || true)"
    [[ -n "$sample_tool" ]] || {
        printf 'stack_sample=unavailable\n---\n' >> "$process_state_log"
        chmod 0600 "$process_state_log"
        return 0
    }
    rm -f "$sample_output"
    {
        printf 'stack_sample_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        "$timeout_runner" 315 "$sample_tool" "$launch_pid" 1 1 \
            -file "$sample_output" || status=$?
        if [[ -s "$sample_output" ]]; then
            tail -c 2097152 "$sample_output"
        else
            printf 'stack_sample_output=empty\n'
        fi
        printf 'stack_sample_status=%s\n---\n' "$status"
    } >> "$process_state_log" 2>&1
    rm -f "$sample_output"
    chmod 0600 "$process_state_log"
    # Stack capture is supplementary.  Its failure must not replace the
    # actual app/gate result, which remains fail-closed below.
    return 0
}

preserve_failure_process_log() {
    [[ -n "$process_diagnostics" && -s "$process_state_log" ]] || return 0
    cp "$process_state_log" "$process_diagnostics"
    chmod 0600 "$process_diagnostics"
}

capture_postmortem_log() {
    [[ -n "$postmortem_diagnostics" && -n "$active_udid" ]] || return 0
    local status=0
    : > "$postmortem_diagnostics"
    "$timeout_runner" 345 xcrun simctl spawn "$active_udid" log show \
        --last 5m --style compact --info --debug \
        --predicate "process == \"Overte\" OR process == \"SimMetalHost\" OR process == \"launchd_sim\" OR composedMessage CONTAINS \"$bundle_id\" OR composedMessage CONTAINS \"Overte\"" \
        > "$postmortem_diagnostics" 2>&1 || status=$?
    printf '\npostmortem_status=%s\n' "$status" >> "$postmortem_diagnostics"
    chmod 0600 "$postmortem_diagnostics"
}

capture_host_metal_log() {
    [[ -n "$host_metal_diagnostics" ]] || return 0
    local log_tool temp_log="$temp_root/host-metal.log" status=0
    log_tool="$(command -v log || true)"
    if [[ -z "$log_tool" ]]; then
        printf 'host_metal_log=unavailable\n' > "$host_metal_diagnostics"
        chmod 0600 "$host_metal_diagnostics"
        return 0
    fi
    : > "$temp_log"
    "$timeout_runner" 345 "$log_tool" show --last 20m --style compact --info --debug \
        --predicate 'process == "SimMetalHost" OR process == "MTLCompilerService" OR eventMessage CONTAINS "OS_REASON_METAL" OR eventMessage CONTAINS "MTLRenderPipeline"' \
        > "$temp_log" 2>&1 || status=$?
    {
        tail -c 2097152 "$temp_log"
        printf '\nhost_metal_status=%s\n' "$status"
    } > "$host_metal_diagnostics"
    chmod 0600 "$host_metal_diagnostics"
}

preserve_moltenvk_shader_dump() {
    [[ -n "$mvk_dump_diagnostics" && -n "$mvk_dump_root" && -d "$mvk_dump_root" ]] || return 0
    local source name size count=0 total=0
    mkdir "$mvk_dump_diagnostics"
    while IFS= read -r -d '' source; do
        name="$(basename "$source")"
        case "$name" in
            shader*.metal|shader*.spv|pipeline*.txt) ;;
            *) continue ;;
        esac
        [[ -f "$source" && ! -L "$source" ]] || continue
        size="$(wc -c < "$source" | tr -d '[:space:]')"
        [[ "$size" =~ ^[0-9]+$ ]] || continue
        ((size <= 4194304)) || continue
        count=$((count + 1))
        total=$((total + size))
        ((count <= 128 && total <= 67108864)) || {
            echo "MoltenVK shader diagnostic bound exceeded" >&2
            break
        }
        cp "$source" "$mvk_dump_diagnostics/$name"
        chmod 0600 "$mvk_dump_diagnostics/$name"
    done < <(find "$mvk_dump_root" -maxdepth 1 -type f -print0 2>/dev/null)
    if ((count == 0)); then
        rmdir "$mvk_dump_diagnostics"
    fi
}

preserve_gpu_trace() {
    [[ -n "$gpu_trace_diagnostics" && -n "$gpu_trace_file" && -e "$gpu_trace_file" ]] || return 0
    local size_kib
    size_kib="$(du -sk "$gpu_trace_file" | awk '{print $1}')"
    [[ "$size_kib" =~ ^[0-9]+$ ]] && ((size_kib <= 524288)) || {
        echo "Metal GPU trace exceeds the 512 MiB diagnostic bound" >&2
        return 0
    }
    ditto --norsrc "$gpu_trace_file" "$gpu_trace_diagnostics"
}

trigger_gpu_trace() {
    ((gpu_trace)) || return 0
    local pipe_path
    pipe_path="$(run_bounded "Metal capture pipe discovery" 20 \
        xcrun simctl spawn "$active_udid" /usr/bin/find /tmp -maxdepth 1 -type p \
            -name 'MoltenVKCapturePipe-*' -print | tail -n 1)"
    [[ "$pipe_path" =~ ^/tmp/MoltenVKCapturePipe-[A-Za-z0-9]+$ ]] || {
        echo "MoltenVK on-demand capture pipe is unavailable" >&2
        return 1
    }
    run_bounded "Metal frame capture trigger" 20 \
        xcrun simctl spawn "$active_udid" /bin/sh -c 'printf x > "$1"' overte-capture "$pipe_path"
    gpu_capture_triggered=1
    live_log "phase=gpu-trace-triggered"
}

collect_gpu_trace() {
    ((gpu_trace && gpu_capture_triggered)) || return 0
    local deadline=$(( $(date +%s) + 30 )) size_kib
    while [[ ! -e "$gpu_trace_file" ]]; do
        if (( $(date +%s) >= deadline )); then
            echo "Metal GPU trace was not finalized" >&2
            return 1
        fi
        sleep 1
    done
    size_kib="$(du -sk "$gpu_trace_file" | awk '{print $1}')"
    [[ "$size_kib" =~ ^[0-9]+$ ]] && ((size_kib <= 524288)) || {
        echo "Metal GPU trace exceeds the 512 MiB evidence bound" >&2
        return 1
    }
    ditto --norsrc "$gpu_trace_file" "$output_dir/${stem}.gputrace"
    live_log "phase=gpu-trace-collected"
}

capture_crash_reports() {
    [[ -n "$overte_crash_diagnostics" && -n "$simmetalhost_crash_diagnostics" && -f "$launch_marker" ]] || return 0
    local wait_seconds="${1:-0}" root report deadline
    local -a overte_reports=() simmetalhost_reports=()
    deadline=$(( $(date +%s) + 10#$wait_seconds ))
    while :; do
        overte_reports=()
        simmetalhost_reports=()
        for root in \
            "$HOME/Library/Logs/DiagnosticReports" \
            "$HOME/Library/Developer/CoreSimulator/Devices/$active_udid/data/Library/Logs/CrashReporter"; do
            [[ -d "$root" ]] || continue
            while IFS= read -r -d '' report; do
                case "$(basename "$report")" in
                    Overte*) overte_reports+=("$report") ;;
                    SimMetalHost*) simmetalhost_reports+=("$report") ;;
                esac
            done < <(find "$root" -maxdepth 3 -type f \
                \( -name 'Overte*.ips' -o -name 'Overte*.crash' -o \
                   -name 'SimMetalHost*.ips' -o -name 'SimMetalHost*.crash' \) \
                -newer "$launch_marker" -print0 2>/dev/null)
        done
        if (( $(date +%s) >= deadline )); then
            break
        fi
        sleep 1
    done
    rm -f "$overte_crash_diagnostics" "$simmetalhost_crash_diagnostics"
    if ((${#overte_reports[@]} > 0)); then
        : > "$overte_crash_diagnostics"
        for report in "${overte_reports[@]}"; do
            printf '=== %s ===\n' "$(basename "$report")" >> "$overte_crash_diagnostics"
            tail -c 2097152 "$report" >> "$overte_crash_diagnostics" 2>/dev/null || true
            printf '\n' >> "$overte_crash_diagnostics"
        done
        chmod 0600 "$overte_crash_diagnostics"
    fi
    if ((${#simmetalhost_reports[@]} > 0)); then
        : > "$simmetalhost_crash_diagnostics"
        for report in "${simmetalhost_reports[@]}"; do
            printf '=== %s ===\n' "$(basename "$report")" >> "$simmetalhost_crash_diagnostics"
            tail -c 2097152 "$report" >> "$simmetalhost_crash_diagnostics" 2>/dev/null || true
            printf '\n' >> "$simmetalhost_crash_diagnostics"
        done
        chmod 0600 "$simmetalhost_crash_diagnostics"
    fi
}

runtime_log_contains() {
    local pattern="$1"
    grep -Eq "$pattern" "$marker_log" "$log_snapshot" "$raw_log" "$app_stdout" "$app_stderr"
}

world_progress_summary() {
    local -a observed=()
    runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested' && observed+=(navigation)
    if [[ "$scenario" == serverless ]]; then
        runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed' && observed+=(import)
        runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_viewpoint_applied[[:space:]]+success=[[:space:]]+1' && observed+=(viewpoint)
    else
        runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+domain_list_connected' && observed+=(domain)
        runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active' && observed+=(server)
        runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_query_sent' && observed+=(query)
        runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received' && observed+=(data)
    fi
    runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' && observed+=(tree)
    runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && observed+=(handoff)
    camera_diagnostic_observed && observed+=(camera)
    renderer_output_observed && observed+=(renderer)
    if ((${#observed[@]} == 0)); then
        printf 'none'
    else
        local IFS=,
        printf '%s' "${observed[*]}"
    fi
}

camera_diagnostic_observed() {
    [[ "$camera_diagnostic" != first-person ]] ||
        runtime_log_contains 'OVERTE_IOS_CAMERA_DIAGNOSTIC[[:space:]]+mode=first person look at([[:space:]]|$)'
}

renderer_output_observed() {
    # The state-transition marker can be emitted before unified-log capture
    # attaches. Resample plus final CompositeHUD completion is repeated every
    # frame; the later screenshot validator remains the fail-closed proof that
    # those commands reached the swapchain with visible world detail.
    runtime_log_contains 'OVERTE_IOS_VULKAN_PRESENT.*output_ready=1' || {
        runtime_log_contains 'OVERTE_IOS_VULKAN_DRAW[[:space:]]+batch=Resample::run[[:space:]]+stage=draw_pass_complete' &&
            runtime_log_contains 'OVERTE_IOS_VULKAN_DRAW[[:space:]]+batch=CompositeHUD[[:space:]]+stage=draw_pass_complete'
    }
}

report_missing_world_gates() {
    local marker pattern
    local -a required=(
        'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested'
    )
    if [[ "$scenario" == serverless ]]; then
        required+=(
            'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff'
            'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_viewpoint_applied[[:space:]]+success=[[:space:]]+1'
        )
    else
        required+=(
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+domain_list_connected'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_query_sent'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty'
            'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff'
        )
    fi
    if [[ "$camera_diagnostic" == first-person ]]; then
        required+=(
            'OVERTE_IOS_CAMERA_DIAGNOSTIC[[:space:]]+mode=first person look at([[:space:]]|$)'
        )
    fi
    for pattern in "${required[@]}"; do
        if ! runtime_log_contains "$pattern"; then
            marker="${pattern#*+}"
            marker="${marker//\[[:space:]\]/ }"
            printf 'missing_runtime_gate=%s\n' "$marker" >&2
        fi
    done
    renderer_output_observed || printf '%s\n' 'missing_runtime_gate=renderer_output' >&2
}

retain_acceptance_markers() {
    local source
    # Gates can be visible first in the continuously streamed log but absent
    # from a later rolling `log show` snapshot. Store a canonical, timestamp-
    # free copy from every capture source before the raw sources are discarded.
    for source in "$raw_log" "$app_stdout" "$app_stderr" "$log_snapshot"; do
        [[ -s "$source" ]] || continue
        sed -nE 's/^.*(OVERTE_IOS_((WORLD|ENTITY)_GATE|CAMERA_DIAGNOSTIC)[[:space:]]+.*)$/\1/p' \
            "$source" >> "$marker_log"
    done
    awk '!seen[$0]++' "$marker_log" > "$marker_log.next"
    mv "$marker_log.next" "$marker_log"
}

refresh_runtime_log_snapshot() {
    [[ -n "$active_udid" && "$launch_pid" =~ ^[1-9][0-9]*$ ]] || return 0
    local snapshot_candidate="$temp_root/process-snapshot.next" status=0
    rm -f "$snapshot_candidate"
    # This persisted-log query is supplementary to the continuous stream. A
    # wedged `log show` must return control before the five-second live update
    # is due, rather than freezing the gate loop for the former 308 seconds.
    "$timeout_runner" 4 xcrun simctl spawn "$active_udid" log show \
        --last 2m --style compact --info --debug \
        --predicate "processIdentifier == $launch_pid AND (eventMessage CONTAINS \"OVERTE_IOS_WORLD_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_TRACE\" OR eventMessage CONTAINS \"OVERTE_IOS_CAMERA_DIAGNOSTIC\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_FATAL\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DEBUG\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CONTEXT\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CREATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PRESENT\")" \
        > "$snapshot_candidate" 2>/dev/null || status=$?
    if ((status == 0)); then
        mv "$snapshot_candidate" "$log_snapshot"
        # Persist sparse one-shot gates across the rolling two-minute snapshot
        # and the independently captured stream/stdout/stderr sources.
        retain_acceptance_markers
        grep -Eh '(^|[[:space:]])OVERTE_IOS_VULKAN_FATAL[[:space:]]|OVERTE_IOS_VULKAN_PRESENT.*output_ready=1' \
            "$log_snapshot" >> "$marker_log" 2>/dev/null || true
        awk '!seen[$0]++' "$marker_log" > "$marker_log.next"
        mv "$marker_log.next" "$marker_log"
    else
        rm -f "$snapshot_candidate"
    fi
    # The continuously running stream remains the fallback. A failed snapshot
    # query is supplementary and must never replace the runtime result.
    return 0
}

fail_if_vulkan_fatal() {
    # `log stream` prints its predicate before the first event. Match only a
    # standalone runtime marker, not the marker name quoted in that banner.
    if runtime_log_contains '(^|[[:space:]])OVERTE_IOS_VULKAN_FATAL[[:space:]]'; then
        # The pipeline-context and driver callback immediately follow the fatal
        # marker. Let the already-running stream drain them before the EXIT trap
        # stops it and copies the bounded diagnostics.
        sleep 1
        echo "fatal iOS Vulkan pipeline error observed" >&2
        return 1
    fi
    return 0
}

assemble_runtime_log() {
    retain_acceptance_markers
    if [[ "$scenario" == online ]]; then
        local source candidate="$temp_root/runtime-candidate.log"
        local navigation
        navigation="$(grep -Em1 'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested' "$marker_log")"
        for source in "$log_snapshot" "$raw_log" "$app_stdout" "$app_stderr"; do
            [[ -s "$source" ]] || continue
            {
                printf '%s\n' "$navigation"
                sed -nE 's/^.*(OVERTE_IOS_ENTITY_GATE[[:space:]]+.*)$/\1/p' "$source"
            } > "$candidate"
            if python3 "$entity_gate_validator" "$candidate" >/dev/null 2>&1; then
                mv "$candidate" "$runtime_log"
                return
            fi
        done
        rm -f "$candidate"
    fi
    # Validation consumes only the canonical ledger. Mixing timestamped raw
    # sources back in would turn one gate into multiple logical occurrences.
    # For online runs, prefer one individually validated chronological source
    # above: independently refreshed snapshots can discover older events after
    # newer ones and therefore cannot define event order by discovery time.
    cp "$marker_log" "$runtime_log"
}

fail_stopped_log_stream() {
    local status=0
    wait "$log_stream_pid" 2>/dev/null || status=$?
    log_stream_pid=""
    if ((status == 0)); then
        status=1
    fi
    if [[ -n "$command_diagnostics" ]]; then
        {
            printf 'command_label=process log stream\ncommand_status=%s\n' "$status"
            if [[ -s "$log_stream_stderr" ]]; then
                cat "$log_stream_stderr"
            else
                printf 'command_stderr=empty\n'
            fi
            printf '%s\n' '---'
        } >> "$command_diagnostics"
        chmod 0600 "$command_diagnostics"
    fi
    echo "process log stream stopped before the world gates were observed" >&2
    rm -f "$log_stream_stderr"
    return "$status"
}

finish() {
    local status=$? report_wait=0
    trap - EXIT
    live_log "phase=cleanup result_status=$status"
    resume_application_after_screenshot
    stop_log_stream
    if ((status != 0)); then
        preserve_failure_application_log
        record_process_state
        preserve_failure_process_log
    fi
    if ((status != 0)) && [[ -n "$active_udid" && ! -f "$failure_screenshot" ]]; then
        pause_application_for_screenshot || true
        run_bounded "failure screenshot" 30 xcrun simctl io "$active_udid" screenshot \
            "$failure_screenshot" >/dev/null || true
        resume_application_after_screenshot
    fi
    if ((status != 0)); then
        if ((app_launched)); then
            report_wait=$((10#$crash_report_wait))
        fi
        capture_crash_reports "$report_wait" || true
        capture_postmortem_log || true
        capture_host_metal_log || true
        preserve_moltenvk_shader_dump || true
        preserve_gpu_trace || true
    fi
    if ((app_launched)) && [[ -n "$active_udid" ]]; then
        run_bounded "application cleanup" 30 xcrun simctl terminate \
            "$active_udid" "$bundle_id" >/dev/null || true
    fi
    if ((app_installed)) && [[ -n "$active_udid" ]]; then
        run_bounded "installed application cleanup" 60 xcrun simctl uninstall \
            "$active_udid" "$bundle_id" >/dev/null || true
    fi
    if ((boot_requested)) && [[ -n "$active_udid" ]]; then
        run_bounded "simulator cleanup" 60 xcrun simctl shutdown "$active_udid" >/dev/null || true
    fi
    rm -f "$raw_log" "$log_snapshot" "$marker_log" "$app_stdout" "$app_stderr" "$runtime_log" "$process_state_log" \
        "$command_stderr" "$log_stream_stderr" "$device_list" "$temp_root/startup.sample"
    rm -rf "$temp_root"
    exit "$status"
}
trap finish EXIT

live_log "phase=start gate_timeout_seconds=$poll_timeout entity_stall_timeout_seconds=$entity_stall_timeout screenshot_timeout_seconds=$screenshot_wait live_interval_seconds=$live_update_interval_seconds"
live_log "phase=simulator-discovery"
run_bounded "simulator discovery" 60 xcrun simctl list devices available --json > "$device_list"
active_udid="$(python3 "$simulator_selector" "$family" < "$device_list")"
[[ -n "$active_udid" ]] || { echo "simulator selection returned no device" >&2; exit 1; }
device_identity="$(python3 - "$device_list" "$active_udid" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
udid = sys.argv[2]
for runtime, devices in payload.get("devices", {}).items():
    for device in devices:
        if device.get("udid") == udid:
            name = str(device.get("name", "unknown")).replace("\n", " ").replace("\r", " ")
            print(f"device={name} runtime={runtime.rsplit('.', 1)[-1]}")
            raise SystemExit(0)
raise SystemExit("selected simulator identity is unavailable")
PY
)"
live_log "phase=simulator-selected $device_identity"

boot_requested=1
boot_status=0
live_log "phase=simulator-boot"
run_bounded "simulator boot request" 60 xcrun simctl boot "$active_udid" >/dev/null || boot_status=$?
if ((boot_status == 124 || boot_status >= 128)); then
    exit "$boot_status"
fi
if [[ "$family" == ipad ]]; then
    # Reviewed iPad runners normally boot in about 80 seconds. Fail at 120
    # seconds so a wedged CoreSimulator cannot consume the former 25-minute
    # allowance plus generic command grace.
    run_strict_bounded "simulator boot" 120 \
        xcrun simctl bootstatus "$active_udid" -b >/dev/null
else
    run_bounded "simulator boot" 1500 \
        xcrun simctl bootstatus "$active_udid" -b >/dev/null
fi
live_log "phase=simulator-ready"

stale_remove_status=0
run_bounded "stale application removal" 60 xcrun simctl uninstall \
    "$active_udid" "$bundle_id" >/dev/null || stale_remove_status=$?
if ((stale_remove_status != 0)); then
    if run_bounded "stale application probe" 30 xcrun simctl get_app_container \
        "$active_udid" "$bundle_id" data >/dev/null; then
        echo "stale application data could not be removed" >&2
        exit "$stale_remove_status"
    fi
fi
live_log "phase=application-install"
run_bounded "application install" 120 xcrun simctl install "$active_udid" "$app_path" >/dev/null
app_installed=1
data_container="$(get_application_data_container)"
[[ -n "$data_container" && "$data_container" == /* && -d "$data_container" ]] || {
    echo "application data container is unavailable" >&2
    exit 1
}
if [[ "$camera_diagnostic" == first-person ]]; then
    # Do not alter firstRun: it also selects the startup navigation path. Load
    # one app-sandboxed startup script that changes only Camera.mode, allowing
    # the preserved binary to A/B first-person without changing world import.
    camera_script="$data_container/tmp/overte-ios-camera-first-person.js"
    [[ ! -e "$camera_script" ]] || { echo "camera diagnostic script path already exists" >&2; exit 1; }
    install -m 0600 "$first_person_script" "$camera_script"
    camera_launch_arguments=(--defaultScriptsOverride "file://$camera_script")
    live_log "phase=camera-diagnostic-ready mode=first-person"
fi
mvk_dump_root="$data_container/tmp/overte-mvk-shaders-$stem"
[[ ! -e "$mvk_dump_root" ]] || { echo "MoltenVK dump path already exists" >&2; exit 1; }
mkdir "$mvk_dump_root"
chmod 0700 "$mvk_dump_root"
if ((gpu_trace)); then
    gpu_trace_file="$data_container/tmp/overte-$stem.gputrace"
    [[ ! -e "$gpu_trace_file" ]] || { echo "Metal GPU trace path already exists" >&2; exit 1; }
fi

# The world evidence is a rendering/navigation test, not a permission-dialog
# test. Grant the simulator-only microphone privacy permission before launch so the
# deterministic screenshots cannot be obscured by AVAudioSession's consent
# sheet. Physical-device consent remains a separate manual/device acceptance
# gate and is never bypassed here.
run_bounded "simulator microphone permission" 60 xcrun simctl privacy \
    "$active_udid" grant microphone "$bundle_id" >/dev/null
live_log "phase=application-installed"

# Capture the app process, its lifecycle messages and the privacy-bounded
# world/entity markers. Starting the stream before launch prevents immediate
# startup failures or fast gates from falling into the gap between launch and
# a later query. The raw stream remains runner-local; only a size-bounded,
# secret-redacted copy is uploaded on failure by the workflow.
: > "$raw_log"
: > "$app_stdout"
: > "$app_stderr"
: > "$log_stream_stderr"
# The subscriber starts before application launch and must survive both the
# world-gate and post-handoff framebuffer deadlines.
log_stream_timeout=$((10#$launch_timeout + (2 * 10#$poll_timeout) + 60))
"$timeout_runner" "$log_stream_timeout" xcrun simctl spawn "$active_udid" log stream \
    --style compact --level debug \
    --predicate "(eventMessage CONTAINS \"OVERTE_IOS_WORLD_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_TRACE\" OR eventMessage CONTAINS \"OVERTE_IOS_CAMERA_DIAGNOSTIC\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_FATAL\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DEBUG\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CONTEXT\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CREATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PRESENT\")" \
    > "$raw_log" 2> "$log_stream_stderr" &
log_stream_pid=$!
# Give CoreSimulator's log subscriber a bounded head start. Merely spawning the
# background wrapper is not sufficient: the shell may otherwise launch the app
# before `log stream` has subscribed and lose an immediate navigation marker.
sleep 1
if ! kill -0 "$log_stream_pid" 2>/dev/null; then
    stream_status=0
    fail_stopped_log_stream || stream_status=$?
    exit "$stream_status"
fi

touch "$launch_marker"
launch_environment=(
    "SIMCTL_CHILD_MVK_CONFIG_LOG_LEVEL=4"
    "SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0"
    "SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR=$mvk_dump_root"
    "SIMCTL_CHILD_OVERTE_IOS_RENDER_DIAGNOSTIC=$render_diagnostic"
)
if ((gpu_trace)); then
    launch_environment+=(
        "SIMCTL_CHILD_MTL_CAPTURE_ENABLED=1"
        "SIMCTL_CHILD_METAL_CAPTURE_ENABLED=1"
        "SIMCTL_CHILD_MVK_CONFIG_AUTO_GPU_CAPTURE_SCOPE=3"
        "SIMCTL_CHILD_MVK_CONFIG_AUTO_GPU_CAPTURE_OUTPUT_FILE=$gpu_trace_file"
    )
fi
if [[ -n "${OVERTE_IOS_PRESENT_PROBE:-}" ]]; then
    launch_environment+=("SIMCTL_CHILD_OVERTE_IOS_PRESENT_PROBE=$OVERTE_IOS_PRESENT_PROBE")
fi
if [[ -n "$mvk_trace_vulkan_calls" ]]; then
    launch_environment+=("SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS=$mvk_trace_vulkan_calls")
fi
if [[ -n "$mvk_synchronous_queue_submits" ]]; then
    launch_environment+=("SIMCTL_CHILD_MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=$mvk_synchronous_queue_submits")
fi
live_log "phase=application-launch"
launch_output="$(run_bounded "application launch" "$launch_timeout" env \
    "${launch_environment[@]}" \
    xcrun simctl launch \
    --stdout="$app_stdout" --stderr="$app_stderr" \
    "$active_udid" "$bundle_id" --url "$launch_url" --ios-world-evidence \
    --no-login-suggestion "${camera_launch_arguments[@]}")"
[[ "$launch_output" == *":"* ]] || { echo "application launch returned no process identifier" >&2; exit 1; }
launch_pid="${launch_output##*: }"
[[ "$launch_pid" =~ ^[1-9][0-9]*$ ]] || { echo "application launch returned an invalid process identifier" >&2; exit 1; }
app_launched=1
record_process_state
live_log "phase=application-running pid=$launch_pid"

deadline=$(( $(date +%s) + 10#$poll_timeout ))
absolute_deadline=$(( $(date +%s) + (2 * 10#$poll_timeout) ))
runtime_wait_started="$(date +%s)"
next_live_update="$runtime_wait_started"
entity_stall_started=0
entity_stall_deadline=0
progress_size=0
startup_stack_captured=0
if ((10#$stack_sample_delay > 0)); then
    # Diagnostic runs must attach before the first persisted-log query. That
    # query can itself take longer than the requested delay and otherwise miss
    # a startup crash entirely.
    sleep "$stack_sample_delay"
    if process_is_running; then
        capture_startup_stack
    fi
    startup_stack_captured=1
fi
while :; do
    # `log stream` can block-buffer when redirected to a file. Query the
    # simulator's persisted log for this exact process so accepted gates become
    # visible promptly, while retaining the continuous stream for crash tails.
    refresh_runtime_log_snapshot
    current_progress_size="$(wc -c < "$marker_log" | tr -d '[:space:]')"
    if ((current_progress_size > progress_size)); then
        progress_size=$current_progress_size
        deadline=$(( $(date +%s) + 10#$poll_timeout ))
        ((deadline <= absolute_deadline)) || deadline=$absolute_deadline
        if ((entity_stall_started)); then
            entity_stall_deadline=$(( $(date +%s) + 10#$entity_stall_timeout ))
        fi
        live_log "phase=runtime-gates observed=$(world_progress_summary)"
    fi
    fail_if_vulkan_fatal || exit 1
    if ! process_is_running; then
        # Give the unified log stream one bounded opportunity to flush a fatal
        # marker emitted immediately before process termination.
        sleep 1
        fail_if_vulkan_fatal || exit 1
        echo "application process exited before the world gates were observed" >&2
        exit 1
    fi
    record_process_state
    ready=0
    if [[ "$capture_only" == 1 ]]; then
        runtime_log_contains 'OVERTE_IOS_VULKAN_DRAW[[:space:]]+batch=Resample::run[[:space:]]+stage=draw_pass_complete' && \
            renderer_output_observed && ready=1
    elif runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested'; then
        if [[ "$scenario" == serverless ]]; then
            runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && \
            runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_viewpoint_applied[[:space:]]+success=[[:space:]]+1' && ready=1
        else
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+domain_list_connected' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_query_sent' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && ready=1
        fi
    fi
    if ((ready)) && ! camera_diagnostic_observed; then
        ready=0
    fi
    ((ready)) && break
    current_time="$(date +%s)"
    entity_source_ready=0
    entity_handoff_incomplete=0
    if [[ "$scenario" == serverless ]]; then
        runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed' && entity_source_ready=1
        if ! runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' || \
                ! runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' || \
                ! runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_viewpoint_applied[[:space:]]+success=[[:space:]]+1'; then
            entity_handoff_incomplete=1
        fi
    else
        runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received' && entity_source_ready=1
        if ! runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active' || \
                ! runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' || \
                ! runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff'; then
            entity_handoff_incomplete=1
        fi
    fi
    if ((entity_source_ready && entity_handoff_incomplete)); then
        if ((!entity_stall_started)); then
            entity_stall_started=$current_time
            entity_stall_deadline=$((current_time + 10#$entity_stall_timeout))
            live_log "phase=entity-handoff-stall-watch observed=$(world_progress_summary)"
        elif ((current_time >= entity_stall_deadline)); then
            report_missing_world_gates
            echo "$scenario world entity handoff stalled after source data became available" >&2
            exit 124
        fi
    fi
    if ((current_time >= next_live_update)); then
        live_log "phase=runtime-gates-wait elapsed_seconds=$((current_time - runtime_wait_started)) observed=$(world_progress_summary)"
        next_live_update=$((current_time + live_update_interval_seconds))
    fi
    if ! kill -0 "$log_stream_pid" 2>/dev/null; then
        stream_status=0
        fail_stopped_log_stream || stream_status=$?
        exit "$stream_status"
    fi
    if (( $(date +%s) >= deadline )); then
        report_missing_world_gates
        echo "$scenario world runtime timed out" >&2
        exit 124
    fi
    sleep_until_next_live_update
done
live_log "phase=runtime-gates-ready observed=$(world_progress_summary)"
trigger_gpu_trace

# The entity handoff precedes the first composited framebuffer.  On the
# simulator that gap is material, so a fixed short sleep can capture the
# startup clear rather than the world. Require the renderer's durable output
# transition before the optional final settle interval. The one-shot present
# marker can precede log attachment, so repeated completion of both final
# renderer batches is also accepted here; screenshot validation remains the
# final fail-closed presentation proof.
if [[ "$capture_only" == 0 ]]; then
    output_deadline=$(( $(date +%s) + 10#$poll_timeout ))
    framebuffer_wait_started="$(date +%s)"
    next_live_update="$framebuffer_wait_started"
    live_log "phase=framebuffer-wait"
    while :; do
        if runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && \
                renderer_output_observed; then
            if ((10#$stack_sample_delay > 0)) && ((!startup_stack_captured)); then
                capture_startup_stack
                startup_stack_captured=1
            fi
            break
        fi
        refresh_runtime_log_snapshot
        fail_if_vulkan_fatal || exit 1
        process_is_running || { echo "application process exited before world framebuffer output" >&2; exit 1; }
        current_time="$(date +%s)"
        if ((current_time >= next_live_update)); then
            live_log "phase=framebuffer-wait elapsed_seconds=$((current_time - framebuffer_wait_started)) observed=$(world_progress_summary)"
            next_live_update=$((current_time + live_update_interval_seconds))
        fi
        if (( $(date +%s) >= output_deadline )); then
            echo "$scenario world framebuffer output timed out" >&2
            exit 124
        fi
        sleep_until_next_live_update
    done
    live_log "phase=framebuffer-ready observed=$(world_progress_summary)"
fi

# Keep the log subscriber alive through the final presentation interval: a
# fatal renderer error after output readiness must invalidate the screenshot.
if ((10#$screenshot_settle > 0)); then
    sleep "$screenshot_settle"
fi
fail_if_vulkan_fatal || exit 1
process_is_running || { echo "application process exited before the world screenshot" >&2; exit 1; }
kill -0 "$log_stream_pid" 2>/dev/null || {
    stream_status=0
    fail_stopped_log_stream || stream_status=$?
    exit "$stream_status"
}
screenshot_deadline=$(( $(date +%s) + 10#$screenshot_wait ))
screenshot_attempt=0
while :; do
    screenshot_attempt=$((screenshot_attempt + 1))
    live_log "phase=screenshot-capture attempt=$screenshot_attempt"
    pause_application_for_screenshot
    run_bounded "world screenshot" 30 xcrun simctl io "$active_udid" screenshot "$screenshot" >/dev/null
    if [[ "$capture_only" == 1 ]] || python3 "$screenshot_validator" "$screenshot" \
            --scenario "$scenario" --destination "$destination" --output "$screenshot_report"; then
        # Keep the accepted framebuffer frozen while logs and evidence are
        # assembled. This prevents unrelated late pipeline compilation from
        # replacing or invalidating an already proven frame.
        live_log "phase=screenshot-accepted attempt=$screenshot_attempt"
        break
    fi
    live_log "phase=screenshot-retry attempt=$screenshot_attempt"
    resume_application_after_screenshot
    if (( $(date +%s) >= screenshot_deadline )); then
        echo "$scenario world screenshot detail timed out" >&2
        exit 1
    fi
    sleep 5
    fail_if_vulkan_fatal || exit 1
    process_is_running || { echo "application process exited while waiting for world detail" >&2; exit 1; }
    kill -0 "$log_stream_pid" 2>/dev/null || {
        stream_status=0
        fail_stopped_log_stream || stream_status=$?
        exit "$stream_status"
    }
done
assemble_runtime_log
if [[ "$capture_only" == 0 ]]; then
    validator_arguments=(
        "$runtime_log" --scenario "$scenario" --destination "$destination"
        --screenshot "$screenshot" --screenshot-report "$screenshot_report" --output "$result"
    )
    if [[ "$scenario" == online ]]; then
        validator_arguments+=(--expected-domain "$expected_domain")
    fi
    python3 "$world_validator" "${validator_arguments[@]}"
fi
resume_application_after_screenshot
collect_gpu_trace
fail_if_vulkan_fatal || exit 1
process_is_running || { echo "application process exited before world validation completed" >&2; exit 1; }
kill -0 "$log_stream_pid" 2>/dev/null || {
    stream_status=0
    fail_stopped_log_stream || stream_status=$?
    exit "$stream_status"
}
stop_log_stream

run_bounded "application termination" 60 xcrun simctl terminate "$active_udid" "$bundle_id" >/dev/null
app_launched=0
run_bounded "application removal" 60 xcrun simctl uninstall "$active_udid" "$bundle_id" >/dev/null
app_installed=0
run_bounded "simulator shutdown" 60 xcrun simctl shutdown "$active_udid" >/dev/null
boot_requested=0

if [[ "$capture_only" == 1 ]]; then
    echo "PASS full-client $family simulator $scenario diagnostic screenshot"
else
    echo "PASS full-client $family simulator $scenario world with screenshot"
fi
