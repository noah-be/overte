#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/serverless-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-smoke}"
readonly executable="$app/Contents/MacOS/Overte"
readonly scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly test_script="$source_root/macos/tests/serverless-smoke.js"
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
readonly log="$output_dir/serverless.log"
readonly process_result="$output_dir/serverless-process.json"
readonly process_sample="$output_dir/serverless.sample.txt"
readonly crash_report="$output_dir/serverless.crash.ips"
readonly lldb_log="$output_dir/serverless-lldb.log"
readonly lldb_result="$output_dir/serverless-lldb-process.json"
readonly snapshot="$output_dir/macos-serverless-smoke.png"
readonly timeout_seconds="${OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-360}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly lldb_timeout_seconds="${OVERTE_MACOS_LLDB_TIMEOUT_SECONDS:-90}"

export OVERTE_MACOS_GL_DIAGNOSTICS=1
export QT_LOGGING_RULES="${QT_LOGGING_RULES:+${QT_LOGGING_RULES};}hifi.gpu.gl41.info=true"

[[ "$(uname -s)" == Darwin ]] || { echo "serverless smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ -f "$scene" ]] || { echo "missing scene fixture: $scene" >&2; exit 1; }
[[ -f "$default_scripts_override" ]] || { echo "missing default script override: $default_scripts_override" >&2; exit 1; }
mkdir -p "$output_dir"

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --defaultScriptsOverride "file://$default_scripts_override"
    --url "file://$scene" --testScript "$test_script"
    --testResultsLocation "$output_dir" --quitWhenFinished
)

set +e
python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" \
    --crash-report "$crash_report" -- \
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
[[ -s "$snapshot" ]] || { echo "serverless snapshot is missing or empty" >&2; exit 1; }
readonly snapshot_width="$(sips -g pixelWidth "$snapshot" | awk '/pixelWidth:/ { print $2 }')"
readonly snapshot_height="$(sips -g pixelHeight "$snapshot" | awk '/pixelHeight:/ { print $2 }')"
(( snapshot_width > 0 && snapshot_height > 0 )) || {
    echo "serverless snapshot has invalid dimensions" >&2; exit 1;
}

echo "macOS serverless smoke passed"
