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
readonly procedural_shader="$source_root/macos/tests/fixtures/profile-procedural.fs"
readonly scene="$source_root/macos/tests/fixtures/serverless-render.json"
readonly default_scripts_override="$source_root/macos/tests/fixtures/no-default-scripts.js"
readonly mode="${OVERTE_MACOS_PROFILE_MATRIX_MODE:-quick}"
readonly repeats="${OVERTE_MACOS_PROFILE_REPEATS:-1}"
readonly timeout_seconds="${OVERTE_MACOS_PROFILE_TIMEOUT_SECONDS:-420}"
readonly shutdown_grace_seconds="${OVERTE_MACOS_SMOKE_SHUTDOWN_GRACE_SECONDS:-15}"

[[ "$(uname -s)" == Darwin ]] || { echo "performance matrix requires macOS" >&2; exit 1; }
[[ -x "$executable" ]] || { echo "missing executable: $executable" >&2; exit 1; }
[[ "$mode" == quick || "$mode" == full ]] || { echo "matrix mode must be quick or full" >&2; exit 2; }
[[ "$repeats" =~ ^[1-9][0-9]*$ ]] && (( repeats <= 10 )) || {
    echo "profile repeats must be in 1..10" >&2
    exit 2
}

mkdir -p "$output_dir"
if [[ -n "$(find "$output_dir" -mindepth 1 -print -quit)" ]]; then
    echo "refusing to mix a performance matrix with existing evidence: $output_dir" >&2
    exit 2
fi
os_name="$(sw_vers -productName)"
os_version="$(sw_vers -productVersion)"
os_build="$(sw_vers -buildVersion)"
cpu_model="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || :)"
LC_ALL=C system_profiler -json SPHardwareDataType SPDisplaysDataType | \
    python3 "$source_root/macos/tools/sanitize-performance-hardware.py" \
        --output "$output_dir/hardware.json" \
        --os-name "$os_name" --os-version "$os_version" --os-build "$os_build" \
        --cpu-model "$cpu_model"
printf 'ProductName:\t%s\nProductVersion:\t%s\nBuildVersion:\t%s\n' \
    "$os_name" "$os_version" "$os_build" > "$output_dir/macos-version.txt"
shasum -a 256 "$executable" > "$output_dir/application.sha256"
readonly fixture_sha256="$(python3 - "$template" "$procedural_shader" <<'PY'
import hashlib
from pathlib import Path
import sys

print(hashlib.sha256(Path(sys.argv[1]).read_bytes() + b"\0" + Path(sys.argv[2]).read_bytes()).hexdigest())
PY
)"

detected_runner_class="$(python3 \
    "$source_root/macos/tools/sanitize-performance-hardware.py" \
    --classify "$output_dir/hardware.json")"
runner_class="${OVERTE_MACOS_PROFILE_RUNNER_CLASS:-auto}"
[[ "$runner_class" == diagnostic || "$runner_class" == hardware ]] || {
    [[ "$runner_class" == auto ]] || {
        echo "profile runner class must be auto, diagnostic, or hardware" >&2
        exit 2
    }
}
if [[ "$runner_class" == hardware && "$detected_runner_class" != hardware ]]; then
    echo "refusing to upgrade diagnostic graphics evidence to hardware" >&2
    exit 2
fi
[[ "$runner_class" == auto ]] && runner_class="$detected_runner_class"
readonly runner_class
readonly fixture_mode="$([[ "$runner_class" == diagnostic ]] && printf diagnostic-lite || printf full)"
printf '{"detected_runner_class":"%s","fixture_mode":"%s","runner_class":"%s"}\n' \
    "$detected_runner_class" "$fixture_mode" "$runner_class" > \
    "$output_dir/runner-class.json"

profiles=()
while IFS= read -r profile; do
    profiles+=("$profile")
done < <(python3 - "$profiles_file" "$mode" "$runner_class" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
order = "diagnostic_order" if sys.argv[3] == "diagnostic" else f"{sys.argv[2]}_order"
for identifier in payload[order]:
    print(identifier)
PY
)
(( ${#profiles[@]} > 0 )) || { echo "profile order is empty" >&2; exit 2; }

translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')"
python3 - "$output_dir/matrix-manifest.json" "$mode" "$runner_class" "$fixture_mode" \
    "$repeats" "$output_dir/application.sha256" "$profiles_file" "$fixture_sha256" \
    "$(uname -m)" "$translated" \
    "${profiles[@]}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

path, mode, runner_class, fixture_mode, repeats, app_sha_path, profiles_path, fixture_sha, machine, translated, *profiles = sys.argv[1:]
app_sha = Path(app_sha_path).read_text(encoding="utf-8").split()[0]
catalog = Path(profiles_path).read_bytes()
payload = {
    "schema_version": 2,
    "mode": mode,
    "runner_class": runner_class,
    "fixture_mode": fixture_mode,
    "repeats": int(repeats),
    "expected_profiles": profiles,
    "application_sha256": app_sha,
    "profiles_sha256": hashlib.sha256(catalog).hexdigest(),
    "fixture_sha256": fixture_sha,
    "machine": machine,
    "translated": translated == "1",
}
target = Path(path)
target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(target, 0o600)
PY

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
    local warmup_snapshot="$run_dir/macos-profile-warmup.png"
    local snapshot="$run_dir/macos-profile.png"
    local screenshot_result="$run_dir/profile-screenshot.json"
    local profile_result="$run_dir/macos-profile.json"
    local private_results
    private_results="$(mktemp -d "${TMPDIR:-/tmp}/overte-macos-profile.XXXXXX")"
    local private_warmup_snapshot="$private_results/macos-profile-warmup.png"
    local private_snapshot="$private_results/macos-profile.png"
    local private_profile_result="$private_results/macos-profile.json"
    local status=0
    local accepted=false
    local screenshot_sha256=""
    local visual_validation_passed=false

    mkdir -p "$run_dir" "$output_dir/cache/$profile"
    rm -f "$warmup_snapshot" "$snapshot" "$screenshot_result" \
        "$profile_result" \
        "$run_dir/profile-accepted"
    python3 "$source_root/macos/tools/render-performance-profile.py" \
        --profiles "$profiles_file" --profile "$profile" --template "$template" \
        --procedural-shader "$procedural_shader" \
        --output "$generated_script" --trace "$trace" --run-index "$run_index" \
        --fixture-mode "$fixture_mode"

    local -a app_command=(
        "$executable" --allowMultipleInstances --no-login-suggestion --disableWatchdog --display Desktop
        --disableLocalAvatar --cache "$output_dir/cache/$profile"
        --defaultScriptsOverride "file://$default_scripts_override"
        --url "file://$scene" --testScript "$generated_script"
        --testResultsLocation "$private_results" --quitWhenFinished
    )

    set +e
    python3 "$source_root/macos/tools/run-process-with-timeout.py" \
        --timeout "$timeout_seconds" --grace "$shutdown_grace_seconds" \
        --log "$log" --result "$process_result" --sample "$sample" \
        --crash-report "$crash_report" -- \
        "${app_command[@]}"
    status=$?
    set -e

    # PlatformInfo.getPlatform() contains NIC identifiers on macOS. The app
    # writes outside the uploaded artifact tree; only the atomically sanitized
    # result can cross into it. A cancelled run therefore cannot upload raw
    # runtime platform data.
    if [[ -e "$private_profile_result" ]]; then
        if python3 "$source_root/macos/tools/sanitize-performance-hardware.py" \
                --profile-result "$private_profile_result"; then
            mv "$private_profile_result" "$profile_result"
        else
            status=1
        fi
    fi
    [[ ! -e "$private_warmup_snapshot" ]] || mv "$private_warmup_snapshot" "$warmup_snapshot"
    [[ ! -e "$private_snapshot" ]] || mv "$private_snapshot" "$snapshot"

    if (( status == 0 )); then
        grep -Fq "OVERTE_MACOS_PROFILE passed id=$profile" "$log" || status=1
        grep -Fq "OVERTE_MACOS_PROFILE warmup_snapshot=" "$log" || status=1
        grep -Fq "OVERTE_MACOS_PROFILE warmup_cooldown_ms=" "$log" || status=1
        grep -Fq "OVERTE_MACOS_PROFILE final_snapshot=" "$log" || status=1
        [[ -s "$warmup_snapshot" && -s "$snapshot" && \
            -s "$profile_result" ]] || status=1
    fi
    if (( status == 0 )); then
        python3 "$source_root/macos/tools/validate-screenshot.py" "$snapshot" \
            --result "$screenshot_result" \
            --require-red-pixels 128 --require-cyan-pixels 128 \
            --require-red-left --require-cyan-right || status=$?
    fi
    if (( status == 0 )); then
        screenshot_sha256="$(shasum -a 256 "$snapshot" | awk '{print $1}')"
        visual_validation_passed=true
        printf 'accepted\n' > "$run_dir/profile-accepted"
        accepted=true
    fi
    python3 - "$output_dir/attempts.jsonl" "$profile" "$label" "$run_index" "$status" \
        "$accepted" "$run_dir" "$screenshot_sha256" "$visual_validation_passed" <<'PY'
import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
with path.open("a", encoding="utf-8") as output:
    output.write(json.dumps({
        "profile": sys.argv[2],
        "label": sys.argv[3],
        "run_index": int(sys.argv[4]),
        "exit_code": int(sys.argv[5]),
        "accepted": sys.argv[6] == "true",
        "result_directory": str(Path(sys.argv[7]).relative_to(path.parent)),
        "screenshot_sha256": sys.argv[8] or None,
        "visual_validation_passed": sys.argv[9] == "true",
    }, sort_keys=True) + "\n")
os.chmod(path, 0o600)
PY
    if (( status != 0 )); then
        echo "profile case failed but matrix continues: $profile/$label status=$status" >&2
    fi
    return 0
}

# Physical hardware gets a throwaway process so shader/resource first-use costs
# do not contaminate the repeated steady-state measurements. The hosted
# software renderer retains first-use cost as bounded diagnostic evidence and
# avoids doubling a process that cannot persist useful driver binaries.
if [[ "$runner_class" == hardware ]]; then
    for profile in "${profiles[@]}"; do
        run_case "$profile" warmup 1
    done
fi
for (( repeat = 1; repeat <= repeats; repeat += 1 )); do
    if (( repeat % 2 == 0 )); then
        for (( index = ${#profiles[@]} - 1; index >= 0; index -= 1 )); do
            run_case "${profiles[index]}" "run-$repeat" "$((repeat + 1))"
        done
    else
        for profile in "${profiles[@]}"; do
            run_case "$profile" "run-$repeat" "$((repeat + 1))"
        done
    fi
done

python3 "$source_root/macos/tools/analyze-performance-matrix.py" "$output_dir" \
    --profiles "$profiles_file" \
    --fixture-source "$template" --procedural-shader "$procedural_shader" \
    --result "$output_dir/matrix-result.json" \
    --junit "$output_dir/TEST-overte-macos-performance-matrix.xml" \
    --minimum-runs "$repeats"

echo "macOS performance matrix passed"
