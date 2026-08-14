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
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
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
readonly timeout_seconds="${OVERTE_MACOS_SMOKE_TIMEOUT_SECONDS:-360}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly lldb_timeout_seconds="${OVERTE_MACOS_LLDB_TIMEOUT_SECONDS:-90}"

export OVERTE_MACOS_GL_DIAGNOSTICS=1

[[ "$(uname -s)" == Darwin ]] || { echo "online smoke requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ -f "$default_scripts_override" ]] || { echo "missing default script override: $default_scripts_override" >&2; exit 1; }
mkdir -p "$output_dir"
rm -f "$snapshot" "$screenshot_result" "$entity_inventory" "$entity_validation"

readonly -a app_command=(
    "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
    --disableLocalAvatar
    --defaultScriptsOverride "file://$default_scripts_override" --url "$location"
    --testScript "$test_script" --testResultsLocation "$output_dir" --quitWhenFinished
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
for marker in domain_list_connected entity_server_active entity_query_sent entity_data_received render_handoff; do
    grep -Fq "OVERTE_MACOS_ENTITY_GATE $marker" "$log" || {
        echo "missing online runtime gate: $marker" >&2
        exit 1
    }
done
for marker in local_avatar_skipped local_avatar_scene_submission_skipped; do
    grep -Fq "OVERTE_MACOS_RENDER_PHASE $marker" "$log" || {
        echo "missing local-avatar isolation gate: $marker" >&2
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
if python3 - "$entity_inventory" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("type_counts", {}).get("Web", 0) > 0 else 1)
PY
then
    grep -Fq "OVERTE_MACOS_RENDER_PHASE web_entity_qml_paused" "$log" || {
        echo "online Web entity was not isolated from the macOS test render context" >&2
        exit 1
    }
fi
python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
    --result "$screenshot_result"

echo "macOS online smoke passed for $location"
