#!/usr/bin/env python3
"""Device-free positive and negative contracts for the controlled asset suite."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from urllib.parse import urlencode
from urllib.request import urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from contracts import validate_operation_arguments, validate_probe_snapshot  # noqa: E402
from test_vertical_locomotion import snapshot as probe_snapshot  # noqa: E402


class AssetLoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temporary = tempfile.TemporaryDirectory(prefix="overte-asset-fixture-")
        cls.ready = Path(cls.fixture_temporary.name) / "ready.json"
        cls.fixture = subprocess.Popen([
            sys.executable, str(DEVICE_ROOT / "fixture/serve.py"),
            "--ready-file", str(cls.ready),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 5
        while not cls.ready.exists() and time.monotonic() < deadline:
            if cls.fixture.poll() is not None:
                break
            time.sleep(0.02)
        if not cls.ready.exists():
            stdout, stderr = cls.fixture.communicate(timeout=2)
            raise RuntimeError(f"fixture failed: {stdout}\n{stderr}")
        cls.metadata = json.loads(cls.ready.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.terminate()
        cls.fixture.communicate(timeout=5)
        cls.fixture_temporary.cleanup()

    def run_asset_suite(self, mock_flag: str | None = None):
        temporary = tempfile.TemporaryDirectory(prefix="overte-asset-suite-")
        root = Path(temporary.name)
        asset = self.metadata["asset"]
        environment = os.environ.copy()
        environment.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "mock-state.json"),
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": "1",
            "OVERTE_E2E_ASSET_REQUEST_ID": uuid.uuid4().hex,
            "OVERTE_E2E_ASSET_ID": asset["id"],
            "OVERTE_E2E_ASSET_URL": asset["url"],
            "OVERTE_E2E_ASSET_TELEMETRY_URL": asset["telemetryUrl"],
            "OVERTE_E2E_ASSET_CONTENT_TYPE": asset["contentType"],
            "OVERTE_E2E_ASSET_SHA256": asset["sha256"],
            "OVERTE_E2E_ASSET_BYTES": str(asset["bytes"]),
            "OVERTE_E2E_ASSET_WIDTH": str(asset["width"]),
            "OVERTE_E2E_ASSET_HEIGHT": str(asset["height"]),
            "OVERTE_E2E_ASSET_ENTITY_NAME": asset["entityName"],
        })
        if mock_flag:
            environment[mock_flag] = "1"
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"), "--suite", "asset-smoke",
            "--target", "mock-e2e-target", "--allow-virtual", "--require-complete",
            "--output-dir", str(root / "results"),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, check=False)
        return temporary, root, result

    def test_asset_suite_selection_preserves_shared_launch_sequence(self):
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", "asset-smoke", "--list",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(
            ["launch-smoke", "asset-load"],
            [line.split(":", 1)[0] for line in result.stdout.splitlines()],
        )

    def test_asset_operation_arguments_are_strict(self):
        valid = {
            "assetId": "texture-rgb-3x1-v1",
            "url": "http://127.0.0.1:18080/asset.png?requestId=one",
            "entityName": "OVERTE_E2E_ASSET_LOAD",
        }
        self.assertEqual(valid, validate_operation_arguments("asset.load", valid))
        for invalid in (
                valid | {"extra": True},
                valid | {"assetId": "Wrong ID"},
                valid | {"url": "file:///tmp/asset.png"},
                valid | {"entityName": "ordinary-entity"}):
            with self.subTest(arguments=invalid), self.assertRaises(ValueError):
                validate_operation_arguments("asset.load", invalid)

    def test_asset_fixture_has_stable_bytes_headers_and_request_telemetry(self):
        asset = self.metadata["asset"]
        request_id = uuid.uuid4().hex
        with urlopen(asset["url"] + "?" + urlencode({"requestId": request_id}),
                     timeout=2) as response:
            payload = response.read()
            self.assertEqual("image/png", response.headers.get_content_type())
            self.assertEqual("no-store", response.headers["Cache-Control"])
        self.assertEqual(asset["bytes"], len(payload))
        self.assertEqual(asset["sha256"], hashlib.sha256(payload).hexdigest())
        query = urlencode({"assetId": asset["id"], "requestId": request_id})
        with urlopen(asset["telemetryUrl"] + "?" + query, timeout=2) as response:
            telemetry = json.load(response)
        self.assertEqual(1, telemetry["completedRequests"])
        self.assertTrue(telemetry["latestCompleted"]["completed"])
        self.assertEqual("no-store", telemetry["latestCompleted"]["cacheControl"])

    def test_mock_runs_complete_asset_smoke_suite_in_one_process(self):
        temporary, root, result = self.run_asset_suite()
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((root / "results/summary.json").read_text())
            self.assertEqual("passed", summary["status"])
            self.assertEqual(
                ["launch-smoke", "asset-load"],
                [entry["id"] for entry in summary["results"]],
            )
            delivery = json.loads(
                (root / "results/modules/asset-load/asset-delivery.json").read_text())
            ready = json.loads(
                (root / "results/modules/asset-load/asset-ready.json").read_text())
            metrics = json.loads(
                (root / "results/modules/asset-load/metrics.json").read_text())
            state = json.loads((root / "mock-state.json").read_text())
            self.assertEqual(1, delivery["completedRequests"])
            self.assertEqual("finished", ready["asset"]["resource"]["state"])
            self.assertEqual("Image", ready["asset"]["entity"]["type"])
            self.assertEqual("mock-e2e-process", metrics["processIdentity"])
            self.assertEqual(1, state["launchCount"])
        finally:
            temporary.cleanup()

    def assert_asset_failure(self, flag: str, expected: str, status: str = "failed") -> None:
        temporary, root, result = self.run_asset_suite(flag)
        try:
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads((root / "results/summary.json").read_text())
            self.assertEqual(["passed", status],
                             [entry["status"] for entry in summary["results"]])
            log = (root / "results/modules/asset-load/module.log").read_text()
            self.assertIn(expected, log)
        finally:
            temporary.cleanup()

    def test_wrong_asset_id_and_url_are_rejected(self):
        cases = (
            ("OVERTE_MOCK_ASSET_WRONG_ID", "wrong asset ID"),
            ("OVERTE_MOCK_ASSET_WRONG_URL", "wrong asset URL"),
        )
        for flag, expected in cases:
            with self.subTest(flag=flag):
                self.assert_asset_failure(flag, expected)

    def test_missing_http_fetch_is_rejected(self):
        self.assert_asset_failure(
            "OVERTE_MOCK_ASSET_SKIP_HTTP", "did not observe a completed asset HTTP request")

    def test_incomplete_probe_asset_data_is_rejected(self):
        self.assert_asset_failure(
            "OVERTE_MOCK_ASSET_INCOMPLETE_PROBE", "requires entity evidence", "error")

    def test_process_restart_during_asset_load_is_rejected(self):
        self.assert_asset_failure("OVERTE_MOCK_ASSET_RESTART", "process restarted")

    def test_asset_that_never_finishes_times_out(self):
        self.assert_asset_failure(
            "OVERTE_MOCK_ASSET_NEVER_FINISH", "timed out waiting for the controlled asset")

    def test_probe_contract_rejects_incomplete_and_inconsistent_asset_evidence(self):
        snapshot = probe_snapshot()
        snapshot["asset"] = {"assetId": "texture-rgb-3x1-v1"}
        with self.assertRaisesRegex(ValueError, "resource evidence"):
            validate_probe_snapshot(snapshot)
        snapshot["asset"] = {
            "assetId": "texture-rgb-3x1-v1",
            "resource": {"url": "http://fixture/asset.png", "state": "finished"},
            "entity": {
                "id": "entity", "name": "OVERTE_E2E_ASSET_LOAD", "type": "Image",
                "imageURL": "http://fixture/wrong.png",
                "naturalDimensions": {"x": 1, "y": 0.5, "z": 0.01},
            },
        }
        with self.assertRaisesRegex(ValueError, "imageURL must match"):
            validate_probe_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
