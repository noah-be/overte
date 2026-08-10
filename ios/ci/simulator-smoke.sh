#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_path="${1:-}"
bundle_id="${2:-org.overte.interface.dev}"
diagnostics_dir="${3:-}"
[[ -d "$app_path" && "$app_path" == *.app ]] || {
    printf 'usage: %s APP_PATH [BUNDLE_ID] [DIAGNOSTICS_DIR]\n' "$0" >&2
    exit 2
}

select_device() {
    local family="$1"
    xcrun simctl list devices available --json \
        | python3 "$script_dir/../tools/select-simulator.py" "$family"
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
        xcrun simctl io "$active_udid" screenshot \
            "$diagnostics_dir/${active_family:-simulator}-failure.png" >/dev/null 2>&1 || true
        xcrun simctl spawn "$active_udid" log show --style compact --last 5m \
            --predicate "process == 'OverteIOSBootstrap'" \
            >"$diagnostics_dir/${active_family:-simulator}-console.log" 2>&1 || true
    fi
    for cleanup_udid in "$iphone_udid" "$ipad_udid"; do
        [[ -n "$cleanup_udid" ]] || continue
        xcrun simctl terminate "$cleanup_udid" "$bundle_id" >/dev/null 2>&1 || true
        xcrun simctl shutdown "$cleanup_udid" >/dev/null 2>&1 || true
    done
    exit "$status"
}
trap finish EXIT

iphone_udid="$(select_device iphone)"
ipad_udid="$(select_device ipad)"
[[ "$iphone_udid" != "$ipad_udid" ]] || {
    echo "simulator selector returned one device for both form factors" >&2
    exit 1
}

# Start both first boots together: fresh hosted runners otherwise spend several
# minutes performing the same runtime migration serially for each form factor.
for boot_udid in "$iphone_udid" "$ipad_udid"; do
    xcrun simctl boot "$boot_udid" >/dev/null 2>&1 || true
done

for family in iphone ipad; do
    active_family="$family"
    if [[ "$family" == "iphone" ]]; then
        active_udid="$iphone_udid"
    else
        active_udid="$ipad_udid"
    fi
    xcrun simctl bootstatus "$active_udid" -b
    xcrun simctl install "$active_udid" "$app_path"
    launch_output="$(xcrun simctl launch "$active_udid" "$bundle_id")"
    [[ "$launch_output" == *":"* ]] || {
        echo "unexpected launch result for $family: $launch_output" >&2
        exit 1
    }
    launch_pid="${launch_output##*: }"
    [[ "$launch_pid" =~ ^[0-9]+$ ]] || {
        echo "launch did not return a process ID for $family: $launch_output" >&2
        exit 1
    }
    sleep 5
    # A successful terminate after the grace period proves that the launched
    # application is still registered and running. Minimal simulator runtimes
    # do not necessarily ship a standalone `kill` executable.
    xcrun simctl terminate "$active_udid" "$bundle_id"
    xcrun simctl shutdown "$active_udid"
    active_udid=""
    active_family=""
    echo "PASS $family simulator launch"
done
