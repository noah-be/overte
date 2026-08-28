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
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from contracts import validate_probe_snapshot  # noqa: E402
from test_vertical_locomotion import snapshot as probe_snapshot  # noqa: E402


class CoreSequenceTest(unittest.TestCase):
    @staticmethod
    def snapshot() -> dict:
        return probe_snapshot()

    def test_probe_contract_validates_connected_domain_identity_and_markers(self):
        snapshot = self.snapshot()
        snapshot["domain"] = {
            "connected": True,
            "hostname": "127.0.0.1",
            "id": "11111111-2222-4333-8444-555555555555",
            "protocol": "hifi",
            "serverless": False,
        }
        snapshot["scene"].update({
            "domainMarkerCount": 2,
            "domainMarkers": ["OVERTE_E2E_DOMAIN_FLOOR", "OVERTE_E2E_DOMAIN_ORIGIN"],
        })
        self.assertIs(snapshot, validate_probe_snapshot(snapshot))
        snapshot["scene"]["domainMarkerCount"] = 1
        with self.assertRaisesRegex(ValueError, "domainMarkers"):
            validate_probe_snapshot(snapshot)

        snapshot = self.snapshot()
        snapshot["domain"] = {
            "connected": True, "hostname": "", "id": "", "protocol": "hifi",
            "serverless": False,
        }
        with self.assertRaisesRegex(ValueError, "connected probe domain"):
            validate_probe_snapshot(snapshot)

    def test_probe_observes_spawn_without_teleporting_avatar(self):
        probe = (DEVICE_ROOT / "probe/overte_e2e_probe.js").read_text(
            encoding="utf-8")
        self.assertNotIn("MyAvatar.goToLocation", probe)
        self.assertNotIn("MyAvatar.position =", probe)
        self.assertNotIn("MyAvatar.velocity =", probe)
        self.assertIn("Window.location = scenePath", probe)
        self.assertIn("spawnLocationObserved: avatarAtSpawn", probe)
        self.assertIn("return Boolean(tablet.tabletShown || HMD.showTablet)", probe)
        self.assertIn('(name === "tablet" || !controlledTabletOpen())', probe)

    def test_probe_normalizes_initial_and_controlled_reload_flight_state(self):
        probe = (DEVICE_ROOT / "probe/overte_e2e_probe.js").read_text(
            encoding="utf-8")
        self.assertIn("flightNormalizationAllowed && !flightNormalizationActive", probe)
        self.assertIn("MyAvatar.setFlyingEnabled(false)", probe)
        self.assertGreaterEqual(
            probe.count("MyAvatar.setFlyingEnabled(flyingEnabledBeforeNormalization)"), 2)
        self.assertIn("!flightNormalizationActive && !MyAvatar.isInAir()", probe)
        self.assertIn("flightNormalizationAllowed = false;", probe)
        reset = probe.split("function resetSceneObservation()", 1)[1].split("}", 1)[0]
        self.assertIn("flightNormalizationAllowed = true;", reset)
        self.assertIn("flightNormalizationStableSamples = 0;", reset)
        reapply = probe.split("function applySceneLocation", 1)[1].split("}", 1)[0]
        self.assertIn("resetSceneObservation();", reapply)
        self.assertIn("!avatarAtExpectedSpawn()", reapply)
        self.assertIn("Controller.Actions.TranslateY", probe)
        self.assertIn("DriveKeys.TRANSLATE_Y", probe)
        self.assertIn("velocity: vector(MyAvatar.velocity)", probe)

    def test_complete_core_suite_reuses_one_app_session(self):
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

            diagnostic = result.stdout
            if (output / "junit.xml").is_file():
                diagnostic += (output / "junit.xml").read_text(encoding="utf-8")
            self.assertEqual(0, result.returncode, diagnostic)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])
            self.assertEqual(
                ["launch-smoke", "scene", "spawn-grounded", "look", "move",
                 "input-neutral", "collision", "scene-reload", "jump", "fly",
                 "tablet", "tablet-input-isolation"],
                [entry["id"] for entry in summary["results"]],
            )
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(2, state["sceneLoadCount"])
            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("12", junit.attrib["tests"])
            self.assertEqual("0", junit.attrib["failures"])
            self.assertEqual("0", junit.attrib["errors"])

    def test_look_accepts_a_transient_observed_rotation_history(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-transient-look-") as temporary:
            root = Path(temporary)
            output = root / "results"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_MOCK_FAILURES": "transient-look",
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            catalog = root / "catalog.json"
            source_catalog = json.loads(
                (DEVICE_ROOT / "catalog.json").read_text(encoding="utf-8"))
            source_catalog["modules"] = [
                module for module in source_catalog["modules"]
                if module["id"] in {"launch-smoke", "scene", "look"}
            ]
            for module in source_catalog["modules"]:
                module["command"][0] = str(DEVICE_ROOT / module["command"][0])
            catalog.write_text(json.dumps(source_catalog), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(catalog), "--suite", "e2e-core",
                "--allow-virtual", "--require-complete", "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            diagnostic = result.stdout
            if (output / "junit.xml").is_file():
                diagnostic += (output / "junit.xml").read_text(encoding="utf-8")
            self.assertEqual(0, result.returncode, diagnostic)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])

    def test_recovery_suite_reloads_scene_and_restarts_with_new_identity(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-recovery-") as temporary:
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
                "--suite", "e2e-recovery", "--allow-virtual", "--require-complete",
                "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["launch-smoke", "scene-reload", "app-restart"],
                [entry["id"] for entry in summary["results"]],
            )
            restart = json.loads(
                (output / "modules/app-restart/restart.json").read_text(encoding="utf-8"))
            self.assertNotEqual(restart["beforeIdentity"], restart["afterIdentity"])
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(2, state["launchCount"])
            self.assertEqual(1, state["sceneLoadCount"])

    def test_domain_smoke_enters_controlled_domain_without_process_restart(self):
        with tempfile.TemporaryDirectory(prefix="overte-domain-e2e-core-") as temporary:
            root = Path(temporary)
            output = root / "results"
            manifest = json.loads(
                (DEVICE_ROOT / "fixture/domain-manifest.json").read_text(encoding="utf-8"))
            domain_id = "11111111-2222-4333-8444-555555555555"
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_MOCK_E2E_DOMAIN_ID": domain_id,
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
                "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
                "OVERTE_E2E_DOMAIN_ID": domain_id,
                "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(manifest["requiredMarkers"]),
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            environment.pop("OVERTE_MOCK_E2E_DOMAIN_MARKERS_JSON", None)
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "domain-smoke", "--allow-virtual", "--require-complete",
                "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)

            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["launch-smoke", "domain-enter"],
                [entry["id"] for entry in summary["results"]],
            )
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["domainEnterCount"])
            connected = json.loads(
                (output / "modules/domain-enter/domain-connected.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(domain_id, connected["domain"]["id"])
            self.assertEqual(manifest["requiredMarkers"],
                             connected["scene"]["domainMarkers"])
            samples = json.loads(
                (output / "modules/domain-enter/domain-stable-samples.json").read_text(
                    encoding="utf-8"))
            self.assertGreaterEqual(len(samples), 3)

    def test_domain_smoke_rejects_wrong_identity_and_incomplete_content(self):
        manifest = json.loads(
            (DEVICE_ROOT / "fixture/domain-manifest.json").read_text(encoding="utf-8"))
        expected_id = "11111111-2222-4333-8444-555555555555"
        cases = {
            "wrong-domain-id": {
                "OVERTE_MOCK_E2E_DOMAIN_ID": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            },
            "missing-domain-marker": {
                "OVERTE_MOCK_E2E_DOMAIN_ID": expected_id,
                "OVERTE_MOCK_E2E_DOMAIN_MARKERS_JSON": json.dumps(
                    manifest["requiredMarkers"][:-1]),
            },
        }
        for name, overrides in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                    prefix="overte-domain-e2e-negative-") as temporary:
                root = Path(temporary)
                output = root / "results"
                environment = os.environ.copy()
                environment.update({
                    "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                    "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                    "OVERTE_E2E_DOMAIN_URL":
                        "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
                    "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
                    "OVERTE_E2E_DOMAIN_ID": expected_id,
                    "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(
                        manifest["requiredMarkers"]),
                    "OVERTE_E2E_POLL_SECONDS": "0.05",
                    "OVERTE_E2E_TIMEOUT_SECONDS": "1",
                })
                environment.pop("OVERTE_MOCK_E2E_DOMAIN_MARKERS_JSON", None)
                environment.update(overrides)
                result = subprocess.run([
                    sys.executable, str(DEVICE_ROOT / "run.py"),
                    "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                    "--catalog", str(DEVICE_ROOT / "catalog.json"),
                    "--suite", "domain-smoke", "--allow-virtual", "--require-complete",
                    "--output-dir", str(output),
                ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   env=environment, check=False)

                self.assertNotEqual(0, result.returncode, result.stdout)
                summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
                domain_result = next(entry for entry in summary["results"]
                                     if entry["id"] == "domain-enter")
                self.assertEqual("failed", domain_result["status"])
                self.assertTrue(
                    (output / "modules/domain-enter/domain-last-probe.json").is_file())

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
