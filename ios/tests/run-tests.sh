#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$script_dir/port-contract-test.py"
python3 "$script_dir/build-cli-test.py"
python3 "$script_dir/command-timeout-test.py"
python3 "$script_dir/simulator-smoke-contract-test.py"
python3 "$script_dir/runtime-candidate-verifier-test.py"
python3 "$script_dir/sideload-ipa-normalizer-test.py"
python3 "$script_dir/sideload-handoff-test.py"
python3 "$script_dir/sideload-repackage-workflow-contract-test.py"
python3 "$script_dir/interface-simulator-smoke-test.py"
python3 "$script_dir/interface-world-simulator-smoke-test.py"
python3 "$script_dir/interface-world-simulator-lldb-test.py"
python3 "$script_dir/symbolicate-simulator-crash-test.py"
python3 "$script_dir/interface-ios-domain-login-thread-contract-test.py"
python3 "$script_dir/interface-ios-display-mode-contract-test.py"
python3 "$script_dir/world-runtime-evidence-test.py"
python3 "$script_dir/world-runtime-workflow-contract-test.py"
python3 "$script_dir/simulator-install-diagnostic-workflow-test.py"
python3 "$script_dir/ipad-device-acceptance-test.py"
python3 "$script_dir/ipad-signing-verifier-test.py"
python3 "$script_dir/interface-runtime-workflow-contract-test.py"
python3 "$script_dir/bundle-metadata-test.py"
python3 "$script_dir/client-bundle-metadata-test.py"
python3 "$script_dir/device-results-validator-test.py"
python3 "$script_dir/fedora-ipad-log-test.py"
python3 "$script_dir/prepare-ipad-result-test.py"
python3 "$script_dir/conan-graph-audit-test.py"
python3 "$script_dir/entity-conan-contract-test.py"
python3 "$script_dir/entity-dynamic-qt6-variant-contract-test.py"
python3 "$script_dir/fbx-writer-qt6-variant-contract-test.py"
python3 "$script_dir/ios-header-guard-test.py"
python3 "$script_dir/keyboard-mouse-qt6-touch-contract-test.py"
python3 "$script_dir/compatibility-debt-test.py"
python3 "$script_dir/core5compat-cmake-contract-test.py"
python3 "$script_dir/ios-static-codec-plugin-contract-test.py"
python3 "$script_dir/ios-static-runtime-linkage-test.py"
python3 "$script_dir/ios-full-client-sccache-contract-test.py"
python3 "$script_dir/compiler-watchdog-test.py"
python3 "$script_dir/qt-per-object-checkpoint-contract-test.py"
python3 "$script_dir/build-heartbeat-test.py"
python3 "$script_dir/runner-telemetry-test.py"
python3 "$script_dir/ios-integrated-recovery-contract-test.py"
python3 "$script_dir/qt-checkpoint-artifact-test.py"
python3 "$script_dir/interface-ios-macos-source-isolation-test.py"
python3 "$script_dir/interface-ios-input-platform-test.py"
python3 "$script_dir/interface-ios-platform-reporting-test.py"
python3 "$script_dir/interface-ios-window-platform-test.py"
python3 "$script_dir/ios-avatar-viewpoint-physics-contract-test.py"
python3 "$script_dir/ios-touch-ui-adapter-contract-test.py"
python3 "$script_dir/shared-ios-desktop-api-isolation-test.py"

# Native renderer source/CMake contracts. Keep this list alphabetical so graph
# drift is reviewable and every contract runs exactly once in the host suite.
readonly rendering_contracts=(
    application-graphics-ios-diagnostics-test.py
    display-plugins-ios-gl-link-removal-test.py
    display-plugins-ios-source-isolation-test.py
    display-plugins-ios-vulkan-cmake-test.py
    gl-canvas-ios-vulkan-isolation-test.py
    gpu-vk-ios-link-contract-test.py
    graphics-engine-backend-include-contract-test.py
    interface-ios-gl-diagnostics-isolation-test.py
    interface-ios-gl-link-audit-test.py
    interface-ios-gl-link-removal-test.py
    interface-ios-gl-telemetry-isolation-test.py
    ios-explicit-gl-api-debt-test.py
    ios-moltenvk-argument-buffer-contract-test.py
    ios-offscreen-qml-backend-audit-test.py
    ios-opengles-compatibility-link-test.py
    ios-render-forensics-contract-test.py
    ios-rendering-backend-contract-test.py
    ios-vulkan-buffer-upload-barrier-test.py
    ios-vulkan-device-creation-contract-test.py
    ios-vulkan-external-texture-gate-test.py
    ios-vulkan-hybrid-gl-migration-test.py
    ios-vulkan-pipeline-key-contract-test.py
    ios-vulkan-platform-backend-test.py
    ios-vulkan-quick-copy-gate-test.py
    ios-vulkan-shader-dialect-contract-test.py
    offscreen-qml-context-contract-test.py
    quick-texture-copy-abi-test.py
    rendering-compatibility-cmake-preflight-test.py
    rendering-integration-inventory-test.py
    rendering-target-ownership-acceptance-test.py
    resource-image-item-ios-contract-test.py
    vk-ios-gl-interop-helper-contract-test.py
    vk-qt-public-api-contract-test.py
    vulkan-display-ios-context-restore-test.py
    vulkan-display-ios-gl-helper-isolation-test.py
    vulkan-display-ios-ktx-capture-gate-test.py
    vulkan-display-ios-main-thread-resize-test.py
    vulkan-display-ios-output-pending-test.py
    vulkan-ios-surface-contract-test.py
)
for contract in "${rendering_contracts[@]}"; do
    python3 "$script_dir/$contract"
done

python3 "$script_dir/sbom-test.py"
python3 "$script_dir/windows-handoff-test.py"
python3 "$script_dir/variant-map-script-value-qt6-contract-test.py"
python3 "$script_dir/release-readiness-test.py"
python3 "$script_dir/ci-log-sanitizer-test.py"
python3 "$script_dir/moltenvk-diagnostics-sanitizer-test.py"
python3 "$script_dir/pending-deep-link-test.py"
python3 "$script_dir/qrc-file-resource-path-contract-test.py"
python3 "$script_dir/overte-address-test.py"
python3 "$script_dir/lifecycle-state-test.py"
python3 "$script_dir/entity-integration-inventory-test.py"
python3 "$script_dir/entity-integration-cmake-gate-test.py"
python3 "$script_dir/entity-gate-telemetry-test.py"
python3 "$script_dir/entity-gate-log-validator-test.py"
python3 "$script_dir/entity-evidence-handoff-test.py"
python3 "$script_dir/v8-ios-checkpoint-contract-test.py"
python3 "$script_dir/v8-build-plan-test.py"
python3 "$script_dir/sccache-stats-report-test.py"
python3 "$script_dir/../tools/tests/test-prepare-qt-ios.py"
python3 "$script_dir/../tools/tests/test-build-qt-ios-from-source.py"
bash -n "$script_dir/../build-ios.sh"
cmake -P "$script_dir/qt-compat-test.cmake"
cmake -P "$script_dir/qt5-compat-test.cmake"
cmake -P "$script_dir/find-moltenvk-test.cmake"
