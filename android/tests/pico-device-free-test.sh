#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

run() {
    printf '\n== %s ==\n' "$1"
    shift
    "$@"
}

run "Shell syntax" bash -c '
    set -euo pipefail
    while IFS= read -r -d "" script; do
        bash -n "$script"
    done < <(find "$1" -maxdepth 2 -type f -name "*.sh" -print0)
' bash "$ANDROID_DIR"
run "WebView frame/JNI bridge" python3 "$SCRIPT_DIR/pico-webview-bridge-test.py"
run "WebView gesture state" "$SCRIPT_DIR/pico-webview-input-test.sh"
run "AudioRecord lifecycle state" "$SCRIPT_DIR/pico-audio-capture-state-test.sh"
run "OpenXR loader lifecycle" python3 "$SCRIPT_DIR/pico-openxr-loader-test.py"
run "Microphone runner mocks" "$SCRIPT_DIR/pico-microphone-test-test.sh"
run "Unattended runner mocks" "$SCRIPT_DIR/pico-unattended-test-test.sh"
run "Device-lock mocks" "$SCRIPT_DIR/pico-device-lock-test.sh"
run "Serverless fixture integrity" "$SCRIPT_DIR/serverless-hub-fixture-test.sh"
run "Power analyzer" python3 "$ANDROID_DIR/tools/tests/test_analyze_pico4_power.py"

printf '\nPASS all Pico device-free regressions\n'
