#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/serverless-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-smoke}"
readonly executable="$app/Contents/MacOS/Overte"
readonly scene="$source_root/interface/resources/serverless/tutorial.json"
readonly test_script="$source_root/macos/tests/serverless-smoke.js"
readonly log="$output_dir/serverless.log"

[[ "$(uname -s)" == Darwin ]] || { echo "serverless smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ -f "$scene" ]] || { echo "missing scene fixture: $scene" >&2; exit 1; }
mkdir -p "$output_dir"

set +e
"$executable" --allowMultipleInstances --no-login-suggestion \
    --url "file://$scene" --testScript "$test_script" \
    --testResultsLocation "$output_dir" --quitWhenFinished 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e

[[ $status -eq 0 ]] || { echo "Overte exited with status $status" >&2; exit "$status"; }
for marker in serverless_import_committed entity_tree_nonempty render_handoff; do
    rg -q "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing runtime gate: $marker" >&2
        exit 1
    }
done
rg -q "OVERTE_MACOS_SMOKE passed" "$log" || {
    echo "serverless smoke script did not pass" >&2
    exit 1
}

echo "macOS serverless smoke passed"
