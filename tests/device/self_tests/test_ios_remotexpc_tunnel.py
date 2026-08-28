#!/usr/bin/env python3
"""Device-free checks for the Fedora RemoteXPC service wrapper."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


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

    def test_pymobiledevice3_keeper_ignores_test_plan_completion(self):
        source = TUNNEL.PYMOBILEDEVICE3_XCTEST_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        keep_alive_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AppiumKeepAliveEvent"
        )
        namespace = {"asyncio": asyncio}
        module = ast.fix_missing_locations(ast.Module(
            body=[keep_alive_class], type_ignores=[]
        ))
        exec(compile(module, str(TUNNEL.PYMOBILEDEVICE3_XCTEST_FILE), "exec"),
             namespace)

        async def exercise() -> None:
            event = namespace["AppiumKeepAliveEvent"]()
            event.set()
            self.assertFalse(event.is_set())
            event.stop()
            self.assertTrue(event.is_set())

        asyncio.run(exercise())
        run_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and any(keyword.arg == "test_done_event"
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id == "keep_alive"
                    for keyword in node.keywords)
        ]
        self.assertEqual(1, len(run_calls))

    def test_pymobiledevice3_keeper_diagnostics_are_phase_only(self):
        source = TUNNEL.PYMOBILEDEVICE3_XCTEST_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        phases = {
            "host-platform", "parent-death-signal", "parent-lost", "request",
            "request-endpoint", "request-environment", "runtime-version",
            "rsd-connect", "rsd-identity", "xctest-config", "xctest-start",
            "wda-ready", "wda-ready-runner-disconnected",
            "wda-ready-runner-error", "wda-ready-runner-returned",
            "wda-ready-runner-runtime", "wda-ready-runner-timeout",
            "wda-ready-timeout", "session-lifetime",
            "session-lifetime-runner-disconnected",
            "session-lifetime-runner-error",
            "session-lifetime-runner-returned",
            "session-lifetime-runner-runtime",
            "session-lifetime-runner-timeout", "unexpected",
        }
        assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "FAILURE_PHASES"
                    for target in node.targets)
        )
        self.assertEqual(phases, ast.literal_eval(assignment.value))
        self.assertIn(
            "error: immutable Fedora XCTest keeper failed phase={phase}", source
        )
        self.assertNotIn("str(error)", source)

        host_ops = TUNNEL.WDA_HOST_OPS_FILE.read_text(encoding="utf-8")
        self.assertIn("stdio: ['pipe', 'pipe', 'pipe']", host_ops)
        self.assertIn("KEEPER_FAILURE_PHASES.has(match[1])", host_ops)
        self.assertIn("(phase: ${diagnosticPhase})", host_ops)
        self.assertNotIn("{cause: error}", host_ops)
        self.assertIn(
            "child.exitCode !== null || child.signalCode !== null", host_ops
        )
        self.assertIn("XCTest keeper could not be reaped", host_ops)
        self.assertIn("'host-platform', 'keeper-reap',", host_ops)
        self.assertIn("phase || (keeperCleanupFailed ? 'keeper-reap' : null)", host_ops)
        self.assertIn("KEEPER_GRACEFUL_STOP_MS = 12000", host_ops)
        self.assertIn("KEEPER_FORCE_REAP_MS = 3000", host_ops)
        self.assertIn("setTimeout(() => resolve(false), KEEPER_GRACEFUL_STOP_MS)", host_ops)
        self.assertIn("setTimeout(() => resolve(false), KEEPER_FORCE_REAP_MS)", host_ops)
        previous_guard = host_ops.index("if (previous) {")
        readiness_timeout = host_ops.index("const boundedTimeout", previous_guard)
        guarded_startup = host_ops[previous_guard:readiness_timeout]
        self.assertEqual(1, guarded_startup.count("terminateExactRunner"))
        self.assertNotIn(
            "}\n    await terminateExactRunner(driver, udid, bundleId);",
            guarded_startup,
        )

    def make_source_runtime(self, root: Path) -> tuple[Path, Path]:
        appium_home = root / "appium-home"
        appium_home.mkdir()
        shutil.copy2(TUNNEL.PACKAGE_FILE, appium_home / "package.json")
        shutil.copy2(TUNNEL.NPM_LOCK_FILE, appium_home / "package-lock.json")
        package = appium_home / "node_modules/appium-ios-remotexpc"
        (package / "scripts").mkdir(parents=True)
        (package / "scripts/tunnel-creation.mjs").write_text(
            "console.log('tunnel');\n", encoding="utf-8",
        )
        (package / "package.json").write_text(json.dumps({
            "name": "appium-ios-remotexpc", "version": "5.15.3",
        }), encoding="utf-8")
        direct = {
            "appium": "3.7.0",
            "appium-xcuitest-driver": "12.8.0",
            "appium-webdriveragent": "16.8.0",
        }
        for name, version in direct.items():
            root_path = appium_home / "node_modules" / name
            root_path.mkdir(parents=True, exist_ok=True)
            (root_path / "package.json").write_text(json.dumps({
                "name": name, "version": version,
            }), encoding="utf-8")
        appium_entry = appium_home / "node_modules/appium/build/lib/main.js"
        appium_entry.parent.mkdir(parents=True)
        appium_entry.write_text("export {};\n", encoding="utf-8")
        ios_device = appium_home / (
            "node_modules/appium-xcuitest-driver/node_modules/appium-ios-device/package.json"
        )
        ios_device.parent.mkdir(parents=True, exist_ok=True)
        ios_device.write_text(json.dumps({
            "name": "appium-ios-device", "version": "3.1.21",
        }), encoding="utf-8")
        real_device = appium_home / (
            "node_modules/appium-xcuitest-driver/build/lib/device/real-device-management.js"
        )
        real_device.parent.mkdir(parents=True, exist_ok=True)
        real_device.write_text("export class RealDevice {}\n", encoding="utf-8")
        host_ops = appium_home.joinpath(*TUNNEL.XCUITEST_WDA_HOST_OPS.parts[1:])
        host_ops.write_text("export const upstreamHostOps = true;\n", encoding="utf-8")
        node = root / "node"
        node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        node.chmod(0o700)
        return appium_home, node

    def make_pymobiledevice3_runtime(self, root: Path, appium_home: Path) -> tuple[Path, dict]:
        home = root / "pymobiledevice3-home"
        site_packages = home / "lib/python3.14/site-packages"
        package = site_packages / "pymobiledevice3"
        distribution = site_packages / "pymobiledevice3-11.1.5.dist-info"
        package.mkdir(parents=True)
        distribution.mkdir()
        (package / "__init__.py").write_text(
            "__version__ = '11.1.5'\n", encoding="utf-8",
        )
        (distribution / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: pymobiledevice3\nVersion: 11.1.5\n",
            encoding="utf-8",
        )
        (distribution / "RECORD").write_text("\n", encoding="utf-8")
        upstream_host_ops = appium_home.joinpath(
            *TUNNEL.XCUITEST_WDA_HOST_OPS.parts[1:]
        )
        locked = dict(TUNNEL.load_lock()["appium"]["iosRuntime"]["pymobiledevice3"])
        locked.update({
            "distributionCount": 1,
            "freezeSha256": hashlib.sha256(
                b"pymobiledevice3==11.1.5\n"
            ).hexdigest(),
            "sitePackagesTreeSha256": TUNNEL.python_site_packages_tree_sha256(
                site_packages
            ),
            "upstreamWdaHostOpsSha256": TUNNEL.file_sha256(upstream_host_ops),
        })
        return home, locked

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

    @staticmethod
    def fake_extension_template(_appium_home: Path, _node: Path,
                                destination: Path, template: Path) -> None:
        if not os.access(_node, os.X_OK):
            raise AssertionError("staged Node must be executable before Appium attestation")
        driver = destination / "appium/node_modules/appium-xcuitest-driver"
        template.write_text(
            "drivers:\n  xcuitest:\n"
            "    pkgName: appium-xcuitest-driver\n"
            "    version: 12.8.0\n"
            f"    installPath: {driver}\n"
            "plugins: {}\nschemaRev: 4\n",
            encoding="utf-8",
        )

    def test_runtime_resolution_requires_exact_locked_version(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-runtime-") as name:
            root = Path(name)
            appium_home, _node = self.make_source_runtime(root)
            package = appium_home / "node_modules/appium-ios-remotexpc"
            (package / "package.json").write_text(json.dumps({
                "name": "appium-ios-remotexpc", "version": "0.0.1",
            }), encoding="utf-8")
            with self.assertRaisesRegex(TUNNEL.TunnelError, "differs from its exact pin"):
                TUNNEL.resolve_runtime(appium_home)

    def test_pymobiledevice3_site_packages_are_inventory_and_tree_attested(self):
        with tempfile.TemporaryDirectory(prefix="overte-pymobiledevice3-runtime-") as name:
            root = Path(name)
            appium_home, _node = self.make_source_runtime(root)
            home, locked = self.make_pymobiledevice3_runtime(root, appium_home)
            site_packages = home / "lib/python3.14/site-packages"
            with patch.object(TUNNEL, "pymobiledevice3_lock", return_value=locked):
                self.assertEqual(
                    site_packages, TUNNEL.pymobiledevice3_site_packages(
                        home, TUNNEL.load_lock()
                    ),
                )
                (site_packages / "pymobiledevice3/__init__.py").write_text(
                    "__version__ = 'tampered'\n", encoding="utf-8",
                )
                with self.assertRaisesRegex(
                        TUNNEL.TunnelError, "site-packages bytes differ"):
                    TUNNEL.pymobiledevice3_site_packages(home, TUNNEL.load_lock())

    def test_install_rejects_drifted_upstream_host_ops_before_overlay(self):
        with tempfile.TemporaryDirectory(prefix="overte-host-ops-drift-") as name:
            root = Path(name)
            appium_home, node = self.make_source_runtime(root)
            pymobiledevice3_home, locked = self.make_pymobiledevice3_runtime(
                root, appium_home
            )
            upstream = appium_home.joinpath(*TUNNEL.XCUITEST_WDA_HOST_OPS.parts[1:])
            upstream.write_text("export const drifted = true;\n", encoding="utf-8")
            service_root = root / "service"
            try:
                with patch.object(
                        TUNNEL, "resolve_runtime", return_value=(
                            node, appium_home / "node_modules/appium-ios-remotexpc/"
                            "scripts/tunnel-creation.mjs",
                        )), patch.object(
                            TUNNEL, "prepare_appium_extension_template",
                            side_effect=self.fake_extension_template), patch.object(
                            TUNNEL, "pymobiledevice3_lock", return_value=locked), \
                        patch.object(
                            TUNNEL, "validate_host_python",
                            return_value=Path(sys.executable).resolve()):
                    with self.assertRaisesRegex(
                            TUNNEL.TunnelError, "host operations differ"):
                        TUNNEL.install_service_runtime(
                            appium_home, pymobiledevice3_home,
                            service_root=service_root,
                        )
            finally:
                if service_root.exists():
                    self.make_tree_writable(service_root)

    def test_install_creates_versioned_immutable_runtime_copy(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-install-") as name:
            root = Path(name)
            appium_home, node = self.make_source_runtime(root)
            pymobiledevice3_home, pymobiledevice3_lock = \
                self.make_pymobiledevice3_runtime(root, appium_home)
            xattr_source = appium_home / "package.json"
            xattr_added = False
            try:
                os.setxattr(xattr_source, b"user.overte-copy-test", b"must-not-copy")
                xattr_added = True
            except (AttributeError, OSError):
                pass
            service_root = root / "service"
            try:
                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")), patch.object(
                        TUNNEL, "prepare_appium_extension_template",
                        side_effect=self.fake_extension_template), patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()), patch.object(
                        TUNNEL, "restore_security_context") as restore_context:
                    installed = TUNNEL.install_service_runtime(
                        appium_home, pymobiledevice3_home, service_root=service_root,
                    )
                    self.assertEqual(installed, restore_context.call_args.args[0])
                self.assertEqual(service_root / "5.15.3-r12", installed)
                self.assertEqual(
                    Path(TUNNEL.__file__).read_bytes(),
                    (installed / "remotexpc_tunnel.py").read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.DEVICE_PREFLIGHT_FILE.read_bytes(),
                    (installed / TUNNEL.DEVICE_PREFLIGHT_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.DEVICE_INSTALL_FILE.read_bytes(),
                    (installed / TUNNEL.DEVICE_INSTALL_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.DEVICE_DDI_FILE.read_bytes(),
                    (installed / TUNNEL.DEVICE_DDI_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.DEVICE_PROCESS_FILE.read_bytes(),
                    (installed / TUNNEL.DEVICE_PROCESS_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.PYMOBILEDEVICE3_XCTEST_FILE.read_bytes(),
                    (installed / TUNNEL.PYMOBILEDEVICE3_XCTEST_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.WDA_HOST_OPS_FILE.read_bytes(),
                    (installed / TUNNEL.XCUITEST_WDA_HOST_OPS).read_bytes(),
                )
                self.assertEqual(
                    TUNNEL.WDA_HOST_OPS_FILE.read_bytes(),
                    (installed / TUNNEL.WDA_HOST_OPS_FILE.name).read_bytes(),
                )
                self.assertEqual(
                    pymobiledevice3_lock["sitePackagesTreeSha256"],
                    TUNNEL.python_site_packages_tree_sha256(
                        installed / TUNNEL.PYMOBILEDEVICE3_SITE_PACKAGES
                    ),
                )
                self.assertEqual(
                    TUNNEL.ARTIFACT_TREE_FILE.read_bytes(),
                    (installed / TUNNEL.ARTIFACT_TREE_FILE.name).read_bytes(),
                )
                self.assertFalse(any(installed.rglob(".bin")))
                if xattr_added:
                    self.assertNotIn(
                        "user.overte-copy-test",
                        os.listxattr(installed / "appium/package.json"),
                    )
                with patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()):
                    TUNNEL.verify_service_runtime(installed, os.geteuid())
                with patch.object(
                        TUNNEL, "visible_system_root_owner_uid", return_value=os.geteuid()), \
                        patch.object(TUNNEL, "pymobiledevice3_lock",
                                     return_value=pymobiledevice3_lock), patch.object(
                            TUNNEL, "validate_host_python",
                            return_value=Path(sys.executable).resolve()):
                    TUNNEL.verify_service_runtime(installed)
                source_file = TUNNEL.__file__
                try:
                    TUNNEL.__file__ = str(installed / "remotexpc_tunnel.py")
                    self.assertEqual(installed, TUNNEL.default_service_runtime())
                finally:
                    TUNNEL.__file__ = source_file
                for path in (installed, *installed.rglob("*")):
                    self.assertEqual(0, path.lstat().st_mode & 0o222)
                    self.assertEqual(os.geteuid(), path.lstat().st_uid)

                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")), patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()), patch.object(
                        TUNNEL, "restore_security_context") as restore_existing:
                    self.assertEqual(
                        installed,
                        TUNNEL.install_service_runtime(
                            appium_home, pymobiledevice3_home, service_root=service_root,
                        ),
                    )
                    restore_existing.assert_called_once_with(installed)

                drifted_helper = root / "drift" / TUNNEL.DEVICE_PREFLIGHT_FILE.name
                drifted_helper.parent.mkdir()
                drifted_helper.write_text("// drift\n", encoding="utf-8")
                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")), patch.object(
                        TUNNEL, "DEVICE_PREFLIGHT_FILE", drifted_helper), patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()), patch.object(
                        TUNNEL, "restore_security_context") as rejected_restore:
                    with self.assertRaisesRegex(
                            TUNNEL.TunnelError, "differs from the audited source"):
                        TUNNEL.install_service_runtime(
                            appium_home, pymobiledevice3_home, service_root=service_root,
                        )
                    rejected_restore.assert_not_called()
            finally:
                if service_root.exists():
                    self.make_tree_writable(service_root)

    def test_visible_root_owner_accepts_only_root_or_kernel_overflow_uid(self):
        root = MagicMock()
        root.is_symlink.return_value = False
        value = MagicMock()
        value.st_mode = stat.S_IFDIR | 0o755
        root.lstat.return_value = value
        overflow = MagicMock()

        value.st_uid = 0
        self.assertEqual(0, TUNNEL.visible_root_owner_uid(root, overflow))
        overflow.read_text.assert_not_called()

        value.st_uid = 65534
        overflow.read_text.return_value = "65534\n"
        self.assertEqual(65534, TUNNEL.visible_root_owner_uid(root, overflow))
        overflow.read_text.return_value = "12345\n"
        with self.assertRaisesRegex(TUNNEL.TunnelError, "unexpected owner"):
            TUNNEL.visible_root_owner_uid(root, overflow)

    def test_host_python_accepts_the_visible_root_owner_in_a_user_namespace(self):
        configured = Path(
            TUNNEL.pymobiledevice3_lock(TUNNEL.load_lock())["pythonExecutable"]
        )
        with patch.object(
                TUNNEL, "visible_root_owner_uid",
                return_value=configured.lstat().st_uid):
            self.assertEqual(configured, TUNNEL.validate_host_python(TUNNEL.load_lock()))
        with patch.object(
                TUNNEL, "visible_root_owner_uid",
                return_value=configured.lstat().st_uid + 1):
            with self.assertRaisesRegex(
                    TUNNEL.TunnelError, "host Python executable differs"):
                TUNNEL.validate_host_python(TUNNEL.load_lock())

    def test_trusted_runtime_path_rejects_drift_writable_or_symlink_parent(self):
        with tempfile.TemporaryDirectory(prefix="overte-runtime-parents-") as name:
            base = Path(name)
            service_root = base / "service"
            runtime = service_root / "5.15.3-r12"
            runtime.mkdir(parents=True)
            owner = os.geteuid()
            with patch.object(
                    TUNNEL, "service_runtime_path", return_value=runtime), patch.object(
                    TUNNEL, "SYSTEM_RUNTIME_PARENT_CHAIN", (base, service_root)):
                TUNNEL.require_trusted_runtime_path(runtime, owner)
                with self.assertRaisesRegex(TUNNEL.TunnelError, "exact locked"):
                    TUNNEL.require_trusted_runtime_path(runtime / "other", owner)
                service_root.chmod(0o775)
                with self.assertRaisesRegex(TUNNEL.TunnelError, "root-owned and protected"):
                    TUNNEL.require_trusted_runtime_path(runtime, owner)
                service_root.chmod(0o755)
                link = base / "link"
                link.symlink_to(service_root, target_is_directory=True)
                with patch.object(TUNNEL, "SYSTEM_RUNTIME_PARENT_CHAIN", (base, link)):
                    with self.assertRaisesRegex(
                            TUNNEL.TunnelError, "root-owned and protected"):
                        TUNNEL.require_trusted_runtime_path(runtime, owner)

    def test_visible_system_owner_rejects_unprivileged_caller_identity(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        with patch.object(TUNNEL, "visible_root_owner_uid", return_value=1000), patch.object(
                TUNNEL.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(TUNNEL.TunnelError, "unprivileged caller"):
                TUNNEL.visible_system_root_owner_uid(runtime)
        with patch.object(TUNNEL, "visible_root_owner_uid", return_value=65534), patch.object(
                TUNNEL.os, "geteuid", return_value=1000), patch.object(
                TUNNEL, "require_trusted_runtime_path") as trusted:
            self.assertEqual(65534, TUNNEL.visible_system_root_owner_uid(runtime))
            trusted.assert_called_once_with(runtime, 65534)

    def test_selinux_restorecon_is_exact_and_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-selinux-") as name:
            root = Path(name)
            enforce = root / "enforce"
            enforce.write_text("1", encoding="ascii")
            restorecon = root / "restorecon"
            restorecon.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            restorecon.chmod(0o755)
            runtime = root / "runtime"
            runtime.mkdir()
            owner = os.geteuid()
            with patch.object(TUNNEL, "SELINUX_ENFORCE_FILE", enforce), patch.object(
                    TUNNEL, "RESTORECON_CANDIDATES", (restorecon,)), patch.object(
                    TUNNEL.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0)) as execute:
                TUNNEL.restore_security_context(runtime, owner_uid=owner)
            self.assertEqual(
                [str(restorecon), "-RF", "--", str(runtime)],
                execute.call_args.args[0],
            )

            with patch.object(TUNNEL, "SELINUX_ENFORCE_FILE", enforce), patch.object(
                    TUNNEL, "RESTORECON_CANDIDATES", (restorecon,)), patch.object(
                    TUNNEL.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(TUNNEL.TunnelError, "context restoration"):
                    TUNNEL.restore_security_context(runtime, owner_uid=owner)

    def test_service_runtime_rejects_writable_or_wrong_owner_tree(self):
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-mode-") as name:
            root = Path(name)
            appium_home, node = self.make_source_runtime(root)
            pymobiledevice3_home, pymobiledevice3_lock = \
                self.make_pymobiledevice3_runtime(root, appium_home)
            service_root = root / "service"
            try:
                with patch.object(
                        TUNNEL, "resolve_runtime",
                        return_value=(node, appium_home / "node_modules/appium-ios-remotexpc/"
                                      "scripts/tunnel-creation.mjs")), patch.object(
                        TUNNEL, "prepare_appium_extension_template",
                        side_effect=self.fake_extension_template), patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()):
                    installed = TUNNEL.install_service_runtime(
                        appium_home, pymobiledevice3_home, service_root=service_root,
                    )
                marker = installed / TUNNEL.RUNTIME_MARKER
                marker.chmod(0o644)
                with patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()):
                    with self.assertRaisesRegex(TUNNEL.TunnelError, "writable"):
                        TUNNEL.verify_service_runtime(installed, os.geteuid())
                marker.chmod(0o444)
                with patch.object(
                        TUNNEL, "pymobiledevice3_lock",
                        return_value=pymobiledevice3_lock), patch.object(
                        TUNNEL, "validate_host_python",
                        return_value=Path(sys.executable).resolve()):
                    with self.assertRaisesRegex(TUNNEL.TunnelError, "owned by root"):
                        TUNNEL.verify_service_runtime(installed, os.geteuid() + 1)
            finally:
                if service_root.exists():
                    self.make_tree_writable(service_root)

    def test_unit_executes_only_installed_runtime_and_is_hardened(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        unit = TUNNEL.service_unit(runtime, TUNNEL.DEFAULT_PORT)
        exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
        working_directory = next(
            line for line in unit.splitlines() if line.startswith("WorkingDirectory=")
        )
        self.assertIn(str(runtime / "remotexpc_tunnel.py"), exec_start)
        self.assertIn(f'"--service-runtime" "{runtime}"', exec_start)
        self.assertEqual(f"WorkingDirectory={runtime}", working_directory)
        self.assertNotIn("--appium-home", exec_start)
        self.assertNotIn(str(DEVICE_ROOT), exec_start)
        for contract in (
            "ProtectHome=true", "NoNewPrivileges=true",
            "CapabilityBoundingSet=CAP_NET_ADMIN", "ProtectSystem=strict",
            "StartLimitBurst=5", "Restart=on-failure",
            "StateDirectory=overte-ios-remotexpc", "StateDirectoryMode=0700",
            "Environment=XDG_DATA_HOME=\"/var/lib/overte-ios-remotexpc\"",
        ):
            self.assertIn(contract, unit)
        self.assertNotIn("/root", unit)
        parsed = TUNNEL.parser().parse_args([
            "install-unit", "--appium-home", "/private/appium",
            "--pymobiledevice3-home", "/private/pymobiledevice3",
        ])
        self.assertEqual(Path("/etc/systemd/system/overte-ios-remotexpc.service"),
                         parsed.unit_path)
        self.assertEqual(Path("/private/pymobiledevice3"), parsed.pymobiledevice3_home)
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

    def test_generated_unit_passes_systemd_parser(self):
        analyzer = shutil.which("systemd-analyze")
        if analyzer is None:
            self.skipTest("systemd-analyze is unavailable")
        with tempfile.TemporaryDirectory(prefix="overte-remotexpc-systemd-") as name:
            root = Path(name)
            runtime = root / "runtime"
            runtime.mkdir()
            wrapper = runtime / "remotexpc_tunnel.py"
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o755)
            unit_path = root / TUNNEL.UNIT_NAME
            unit_path.write_text(
                TUNNEL.service_unit(runtime, TUNNEL.DEFAULT_PORT), encoding="utf-8"
            )
            result = subprocess.run(
                [analyzer, "verify", str(unit_path)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=30, check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout)

    def test_unit_activation_resets_failure_limit_before_start(self):
        with patch.object(TUNNEL.subprocess, "run") as execute:
            TUNNEL.activate_systemd_unit()
        self.assertEqual([
            ["systemctl", "daemon-reload"],
            ["systemctl", "reset-failed", TUNNEL.UNIT_NAME],
            ["systemctl", "enable", TUNNEL.UNIT_NAME],
            ["systemctl", "restart", TUNNEL.UNIT_NAME],
        ], [call.args[0] for call in execute.call_args_list])

    def test_status_defaults_to_versioned_service_runtime_not_appium_home(self):
        arguments = TUNNEL.parser().parse_args(["status"])
        self.assertEqual(
            Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12"),
            arguments.service_runtime,
        )
        self.assertFalse(hasattr(arguments, "appium_home"))

    def test_appium_server_is_root_owned_loopback_and_privacy_bounded(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        with tempfile.TemporaryDirectory(prefix="overte-appium-state-") as name:
            state = Path(name)
            state.chmod(0o700)
            arguments = TUNNEL.parser().parse_args([
                "appium-server", "--state-root", str(state),
            ])
            self.assertEqual(runtime, arguments.service_runtime)
            child = MagicMock()
            child.wait.return_value = 0
            child.poll.return_value = None
            observed = {}

            def start_appium(command, **options):
                data_home = Path(options["env"]["XDG_DATA_HOME"])
                port_file = data_home / TUNNEL.TUNNEL_PORT_ITEM
                observed["registryPort"] = port_file.read_text(encoding="ascii")
                observed["registryMode"] = stat.S_IMODE(port_file.stat().st_mode)
                observed["dataHome"] = data_home
                return child

            with patch.object(
                    TUNNEL, "verify_service_runtime",
                    return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                    TUNNEL, "validate_appium_extension_template",
                    return_value=SCRIPT), patch.object(
                    TUNNEL.subprocess, "Popen", side_effect=start_appium) as execute, patch.object(
                    TUNNEL.signal, "signal"):
                self.assertEqual(0, TUNNEL.appium_server(arguments))
            command = execute.call_args.args[0]
            options = execute.call_args.kwargs
            self.assertIn(str(runtime / "appium/node_modules/appium/build/lib/main.js"), command)
            self.assertIn("127.0.0.1", command)
            self.assertIn("--use-drivers", command)
            self.assertIn("xcuitest", command)
            self.assertIn("--log-level", command)
            self.assertIn("error", command)
            self.assertEqual(runtime / "appium", options["cwd"])
            self.assertTrue(options["env"]["APPIUM_HOME"].startswith(str(state)))
            self.assertNotIn(str(Path.home()), options["env"]["APPIUM_HOME"])
            self.assertEqual("42314", observed["registryPort"])
            self.assertEqual(0o600, observed["registryMode"])
            self.assertTrue(str(observed["dataHome"]).startswith(str(state)))
            self.assertEqual(str(observed["dataHome"]), options["env"]["XDG_DATA_HOME"])
            self.assertEqual([], list(state.iterdir()))

    def test_device_preflight_passes_udid_only_over_stdin_and_redacts_output(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        arguments = TUNNEL.parser().parse_args(["device-preflight"])
        private_udid = "00008101-1234567890ABCDEF"
        stdin = MagicMock()
        stdin.buffer = io.BytesIO(json.dumps({"udid": private_udid}).encode("utf-8"))
        output = io.StringIO()
        with patch.object(
                TUNNEL, "verify_service_runtime",
                return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                TUNNEL.sys, "stdin", stdin), patch.object(
                TUNNEL.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0)) as execute, redirect_stdout(output):
            self.assertEqual(0, TUNNEL.device_preflight(arguments))
        command = execute.call_args.args[0]
        self.assertNotIn(private_udid, command)
        self.assertIn(private_udid, execute.call_args.kwargs["input"].decode("utf-8"))
        self.assertNotIn(private_udid, output.getvalue())
        self.assertEqual("PASS: installed iOS app contracts verified\n", output.getvalue())

        inventory = {
            "overteBundleId": "com.sideloadly.slot.overte",
            "wdaBundleId": "com.sideloadly.slot.wda",
            "wdaUpdatedBundleId": "com.sideloadly.slot.wda",
            "wdaBundleIdSuffix": "",
        }
        stdin = MagicMock()
        stdin.buffer = io.BytesIO(json.dumps({
            "udid": private_udid, "discoverRemappedBundleIds": True,
        }).encode("utf-8"))
        output = io.StringIO()
        with patch.object(
                TUNNEL, "verify_service_runtime",
                return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                TUNNEL.sys, "stdin", stdin), patch.object(
                TUNNEL.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, stdout=json.dumps(inventory).encode("utf-8"))), \
                redirect_stdout(output):
            self.assertEqual(0, TUNNEL.device_preflight(arguments))
        self.assertEqual(inventory, json.loads(output.getvalue()))
        self.assertNotIn(private_udid, output.getvalue())


    def test_private_developer_disk_image_is_digest_and_manifest_bound(self):
        with tempfile.TemporaryDirectory(prefix="overte-private-ddi-") as name:
            root = Path(name)
            root.chmod(0o700)
            image = root / "Image.dmg"
            trustcache = root / "Image.dmg.trustcache"
            manifest_path = root / "BuildManifest.plist"
            image.write_bytes(b"pinned developer disk image")
            trustcache.write_bytes(b"pinned trust cache")
            manifest_path.write_bytes(plistlib.dumps({
                "ProductBuildVersion": "27A5228h",
                "BuildIdentities": [{"Manifest": {
                    "PersonalizedDMG": {
                        "Digest": bytes.fromhex(TUNNEL.file_sha384(image)),
                        "Info": {"Path": "Image.dmg", "HashMethod": "sha2-384"},
                    },
                    "LoadableTrustCache": {
                        "Digest": bytes.fromhex(TUNNEL.file_sha384(trustcache)),
                        "Info": {"Path": "Image.dmg.trustcache"},
                    },
                }}],
            }))
            for path in (image, trustcache, manifest_path):
                path.chmod(0o600)
            lock = TUNNEL.load_lock()
            lock["developerDiskImage"] = {
                "provenance": {"productBuildVersion": "27A5228h"},
                "files": {
                    path.name: {
                        "size": path.stat().st_size,
                        "sha256": TUNNEL.file_sha256(path),
                        **({"sha1": TUNNEL.file_sha1(path),
                            "sha384": TUNNEL.file_sha384(path)}
                           if path != manifest_path else {}),
                    }
                    for path in (image, trustcache, manifest_path)
                },
            }
            request = {
                "image": str(image), "manifest": str(manifest_path),
                "trustcache": str(trustcache),
            }
            self.assertEqual(
                (image, manifest_path, trustcache),
                TUNNEL.validate_developer_disk_image(request, lock),
            )

            image.write_bytes(b"tampered")
            with self.assertRaisesRegex(TUNNEL.TunnelError, "differs from its lock"):
                TUNNEL.validate_developer_disk_image(request, lock)

            image.write_bytes(b"pinned developer disk image")
            image.chmod(0o644)
            with self.assertRaisesRegex(TUNNEL.TunnelError, "mode"):
                TUNNEL.validate_developer_disk_image(request, lock)
            image.chmod(0o600)

            extra_link = root / "unexpected-hardlink"
            os.link(image, extra_link)
            with self.assertRaisesRegex(TUNNEL.TunnelError, "link count"):
                TUNNEL.validate_developer_disk_image(request, lock)
            extra_link.unlink()

            linked_root = root / "linked"
            linked_root.mkdir(mode=0o700)
            linked_image = linked_root / "Image.dmg"
            linked_image.symlink_to(image)
            linked_request = {**request, "image": str(linked_image)}
            with self.assertRaisesRegex(TUNNEL.TunnelError, "safe absolute"):
                TUNNEL.validate_developer_disk_image(linked_request, lock)

    def test_device_ddi_passes_private_values_only_on_stdin(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        private_udid = "00008101-1234567890ABCDEF"
        private_root = Path("/private/operator-ddi")
        request = {
            "udid": private_udid,
            "image": str(private_root / "Image.dmg"),
            "manifest": str(private_root / "BuildManifest.plist"),
            "trustcache": str(private_root / "Image.dmg.trustcache"),
        }
        stdin = MagicMock()
        stdin.buffer = io.BytesIO(json.dumps(request).encode("utf-8"))
        output = io.StringIO()
        observed = {}

        def execute_helper(command, **options):
            payload = json.loads(options["input"])
            observed.update(payload)
            port_file = Path(options["env"]["XDG_DATA_HOME"]) / TUNNEL.TUNNEL_PORT_ITEM
            observed["port"] = port_file.read_text(encoding="ascii")
            observed["mode"] = stat.S_IMODE(port_file.stat().st_mode)
            return subprocess.CompletedProcess(command, 0)

        arguments = TUNNEL.parser().parse_args(["device-ddi-mount"])
        with patch.object(
                TUNNEL, "verify_service_runtime",
                return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                TUNNEL, "load_lock", return_value=TUNNEL.load_lock()), patch.object(
                TUNNEL, "validate_developer_disk_image",
                side_effect=lambda value, _lock: (
                    Path(value["image"]), Path(value["manifest"]),
                    Path(value["trustcache"]),
                )), patch.object(
                TUNNEL.shutil, "copyfile",
                side_effect=lambda _source, destination: Path(destination).write_bytes(b"fixture")), \
                patch.object(
                TUNNEL.sys, "stdin", stdin), patch.object(
                TUNNEL.subprocess, "run", side_effect=execute_helper) as execute, \
                redirect_stdout(output):
            self.assertEqual(0, TUNNEL.device_ddi(arguments))
        command = " ".join(map(str, execute.call_args.args[0]))
        for private in (private_udid, *request.values()):
            self.assertNotIn(private, command + output.getvalue())
        self.assertEqual("mount", observed["action"])
        self.assertEqual(private_udid, observed["udid"])
        self.assertEqual("42314", observed["port"])
        self.assertEqual(0o600, observed["mode"])
        self.assertEqual(
            "PASS: iOS Personalized DDI and XCTest services are ready\n",
            output.getvalue(),
        )

    def test_device_app_terminate_passes_private_values_only_on_stdin(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        private_udid = "00008101-1234567890ABCDEF"
        private_bundle = "com.private.slot.overte"
        stdin = MagicMock()
        stdin.buffer = io.BytesIO(json.dumps({
            "udid": private_udid, "bundleId": private_bundle,
        }).encode("utf-8"))
        output = io.StringIO()
        observed = {}

        def execute_helper(command, **options):
            observed.update(json.loads(options["input"]))
            port_file = Path(options["env"]["XDG_DATA_HOME"]) / TUNNEL.TUNNEL_PORT_ITEM
            observed["port"] = port_file.read_text(encoding="ascii")
            observed["mode"] = stat.S_IMODE(port_file.stat().st_mode)
            return subprocess.CompletedProcess(command, 0)

        arguments = TUNNEL.parser().parse_args(["device-app-terminate"])
        with patch.object(
                TUNNEL, "verify_service_runtime",
                return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                TUNNEL.sys, "stdin", stdin), patch.object(
                TUNNEL.subprocess, "run", side_effect=execute_helper) as execute, \
                redirect_stdout(output):
            self.assertEqual(0, TUNNEL.device_app_terminate(arguments))
        command = " ".join(map(str, execute.call_args.args[0]))
        self.assertNotIn(private_udid, command + output.getvalue())
        self.assertNotIn(private_bundle, command + output.getvalue())
        self.assertEqual(private_udid, observed["udid"])
        self.assertEqual(private_bundle, observed["bundleId"])
        self.assertEqual("42314", observed["port"])
        self.assertEqual(0o600, observed["mode"])
        self.assertEqual("PASS: iOS application is not running\n", output.getvalue())

    def test_javascript_process_helper_kills_and_verifies_the_exact_bundle(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-process-helper-") as name:
            runtime = Path(name)
            helper = runtime / TUNNEL.DEVICE_PROCESS_FILE.name
            shutil.copy2(TUNNEL.DEVICE_PROCESS_FILE, helper)
            package = runtime / "appium/node_modules/appium-ios-remotexpc"
            module = package / "build/src/index.js"
            module.parent.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({
                "name": "appium-ios-remotexpc", "version": "5.15.3", "type": "module",
            }), encoding="utf-8")
            operations = runtime / "operations.jsonl"
            module.write_text(f"""
import fs from 'node:fs';
const record = (value) => fs.appendFileSync({json.dumps(str(operations))}, value + '\\n');
let running = true;
export const Services = {{
  startDVTService: async () => ({{
    processControl: {{
      getPidForBundleIdentifier: async () => {{ record('get'); return running ? 4123 : 0; }},
      kill: async (pid) => {{ if (pid !== 4123) throw new Error('wrong pid'); record('kill'); running = false; }},
    }},
    dvtService: {{close: async () => record('close')}},
  }}),
}};
""", encoding="utf-8")
            private_request = {
                "udid": "00008101-1234567890ABCDEF",
                "bundleId": "com.private.slot.overte",
            }
            result = subprocess.run(
                ["node", str(helper)], input=json.dumps(private_request), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn(private_request["udid"], result.stdout + result.stderr)
            self.assertNotIn(private_request["bundleId"], result.stdout + result.stderr)
            self.assertEqual(
                ["get", "kill", "get", "close"],
                operations.read_text(encoding="utf-8").splitlines(),
            )

    def test_javascript_ddi_helper_binds_mounted_signature_and_xctest_services(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-ddi-helper-") as name:
            runtime = Path(name)
            helper = runtime / TUNNEL.DEVICE_DDI_FILE.name
            shutil.copy2(TUNNEL.DEVICE_DDI_FILE, helper)
            package = runtime / "appium/node_modules/appium-ios-remotexpc"
            module = package / "build/src/index.js"
            module.parent.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({
                "name": "appium-ios-remotexpc", "version": "5.15.3", "type": "module",
            }), encoding="utf-8")
            operations = runtime / "operations.jsonl"
            module.write_text(f"""
import fs from 'node:fs';
const record = (value) => fs.appendFileSync({json.dumps(str(operations))}, value + '\\n');
let mounted = process.env.FAKE_MOUNTED === '1';
const expectedHash = Buffer.from('ab'.repeat(48), 'hex');
export const Services = {{
  startMobileImageMounterService: async () => ({{
    lookup: async () => {{
      record('lookup');
      return mounted ? [process.env.FAKE_WRONG_SIGNATURE === '1'
        ? Buffer.from('wrong') : expectedHash] : [];
    }},
    unmountImage: async () => {{ record('unmount'); mounted = false; }},
    mount: async () => {{ record('mount'); mounted = true; }},
    cleanup: async () => record('cleanup'),
  }}),
}};
export async function resolveTunnelServicePorts(_udid, services) {{
  record(`services:${{services.join(',')}}`);
}}
""", encoding="utf-8")
            private_udid = "00008101-1234567890ABCDEF"
            image_sha384 = "ab" * 48
            base = {
                "action": "status", "udid": private_udid,
                "imageSha384": image_sha384,
            }
            status = subprocess.run(
                ["node", str(helper)], input=json.dumps(base), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "FAKE_MOUNTED": "1"}, timeout=10, check=False,
            )
            self.assertEqual(0, status.returncode, status.stderr)
            self.assertNotIn(private_udid, status.stdout + status.stderr)
            lines = operations.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "services:com.apple.dt.testmanagerd.remote,"
                "com.apple.instruments.dtservicehub", lines,
            )
            self.assertEqual("cleanup", lines[-1])

            operations.unlink()
            mount = subprocess.run(
                ["node", str(helper)], input=json.dumps({
                    **base, "action": "mount", "image": "/private/Image.dmg",
                    "manifest": "/private/BuildManifest.plist",
                    "trustcache": "/private/Image.dmg.trustcache",
                }), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, check=False,
            )
            self.assertEqual(0, mount.returncode, mount.stderr)
            self.assertEqual(1, operations.read_text().splitlines().count("mount"))

            operations.unlink()
            remount = subprocess.run(
                ["node", str(helper)], input=json.dumps({
                    **base, "action": "mount", "image": "/private/Image.dmg",
                    "manifest": "/private/BuildManifest.plist",
                    "trustcache": "/private/Image.dmg.trustcache",
                }), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "FAKE_MOUNTED": "1"},
                timeout=10, check=False,
            )
            self.assertEqual(0, remount.returncode, remount.stderr)
            self.assertEqual(
                ["lookup", "unmount", "mount", "lookup",
                 "services:com.apple.dt.testmanagerd.remote,"
                 "com.apple.instruments.dtservicehub", "cleanup"],
                operations.read_text(encoding="utf-8").splitlines(),
            )

            operations.unlink()
            rejected = subprocess.run(
                ["node", str(helper)], input=json.dumps(base), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "FAKE_MOUNTED": "1", "FAKE_WRONG_SIGNATURE": "1"},
                timeout=10, check=False,
            )
            self.assertEqual(2, rejected.returncode)
            self.assertNotIn(private_udid, rejected.stdout + rejected.stderr)
            rejected_operations = operations.read_text().splitlines()
            self.assertEqual("cleanup", rejected_operations[-1])
            self.assertNotIn("unmount", rejected_operations)

    def test_device_install_revalidates_receipt_and_passes_private_values_only_on_stdin(self):
        runtime = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r12")
        with tempfile.TemporaryDirectory(prefix="overte-ios-device-install-") as name:
            root = Path(name)
            overte = root / "Overte.ipa"
            wda = root / "WDA.ipa"
            overte.write_bytes(b"overte signed fixture")
            wda.write_bytes(b"wda signed fixture")
            overte.chmod(0o600)
            wda.chmod(0o600)
            prebuilt = root / "WebDriverAgentRunner-Runner.app"
            prebuilt.mkdir(mode=0o700)
            (prebuilt / "Info.plist").write_bytes(b"plist")
            (prebuilt / "Info.plist").chmod(0o600)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "schemaVersion": 1,
                "contract": TUNNEL.PROTECTED_RECEIPT,
                "sourceRevision": "a" * 40,
                "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "notAfter": (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "provenance": {
                    "repository": "noah-be/overte", "repositoryId": 42,
                    "workflow": ".github/workflows/ios-bootstrap.yml",
                    "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
                    "ref": "refs/heads/apple-ios", "runId": 123, "runAttempt": 2,
                },
                "overte": {
                    "path": str(overte), "sha256": TUNNEL.file_sha256(overte),
                    "bundleId": TUNNEL.OVERTE_BUNDLE_ID,
                },
                "wda": {
                    "ipaPath": str(wda), "ipaSha256": TUNNEL.file_sha256(wda),
                    "prebuiltPath": str(prebuilt),
                    "prebuiltTreeSha256": TUNNEL.artifact_tree_sha256(prebuilt),
                    "bundleId": TUNNEL.WDA_BUNDLE_ID,
                },
                "toolchain": {
                    "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
                    "webdriverAgent": "16.8.0",
                },
            }), encoding="utf-8")
            receipt.chmod(0o600)
            private_udid = "00008101-1234567890ABCDEF"
            request = json.dumps({"udid": private_udid, "receipt": str(receipt)})
            stdin = MagicMock()
            stdin.buffer = io.BytesIO(request.encode("utf-8"))
            output = io.StringIO()
            arguments = TUNNEL.parser().parse_args(["device-install"])
            with patch.object(
                    TUNNEL, "verify_service_runtime",
                    return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                    TUNNEL.sys, "stdin", stdin), patch.object(
                    TUNNEL.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0)) as execute, \
                    redirect_stdout(output):
                self.assertEqual(0, TUNNEL.device_install(arguments))
            command = execute.call_args.args[0]
            helper_input = execute.call_args.kwargs["input"].decode("utf-8")
            for private in (private_udid, str(receipt), str(overte), str(wda)):
                self.assertNotIn(private, " ".join(command) + output.getvalue())
            self.assertIn(private_udid, helper_input)
            self.assertIn(str(overte), helper_input)
            self.assertIn(str(wda), helper_input)
            self.assertEqual("PASS: receipt-bound signed iOS apps installed\n", output.getvalue())

            overte.write_bytes(b"receipt tamper")
            rejected_stdin = MagicMock()
            rejected_stdin.buffer = io.BytesIO(request.encode("utf-8"))
            with patch.object(
                    TUNNEL, "verify_service_runtime",
                    return_value=(runtime / "bin/node", runtime / "tunnel.mjs")), patch.object(
                    TUNNEL.sys, "stdin", rejected_stdin), patch.object(
                    TUNNEL.subprocess, "run") as rejected_execute:
                with self.assertRaisesRegex(TUNNEL.TunnelError, "installation request failed"):
                    TUNNEL.device_install(arguments)
            rejected_execute.assert_not_called()

    def test_javascript_device_installer_replaces_both_apps_in_fixed_order(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-install-helper-") as name:
            runtime = Path(name)
            helper = runtime / TUNNEL.DEVICE_INSTALL_FILE.name
            shutil.copy2(TUNNEL.DEVICE_INSTALL_FILE, helper)
            driver = runtime / "appium/node_modules/appium-xcuitest-driver"
            module = driver / "build/lib/device/real-device-management.js"
            module.parent.mkdir(parents=True)
            (driver / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
            operations = runtime / "operations.jsonl"
            module.write_text(f"""
import fs from 'node:fs';
const record = (value) => fs.appendFileSync({json.dumps(str(operations))}, value + '\\n');
export class RealDevice {{
  constructor() {{}}
  async isAppInstalled(bundle) {{ record(`present:${{bundle}}`); return true; }}
  async removeApp(bundle) {{ record(`remove:${{bundle}}`); }}
  async installApp(_path, bundle) {{ record(`install:${{bundle}}`); }}
}}
""", encoding="utf-8")
            overte = runtime / "private-overte.ipa"
            wda = runtime / "private-wda.ipa"
            overte.write_bytes(b"fixture")
            wda.write_bytes(b"fixture")
            private_udid = "00008101-1234567890ABCDEF"
            result = subprocess.run(
                ["node", str(helper)], input=json.dumps({
                    "udid": private_udid, "overteIpa": str(overte), "wdaIpa": str(wda),
                }), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS: signed iOS apps installed\n", result.stdout)
            self.assertNotIn(private_udid, result.stdout + result.stderr)
            lines = operations.read_text(encoding="utf-8").splitlines()
            self.assertEqual([
                f"present:{TUNNEL.OVERTE_BUNDLE_ID}",
                f"remove:{TUNNEL.OVERTE_BUNDLE_ID}",
                f"present:{TUNNEL.WDA_BUNDLE_ID}",
                f"remove:{TUNNEL.WDA_BUNDLE_ID}",
                f"install:{TUNNEL.WDA_BUNDLE_ID}",
                f"install:{TUNNEL.OVERTE_BUNDLE_ID}",
            ], lines)

    def test_javascript_installation_proxy_helper_checks_markers_and_team(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-device-helper-") as name:
            runtime = Path(name)
            helper = runtime / TUNNEL.DEVICE_PREFLIGHT_FILE.name
            shutil.copy2(TUNNEL.DEVICE_PREFLIGHT_FILE, helper)
            package = runtime / (
                "appium/node_modules/appium-xcuitest-driver/node_modules/appium-ios-device"
            )
            package.mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({
                "name": "appium-ios-device", "version": "3.1.21",
            }), encoding="utf-8")
            module = """
const team = 'TEAM123456';
const overte = 'org.overte.interface.e2e';
const wda = 'org.overte.WebDriverAgentRunner.xctrunner';
const common = (id) => ({CFBundleIdentifier:id, ApplicationType:'User',
  ProfileValidated:true, SignerIdentity:'private signer',
  Entitlements:{'com.apple.developer.team-identifier':team,
    'application-identifier':`${team}.${id}`}});
module.exports.services = {startInstallationProxyService: async () => ({
  lookupApplications: async () => ({
    [overte]: {...common(overte), OverteE2ETestBuildContractVersion:1,
      UIFileSharingEnabled:true},
    [wda]: {...common(wda), CFBundleExecutable:'WebDriverAgentRunner-Runner',
      OverteE2EWebDriverAgentVersion:'16.8.0',
      OverteE2EXCUITestDriverVersion:'12.8.0'}
  }), close: () => {}
})};
"""
            entry = package / "index.js"
            entry.write_text(module, encoding="utf-8")
            request = json.dumps({"udid": "00008101-1234567890ABCDEF"})
            result = subprocess.run(
                ["node", str(helper)], input=request, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS: installed iOS app contracts verified\n", result.stdout)
            self.assertNotIn("00008101", result.stdout + result.stderr)

            remapped_module = module.replace(
                "org.overte.interface.e2e", "com.sideloadly.slot.overte"
            ).replace(
                "org.overte.WebDriverAgentRunner.xctrunner", "com.sideloadly.slot.wda"
            )
            entry.write_text(remapped_module, encoding="utf-8")
            discovered = subprocess.run(
                ["node", str(helper)], input=json.dumps({
                    "udid": "00008101-1234567890ABCDEF",
                    "discoverRemappedBundleIds": True,
                }), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, check=False,
            )
            self.assertEqual(0, discovered.returncode, discovered.stderr)
            self.assertEqual({
                "overteBundleId": "com.sideloadly.slot.overte",
                "wdaBundleId": "com.sideloadly.slot.wda",
                "wdaUpdatedBundleId": "com.sideloadly.slot.wda",
                "wdaBundleIdSuffix": "",
            }, json.loads(discovered.stdout))
            self.assertNotIn("00008101", discovered.stdout + discovered.stderr)

            entry.write_text(remapped_module.replace(
                "OverteE2EWebDriverAgentVersion:'16.8.0'",
                "OverteE2EWebDriverAgentVersion:'99.0.0'",
            ), encoding="utf-8")
            rejected = subprocess.run(
                ["node", str(helper)], input=json.dumps({
                    "udid": "00008101-1234567890ABCDEF",
                    "discoverRemappedBundleIds": True,
                }), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
            )
            self.assertEqual(2, rejected.returncode)
            self.assertNotIn("00008101", rejected.stdout + rejected.stderr)


if __name__ == "__main__":
    unittest.main()
