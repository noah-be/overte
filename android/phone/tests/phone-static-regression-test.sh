#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"

# Explicit device-free allowlist. Never discover tests by wildcard: a future
# device runner must not start merely because its name matches a pattern. The
# benchmark entry tests its harness with private mock ADB, not a real device.
readonly tests=(
    phone-16k-dependency-sentinel-test.sh
    phone-apk-contents-test.sh
    phone-apk-metadata-test.sh
    phone-apk-padding-test.sh
    phone-archive-extraction-test.sh
    phone-audio-output-race-test.sh
    phone-build-resource-guard-test.sh
    phone-build-download-parity-test.sh
    phone-data-protection-test.sh
    phone-deep-link-test.sh
    phone-default-sky-payload-test.sh
    phone-deploy-safety-test.sh
    phone-device-lock-test.sh
    phone-device-smoke-mock-test.sh
    phone-doctor-output-test.sh
    phone-elf-alignment-test.sh
    phone-emulator-config-test.sh
    phone-focus-debugger-animation-test.sh
    phone-forward-pass-trim-test.sh
    phone-framebuffer-telemetry-test.sh
    phone-gl-trash-telemetry-test.sh
    phone-graphics-benchmark-test.sh
    phone-graphics-profile-test.sh
    phone-host-runtime-test.sh
    phone-light-clustering-fastpath-test.sh
    phone-native-present-telemetry-test.sh
    phone-offscreen-ui-mip-test.sh
    phone-overlay-cache-test.sh
    phone-overlay-depth-test.sh
    phone-overlay-scale-test.sh
    phone-pico-qt-fallback-test.sh
    phone-prebuilt-16k-deps-test.sh
    phone-prepare-architecture-test.sh
    phone-qml-scenegraph-trim-test.sh
    phone-qt-runtime-trim-test.sh
    phone-release-config-test.sh
    phone-render-timing-telemetry-test.sh
    phone-script-debug-assets-trim-test.sh
    phone-serverless-packaging-test.sh
    phone-serverless-viewpoint-test.sh
    phone-shader-payload-test.sh
    phone-tablet-static-test.sh
    phone-touch-navigation-test.sh
    phone-virtual-pad-texture-test.sh
)

for test_name in "${tests[@]}"; do
    printf '\n[%s]\n' "$test_name"
    "$script_dir/$test_name"
done

git -C "$repo_root" diff --check

printf '\nAndroid phone complete device-free regression gate passed (%d suites).\n' \
    "${#tests[@]}"
