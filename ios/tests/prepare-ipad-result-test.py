#!/usr/bin/env python3
"""Host contracts for the privacy-minimal iPad result template."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "ios/tools/prepare-ipad-result.py"
MATRIX = ROOT / "ios/tests/device-acceptance.json"


def load_validator():
    path = ROOT / "ios/tools/validate-device-results.py"
    spec = importlib.util.spec_from_file_location("device_results", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with tempfile.TemporaryDirectory(prefix="overte-ipad-template-") as temporary:
    output = Path(temporary) / "ipad-result.json"
    result = subprocess.run(
        [
            sys.executable, str(TOOL), "--matrix", str(MATRIX), "--output", str(output),
            "--source-revision", "a" * 40, "--ipa-sha256", "b" * 64,
            "--xcode", "26.6 (17F113)", "--sdk", "26.5", "--os-version", "26.0",
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = json.loads(output.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert payload["device"] == {"osVersion": "26.0"}
    assert [item["id"] for item in payload["results"]] == [item["id"] for item in matrix["cases"]]
    assert all(item["outcome"] == "blocked" and item["notes"] for item in payload["results"])
    load_validator().validate_result(matrix, payload, output)

    repeated = subprocess.run(
        [
            sys.executable, str(TOOL), "--output", str(output),
            "--source-revision", "a" * 40, "--ipa-sha256", "b" * 64,
            "--xcode", "26.6", "--sdk", "26.5", "--os-version", "26.0",
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert repeated.returncode == 1 and "already exists" in repeated.stderr

print("PASS privacy-minimal iPad result template contracts")
