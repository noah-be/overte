#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly repository_root="$(cd -- "$android_root/.." && pwd)"
readonly build_dir="${OVERTE_NATIVE_COVERAGE_BUILD_DIR:-$android_root/build/native-coverage}"
readonly report_dir="${OVERTE_NATIVE_COVERAGE_REPORT_DIR:-$android_root/build/reports/coverage/native}"
readonly managed_gcovr="$android_root/build/tools/native-coverage-venv/bin/gcovr"
readonly cmake_command="${OVERTE_CMAKE_COMMAND:-cmake}"
readonly ctest_command="${OVERTE_CTEST_COMMAND:-ctest}"
readonly mktemp_command="${OVERTE_NATIVE_COVERAGE_MKTEMP_COMMAND:-mktemp}"

gcovr_command="${OVERTE_GCOVR_COMMAND:-$(command -v gcovr 2>/dev/null || true)}"
if [[ -z "$gcovr_command" && -x "$managed_gcovr" ]]; then
    gcovr_command="$managed_gcovr"
fi
if [[ -z "$gcovr_command" ]]; then
    printf 'SKIP: gcovr is required for native coverage reporting.\n'
    printf 'Install it in a virtual environment; no system installation is required.\n'
    exit 77
fi

mkdir -p -- "$(dirname -- "$build_dir")" "$report_dir"
lock_timeout="${OVERTE_NATIVE_COVERAGE_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'FAIL: invalid native coverage lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
exec {coverage_lock_fd}>>"${build_dir}.lock"
if ! flock -x -w "$lock_timeout" "$coverage_lock_fd"; then
    printf 'FAIL: timed out waiting for native coverage lock: %s\n' "${build_dir}.lock" >&2
    exit 1
fi
staging_dir=''
cleanup() {
    if [[ -n "$staging_dir" ]]; then
        rm -rf -- "$staging_dir"
    fi
    flock -u "$coverage_lock_fd" 2>/dev/null || true
    exec {coverage_lock_fd}>&-
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rm -f -- "$report_dir"/interface.xml "$report_dir"/login-state.xml \
    "$report_dir"/pending-handoff.xml "$report_dir"/interface*.html \
    "$report_dir"/login-state*.html "$report_dir"/pending-handoff*.html

staging_dir="$("$mktemp_command" -d "$report_dir/.native-coverage.XXXXXXXX")"

"$cmake_command" -S "$android_root/tests/native" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_CXX_FLAGS=--coverage \
    -DCMAKE_EXE_LINKER_FLAGS=--coverage
"$cmake_command" --build "$build_dir" --parallel
"$ctest_command" --test-dir "$build_dir" --output-on-failure
# gcovr resolves the parent repository and the nested Android tree as two
# source roots. Report them separately so neither root can silently disappear
# during path normalization/merging.
"$gcovr_command" "$build_dir" --root "$repository_root" \
    --filter 'interface/src/ui/Phone(LoginState|GraphicsPolicy)\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/interface.xml" \
    --html-details "$staging_dir/interface.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90

"$gcovr_command" "$build_dir" --root "$repository_root" \
    --filter 'interface/src/ui/PhoneLoginState\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/login-state.xml" \
    --html-details "$staging_dir/login-state.html" \
    --print-summary \
    --fail-under-line 100 \
    --fail-under-branch 100

"$gcovr_command" "$build_dir" --root "$repository_root" \
    --filter '.*PhonePendingHandoff\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/pending-handoff.xml" \
    --html-details "$staging_dir/pending-handoff.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90

readonly required_artifacts=(
    interface.xml interface.html
    login-state.xml login-state.html
    pending-handoff.xml pending-handoff.html
)
for artifact in "${required_artifacts[@]}"; do
    if [[ ! -s "$staging_dir/$artifact" ]]; then
        printf 'FAIL: native coverage tool produced no %s report\n' "$artifact" >&2
        exit 1
    fi
done

python3 - "$staging_dir/interface.xml" "$staging_dir/login-state.xml" \
    "$staging_dir/pending-handoff.xml" <<'PY'
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

try:
    for argument in sys.argv[1:]:
        path = Path(argument)
        root = ET.parse(path).getroot()
        if root.tag != "coverage":
            raise ValueError(f"{path.name} has unsupported root {root.tag!r}")
        for name in ("line-rate", "branch-rate"):
            value = float(root.get(name, ""))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{path.name} has invalid {name}")
except (ET.ParseError, OSError, TypeError, ValueError) as error:
    print(f"FAIL: invalid native coverage XML: {error}", file=sys.stderr)
    raise SystemExit(1)
PY

for artifact in "$staging_dir"/*; do
    [[ -f "$artifact" ]] || continue
    mv -f -- "$artifact" "$report_dir/${artifact##*/}"
done
