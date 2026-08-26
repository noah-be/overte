#!/usr/bin/env python3
"""Contract and device-free scenario tests for vertical locomotion."""

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

from contracts import (load_capability_registry, validate_operation_arguments,
                       validate_performed_result, validate_probe_snapshot)


def snapshot(**avatar_overrides: object) -> dict:
    avatar = {
        "position": {"x": 0.0, "y": 1.0, "z": 4.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bodyYawDegrees": 0.0,
        "inAir": False,
        "flying": False,
        "flyingEnabled": True,
    }
    avatar.update(avatar_overrides)
    return {
        "schemaVersion": 2,
        "sampleEpochMs": 1,
        "sampleSequence": 1,
        "build": {"platform": "Mock", "version": "1", "date": "1970-01-01"},
        "application": {"running": True, "foreground": True},
        "input": {"dominantHand": "right", "advancedMovementControls": True},
        "scene": {
            "url": "http://fixture.invalid/scene.json",
            "ready": True,
            "entityCount": 5,
            "fixtureMarkerCount": 5,
            "fixtureMarkers": [
                "OVERTE_E2E_COLLISION_WALL", "OVERTE_E2E_EAST", "OVERTE_E2E_FLOOR",
                "OVERTE_E2E_NORTH", "OVERTE_E2E_ORIGIN",
            ],
            "floorTopY": 0.0,
            "avatarAboveFloor": True,
            "spawnLocationObserved": True,
            "spawnValidated": True,
            "collisionWall": {
                "name": "OVERTE_E2E_COLLISION_WALL",
                "center": {"x": 0.0, "y": 2.0, "z": 0.5},
                "dimensions": {"x": 8.0, "y": 4.0, "z": 0.5},
            },
        },
        "avatar": avatar,
        "view": {"orientation": {"x": 0.0, "y": 0.0, "z": 0.0}},
        "tablet": {"open": False, "home": False, "toolbarMode": False},
    }


class VerticalLocomotionTest(unittest.TestCase):
    def test_capabilities_are_registered(self):
        registry = load_capability_registry()
        self.assertEqual("input.jump", registry["input.jump"]["operation"])
        self.assertEqual("input.fly", registry["input.fly"]["operation"])

    def test_operation_argument_and_result_contracts(self):
        self.assertEqual({}, validate_operation_arguments("input.jump", {}))
        self.assertEqual(
            {"durationSeconds": 2.0},
            validate_operation_arguments("input.fly", {"durationSeconds": 2.0}),
        )
        self.assertEqual(
            {"performed": True},
            validate_performed_result("input.jump", {"performed": True}),
        )
        for operation, arguments in (
                ("input.jump", {"button": "A"}),
                ("input.fly", {}),
                ("input.fly", {"durationSeconds": 0}),
                ("input.fly", {"durationSeconds": 11}),
                ("input.fly", {"durationSeconds": True})):
            with self.subTest(operation=operation, arguments=arguments):
                with self.assertRaises(ValueError):
                    validate_operation_arguments(operation, arguments)
        with self.assertRaises(ValueError):
            validate_performed_result("input.fly", {"performed": False})

    def test_probe_requires_vertical_state_and_rejects_inconsistent_avatar(self):
        self.assertEqual(snapshot(), validate_probe_snapshot(snapshot()))
        for invalid in (
                snapshot(inAir=None),
                snapshot(flying=None),
                snapshot(flyingEnabled=None),
                snapshot(inAir=False, flying=True)):
            with self.subTest(avatar=invalid["avatar"]):
                with self.assertRaises(ValueError):
                    validate_probe_snapshot(invalid)

    def test_complete_vertical_suite_proves_jump_and_fly_trajectories(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-vertical-") as temporary:
            root = Path(temporary)
            output = root / "results"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual", "--require-complete",
                "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["launch-smoke", "jump", "fly-ascent"],
                [item["id"] for item in summary["results"]])
            jump_airborne = json.loads(
                (output / "modules/jump/jump-airborne.json").read_text(encoding="utf-8"))
            jump_landed = json.loads(
                (output / "modules/jump/jump-landed.json").read_text(encoding="utf-8"))
            fly_active = json.loads(
                (output / "modules/fly-ascent/fly-active.json").read_text(encoding="utf-8"))
            self.assertTrue(jump_airborne["avatar"]["inAir"])
            self.assertFalse(jump_airborne["avatar"]["flying"])
            self.assertFalse(jump_landed["avatar"]["inAir"])
            self.assertTrue(fly_active["avatar"]["inAir"])
            self.assertTrue(fly_active["avatar"]["flying"])

    def test_adapter_without_vertical_capabilities_skips_or_fails_complete(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-no-vertical-") as temporary:
            root = Path(temporary)
            adapter = root / "adapter.py"
            adapter.write_text(
                "#!/usr/bin/env python3\n"
                "import json,sys\n"
                "if sys.argv[1] == 'discover':\n"
                " print(json.dumps([{'selector':'mock','displayName':'Mock','platform':'mock','physical':False,'capabilities':['probe.snapshot','scene.load']}]))\n"
                "elif sys.argv[1] == 'describe': print('{}')\n"
                "else: print(json.dumps({'cleaned': True}))\n",
                encoding="utf-8")
            adapter.chmod(0o700)
            manifest = root / "adapter.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1, "id": "no-vertical", "command": ["adapter.py"]}),
                encoding="utf-8")
            base = [
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(manifest), "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual",
            ]
            skipped = subprocess.run(
                [*base, "--output-dir", str(root / "skip")], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            complete = subprocess.run(
                [*base, "--require-complete", "--output-dir", str(root / "complete")],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, skipped.returncode, skipped.stdout)
            self.assertTrue(all(item["status"] == "skipped" for item in json.loads(
                (root / "skip/summary.json").read_text(encoding="utf-8"))["results"]))
            self.assertEqual(1, complete.returncode, complete.stdout)
            self.assertTrue(all(item["status"] == "error" for item in json.loads(
                (root / "complete/summary.json").read_text(encoding="utf-8"))["results"]))

    def test_jump_and_fly_reject_missing_height_gain(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-bad-vertical-") as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
                "OVERTE_E2E_TIMEOUT_SECONDS": "1",
                "OVERTE_MOCK_E2E_BAD_JUMP": "1",
                "OVERTE_MOCK_E2E_BAD_FLY": "1",
            })
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual", "--require-complete",
                "--output-dir", str(root / "results"),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads(
                (root / "results/summary.json").read_text(encoding="utf-8"))
            self.assertEqual(["passed", "failed", "failed"],
                             [item["status"] for item in summary["results"]])


if __name__ == "__main__":
    unittest.main()
