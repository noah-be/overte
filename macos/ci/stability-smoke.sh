#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/stability-smoke.sh /path/to/Overte.app [output-directory] [iterations]}"
readonly output_dir="${2:-$source_root/build/macos-stability}"
readonly iterations="${3:-3}"

[[ "$(uname -s)" == Darwin ]] || { echo "stability smoke requires macOS" >&2; exit 1; }
[[ "$iterations" =~ ^[1-9][0-9]*$ ]] && (( iterations <= 20 )) || {
    echo "stability iterations must be between 1 and 20" >&2
    exit 2
}
mkdir -p "$output_dir"

for (( iteration = 1; iteration <= iterations; ++iteration )); do
    run_name="$(printf 'run-%02d' "$iteration")"
    run_dir="$output_dir/$run_name"
    [[ ! -e "$run_dir" ]] || {
        echo "refusing to reuse existing stability evidence: $run_name" >&2
        exit 2
    }
    echo "macOS stability cycle $iteration/$iterations: $run_name"
    set +e
    "$source_root/macos/ci/serverless-smoke.sh" "$app" "$run_dir"
    status=$?
    set -e
    echo "macOS stability cycle $iteration/$iterations exited with status $status"
done

python3 "$source_root/macos/tools/validate-stability.py" "$output_dir" \
    --iterations "$iterations" \
    --result "$output_dir/stability-summary.json" \
    --junit "$output_dir/TEST-overte-macos-stability.xml"

echo "macOS stability smoke passed $iterations/$iterations cycles"
