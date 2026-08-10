#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${OVERTE_NATIVE_TEST_BUILD_DIR:-$script_dir/.build}"
android_root="$(cd -- "$script_dir/../.." && pwd)"
report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/native"
cmake_command="${OVERTE_CMAKE_COMMAND:-cmake}"
ctest_command="${OVERTE_CTEST_COMMAND:-ctest}"
source "$script_dir/../reporting/atomic-junit-report.sh"
overte_junit_prepare "$report_dir" TEST-native.xml
trap overte_junit_cleanup EXIT

"$cmake_command" -S "$script_dir" -B "$build_dir" \
    -DBUILD_TESTING=ON \
    -DCMAKE_BUILD_TYPE=Debug
"$cmake_command" --build "$build_dir" --parallel
set +e
"$ctest_command" --test-dir "$build_dir" --output-on-failure \
    --output-junit "$OVERTE_JUNIT_TEMP_REPORT"
status=$?
set -e
if ! overte_junit_publish && (( status == 0 )); then
    status=1
fi
exit "$status"
