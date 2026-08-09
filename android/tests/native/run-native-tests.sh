#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${OVERTE_NATIVE_TEST_BUILD_DIR:-$script_dir/.build}"

cmake -S "$script_dir" -B "$build_dir" \
    -DBUILD_TESTING=ON \
    -DCMAKE_BUILD_TYPE=Debug
cmake --build "$build_dir" --parallel
ctest --test-dir "$build_dir" --output-on-failure
