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
class LocalLabBootstrapTest(unittest.TestCase):
    def test_private_paths_reject_symlink_components_and_weak_existing_mode(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-path-") as name:
            temporary = Path(name)
            real = temporary / "real"
            real.mkdir(mode=0o700)
            link = temporary / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symbolic links"):
                LAB.secure_directory(link / "private")
            self.assertFalse((real / "private").exists())

            weak = temporary / "weak"
            weak.mkdir(mode=0o755)
            with self.assertRaisesRegex(RuntimeError, "group or other"):
                LAB.secure_directory(weak)

    def test_secure_write_does_not_follow_fixed_temp_or_destination_symlinks(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-write-") as name:
            private = Path(name) / "private"
            private.mkdir(mode=0o700)
            victim = Path(name) / "must-not-change"
            victim.write_text("private\n", encoding="utf-8")
            (private / "secret.tmp").symlink_to(victim)
            LAB.secure_write(private / "secret", "new secret\n")
            self.assertEqual("private\n", victim.read_text(encoding="utf-8"))
            self.assertEqual("new secret\n", (private / "secret").read_text())
            self.assertEqual(0o600, (private / "secret").stat().st_mode & 0o777)

            (private / "linked-secret").symlink_to(victim)
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                LAB.secure_write(private / "linked-secret", "must fail\n")
            self.assertEqual("private\n", victim.read_text(encoding="utf-8"))

    def test_rendered_casc_keeps_secrets_out_of_the_checkout(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-test-") as name:
            root = Path(name)
            values = {
                "password": root / "private/admin-password",
                "agentRoot": root / "private/agent",
                "casc": root / "private/jenkins.yaml",
            }
            values["agentRoot"].mkdir(parents=True)
            values["password"].parent.chmod(0o700)
            LAB.secure_write(values["password"], "not-embedded-in-yaml\n")
            LAB.render_casc(values)
            rendered = values["casc"].read_text(encoding="utf-8")
            self.assertNotIn("not-embedded-in-yaml", rendered)
            self.assertIn("overte-ios-fedora-device", rendered)
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

            appium = root / "software/appium"
            appium.mkdir(parents=True)
            (root / "software").chmod(0o700)
            with patch.object(LAB, "java_major", return_value=21), \
                    patch.object(LAB, "download", side_effect=fake_download), \
                    patch.object(LAB, "install_plugins"), \
                    patch.object(
                        LAB, "install_appium", return_value=appium
                    ) as install_appium:
                self.assertEqual(0, LAB.install(arguments))

            appium_lock = install_appium.call_args.args[0]["appium"]
            self.assertNotIn("uiautomator2", appium_lock["drivers"])
            self.assertEqual("12.8.0", appium_lock["drivers"]["xcuitest"]["version"])

            state_path = root / "private/local-lab.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("http://127.0.0.1:18080", state["serverUrl"])
            self.assertEqual(str(appium), state["appiumBootstrapRoot"])
            appium_state = Path(state["appiumStateRoot"])
            self.assertTrue(appium_state.is_dir())
            self.assertEqual(0o700, appium_state.stat().st_mode & 0o777)
            self.assertNotIn("oculixJar", state)
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

    def test_systemd_appium_service_is_local_and_hardened(self):
        with tempfile.TemporaryDirectory(prefix="overte-local-lab-systemd-") as name:
            root = Path(name)
            private = root / "private"
            state = {
                "schemaVersion": 1,
                "serverUrl": "http://127.0.0.1:18080",
                "adminPasswordFile": str(private / "admin-password"),
                "adminId": "overte-admin",
                "agentRoot": str(private / "agent"),
                "appiumBootstrapRoot": str(root / "appium"),
                "appiumStateRoot": str(private / "appium-state"),
            }
            LAB.secure_write(private / "local-lab.json", json.dumps(state))
            arguments = argparse.Namespace(config_root=str(private))
            fake_home = root / "home"
            with patch.object(LAB.Path, "home", return_value=fake_home), \
                    patch.object(LAB.platform, "system", return_value="Linux"), \
                    patch.object(LAB, "wait_controller"), \
                    patch.object(LAB.subprocess, "run"), \
                    patch.object(LAB, "immutable_appium_command", return_value=[
                        "/usr/local/lib/overte-ios-remotexpc/5.15.3-r5/remotexpc_tunnel.py",
                        "appium-server", "--service-runtime",
                        "/usr/local/lib/overte-ios-remotexpc/5.15.3-r5",
                        "--state-root", str(private / "appium-state"),
                    ]) as immutable_appium:
                self.assertEqual(0, LAB.install_systemd_user_services(arguments))
            appium_lock = immutable_appium.call_args.args[0]["appium"]
            self.assertNotIn("uiautomator2", appium_lock["drivers"])
            self.assertEqual("5.15.3", appium_lock["iosRuntime"]["remoteXpc"]["version"])
            unit = (fake_home / ".config/systemd/user/overte-appium.service").read_text()
            self.assertIn("--address", unit)
            self.assertIn("127.0.0.1", unit)
            self.assertIn("appium-server", unit)
            self.assertIn("--state-root", unit)
            self.assertIn(str(private / "appium-state"), unit)
            self.assertIn("ReadWritePaths=", unit)
            self.assertNotIn("node_modules/.bin/appium", unit)
            self.assertIn("NoNewPrivileges=true", unit)

            tunnel_path = LAB.DEVICE_ROOT / "ios/remotexpc_tunnel.py"
            tunnel_spec = importlib.util.spec_from_file_location(
                "overte_remotexpc_parser", tunnel_path)
            self.assertIsNotNone(tunnel_spec)
            self.assertIsNotNone(tunnel_spec.loader)
            tunnel = importlib.util.module_from_spec(tunnel_spec)
            tunnel_spec.loader.exec_module(tunnel)
            parsed = tunnel.parser().parse_args([
                "appium-server", "--service-runtime",
                "/usr/local/lib/overte-ios-remotexpc/5.15.3-r5",
                "--state-root", str(private / "appium-state"),
                "--address", "127.0.0.1", "--port", "4723",
            ])
            self.assertEqual(private / "appium-state", parsed.state_root)

    def test_install_and_config_roots_must_stay_outside_checkout(self):
        for attribute, forbidden in (
                ("install_root", LAB.REPOSITORY / "forbidden-software"),
                ("config_root", LAB.REPOSITORY / "forbidden-private")):
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory(
                    prefix="overte-local-lab-external-") as name:
                temporary = Path(name)
                values = {
                    "install_root": str(temporary / "safe-install"),
                    "config_root": str(temporary / "safe-config"),
                }
                values[attribute] = str(forbidden)
                arguments = argparse.Namespace(**values)
                with self.assertRaisesRegex(RuntimeError, "outside the source checkout"):
                    LAB.paths(arguments)
                self.assertFalse(forbidden.exists())

    def test_locks_pin_required_jenkins_and_appium_versions(self):
        lock = LAB.load_lock()
        ios_lock = LAB.load_ios_lock(lock)
        self.assertEqual(21, lock["jenkins"]["recommendedJavaMajor"])
        self.assertEqual("2.568.2", lock["jenkins"]["lts"]["version"])
        self.assertEqual("3.7.0", lock["appium"]["core"]["version"])
        self.assertEqual("12.8.0", lock["appium"]["drivers"]["xcuitest"]["version"])
        self.assertEqual(
            json.loads((LAB.DEVICE_ROOT / "ios/package.json").read_text(
                encoding="utf-8"))["dependencies"],
            LAB.appium_dependencies(ios_lock["appium"]),
        )
        self.assertNotIn(
            "appium-uiautomator2-driver",
            LAB.appium_dependencies(ios_lock["appium"]),
        )


if __name__ == "__main__":
    unittest.main()
