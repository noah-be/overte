#!/usr/bin/env python3
"""Device-free negative and positive tests for the shared release contract."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "tools/release/build-release-bundle.py"
VALIDATE = ROOT / "tools/release/validate-release-bundle.py"
REVISION = "a" * 40


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get(
            "OVERTE_RELEASE_TEST_TMPDIR",
            "/home/user/Documents/github/overte-53x-test-tmp/release",
        ))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.directory = Path(self.temporary.name)
        self.payload = self.directory / "candidate.apk"
        self.payload.write_bytes(b"synthetic APK")
        self.verified = self.write_json("verified.json", {
            "source_revision": REVISION,
            "sha256": self.digest(self.payload),
        })
        self.version = self.write_json("version.json", {
            "source_revision": REVISION,
            "version_name": "1.2.3-rc.4",
            "version_code": 10203004,
            "tag": "synthetic-v1.2.3-rc.4",
        })
        self.components = [
            {
                "bom_ref": "pkg:conan/openssl@3.0.0", "name": "openssl",
                "version": "3.0.0", "source": "https://openssl.org/",
                "sha256": "1" * 64, "spdx_license": "Apache-2.0",
                "purl": "pkg:conan/openssl@3.0.0",
                "categories": ["conan", "native", "openssl"],
                "notice_files": ["licenses/openssl.txt"],
            },
            {
                "bom_ref": "pkg:generic/qt@5.15.18", "name": "qt",
                "version": "5.15.18", "source": "https://qt.io/",
                "sha256": "2" * 64, "spdx_license": "LGPL-3.0-only",
                "categories": ["qt", "v8"],
                "notice_files": ["licenses/qt.txt"],
            },
            {
                "bom_ref": "pkg:maven/example@1.0", "name": "example",
                "version": "1.0", "source": "https://example.invalid/source",
                "sha256": "3" * 64, "spdx_license": "Apache-2.0",
                "purl": "pkg:maven/example@1.0",
                "categories": ["asset", "font", "gradle", "script"],
                "notice_files": ["licenses/example.txt"],
            },
        ]
        self.inventory = self.write_inventory(self.components)
        self.notices = self.directory / "notices.zip"
        with zipfile.ZipFile(self.notices, "w") as archive:
            archive.writestr("NOTICE.txt", "Synthetic distribution notices\n")
            archive.writestr("licenses/openssl.txt", "Apache License 2.0\n")
            archive.writestr("licenses/qt.txt", "GNU LGPL 3.0\n")
            archive.writestr("licenses/example.txt", "Apache License 2.0\n")
        source_file = self.directory / "source.txt"
        source_file.write_text("source\n", encoding="utf-8")
        self.source = self.directory / "source.tar"
        with tarfile.open(self.source, "w") as archive:
            archive.add(source_file, arcname="source.txt")
        self.environment = self.write_json("environment.json", {
            "schema": "org.overte.release-build-environment.v1",
            "builder_id": "https://github.com/noah-be/overte/actions/runs/1",
            "runner_image": "ubuntu-24.04@sha256:" + "4" * 64,
            "toolchain": {"cmake": "4.1.0", "java": "17", "ndk": "27.3"},
            "actions": [{"name": "actions/checkout", "sha": "5" * 40}],
            "resolved_dependencies": [{
                "bom_ref": "pkg:conan/openssl@3.0.0",
                "recipe_revision": "recipe-r1", "package_revision": "package-r1",
            }],
        })
        self.output = self.directory / "bundle"

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_json(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def write_inventory(self, components, complete=True):
        return self.write_json("inventory.json", {
            "schema": "org.overte.release-license-inventory.v1",
            "complete": complete, "components": components,
        })

    def build(self, inventory=None, product="android-test"):
        return subprocess.run([
            str(BUILD), "--product", product, "--source-revision", REVISION,
            "--payload", str(self.payload), "--verified-manifest", str(self.verified),
            "--version-manifest", str(self.version), "--dependency-inventory",
            str(inventory or self.inventory), "--notice-bundle", str(self.notices),
            "--source-archive", str(self.source), "--build-environment",
            str(self.environment), "--output-dir", str(self.output),
        ], text=True, capture_output=True, check=False)

    def validate(self):
        return subprocess.run([
            str(VALIDATE), str(self.output), "--product", "android-test",
            "--source-revision", REVISION,
        ], text=True, capture_output=True, check=False)

    def test_creates_complete_deterministic_bundle(self):
        first = self.build()
        self.assertEqual(0, first.returncode, first.stderr)
        first_files = {path.name: path.read_bytes() for path in self.output.iterdir()}
        shutil.rmtree(self.output)
        second = self.build()
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first_files, {path.name: path.read_bytes() for path in self.output.iterdir()})
        self.assertEqual(0, self.validate().returncode)
        provenance = json.loads((self.output / "android-test-provenance.intoto.json").read_text())
        self.assertEqual(
            {"candidate.apk", "android-test-sbom.cdx.json", "android-test-licenses.json",
             "android-test-license-notices.zip", "android-test-source.tar", "SHA256SUMS"},
            {subject["name"] for subject in provenance["subject"]},
        )

    def test_same_contract_builds_phone_and_pico_bundles(self):
        for product in ("android-phone", "pico4"):
            with self.subTest(product=product):
                output = self.output
                result = self.build(product=product)
                self.assertEqual(0, result.returncode, result.stderr)
                validate = subprocess.run([
                    str(VALIDATE), str(output), "--product", product,
                    "--source-revision", REVISION,
                ], text=True, capture_output=True, check=False)
                self.assertEqual(0, validate.returncode, validate.stderr)
                shutil.rmtree(output)

    def test_rejects_missing_license(self):
        components = json.loads(json.dumps(self.components))
        components[0]["spdx_license"] = "UNKNOWN"
        result = self.build(self.write_inventory(components))
        self.assertEqual(2, result.returncode)
        self.assertIn("unresolved license", result.stderr)

    def test_rejects_unresolved_compound_or_trailing_license_text(self):
        for expression in ("UNKNOWN AND MIT", "MIT arbitrary text"):
            with self.subTest(expression=expression):
                components = json.loads(json.dumps(self.components))
                components[0]["spdx_license"] = expression
                result = self.build(self.write_inventory(components))
                self.assertEqual(2, result.returncode)

    def test_rejects_missing_provenance_subject(self):
        self.assertEqual(0, self.build().returncode)
        path = self.output / "android-test-provenance.intoto.json"
        value = json.loads(path.read_text())
        value["subject"].pop()
        path.write_text(json.dumps(value), encoding="utf-8")
        contract = json.loads((self.output / "release-bundle.json").read_text())
        contract["artifacts"]["provenance"]["sha256"] = self.digest(path)
        (self.output / "release-bundle.json").write_text(json.dumps(contract), encoding="utf-8")
        result = self.validate()
        self.assertEqual(2, result.returncode)
        self.assertIn("subjects", result.stderr)

    def test_rejects_missing_or_unbound_provenance_predicate(self):
        self.assertEqual(0, self.build().returncode)
        path = self.output / "android-test-provenance.intoto.json"
        value = json.loads(path.read_text())
        value.pop("predicate")
        path.write_text(json.dumps(value), encoding="utf-8")
        contract = json.loads((self.output / "release-bundle.json").read_text())
        contract["artifacts"]["provenance"]["sha256"] = self.digest(path)
        (self.output / "release-bundle.json").write_text(json.dumps(contract), encoding="utf-8")
        result = self.validate()
        self.assertEqual(2, result.returncode)
        self.assertIn("predicate", result.stderr)

    def test_rejects_non_regular_notice_entry(self):
        with zipfile.ZipFile(self.notices, "w") as archive:
            archive.writestr("NOTICE.txt", "Synthetic distribution notices\n")
            for name in ("licenses/openssl.txt", "licenses/qt.txt"):
                archive.writestr(name, "license\n")
            fifo = zipfile.ZipInfo("licenses/example.txt")
            fifo.create_system = 3
            fifo.external_attr = (stat.S_IFIFO | 0o644) << 16
            archive.writestr(fifo, "not regular\n")
        result = self.build()
        self.assertEqual(2, result.returncode)
        self.assertIn("regular files", result.stderr)

    def test_rejects_digest_mismatch(self):
        self.assertEqual(0, self.build().returncode)
        (self.output / "candidate.apk").write_bytes(b"tampered")
        result = self.validate()
        self.assertEqual(2, result.returncode)
        self.assertIn("digest mismatch", result.stderr)

    def test_rejects_incomplete_bundle(self):
        self.assertEqual(0, self.build().returncode)
        (self.output / "android-test-license-notices.zip").unlink()
        result = self.validate()
        self.assertEqual(2, result.returncode)
        self.assertIn("artifact notice_bundle", result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlink(self):
        self.assertEqual(0, self.build().returncode)
        victim = self.directory / "victim"
        victim.write_text("private", encoding="utf-8")
        target = self.output / "candidate.apk"
        target.unlink()
        target.symlink_to(victim)
        result = self.validate()
        self.assertEqual(2, result.returncode)
        self.assertIn("symlink", result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlinked_input_and_output_directory(self):
        real_payload = self.payload
        linked_payload = self.directory / "linked.apk"
        linked_payload.symlink_to(real_payload)
        original = self.payload
        self.payload = linked_payload
        try:
            result = self.build()
        finally:
            self.payload = original
        self.assertEqual(2, result.returncode)
        real_output = self.directory / "real-output"
        real_output.mkdir()
        self.output.symlink_to(real_output, target_is_directory=True)
        result = self.build()
        self.assertEqual(2, result.returncode)

    def test_rejects_incomplete_inventory(self):
        result = self.build(self.write_inventory(self.components, complete=False))
        self.assertEqual(2, result.returncode)
        self.assertIn("complete=true", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
