#!/usr/bin/env python3
"""Device-free positive and negative Personal-Team handoff tests."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "verify_personal_team_artifacts.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("verify_personal_team_artifacts", SCRIPT)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
CREATOR_SCRIPT = DEVICE_ROOT / "ios" / "create_preinstalled_attestation.py"
CREATOR_SPEC = importlib.util.spec_from_file_location(
    "create_preinstalled_attestation", CREATOR_SCRIPT
)
assert CREATOR_SPEC and CREATOR_SPEC.loader
CREATOR = importlib.util.module_from_spec(CREATOR_SPEC)
CREATOR_SPEC.loader.exec_module(CREATOR)


class IosPersonalTeamArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-personal-team-verify-")
        self.root = Path(self.temporary.name)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.overte = self.root / VERIFY.OVERTE_NAME
        self.wda = self.root / VERIFY.WDA_NAME
        self.overte.write_bytes(b"signed overte fixture")
        self.wda.write_bytes(b"signed wda fixture")
        self.overte.chmod(0o600)
        self.wda.chmod(0o600)
        self.kit = self.root / "personal-team-e2e-kit.json"
        self.attestation = self.root / "personal-team-signed-handoff.json"
        self.receipt = self.root / "private/receipt.json"
        self.write_contracts()

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def metadata(path: Path) -> dict:
        return {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }

    def write_contracts(self) -> None:
        unsigned_overte = {
            "name": "Overte-PersonalTeam-E2E-unsigned.ipa", "sha256": "1" * 64,
            "size": 100,
        }
        unsigned_wda = {
            "name": "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa",
            "sha256": "2" * 64, "size": 200,
        }
        kit = {
            "schemaVersion": 1, "contract": VERIFY.KIT_CONTRACT,
            "sourceRevision": "a" * 40,
            "createdAt": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "provenance": {
                "repository": "noah-be/overte", "repositoryId": 42,
                "workflow": ".github/workflows/ios-bootstrap.yml",
                "reusableWorkflow": ".github/workflows/ios-personal-team-e2e-kit.yml",
                "ref": "refs/heads/apple-ios", "runId": 123, "runAttempt": 1,
            },
            "xcuitestDriverVersion": "12.8.0", "webDriverAgentVersion": "16.8.0",
            "webDriverAgentCredentialFreeSigning": VERIFY.WDA_CREDENTIAL_FREE_SIGNING,
            "desiredBundleIdentifiers": VERIFY.BUNDLES,
            "humanSigningBoundary": {
                "method": "manual-sideloadly-personal-team",
                "derivationBinding": "human-verified",
                "signedBytesDerivableFromUnsignedKit": False,
                "maximumProfileLifetimeDays": 7,
            },
            "upstream": {
                "webDriverAgentUrl": "https://github.com/appium/WebDriverAgent/"
                "releases/download/v16.8.0/WebDriverAgentRunner-Runner.zip",
                "webDriverAgentSha256":
                "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623",
            },
            "artifacts": {"overte": unsigned_overte, "webDriverAgent": unsigned_wda},
            "overteArtifactReuse": None,
        }
        self.kit.write_text(json.dumps(kit), encoding="utf-8")
        self.kit.chmod(0o600)
        attestation = {
            "schemaVersion": 1, "contract": VERIFY.ATTESTATION_CONTRACT,
            "createdAt": self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notAfter": (self.now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sourceRevision": "a" * 40,
            "unsignedKitManifestSha256": hashlib.sha256(self.kit.read_bytes()).hexdigest(),
            "xcuitestDriverVersion": "12.8.0", "webDriverAgentVersion": "16.8.0",
            "expectedBundleIdentifiers": VERIFY.BUNDLES,
            "humanAttestation": {
                "derivationBinding": "human-verified",
                "signedFromReviewedUnsignedKit": True,
                "acceptedUnverifiableResigningBoundary": True,
                "samePersonalTeamExpected": True,
            },
            "artifacts": {
                "overte": self.metadata(self.overte),
                "webDriverAgent": self.metadata(self.wda),
            },
        }
        self.attestation.write_text(json.dumps(attestation), encoding="utf-8")
        self.attestation.chmod(0o600)

    def arguments(self) -> argparse.Namespace:
        return argparse.Namespace(
            unsigned_kit=self.kit.resolve(), attestation=self.attestation.resolve(),
            overte_ipa=self.overte.resolve(), wda_ipa=self.wda.resolve(),
            receipt=self.receipt.resolve(), rcodesign=(self.root / "rcodesign").resolve(),
        )

    def test_contract_and_human_boundary_are_strict(self):
        _kit, _attestation, deadline = VERIFY.validate_contracts(self.arguments())
        self.assertGreaterEqual(deadline, self.now + timedelta(hours=24))
        value = json.loads(self.kit.read_text(encoding="utf-8"))
        value["humanSigningBoundary"]["signedBytesDerivableFromUnsignedKit"] = True
        self.kit.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(VERIFY.VERIFY.VerificationError, "human signing boundary"):
            VERIFY.validate_contracts(self.arguments())

    def test_fake_crypto_path_writes_adapter_compatible_private_receipt(self):
        signing = {
            "signed": True, "teamIdentifier": "TEAM123456",
            "applicationIdentifier": "unused", "profileExpiration": "2099-01-01T00:00:00Z",
        }
        nested = "Payload/WebDriverAgentRunner-Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        bundle_results = [
            (signing, "Payload/Overte.app/", set()),
            (signing, "Payload/WebDriverAgentRunner-Runner.app/", {
                nested + "Info.plist", nested + "embedded.mobileprovision",
                nested + "_CodeSignature/CodeResources",
            }),
            (signing, "Payload/WebDriverAgentRunner-Runner.app/", set()),
        ]
        with mock.patch.object(
                VERIFY.VERIFY, "validate_rcodesign", return_value=self.root / "rcodesign"), \
                mock.patch.object(VERIFY, "verify_bundle", side_effect=bundle_results), \
                mock.patch.object(VERIFY.VERIFY, "archive_plist", side_effect=[({
                    "OverteE2ETestBuildContractVersion": 1, "UIFileSharingEnabled": True,
                }, "Payload/Overte.app/", set()), ({
                    "OverteE2EWebDriverAgentVersion": "16.8.0",
                    "OverteE2EXCUITestDriverVersion": "12.8.0",
                }, "Payload/WebDriverAgentRunner-Runner.app/", set())]), \
                mock.patch.object(
                    VERIFY.VERIFY, "extract_prebuilt_wda",
                    return_value=(self.root / "WebDriverAgentRunner-Runner.app", "4" * 64)):
            self.assertEqual(0, VERIFY.run(self.arguments()))
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(VERIFY.RECEIPT_CONTRACT, receipt["contract"])
        self.assertEqual({"path", "sha256", "bundleId"}, set(receipt["overte"]))
        self.assertEqual({
            "ipaPath", "ipaSha256", "prebuiltPath", "prebuiltTreeSha256", "bundleId",
        }, set(receipt["wda"]))
        self.assertEqual("human-verified", receipt["provenance"]["derivationBinding"])
        self.assertEqual(0o600, self.receipt.stat().st_mode & 0o777)

    def test_different_personal_teams_fail_closed(self):
        signing_a = {"teamIdentifier": "TEAM123456"}
        signing_b = {"teamIdentifier": "OTHER12345"}
        nested = "Payload/WebDriverAgentRunner-Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        with mock.patch.object(
                VERIFY.VERIFY, "validate_rcodesign", return_value=self.root / "rcodesign"), \
                mock.patch.object(VERIFY, "verify_bundle", side_effect=[
                    (signing_a, "Payload/Overte.app/", set()),
                    (signing_b, "Payload/WebDriverAgentRunner-Runner.app/", {
                        nested + "Info.plist", nested + "embedded.mobileprovision",
                        nested + "_CodeSignature/CodeResources",
                    }),
                    (signing_b, "Payload/WebDriverAgentRunner-Runner.app/", set()),
                ]), mock.patch.object(VERIFY.VERIFY, "archive_plist", side_effect=[({
                    "OverteE2ETestBuildContractVersion": 1, "UIFileSharingEnabled": True,
                }, "Payload/Overte.app/", set()), ({
                    "OverteE2EWebDriverAgentVersion": "16.8.0",
                    "OverteE2EXCUITestDriverVersion": "12.8.0",
                }, "Payload/WebDriverAgentRunner-Runner.app/", set())]):
            with self.assertRaisesRegex(VERIFY.VERIFY.VerificationError, "same Personal Team"):
                VERIFY.run(self.arguments())

    def test_preinstalled_attestation_creator_is_short_private_and_kit_bound(self):
        output = self.root / "private-observation/preinstalled.json"
        arguments = argparse.Namespace(
            unsigned_kit=self.kit.resolve(), output=output.resolve(),
            device_observed=True, installed_with_sideloadly=True,
            fixed_bundle_identifiers_confirmed=True,
            accept_sideloadly_bundle_id_remapping=False,
            accept_no_cryptographic_byte_binding=True,
        )
        value = CREATOR.create(arguments)
        created = datetime.strptime(value["createdAt"], "%Y-%m-%dT%H:%M:%SZ")
        expiry = datetime.strptime(value["notAfter"], "%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(timedelta(hours=1), expiry - created)
        self.assertEqual(hashlib.sha256(self.kit.read_bytes()).hexdigest(),
                         value["unsignedKitManifestSha256"])
        self.assertEqual("overte-ios-personal-team-e2e-kit-v2",
                         value["unsignedKitContract"])
        self.assertEqual("overte-ios-personal-team-preinstalled-attestation-v2",
                         value["contract"])
        self.assertIsNone(value["signingObservation"])
        self.assertEqual("fixed", value["bundleIdentifierMode"])
        self.assertEqual(0o600, output.stat().st_mode & 0o777)

        arguments.output = (self.root / "private-observation/remapped.json").resolve()
        arguments.fixed_bundle_identifiers_confirmed = False
        arguments.accept_sideloadly_bundle_id_remapping = True
        remapped = CREATOR.create(arguments)
        self.assertEqual("sideloadly-remapped", remapped["bundleIdentifierMode"])
        self.assertFalse(
            remapped["humanAttestation"]["fixedBundleIdentifiersConfirmed"])
        self.assertTrue(remapped["humanAttestation"][
            "acceptedSideloadlyBundleIdentifierRemapping"])

        arguments.output = (self.root / "missing-flags.json").resolve()
        arguments.device_observed = False
        with self.assertRaisesRegex(ValueError, "all explicit"):
            CREATOR.create(arguments)


if __name__ == "__main__":
    unittest.main()
