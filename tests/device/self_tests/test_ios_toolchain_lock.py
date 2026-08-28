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
        self.assertEqual(11, value["serviceRuntimeRevision"])
        self.assertEqual("3.7.0", value["appium"]["core"]["version"])
        self.assertEqual("12.8.0", value["appium"]["drivers"]["xcuitest"]["version"])
        self.assertEqual("5.15.3", value["appium"]["iosRuntime"]["remoteXpc"]["version"])
        self.assertEqual("16.8.0", value["appium"]["iosRuntime"]["webdriverAgent"]["version"])
        pymobiledevice3 = value["appium"]["iosRuntime"]["pymobiledevice3"]
        self.assertEqual("11.1.5", pymobiledevice3["version"])
        self.assertEqual("GPL-3.0-or-later", pymobiledevice3["license"])
        self.assertEqual("cp314", pymobiledevice3["pythonAbi"])
        self.assertEqual(99, pymobiledevice3["distributionCount"])
        npm_lock = json.loads((IOS_ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "3.1.21",
            npm_lock["packages"][
                "node_modules/appium-xcuitest-driver/node_modules/appium-ios-device"
            ]["version"],
        )
        self.assertEqual("1.2.1", value["appium"]["iosSecurity"]["age"]["version"])
        self.assertEqual("0.29.0", value["appium"]["iosSecurity"]["rcodesign"]["version"])
        resigner = value["appium"]["iosSecurity"]["resigner"]
        self.assertEqual("0.3.1", resigner["version"])
        self.assertEqual("Apache-2.0", resigner["license"])
        self.assertEqual(
            "https://github.com/appium/resigner/releases/download/v0.3.1/"
            "linux-amd64.tar.gz",
            resigner["artifact"]["url"],
        )
        self.assertEqual(
            "e8672bfcced781bee017f84d17a84f645668bb664fe709d7dda011c9f1d8d0cd",
            resigner["artifact"]["sha256"],
        )
        self.assertEqual(
            "57a837d4674a5bb4eea9ff0d006b84fd5273fdd0c9d3c05143a46135ae4b988e",
            resigner["executableSha256"],
        )
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

    def test_appium_resigner_pin_drift_is_rejected(self):
        original = json.loads(LOCK.DEFAULT_LOCK.read_text(encoding="utf-8"))
        mutations = {
            "version": lambda value: value["appium"]["iosSecurity"]["resigner"].update(
                version="0.3.0"
            ),
            "license": lambda value: value["appium"]["iosSecurity"]["resigner"].update(
                license="MIT"
            ),
            "URL": lambda value: value["appium"]["iosSecurity"]["resigner"][
                "artifact"
            ].update(url="https://github.com/appium/resigner/releases/download/v0.3.1/other.tar.gz"),
            "archive digest": lambda value: value["appium"]["iosSecurity"]["resigner"][
                "artifact"
            ].update(sha256="0" * 64),
            "executable digest": lambda value: value["appium"]["iosSecurity"][
                "resigner"
            ].update(executableSha256="0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(original)
                mutate(changed)
                with self.assertRaisesRegex(LOCK.LockError, "resigner"):
                    LOCK.validate_security_tools(changed)


if __name__ == "__main__":
    unittest.main()
