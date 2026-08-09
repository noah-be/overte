#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
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
"$gcovr_command" --root "$android_root/.." \
    --filter '.*/interface/src/ui/Phone(LoginState|GraphicsPolicy)\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/interface.xml" \
    --html-details "$staging_dir/interface.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90

"$gcovr_command" --root "$android_root/.." \
    --filter '.*/interface/src/ui/PhoneLoginState\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/login-state.xml" \
    --html-details "$staging_dir/login-state.html" \
    --print-summary \
    --fail-under-line 100 \
    --fail-under-branch 100

"$gcovr_command" --root "$android_root/.." \
    --filter '.*PhonePendingHandoff\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$staging_dir/pending-handoff.xml" \
    --html-details "$staging_dir/pending-handoff.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90

for artifact in "$staging_dir"/*; do
    [[ -f "$artifact" ]] || continue
    mv -f -- "$artifact" "$report_dir/${artifact##*/}"
done
