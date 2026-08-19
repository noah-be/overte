#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
app_path="${1:-}"
bundle_id="${2:-org.overte.bootstrap.dev}"
diagnostics_dir="${3:-}"
grace_seconds="${OVERTE_IOS_SIMULATOR_GRACE_SECONDS:-5}"
[[ -d "$app_path" && "$app_path" == *.app ]] || {
    printf 'usage: %s APP_PATH [BUNDLE_ID] [DIAGNOSTICS_DIR]\n' "$0" >&2
    exit 2
}
[[ "$grace_seconds" =~ ^[0-9]+$ ]] || {
    echo "OVERTE_IOS_SIMULATOR_GRACE_SECONDS must contain seconds as digits" >&2
    exit 2
}

run_timed() {
    local label="$1"
    local timeout="$2"
    local started status elapsed
    shift 2
    started="$(date +%s)"
    printf '[%s] START %s (timeout=%ss)\n' "$(date -u +%FT%TZ)" "$label" "$timeout" >&2
    if "$timeout_runner" "$timeout" "$@"; then
        status=0
    else
        status=$?
    fi
    elapsed=$(( $(date +%s) - started ))
    printf '[%s] END %s status=%s elapsed=%ss\n' \
        "$(date -u +%FT%TZ)" "$label" "$status" "$elapsed" >&2
    return "$status"
}

device_list="$(mktemp)"
select_device() {
    local family="$1"
    python3 "$script_dir/../tools/select-simulator.py" "$family" < "$device_list"
}

active_udid=""
active_family=""
iphone_udid=""
ipad_udid=""
finish() {
    local status=$?
    trap - EXIT
    if ((status != 0)) && [[ -n "$active_udid" && -n "$diagnostics_dir" ]]; then
        mkdir -p "$diagnostics_dir"
        run_timed "diagnostic screenshot $active_family" 30 xcrun simctl io "$active_udid" screenshot \
            "$diagnostics_dir/${active_family:-simulator}-failure.png" >/dev/null 2>&1 || true
        run_timed "diagnostic log $active_family" 30 xcrun simctl spawn "$active_udid" log show --style compact --last 5m \
            --predicate "process == 'OverteIOSBootstrap'" \
            >"$diagnostics_dir/${active_family:-simulator}-console.log" 2>&1 || true
    fi
    if [[ -n "$active_udid" ]]; then
        run_timed "cleanup terminate $active_family" 60 xcrun simctl terminate "$active_udid" "$bundle_id" >/dev/null 2>&1 || true
    fi
    [[ -z "$iphone_udid" ]] || run_timed "cleanup shutdown iphone" 45 xcrun simctl shutdown "$iphone_udid" >/dev/null 2>&1 || true
    [[ -z "$ipad_udid" ]] || run_timed "cleanup shutdown ipad" 45 xcrun simctl shutdown "$ipad_udid" >/dev/null 2>&1 || true
    rm -f "$device_list"
    exit "$status"
}
trap finish EXIT

run_timed "list available simulators" 60 xcrun simctl list devices available --json > "$device_list"
iphone_udid="$(select_device iphone)"
ipad_udid="$(select_device ipad)"

# Start both boots before waiting for either runtime. This overlaps the iPad
# boot with the full iPhone smoke without running two app tests concurrently.
request_boot() {
    local family="$1"
    local udid="$2"
    local status=0
    run_timed "request $family boot" 60 xcrun simctl boot "$udid" >/dev/null 2>&1 || status=$?
    if ((status == 124 || status >= 128)); then
        echo "$family boot request timed out or was interrupted" >&2
        return "$status"
    fi
    if ((status != 0)); then
        echo "$family boot request returned $status; bootstatus will verify an already-booted device" >&2
    fi
}
request_boot iphone "$iphone_udid"
request_boot ipad "$ipad_udid"

for family in iphone ipad; do
    active_family="$family"
    if [[ "$family" == "iphone" ]]; then
        active_udid="$iphone_udid"
    else
        active_udid="$ipad_udid"
    fi
    run_timed "wait for $family boot" 1500 xcrun simctl bootstatus "$active_udid" -b
    run_timed "install on $family" 90 xcrun simctl install "$active_udid" "$app_path"
    launch_output="$(run_timed "launch on $family" 60 xcrun simctl launch "$active_udid" "$bundle_id")"
    [[ "$launch_output" == *":"* ]] || {
        echo "unexpected launch result for $family: $launch_output" >&2
        exit 1
    }
    launch_pid="${launch_output##*: }"
    [[ "$launch_pid" =~ ^[0-9]+$ ]] || {
        echo "launch did not return a process ID for $family: $launch_output" >&2
        exit 1
    }
    run_timed "open deep link on $family" 60 xcrun simctl openurl "$active_udid" "hifi://overte_hub"
    sleep "$grace_seconds"
    # A successful terminate after the grace period proves that the launched
    # application is still registered and running. Minimal simulator runtimes
    # do not necessarily ship a standalone `kill` executable.
    run_timed "terminate on $family" 60 xcrun simctl terminate "$active_udid" "$bundle_id"
    active_udid=""
    active_family=""
    echo "PASS $family simulator launch"
done

# Both application tests have completed. Shutdown is independent and can run
# concurrently, while each command remains individually bounded.
run_timed "shutdown iphone" 240 xcrun simctl shutdown "$iphone_udid" &
iphone_shutdown_pid=$!
run_timed "shutdown ipad" 240 xcrun simctl shutdown "$ipad_udid" &
ipad_shutdown_pid=$!
# Do not retry these acceptance shutdowns serially in the EXIT trap. Each one
# is already bounded and its result is collected below.
iphone_udid=""
ipad_udid=""
shutdown_status=0
wait "$iphone_shutdown_pid" || shutdown_status=$?
wait "$ipad_shutdown_pid" || shutdown_status=$?
((shutdown_status == 0)) || exit "$shutdown_status"
