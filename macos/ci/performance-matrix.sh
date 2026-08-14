#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly app="${1:?usage: macos/ci/performance-matrix.sh /path/to/Overte.app [output-directory]}"
readonly output_dir="${2:-$source_root/build/macos-performance-matrix}"
readonly executable="$app/Contents/MacOS/Overte"
readonly profiles_file="$source_root/macos/tests/performance-profiles.json"
readonly template="$source_root/macos/tests/profile-performance-smoke.js"
readonly scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
readonly mode="${OVERTE_MACOS_PROFILE_MATRIX_MODE:-quick}"
readonly repeats="${OVERTE_MACOS_PROFILE_REPEATS:-1}"
readonly timeout_seconds="${OVERTE_MACOS_PROFILE_TIMEOUT_SECONDS:-300}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"

[[ "$(uname -s)" == Darwin ]] || { echo "performance matrix requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ "$mode" == quick || "$mode" == full ]] || { echo "matrix mode must be quick or full" >&2; exit 2; }
[[ "$repeats" =~ ^[1-9][0-9]*$ ]] && (( repeats <= 10 )) || {
    echo "profile repeats must be in 1..10" >&2
    exit 2
}

mkdir -p "$output_dir"
rm -f "$output_dir/matrix-result.json" "$output_dir/TEST-overte-macos-performance-matrix.xml"
system_profiler -json SPHardwareDataType SPDisplaysDataType > "$output_dir/hardware.json"
sw_vers > "$output_dir/macos-version.txt"
uname -a > "$output_dir/kernel.txt"
shasum -a 256 "$executable" > "$output_dir/application.sha256"

profiles=()
while IFS= read -r profile; do
    profiles+=("$profile")
done < <(python3 - "$profiles_file" "$mode" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for identifier in payload[f"{sys.argv[2]}_order"]:
    print(identifier)
PY
)
(( ${#profiles[@]} > 0 )) || { echo "profile order is empty" >&2; exit 2; }

run_case() {
    local profile="$1"
    local label="$2"
    local run_index="$3"
    local run_dir="$output_dir/$profile/$label"
    local generated_script="$run_dir/profile-script.js"
    local trace="$run_dir/profile-trace.json.gz"
    local log="$run_dir/profile.log"
    local process_result="$run_dir/profile-process.json"
    local sample="$run_dir/profile.sample.txt"
    local crash_report="$run_dir/profile.crash.ips"
    local snapshot="$run_dir/macos-profile.png"
    local screenshot_result="$run_dir/profile-screenshot.json"
    local status=0

    mkdir -p "$run_dir" "$output_dir/cache/$profile"
    rm -f "$snapshot" "$screenshot_result" "$run_dir/macos-profile.json"
    python3 "$source_root/macos/tools/render-performance-profile.py" \
        --profiles "$profiles_file" --profile "$profile" --template "$template" \
        --output "$generated_script" --trace "$trace" --run-index "$run_index"

    local -a app_command=(
        "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
        --disableLocalAvatar --cache "$output_dir/cache/$profile"
        --defaultScriptsOverride "file://$default_scripts_override"
        --url "file://$scene" --testScript "$generated_script"
        --testResultsLocation "$run_dir" --quitWhenFinished
    )

    set +e
    python3 "$source_root/macos/tools/run-process-with-timeout.py" \
        --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
        --log "$log" --result "$process_result" --sample "$sample" \
        --crash-report "$crash_report" -- \
        "${app_command[@]}"
    status=$?
    set -e

    if (( status == 0 )); then
        grep -Fq "OVERTE_MACOS_PROFILE passed id=$profile" "$log" || status=1
        [[ -s "$snapshot" && -s "$run_dir/macos-profile.json" ]] || status=1
    fi
    if (( status == 0 )); then
        python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
            --result "$screenshot_result" || status=$?
    fi
    python3 - "$output_dir/attempts.jsonl" "$profile" "$label" "$run_index" "$status" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
with path.open("a", encoding="utf-8") as output:
    output.write(json.dumps({
        "profile": sys.argv[2],
        "label": sys.argv[3],
        "run_index": int(sys.argv[4]),
        "exit_code": int(sys.argv[5]),
    }, sort_keys=True) + "\n")
PY
    if (( status != 0 )); then
        echo "profile case failed but matrix continues: $profile/$label status=$status" >&2
    fi
    return 0
}

# Each profile gets a throwaway process so shader/resource first-use costs do
# not contaminate the repeated steady-state measurements. The actual runs are
# interleaved by repeat number to reduce runner drift bias.
for profile in "${profiles[@]}"; do
    run_case "$profile" warmup 1
done
for (( repeat = 1; repeat <= repeats; repeat += 1 )); do
    for profile in "${profiles[@]}"; do
        run_case "$profile" "run-$repeat" "$((repeat + 1))"
    done
done

python3 "$source_root/macos/tools/analyze-performance-matrix.py" "$output_dir" \
    --result "$output_dir/matrix-result.json" \
    --junit "$output_dir/TEST-overte-macos-performance-matrix.xml" \
    --minimum-runs "$repeats"

echo "macOS performance matrix passed"
