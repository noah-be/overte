#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

app_path="${1:-}"
bundle_id="${2:-org.overte.interface.dev}"
[[ -d "$app_path" && "$app_path" == *.app ]] || {
    printf 'usage: %s APP_PATH [BUNDLE_ID]\n' "$0" >&2
    exit 2
}

select_device() {
    local family="$1"
    xcrun simctl list devices available --json | python3 -c '
import json, sys
family = sys.argv[1].lower()
payload = json.load(sys.stdin)
for runtime, devices in sorted(payload["devices"].items(), reverse=True):
    if "iOS" not in runtime:
        continue
    for device in devices:
        if device.get("isAvailable") and family in device["name"].lower():
            print(device["udid"])
            raise SystemExit(0)
raise SystemExit(f"no available {family} simulator")
' "$family"
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

