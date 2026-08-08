#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
TEST_CLASSES="$(mktemp -d "${TMPDIR:-/tmp}/pico-audio-state.XXXXXX")"

cleanup() {
    if [[ -d "$TEST_CLASSES" && "$(basename -- "$TEST_CLASSES")" == pico-audio-state.* ]]; then
        rm -rf -- "$TEST_CLASSES"
    fi
}
trap cleanup EXIT

command -v javac >/dev/null || { echo "error: javac is required" >&2; exit 2; }
command -v java >/dev/null || { echo "error: java is required" >&2; exit 2; }

javac -d "$TEST_CLASSES" \
    "$REPO_ROOT/android/apps/picoInterface/src/main/java/org/overte/pico/PicoAudioBufferSize.java" \
    "$REPO_ROOT/android/apps/picoInterface/src/main/java/org/overte/pico/PicoAudioCaptureState.java" \
    "$SCRIPT_DIR/java/org/overte/pico/PicoAudioCaptureStateTest.java" \
    "$SCRIPT_DIR/java/org/overte/pico/PicoAudioBufferSizeTest.java"
java -cp "$TEST_CLASSES" org.overte.pico.PicoAudioCaptureStateTest
java -cp "$TEST_CLASSES" org.overte.pico.PicoAudioBufferSizeTest
echo "PASS Pico AudioRecord capture-state regression"
