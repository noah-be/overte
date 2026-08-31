#!/usr/bin/env python3
"""Device-free positive and negative Personal-Team handoff tests."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest import mock
import sys
import zipfile


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
                nested + "Info.plist", nested + "_CodeSignature/CodeResources",
            }),
        ]
        with mock.patch.object(
                VERIFY.VERIFY, "validate_rcodesign", return_value=self.root / "rcodesign"), \
                mock.patch.object(VERIFY, "verify_bundle", side_effect=bundle_results), \
                mock.patch.object(VERIFY, "bundle_leaf_signer", return_value=b"leaf"), \
                mock.patch.object(VERIFY, "verify_nested_xctest") as nested_verifier, \
                mock.patch.object(VERIFY, "verify_nested_framework") as framework_verifier, \
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
        nested_verifier.assert_called_once_with(
            self.wda.resolve(), nested, bundle_results[1][2], VERIFY.BUNDLES["wdaXCTest"],
            signing["teamIdentifier"], b"leaf", self.root / "rcodesign",
        )
        framework_verifier.assert_called_once_with(
            self.wda.resolve(),
            nested + "Frameworks/WebDriverAgentLib.framework/",
            bundle_results[1][2], signing["teamIdentifier"], b"leaf",
            self.root / "rcodesign",
        )
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(VERIFY.RECEIPT_CONTRACT, receipt["contract"])
        self.assertEqual({"path", "sha256", "bundleId"}, set(receipt["overte"]))
        self.assertEqual({
            "ipaPath", "ipaSha256", "prebuiltPath", "prebuiltTreeSha256", "bundleId",
        }, set(receipt["wda"]))
        self.assertEqual("human-verified", receipt["provenance"]["derivationBinding"])
        self.assertEqual(0o600, self.receipt.stat().st_mode & 0o777)

    def test_overte_and_wda_runner_different_personal_teams_fail_closed(self):
        signing_a = {"teamIdentifier": "TEAM123456"}
        signing_b = {"teamIdentifier": "OTHER12345"}
        with mock.patch.object(
                VERIFY.VERIFY, "validate_rcodesign", return_value=self.root / "rcodesign"), \
                mock.patch.object(VERIFY, "verify_bundle", side_effect=[
                    (signing_a, "Payload/Overte.app/", set()),
                    (signing_b, "Payload/WebDriverAgentRunner-Runner.app/", set()),
                ]), mock.patch.object(VERIFY.VERIFY, "archive_plist", side_effect=[({
                    "OverteE2ETestBuildContractVersion": 1, "UIFileSharingEnabled": True,
                }, "Payload/Overte.app/", set()), ({
                    "OverteE2EWebDriverAgentVersion": "16.8.0",
                    "OverteE2EXCUITestDriverVersion": "12.8.0",
                }, "Payload/WebDriverAgentRunner-Runner.app/", set())]):
            with self.assertRaisesRegex(VERIFY.VERIFY.VerificationError, "same Personal Team"):
                VERIFY.run(self.arguments())

    @staticmethod
    def nested_signature_info(*, xml: object = mock.sentinel.missing,
                              der: object = mock.sentinel.missing,
                              team: str = "TEAM123456") -> list[dict]:
        signature = {
            "code_directory": {
                "identifier": VERIFY.BUNDLES["wdaXCTest"], "team_name": team,
            },
            "cms": {
                "certificates": [{
                    "apple_team_id": team,
                    "apple_certificate_profile": "apple-development",
                }],
                "signers": [{"signature_verifies": True}],
            },
        }
        if xml is not mock.sentinel.missing:
            signature["entitlements_plist"] = xml
        if der is not mock.sentinel.missing:
            signature["entitlements_der_plist"] = der
        return [{"entity": {"mach_o": {"signature": signature}}}]

    def test_nested_signature_accepts_no_entitlement_slots(self):
        VERIFY.validate_nested_signature_info(
            self.nested_signature_info(), "webdriveragent xctest", "TEAM123456",
            VERIFY.BUNDLES["wdaXCTest"],
        )

    def test_nested_signature_rejects_even_empty_xml_entitlement_slot(self):
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "entitlement slot"):
            VERIFY.validate_nested_signature_info(
                self.nested_signature_info(xml=["<?xml version='1.0'?>", "<plist/>"]),
                "webdriveragent xctest", "TEAM123456", VERIFY.BUNDLES["wdaXCTest"],
            )

    def test_nested_signature_rejects_der_entitlement_slot(self):
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "entitlement slot"):
            VERIFY.validate_nested_signature_info(
                self.nested_signature_info(der=[]), "webdriveragent xctest",
                "TEAM123456", VERIFY.BUNDLES["wdaXCTest"],
            )

    def test_nested_signature_rejects_wrong_cms_team(self):
        value = self.nested_signature_info()
        value[0]["entity"]["mach_o"]["signature"]["cms"]["certificates"][0][
            "apple_team_id"
        ] = "OTHER12345"
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "signer team differs"):
            VERIFY.validate_nested_signature_info(
                value, "webdriveragent xctest", "TEAM123456",
                VERIFY.BUNDLES["wdaXCTest"],
            )

    def test_nested_xctest_requires_code_resources(self):
        root = "Payload/Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "signed nested XCTest bundle"):
            VERIFY.verify_nested_xctest(
                self.wda, root, {root + "Info.plist"}, VERIFY.BUNDLES["wdaXCTest"],
                "TEAM123456", b"leaf", self.root / "rcodesign",
            )

    def test_nested_xctest_rejects_embedded_profile(self):
        root = "Payload/Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        names = {
            root + "Info.plist", root + "_CodeSignature/CodeResources",
            root + "embedded.mobileprovision",
        }
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "must not contain a provisioning profile"):
            VERIFY.verify_nested_xctest(
                self.wda, root, names, VERIFY.BUNDLES["wdaXCTest"],
                "TEAM123456", b"leaf", self.root / "rcodesign",
            )

    def test_nested_xctest_rejects_alternative_embedded_profile_name(self):
        root = "Payload/Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        names = {
            root + "Info.plist", root + "_CodeSignature/CodeResources",
            root + "embedded.provisionprofile",
        }
        with self.assertRaisesRegex(
                VERIFY.VERIFY.VerificationError, "must not contain a provisioning profile"):
            VERIFY.verify_nested_xctest(
                self.wda, root, names, VERIFY.BUNDLES["wdaXCTest"],
                "TEAM123456", b"leaf", self.root / "rcodesign",
            )

    def test_nested_framework_is_identity_entitlement_and_leaf_attested(self):
        ipa = self.root / "framework.ipa"
        root = ("Payload/Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
                "Frameworks/WebDriverAgentLib.framework/")
        plist = {
            "CFBundleIdentifier": VERIFY.WDA_FRAMEWORK_BUNDLE_ID,
            "CFBundlePackageType": "FMWK", "CFBundleExecutable": "Framework",
        }
        with zipfile.ZipFile(ipa, "w") as archive:
            archive.writestr(root + "Info.plist", plistlib.dumps(plist))
            archive.writestr(root + "Framework", b"signed executable")
            archive.writestr(root + "_CodeSignature/CodeResources", b"resources")
        with zipfile.ZipFile(ipa) as archive:
            names = set(archive.namelist())
        signature_info = self.nested_signature_info()
        signature_info[0]["entity"]["mach_o"]["signature"]["code_directory"][
            "identifier"
        ] = VERIFY.WDA_FRAMEWORK_BUNDLE_ID
        completed = mock.Mock(returncode=0)
        with mock.patch.object(VERIFY.subprocess, "run", return_value=completed), \
                mock.patch.object(
                    VERIFY, "load_signature_info", return_value=signature_info
                ) as signature_loader, mock.patch.object(
                    VERIFY, "verified_leaf_signer", return_value=b"runner"):
            VERIFY.verify_nested_framework(
                ipa, root, names, "TEAM123456", b"runner", self.root / "rcodesign"
            )
        signature_loader.assert_called_once()

        signature_info[0]["entity"]["mach_o"]["signature"][
            "entitlements_plist"
        ] = []
        with mock.patch.object(VERIFY.subprocess, "run", return_value=completed), \
                mock.patch.object(
                    VERIFY, "load_signature_info", return_value=signature_info
                ), mock.patch.object(
                    VERIFY, "verified_leaf_signer", return_value=b"runner"):
            with self.assertRaisesRegex(
                    VERIFY.VERIFY.VerificationError, "entitlement slot"):
                VERIFY.verify_nested_framework(
                    ipa, root, names, "TEAM123456", b"runner",
                    self.root / "rcodesign",
                )

    def test_nested_xctest_rejects_different_leaf_signer(self):
        ipa = self.root / "nested.ipa"
        root = "Payload/Runner.app/PlugIns/WebDriverAgentRunner.xctest/"
        plist = {
            "CFBundleIdentifier": VERIFY.BUNDLES["wdaXCTest"],
            "CFBundlePackageType": "BNDL", "CFBundleExecutable": "Runner",
        }
        with zipfile.ZipFile(ipa, "w") as archive:
            archive.writestr(root + "Info.plist", plistlib.dumps(plist))
            archive.writestr(root + "Runner", b"signed executable")
            archive.writestr(root + "_CodeSignature/CodeResources", b"resources")
        with zipfile.ZipFile(ipa) as archive:
            names = set(archive.namelist())
        completed = mock.Mock(returncode=0)
        with mock.patch.object(VERIFY.subprocess, "run", return_value=completed), \
                mock.patch.object(
                    VERIFY, "load_signature_info", return_value=self.nested_signature_info()
                ), mock.patch.object(VERIFY, "verified_leaf_signer", return_value=b"other"):
            with self.assertRaisesRegex(
                    VERIFY.VERIFY.VerificationError, "different leaf signers"):
                VERIFY.verify_nested_xctest(
                    ipa, root, names, VERIFY.BUNDLES["wdaXCTest"],
                    "TEAM123456", b"runner", self.root / "rcodesign",
                )

    def test_preinstalled_attestation_creator_is_short_private_and_kit_bound(self):
        output = self.root / "private-observation/preinstalled.json"
        arguments = argparse.Namespace(
            unsigned_kit=self.kit.resolve(), output=output.resolve(),
            integrated_client_manifest=None,
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
        self.assertEqual("overte-ios-personal-team-e2e-kit-v3",
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

    def test_preinstalled_attestation_accepts_integrated_feature_client_manifest(self):
        manifest = self.root / "0573-OverteIOSClient-Release-device-unsigned.json"
        manifest.write_text(json.dumps({
            "schemaVersion": 1, "product": "overte-ios-integrated-client",
            "buildNumber": 573,
            "artifact": "0573-OverteIOSClient-Release-device-unsigned.ipa",
            "manifest": "0573-OverteIOSClient-Release-device-unsigned.json",
            "sha256": "1" * 64, "sourceRevision": "2" * 40,
            "platform": "iphoneos", "architecture": "arm64",
            "configuration": "Release", "xcode": "Xcode test", "sdk": "test",
            "signed": False, "requiresSigning": True,
            "signing": {}, "debugSymbols": {}, "windowsVm": {},
            "testBuildContractVersion": 1,
        }), encoding="utf-8")
        manifest.chmod(0o444)
        output = self.root / "private-observation/integrated.json"
        arguments = argparse.Namespace(
            unsigned_kit=None, integrated_client_manifest=manifest.resolve(),
            output=output.resolve(), device_observed=True,
            installed_with_sideloadly=True,
            fixed_bundle_identifiers_confirmed=False,
            accept_sideloadly_bundle_id_remapping=True,
            accept_no_cryptographic_byte_binding=True,
        )
        value = CREATOR.create(arguments)
        self.assertEqual("2" * 40, value["sourceRevision"])
        self.assertEqual("overte-ios-integrated-client-manifest-v1",
                         value["unsignedKitContract"])
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),
                         value["unsignedKitManifestSha256"])


if __name__ == "__main__":
    unittest.main()
