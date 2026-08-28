#!/usr/bin/env python3
"""Android- and Pico-specific extensions to the shared E2E contracts."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import validate_probe_snapshot  # noqa: E402
from test_vertical_locomotion import snapshot as common_probe_snapshot  # noqa: E402


class E2EStackTest(unittest.TestCase):
    def test_probe_contract_observes_standard_controller_values_and_poses(self):
        snapshot = common_probe_snapshot()
        snapshot["controller"] = {
            "route": {
                "openxrAxes": {"lx": 0.0, "ly": -1.0, "rx": 0.0, "ry": 0.0},
                "standardLy": -1.0,
                "translateZAction": -1.0,
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
        snapshot["controller"]["axes"]["rightGrip"] = float("nan")
        with self.assertRaisesRegex(ValueError, "controller.axes"):
            validate_probe_snapshot(snapshot)

        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn("Controller.getValue(Controller.Standard.LeftGrip)", probe)
        self.assertIn("Controller.getPoseValue(channel)", probe)
        self.assertIn("Controller.getValue(openXr.LY)", probe)
        self.assertIn("Controller.getValue(Controller.Actions.TranslateZ)", probe)
        self.assertIn("MyAvatar.getRawDriveKey(DriveKeys.TRANSLATE_Z)", probe)
        self.assertIn("sampleSequence: sampleSequence", probe)
        self.assertIn("vector(MyAvatar.feetPosition)", probe)
        self.assertIn("OVERTE_E2E_PROBE_HEARTBEAT", probe)
        self.assertIn("OVERTE_E2E_PROBE_ERROR", probe)
        self.assertIn("Script.update.connect(updateProbe)", probe)
        self.assertIn("Script.update.disconnect(updateProbe)", probe)
        self.assertNotIn("Script.setInterval", probe)
        self.assertNotIn('MyAvatar.setDominantHand("right")', probe)
        self.assertNotIn("MyAvatar.useAdvancedMovementControls = true", probe)

    def test_only_implemented_real_adapters_may_advertise_domain_navigation(self):
        adapter_root = ROOT / "adapters"
        for source in (adapter_root / "android/adapter.py",
                       adapter_root / "appium/adapter.py"):
            self.assertIn("navigation.enter-domain", source.read_text(encoding="utf-8"))

    def test_fixture_requires_a_thick_floor_and_explicit_grounded_spawn(self):
        from fixture.serve import controlled_scene_url

        fixture = ROOT / "fixture"
        manifest = json.loads((fixture / "fixture-manifest.json").read_text())
        scene = json.loads((fixture / "scene.json").read_text())
        floor = next(item for item in scene["Entities"]
                     if item["name"] == "OVERTE_E2E_FLOOR")
        spawn = manifest["spawnPosition"]
        self.assertEqual(0.0, floor["position"]["y"] + floor["dimensions"]["y"] / 2.0)
        self.assertGreaterEqual(floor["dimensions"]["y"], manifest["minimumFloorThickness"])
        self.assertEqual(0.0, spawn["y"])
        self.assertEqual(
            f"/{spawn['x']},{spawn['y']},{spawn['z']}/0,0,0,1",
            manifest["spawnPath"])
        served = urlsplit(controlled_scene_url("http://fixture.invalid", manifest))
        self.assertEqual([manifest["spawnPath"]], parse_qs(served.query)["location"])
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn("avatarAboveFloor", probe)
        self.assertIn("spawnDeltaY * spawnDeltaY", probe)
        self.assertIn("avatarAtSpawn", probe)
        self.assertIn("stableAvatarSamples >= 4", probe)
        self.assertIn("avatarAboveFloor && avatarAtSpawn", probe)
        self.assertIn("spawnValidated: sceneReady", probe)
        self.assertNotIn("MyAvatar.goToLocation", probe)
        self.assertNotIn("MyAvatar.velocity =", probe)

    def test_pico_timing_defaults_are_owned_by_the_android_adapter(self):
        session = (ROOT / "overte_session.py").read_text(encoding="utf-8")
        adapter = (ROOT / "adapters/android/adapter.py").read_text(encoding="utf-8")
        launch = (ROOT / "modules/launch_smoke.py").read_text(encoding="utf-8")
        self.assertIn('staged_values.setdefault("durationSeconds", 6.0)', adapter)
        self.assertIn('staged_values.setdefault("strength", 0.4)', adapter)
        self.assertIn('staged_values.setdefault("holdMilliseconds", 1000)', adapter)
        self.assertNotIn("holdMilliseconds", session)
        self.assertNotIn('arguments["durationSeconds"] = 6.0', session)
        self.assertIn("settle = max(settle, 25)", launch)
        self.assertNotIn("brightness", session.lower())


if __name__ == "__main__":
    unittest.main()
