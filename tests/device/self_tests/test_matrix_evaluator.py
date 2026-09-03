#!/usr/bin/env python3
"""Contract tests for selector-free cross-platform result aggregation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


DEVICE_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = DEVICE_ROOT / "evaluate_matrix.py"


class MatrixEvaluatorTest(unittest.TestCase):
    def write_run(self, root: Path, name: str, *, platform: str, suite: str,
                  status: str = "passed", result_status: str = "passed",
                  complete: bool = True) -> Path:
        directory = root / name
        directory.mkdir()
        manifest = {
            "schemaVersion": 1, "adapter": "contract-adapter", "suite": suite,
            "platform": platform, "physical": True, "requireComplete": complete,
            "capabilities": ["app.process"], "modules": ["contract-module"],
            "startedEpochMs": 1000, "finishedEpochMs": 2000,
            "durationSeconds": 1.0, "status": status,
        }
        summary = {
            "schemaVersion": 1, "adapter": "contract-adapter", "suite": suite,
            "status": status, "results": [{
                "id": "contract-module", "description": "Contract module",
                "status": result_status, "returncode": 0 if result_status == "passed" else 1,
                "durationSeconds": 1.0,
            }],
        }
        (directory / "run-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return directory

    def evaluate(self, root: Path, runs: list[Path], required: list[str]):
        output = root / "matrix"
        command = [sys.executable, str(EVALUATOR), "--output-dir", str(output)]
        for run in runs:
            command += ["--result", str(run)]
        for gate in required:
            command += ["--require", gate]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        return result, output

    def test_complete_physical_runs_satisfy_cross_platform_gates(self):
        with tempfile.TemporaryDirectory(prefix="overte-matrix-") as temporary:
            root = Path(temporary)
            runs = [
                self.write_run(root, "private-target-one", platform="android",
                               suite="e2e-core"),
                self.write_run(root, "private-target-two", platform="ios",
                               suite="interaction-smoke"),
            ]
            result, output = self.evaluate(
                root, runs, ["android:e2e-core", "ios:interaction-smoke"])
            self.assertEqual(0, result.returncode, result.stdout)
            payload = json.loads((output / "matrix-summary.json").read_text(
                encoding="utf-8"))
            self.assertEqual("passed", payload["status"])
            serialized = json.dumps(payload)
            self.assertNotIn("private-target-one", serialized)
            self.assertNotIn("private-target-two", serialized)
            self.assertEqual(["run-001", "run-002"],
                             [run["runId"] for run in payload["runs"]])

    def test_missing_or_incomplete_gate_is_an_infrastructure_error(self):
        with tempfile.TemporaryDirectory(prefix="overte-matrix-") as temporary:
            root = Path(temporary)
            run = self.write_run(root, "run", platform="android", suite="e2e-core",
                                 complete=False)
            result, output = self.evaluate(root, [run], ["android:e2e-core"])
            self.assertEqual(2, result.returncode, result.stdout)
            payload = json.loads((output / "matrix-summary.json").read_text())
            self.assertEqual(["android:e2e-core"], payload["missing"])
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("1", junit.attrib["errors"])

    def test_product_failure_remains_distinct_from_infrastructure(self):
        with tempfile.TemporaryDirectory(prefix="overte-matrix-") as temporary:
            root = Path(temporary)
            run = self.write_run(root, "run", platform="linux", suite="e2e-core",
                                 status="failed", result_status="failed")
            result, output = self.evaluate(root, [run], ["linux:e2e-core"])
            self.assertEqual(1, result.returncode, result.stdout)
            payload = json.loads((output / "matrix-summary.json").read_text())
            self.assertEqual("failed", payload["status"])
            self.assertEqual([], payload["missing"])
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("1", junit.attrib["failures"])
            self.assertEqual("0", junit.attrib["errors"])


if __name__ == "__main__":
    unittest.main()
