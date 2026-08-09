#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${OVERTE_TEST_BUILD_DIR:-$ROOT/build-coverage}"
OUTPUT_DIR="${OVERTE_COVERAGE_OUTPUT_DIR:-$ROOT/build/coverage/native}"
BASELINE="${OVERTE_COVERAGE_BASELINE:-}"
CHANGED_SINCE="${OVERTE_COVERAGE_CHANGED_SINCE:-}"
COVERAGE_TMPDIR="${OVERTE_COVERAGE_TMPDIR:-$BUILD_DIR/tmp}"

case "${1:-}" in
    -h|--help)
        echo "Usage: tests/project-native-coverage.sh [BUILD_DIR [OUTPUT_DIR]]"
        exit 0
        ;;
    "") ;;
    *) BUILD_DIR="$1" ;;
esac
[[ "${2:-}" == "" ]] || OUTPUT_DIR="$2"
[[ "$BUILD_DIR" == /* ]] || BUILD_DIR="$ROOT/$BUILD_DIR"
[[ "$OUTPUT_DIR" == /* ]] || OUTPUT_DIR="$ROOT/$OUTPUT_DIR"

[[ -f "$BUILD_DIR/CMakeCache.txt" ]] || {
    echo "error: no configured coverage build at $BUILD_DIR" >&2
    exit 2
}
grep -Eq '^CMAKE_(C|CXX)_FLAGS_DEBUG:[^=]*=.*--coverage' "$BUILD_DIR/CMakeCache.txt" || {
    echo "error: $BUILD_DIR was not configured with --coverage Debug flags" >&2
    exit 2
}
mkdir -p "$COVERAGE_TMPDIR"

TMPDIR="$COVERAGE_TMPDIR" "$ROOT/tests/project-native-test.sh" "$BUILD_DIR"
COVERAGE_ARGS=(--build-dir "$BUILD_DIR" --output-dir "$OUTPUT_DIR")
[[ -z "$BASELINE" ]] || COVERAGE_ARGS+=(--baseline "$BASELINE")
[[ -z "$CHANGED_SINCE" ]] || COVERAGE_ARGS+=(--changed-since "$CHANGED_SINCE")
TMPDIR="$COVERAGE_TMPDIR" "$ROOT/tests/generate-native-coverage.py" "${COVERAGE_ARGS[@]}"
