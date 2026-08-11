#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/online-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-online-smoke}"
readonly location="${OVERTE_MACOS_ONLINE_LOCATION:-overte://welcome}"
readonly executable="$app/Contents/MacOS/Overte"
readonly test_script="$source_root/macos/tests/serverless-smoke.js"
readonly log="$output_dir/online.log"

[[ "$(uname -s)" == Darwin ]] || { echo "online smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"

set +e
"$executable" --allowMultipleInstances --no-login-suggestion --url "$location" \
    --testScript "$test_script" --testResultsLocation "$output_dir" \
    --quitWhenFinished 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e

[[ $status -eq 0 ]] || { echo "Overte exited with status $status" >&2; exit "$status"; }
for marker in domain_list_connected entity_server_active entity_query_sent entity_data_received render_handoff; do
    rg -q "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing online runtime gate: $marker" >&2
        exit 1
    }
done
rg -q "OVERTE_MACOS_SMOKE passed" "$log" || {
    echo "online smoke script did not pass" >&2
    exit 1
}

echo "macOS online smoke passed for $location"
