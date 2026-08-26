#!/usr/bin/env python3
"""Device-free checks for the Fedora RemoteXPC service wrapper."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "remotexpc_tunnel.py"
SPEC = importlib.util.spec_from_file_location("overte_remotexpc_tunnel", SCRIPT)
assert SPEC and SPEC.loader
TUNNEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TUNNEL)


class IosRemoteXpcTunnelTest(unittest.TestCase):
    def test_redaction_covers_real_device_token_shapes(self):
        explicit = {"00008101-1234567890ABCDEF"}
        value = TUNNEL.redact(
            "UDID 00008101-1234567890ABCDEF raw aabbccddeeff00112233445566778899", explicit
        )
        self.assertNotIn("00008101", value)
        self.assertNotIn("aabbccdd", value)
        self.assertEqual(2, value.count("<redacted-device>"))

    def make_source_runtime(self, root: Path) -> tuple[Path, Path]:
        appium_home = root / "appium-home"
        package = appium_home / "node_modules/appium-ios-remotexpc"
        (package / "scripts").mkdir(parents=True)
        (package / "scripts/tunnel-creation.mjs").write_text(
            "console.log('tunnel');\n", encoding="utf-8",
        )
        (package / "package.json").write_text(json.dumps({
            "name": "appium-ios-remotexpc", "version": "5.15.3",
        }), encoding="utf-8")
        node = root / "node"
        node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        node.chmod(0o700)
        return appium_home, node

    @staticmethod
    def make_tree_writable(root: Path) -> None:
        for path in (root, *root.rglob("*")):
            try:
                if path.is_dir():
                    path.chmod(0o700)
                elif path.is_file():
                    path.chmod(0o600)
            except OSError:
                pass

    def test_runtime_resolution_requires_exact_locked_version(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-runtime-") as name:
            root = Path(name)
            package = root / "node_modules/appium-ios-remotexpc"
            (package / "scripts").mkdir(parents=True)
            (package / "scripts/tunnel-creation.mjs").touch()
            (package / "package.json").write_text(json.dumps({
                "name": "appium-ios-remotexpc", "version": "0.0.1",
            }), encoding="utf-8")
            with self.assertRaisesRegex(TUNNEL.TunnelError, "does not match"):
                TUNNEL.resolve_runtime(root)

    def test_install_creates_versioned_immutable_runtime_copy(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-install-") as name:
            root = Path(name)
            appium_home, node = self.make_source_runtime(root)
            service_root = root / "service"
            try:
                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")):
                    installed = TUNNEL.install_service_runtime(appium_home, service_root)
                self.assertEqual(service_root / "5.15.3", installed)
                self.assertEqual(
                    Path(TUNNEL.__file__).read_bytes(),
                    (installed / "remotexpc_tunnel.py").read_bytes(),
                )
                self.assertFalse(any(installed.rglob(".bin")))
                TUNNEL.verify_service_runtime(installed, os.geteuid())
                source_file = TUNNEL.__file__
                try:
                    TUNNEL.__file__ = str(installed / "remotexpc_tunnel.py")
                    self.assertEqual(installed, TUNNEL.default_service_runtime())
                finally:
                    TUNNEL.__file__ = source_file
                for path in (installed, *installed.rglob("*")):
                    self.assertEqual(0, path.lstat().st_mode & 0o222)
                    self.assertEqual(os.geteuid(), path.lstat().st_uid)
            finally:
                if service_root.exists():
                    self.make_tree_writable(service_root)

    def test_service_runtime_rejects_writable_or_wrong_owner_tree(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-mode-") as name:
            root = Path(name)
            appium_home, node = self.make_source_runtime(root)
            service_root = root / "service"
            try:
                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")):
                    installed = TUNNEL.install_service_runtime(appium_home, service_root)
                marker = installed / TUNNEL.RUNTIME_MARKER
                marker.chmod(0o644)
                with self.assertRaisesRegex(TUNNEL.TunnelError, "writable"):
                    TUNNEL.verify_service_runtime(installed, os.geteuid())
                marker.chmod(0o444)
                with self.assertRaisesRegex(TUNNEL.TunnelError, "owned by root"):
                    TUNNEL.verify_service_runtime(installed, os.geteuid() + 1)
            finally:
                if service_root.exists():
                    self.make_tree_writable(service_root)

    def test_unit_executes_only_installed_runtime_and_is_hardened(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3")
        unit = TUNNEL.service_unit(runtime, TUNNEL.DEFAULT_PORT)
        exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
        self.assertIn(str(runtime / "remotexpc_tunnel.py"), exec_start)
        self.assertIn(f'"--service-runtime" "{runtime}"', exec_start)
        self.assertNotIn("--appium-home", exec_start)
        self.assertNotIn(str(DEVICE_ROOT), exec_start)
        for contract in (
            "ProtectHome=true", "NoNewPrivileges=true",
            "CapabilityBoundingSet=CAP_NET_ADMIN", "ProtectSystem=strict",
        ):
            self.assertIn(contract, unit)
        parsed = TUNNEL.parser().parse_args([
            "install-unit", "--appium-home", "/private/appium",
        ])
        self.assertEqual(Path("/etc/systemd/system/overte-ios-remotexpc.service"),
                         parsed.unit_path)
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-unit-") as name:
            unit_path = Path(name) / TUNNEL.UNIT_NAME
            unit_path.write_text(unit, encoding="utf-8")
            unit_path.chmod(0o644)
            TUNNEL.verify_installed_unit(
                runtime, TUNNEL.DEFAULT_PORT, unit_path, os.geteuid(),
            )
            unit_path.chmod(0o664)
            with self.assertRaisesRegex(TUNNEL.TunnelError, "root-owned and protected"):
                TUNNEL.verify_installed_unit(
                    runtime, TUNNEL.DEFAULT_PORT, unit_path, os.geteuid(),
                )

    def test_status_defaults_to_versioned_service_runtime_not_appium_home(self):
        arguments = TUNNEL.parser().parse_args(["status"])
        self.assertEqual(
            Path("/usr/local/lib/overte-ios-remotexpc/5.15.3"),
            arguments.service_runtime,
        )
        self.assertFalse(hasattr(arguments, "appium_home"))


if __name__ == "__main__":
    unittest.main()
