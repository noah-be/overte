#!/usr/bin/env python3
"""Device-free tests for the signed macOS-to-Fedora iOS artifact handoff."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


DEVICE_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = DEVICE_ROOT / "ios" / "verify_fedora_artifacts.py"
SPEC = importlib.util.spec_from_file_location("verify_fedora_artifacts", VERIFIER)
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)


class IosFedoraArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-ios-fedora-artifacts-")
        self.root = Path(self.temporary.name)
        self.revision = "a" * 40
        self.team = "TEAM123456"
        self.overte_id = "org.overte.interface.e2e"
        self.wda_id = "org.overte.WebDriverAgentRunner.xctrunner"
        self.overte = self.make_ipa("Overte", self.overte_id, e2e=True)
        self.wda = self.make_ipa("WebDriverAgentRunner-Runner", self.wda_id, e2e=False)
        self.overte_manifest = self.write_manifest(self.overte, "overte-app", self.overte_id)
        self.wda_manifest = self.write_manifest(self.wda, "webdriveragent", self.wda_id)
        self.receipt = self.root / "private" / "receipt.json"

    def tearDown(self):
        self.temporary.cleanup()

    def make_ipa(self, name: str, bundle_id: str, *, e2e: bool) -> Path:
        destination = self.root / f"{name}.ipa"
        plist = {
            "CFBundleIdentifier": bundle_id,
            "CFBundlePackageType": "APPL",
            "CFBundleExecutable": name,
        }
        if e2e:
            plist.update({
                "OverteE2ETestBuildContractVersion": 1,
                "UIFileSharingEnabled": True,
            })
        prefix = f"Payload/{name}.app/"
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(prefix + "Info.plist", plistlib.dumps(plist))
            archive.writestr(prefix + name, b"mach-o fixture")
            archive.writestr(prefix + "_CodeSignature/CodeResources", b"signed fixture")
            archive.writestr(prefix + "embedded.mobileprovision", b"profile fixture")
        return destination

    def write_manifest(self, artifact: Path, kind: str, bundle_id: str) -> Path:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        value = {
            "schemaVersion": 1,
            "contract": "overte-ios-fedora-e2e-artifact-v1",
            "kind": kind,
            "sourceRevision": self.revision,
            "artifact": {
                "name": artifact.name,
                "sha256": digest,
                "size": artifact.stat().st_size,
            },
            "bundle": {"id": bundle_id},
            "signing": {
                "signed": True,
                "teamIdentifier": self.team,
                "applicationIdentifier": f"{self.team}.{bundle_id}",
                "profileExpiration": "2099-01-01T00:00:00Z",
            },
        }
        if kind == "overte-app":
            value["testBuildContractVersion"] = 1
        else:
            value["toolchain"] = {
                "xcuitestDriver": "12.8.0",
                "webdriverAgent": "16.8.0",
            }
        destination = self.root / f"{kind}.json"
        destination.write_text(json.dumps(value), encoding="utf-8")
        return destination

    def call(self) -> subprocess.CompletedProcess:
        arguments = argparse.Namespace(
            overte_manifest=self.overte_manifest,
            overte_ipa=self.overte,
            wda_manifest=self.wda_manifest,
            wda_ipa=self.wda,
            receipt=self.receipt,
            rcodesign=self.root / "pinned-rcodesign",
        )
        output = io.StringIO()
        status = 0
        with redirect_stdout(output), \
                mock.patch.object(VERIFY, "validate_rcodesign", return_value=arguments.rcodesign), \
                mock.patch.object(VERIFY, "verify_ipa_signature"):
            try:
                status = VERIFY.run(arguments)
            except (VERIFY.VerificationError, OSError, json.JSONDecodeError) as error:
                print(f"error: {error}", file=output)
                status = 2
        return subprocess.CompletedProcess([], status, stdout=output.getvalue())

    def test_verified_pair_writes_private_runtime_receipt(self):
        result = self.call()
        self.assertEqual(0, result.returncode, result.stdout)
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual("overte-ios-fedora-e2e-receipt-v1", receipt["contract"])
        self.assertEqual(str(self.overte.resolve()), receipt["overte"]["path"])
        self.assertEqual(str(self.wda.resolve()), receipt["wda"]["path"])
        self.assertEqual("5.15.3", receipt["toolchain"]["remoteXpc"])
        self.assertEqual(0o600, self.receipt.stat().st_mode & 0o777)

    def test_tampered_ipa_is_rejected(self):
        self.overte.write_bytes(self.overte.read_bytes() + b"tampered")
        result = self.call()
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("manifest size", result.stdout)
        self.assertFalse(self.receipt.exists())

    def test_missing_signature_resource_is_rejected(self):
        self.overte = self.root / "unsigned.ipa"
        prefix = "Payload/Overte.app/"
        with zipfile.ZipFile(self.overte, "w") as archive:
            archive.writestr(prefix + "Info.plist", plistlib.dumps({
                "CFBundleIdentifier": self.overte_id,
                "CFBundlePackageType": "APPL",
                "OverteE2ETestBuildContractVersion": 1,
                "UIFileSharingEnabled": True,
            }))
            archive.writestr(prefix + "embedded.mobileprovision", b"profile")
        self.overte_manifest = self.write_manifest(
            self.overte, "overte-app", self.overte_id
        )
        result = self.call()
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("code-signature resource", result.stdout)

    def test_manifest_device_identifier_is_rejected(self):
        value = json.loads(self.wda_manifest.read_text(encoding="utf-8"))
        value["deviceIdentifiers"] = ["private"]
        self.wda_manifest.write_text(json.dumps(value), encoding="utf-8")
        result = self.call()
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("unexpected or missing fields", result.stdout)

    def test_wda_toolchain_drift_is_rejected(self):
        value = json.loads(self.wda_manifest.read_text(encoding="utf-8"))
        value["toolchain"]["webdriverAgent"] = "99.0.0"
        self.wda_manifest.write_text(json.dumps(value), encoding="utf-8")
        result = self.call()
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("pinned XCUITest/WDA pair", result.stdout)

    def test_unsigned_fixture_fails_cryptographic_macho_verification(self):
        manifest = VERIFY.load_manifest(self.overte_manifest, "overte-app")
        plist, app_root, _names = VERIFY.archive_plist(self.overte, "overte-app")
        with self.assertRaisesRegex(VERIFY.VerificationError, "cryptographic verification"):
            VERIFY.verify_ipa_signature(
                self.overte, "overte-app", manifest, plist, app_root, Path("/bin/false")
            )

    def test_profile_authorization_accepts_only_exact_or_scoped_wildcard(self):
        application = "TEAM123456.org.overte.WebDriverAgentRunner.xctrunner"
        self.assertTrue(VERIFY.profile_authorizes(application, application))
        self.assertTrue(VERIFY.profile_authorizes("TEAM123456.org.overte.*", application))
        self.assertFalse(VERIFY.profile_authorizes("TEAM123456.*", application))
        self.assertFalse(VERIFY.profile_authorizes("TEAM123456.org.*.xctrunner", application))


if __name__ == "__main__":
    unittest.main()
