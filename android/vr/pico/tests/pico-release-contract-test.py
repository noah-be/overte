#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
TOOL = ROOT / "android/vr/pico/ci/pico4-release.py"
REVISION = "a" * 40


class PicoReleaseContractTests(unittest.TestCase):
    def run_tool(self, *arguments):
        return subprocess.run([str(TOOL), *arguments], text=True, capture_output=True, check=False)

    def test_derives_unambiguous_android_versions(self):
        result = self.run_tool("--tag", "pico4-v2.3.4-rc.5", "--revision", REVISION)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["version_name"], "2.3.4-rc.5")
        self.assertEqual(value["version_code"], 20304005)

    def test_rejects_mutable_or_non_rc_refs(self):
        for tag in ("main", "pico4-preview-5", "pico4-v1.2.3", "pico4-v1.2.3-rc.0"):
            with self.subTest(tag=tag):
                self.assertEqual(self.run_tool("--tag", tag, "--revision", REVISION).returncode, 2)

    def test_rejects_ref_tag_mismatch(self):
        result = self.run_tool("--tag", "pico4-v1.2.3-rc.1", "--revision", REVISION,
                               "--github-ref", "refs/heads/android-vr-pico")
        self.assertEqual(result.returncode, 2)

    def test_bundle_is_deterministic_and_checks_apk_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            apk = {"apk": "overte-pico4.apk", "sha256": "b" * 64,
                   "version_name": "1.2.3-rc.4", "version_code": "10203004",
                   "source_revision": REVISION}
            (directory / "apk.json").write_text(json.dumps(apk), encoding="utf-8")
            (directory / "deps").write_text(f"{'c' * 64}  dependency.tgz\n", encoding="utf-8")
            args = ("--tag", "pico4-v1.2.3-rc.4", "--revision", REVISION,
                    "--apk-manifest", str(directory / "apk.json"),
                    "--dependency-checksums", str(directory / "deps"))
            for name in ("one", "two"):
                result = self.run_tool(*args, "--output-dir", str(directory / name))
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((directory / "one/SHA256SUMS").read_bytes(),
                             (directory / "two/SHA256SUMS").read_bytes())
            apk["version_code"] = "7"
            (directory / "apk.json").write_text(json.dumps(apk), encoding="utf-8")
            self.assertEqual(self.run_tool(*args, "--output-dir", str(directory / "bad")).returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
