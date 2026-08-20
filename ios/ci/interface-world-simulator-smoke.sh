#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
readonly simulator_selector="$script_dir/../tools/select-simulator.py"
readonly screenshot_validator="$script_dir/../tools/validate-world-screenshot.py"
readonly world_validator="$script_dir/../tools/validate-world-runtime.py"
readonly timeout_grace_seconds=300

app_path="${1:-}"
bundle_id="${2:-}"
family="${3:-}"
scenario="${4:-}"
expected_domain="${5:-}"
output_dir="${6:-}"
poll_timeout="${OVERTE_IOS_WORLD_TIMEOUT_SECONDS:-540}"
poll_interval="${OVERTE_IOS_WORLD_POLL_SECONDS:-2}"
screenshot_settle="${OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS:-2}"
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
capture_only="${OVERTE_IOS_WORLD_CAPTURE_ONLY:-0}"

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
for helper in "$timeout_runner" "$simulator_selector" "$screenshot_validator" "$world_validator"; do
    [[ -f "$helper" ]] || { echo "iOS world test helper is unavailable" >&2; exit 2; }
done

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

if [[ -n "$diagnostics_dir" ]]; then
    mkdir -p "$diagnostics_dir"
    rm -f "$command_diagnostics" "$application_diagnostics" "$process_diagnostics" \
        "$postmortem_diagnostics" "$overte_crash_diagnostics" \
        "$simmetalhost_crash_diagnostics" "$host_metal_diagnostics"
    [[ ! -e "$mvk_dump_diagnostics" ]] || {
        echo "MoltenVK diagnostic destination already exists" >&2
        exit 2
    }
fi

# These files must exist before any fallible simulator operation because the
# EXIT trap preserves them even when discovery, boot or installation fails.
: > "$raw_log"
: > "$log_snapshot"
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

run_bounded() {
    local label="$1" seconds="$2" status=0
    shift 2
    : > "$command_stderr"
    "$timeout_runner" "$((10#$seconds + timeout_grace_seconds))" "$@" 2>"$command_stderr" || status=$?
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
        grep -Eh 'OVERTE_IOS_(WORLD|ENTITY)_GATE|OVERTE_IOS_(WORLD_DIAGNOSTIC|VULKAN_FATAL|VULKAN_DEBUG|VULKAN_PIPELINE_CONTEXT|VULKAN_PIPELINE_CREATE|VULKAN_DRAW|VULKAN_PRESENT)' \
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
    grep -Eq "$pattern" "$log_snapshot" "$raw_log" "$app_stdout" "$app_stderr"
}

refresh_runtime_log_snapshot() {
    [[ -n "$active_udid" && "$launch_pid" =~ ^[1-9][0-9]*$ ]] || return 0
    local snapshot_candidate="$temp_root/process-snapshot.next" status=0
    rm -f "$snapshot_candidate"
    "$timeout_runner" 308 xcrun simctl spawn "$active_udid" log show \
        --last 2m --style compact --info --debug \
        --predicate "processIdentifier == $launch_pid AND (eventMessage CONTAINS \"OVERTE_IOS_WORLD_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_FATAL\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DEBUG\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CONTEXT\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CREATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DRAW\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PRESENT\")" \
        > "$snapshot_candidate" 2>/dev/null || status=$?
    if ((status == 0)); then
        mv "$snapshot_candidate" "$log_snapshot"
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
    if [[ -s "$log_snapshot" ]]; then
        cat "$log_snapshot" "$app_stdout" "$app_stderr" > "$runtime_log"
    else
        cat "$raw_log" "$app_stdout" "$app_stderr" > "$runtime_log"
    fi
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
    rm -f "$raw_log" "$app_stdout" "$app_stderr" "$runtime_log" "$process_state_log" \
        "$command_stderr" "$log_stream_stderr" "$device_list" "$temp_root/startup.sample"
    rm -rf "$temp_root"
    exit "$status"
}
trap finish EXIT

run_bounded "simulator discovery" 60 xcrun simctl list devices available --json > "$device_list"
active_udid="$(python3 "$simulator_selector" "$family" < "$device_list")"
[[ -n "$active_udid" ]] || { echo "simulator selection returned no device" >&2; exit 1; }

boot_requested=1
boot_status=0
run_bounded "simulator boot request" 60 xcrun simctl boot "$active_udid" >/dev/null || boot_status=$?
if ((boot_status == 124 || boot_status >= 128)); then
    exit "$boot_status"
fi
run_bounded "simulator boot" 1500 xcrun simctl bootstatus "$active_udid" -b >/dev/null

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
run_bounded "application install" 120 xcrun simctl install "$active_udid" "$app_path" >/dev/null
app_installed=1
data_container="$(get_application_data_container)"
[[ -n "$data_container" && "$data_container" == /* && -d "$data_container" ]] || {
    echo "application data container is unavailable" >&2
    exit 1
}
mvk_dump_root="$data_container/tmp/overte-mvk-shaders-$stem"
[[ ! -e "$mvk_dump_root" ]] || { echo "MoltenVK dump path already exists" >&2; exit 1; }
mkdir "$mvk_dump_root"
chmod 0700 "$mvk_dump_root"

# The world evidence is a rendering/navigation test, not a permission-dialog
# test. Grant the simulator-only microphone privacy permission before launch so the
# deterministic screenshots cannot be obscured by AVAudioSession's consent
# sheet. Physical-device consent remains a separate manual/device acceptance
# gate and is never bypassed here.
run_bounded "simulator microphone permission" 60 xcrun simctl privacy \
    "$active_udid" grant microphone "$bundle_id" >/dev/null

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
    --predicate "(process == \"Overte\" OR eventMessage CONTAINS \"$bundle_id\" OR eventMessage CONTAINS \"OVERTE_IOS_WORLD_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_FATAL\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DEBUG\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CONTEXT\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PIPELINE_CREATE\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_DRAW\" OR eventMessage CONTAINS \"OVERTE_IOS_VULKAN_PRESENT\")" \
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
)
if [[ -n "${OVERTE_IOS_PRESENT_PROBE:-}" ]]; then
    launch_environment+=("SIMCTL_CHILD_OVERTE_IOS_PRESENT_PROBE=$OVERTE_IOS_PRESENT_PROBE")
fi
if [[ -n "$mvk_trace_vulkan_calls" ]]; then
    launch_environment+=("SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS=$mvk_trace_vulkan_calls")
fi
if [[ -n "$mvk_synchronous_queue_submits" ]]; then
    launch_environment+=("SIMCTL_CHILD_MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=$mvk_synchronous_queue_submits")
fi
launch_output="$(run_bounded "application launch" "$launch_timeout" env \
    "${launch_environment[@]}" \
    xcrun simctl launch \
    --stdout="$app_stdout" --stderr="$app_stderr" \
    "$active_udid" "$bundle_id" --url "$launch_url" --ios-world-evidence \
    --no-login-suggestion)"
[[ "$launch_output" == *":"* ]] || { echo "application launch returned no process identifier" >&2; exit 1; }
launch_pid="${launch_output##*: }"
[[ "$launch_pid" =~ ^[1-9][0-9]*$ ]] || { echo "application launch returned an invalid process identifier" >&2; exit 1; }
app_launched=1
record_process_state

deadline=$(( $(date +%s) + 10#$poll_timeout ))
sample_deadline=$(( $(date +%s) + 10#$stack_sample_delay ))
startup_stack_captured=0
while :; do
    # `log stream` can block-buffer when redirected to a file. Query the
    # simulator's persisted log for this exact process so accepted gates become
    # visible promptly, while retaining the continuous stream for crash tails.
    refresh_runtime_log_snapshot
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
            runtime_log_contains 'OVERTE_IOS_VULKAN_PRESENT[[:space:]]+output_ready=1' && ready=1
    elif runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested'; then
        if [[ "$scenario" == serverless ]]; then
            runtime_log_contains 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && ready=1
        else
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+domain_list_connected' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_query_sent' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' && \
            runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && ready=1
        fi
    fi
    ((ready)) && break
    if ((10#$stack_sample_delay > 0)) && ((!startup_stack_captured)) && \
            (( $(date +%s) >= sample_deadline )); then
        capture_startup_stack
        startup_stack_captured=1
    fi
    if ! kill -0 "$log_stream_pid" 2>/dev/null; then
        stream_status=0
        fail_stopped_log_stream || stream_status=$?
        exit "$stream_status"
    fi
    if (( $(date +%s) >= deadline )); then
        echo "$scenario world runtime timed out" >&2
        exit 124
    fi
    sleep "$poll_interval"
done

# The entity handoff precedes the first composited framebuffer.  On the
# simulator that gap is material, so a fixed short sleep can capture the
# startup clear rather than the world. Require the renderer's durable output
# transition before the optional final settle interval. output_ready is a
# durable backend state transition and can race slightly ahead of the entity
# handoff on a fast frame; requiring log-line order would then wait forever for
# a marker that is intentionally emitted only once.
if [[ "$capture_only" == 0 ]]; then
    output_deadline=$(( $(date +%s) + 10#$poll_timeout ))
    while :; do
        if runtime_log_contains 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' && \
                runtime_log_contains 'OVERTE_IOS_VULKAN_PRESENT[[:space:]]+output_ready=1'; then
            if ((10#$stack_sample_delay > 0)) && ((!startup_stack_captured)); then
                capture_startup_stack
                startup_stack_captured=1
            fi
            break
        fi
        refresh_runtime_log_snapshot
        fail_if_vulkan_fatal || exit 1
        process_is_running || { echo "application process exited before world framebuffer output" >&2; exit 1; }
        if ((10#$stack_sample_delay > 0)) && ((!startup_stack_captured)) && \
                (( $(date +%s) >= sample_deadline )); then
            capture_startup_stack
            startup_stack_captured=1
        fi
        if (( $(date +%s) >= output_deadline )); then
            echo "$scenario world framebuffer output timed out" >&2
            exit 124
        fi
        sleep "$poll_interval"
    done
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
pause_application_for_screenshot
run_bounded "world screenshot" 30 xcrun simctl io "$active_udid" screenshot "$screenshot" >/dev/null
resume_application_after_screenshot
fail_if_vulkan_fatal || exit 1
process_is_running || { echo "application process exited while capturing the world screenshot" >&2; exit 1; }
kill -0 "$log_stream_pid" 2>/dev/null || {
    stream_status=0
    fail_stopped_log_stream || stream_status=$?
    exit "$stream_status"
}
assemble_runtime_log
if [[ "$capture_only" == 0 ]]; then
    python3 "$screenshot_validator" "$screenshot" \
        --scenario "$scenario" --destination "$destination" --output "$screenshot_report"

    validator_arguments=(
        "$runtime_log" --scenario "$scenario" --destination "$destination"
        --screenshot "$screenshot" --screenshot-report "$screenshot_report" --output "$result"
    )
    if [[ "$scenario" == online ]]; then
        validator_arguments+=(--expected-domain "$expected_domain")
    fi
    python3 "$world_validator" "${validator_arguments[@]}"
fi
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
