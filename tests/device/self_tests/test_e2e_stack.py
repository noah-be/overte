#!/usr/bin/env python3
"""Run every shared core module through the deterministic adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import validate_probe_snapshot  # noqa: E402


class E2EStackTest(unittest.TestCase):
    @staticmethod
    def snapshot() -> dict:
        return {
            "schemaVersion": 1, "sampleEpochMs": 1, "sampleSequence": 1,
            "build": {"platform": "Mock", "version": "1", "date": "1970-01-01"},
            "application": {"running": True},
            "scene": {"ready": True, "entityCount": 4},
            "avatar": {
                "position": {"x": 0, "y": 1, "z": 4},
                "inAir": False, "flying": False, "flyingEnabled": True,
            },
            "view": {"orientation": {"x": 0, "y": 0, "z": 0}},
            "tablet": {"open": False},
        }

    def test_probe_contract_rejects_boolean_counts_and_non_finite_vectors(self):
        snapshot = self.snapshot()
        snapshot["scene"]["entityCount"] = True
        with self.assertRaisesRegex(ValueError, "entityCount"):
            validate_probe_snapshot(snapshot)
        snapshot = self.snapshot()
        snapshot["avatar"]["position"]["x"] = float("nan")
        with self.assertRaisesRegex(ValueError, "position"):
            validate_probe_snapshot(snapshot)
        snapshot = self.snapshot()
        snapshot["sampleSequence"] = True
        with self.assertRaisesRegex(ValueError, "sampleSequence"):
            validate_probe_snapshot(snapshot)

    def test_probe_contract_observes_standard_controller_values_and_poses(self):
        snapshot = self.snapshot()
        snapshot["input"] = {
            "dominantHand": "right", "advancedMovementControls": True,
        }
        snapshot["controller"] = {
            "route": {
                "openxrAxes": {"lx": 0.0, "ly": -1.0, "rx": 0.0, "ry": 0.0},
                "standardLy": -1.0, "translateZAction": -1.0,
                "rawTranslateZDriveKey": 1.0,
                "translateZDriveKeyDisabled": False,
            },
            "axes": {
                "lx": 0.0, "ly": -1.0, "rx": 0.0, "ry": 0.0,
                "leftTrigger": 0.0, "rightTrigger": 1.0,
                "leftGrip": 0.0, "rightGrip": 0.5,
            },
            "buttons": {
                "menu": False, "leftPrimary": False, "leftSecondary": False,
                "leftThumbstick": False, "leftTrigger": False,
                "rightPrimary": True, "rightSecondary": False,
                "rightThumbstick": False, "rightTrigger": True,
            },
            "poses": {
                "left": {"valid": False, "translation": None, "rotation": None},
                "right": {
                    "valid": True,
                    "translation": {"x": 0.1, "y": 1.2, "z": -0.3},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
            },
        }
        self.assertIs(snapshot, validate_probe_snapshot(snapshot))
        snapshot["input"]["advancedMovementControls"] = 1
        with self.assertRaisesRegex(ValueError, "probe input"):
            validate_probe_snapshot(snapshot)
        snapshot["input"]["advancedMovementControls"] = True
        snapshot["controller"]["axes"]["rightGrip"] = float("nan")
        with self.assertRaisesRegex(ValueError, "controller.axes"):
            validate_probe_snapshot(snapshot)
        snapshot = self.snapshot()
        snapshot["controller"] = {
            "axes": dict.fromkeys(("lx", "ly", "rx", "ry", "leftTrigger",
                                    "rightTrigger", "leftGrip", "rightGrip"), 0.0),
            "buttons": dict.fromkeys(("menu", "leftPrimary", "leftSecondary",
                                      "leftThumbstick", "leftTrigger", "rightPrimary",
                                      "rightSecondary", "rightThumbstick", "rightTrigger"), False),
            "poses": {
                "left": {"valid": False, "translation": {"x": 0, "y": 0, "z": 0},
                         "rotation": None},
                "right": {"valid": False, "translation": None, "rotation": None},
            },
        }
        with self.assertRaisesRegex(ValueError, "invalid controller pose left"):
            validate_probe_snapshot(snapshot)

        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn("Controller.getValue(Controller.Standard.LeftGrip)", probe)
        self.assertIn("Controller.getPoseValue(channel)", probe)
        self.assertIn("Controller.Standard.RightHand", probe)
        self.assertNotIn('MyAvatar.setDominantHand("right")', probe)
        self.assertNotIn("MyAvatar.useAdvancedMovementControls = true", probe)
        self.assertIn("application.RightHandDominant", probe)
        self.assertIn("application.AdvancedMovement", probe)
        self.assertIn("Controller.getValue(openXr.LY)", probe)
        self.assertIn("Controller.getValue(Controller.Actions.TranslateZ)", probe)
        self.assertIn("MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Z)", probe)
        self.assertIn("sampleSequence: sampleSequence", probe)
        self.assertIn("OVERTE_E2E_PROBE_HEARTBEAT", probe)
        self.assertIn("OVERTE_E2E_PROBE_ERROR", probe)
        self.assertIn("Script.update.connect(updateProbe)", probe)
        self.assertIn("Script.update.disconnect(updateProbe)", probe)
        self.assertNotIn("Script.setInterval", probe)

    def test_complete_core_suite_is_platform_neutral(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-stack-") as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            output = root / "results"
            result = subprocess.run([
                sys.executable, str(ROOT / "run.py"),
                "--adapter-manifest", str(ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(ROOT / "catalog.json"), "--suite", "e2e-core",
                "--allow-virtual", "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])
            self.assertEqual(["launch-smoke", "scene", "look", "move", "tablet"],
                             [item["id"] for item in summary["results"]])
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["sceneLoadCount"])
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("5", junit.attrib["tests"])
            self.assertEqual("0", junit.attrib["failures"])
            self.assertEqual("0", junit.attrib["errors"])

    def test_complete_core_suite_enforces_pico_hardware_evidence(self):
        with tempfile.TemporaryDirectory(prefix="overte-pico-e2e-stack-") as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "overte-e2e://fixture/scene",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
                "OVERTE_PICO_OPENXR_INPUT": "1",
            })
            output = root / "results"
            result = subprocess.run([
                sys.executable, str(ROOT / "run.py"),
                "--adapter-manifest", str(ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(ROOT / "catalog.json"), "--suite", "e2e-core",
                "--allow-virtual", "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])
            samples = json.loads((output / "modules/scene/fixture-stable-samples.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(5, len(samples))
            route = json.loads((output / "modules/move/move-route-active.json")
                               .read_text(encoding="utf-8"))
            self.assertEqual("right", route["input"]["dominantHand"])
            self.assertTrue(route["input"]["advancedMovementControls"])
            self.assertFalse(route["controller"]["route"]
                             ["translateZDriveKeyDisabled"])
            for module, artifact in (
                    ("look", "look-input-result.json"),
                    ("move", "move-input-result.json"),
                    ("tablet", "tablet-open-input-result.json"),
                    ("tablet", "tablet-close-input-result.json")):
                input_result = json.loads((output / "modules" / module / artifact)
                                          .read_text(encoding="utf-8"))
                if module == "look":
                    self.assertTrue(input_result["viewApplied"])
                    self.assertEqual(25.0, input_result["viewYawDegrees"])
                else:
                    self.assertTrue(input_result["neutralBeforeCommand"])
                if module == "move":
                    self.assertTrue(input_result["openXrVectorApplied"])
                    self.assertEqual(0.4, input_result["openXrLeftThumbstickY"])
                if module == "tablet":
                    self.assertTrue(input_result["openXrBooleanApplied"])

    def test_fixture_requires_a_thick_floor_and_explicit_safe_spawn(self):
        from fixture.serve import controlled_scene_url

        fixture = ROOT / "fixture"
        manifest = json.loads((fixture / "fixture-manifest.json").read_text())
        scene = json.loads((fixture / "scene.json").read_text())
        floor = next(item for item in scene["Entities"]
                     if item["name"] == "OVERTE_E2E_FLOOR")
        spawn = manifest["spawnPosition"]
        self.assertEqual(0.0, floor["position"]["y"] + floor["dimensions"]["y"] / 2.0)
        self.assertGreaterEqual(floor["dimensions"]["y"], manifest["minimumFloorThickness"])
        self.assertGreaterEqual(spawn["y"], 2.0)
        self.assertEqual(
            f"/{spawn['x']},{spawn['y']},{spawn['z']}/0,0,0,1",
            manifest["spawnPath"])
        served = urlsplit(controlled_scene_url("http://fixture.invalid", manifest))
        self.assertEqual([manifest["spawnPath"]], parse_qs(served.query)["location"])
        self.assertEqual("/scene.json", served.path)
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn("avatarAboveFloor", probe)
        self.assertNotIn("MyAvatar.goToLocation", probe)
        self.assertNotIn("MyAvatar.velocity =", probe)
        self.assertNotIn("spawnApplied", probe)
        self.assertNotIn("spawnRequestPending", probe)
        self.assertIn("stableAvatarSamples >= 4", probe)
        self.assertIn("avatarAboveFloor && avatarAtSpawn", probe)
        self.assertIn("spawnValidated: sceneReady", probe)

    def test_pico_actions_span_slow_physical_probe_observations(self):
        session = (ROOT / "overte_session.py").read_text(encoding="utf-8")
        launch = (ROOT / "modules/launch_smoke.py").read_text(encoding="utf-8")
        self.assertIn('arguments["durationSeconds"] = 6.0', session)
        self.assertIn('move_arguments.update({"durationSeconds": 3.0, "strength": 0.4})',
                      session)
        self.assertIn('{"holdMilliseconds": 1000} if self.pico_openxr else None',
                      session)
        self.assertIn("raw_sign != mapped_signs[0]", session)
        self.assertIn("settle = max(settle, 25)", launch)
        self.assertNotIn("brightness", session.lower())

if __name__ == "__main__":
    unittest.main()
