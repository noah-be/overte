#!/usr/bin/env python3
"""Host tests for signed and unsigned Phone APK build provenance."""

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "android/phone/ci/verify-phone-apk.py"


class PhoneApkProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.apk = self.directory / "phone.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic")
        self.gate = self.tool("gate", """
if [ -n "${MOCK_GATE_MARKER:-}" ]; then printf started >"$MOCK_GATE_MARKER"; fi
test "${MOCK_GATE:-1}" = 1
if [ -n "${MOCK_EXPECT_TMPDIR:-}" ]; then
  test "$TMPDIR" = "$MOCK_EXPECT_TMPDIR"
fi
""")
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
if [ "${MOCK_SIGNED:-1}" = 0 ]; then
  printf 'DOES NOT VERIFY\n' >&2
  printf 'ERROR: Missing META-INF/MANIFEST.MF\n' >&2
  exit 1
fi
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
        self.assertEqual(manifest["signing_state"], "signed")

    def test_rejects_failed_complete_package_gate(self):
        result = self.run_verifier({"MOCK_GATE": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_failed_gate_invalidates_stale_output_and_cleans_staging(self):
        output = self.directory / "reports/apk-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")

        result = self.run_verifier(
            {"MOCK_GATE": "0"}, "--output", str(output))

        self.assertEqual(2, result.returncode)
        self.assertFalse(output.exists())
        self.assertEqual([], list(output.parent.glob(".apk-manifest.json.*.tmp")))

    def test_success_atomically_replaces_stale_output(self):
        output = self.directory / "reports/apk-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")

        result = self.run_verifier(None, "--output", str(output))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("org.overte.phone", json.loads(output.read_text())["package"])
        self.assertEqual([], list(output.parent.glob(".apk-manifest.json.*.tmp")))

    def test_symlinked_output_is_rejected_before_gate(self):
        output = self.directory / "reports/apk-manifest.json"
        output.parent.mkdir()
        victim = self.directory / "victim.json"
        victim.write_text("private", encoding="utf-8")
        output.symlink_to(victim)
        marker = self.directory / "gate-started"

        result = self.run_verifier(
            {"MOCK_GATE_MARKER": str(marker)}, "--output", str(output))

        self.assertEqual(2, result.returncode)
        self.assertEqual("private", victim.read_text(encoding="utf-8"))
        self.assertTrue(output.is_symlink())
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_stale_output_without_starting_gate(self):
        import fcntl

        output = self.directory / "reports/apk-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")
        marker = self.directory / "gate-started"
        lock_path = output.parent / ".apk-manifest.json.lock"
        with lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_verifier({
                "MOCK_GATE_MARKER": str(marker),
                "OVERTE_APK_MANIFEST_LOCK_TIMEOUT_SECONDS": "0.05",
            }, "--output", str(output))

        self.assertEqual(2, result.returncode)
        self.assertIn("timed out waiting for APK manifest lock", result.stderr)
        self.assertEqual("stale", output.read_text(encoding="utf-8"))
        self.assertFalse(marker.exists())

    def test_invalid_lock_timeout_preserves_stale_output(self):
        output = self.directory / "reports/apk-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")
        marker = self.directory / "gate-started"

        result = self.run_verifier({
            "MOCK_GATE_MARKER": str(marker),
            "OVERTE_APK_MANIFEST_LOCK_TIMEOUT_SECONDS": "never",
        }, "--output", str(output))

        self.assertEqual(2, result.returncode)
        self.assertEqual("stale", output.read_text(encoding="utf-8"))
        self.assertFalse(marker.exists())

    def test_rejects_wrong_package_even_after_mock_gate(self):
        result = self.run_verifier({"MOCK_PACKAGE": "example.wrong"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected package", result.stderr)

    def test_rejects_failed_signature(self):
        result = self.run_verifier({"MOCK_SIGNED": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_accepts_explicitly_unsigned_store_neutral_apk(self):
        result = self.run_verifier({"MOCK_SIGNED": "0"}, "--expect-unsigned")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["signing_state"], "unsigned")
        self.assertFalse(manifest["signature_verified"])
        self.assertIsNone(manifest["signer_certificate_sha256"])

    def test_rejects_signed_apk_when_unsigned_is_required(self):
        result = self.run_verifier(None, "--expect-unsigned")
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected to be unsigned", result.stderr)

    def test_rejects_ambiguous_unsigned_and_signer_expectations(self):
        result = self.run_verifier(
            {"MOCK_SIGNED": "0"}, "--expect-unsigned", "--expect-signer", "0" * 64,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("mutually exclusive", result.stderr)

    def test_rejects_multiple_signers(self):
        result = self.run_verifier({"MOCK_SIGNERS": "2"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one APK signer", result.stderr)

    def test_accepts_pinned_upload_signer(self):
        result = self.run_verifier(None, "--expect-signer", "00:" * 31 + "00")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_unapproved_upload_signer(self):
        result = self.run_verifier(None, "--expect-signer", "a" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertIn("approved upload key", result.stderr)

    def test_rejects_ambiguous_source_revision(self):
        result = self.run_verifier(None, "--source-revision", "main")
        self.assertEqual(result.returncode, 2)
        self.assertIn("40-character Git commit", result.stderr)

    def test_keeps_package_gate_off_system_tmpfs(self):
        temp_root = self.directory / "large-build-volume"
        result = self.run_verifier({
            "PHONE_APK_VERIFY_TMPDIR": str(temp_root),
            "MOCK_EXPECT_TMPDIR": str(temp_root),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(temp_root.is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
