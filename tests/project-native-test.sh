#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${OVERTE_TEST_BUILD_DIR:-$ROOT/build-tests}"
BUILD_CONFIG="${OVERTE_TEST_BUILD_CONFIG:-Debug}"
JOBS="${OVERTE_TEST_JOBS:-$(nproc)}"
TIMEOUT="${OVERTE_TEST_TIMEOUT:-300}"
INCLUDE_BENCHMARKS="${OVERTE_TEST_INCLUDE_BENCHMARKS:-0}"

usage() {
    cat <<'EOF'
Usage: tests/project-native-test.sh [BUILD_DIR]

Build and execute every CTest-registered automated native test in an already
configured Overte build. Environment: OVERTE_TEST_BUILD_CONFIG,
OVERTE_TEST_JOBS, OVERTE_TEST_TIMEOUT, OVERTE_TEST_INCLUDE_BENCHMARKS,
CTEST_OUTPUT_ON_FAILURE. Benchmarks are excluded unless explicitly enabled;
hardware-dependent tests report precise skips when their backend is absent.
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

QT_PLUGIN_PATH="${QT_QPA_PLATFORM_PLUGIN_PATH:-}"
if [[ -z "$QT_PLUGIN_PATH" ]]; then
    QT5_DIR="$(sed -n 's/^Qt5_DIR:[^=]*=//p' "$BUILD_DIR/CMakeCache.txt" | head -n 1)"
    if [[ -n "$QT5_DIR" ]]; then
        QT_PREFIX="$(cd -- "$QT5_DIR/../.." 2>/dev/null && pwd || true)"
        [[ -d "$QT_PREFIX/qt5/plugins/platforms" ]] && QT_PLUGIN_PATH="$QT_PREFIX/qt5/plugins/platforms"
    fi
fi

cmake --build "$BUILD_DIR" --config "$BUILD_CONFIG" --target all-tests --parallel "$JOBS"
CTEST_ARGS=(--test-dir "$BUILD_DIR" -C "$BUILD_CONFIG" --output-on-failure
    --no-tests=error --parallel "$JOBS" --timeout "$TIMEOUT")
EXCLUDES=()
if [[ "$INCLUDE_BENCHMARKS" != "1" ]]; then
    EXCLUDES+=('BenchmarkTests-test$')
fi
if (( ${#EXCLUDES[@]} )); then
    EXCLUDE_REGEX="$(IFS='|'; echo "${EXCLUDES[*]}")"
    CTEST_ARGS+=(--exclude-regex "$EXCLUDE_REGEX")
fi
QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_PATH" \
ctest "${CTEST_ARGS[@]}"
