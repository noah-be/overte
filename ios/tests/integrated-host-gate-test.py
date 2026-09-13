#!/usr/bin/env python3
"""Exercise the reusable workflow's real same-revision host-test gate."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import re
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[2]
integrated = (ROOT / ".github/workflows/ios-integrated.yml").read_text()
bootstrap = (ROOT / ".github/workflows/ios-bootstrap.yml").read_text()


def job(workflow, name):
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:|\Z)",
                      workflow.split("\njobs:\n", 1)[1], re.M | re.S)
    assert match, name
    return match.group(1)


dispatch, call = integrated.split("  workflow_call:\n", 1)
assert "validated_host_contracts_sha" not in dispatch, "dispatch must run its own checks"
assert re.search(r'''validated_host_contracts_sha:\n(?:.*\n)*?        default: (?:''|"")''', call)

host = job(integrated, "host-contracts")
gate = host.split("      - name: Validate same-revision host contract handoff\n", 1)[1]
gate = gate.split("\n      - name:", 1)[0]
assert "VALIDATED_SHA: ${{ inputs.validated_host_contracts_sha }}" in gate
assert "SOURCE_SHA: ${{ github.sha }}" in gate
shell = textwrap.dedent(gate.split("        run: |\n", 1)[1])
source = "a" * 40
for validated, success in [("", True), (source, True), ("b" * 40, False),
                           ("$(exit 0)", False), (source + "\n", False)]:
    result = subprocess.run(["bash", "-e", "-c", shell],
                            env={**os.environ, "VALIDATED_SHA": validated,
                                 "SOURCE_SHA": source},
                            capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) == success, (validated, result.stderr)
    if not success:
        assert "another source revision" in result.stderr

for name in ["Check out requested revision", "Install host concurrency regression dependencies",
             "Run device-free contracts"]:
    step = host.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
    assert "if: inputs.validated_host_contracts_sha == ''" in step, name
assert "qt6-base-dev pkg-config" in host
assert "OVERTE_HOST_TEST_NETWORK_RUNNER:" in host
assert "run: ios/tests/run-tests.sh" in host
assert "needs: host-contracts" in job(integrated, "v8-checkpoint")
assert "needs: [host-contracts, v8-checkpoint]" in job(integrated, "integrated-configure")

for name in ["integrated-ios-after-qt", "integrated-ios-from-checkpoints"]:
    caller = job(bootstrap, name)
    assert "validated_host_contracts_sha: ${{ github.sha }}" in caller
    assert "uses: ./.github/workflows/ios-integrated.yml" in caller
assert "needs: host-contracts" in job(bootstrap, "integrated-ios-from-checkpoints")
assert "needs: provision-qt-ios" in job(bootstrap, "integrated-ios-after-qt")
assert "needs: host-contracts" in job(bootstrap, "provision-qt-ios")
print("PASS integrated host gate: exact SHA reuse, wrong revision rejection, standalone checks, caller dependencies")
