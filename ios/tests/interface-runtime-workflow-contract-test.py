#!/usr/bin/env python3
"""Fail-closed contracts for Full Client simulator and protected-iPad automation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SIMULATOR = ROOT / ".github/workflows/ios-interface-simulator-acceptance.yml"
IPAD = ROOT / ".github/workflows/ios-ipad-runtime-acceptance.yml"
POLICY = ROOT / "ios/tests/interface-runtime-automation.json"
DEVICE_MATRIX = ROOT / "ios/tests/device-acceptance.json"
RUN_TESTS = ROOT / "ios/tests/run-tests.sh"
PINNED_ACTION = re.compile(r"^\s*uses:\s+[^\s]+@[0-9a-f]{40}(?:\s+#.*)?$", re.MULTILINE)


def require(text: str, pattern: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)


def main() -> None:
    simulator = SIMULATOR.read_text(encoding="utf-8")
    ipad = IPAD.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    matrix = json.loads(DEVICE_MATRIX.read_text(encoding="utf-8"))
    runner = RUN_TESTS.read_text(encoding="utf-8")

    assert policy["policy"] == {
        "fullClientOnly": True,
        "bootstrapEvidenceCountsAsInterfaceAcceptance": False,
        "simulatorEvidenceCountsAsPhysicalDeviceAcceptance": False,
        "rawRuntimeLogsMayBeUploaded": False,
    }
    tiers = {tier["id"]: tier for tier in policy["tiers"]}
    assert tiers["full-client-simulator"]["status"] == "prepared"
    assert tiers["full-client-ipad"]["status"] == "prepared"
    matrix_cases = {case["id"] for case in matrix["cases"]}
    declared_runtime_cases = {case["id"] for case in policy["runtimeCases"]}
    hardware_remainder = set(policy["hardwareOnlyRemainder"])
    assert matrix_cases == declared_runtime_cases | hardware_remainder
    assert declared_runtime_cases.isdisjoint(hardware_remainder)

    for name, workflow in (("simulator", simulator), ("ipad", ipad)):
        require(workflow, r"^on:\n\s+workflow_dispatch:\s*$", f"{name} must be dispatch-only")
        assert "pull_request:" not in workflow and "push:" not in workflow
        require(workflow, r"permissions:\n\s+actions: read\n\s+contents: read", f"{name} permissions widened")
        assert "secrets." not in workflow, f"{name} must not consume repository secrets"
        assert "cancel-in-progress: false" in workflow
        assert "persist-credentials: false" in workflow
        assert "candidate_run_attempt:" in workflow
        assert 'payload.get("head_sha")' in workflow
        assert 'repository.get("full_name")' in workflow
        assert 'payload.get("conclusion") != "success"' in workflow
        assert 'payload.get("head_branch") != "apple-ios"' in workflow
        assert "verify-runtime-candidate.py" in workflow
        for line in workflow.splitlines():
            if line.lstrip().startswith("uses:"):
                assert PINNED_ACTION.fullmatch(line), f"unpinned action in {name}: {line}"

    assert "matrix:\n        family: [iphone, ipad]" in simulator
    assert "runs-on: macos-26" in simulator
    assert "--mode simulator" in simulator
    assert "interface-simulator-smoke.sh" in simulator
    assert "simctl openurl" not in simulator, "the runtime helper must own URL delivery"
    assert '"requestedDestination": "hifi://overte_hub"' in simulator
    assert '"destinationBoundToGates": False' in simulator
    assert "candidate/${{ steps.candidate.outputs" not in simulator
    assert '--expected-source-revision "${{ inputs.' not in simulator
    assert "raw" not in "\n".join(
        line for line in simulator.splitlines() if "${{ env.RUNTIME_ROOT }}/evidence/" in line
    ).lower()

    assert "environment: ios-ipad-device-acceptance" in ipad
    assert "runs-on: [self-hosted, macOS, ARM64, overte-ios-ipad]" in ipad
    assert '"INSTALL $APPROVED_SHA256"' in ipad
    assert "--mode ipad" in ipad
    assert "verify-ipad-signing.py" in ipad
    assert "ipad-device-acceptance.py" in ipad
    assert "candidate/${{ steps.candidate.outputs" not in ipad
    assert '--expected-source-revision "${{ inputs.' not in ipad
    assert "OVERTE_IOS_IPAD_DEVICE_ID_FILE" not in ipad, "device identity must stay runner-local"
    assert "security import" not in ipad and "codesign --sign" not in ipad
    uploaded = "\n".join(
        line for line in ipad.splitlines() if "${{ env.RUNTIME_ROOT }}/evidence/" in line
    )
    assert "console" not in uploaded.lower() and "devices.json" not in uploaded
    assert "embedded.mobileprovision" not in uploaded

    for test in (
        "runtime-candidate-verifier-test.py",
        "interface-simulator-smoke-test.py",
        "ipad-device-acceptance-test.py",
        "ipad-signing-verifier-test.py",
        "interface-runtime-workflow-contract-test.py",
    ):
        assert runner.count(test) == 1, f"{test} must be registered exactly once"

    print("PASS Full Client simulator and protected-iPad workflow contracts")


if __name__ == "__main__":
    main()
