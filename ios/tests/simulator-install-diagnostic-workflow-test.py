#!/usr/bin/env python3
"""Protect the no-rebuild CoreSimulator installation diagnostic."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-simulator-install-diagnostic.yml").read_text(encoding="utf-8")
RUN_TESTS = (ROOT / "ios/tests/run-tests.sh").read_text(encoding="utf-8")


assert re.search(r"^\s+workflow_dispatch:\s*$", WORKFLOW, re.MULTILINE)
assert "pull_request:" not in WORKFLOW
assert re.search(
    r"push:\n\s+branches:\n\s+- apple-ios\n\s+paths:\n"
    r"\s+- [.]github/workflows/ios-simulator-install-diagnostic[.]yml",
    WORKFLOW,
)
assert "inputs.source_run_id || '31818380576'" in WORKFLOW
assert "actions: read" in WORKFLOW and "contents: read" in WORKFLOW
assert "persist-credentials: false" in WORKFLOW
for line in WORKFLOW.splitlines():
    if line.lstrip().startswith("uses:"):
        assert re.search(r"@[0-9a-f]{40}(?:\s+#.*)?$", line), line

assert "actions/download-artifact@" in WORKFLOW
assert "run-id: ${{ env.SOURCE_RUN_ID }}" in WORKFLOW
assert "shasum -a 256" in WORKFLOW
assert "expected one available runtime" in WORKFLOW
for version, build in (("26.4.1", "17E202"), ("26.5", "17F42"), ("26.6", "17F113")):
    assert version in WORKFLOW and build in WORKFLOW
assert "simctl install" in WORKFLOW
assert "codesign --force --deep --sign - --timestamp=none" in WORKFLOW
assert "cmake --build" not in WORKFLOW and "build-ios.sh build" not in WORKFLOW
assert "all bounded install variants failed" in WORKFLOW
assert "retention-days: 14" in WORKFLOW
assert RUN_TESTS.count("simulator-install-diagnostic-workflow-test.py") == 1

print("PASS no-rebuild CoreSimulator installation diagnostic workflow contract")
