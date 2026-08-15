#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
readonly simulator_selector="$script_dir/../tools/select-simulator.py"
readonly screenshot_validator="$script_dir/../tools/validate-world-screenshot.py"
readonly world_validator="$script_dir/../tools/validate-world-runtime.py"

app_path="${1:-}"
bundle_id="${2:-}"
family="${3:-}"
scenario="${4:-}"
expected_domain="${5:-}"
output_dir="${6:-}"
poll_timeout="${OVERTE_IOS_WORLD_TIMEOUT_SECONDS:-240}"
poll_interval="${OVERTE_IOS_WORLD_POLL_SECONDS:-2}"
screenshot_settle="${OVERTE_IOS_WORLD_SCREENSHOT_SETTLE_SECONDS:-2}"
diagnostics_dir="${OVERTE_IOS_WORLD_DIAGNOSTICS_DIR:-}"

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
[[ "$poll_timeout" =~ ^[1-9][0-9]*$ ]] && ((10#$poll_timeout <= 900)) || {
    echo "OVERTE_IOS_WORLD_TIMEOUT_SECONDS must be an integer from 1 through 900" >&2
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
readonly command_stderr="$temp_root/command.stderr"
readonly log_stream_stderr="$temp_root/log-stream.stderr"
readonly command_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-command-errors.log}"
readonly application_diagnostics="${diagnostics_dir:+$diagnostics_dir/${stem}-application.log}"

if [[ -n "$diagnostics_dir" ]]; then
    mkdir -p "$diagnostics_dir"
    rm -f "$command_diagnostics"
fi

active_udid=""
boot_requested=0
app_launched=0
app_installed=0
log_stream_pid=""
launch_pid=""

run_bounded() {
    local label="$1" seconds="$2" status=0
    shift 2
    : > "$command_stderr"
    "$timeout_runner" "$seconds" "$@" 2>"$command_stderr" || status=$?
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
    [[ -n "$application_diagnostics" && -s "$raw_log" ]] || return 0
    install -m 0600 "$raw_log" "$application_diagnostics"
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
    local status=$?
    trap - EXIT
    stop_log_stream
    if ((status != 0)); then
        preserve_failure_application_log
    fi
    if ((status != 0)) && [[ -n "$active_udid" && ! -f "$failure_screenshot" ]]; then
        run_bounded "failure screenshot" 30 xcrun simctl io "$active_udid" screenshot \
            "$failure_screenshot" >/dev/null || true
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
    rm -f "$raw_log" "$command_stderr" "$log_stream_stderr" "$device_list"
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
run_bounded "simulator boot" 360 xcrun simctl bootstatus "$active_udid" -b >/dev/null

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

# Capture the app process, its lifecycle messages and the privacy-bounded
# world/entity markers. Starting the stream before launch prevents immediate
# startup failures or fast gates from falling into the gap between launch and
# a later query. The raw stream remains runner-local; only a size-bounded,
# secret-redacted copy is uploaded on failure by the workflow.
: > "$raw_log"
: > "$log_stream_stderr"
log_stream_timeout=$((10#$poll_timeout + 30))
"$timeout_runner" "$log_stream_timeout" xcrun simctl spawn "$active_udid" log stream \
    --style compact --level debug \
    --predicate "(process == \"Overte\" OR eventMessage CONTAINS \"$bundle_id\" OR eventMessage CONTAINS \"OVERTE_IOS_WORLD_GATE\" OR eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\")" \
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

launch_output="$(run_bounded "application launch" 60 xcrun simctl launch \
    "$active_udid" "$bundle_id" --url "$launch_url" --ios-world-evidence \
    --no-login-suggestion)"
[[ "$launch_output" == *":"* ]] || { echo "application launch returned no process identifier" >&2; exit 1; }
launch_pid="${launch_output##*: }"
[[ "$launch_pid" =~ ^[1-9][0-9]*$ ]] || { echo "application launch returned an invalid process identifier" >&2; exit 1; }
app_launched=1

deadline=$(( $(date +%s) + 10#$poll_timeout ))
while :; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
        echo "application process exited before the world gates were observed" >&2
        exit 1
    fi
    ready=0
    if grep -Eq 'OVERTE_IOS_WORLD_GATE[[:space:]]+navigation_requested' "$raw_log"; then
        if [[ "$scenario" == serverless ]]; then
            grep -Eq 'OVERTE_IOS_WORLD_GATE[[:space:]]+serverless_import_committed' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' "$raw_log" && ready=1
        else
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+domain_list_connected' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_server_active' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_query_sent' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_data_received' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+entity_tree_nonempty' "$raw_log" && \
            grep -Eq 'OVERTE_IOS_ENTITY_GATE[[:space:]]+render_handoff' "$raw_log" && ready=1
        fi
    fi
    ((ready)) && break
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
stop_log_stream

# Let the accepted scene transaction reach the presented framebuffer before
# capturing. The screenshot validator still rejects blank/loading-only output.
if ((10#$screenshot_settle > 0)); then
    sleep "$screenshot_settle"
fi
run_bounded "world screenshot" 30 xcrun simctl io "$active_udid" screenshot "$screenshot" >/dev/null
python3 "$screenshot_validator" "$screenshot" \
    --scenario "$scenario" --destination "$destination" --output "$screenshot_report"

validator_arguments=(
    "$raw_log" --scenario "$scenario" --destination "$destination"
    --screenshot "$screenshot" --screenshot-report "$screenshot_report" --output "$result"
)
if [[ "$scenario" == online ]]; then
    validator_arguments+=(--expected-domain "$expected_domain")
fi
python3 "$world_validator" "${validator_arguments[@]}"

run_bounded "application termination" 60 xcrun simctl terminate "$active_udid" "$bundle_id" >/dev/null
app_launched=0
run_bounded "application removal" 60 xcrun simctl uninstall "$active_udid" "$bundle_id" >/dev/null
app_installed=0
run_bounded "simulator shutdown" 60 xcrun simctl shutdown "$active_udid" >/dev/null
boot_requested=0

echo "PASS full-client $family simulator $scenario world with screenshot"
