#!/usr/bin/env python3
"""Device-free tests for release manifest, SBOM and provenance creation."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "android/ci/create-phone-release-metadata.py"


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
            "sha256": self.digest(self.apk), "signer_certificate_sha256": "a" * 64,
            "source_revision": self.revision, "version_code": 100005,
            "version_name": "0.1.0-alpha.5", "signature_verified": True,
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

    def run_tool(self):
        return subprocess.run([
            str(TOOL), "--repository", str(ROOT), "--apk", str(self.apk),
            "--apk-manifest", str(self.apk_path), "--version-manifest", str(self.version_path),
            "--output-dir", str(self.output),
        ], text=True, capture_output=True, check=False)

    def test_creates_complete_locally_verifiable_metadata(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stderr)
        release = json.loads((self.output / "android-phone-release-manifest.json").read_text())
        sbom = json.loads((self.output / "android-phone-sbom.cdx.json").read_text())
        provenance = json.loads((self.output / "android-phone-provenance.intoto.json").read_text())
        self.assertFalse(release["published"])
        self.assertRegex(release["source_archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["components"][0]["name"], "lib/arm64-v8a/libphone.so")
        self.assertEqual(provenance["subject"][0]["digest"]["sha256"], self.apk_data["sha256"])
        self.assertTrue((self.output / "SHA256SUMS").is_file())

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


if __name__ == "__main__":
    (ROOT / "android/build").mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
