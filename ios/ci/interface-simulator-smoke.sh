#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
readonly simulator_selector="$script_dir/../tools/select-simulator.py"
readonly gate_validator="$script_dir/../tools/validate-entity-gate-log.py"
readonly destination="hifi://overte_hub"

app_path="${1:-}"
bundle_id="${2:-}"
family="${3:-}"
output_dir="${4:-}"
poll_timeout="${OVERTE_IOS_INTERFACE_SMOKE_TIMEOUT_SECONDS:-180}"
poll_interval="${OVERTE_IOS_INTERFACE_SMOKE_POLL_SECONDS:-2}"

[[ -d "$app_path" && "$app_path" == *.app ]] || {
    echo "usage: $0 APP_PATH BUNDLE_ID iphone|ipad OUTPUT_DIR" >&2
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
[[ -n "$output_dir" ]] || {
    echo "output directory is required" >&2
    exit 2
}
[[ "$poll_timeout" =~ ^[1-9][0-9]*$ ]] && ((10#$poll_timeout <= 900)) || {
    echo "OVERTE_IOS_INTERFACE_SMOKE_TIMEOUT_SECONDS must be an integer from 1 through 900" >&2
    exit 2
}
[[ "$poll_interval" =~ ^[1-9][0-9]*$ ]] && ((10#$poll_interval <= 30)) || {
    echo "OVERTE_IOS_INTERFACE_SMOKE_POLL_SECONDS must be an integer from 1 through 30" >&2
    exit 2
}
[[ -x "$timeout_runner" && -f "$simulator_selector" && -f "$gate_validator" ]] || {
    echo "iOS simulator test helpers are unavailable" >&2
    exit 2
}

mkdir -p "$output_dir"
readonly evidence="$output_dir/${family}-entity-gates.json"
readonly failure_screenshot="$output_dir/${family}-failure.png"
# Every invocation must produce its own verdict. Never let evidence or a
# screenshot from an earlier attempt masquerade as this run's result.
rm -f "$evidence" "$failure_screenshot"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/overte-ios-interface-smoke.XXXXXX")"
[[ -d "$temp_root" && "$temp_root" == */overte-ios-interface-smoke.* ]] || {
    echo "could not create bounded simulator workspace" >&2
    exit 2
}
readonly temp_root
readonly device_list="$temp_root/devices.json"
readonly raw_log="$temp_root/process.log"
readonly candidate_report="$temp_root/entity-gates.json"
readonly command_stderr="$temp_root/command.stderr"

active_udid=""
boot_requested=0
app_launched=0
app_installed=0

# The timeout helper prints the full child command on timeout. Capture that
# private diagnostic and expose only a fixed phase label so app paths, launch
# arguments, and future credentials can never reach CI output.
run_bounded() {
    local label="$1"
    local seconds="$2"
    local status=0
    shift 2
    : > "$command_stderr"
    "$timeout_runner" "$seconds" "$@" 2>"$command_stderr" || status=$?
    rm -f "$command_stderr"
    if ((status != 0)); then
        echo "$label failed with status $status" >&2
    fi
    return "$status"
}

finish() {
    local status=$?
    trap - EXIT
    if ((status != 0)) && [[ -n "$active_udid" ]]; then
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
        run_bounded "simulator cleanup" 60 xcrun simctl shutdown \
            "$active_udid" >/dev/null || true
    fi
    # Raw process output is validation input only. The canonical validator
    # report is the sole retained log evidence.
    rm -f "$raw_log" "$candidate_report" "$command_stderr" "$device_list"
    rm -rf "$temp_root"
    exit "$status"
}
trap finish EXIT

run_bounded "simulator discovery" 60 xcrun simctl list devices available --json > "$device_list"
active_udid="$(python3 "$simulator_selector" "$family" < "$device_list")"
[[ -n "$active_udid" ]] || {
    echo "simulator selection returned no device" >&2
    exit 1
}

boot_requested=1
boot_status=0
run_bounded "simulator boot request" 60 xcrun simctl boot "$active_udid" \
    >/dev/null || boot_status=$?
if ((boot_status == 124 || boot_status >= 128)); then
    exit "$boot_status"
fi
# A non-zero request can mean the selected simulator was already booted. The
# bounded bootstatus call is the authoritative readiness check.
run_bounded "simulator boot" 1500 xcrun simctl bootstatus "$active_udid" -b >/dev/null

# A prior installation must not leak settings, cached domains, or a previous
# process into this acceptance run. A failed uninstall is harmless only when
# simctl also proves that no matching app container exists.
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

log_start="$(date -u '+%Y-%m-%d %H:%M:%S')"
launch_output="$(run_bounded "application launch" 60 xcrun simctl launch \
    "$active_udid" "$bundle_id")"
[[ "$launch_output" == *":"* ]] || {
    echo "application launch returned no process identifier" >&2
    exit 1
}
launch_pid="${launch_output##*: }"
[[ "$launch_pid" =~ ^[1-9][0-9]*$ ]] || {
    echo "application launch returned an invalid process identifier" >&2
    exit 1
}
app_launched=1

run_bounded "deep-link delivery" 60 xcrun simctl openurl \
    "$active_udid" "$destination" >/dev/null

deadline=$(( $(date +%s) + 10#$poll_timeout ))
while :; do
    : > "$raw_log"
    # Query only this launch PID and only records created after this launch.
    # Never print or retain the raw unified log.
    run_bounded "process log query" 30 xcrun simctl spawn "$active_udid" log show \
        --style compact --start "$log_start" \
        --predicate "processIdentifier == $launch_pid AND eventMessage CONTAINS \"OVERTE_IOS_ENTITY_GATE\"" \
        > "$raw_log"

    rm -f "$candidate_report"
    validator_status=0
    python3 "$gate_validator" "$raw_log" --output "$candidate_report" \
        >/dev/null 2>&1 || validator_status=$?
    if ((validator_status == 0)); then
        install -m 0644 "$candidate_report" "$evidence"
        break
    fi

    report_state="$(python3 - "$candidate_report" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
errors = report.get("errors", [])
print("incomplete" if len(errors) == 1 and errors[0].startswith("missing gate ") else "invalid")
PY
)"
    if [[ "$report_state" != incomplete ]]; then
        install -m 0644 "$candidate_report" "$evidence"
        echo "entity gate telemetry was invalid" >&2
        exit 1
    fi
    if (( $(date +%s) >= deadline )); then
        install -m 0644 "$candidate_report" "$evidence"
        echo "entity gate telemetry timed out" >&2
        exit 124
    fi
    sleep "$poll_interval"
done

# Successful termination proves that the process which emitted the accepted
# gates was still alive after the final render handoff.
run_bounded "application termination" 60 xcrun simctl terminate \
    "$active_udid" "$bundle_id" >/dev/null
app_launched=0
run_bounded "application removal" 60 xcrun simctl uninstall \
    "$active_udid" "$bundle_id" >/dev/null
app_installed=0
run_bounded "simulator shutdown" 60 xcrun simctl shutdown "$active_udid" >/dev/null
boot_requested=0

echo "PASS full-client $family simulator entity runtime"
