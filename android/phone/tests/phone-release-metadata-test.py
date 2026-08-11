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


class PhoneReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "android/build")
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

    def command(self, apk_manifest=None, version_manifest=None):
        return [
            str(TOOL), "--repository", str(ROOT), "--apk", str(self.apk),
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

    def test_creates_complete_locally_verifiable_metadata(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stderr)
        release = json.loads((self.output / "android-phone-release-manifest.json").read_text())
        sbom = json.loads((self.output / "android-phone-sbom.cdx.json").read_text())
        provenance = json.loads((self.output / "android-phone-provenance.intoto.json").read_text())
        self.assertFalse(release["published"])
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
    (ROOT / "android/build").mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
