#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# Prepares receive-only permission lifecycle evidence on an already-created iOS
# simulator. This cannot prove microphone capture, routing, AEC, or latency.
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: $0 APP_PATH BUNDLE_ID SIMULATOR_UDID OUTPUT_DIR" >&2
    exit 2
fi

readonly app_path="$1"
readonly bundle_id="$2"
readonly simulator_udid="$3"
readonly output_dir="$4"
readonly wait_seconds="${OVERTE_IOS_AUDIO_SIMULATOR_WAIT_SECONDS:-3}"

[[ -d "$app_path" ]] || { echo "APP_PATH is not an app directory" >&2; exit 2; }
[[ "$wait_seconds" =~ ^[1-9][0-9]*$ ]] || { echo "wait duration must be a positive integer" >&2; exit 2; }
mkdir -p "$output_dir"

cleanup() {
    xcrun simctl terminate "$simulator_udid" "$bundle_id" >/dev/null 2>&1 || true
}
trap cleanup EXIT

xcrun simctl boot "$simulator_udid" >/dev/null 2>&1 || true
xcrun simctl bootstatus "$simulator_udid" -b
xcrun simctl install "$simulator_udid" "$app_path"

run_phase() {
    local phase="$1"
    local privacy_action="$2"
    local raw_log
    raw_log="$(mktemp "${TMPDIR:-/tmp}/overte-ios-audio-sim.XXXXXX")"
    xcrun simctl terminate "$simulator_udid" "$bundle_id" >/dev/null 2>&1 || true
    xcrun simctl privacy "$simulator_udid" "$privacy_action" microphone "$bundle_id"
    local launch_output
    launch_output="$(xcrun simctl launch "$simulator_udid" "$bundle_id")"
    local process_id="${launch_output##*: }"
    [[ "$process_id" =~ ^[0-9]+$ ]] || { echo "simulator launch did not return a process id" >&2; exit 1; }
    sleep "$wait_seconds"
    xcrun simctl spawn "$simulator_udid" log show --style compact --last 2m \
        --predicate "processIdentifier == $process_id AND (eventMessage CONTAINS 'Audio lifecycle state=' OR eventMessage CONTAINS 'iOS microphone permission state=' OR eventMessage CONTAINS 'Overte full-client audio session activation=')" \
        >"$raw_log"
    grep -E "Audio lifecycle state=|iOS microphone permission state=|Overte full-client audio session activation=" \
        "$raw_log" >"$output_dir/$phase.log" || true
    rm -f "$raw_log"
    [[ -s "$output_dir/$phase.log" ]] || { echo "missing sanitized audio markers for $phase" >&2; exit 1; }
}

run_phase denied revoke
run_phase granted grant
xcrun simctl privacy "$simulator_udid" reset microphone "$bundle_id"

python3 - "$output_dir/result.json" <<'PY'
import json
import sys
from pathlib import Path

target = Path(sys.argv[1])
target.write_text(json.dumps({
    "schemaVersion": 1,
    "status": "simulator-permission-precheck-passed",
    "physicalAudioValidated": False,
    "phases": ["denied", "granted"],
}, indent=2) + "\n", encoding="utf-8")
PY

echo "PASS iOS simulator audio permission precheck (not physical audio validation)"
