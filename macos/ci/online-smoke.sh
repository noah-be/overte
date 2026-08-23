#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/online-smoke.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-online-smoke}"
# The user-facing product is Overte, but the on-wire/navigation URL scheme is
# intentionally still "hifi" for protocol compatibility (URL_SCHEME_OVERTE).
readonly location="${OVERTE_MACOS_ONLINE_LOCATION:-hifi://overte_hub}"
readonly executable="$app/Contents/MacOS/Overte"
readonly test_script="$source_root/macos/tests/online-smoke.js"
readonly log="$output_dir/online.log"
readonly process_result="$output_dir/online-process.json"
readonly process_sample="$output_dir/online.sample.txt"
readonly crash_report="$output_dir/online.crash.ips"
readonly lldb_log="$output_dir/online-lldb.log"
readonly lldb_result="$output_dir/online-lldb-process.json"
readonly snapshot="$output_dir/macos-online-smoke.png"
readonly screenshot_result="$output_dir/online-screenshot.json"
readonly entity_inventory="$output_dir/macos-online-entities.json"
readonly entity_validation="$output_dir/online-entity-validation.json"
readonly completion="$output_dir/macos-online-smoke-completion.json"
readonly completion_validation="$output_dir/online-completion-validation.json"
readonly runtime_diagnostics="$output_dir/runtime-diagnostics"
readonly timeline="$output_dir/online-diagnostic-timeline.json"
readonly timeout_seconds="${OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-2400}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly lldb_timeout_seconds="${OVERTE_MACOS_LLDB_TIMEOUT_SECONDS:-90}"

export OVERTE_MACOS_GL_DIAGNOSTICS=1

[[ "$(uname -s)" == Darwin ]] || { echo "online smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
mkdir -p "$output_dir"
rm -f "$snapshot" "$screenshot_result" "$entity_inventory" "$entity_validation" \
    "$completion" "$completion_validation" "$timeline"
mkdir -p "$runtime_diagnostics"

observer_pid=""
stop_observer() {
    if [[ -n "$observer_pid" ]] && kill -0 "$observer_pid" 2>/dev/null; then
        kill -TERM "$observer_pid" 2>/dev/null || true
        wait "$observer_pid" 2>/dev/null || true
    fi
    observer_pid=""
}
trap stop_observer EXIT

python3 "$source_root/macos/tools/observe-online-runtime.py" \
    --log "$log" --output-dir "$runtime_diagnostics" \
    --max-runtime "$((timeout_seconds + shutdown_grace_seconds + 60))" &
observer_pid=$!

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --url "$location"
    --testScript "$test_script" --testResultsLocation "$output_dir" --quitWhenFinished
)

set +e
python3 "$source_root/macos/tools/run-process-with-timeout.py" \
    --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
    --log "$log" --result "$process_result" --sample "$process_sample" \
    --crash-report "$crash_report" --completion-file "$completion" \
    --completion-settle 1 -- \
    "${app_command[@]}"
status=$?
set -e
stop_observer
trap - EXIT

python3 "$source_root/macos/tools/analyze-online-smoke-log.py" \
    "$log" --process "$process_result" \
    --udp-headers "$runtime_diagnostics/udp-headers.log" --result "$timeline" || {
        echo "online postmortem analysis failed; preserving raw diagnostics" >&2
    }

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
for marker in domain_list_connected entity_server_active entity_query_sent entity_data_received entity_tree_nonempty render_handoff; do
    grep -Fq "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing online runtime gate: $marker" >&2
        exit 1
    }
done
grep -Fq "OVERTE_MACOS_SMOKE passed" "$log" || {
    echo "online smoke script did not pass" >&2
    exit 1
}
[[ -s "$snapshot" ]] || { echo "online snapshot is missing or empty" >&2; exit 1; }
[[ -s "$entity_inventory" ]] || { echo "online entity inventory is missing" >&2; exit 1; }
render_handoff_id="$(sed -nE 's/.*OVERTE_MACOS_ENTITY_GATE render_handoff entity= \{([^}]*)\}.*/\1/p' "$log" | tail -n 1)"
[[ -n "$render_handoff_id" ]] || { echo "online render-handoff entity ID is missing" >&2; exit 1; }
python3 "$source_root/macos/tools/validate-online-entities.py" "$entity_inventory" \
    --render-handoff-id "$render_handoff_id" --result "$entity_validation"
python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
    --result "$screenshot_result" --min-color-buckets 16 \
    --max-dominant-color-ratio 0.55 --min-edge-ratio 0.003

echo "macOS online smoke passed for $location"
