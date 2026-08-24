#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/tutorial-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-tutorial-smoke}"
readonly executable="$app/Contents/MacOS/Overte"
readonly location="file:///~/serverless/tutorial.json"
readonly test_script="$source_root/macos/tests/tutorial-smoke.js"
readonly log="$output_dir/tutorial.log"
readonly process_result="$output_dir/tutorial-process.json"
readonly process_sample="$output_dir/tutorial.sample.txt"
readonly crash_report="$output_dir/tutorial.crash.ips"
readonly lldb_log="$output_dir/tutorial-lldb.log"
readonly lldb_result="$output_dir/tutorial-lldb-process.json"
readonly snapshot="$output_dir/macos-tutorial-smoke.png"
readonly screenshot_result="$output_dir/tutorial-screenshot.json"
readonly entity_inventory="$output_dir/macos-tutorial-entities.json"
readonly entity_validation="$output_dir/tutorial-entity-validation.json"
readonly completion="$output_dir/macos-tutorial-smoke-completion.json"
readonly completion_validation="$output_dir/tutorial-completion-validation.json"
readonly timeout_seconds="${OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-3600}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly lldb_timeout_seconds="${OVERTE_MACOS_LLDB_TIMEOUT_SECONDS:-90}"

export OVERTE_MACOS_GL_DIAGNOSTICS=1

[[ "$(uname -s)" == Darwin ]] || { echo "tutorial smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"
rm -f "$snapshot" "$screenshot_result" "$entity_inventory" "$entity_validation" \
    "$completion" "$completion_validation"
rm -f "$process_sample" "$output_dir"/tutorial.sample.periodic-*.txt

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --url "$location" --testScript "$test_script"
    --testResultsLocation "$output_dir" --quitWhenFinished
)

set +e
python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" \
    --periodic-sample-interval 300 --periodic-sample-count 12 \
    --crash-report "$crash_report" --completion-file "$completion" \
    --completion-settle 1 -- \
    "${app_command[@]}"
status=$?
set -e

if (( status > 128 && status < 192 )); then
    if command -v lldb >/dev/null 2>&1; then
        echo "Overte exited after signal $((status - 128)); rerunning once under LLDB" >&2
        python3 "$source_root/macos/tools/run-process-with-timeout.py" \
            --timeout "$lldb_timeout_seconds" --grace "$shutdown_grace_seconds" \
            --log "$lldb_log" --result "$lldb_result" -- \
            lldb --batch -o run -k "thread backtrace all" -- "${app_command[@]}" || true
    else
        echo "LLDB unavailable; no automatic crash backtrace was captured" >&2
    fi
fi

[[ $status -eq 0 ]] || { echo "Overte supervisor exited with status $status" >&2; exit "$status"; }
python3 "$source_root/macos/tools/validate-online-smoke-completion.py" \
    "$completion" "$process_result" --result "$completion_validation"
for marker in serverless_import_committed entity_tree_nonempty render_handoff; do
    grep -Fq "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing tutorial runtime gate: $marker" >&2
        exit 1
    }
done
grep -Fq "OVERTE_MACOS_TUTORIAL passed" "$log" || {
    echo "tutorial smoke script did not pass" >&2
    exit 1
}
[[ -s "$snapshot" ]] || { echo "tutorial snapshot is missing or empty" >&2; exit 1; }
[[ -s "$entity_inventory" ]] || { echo "tutorial entity inventory is missing" >&2; exit 1; }
python3 "$source_root/macos/tools/validate-tutorial-entities.py" \
    "$entity_inventory" --result "$entity_validation"
python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
    --result "$screenshot_result" --min-nonblack-ratio 0.05 \
    --min-color-buckets 32 --max-dominant-color-ratio 0.55 \
    --min-edge-ratio 0.003

echo "macOS bundled tutorial smoke passed"
