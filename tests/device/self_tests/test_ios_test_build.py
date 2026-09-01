#!/usr/bin/env python3
"""Device-free checks for the isolated iOS test-build packaging contract."""

from __future__ import annotations

import plistlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios"
VALIDATOR = IOS / "validate_test_build.py"
FRAGMENT = IOS / "Info.plist.e2e.fragment.plist"


class IosTestBuildTest(unittest.TestCase):
    def run_validator(self, path: Path, bundle_id: str | None = None):
        command = [sys.executable, str(VALIDATOR), "--plist", str(path)]
        if bundle_id is not None:
            command += ["--bundle-id", bundle_id]
        return subprocess.run(command, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)

    def test_repository_fragment_declares_exact_test_only_contract(self):
        result = self.run_validator(FRAGMENT)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("contract version 1", result.stdout)

    def test_exported_plist_requires_marker_file_sharing_and_bundle_identity(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-plist-test-") as name:
            path = Path(name) / "Info.plist"
            valid = {
                "CFBundleIdentifier": "org.overte.interface.e2e",
                "OverteE2ETestBuildContractVersion": 1,
                "UIFileSharingEnabled": True,
            }
            with path.open("wb") as destination:
                plistlib.dump(valid, destination)
            result = self.run_validator(path, "org.overte.interface.e2e")
            self.assertEqual(0, result.returncode, result.stdout)

            for key in ("OverteE2ETestBuildContractVersion", "UIFileSharingEnabled"):
                with self.subTest(missing=key):
                    invalid = dict(valid)
                    invalid.pop(key)
                    with path.open("wb") as destination:
                        plistlib.dump(invalid, destination)
                    result = self.run_validator(path, "org.overte.interface.e2e")
                    self.assertEqual(2, result.returncode, result.stdout)

            with path.open("wb") as destination:
                plistlib.dump(valid, destination)
            result = self.run_validator(path, "org.overte.interface.release")
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertIn("dedicated E2E bundle ID", result.stdout)


if __name__ == "__main__":
    unittest.main()
