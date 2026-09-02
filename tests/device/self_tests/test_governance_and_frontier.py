#!/usr/bin/env python3
"""Device-free proofs for the acceptance-governance contracts."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from acceptance_policy import load_policy  # noqa: E402
from contracts import validate_operation_arguments, validate_operation_result  # noqa: E402


class GovernanceAndFrontierTest(unittest.TestCase):
    def test_frontier_operation_contracts_are_closed(self):
        self.assertEqual({"mode": "abort"}, validate_operation_arguments(
            "app.crash", {"mode": "abort"}))
        self.assertEqual({"permissionId": "microphone", "state": "denied"},
                         validate_operation_arguments("permission.set", {
                             "permissionId": "microphone", "state": "denied"}))
        self.assertEqual({"applied": True}, validate_operation_result(
            "app.upgrade", {"applied": True}))
        shared = {"schemaVersion": 1, "entityName": "OVERTE_E2E_SHARED_COLOR",
                  "value": "blue", "revision": 1,
                  "actorId": "OVERTE_E2E_ACTOR_FIXTURE"}
        self.assertEqual(shared, validate_operation_result(
            "collaboration.snapshot", shared))
        for operation, arguments in (
                ("app.crash", {"mode": "kill"}),
                ("app.upgrade", {"fromVersion": "1", "toVersion": "1"}),
                ("permission.set", {"permissionId": "camera", "state": "denied"}),
                ("collaboration.edit", {"entityName": "OTHER", "value": "blue"})):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                validate_operation_arguments(operation, arguments)

    def test_policy_and_version_registries(self):
        commands = ([
            sys.executable, str(DEVICE_ROOT / "validate_policy.py"),
            "--policy", str(DEVICE_ROOT / "acceptance-policy.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
        ], [
            sys.executable, str(DEVICE_ROOT / "validate_contract_versions.py"),
            "--registry", str(DEVICE_ROOT / "contract-versions.json"),
        ])
        for command in commands:
            with self.subTest(command=Path(command[1]).name):
                result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, check=False)
                self.assertEqual(0, result.returncode, result.stdout)

        evidence = json.loads(
            (DEVICE_ROOT / "acceptance-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual([], evidence["evidence"])

    def test_acceptance_promotion_requires_matching_real_run_evidence(self):
        with tempfile.TemporaryDirectory(prefix="overte-policy-") as temporary:
            root = Path(temporary)
            policy = json.loads(
                (DEVICE_ROOT / "acceptance-policy.json").read_text(encoding="utf-8"))
            policy["platforms"]["linux"]["suites"]["smoke"] = {
                "state": "accepted", "evidence": ["missing-real-run"]}
            policy_path = root / "acceptance-policy.json"
            policy_path.write_text(json.dumps(policy, sort_keys=True) + "\n",
                                   encoding="utf-8")
            (root / "acceptance-evidence.json").write_text(json.dumps({
                "schemaVersion": 1, "contractVersion": 1, "evidence": [],
            }, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mismatched acceptance evidence"):
                load_policy(policy_path, DEVICE_ROOT / "catalog.json")

    def test_history_analysis_keeps_product_failures_red(self):
        with tempfile.TemporaryDirectory(prefix="overte-history-") as temporary:
            root = Path(temporary)
            results = []
            for index, status in enumerate(("passed", "failed"), 1):
                run = root / f"run-{index}"
                run.mkdir()
                (run / "run-manifest.json").write_text(json.dumps({
                    "schemaVersion": 1,
                    "platform": "linux",
                    "suite": "smoke",
                    "status": status,
                    "durationSeconds": float(index),
                }) + "\n", encoding="utf-8")
                (run / "summary.json").write_text(json.dumps({
                    "schemaVersion": 1,
                    "results": [{"status": status}],
                }) + "\n", encoding="utf-8")
                results.extend(["--result", str(run)])
            output = root / "history.json"
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "analyze_history.py"),
                *results, "--quarantine", "linux:smoke", "--output", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            history = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("failed", history["status"])
            self.assertEqual(2, history["cells"][0]["runs"])
            self.assertTrue(history["cells"][0]["quarantined"])

    def test_artifact_audit_rejects_secret_keys_without_echoing_values(self):
        with tempfile.TemporaryDirectory(prefix="overte-audit-") as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            private_value = "private-value-for-self-test"
            (artifacts / "bad.json").write_text(
                json.dumps({"controlToken": private_value}) + "\n", encoding="utf-8")
            output = root / "audit.json"
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "audit_artifacts.py"),
                "--result", str(artifacts), "--forbid-value", private_value,
                "--output", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(1, result.returncode, result.stdout)
            self.assertNotIn(private_value, result.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                ["credential-key", "private-selector"],
                [finding["category"] for finding in report["findings"]])


if __name__ == "__main__":
    unittest.main()
