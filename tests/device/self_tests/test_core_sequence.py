#!/usr/bin/env python3
"""Device-free proof that the shared core scenarios reuse one app session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class CoreSequenceTest(unittest.TestCase):
    def test_probe_observes_spawn_without_teleporting_avatar(self):
        probe = (DEVICE_ROOT / "probe/overte_e2e_probe.js").read_text(
            encoding="utf-8")
        self.assertNotIn("MyAvatar.goToLocation", probe)
        self.assertNotIn("MyAvatar.velocity =", probe)
        self.assertIn("spawnLocationObserved: avatarAtSpawn", probe)

    def test_complete_core_suite_reuses_one_launch_and_one_scene(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-core-") as temporary:
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
                sys.executable,
                str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest",
                str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog",
                str(DEVICE_ROOT / "catalog.json"),
                "--suite",
                "e2e-core",
                "--allow-virtual",
                "--require-complete",
                "--output-dir",
                str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)

            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])
            self.assertEqual(
                ["launch-smoke", "scene", "look", "move", "tablet"],
                [entry["id"] for entry in summary["results"]],
            )
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["sceneLoadCount"])
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("5", junit.attrib["tests"])
            self.assertEqual("0", junit.attrib["failures"])
            self.assertEqual("0", junit.attrib["errors"])

    def test_accessibility_audit_observes_both_tablet_states_in_one_session(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-accessibility-") as temporary:
            root = Path(temporary)
            output = root / "results"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
                "OVERTE_E2E_TABLET_OPEN_ACCESSIBILITY_ID": "OverteTabletOpen",
                "OVERTE_E2E_TABLET_CLOSE_ACCESSIBILITY_ID": "OverteTabletClose",
            })
            result = subprocess.run([
                sys.executable,
                str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest",
                str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog",
                str(DEVICE_ROOT / "catalog.json"),
                "--suite",
                "accessibility",
                "--allow-virtual",
                "--require-complete",
                "--output-dir",
                str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)

            self.assertEqual(0, result.returncode, result.stdout)
            audit = json.loads((output / "modules" / "accessibility" /
                                "accessibility-audit.json").read_text(encoding="utf-8"))
            self.assertEqual([], audit["missing"])
            self.assertEqual(["OverteTabletOpen", "OverteTabletClose"], audit["required"])
            self.assertNotIn("source", audit)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["sceneLoadCount"])
            self.assertIs(state["tablet"], False)

    def test_accessibility_configuration_error_is_infrastructure_not_product(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-accessibility-config-") as temporary:
            root = Path(temporary)
            output = root / "results"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            environment.pop("OVERTE_E2E_TABLET_OPEN_ACCESSIBILITY_ID", None)
            environment.pop("OVERTE_E2E_TABLET_CLOSE_ACCESSIBILITY_ID", None)
            result = subprocess.run([
                sys.executable,
                str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest",
                str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog",
                str(DEVICE_ROOT / "catalog.json"),
                "--suite",
                "accessibility",
                "--allow-virtual",
                "--require-complete",
                "--output-dir",
                str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)

            self.assertEqual(1, result.returncode, result.stdout)
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("0", junit.attrib["failures"])
            self.assertEqual("1", junit.attrib["errors"])


if __name__ == "__main__":
    unittest.main()
