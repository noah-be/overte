#!/usr/bin/env python3
"""Protect the real Full Client simulator world/screenshot acceptance path."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-world-runtime.yml").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / ".github/workflows/ios-bootstrap.yml").read_text(encoding="utf-8")
QT = (ROOT / ".github/workflows/ios-qt-source.yml").read_text(encoding="utf-8")
MOLTENVK_SIMULATOR = (ROOT / "ios/moltenvk-simulator.env").read_text(encoding="utf-8")
RUN_TESTS = (ROOT / "ios/tests/run-tests.sh").read_text(encoding="utf-8")
SMOKE = (ROOT / "ios/ci/interface-world-simulator-smoke.sh").read_text(encoding="utf-8")
PINNED_ACTION = re.compile(r"^\s*uses:\s+[^\s]+@[0-9a-f]{40}(?:\s+#.*)?$", re.MULTILINE)


def require(text: str, pattern: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)


require(WORKFLOW, r"^on:\n\s+workflow_call:\s*$", "world evidence must run only through its gated caller")
assert "pull_request:" not in WORKFLOW and "push:" not in WORKFLOW
assert "cancel-in-progress: false" in WORKFLOW
assert "persist-credentials: false" in WORKFLOW
for line in WORKFLOW.splitlines():
    if line.lstrip().startswith("uses:") and not line.lstrip().startswith("uses: ./"):
        assert PINNED_ACTION.fullmatch(line), f"unpinned action: {line}"

require(WORKFLOW, r"qt-simulator:[\s\S]*uses: \./\.github/workflows/ios-qt-source\.yml[\s\S]*target_sdk: iphonesimulator", "world workflow must provision simulator Qt")
require(QT, r"target_sdk:[\s\S]*iphoneos[\s\S]*iphonesimulator", "Qt provisioner must keep device and simulator explicit")
require(WORKFLOW, r"OVERTE_IOS_V8_PLATFORM: simulator", "V8 must be compiled and validated for the simulator")
require(WORKFLOW, r"v8-build-plan\.py identity[\s\S]*--platform simulator", "simulator V8 must use the canonical output identity")
assert 'recipe_hash="$(shasum -a 256 ios/v8.env ios/tools/build-v8-ios.sh' not in WORKFLOW
for checkpoint_step in (
    "Restore validated simulator V8 cache",
    "Restore durable simulator V8 checkpoint",
    "Restore reviewed legacy simulator V8 checkpoint for v2 promotion",
    "Restore simulator V8 compiler recovery checkpoint",
    "Report simulator V8 checkpoint decision",
    "Build pinned simulator V8",
):
    assert checkpoint_step in WORKFLOW
assert "Simulator V8 sccache state before rebuild" in WORKFLOW
assert "Simulator V8 sccache state after rebuild" in WORKFLOW
assert "retention-days: 90" in WORKFLOW
require(WORKFLOW, r"target-sdk iphonesimulator --print-plan", "restored Qt must prove simulator provenance")
require(WORKFLOW, r'QT_OSX_ARCHITECTURES "arm64"', "restored simulator Qt must prove its arm64 target architecture")
require(MOLTENVK_SIMULATOR, r"OVERTE_IOS_MOLTENVK_SIMULATOR_ARCHIVE=MoltenVK-all\.tar", "simulator MoltenVK must use the multi-slice archive")
require(MOLTENVK_SIMULATOR, r"OVERTE_IOS_MOLTENVK_SIMULATOR_SHA256=[0-9a-f]{64}", "simulator MoltenVK digest must be pinned")
require(WORKFLOW, r"overte-moltenvk-ios-simulator-v1", "simulator MoltenVK must have a distinct cache namespace")
require(WORKFLOW, r"source ios/moltenvk-simulator\.env", "simulator MoltenVK pin must drive the download")
require(WORKFLOW, r"OVERTE_IOS_MOLTENVK_SIMULATOR_SHA256", "simulator MoltenVK download must verify its digest")
require(WORKFLOW, r"deps --platform simulator --graphics-toolchain", "Conan must resolve the simulator graph")
require(WORKFLOW, r"configure --platform simulator --client-graph", "the real Full Client simulator graph must be configured")
require(WORKFLOW, r"cmake --build build-ios/simulator[\s\S]*--target Overte", "the real Overte client target must be built")
require(WORKFLOW, r"package-client --platform simulator --configuration Release", "the tested simulator app must be packaged")
require(WORKFLOW, r"verify-runtime-candidate\.py build-ios/artifacts[\s\S]*--mode simulator", "candidate platform and Mach-O must be verified")
assert WORKFLOW.count("*-OverteIOSClient-Release-simulator-symbols.zip") == 2

for phase in (
    "v8-simulator-build",
    "conan-simulator-dependencies",
    "client-simulator-configure",
    "client-simulator-build",
):
    assert f"--phase {phase}" in WORKFLOW, f"missing telemetry for {phase}"
assert WORKFLOW.count("--inactivity-timeout") >= 4
assert WORKFLOW.count("--max-runtime") >= 4
assert "compiler-live.jsonl" in WORKFLOW
assert "sccache --show-stats" in WORKFLOW
assert "SCCACHE_GHA_VERSION=overte-ios-world-client-objects" in WORKFLOW

require(WORKFLOW, r"https://mv\.overte\.org/server/api/v1/places/overte_hub", "online place must be resolved authoritatively at runtime")
require(WORKFLOW, r'domain\.get\("active"\) is not True', "inactive online worlds must fail closed")
require(WORKFLOW, r"/Applications/Xcode_26[.]5[.]app/Contents/Developer", "runtime install must avoid the Xcode 26.6 CoreSimulator regression")
require(WORKFLOW, r'xcode_build[^\n]*17F42', "stable CoreSimulator selection must verify the reviewed Xcode build")
require(WORKFLOW, r"OVERTE_IOS_WORLD_DIAGNOSTICS_DIR:.*world-raw-diagnostics", "simctl failures must be retained for sanitization")
world_step = WORKFLOW[
    WORKFLOW.index("Load serverless and online worlds with screenshots"):
    WORKFLOW.index("Upload simulator candidate and world screenshot evidence")
]
for family in ("iphone ipad",):
    assert f"for family in {family}" in world_step
for scenario in ("serverless -", 'online "$ONLINE_DOMAIN"'):
    assert scenario in world_step
assert "interface-world-simulator-smoke.sh" in world_step
assert "validate-world-evidence-set.py" in world_step
assert "--source-revision \"$GITHUB_SHA\"" in world_step
assert "steps.candidate.outputs.sha256" in world_step

upload = WORKFLOW[
    WORKFLOW.index("Upload simulator candidate and world screenshot evidence"):
    WORKFLOW.index("Sanitize world-build failure diagnostics")
]
for retained in ("*.png", "*-screenshot.json", "*-runtime.json", "world-evidence-set.json"):
    assert retained in upload
assert "*.log" not in upload and "raw" not in upload.lower()
assert "retention-days: 14" in upload

failure_candidate = WORKFLOW[
    WORKFLOW.index("Preserve simulator candidate after runtime failure"):
    WORKFLOW.index("Sanitize world-build failure diagnostics")
]
assert "if: failure()" in failure_candidate
assert "*-OverteIOSClient-Release-simulator.zip" in failure_candidate
assert "*-OverteIOSClient-Release-simulator-symbols.zip" in failure_candidate
assert "*-failure.png" in failure_candidate
assert "if-no-files-found: error" in failure_candidate
require(
    WORKFLOW,
    r"Sanitize world-build failure diagnostics[\s\S]*Overte[.]app[.]dSYM/Contents/Resources/DWARF/Overte[\s\S]*[*]-overte-crash-report[.]log[\s\S]*symbolicate-simulator-crash[.]py",
    "world crashes must be symbolicated with the preserved dSYM before upload",
)
require(
    WORKFLOW,
    r"if ! python3 ios/tools/symbolicate-simulator-crash[.]py[\s\S]*preserving sanitized raw crash diagnostics",
    "driver-only crashes must not suppress the sanitized raw diagnostics",
)
assert "*-moltenvk-shaders" in WORKFLOW
assert "${stem}-overte-crash-report.log" in SMOKE
assert "${stem}-simmetalhost-crash-report.log" in SMOKE
assert "prepare-moltenvk-diagnostics.py" in WORKFLOW
assert "MoltenVK diagnostics failed validation and will not be uploaded" in WORKFLOW

require(BOOTSTRAP, r"world_evidence:[\s\S]*type: boolean[\s\S]*default: false", "manual world acceptance needs an explicit opt-in")
require(
    BOOTSTRAP,
    r"concurrency:[\s\S]*ios-bootstrap-\$\{\{ github[.]ref \}\}-\$\{\{[\s\S]*inputs[.]world_evidence[\s\S]*'world'[\s\S]*inputs[.]integrated[\s\S]*'integrated'[\s\S]*'smoke'",
    "world, integrated, and smoke runs must not share one branch-wide mutex",
)
require(BOOTSTRAP, r"contains\(github\.event\.head_commit\.message, '\[ios-worlds\]'\)", "branch world acceptance needs an explicit marker")
require(BOOTSTRAP, r"world-runtime-evidence:[\s\S]*needs: host-contracts[\s\S]*uses: \./\.github/workflows/ios-world-runtime\.yml", "world runtime must wait for all host contracts")
assert RUN_TESTS.count("world-runtime-workflow-contract-test.py") == 1
assert RUN_TESTS.count("interface-world-simulator-smoke-test.py") == 1
assert RUN_TESTS.count("world-runtime-evidence-test.py") == 1

print("PASS real Full Client serverless/online simulator screenshot workflow contract")
