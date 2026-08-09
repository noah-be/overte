#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly build_dir="$android_root/build/native-coverage"
readonly report_dir="$android_root/build/reports/coverage/native"
readonly managed_gcovr="$android_root/build/tools/native-coverage-venv/bin/gcovr"

gcovr_command="$(command -v gcovr 2>/dev/null || true)"
if [[ -z "$gcovr_command" && -x "$managed_gcovr" ]]; then
    gcovr_command="$managed_gcovr"
fi
if [[ -z "$gcovr_command" ]]; then
    printf 'SKIP: gcovr is required for native coverage reporting.\n'
    printf 'Install it in a virtual environment; no system installation is required.\n'
    exit 77
fi

cmake -S "$android_root/tests/native" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_CXX_FLAGS=--coverage \
    -DCMAKE_EXE_LINKER_FLAGS=--coverage
cmake --build "$build_dir" --parallel
ctest --test-dir "$build_dir" --output-on-failure
mkdir -p "$report_dir"
# gcovr resolves the parent repository and the nested Android tree as two
# source roots. Report them separately so neither root can silently disappear
# during path normalization/merging.
"$gcovr_command" --root "$android_root/.." \
    --filter '.*/interface/src/ui/Phone(LoginState|GraphicsPolicy)\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$report_dir/interface.xml" \
    --html-details "$report_dir/interface.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90

"$gcovr_command" --root "$android_root/.." \
    --filter '.*/interface/src/ui/PhoneLoginState\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$report_dir/login-state.xml" \
    --html-details "$report_dir/login-state.html" \
    --print-summary \
    --fail-under-line 100 \
    --fail-under-branch 100

exec "$gcovr_command" --root "$android_root/.." \
    --filter '.*PhonePendingHandoff\.h$' \
    --exclude-throw-branches \
    --xml-pretty --xml "$report_dir/pending-handoff.xml" \
    --html-details "$report_dir/pending-handoff.html" \
    --print-summary \
    --fail-under-line 95 \
    --fail-under-branch 90
