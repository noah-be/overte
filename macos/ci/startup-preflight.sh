#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/startup-preflight.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-startup-preflight}"
readonly executable="$app/Contents/MacOS/Overte"
readonly log="$output_dir/startup.log"
readonly process_result="$output_dir/startup-process.json"
readonly process_sample="$output_dir/startup.sample.txt"
readonly timeout_seconds="${OVERTE_MACOS_STARTUP_TIMEOUT_SECONDS:-30}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"

[[ "$(uname -s)" == Darwin ]] || { echo "startup preflight requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"

set +e
python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" -- \
    "$executable" --allowMultipleInstances --abortAfterStartup
status=$?
set -e

[[ $status -eq 99 ]] || {
    echo "startup preflight expected exit 99 but received $status" >&2
    exit 1
}

echo "macOS startup preflight passed"
