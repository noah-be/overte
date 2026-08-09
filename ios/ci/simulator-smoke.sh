#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_path="${1:-}"
bundle_id="${2:-org.overte.interface.dev}"
[[ -d "$app_path" && "$app_path" == *.app ]] || {
    printf 'usage: %s APP_PATH [BUNDLE_ID]\n' "$0" >&2
    exit 2
}

select_device() {
    local family="$1"
    xcrun simctl list devices available --json \
        | python3 "$script_dir/../tools/select-simulator.py" "$family"
}

active_udid=""
cleanup() {
    if [[ -n "$active_udid" ]]; then
        xcrun simctl terminate "$active_udid" "$bundle_id" >/dev/null 2>&1 || true
        xcrun simctl shutdown "$active_udid" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

for family in iphone ipad; do
    active_udid="$(select_device "$family")"
    xcrun simctl boot "$active_udid" >/dev/null 2>&1 || true
    xcrun simctl bootstatus "$active_udid" -b
    xcrun simctl install "$active_udid" "$app_path"
    launch_output="$(xcrun simctl launch "$active_udid" "$bundle_id")"
    [[ "$launch_output" == *":"* ]] || {
        echo "unexpected launch result for $family: $launch_output" >&2
        exit 1
    }
    xcrun simctl terminate "$active_udid" "$bundle_id"
    xcrun simctl shutdown "$active_udid"
    active_udid=""
    echo "PASS $family simulator launch"
done
