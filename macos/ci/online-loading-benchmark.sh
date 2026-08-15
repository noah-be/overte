#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/online-loading-benchmark.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-online-loading}"
readonly executable="$app/Contents/MacOS/Overte"
readonly template="$source_root/macos/tests/online-loading-benchmark.js"
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
readonly baseline_scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly location="${OVERTE_MACOS_ONLINE_LOCATION:-hifi://overte_hub}"
readonly location_label="${OVERTE_MACOS_ONLINE_LOCATION_LABEL:-overte-hub}"
readonly concurrency_csv="${OVERTE_MACOS_ONLINE_CONCURRENCIES:-10,16}"
readonly repeats="${OVERTE_MACOS_ONLINE_REPEATS:-1}"
readonly timeout_seconds="${OVERTE_MACOS_ONLINE_LOADING_TIMEOUT_SECONDS:-420}"
readonly diagnostic_timeout_seconds="${OVERTE_MACOS_ONLINE_DIAGNOSTIC_TIMEOUT_SECONDS:-300}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"
readonly lldb_timeout_seconds="${OVERTE_MACOS_LLDB_TIMEOUT_SECONDS:-420}"

[[ "$(uname -s)" == Darwin ]] || { echo "online loading benchmark requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ "$repeats" =~ ^[1-9][0-9]*$ ]] && (( repeats <= 10 )) || {
    echo "online repeats must be in 1..10" >&2
    exit 2
}
[[ "$diagnostic_timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
    echo "diagnostic online timeout must be a positive integer" >&2
    exit 2
}

mkdir -p "$output_dir"
if [[ -n "$(find "$output_dir" -mindepth 1 -print -quit)" ]]; then
    echo "refusing to mix an online-loading benchmark with existing evidence: $output_dir" >&2
    exit 2
fi
system_profiler -json SPHardwareDataType SPDisplaysDataType > "$output_dir/hardware.json"
sw_vers > "$output_dir/macos-version.txt"
shasum -a 256 "$executable" > "$output_dir/application.sha256"

runner_class="$(python3 - "$output_dir/hardware.json" <<'PY'
import json
from pathlib import Path
import sys

text = json.dumps(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))).lower()
tokens = ("software", "paravirtual", "virtual", "swiftshader", "llvmpipe", "softpipe", "offscreen")
has_display = "spdisplays" in text or "sppci" in text or "chipset_model" in text
print("diagnostic" if not has_display or any(token in text for token in tokens) else "hardware")
PY
)"
readonly runner_class

IFS=',' read -r -a concurrencies <<< "$concurrency_csv"
(( ${#concurrencies[@]} > 0 )) || { echo "online concurrency list is empty" >&2; exit 2; }
for concurrency in "${concurrencies[@]}"; do
    [[ "$concurrency" =~ ^[1-9][0-9]*$ ]] && (( concurrency <= 64 )) || {
        echo "invalid online concurrency: $concurrency" >&2
        exit 2
    }
done
requested_concurrencies=("${concurrencies[@]}")
if [[ "$runner_class" == diagnostic ]]; then
    # A virtual software renderer cannot produce a meaningful asset/render
    # concurrency comparison and is prone to multi-minute driver compilation.
    # Retain one full-content cold/warm pair as bounded diagnostic evidence.
    concurrencies=("${concurrencies[0]}")
fi

translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')"
python3 - "$output_dir/online-loading-manifest.json" "$runner_class" "$repeats" \
    "$location_label" "$location" "$output_dir/application.sha256" "$(uname -m)" "$translated" \
    "${concurrencies[*]}" "${requested_concurrencies[*]}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

path, runner_class, repeats, label, location, app_sha_path, machine, translated, executed, requested = sys.argv[1:]
payload = {
    "schema_version": 2,
    "runner_class": runner_class,
    "repeats": int(repeats),
    "location_label": label,
    "location_sha256": hashlib.sha256(location.encode("utf-8")).hexdigest(),
    "application_sha256": Path(app_sha_path).read_text(encoding="utf-8").split()[0],
    "machine": machine,
    "translated": translated == "1",
    "executed_concurrencies": [int(value) for value in executed.split()],
    "requested_concurrencies": [int(value) for value in requested.split()],
    "public_world_informational": True,
    "navigation_after_startup": True,
}
target = Path(path)
target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(target, 0o600)
PY
location_sha256="$(python3 - "$output_dir/online-loading-manifest.json" <<'PY'
import json
from pathlib import Path
import sys

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["location_sha256"]
if not isinstance(value, str) or len(value) != 64:
    raise SystemExit("online-loading manifest has an invalid location identity")
print(value)
PY
)"
readonly location_sha256

run_case() {
    local concurrency="$1"
    local pair="$2"
    local cache_mode="$3"
    local navigation_id="c${concurrency}-p${pair}-${cache_mode}"
    local cache_dir="$output_dir/c$concurrency/pair-$pair/cache"
    local run_dir="$output_dir/c$concurrency/pair-$pair/$cache_mode"
    local generated_script="$run_dir/online-loading-script.js"
    local log="$run_dir/online-loading.log"
    local result="$run_dir/online-loading-process.json"
    local sample="$run_dir/online-loading.sample.txt"
    local crash="$run_dir/online-loading.crash.ips"
    local lldb_dir="$run_dir/lldb"
    local lldb_log="$lldb_dir/online-loading-lldb.log"
    local lldb_result="$lldb_dir/online-loading-lldb-process.json"
    local snapshot="$run_dir/macos-online-loading.png"
    local screenshot_result="$run_dir/online-loading-screenshot.json"
    local status=0
    local accepted=false
    local metrics_present=false
    local case_timeout_seconds="$timeout_seconds"
    local -a app_command
    local -a completion_args=()

    if [[ "$runner_class" == diagnostic ]]; then
        case_timeout_seconds="$diagnostic_timeout_seconds"
        completion_args=(--completion-file "$run_dir/macos-online-loading.json")
    fi

    mkdir -p "$cache_dir" "$run_dir"
    rm -f "$snapshot" "$screenshot_result" "$run_dir/macos-online-loading.json" \
        "$run_dir/online-loading-accepted"
    python3 "$source_root/macos/tools/render-online-loading-case.py" \
        --template "$template" --output "$generated_script" --cache-mode "$cache_mode" \
        --concurrency "$concurrency" --run-index "$pair" --location-label "$location_label" \
        --location-sha256 "$location_sha256" --navigation-id "$navigation_id" \
        --runner-class "$runner_class"

    app_command=(
        "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
        --disableLocalAvatar --cache "$cache_dir" --concurrent-downloads "$concurrency"
        --defaultScriptsOverride "file://$default_scripts_override" --url "file://$baseline_scene"
        --testScript "$generated_script" --testResultsLocation "$run_dir" --quitWhenFinished
    )
    set +e
    OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID="$navigation_id" \
    OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256="$location_sha256" \
    OVERTE_MACOS_ONLINE_LOADING_TARGET_URL="$location" \
    python3 "$source_root/macos/tools/run-process-with-timeout.py" \
        --timeout "$case_timeout_seconds" --grace "$shutdown_grace_seconds" \
        --log "$log" --result "$result" --sample "$sample" --crash-report "$crash" \
        "${completion_args[@]}" -- \
        "${app_command[@]}"
    status=$?
    set -e
    if (( status > 128 && status < 192 )) && [[ "$runner_class" == diagnostic ]]; then
        if command -v lldb >/dev/null 2>&1; then
            echo "online loading exited after signal $((status - 128)); rerunning once under LLDB" >&2
            mkdir -p "$lldb_dir"
            rm -f "$lldb_dir/macos-online-loading.json"
            local -a lldb_app_command=(
                "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog
                --display Desktop --disableLocalAvatar --cache "$cache_dir"
                --concurrent-downloads "$concurrency"
                --defaultScriptsOverride "file://$default_scripts_override" --url "file://$baseline_scene"
                --testScript "$generated_script" --testResultsLocation "$lldb_dir"
                --quitWhenFinished
            )
            OVERTE_MACOS_ONLINE_LOADING_NAVIGATION_ID="$navigation_id" \
            OVERTE_MACOS_ONLINE_LOADING_LOCATION_SHA256="$location_sha256" \
            OVERTE_MACOS_ONLINE_LOADING_TARGET_URL="$location" \
            python3 "$source_root/macos/tools/run-process-with-timeout.py" \
                --timeout "$lldb_timeout_seconds" --grace "$shutdown_grace_seconds" \
                --log "$lldb_log" --result "$lldb_result" \
                --completion-file "$lldb_dir/macos-online-loading.json" -- \
                lldb --batch -o run -k "thread backtrace all" -k "register read" \
                -- "${lldb_app_command[@]}" || true
        else
            echo "LLDB unavailable; no automatic online-loading crash backtrace was captured" >&2
        fi
    fi
    if (( status == 0 )) && [[ "$runner_class" != diagnostic ]]; then
        grep -Fq "OVERTE_MACOS_ONLINE_LOADING passed" "$log" || status=1
        [[ -s "$snapshot" && -s "$run_dir/macos-online-loading.json" ]] || status=1
    fi
    if (( status == 0 )) && [[ "$runner_class" == diagnostic ]]; then
        [[ -s "$run_dir/macos-online-loading.json" ]] || status=1
    fi
    if (( status == 0 )) && [[ "$runner_class" != diagnostic ]]; then
        python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
            --result "$screenshot_result" || status=$?
    fi
    if (( status == 0 )); then
        printf 'accepted\n' > "$run_dir/online-loading-accepted"
        accepted=true
    fi
    [[ -s "$run_dir/macos-online-loading.json" ]] && metrics_present=true
    python3 - "$output_dir/attempts.jsonl" "$concurrency" "$pair" "$cache_mode" "$navigation_id" "$status" \
        "$accepted" "$metrics_present" "$run_dir" <<'PY'
import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
with path.open("a", encoding="utf-8") as output:
    output.write(json.dumps({
        "concurrency": int(sys.argv[2]),
        "pair": int(sys.argv[3]),
        "cache_mode": sys.argv[4],
        "navigation_id": sys.argv[5],
        "exit_code": int(sys.argv[6]),
        "accepted": sys.argv[7] == "true",
        "metrics_present": sys.argv[8] == "true",
        "result_directory": str(Path(sys.argv[9]).relative_to(path.parent)),
    }, sort_keys=True) + "\n")
os.chmod(path, 0o600)
PY
    if (( status != 0 )); then
        echo "online loading case failed but suite continues: c$concurrency pair=$pair $cache_mode status=$status" >&2
    fi
}

for (( pair = 1; pair <= repeats; pair += 1 )); do
    if (( pair % 2 == 0 )); then
        for (( index = ${#concurrencies[@]} - 1; index >= 0; index -= 1 )); do
            concurrency="${concurrencies[index]}"
            run_case "$concurrency" "$pair" cold
            run_case "$concurrency" "$pair" warm
        done
    else
        for concurrency in "${concurrencies[@]}"; do
            # A unique cache per pair makes the first process cold for resources;
            # the immediately following process reuses that exact disk cache.
            run_case "$concurrency" "$pair" cold
            run_case "$concurrency" "$pair" warm
        done
    fi
done

python3 "$source_root/macos/tools/analyze-online-loading.py" "$output_dir" \
    --result "$output_dir/online-loading-result.json" \
    --junit "$output_dir/TEST-overte-macos-online-loading.xml" \
    --minimum-runs "$repeats"

echo "macOS online loading benchmark passed"
