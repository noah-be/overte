#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/performance-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-performance}"
readonly executable="$app/Contents/MacOS/Overte"
readonly scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly test_script="$source_root/macos/tests/performance-smoke.js"
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
readonly log="$output_dir/performance.log"
readonly process_result="$output_dir/performance-process.json"
readonly process_sample="$output_dir/performance.sample.txt"
readonly crash_report="$output_dir/performance.crash.ips"
readonly snapshot="$output_dir/macos-performance-warmup.png"
readonly screenshot_result="$output_dir/performance-screenshot.json"
readonly metrics="$output_dir/macos-performance.json"
readonly validation="$output_dir/performance-validation.json"
readonly junit="$output_dir/TEST-overte-macos-performance.xml"
readonly timeout_seconds="${OVERTE_MACOS_PERFORMANCE_TIMEOUT_SECONDS:-360}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly minimum_samples="${OVERTE_MACOS_PERFORMANCE_MINIMUM_SAMPLES:-30}"
readonly maximum_p95_ms="${OVERTE_MACOS_PERFORMANCE_MAXIMUM_P95_MS:-}"

[[ "$(uname -s)" == Darwin ]] || { echo "performance smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"
rm -f "$snapshot" "$screenshot_result" "$metrics" "$validation" "$junit"

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --disableLocalAvatar
    --defaultScriptsOverride "file://$default_scripts_override"
    --url "file://$scene" --testScript "$test_script"
    --testResultsLocation "$output_dir" --quitWhenFinished
)

python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" \
    --crash-report "$crash_report" -- \
    "${app_command[@]}"

for marker in serverless_import_committed entity_tree_nonempty render_handoff; do
    grep -Fq "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing performance runtime gate: $marker" >&2
        exit 1
    }
done
grep -Fq "OVERTE_MACOS_PERFORMANCE passed" "$log" || {
    echo "performance script did not pass" >&2
    exit 1
}
[[ -s "$snapshot" ]] || { echo "performance warmup snapshot is missing" >&2; exit 1; }
[[ -s "$metrics" ]] || { echo "performance metrics are missing" >&2; exit 1; }
python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
    --result "$screenshot_result" --require-red-pixels 128 --require-cyan-pixels 128 \
    --require-red-left --require-cyan-right

validator=(
    python3 "$source_root/macos/tools/validate-performance.py" "$metrics"
    --result "$validation" --junit "$junit" --minimum-samples "$minimum_samples"
)
if [[ -n "$maximum_p95_ms" ]]; then
    validator+=(--maximum-p95-ms "$maximum_p95_ms")
fi
"${validator[@]}"

echo "macOS performance smoke passed"
