#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${OVERTE_TEST_BUILD_DIR:-$ROOT/build-tests}"
BUILD_CONFIG="${OVERTE_TEST_BUILD_CONFIG:-Debug}"
JOBS="${OVERTE_TEST_JOBS:-$(nproc)}"

usage() {
    cat <<'EOF'
Usage: tests/project-native-test.sh [BUILD_DIR]

Build and execute every CTest-registered automated native test in an already
configured Overte build. Environment: OVERTE_TEST_BUILD_CONFIG,
OVERTE_TEST_JOBS, CTEST_OUTPUT_ON_FAILURE.
EOF
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) BUILD_DIR="$1" ;;
esac
[[ "$BUILD_DIR" == /* ]] || BUILD_DIR="$ROOT/$BUILD_DIR"
[[ -f "$BUILD_DIR/CMakeCache.txt" ]] || {
    echo "error: no configured CMake build at $BUILD_DIR" >&2
    exit 2
}
command -v cmake >/dev/null || { echo "error: cmake is required" >&2; exit 2; }
command -v ctest >/dev/null || { echo "error: ctest is required" >&2; exit 2; }

cmake --build "$BUILD_DIR" --config "$BUILD_CONFIG" --target all-tests --parallel "$JOBS"
ctest --test-dir "$BUILD_DIR" -C "$BUILD_CONFIG" --output-on-failure --no-tests=error
