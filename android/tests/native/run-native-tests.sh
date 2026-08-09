#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${OVERTE_NATIVE_TEST_BUILD_DIR:-$script_dir/.build}"
android_root="$(cd -- "$script_dir/../.." && pwd)"
report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/native"
cmake_command="${OVERTE_CMAKE_COMMAND:-cmake}"
ctest_command="${OVERTE_CTEST_COMMAND:-ctest}"

"$cmake_command" -S "$script_dir" -B "$build_dir" \
    -DBUILD_TESTING=ON \
    -DCMAKE_BUILD_TYPE=Debug
"$cmake_command" --build "$build_dir" --parallel
mkdir -p "$report_dir"
temporary_report="$(mktemp "$report_dir/.TEST-native.XXXXXX.xml")"
trap 'rm -f -- "$temporary_report"' EXIT
set +e
"$ctest_command" --test-dir "$build_dir" --output-on-failure \
    --output-junit "$temporary_report"
status=$?
set -e
if [[ -s "$temporary_report" ]]; then
    mv -f -- "$temporary_report" "$report_dir/TEST-native.xml"
fi
exit "$status"
