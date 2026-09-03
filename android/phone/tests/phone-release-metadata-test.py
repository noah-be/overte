#!/usr/bin/env python3
"""Device-free tests for release manifest, SBOM and provenance creation."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "android/phone/ci/create-phone-release-metadata.py"
VALIDATOR = ROOT / "tools/release/validate-release-bundle.py"


class PhoneReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get(
            "OVERTE_RELEASE_TEST_TMPDIR",
            "/home/user/Documents/github/overte-53x-test-tmp/release",
        ))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.directory = Path(self.temporary.name)
        self.apk = self.directory / "phone-release.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("lib/arm64-v8a/libphone.so", b"ELF synthetic")
        self.revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
            stdout=subprocess.PIPE, check=True,
        ).stdout.strip()
        self.version = {
            "tag": "android-phone-v0.1.0-alpha.5", "version_name": "0.1.0-alpha.5",
            "version_code": 100005, "source_revision": self.revision,
        }
        self.apk_data = {
            "sha256": self.digest(self.apk), "signer_certificate_sha256": None,
            "source_revision": self.revision, "version_code": 100005,
            "version_name": "0.1.0-alpha.5", "signature_verified": False,
            "signing_state": "unsigned",
            "package_gate": "phone-16k",
        }
        self.version_path = self.write("version.json", self.version)
        self.apk_path = self.write("apk.json", self.apk_data)
        self.output = self.directory / "output"

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def command(self, apk_manifest=None, version_manifest=None, repository=ROOT):
        return [
            str(TOOL), "--repository", str(repository), "--apk", str(self.apk),
            "--apk-manifest", str(apk_manifest or self.apk_path),
            "--version-manifest", str(version_manifest or self.version_path),
            "--output-dir", str(self.output),
        ]

    def run_tool(self, environment=None):
        return subprocess.run([
            *self.command(),
        ], text=True, capture_output=True, check=False, env=environment)

    def seed_finals(self, content="stale"):
        self.output.mkdir(parents=True, exist_ok=True)
        for name in (
                "android-phone-sbom.cdx.json",
                "android-phone-provenance.intoto.json",
                "android-phone-release-manifest.json",
                "SHA256SUMS"):
            (self.output / name).write_text(content, encoding="utf-8")

    def complete_evidence(self):
        repository = self.directory / "source-repository"
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email",
                        "test@example.invalid"], check=True)
        (repository / "source.txt").write_text("source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "source"], check=True)
        revision = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True,
            stdout=subprocess.PIPE, check=True,
        ).stdout.strip()
        self.version["source_revision"] = revision
        self.apk_data["source_revision"] = revision
        self.version_path = self.write("version.json", self.version)
        self.apk_path = self.write("apk.json", self.apk_data)
        source_archive = self.directory / "source.tar"
        subprocess.run([
            "git", "-C", str(repository), "archive", "--format=tar",
            f"--output={source_archive}", revision,
        ], check=True)
        inventory = self.write("inventory.json", {
            "schema": "org.overte.release-license-inventory.v1", "complete": True,
            "components": [{
                "bom_ref": "pkg:conan/runtime@1.0", "name": "runtime", "version": "1.0",
                "purl": "pkg:conan/runtime@1.0", "source": "https://example.invalid/runtime",
                "sha256": "1" * 64, "spdx_license": "Apache-2.0",
                "categories": ["asset", "conan", "font", "gradle", "native", "openssl",
                               "qt", "script", "v8"],
                "notice_files": ["licenses/runtime.txt"],
            }],
        })
        notices = self.directory / "notices.zip"
        with zipfile.ZipFile(notices, "w") as archive:
            archive.writestr("NOTICE.txt", "Synthetic notice\n")
            archive.writestr("licenses/runtime.txt", "Apache License 2.0\n")
        environment = self.write("environment.json", {
            "schema": "org.overte.release-build-environment.v1",
            "builder_id": "https://github.com/noah-be/overte/actions/runs/1",
            "runner_image": "ubuntu-24.04@sha256:" + "2" * 64,
            "toolchain": {"java": "17", "ndk": "27.3"},
            "actions": [{"name": "actions/checkout", "sha": "3" * 40}],
            "resolved_dependencies": [{
                "bom_ref": "pkg:conan/runtime@1.0", "recipe_revision": "recipe-r1",
                "package_revision": "package-r1",
            }],
        })
        return repository, source_archive, inventory, notices, environment

    def test_creates_complete_locally_verifiable_metadata(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stderr)
        release = json.loads((self.output / "android-phone-release-manifest.json").read_text())
        sbom = json.loads((self.output / "android-phone-sbom.cdx.json").read_text())
        provenance = json.loads((self.output / "android-phone-provenance.intoto.json").read_text())
        self.assertFalse(release["published"])
        self.assertFalse(release["complete_release_bundle"])
        self.assertIn("only", release["inventory_scope"])
        self.assertEqual(release["distribution"], {
            "kind": "store-neutral", "signing_state": "unsigned",
        })
        self.assertRegex(release["source_archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["components"][0]["name"], "lib/arm64-v8a/libphone.so")
        self.assertEqual(provenance["subject"][0]["digest"]["sha256"], self.apk_data["sha256"])
        self.assertTrue((self.output / "SHA256SUMS").is_file())
        checksums = {
            name: digest for digest, name in
            (line.split("  ", 1) for line in
             (self.output / "SHA256SUMS").read_text(encoding="utf-8").splitlines())
        }
        for name in (
                "android-phone-sbom.cdx.json",
                "android-phone-provenance.intoto.json",
                "android-phone-release-manifest.json"):
            self.assertEqual(self.digest(self.output / name), checksums[name])
        self.assertEqual([], list(self.output.glob(".phone-release-metadata.????????")))

    def test_complete_mode_uses_common_bundle_contract(self):
        repository, source, inventory, notices, environment = self.complete_evidence()
        bundle = self.directory / "complete-bundle"
        result = subprocess.run([
            *self.command(repository=repository),
            "--complete-bundle-output-dir", str(bundle),
            "--dependency-inventory", str(inventory),
            "--notice-bundle", str(notices),
            "--source-archive", str(source),
            "--build-environment", str(environment),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        validate = subprocess.run([
            str(VALIDATOR), str(bundle), "--product", "android-phone",
            "--source-revision", self.version["source_revision"],
        ], text=True, capture_output=True, check=False)
        self.assertEqual(0, validate.returncode, validate.stderr)
        self.assertTrue(json.loads((bundle / "release-bundle.json").read_text())["complete"])

    def test_complete_mode_rejects_source_archive_mismatch_atomically(self):
        repository, source, inventory, notices, environment = self.complete_evidence()
        source.write_bytes(source.read_bytes() + b"tampered")
        bundle = self.directory / "complete-bundle"
        result = subprocess.run([
            *self.command(repository=repository),
            "--complete-bundle-output-dir", str(bundle),
            "--dependency-inventory", str(inventory), "--notice-bundle", str(notices),
            "--source-archive", str(source), "--build-environment", str(environment),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("does not match git archive", result.stderr)
        self.assertFalse((bundle / "release-bundle.json").exists())
        for name in (
                "android-phone-sbom.cdx.json", "android-phone-provenance.intoto.json",
                "android-phone-release-manifest.json", "SHA256SUMS"):
            self.assertFalse((self.output / name).exists())

    def test_complete_mode_rejects_partial_evidence_before_publication(self):
        inventory = self.write("inventory.json", {})
        result = subprocess.run([
            *self.command(), "--dependency-inventory", str(inventory),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("requires --complete-bundle-output-dir", result.stderr)
        self.assertFalse(self.output.exists())

    def test_complete_and_legacy_outputs_must_not_overlap(self):
        repository, source, inventory, notices, environment = self.complete_evidence()
        result = subprocess.run([
            *self.command(repository=repository),
            "--complete-bundle-output-dir", str(self.output / "bundle"),
            "--dependency-inventory", str(inventory), "--notice-bundle", str(notices),
            "--source-archive", str(source), "--build-environment", str(environment),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("must not overlap", result.stderr)
        self.assertFalse(self.output.exists())

    def test_invalid_revision_invalidates_stale_final_set(self):
        self.seed_finals()
        self.version["source_revision"] = "f" * 40
        self.apk_data["source_revision"] = "f" * 40
        self.version_path = self.write("version.json", self.version)
        self.apk_path = self.write("apk.json", self.apk_data)
        result = self.run_tool()
        self.assertEqual(2, result.returncode)
        for name in (
                "android-phone-sbom.cdx.json",
                "android-phone-provenance.intoto.json",
                "android-phone-release-manifest.json",
                "SHA256SUMS"):
            self.assertFalse((self.output / name).exists())
        self.assertEqual([], list(self.output.glob(".phone-release-metadata.????????")))

    def test_symlinked_final_refuses_all_publication(self):
        self.seed_finals("owned")
        victim = self.directory / "victim"
        victim.write_text("private", encoding="utf-8")
        sbom = self.output / "android-phone-sbom.cdx.json"
        sbom.unlink()
        try:
            sbom.symlink_to(victim)
        except OSError:
            self.skipTest("symlinks unavailable")
        result = self.run_tool()
        self.assertEqual(2, result.returncode)
        self.assertEqual("private", victim.read_text(encoding="utf-8"))
        self.assertTrue(sbom.is_symlink())
        self.assertEqual(
            "owned", (self.output / "SHA256SUMS").read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_owner_final_set(self):
        import fcntl

        self.seed_finals("owned")
        lock_path = self.output / ".phone-release-metadata.lock"
        environment = {
            **os.environ,
            "OVERTE_RELEASE_METADATA_LOCK_TIMEOUT_SECONDS": "0.01",
        }
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_tool(environment)
        self.assertEqual(2, result.returncode)
        for name in (
                "android-phone-sbom.cdx.json",
                "android-phone-provenance.intoto.json",
                "android-phone-release-manifest.json",
                "SHA256SUMS"):
            self.assertEqual("owned", (self.output / name).read_text(encoding="utf-8"))

    def test_rejects_apk_digest_mismatch(self):
        self.apk_data["sha256"] = "0" * 64
        self.apk_path = self.write("apk.json", self.apk_data)
        result = self.run_tool()
        self.assertEqual(result.returncode, 2)
        self.assertIn("digest", result.stderr)

    def test_rejects_version_disagreement(self):
        self.apk_data["version_code"] = 100006
        self.apk_path = self.write("apk.json", self.apk_data)
        result = self.run_tool()
        self.assertEqual(result.returncode, 2)
        self.assertIn("version_code", result.stderr)

    def test_rejects_contradictory_unsigned_signature_evidence(self):
        self.apk_data["signature_verified"] = True
        self.apk_data["signer_certificate_sha256"] = "a" * 64
        self.apk_path = self.write("apk.json", self.apk_data)
        result = self.run_tool()
        self.assertEqual(result.returncode, 2)
        self.assertIn("contradictory", result.stderr)

    def test_rejects_signed_input_for_store_neutral_candidate(self):
        self.apk_data["signing_state"] = "signed"
        self.apk_data["signature_verified"] = True
        self.apk_data["signer_certificate_sha256"] = "a" * 64
        self.apk_path = self.write("apk.json", self.apk_data)
        result = self.run_tool()
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be explicitly unsigned", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
