#!/usr/bin/env python3
"""Host tests for signed Phone APK build provenance."""

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "android/ci/verify-phone-apk.py"


class PhoneApkProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.apk = self.directory / "phone.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic")
        self.gate = self.tool("gate", "test \"${MOCK_GATE:-1}\" = 1\n")
        self.analyzer = self.tool("apkanalyzer", """
case "$2" in
  application-id) printf '%s\n' "${MOCK_PACKAGE:-org.overte.phone}" ;;
  version-code) printf '7\n' ;;
  version-name) printf '0.4.0\n' ;;
  min-sdk) printf '26\n' ;;
  target-sdk) printf '36\n' ;;
  debuggable) printf 'true\n' ;;
  *) exit 2 ;;
esac
""")
        self.signer = self.tool("apksigner", """
test "${MOCK_SIGNED:-1}" = 1
printf 'Number of signers: %s\n' "${MOCK_SIGNERS:-1}"
printf 'Signer #1 certificate SHA-256 digest: %064d\n' 0
""")

    def tearDown(self):
        self.temporary.cleanup()

    def tool(self, name, body):
        path = self.directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def run_verifier(self, env=None, *extra):
        variables = os.environ.copy()
        variables.update(env or {})
        return subprocess.run([
            str(VERIFIER), str(self.apk), "--package-gate", str(self.gate),
            "--apkanalyzer", str(self.analyzer), "--apksigner", str(self.signer),
            *extra,
        ], text=True, capture_output=True, env=variables, check=False)

    def test_emits_complete_verified_manifest(self):
        revision = "a" * 40
        result = self.run_verifier(None, "--expect-debuggable", "1", "--source-revision", revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["package"], "org.overte.phone")
        self.assertEqual(manifest["target_sdk"], 36)
        self.assertEqual(manifest["page_size_bytes"], 16384)
        self.assertEqual(manifest["source_revision"], revision)
        self.assertRegex(manifest["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["signer_certificate_sha256"], r"^[0-9a-f]{64}$")

    def test_rejects_failed_complete_package_gate(self):
        result = self.run_verifier({"MOCK_GATE": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_rejects_wrong_package_even_after_mock_gate(self):
        result = self.run_verifier({"MOCK_PACKAGE": "example.wrong"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected package", result.stderr)

    def test_rejects_failed_signature(self):
        result = self.run_verifier({"MOCK_SIGNED": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_rejects_multiple_signers(self):
        result = self.run_verifier({"MOCK_SIGNERS": "2"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one APK signer", result.stderr)

    def test_rejects_ambiguous_source_revision(self):
        result = self.run_verifier(None, "--source-revision", "main")
        self.assertEqual(result.returncode, 2)
        self.assertIn("40-character Git commit", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
