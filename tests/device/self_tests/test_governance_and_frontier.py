#!/usr/bin/env python3
"""Device-free proofs for orchestration, governance and frontier suites."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from contracts import validate_operation_arguments, validate_operation_result


DOMAIN_ID = "11111111-2222-4333-8444-555555555555"
DOMAIN_MARKERS = [
    "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_FLOOR",
    "OVERTE_E2E_DOMAIN_NORTH", "OVERTE_E2E_DOMAIN_ORIGIN",
]


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

    def environment(self, root: Path, failures: str = "") -> dict[str, str]:
        return os.environ | {
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": "2",
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": DOMAIN_ID,
            "OVERTE_MOCK_E2E_DOMAIN_ID": DOMAIN_ID,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(DOMAIN_MARKERS),
            "OVERTE_E2E_UPGRADE_FROM_VERSION": "1.0.0",
            "OVERTE_E2E_UPGRADE_TO_VERSION": "2.0.0",
            "OVERTE_MOCK_E2E_FAILURES": failures,
        }

    def run_suite(self, root: Path, suite: str, failures: str = "") -> tuple[Path, subprocess.CompletedProcess]:
        output = root / "result"
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", suite, "--allow-virtual", "--require-complete",
            "--output-dir", str(output),
        ], env=self.environment(root, failures), text=True,
           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return output, result

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

    def test_unified_fixture_scene_only_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="overte-orchestrator-") as temporary:
            output = Path(temporary) / "fixture"
            process = subprocess.Popen([
                sys.executable, str(DEVICE_ROOT / "fixture/orchestrate.py"),
                "--scene-only", "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                ready = json.loads(process.stdout.readline())
                self.assertTrue(ready["sceneReady"])
                self.assertFalse(ready["domainReady"])
                environment = json.loads(
                    Path(ready["environmentFile"]).read_text(encoding="utf-8"))
                self.assertIn("OVERTE_E2E_SCENE_URL", environment["environment"])
                self.assertNotIn("OVERTE_E2E_DOMAIN_CONTROL_TOKEN", environment["environment"])
                self.assertEqual(0o600, Path(ready["environmentFile"]).stat().st_mode & 0o777)
            finally:
                process.terminate()
                process.communicate(timeout=10)

    def test_frontier_suites_positive_and_negative(self):
        for suite in ("entity-sync-smoke", "permission-recovery",
                      "crash-recovery-under-load", "update-upgrade"):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as temporary:
                output, result = self.run_suite(Path(temporary), suite)
                self.assertEqual(0, result.returncode, result.stdout)
                self.assertEqual("passed", json.loads(
                    (output / "summary.json").read_text(encoding="utf-8"))["status"])
        failures = {
            "entity-sync-smoke": "entity-sync-duplicate",
            "permission-recovery": "permission-deny-missing",
            "update-upgrade": "upgrade-version-unchanged",
        }
        for suite, failure in failures.items():
            with self.subTest(suite=suite, failure=failure), tempfile.TemporaryDirectory() as temporary:
                output, result = self.run_suite(Path(temporary), suite, failure)
                self.assertEqual(1, result.returncode, result.stdout)
                statuses = {item["status"] for item in json.loads(
                    (output / "summary.json").read_text(encoding="utf-8"))["results"]}
                self.assertIn("failed", statuses)

    def test_pipeline_timeline_artifacts_history_and_security(self):
        with tempfile.TemporaryDirectory(prefix="overte-pipeline-") as temporary:
            root = Path(temporary)
            output = root / "pipeline"
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "pipeline.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--policy", str(DEVICE_ROOT / "acceptance-policy.json"),
                "--platform", "mock", "--suite", "smoke", "--allow-virtual",
                "--output-dir", str(output),
            ], env=self.environment(root), text=True, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            run = output / "smoke/attempt-01"
            self.assertTrue((run / "artifact-manifest.json").is_file())
            events = [json.loads(line) for line in
                      (run / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(list(range(1, len(events) + 1)),
                             [item["sequence"] for item in events])
            history = root / "history.json"
            trend = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "analyze_history.py"),
                "--result", str(run), "--output", str(history),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, trend.returncode, trend.stdout)
            self.assertEqual(1, json.loads(history.read_text(encoding="utf-8"))["cells"][0]["runs"])

            matrix = root / "matrix"
            promoted_policy = json.loads(
                (DEVICE_ROOT / "acceptance-policy.json").read_text(encoding="utf-8"))
            promoted_policy["platforms"]["mock"]["suites"]["smoke"] = {
                "state": "required", "evidence": "self-test run"}
            policy_path = root / "promoted-policy.json"
            policy_path.write_text(json.dumps(promoted_policy, sort_keys=True) + "\n",
                                   encoding="utf-8")
            evaluated = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "evaluate_matrix.py"),
                "--result", str(run), "--output-dir", str(matrix),
                "--policy", str(policy_path),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--allow-virtual-platform", "mock",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, evaluated.returncode, evaluated.stdout)
            matrix_value = json.loads(
                (matrix / "matrix-summary.json").read_text(encoding="utf-8"))
            self.assertIn("mock:smoke", matrix_value["required"])
            self.assertNotIn("mock:smoke", matrix_value["missing"])

            leak = root / "leak"
            leak.mkdir()
            (leak / "bad.json").write_text('{"controlToken":"not-a-real-secret"}\n',
                                            encoding="utf-8")
            audit = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "audit_artifacts.py"),
                "--result", str(leak), "--output", str(root / "audit.json"),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(1, audit.returncode, audit.stdout)
            report = json.loads((root / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual("credential-key", report["findings"][0]["category"])

    def test_pipeline_retries_only_infrastructure_errors(self):
        def pipeline(root: Path, suite: str, extra: dict[str, str]):
            output = root / "pipeline"
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "pipeline.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--policy", str(DEVICE_ROOT / "acceptance-policy.json"),
                "--platform", "mock", "--suite", suite, "--allow-virtual",
                "--retry-infrastructure", "2", "--output-dir", str(output),
            ], env=self.environment(root) | extra, text=True, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT, check=False)
            return output, result

        with tempfile.TemporaryDirectory(prefix="overte-product-no-retry-") as temporary:
            output, result = pipeline(Path(temporary), "permission-recovery", {
                "OVERTE_MOCK_E2E_FAILURES": "permission-deny-missing"})
            self.assertEqual(1, result.returncode, result.stdout)
            self.assertTrue((output / "permission-recovery/attempt-01").is_dir())
            self.assertFalse((output / "permission-recovery/attempt-02").exists())
        with tempfile.TemporaryDirectory(prefix="overte-infra-retry-") as temporary:
            output, result = pipeline(Path(temporary), "smoke", {
                "OVERTE_MOCK_MISSING_CAPABILITY": "app.launch"})
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertTrue((output / "smoke/attempt-03").is_dir())


if __name__ == "__main__":
    unittest.main()
