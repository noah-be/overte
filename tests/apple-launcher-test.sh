#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
    printf 'SKIP: Apple launcher XCTest requires macOS and Xcode.\n'
    exit 77
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly repo_root
readonly build_dir="${1:-$repo_root/build/apple-launcher-tests}"

cmake -S "$repo_root/launchers/darwin" -B "$build_dir" \
    -DLAUNCHER_HMAC_SECRET=overte-test-only
cmake --build "$build_dir" --target HQLauncherTests
ctest --test-dir "$build_dir" --output-on-failure
