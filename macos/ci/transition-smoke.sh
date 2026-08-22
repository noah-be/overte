#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/transition-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-transition}"
readonly executable="$app/Contents/MacOS/Overte"
readonly scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly test_script="$source_root/macos/tests/transition-smoke.js"
readonly log="$output_dir/transition.log"
readonly process_result="$output_dir/transition-process.json"
readonly process_sample="$output_dir/transition.sample.txt"
readonly crash_report="$output_dir/transition.crash.ips"
readonly initial_snapshot="$output_dir/macos-transition-initial.png"
readonly online_snapshot="$output_dir/macos-transition-online.png"
readonly final_snapshot="$output_dir/macos-transition-final.png"
readonly initial_result="$output_dir/transition-initial-screenshot.json"
readonly online_result="$output_dir/transition-online-screenshot.json"
readonly final_result="$output_dir/transition-final-screenshot.json"
readonly timeout_seconds="${OVERTE_MACOS_TRANSITION_TIMEOUT_SECONDS:-720}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"

[[ "$(uname -s)" == Darwin ]] || { echo "transition smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"
rm -f "$initial_snapshot" "$online_snapshot" "$final_snapshot" \
    "$initial_result" "$online_result" "$final_result"

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --url "file://$scene" --testScript "$test_script"
    --testResultsLocation "$output_dir" --quitWhenFinished
)

python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" \
    --crash-report "$crash_report" -- \
    "${app_command[@]}"

for marker in domain_list_connected entity_server_active entity_query_sent entity_data_received render_handoff; do
    grep -Fq "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing transition runtime gate: $marker" >&2
        exit 1
    }
done
awk '
    /OVERTE_MACOS_TRANSITION online_entities=/ { online_seen = 1 }
    online_seen && /OVERTE_MACOS_ENTITY_GATE serverless_import_committed/ { returned = 1 }
    END { exit returned ? 0 : 1 }
' "$log" || {
    echo "transition did not commit a new serverless generation after the online scene" >&2
    exit 1
}
for marker in initial_fixture_entities=3 online_entities= returned_fixture_entities=3; do
    grep -Fq "OVERTE_MACOS_TRANSITION $marker" "$log" || {
        echo "missing transition script gate: $marker" >&2
        exit 1
    }
done
grep -Fq "OVERTE_MACOS_TRANSITION passed serverless_online_serverless" "$log" || {
    echo "serverless/online transition script did not pass" >&2
    exit 1
}

for phase in initial final; do
    snapshot_variable="${phase}_snapshot"
    result_variable="${phase}_result"
    snapshot="${!snapshot_variable}"
    result="${!result_variable}"
    [[ -s "$snapshot" ]] || { echo "$phase transition snapshot is missing" >&2; exit 1; }
    python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
        --result "$result" --require-red-pixels 128 --require-cyan-pixels 128 \
        --require-red-left --require-cyan-right
done
[[ -s "$online_snapshot" ]] || { echo "online transition snapshot is missing" >&2; exit 1; }
python3 "$source_root/macos/tools/validate-screenshot.py" "$online_snapshot" \
    --result "$online_result"

echo "macOS serverless-online-serverless transition smoke passed"
