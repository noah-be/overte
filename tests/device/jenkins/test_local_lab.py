#!/usr/bin/env python3
"""Device-free tests for the pinned local Jenkins bootstrap."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("overte_local_lab", HERE / "local_lab.py")
LAB = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LAB)
TARGET_SPEC = importlib.util.spec_from_file_location(
    "overte_prepare_private_targets", HERE / "prepare_private_targets.py")
TARGETS = importlib.util.module_from_spec(TARGET_SPEC)
assert TARGET_SPEC.loader is not None
TARGET_SPEC.loader.exec_module(TARGETS)


class LocalLabBootstrapTest(unittest.TestCase):
    def test_rendered_casc_keeps_secrets_out_of_the_checkout(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-test-") as name:
            root = Path(name)
            values = {
                "password": root / "private/admin-password",
                "agentRoot": root / "private/agent",
                "casc": root / "private/jenkins.yaml",
            }
            values["agentRoot"].mkdir(parents=True)
            LAB.secure_write(values["password"], "not-embedded-in-yaml\n")
            LAB.render_casc(values)
            rendered = values["casc"].read_text(encoding="utf-8")
            self.assertNotIn("not-embedded-in-yaml", rendered)
            self.assertIn(values["password"].as_posix(), rendered)
            self.assertIn(values["agentRoot"].as_posix(), rendered)
            self.assertNotIn("__OVERTE_", rendered)

    def test_install_writes_private_state_from_pinned_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-install-") as name:
            root = Path(name)
            java = root / "java"
            java.touch()
            arguments = argparse.Namespace(
                install_root=str(root / "software"), config_root=str(root / "private"),
                java=str(java), npm="npm", port=18080, skip_appium=False,
            )

            def fake_download(_artifact, destination):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"pinned")
                return destination

            appium = root / "software/appium/node_modules/.bin/appium"
            appium.parent.mkdir(parents=True)
            appium.touch()
            with patch.object(LAB, "java_major", return_value=21), \
                    patch.object(LAB, "download", side_effect=fake_download), \
                    patch.object(LAB, "install_plugins"), \
                    patch.object(LAB, "install_appium", return_value=appium):
                self.assertEqual(0, LAB.install(arguments))

            state_path = root / "private/local-lab.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("http://127.0.0.1:18080", state["serverUrl"])
            self.assertEqual(str(appium), state["appiumExecutable"])
            self.assertNotIn(
                (root / "private/admin-password").read_text().strip(),
                (root / "private/jenkins.yaml").read_text(encoding="utf-8"),
            )

    def test_status_is_fail_closed_when_controller_is_offline(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-status-") as name:
            root = Path(name)
            LAB.secure_write(root / "local-lab.json", json.dumps({
                "schemaVersion": 1,
                "serverUrl": "http://127.0.0.1:1",
                "adminPasswordFile": str(root / "password"),
                "adminId": "overte-admin",
            }))
            LAB.secure_write(root / "password", "unused\n")
            arguments = argparse.Namespace(config_root=str(root))
            self.assertEqual(1, LAB.status(arguments))

    def test_systemd_appium_service_receives_android_sdk(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-systemd-") as name:
            root = Path(name)
            private = root / "private"
            sdk = root / "sdk"
            adb = sdk / "platform-tools/adb"
            adb.parent.mkdir(parents=True)
            adb.touch()
            state = {
                "schemaVersion": 1,
                "serverUrl": "http://127.0.0.1:18080",
                "adminPasswordFile": str(private / "admin-password"),
                "adminId": "overte-admin",
                "agentRoot": str(private / "agent"),
                "appiumExecutable": str(root / "appium"),
                "appiumHome": str(private / "appium-home"),
            }
            LAB.secure_write(private / "local-lab.json", json.dumps(state))
            arguments = argparse.Namespace(config_root=str(private))
            fake_home = root / "home"
            with patch.object(LAB.Path, "home", return_value=fake_home), \
                    patch.object(LAB.platform, "system", return_value="Linux"), \
                    patch.object(LAB, "wait_controller"), \
                    patch.object(LAB.subprocess, "run"), \
                    patch.dict(LAB.os.environ, {"ANDROID_SDK_ROOT": str(sdk)}, clear=False):
                self.assertEqual(0, LAB.install_systemd_user_services(arguments))
            unit = (fake_home / ".config/systemd/user/overte-appium.service").read_text()
            self.assertIn(f'Environment="ANDROID_SDK_ROOT={sdk.resolve()}"', unit)
            self.assertIn(f'Environment="ANDROID_HOME={sdk.resolve()}"', unit)

    def test_private_target_templates_start_disabled(self):
        with tempfile.TemporaryDirectory(prefix="overte-private-targets-") as name:
            root = Path(name)
            state = {
                "schemaVersion": 1,
                "java": "/private/jdk/bin/java",
                "appiumHome": "/private/appium-home",
            }
            LAB.secure_write(root / "local-lab.json", json.dumps(state))
            arguments = argparse.Namespace(
                config_root=str(root), environment_only=False)
            self.assertEqual(0, TARGETS.prepare(arguments))
            payload = json.loads((root / "targets/appium.json").read_text())
            self.assertTrue(payload["targets"])
            self.assertTrue(all(target["enabled"] is False
                                for target in payload["targets"]))
            agent_environment = (root / "agent.env").read_text(encoding="utf-8")
            self.assertIn("OVERTE_APPIUM_TARGETS=", agent_environment)
            self.assertIn("OVERTE_CONAN_CACHE_ROOT=", agent_environment)
            self.assertIn("OVERTE_ANDROID_BUILD_ROOT=", agent_environment)
            self.assertNotIn("REPLACE_WITH_PRIVATE_UDID", agent_environment)


if __name__ == "__main__":
    unittest.main()
