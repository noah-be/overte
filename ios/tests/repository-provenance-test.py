#!/usr/bin/env python3
"""Device-free identity checks at iOS kit production and reuse boundaries."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = load("ios/tests/personal-team-e2e-kit-contract-test.py", "kit_fixtures")
KIT = FIXTURES.load_tool("create-personal-team-e2e-kit.py", "kit_identity")
ATTEST = FIXTURES.load_tool("create-personal-team-signed-attestation.py", "attest_identity")
PREINSTALLED = load("tests/device/ios/create_preinstalled_attestation.py", "preinstall_identity")
CURRENT = ("noah-l-frank/overte", 1319052603)
REJECTED = (
    ("noah-be/overte", 1319052603),
    ("overte-org/overte", 1319052603),
    ("foreign/overte", 1319052603),
    ("noah-l-frank/overte", 42),
    ("noah-l-frank/overte", True),
)


class OperativeKitIdentity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-kit-identity-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ipa, self.manifest = FIXTURES.write_overte_fixture(self.root)
        self.wda = FIXTURES.write_wda_fixture(self.root)
        previous = KIT.WDA_UPSTREAM_SHA256
        self.addCleanup(setattr, KIT, "WDA_UPSTREAM_SHA256", previous)
        KIT.WDA_UPSTREAM_SHA256 = FIXTURES.digest(self.wda)

    def create_kit(self, identity, output):
        return KIT.create_kit(
            self.ipa, self.manifest, self.wda, output, "a" * 40,
            "2029-01-01T00:00:00Z", *identity,
            "refs/heads/apple-ios", ".github/workflows/ios-bootstrap.yml",
            ".github/workflows/ios-personal-team-e2e-kit.yml", 987654, 2,
        )

    def test_new_producer_rejects_stale_foreign_and_wrong_id(self):
        for number, identity in enumerate(REJECTED):
            with self.subTest(identity=identity):
                output = self.root / f"rejected-{number}"
                with self.assertRaisesRegex(ValueError, "source repository"):
                    self.create_kit(identity, output)
                self.assertFalse(output.exists())
        value = self.create_kit(CURRENT, self.root / "accepted")
        self.assertEqual(CURRENT, (value["provenance"]["repository"],
                                   value["provenance"]["repositoryId"]))

    def test_both_reuse_consumers_require_current_tuple_and_actual_payload_binding(self):
        value = {
            "schemaVersion": 1, "contract": KIT.REUSE_CONTRACT,
            "assemblyRevision": "b" * 40, "sourceRevision": "a" * 40,
            "provenance": {
                "repository": CURRENT[0], "repositoryId": CURRENT[1],
                "workflow": ".github/workflows/ios-bootstrap.yml",
                "ref": "refs/heads/apple-ios", "runId": 321, "runAttempt": 1,
                "runNumber": 42, "artifactId": 456, "artifactSize": 789,
                "artifactName": "42-overte-ios-integrated-e2e-unsigned-321",
                "artifactCreatedAt": "2026-10-14T00:00:00Z",
                "actionsArchiveSha256": "c" * 64,
            },
            "artifacts": {role: {"name": path.name, "size": path.stat().st_size,
                                  "sha256": FIXTURES.digest(path)}
                          for role, path in (("overte", self.ipa),
                                             ("integratedManifest", self.manifest))},
        }
        path = self.root / "reuse.json"

        def validate(identity):
            value["provenance"].update(repository=identity[0], repositoryId=identity[1])
            path.write_text(json.dumps(value))
            KIT.validate_overte_reuse(path, "b" * 40, self.ipa, self.manifest)

        validate(CURRENT)
        PREINSTALLED.validate_overte_reuse(value, "a" * 40)
        for identity in REJECTED:
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    validate(identity)
                with self.assertRaisesRegex(ValueError, "provenance"):
                    PREINSTALLED.validate_overte_reuse(value, "a" * 40)
        validate(CURRENT)
        self.ipa.write_bytes(b"tampered payload")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            validate(CURRENT)

    def test_human_attestation_creation_does_not_authorize_stale_kit_identity(self):
        directory = self.root / "kit"
        self.create_kit(CURRENT, directory)
        manifest = directory / KIT.MANIFEST_OUTPUT
        original = json.loads(manifest.read_text())
        signed_overte = self.root / ATTEST.OVERTE_SIGNED_NAME
        signed_wda = self.root / ATTEST.WDA_SIGNED_NAME
        for path in (signed_overte, signed_wda):
            path.write_bytes(b"synthetic signed-input fixture; no signing operation")
            path.chmod(0o600)
        for number, identity in enumerate(REJECTED):
            with self.subTest(identity=identity):
                value = json.loads(json.dumps(original))
                value["provenance"].update(repository=identity[0], repositoryId=identity[1])
                manifest.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "provenance"):
                    ATTEST.create_attestation(
                        manifest, signed_overte, signed_wda,
                        self.root / f"rejected-attestation-{number}.json",
                        "2029-01-02T00:00:00Z", True, True, True,
                    )
        manifest.write_text(json.dumps(original))
        value = ATTEST.create_attestation(
            manifest, signed_overte, signed_wda, self.root / "attestation.json",
            "2029-01-02T00:00:00Z", True, True, True,
        )
        self.assertEqual(FIXTURES.digest(manifest), value["unsignedKitManifestSha256"])
        self.assertEqual("human-verified", value["humanAttestation"]["derivationBinding"])


if __name__ == "__main__":
    unittest.main()
