#!/usr/bin/env python3
"""Device-free tests for the Phone release tag/version gate."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "android/ci/verify-phone-release.py"


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

    def run_gate(self, **overrides):
        values = {
            "tag": "android-phone-v0.1.0-alpha.5", "version_code": "100005",
            "published_code_floor": "100004", "source_revision": self.revision,
        }
        values.update(overrides)
        command = [str(GATE), "--repository", str(self.repository)]
        for key, value in values.items():
            command.extend(["--" + key.replace("_", "-"), value])
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_accepts_consistent_newest_tag(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["version_name"], "0.1.0-alpha.5")
        self.assertEqual(manifest["version_code"], 100005)

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
