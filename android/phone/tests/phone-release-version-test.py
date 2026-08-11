#!/usr/bin/env python3
"""Device-free tests for the Phone release tag/version gate."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
GATE = ROOT / "android/phone/ci/verify-phone-release.py"


class PhoneReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "android/build")
        self.repository = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.invalid"], check=True)
        (self.repository / "source").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repository), "add", "source"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "one"], check=True)
        self.old_revision = self.git("rev-parse", "HEAD")
        self.git("tag", "android-phone-v0.1.0-alpha.4")
        (self.repository / "source").write_text("two\n", encoding="utf-8")
        self.git("commit", "-qam", "two")
        self.revision = self.git("rev-parse", "HEAD")
        self.git("tag", "android-phone-v0.1.0-alpha.5")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repository), *args], text=True,
            stdout=subprocess.PIPE, check=True,
        ).stdout.strip()

    def run_gate(self, environment=None, **overrides):
        values = {
            "tag": "android-phone-v0.1.0-alpha.5", "version_code": "100005",
            "published_code_floor": "100004", "source_revision": self.revision,
        }
        values.update(overrides)
        command = [str(GATE), "--repository", str(self.repository)]
        for key, value in values.items():
            command.extend(["--" + key.replace("_", "-"), value])
        return subprocess.run(
            command, text=True, capture_output=True, check=False,
            env={**os.environ, **(environment or {})})

    def test_accepts_consistent_newest_tag(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["version_name"], "0.1.0-alpha.5")
        self.assertEqual(manifest["version_code"], 100005)

    def test_success_atomically_replaces_stale_output(self):
        output = self.repository / "reports/version-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")

        result = self.run_gate(output=str(output))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(100005, json.loads(output.read_text())["version_code"])
        self.assertEqual([], list(output.parent.glob(".version-manifest.json.*.tmp")))

    def test_validation_failure_invalidates_stale_output(self):
        output = self.repository / "reports/version-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")

        result = self.run_gate(output=str(output), version_code="100006")

        self.assertEqual(2, result.returncode)
        self.assertFalse(output.exists())
        self.assertEqual([], list(output.parent.glob(".version-manifest.json.*.tmp")))

    def test_symlinked_output_preserves_victim(self):
        output = self.repository / "reports/version-manifest.json"
        output.parent.mkdir()
        victim = self.repository / "victim.json"
        victim.write_text("private", encoding="utf-8")
        output.symlink_to(victim)

        result = self.run_gate(output=str(output))

        self.assertEqual(2, result.returncode)
        self.assertEqual("private", victim.read_text(encoding="utf-8"))
        self.assertTrue(output.is_symlink())

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_owner_output(self):
        import fcntl

        output = self.repository / "reports/version-manifest.json"
        output.parent.mkdir()
        output.write_text("owner", encoding="utf-8")
        lock_path = output.parent / ".version-manifest.json.lock"
        with lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_gate(
                {"OVERTE_RELEASE_VERSION_LOCK_TIMEOUT_SECONDS": "0.05"},
                output=str(output))

        self.assertEqual(2, result.returncode)
        self.assertIn("timed out waiting for release version lock", result.stderr)
        self.assertEqual("owner", output.read_text(encoding="utf-8"))

    def test_invalid_lock_timeout_preserves_stale_output(self):
        output = self.repository / "reports/version-manifest.json"
        output.parent.mkdir()
        output.write_text("stale", encoding="utf-8")

        result = self.run_gate(
            {"OVERTE_RELEASE_VERSION_LOCK_TIMEOUT_SECONDS": "never"},
            output=str(output))

        self.assertEqual(2, result.returncode)
        self.assertEqual("stale", output.read_text(encoding="utf-8"))

    def test_rejects_noncanonical_tag(self):
        result = self.run_gate(tag="android-phone-v0.01.0-alpha.5")
        self.assertEqual(result.returncode, 2)
        self.assertIn("canonical", result.stderr)

    def test_rejects_mismatched_code(self):
        result = self.run_gate(version_code="100006")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be 100005", result.stderr)

    def test_rejects_nonmonotonic_published_floor(self):
        result = self.run_gate(published_code_floor="100005")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not exceed", result.stderr)

    def test_rejects_tag_from_another_commit(self):
        result = self.run_gate(source_revision=self.old_revision)
        self.assertEqual(result.returncode, 2)
        self.assertIn("checked-out source revision", result.stderr)

    def test_rejects_candidate_when_newer_tag_exists(self):
        result = self.run_gate(
            tag="android-phone-v0.1.0-alpha.4", version_code="100004",
            published_code_floor="0", source_revision=self.old_revision,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    (ROOT / "android/build").mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
