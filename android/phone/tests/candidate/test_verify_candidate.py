"""Host-only synthetic byte fixtures, explicitly not APK/package evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import verify_candidate as candidate_module
from verify_candidate import ROOT, EVIDENCE_KEYS, IdentityError, verify_candidate
from artifact_identity import INPUT_KEYS, normalized_inputs
import test_android_build_evidence as shared_evidence_tests


class PhoneCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="phone-candidate-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifact = self.root / "synthetic-not-an-apk.bin"
        self.artifact.write_bytes(b"synthetic byte-binding fixture, not an APK")
        self.evidence = {key: self.root / (key + ".json") for key in EVIDENCE_KEYS}
        for key, path in self.evidence.items():
            path.write_text(json.dumps({"testOnly": key}))
        self.inputs = {key: hashlib.sha256(key.encode()).hexdigest() for key in INPUT_KEYS}
        self.inputs_path = self.root / "expected-inputs.json"
        self.inputs_path.write_text(json.dumps(self.inputs))
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        self.record = dict(contract="overte-sh009-identity-v1", sourceRevision="a"*40,
                           product="android-phone", versionCode=3, channel="fdroid-candidate",
                           artifactSha256=sha(self.artifact), inputs=self.inputs,
                           normalizedInputsSha256=normalized_inputs(self.inputs),
                           evidence={key: sha(path) for key, path in self.evidence.items()},
                           signature=dict(state="pending", receiptSha256=None),
                           upgrade=dict(state="pending", receiptSha256=None))
        self.record_path = self.root / "identity.json"
        self.write()

    def write(self): self.record_path.write_text(json.dumps(self.record))

    def check(self):
        return verify_candidate(self.record_path, self.artifact, self.evidence, "a"*40,
                                self.inputs_path, 3, 2, "fdroid-candidate")

    def command(self):
        result = ["bash", str(ROOT / "android/phone/build.sh"), "fdroid", "verify-candidate",
                  "--record", str(self.record_path), "--artifact", str(self.artifact),
                  "--expected-source-sha", "a"*40, "--expected-inputs", str(self.inputs_path),
                  "--expected-version-code", "3", "--minimum-version-code", "2",
                  "--channel", "fdroid-candidate"]
        for key, path in self.evidence.items(): result += ["--" + key, str(path)]
        return result

    def build_fixture(self):
        # Reuse original Shared synthetic receipt producer, never production
        # receipt creation or a second Android tier schema.
        fixture = shared_evidence_tests.AndroidEvidence().fixture(self.root / "test-only-build-evidence")
        path, self.record_path, self.artifact, self.inputs_path, _, expected_sha, _ = fixture["args"]
        self.record, self.inputs, self.evidence = fixture["record"], fixture["inputs"], fixture["files"]
        self.record.update(versionCode=3, channel="fdroid-candidate")
        self.write()
        fixture["evidence"]["identityRecordSha256"] = hashlib.sha256(self.record_path.read_bytes()).hexdigest()
        shared_evidence_tests.AndroidEvidence().update(fixture)
        self.tiers, self.build_evidence_path, self.expected_artifact = fixture, path, expected_sha
        return fixture

    def check_build(self):
        return verify_candidate(self.record_path, self.artifact, self.evidence, "a"*40,
                                self.inputs_path, 3, 2, "fdroid-candidate",
                                build_evidence=self.build_evidence_path,
                                expected_artifact_sha256=self.expected_artifact)

    def build_command(self):
        return self.command() + ["--build-evidence", str(self.build_evidence_path),
                                 "--expected-artifact-sha256", self.expected_artifact]

    def test_actual_public_build_wrapper_binds_without_building(self):
        self.assertEqual("ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING", self.check()["status"])
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PHONE_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING\n", result.stdout)

    def test_foreign_product_channel_version_or_verified_claim_rejected(self):
        original = copy.deepcopy(self.record)
        for key, value in (("product", "pico4"), ("channel", "source-proof"), ("versionCode", 4),
                           ("versionCode", True), ("versionCode", 2),
                           ("signature", dict(state="verified", receiptSha256="f"*64))):
            with self.subTest(key=key):
                self.record = copy.deepcopy(original); self.record[key] = value; self.write()
                with self.assertRaises(IdentityError): self.check()

    def test_expected_inputs_cannot_be_taken_from_foreign_output(self):
        self.record["inputs"] = dict(self.inputs, toolchain="f"*64)
        self.record["normalizedInputsSha256"] = normalized_inputs(self.record["inputs"])
        self.write()
        with self.assertRaises(IdentityError): self.check()

    def test_reused_evidence_and_hardlinks_are_not_independent_documents(self):
        original = self.evidence["cyclonedx"]
        self.evidence["cyclonedx"] = self.evidence["spdx"]
        self.record["evidence"]["cyclonedx"] = self.record["evidence"]["spdx"]
        self.write()
        with self.assertRaises(IdentityError): self.check()
        link = self.root / "hardlink.json"
        os.link(self.evidence["spdx"], link)
        self.evidence["cyclonedx"] = link
        with self.assertRaises(IdentityError): self.check()
        self.evidence["cyclonedx"] = original

    def test_missing_changed_and_symlinked_artifact_fail(self):
        self.artifact.write_bytes(b"foreign")
        with self.assertRaises(IdentityError): self.check()
        self.artifact.unlink()
        self.artifact.symlink_to(self.evidence["spdx"])
        with self.assertRaises(IdentityError): self.check()

    def test_cli_duplicate_and_private_argument_errors_are_closed(self):
        for extra in (["--channel", "source-proof"], ["--unexpected=private-canary"]):
            result = subprocess.run(self.command() + extra, capture_output=True, text=True, timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertEqual("PHONE_CANDIDATE_ARGUMENTS_REJECTED\n", result.stderr)
            self.assertEqual("", result.stdout)

    def test_public_build_evidence_join_retains_pending_producer_status(self):
        self.build_fixture()
        expected = "MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING"
        self.assertEqual(self.check_build()["status"], expected)
        result = subprocess.run(self.build_command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected + "\n")
        self.assertEqual(result.stderr, "")
        # Omitting both optional inputs is byte-only diagnostics, not tier proof.
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "PHONE_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING\n")

    def test_build_evidence_requires_independent_hash_and_actual_receipts(self):
        self.build_fixture()
        variants = [self.command() + ["--build-evidence", str(self.build_evidence_path)],
                    self.command() + ["--expected-artifact-sha256", self.expected_artifact],
                    self.command() + ["--build-evidence", str(self.root / "missing-secret.json"),
                                     "--expected-artifact-sha256", self.expected_artifact],
                    self.command() + ["--build-evidence", str(self.build_evidence_path),
                                     "--expected-artifact-sha256", "b" * 64]]
        for command in variants:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "PHONE_CANDIDATE_REJECTED\n")
        result = subprocess.run(self.build_command() + ["--build-evidence", "private-canary"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "PHONE_CANDIDATE_ARGUMENTS_REJECTED\n")

    def test_phone_join_preserves_all_mandatory_tiers_and_named_checks(self):
        fixture = self.build_fixture()
        for tier, receipt in copy.deepcopy(fixture["receipts"]).items():
            fixture = self.build_fixture()
            fixture["evidence"]["receipts"] = [item for item in fixture["evidence"]["receipts"]
                                                 if item["tier"] != tier]
            shared_evidence_tests.AndroidEvidence().update(fixture)
            with self.assertRaises(ValueError): self.check_build()
            for name in receipt["checks"]:
                fixture = self.build_fixture()
                del fixture["receipts"][tier]["checks"][name]
                shared_evidence_tests.AndroidEvidence().update(fixture)
                with self.assertRaises(ValueError): self.check_build()

    def test_phone_join_rejects_failed_skipped_foreign_and_networked_receipts(self):
        for kind in ("skip", "zero", "error", "network", "toolchain", "source", "product"):
            fixture = self.build_fixture()
            receipt = fixture["receipts"]["cold-full-client-build"]
            if kind == "skip": receipt["checks"]["empty-binary-cache"]["skipped"] = 1
            elif kind == "zero": receipt["checks"]["empty-binary-cache"]["executed"] = 0
            elif kind == "error": fixture["receipts"]["fdroid-source-scanner"]["status"] = "ERROR"
            elif kind == "network": receipt["provenance"]["network"] = "online"
            elif kind == "toolchain": receipt["provenance"]["toolchainSha256"] = "b" * 64
            elif kind == "source": receipt["sourceRevision"] = "b" * 40
            else: receipt["product"] = "pico4"
            shared_evidence_tests.AndroidEvidence().update(fixture)
            with self.assertRaises(ValueError): self.check_build()

    def test_coherent_tier_join_cannot_override_original_phone_identity_policy(self):
        for key, value in (("versionCode", 4), ("channel", "source-proof"),
                           ("signature", dict(state="verified", receiptSha256="b" * 64))):
            fixture = self.build_fixture()
            self.record[key] = value
            self.write()
            fixture["evidence"]["identityRecordSha256"] = hashlib.sha256(self.record_path.read_bytes()).hexdigest()
            shared_evidence_tests.AndroidEvidence().update(fixture)
            with self.assertRaises(IdentityError): self.check_build()

    def test_candidate_and_inventory_rechecked_after_shared_join(self):
        original = candidate_module.validate_build_evidence
        for changed in ("record", "inventory"):
            self.build_fixture()
            def during_join(*args):
                result = original(*args)
                if changed == "record":
                    self.record["versionCode"] = 4
                    self.write()
                else:
                    self.evidence["spdx"].write_text('{"testOnly":"changed"}')
                return result
            with patch.object(candidate_module, "validate_build_evidence", side_effect=during_join):
                with self.assertRaises(IdentityError): self.check_build()


if __name__ == "__main__": unittest.main()
