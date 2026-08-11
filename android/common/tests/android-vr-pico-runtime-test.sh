#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"

# This is the Pico implementation evidence relevant to a parent android-vr
# integration lane. Pico packaging, release, performance, power, and device
# tooling deliberately remain in the complete Pico child suite.
exec python3 "$android_root/vr/pico/tests/pico4-test-suite.py" \
    --timeout 120 \
    --test platform-glue \
    --test android-entrypoints \
    --test webview-bridge \
    --test webview-touch-state \
    --test audio-capture-state \
    --test audio-native-transport \
    --test openxr-loader \
    --test openxr-input \
    --test openxr-display \
    --test interaction-diagnostics \
    --test tablet-lifecycle \
    --test tablet-settings \
    --test create-qml \
    --test create-properties \
    --test create-message \
    --test world-state
