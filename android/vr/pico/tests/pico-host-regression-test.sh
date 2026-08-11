#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../../.." && pwd)"
BUILD_DIR="${PICO_HOST_BUILD_DIR:-$REPO_ROOT/build-tests}"
BUILD_CONFIG="${PICO_HOST_BUILD_CONFIG:-Debug}"
TIMEOUT_SECONDS="${PICO_HOST_TIMEOUT_SECONDS:-120}"
BUILD_TESTS=1
KEEP_LOGS="${PICO_HOST_KEEP_LOGS:-0}"

usage() {
    cat <<'USAGE'
Usage: ./android/vr/pico/tests/pico-host-regression-test.sh [options]

Build and run the host-side test suites that cover Pico-specific changes.

Options:
  --build-dir DIR   CMake build directory (default: build-tests)
  --config NAME     Multi-config build configuration (default: Debug)
  --no-build        Run already-built test executables
  --keep-logs       Keep per-suite logs below the temporary directory
  -h, --help        Show this help

Environment equivalents:
  PICO_HOST_BUILD_DIR, PICO_HOST_BUILD_CONFIG, PICO_HOST_TIMEOUT_SECONDS,
  PICO_HOST_KEEP_LOGS
USAGE
}

while (( $# > 0 )); do
    case "$1" in
        --build-dir)
            [[ $# -ge 2 ]] || { printf 'error: --build-dir requires a value\n' >&2; exit 2; }
            BUILD_DIR="$2"
            shift 2
            ;;
        --config)
            [[ $# -ge 2 ]] || { printf 'error: --config requires a value\n' >&2; exit 2; }
            BUILD_CONFIG="$2"
            shift 2
            ;;
        --no-build)
            BUILD_TESTS=0
            shift
            ;;
        --keep-logs)
            KEEP_LOGS=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'error: unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$BUILD_DIR" != /* ]]; then
    BUILD_DIR="$REPO_ROOT/$BUILD_DIR"
fi

[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
    printf 'error: timeout must be a positive integer, got %s\n' "$TIMEOUT_SECONDS" >&2
    exit 2
}
[[ "$KEEP_LOGS" == 0 || "$KEEP_LOGS" == 1 ]] || {
    printf 'error: PICO_HOST_KEEP_LOGS must be 0 or 1, got %s\n' "$KEEP_LOGS" >&2
    exit 2
}
[[ -f "$BUILD_DIR/CMakeCache.txt" ]] || {
    printf 'error: no configured CMake build at %s\n' "$BUILD_DIR" >&2
    exit 2
}
command -v cmake >/dev/null || { printf 'error: cmake is required\n' >&2; exit 2; }
command -v timeout >/dev/null || { printf 'error: timeout is required\n' >&2; exit 2; }

CONAN_GENERATORS_DIR="$BUILD_DIR/generators"
BUILD_CONFIG_LOWER="${BUILD_CONFIG,,}"
if [[ -f "$CONAN_GENERATORS_DIR/glmTargets.cmake" && \
      ! -f "$CONAN_GENERATORS_DIR/glm-Target-$BUILD_CONFIG_LOWER.cmake" ]]; then
    printf 'error: Conan dependencies for configuration %s are not installed in %s\n' \
        "$BUILD_CONFIG" "$BUILD_DIR" >&2
    printf 'error: run the matching Conan install and reconfigure CMake first\n' >&2
    exit 2
fi

TARGETS=(
    animation-AnimTests
    audio-PositionalAudioStreamTests
    avatars-AvatarDataTests
    networking-PacketTests
    networking-ReceivedMessageTests
    shared-GLMHelpersTests
)
TEST_GROUPS=(animation audio avatars networking networking shared)

if (( BUILD_TESTS )); then
    printf 'Building %s Pico-relevant host test targets (%s)\n' "${#TARGETS[@]}" "$BUILD_CONFIG"
    cmake --build "$BUILD_DIR" --config "$BUILD_CONFIG" --target "${TARGETS[@]}"
fi

QT_PLUGIN_PATH="${QT_QPA_PLATFORM_PLUGIN_PATH:-}"
if [[ -z "$QT_PLUGIN_PATH" ]]; then
    QT_CORE_DIR="$(sed -n 's/^Qt5Core_DIR:PATH=//p' "$BUILD_DIR/CMakeCache.txt" | head -n 1)"
    if [[ -n "$QT_CORE_DIR" ]]; then
        QT_LIBRARY_DIR="$(cd -- "$QT_CORE_DIR/../.." 2>/dev/null && pwd || true)"
        if [[ -d "$QT_LIBRARY_DIR/qt5/plugins/platforms" ]]; then
            QT_PLUGIN_PATH="$QT_LIBRARY_DIR/qt5/plugins/platforms"
        fi
    fi
fi

LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pico-host-regression.XXXXXX")"
CONFIG_DIR="$LOG_DIR/config"
mkdir -p "$CONFIG_DIR"
PASSED=0
FAILED=0

cleanup() {
    if (( KEEP_LOGS )); then
        printf 'Logs: %s\n' "$LOG_DIR"
    elif [[ -d "$LOG_DIR" && "$(basename -- "$LOG_DIR")" == pico-host-regression.* ]]; then
        rm -rf -- "$LOG_DIR"
    fi
}
trap cleanup EXIT

for index in "${!TARGETS[@]}"; do
    target="${TARGETS[$index]}"
    group="${TEST_GROUPS[$index]}"
    binary="$BUILD_DIR/tests/$group/$BUILD_CONFIG/$target"
    if [[ ! -x "$binary" ]]; then
        binary="$BUILD_DIR/tests/$group/$target"
    fi

    if [[ ! -x "$binary" ]]; then
        printf 'FAIL %-42s executable not found\n' "$target" >&2
        FAILED=$((FAILED + 1))
        continue
    fi

    log="$LOG_DIR/$target.log"
    set +e
    (
        cd -- "$REPO_ROOT"
        XDG_CONFIG_HOME="$CONFIG_DIR" \
        QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
        QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_PATH" \
        timeout "${TIMEOUT_SECONDS}s" "$binary"
    ) >"$log" 2>&1
    code=$?
    set -e

    totals="$(sed -n '/^Totals:/h; ${x;p;}' "$log")"
    totals="${totals:-no Qt totals}"
    if (( code == 0 )); then
        printf 'PASS %-42s %s\n' "$target" "$totals"
        PASSED=$((PASSED + 1))
    else
        printf 'FAIL %-42s exit=%s, %s\n' "$target" "$code" "$totals" >&2
        FAILED=$((FAILED + 1))
    fi
done

printf 'Suites: %s passed, %s failed\n' "$PASSED" "$FAILED"
(( FAILED == 0 ))
