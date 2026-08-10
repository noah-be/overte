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
    if [[ -n "$active_udid" ]]; then
        xcrun simctl terminate "$active_udid" "$bundle_id" >/dev/null 2>&1 || true
        xcrun simctl shutdown "$active_udid" >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap finish EXIT

for family in iphone ipad; do
    active_family="$family"
    active_udid="$(select_device "$family")"
    xcrun simctl boot "$active_udid" >/dev/null 2>&1 || true
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
    xcrun simctl spawn "$active_udid" kill -0 "$launch_pid" || {
        echo "application process did not survive launch on $family" >&2
        exit 1
    }
    xcrun simctl terminate "$active_udid" "$bundle_id"
    xcrun simctl shutdown "$active_udid"
    active_udid=""
    active_family=""
    echo "PASS $family simulator launch"
done
