#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${OVERTE_TEST_BUILD_DIR:-$ROOT/build-tests}"
BUILD_CONFIG="${OVERTE_TEST_BUILD_CONFIG:-Debug}"

default_jobs() {
    local detected=''
    if command -v nproc >/dev/null 2>&1; then
        detected="$(nproc 2>/dev/null || true)"
    fi
    if [[ ! "$detected" =~ ^[1-9][0-9]*$ ]] && command -v sysctl >/dev/null 2>&1; then
        detected="$(sysctl -n hw.logicalcpu 2>/dev/null || true)"
    fi
    [[ "$detected" =~ ^[1-9][0-9]*$ ]] || detected=1
    printf '%s\n' "$detected"
}

JOBS="${OVERTE_TEST_JOBS:-$(default_jobs)}"
JUNIT="${OVERTE_TEST_JUNIT:-}"
TEST_TIMEOUT="${OVERTE_TEST_TIMEOUT:-900}"

usage() {
    cat <<'EOF'
Usage: tests/project-native-test.sh [BUILD_DIR]

Build and execute every CTest-registered automated native test in an already
configured Overte build. Environment: OVERTE_TEST_BUILD_CONFIG,
OVERTE_TEST_JOBS, OVERTE_TEST_JUNIT, OVERTE_TEST_TIMEOUT,
CTEST_OUTPUT_ON_FAILURE.
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
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "error: OVERTE_TEST_JOBS must be positive" >&2; exit 2; }
[[ "$TEST_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "error: OVERTE_TEST_TIMEOUT must be positive" >&2; exit 2; }

if [[ "$(uname -s)" == "Darwin" ]]; then
    conan_dylib_dir="$BUILD_DIR/conanlibs/$BUILD_CONFIG"
    [[ -d "$conan_dylib_dir" ]] || {
        echo "error: missing macOS Conan dylib directory: $conan_dylib_dir" >&2
        exit 2
    }
    export DYLD_LIBRARY_PATH="$conan_dylib_dir${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi

cmake --build "$BUILD_DIR" --config "$BUILD_CONFIG" --target all-tests --parallel "$JOBS"
ctest_args=(--test-dir "$BUILD_DIR" -C "$BUILD_CONFIG" --output-on-failure
    --no-tests=error --timeout "$TEST_TIMEOUT")
if [[ -n "$JUNIT" ]]; then
    [[ "$JUNIT" == /* ]] || JUNIT="$ROOT/$JUNIT"
    [[ ! -L "$JUNIT" ]] || { echo "error: refusing a symlinked JUnit report" >&2; exit 2; }
    mkdir -p "$(dirname "$JUNIT")"
    ctest_args+=(--output-junit "$JUNIT")
fi
ctest "${ctest_args[@]}"
