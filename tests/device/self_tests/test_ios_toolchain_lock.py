#!/usr/bin/env python3
"""Device-free checks for the exact Fedora iOS npm/tool security lock."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


IOS_ROOT = Path(__file__).resolve().parents[1] / "ios"
SCRIPT = IOS_ROOT / "validate_toolchain_lock.py"
SPEC = importlib.util.spec_from_file_location("validate_ios_toolchain", SCRIPT)
LOCK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LOCK)


class IosToolchainLockTest(unittest.TestCase):
    def test_checked_in_lock_and_full_npm_resolution_are_exact(self):
        value = LOCK.validate()
        self.assertEqual(7, value["serviceRuntimeRevision"])
        self.assertEqual("3.7.0", value["appium"]["core"]["version"])
        self.assertEqual("12.8.0", value["appium"]["drivers"]["xcuitest"]["version"])
        self.assertEqual("5.15.3", value["appium"]["iosRuntime"]["remoteXpc"]["version"])
        self.assertEqual("16.8.0", value["appium"]["iosRuntime"]["webdriverAgent"]["version"])
        npm_lock = json.loads((IOS_ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "3.1.21",
            npm_lock["packages"][
                "node_modules/appium-xcuitest-driver/node_modules/appium-ios-device"
            ]["version"],
        )
        self.assertEqual("1.2.1", value["appium"]["iosSecurity"]["age"]["version"])
        self.assertEqual("0.29.0", value["appium"]["iosSecurity"]["rcodesign"]["version"])
        self.assertEqual(
            "27A5228h",
            value["developerDiskImage"]["provenance"]["productBuildVersion"],
        )

    def test_direct_version_or_integrity_drift_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-toolchain-test-") as name:
            root = Path(name)
            lock = json.loads(LOCK.DEFAULT_LOCK.read_text(encoding="utf-8"))
            package = json.loads(LOCK.DEFAULT_PACKAGE.read_text(encoding="utf-8"))
            npm_lock = json.loads(LOCK.DEFAULT_NPM_LOCK.read_text(encoding="utf-8"))
            changed = copy.deepcopy(lock)
            changed["appium"]["iosRuntime"]["remoteXpc"]["version"] = "5.15.2"
            lock_path = root / "toolchain.lock.json"
            lock_path.write_text(json.dumps(changed), encoding="utf-8")
            package_path = root / "package.json"
            package_path.write_text(json.dumps(package), encoding="utf-8")
            npm_path = root / "package-lock.json"
            npm_path.write_text(json.dumps(npm_lock), encoding="utf-8")
            with self.assertRaisesRegex(LOCK.LockError, "pin drifted"):
                LOCK.validate(lock_path, package_path, npm_path)

            changed = copy.deepcopy(lock)
            changed["serviceRuntimeRevision"] = 4
            lock_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(LOCK.LockError, "header drifted"):
                LOCK.validate(lock_path, package_path, npm_path)

            changed = copy.deepcopy(lock)
            changed["developerDiskImage"]["files"]["Image.dmg"]["size"] = 1
            lock_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(LOCK.LockError, "pin is invalid"):
                LOCK.validate(lock_path, package_path, npm_path)

            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            npm_lock["packages"]["node_modules/appium"]["integrity"] = "sha512-" + "A" * 88
            npm_path.write_text(json.dumps(npm_lock), encoding="utf-8")
            with self.assertRaises(LOCK.LockError):
                LOCK.validate(lock_path, package_path, npm_path)

    def test_mutable_link_or_non_registry_resolution_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-npm-lock-test-") as name:
            root = Path(name)
            npm_lock = json.loads(LOCK.DEFAULT_NPM_LOCK.read_text(encoding="utf-8"))
            first = next(key for key in npm_lock["packages"] if key)
            npm_lock["packages"][first]["link"] = True
            npm_path = root / "package-lock.json"
            npm_path.write_text(json.dumps(npm_lock), encoding="utf-8")
            with self.assertRaisesRegex(LOCK.LockError, "mutable linked"):
                LOCK.validate(LOCK.DEFAULT_LOCK, LOCK.DEFAULT_PACKAGE, npm_path)


if __name__ == "__main__":
    unittest.main()
