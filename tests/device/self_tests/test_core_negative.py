#!/usr/bin/env python3
"""Negative proofs that the common behavior layer rejects false-positive evidence."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class CoreNegativeTest(unittest.TestCase):
    def run_case(self, module_id: str, failure: str) -> tuple[subprocess.CompletedProcess, dict]:
        with tempfile.TemporaryDirectory(prefix=f"overte-e2e-negative-{module_id}-") as temporary:
            root = Path(temporary)
            source = json.loads((DEVICE_ROOT / "catalog.json").read_text(encoding="utf-8"))
            wanted = ["launch-smoke"] if module_id == "launch-smoke" else [
                "launch-smoke", module_id]
            modules = []
            for identifier in wanted:
                original = next(item for item in source["modules"] if item["id"] == identifier)
                module = copy.deepcopy(original)
                module["suites"] = ["negative"]
                module["command"][0] = str((DEVICE_ROOT / module["command"][0]).resolve())
                modules.append(module)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"schemaVersion": 1, "modules": modules}),
                               encoding="utf-8")
            output = root / "results"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_MOCK_E2E_FAILURES": failure,
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
                "OVERTE_E2E_TIMEOUT_SECONDS": "1",
            })
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(catalog), "--suite", "negative", "--allow-virtual",
                "--require-complete", "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            return result, summary

    def assert_product_failure(self, module_id: str, failure: str) -> None:
        result, summary = self.run_case(module_id, failure)
        self.assertEqual(1, result.returncode, result.stdout)
        observed = next(item for item in summary["results"] if item["id"] == module_id)
        self.assertEqual("failed", observed["status"], result.stdout)

    def test_wrong_signed_movement_is_rejected(self):
        self.assert_product_failure("move-forward", "wrong-move-direction")

    def test_look_below_minimum_is_rejected(self):
        self.assert_product_failure("look-right", "small-look")

    def test_stuck_input_is_rejected_after_movement(self):
        self.assert_product_failure("move-left", "stuck-input")

    def test_jump_mislabeled_as_flight_is_rejected(self):
        self.assert_product_failure("jump", "jump-as-flight")

    def test_jump_without_landing_is_rejected(self):
        self.assert_product_failure("jump", "jump-no-landing")

    def test_flight_without_height_gain_is_rejected(self):
        self.assert_product_failure("fly-ascent", "fly-no-height")

    def test_missing_tablet_transition_is_rejected(self):
        self.assert_product_failure("tablet-toggle", "tablet-transition")

    def test_tablet_touch_through_is_rejected(self):
        self.assert_product_failure("tablet-input-isolation", "tablet-touch-through")

    def test_missing_fixture_marker_is_rejected(self):
        self.assert_product_failure("scene-load", "missing-markers")

    def test_floor_fall_through_is_rejected(self):
        self.assert_product_failure("spawn-grounded", "floor-fall-through")

    def test_collision_pass_through_is_rejected(self):
        self.assert_product_failure("collision", "collision-pass-through")

    def test_unexpected_process_identity_change_is_rejected(self):
        self.assert_product_failure("launch-smoke", "process-change")

    def test_stale_probe_sequence_is_an_infrastructure_error(self):
        result, summary = self.run_case("scene-load", "stale-sequence")
        self.assertEqual(1, result.returncode, result.stdout)
        scene = next(item for item in summary["results"] if item["id"] == "scene-load")
        self.assertEqual("error", scene["status"], result.stdout)


if __name__ == "__main__":
    unittest.main()
