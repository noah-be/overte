#!/usr/bin/env python3
"""Hermetic tests for resumable macOS Ninja build-tree checkpoints."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/ci/build-tree-checkpoint.py"
BASELINE_NS = 946_684_800 * 1_000_000_000


class BuildTreeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.build = self.repository / "build"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Checkpoint Test")
        self.git("config", "user.email", "checkpoint@example.invalid")
        (self.repository / "unchanged.cpp").write_text("unchanged\n", encoding="utf-8")
        (self.repository / "changed.cpp").write_text("one\n", encoding="utf-8")
        self.git("add", "unchanged.cpp", "changed.cpp")
        self.git("commit", "-qm", "checkpoint")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def tool(self, operation, *, check=True):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                operation,
                "--repository",
                str(self.repository),
                "--build-dir",
                str(self.build),
            ],
            check=check,
            capture_output=True,
            text=True,
        )

    def test_restore_ages_unchanged_sources_and_marks_commit_changes_new(self):
        recorded = self.tool("record")
        checkpoint = self.git("rev-parse", "HEAD")
        metadata_path = self.build / ".overte-ninja-checkpoint.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["commit"], checkpoint)
        self.assertEqual(metadata["baseline_ns"], BASELINE_NS)
        self.assertEqual(metadata_path.stat().st_mode & 0o777, 0o600)
        self.assertIn(checkpoint, recorded.stdout)

        (self.repository / "changed.cpp").write_text("two\n", encoding="utf-8")
        (self.repository / "new.cpp").write_text("new\n", encoding="utf-8")
        self.git("add", "changed.cpp", "new.cpp")
        self.git("commit", "-qm", "source changes")

        # Model a fresh checkout whose source mtimes are newer than a cached
        # object.  Restore must make only actual changes remain newer.
        checkout_ns = time.time_ns() - 1_000_000_000
        object_ns = checkout_ns - 10_000_000_000
        self.build.mkdir(exist_ok=True)
        cached_object = self.build / "cached.o"
        cached_object.write_bytes(b"object")
        os.utime(cached_object, ns=(object_ns, object_ns))
        for name in ("unchanged.cpp", "changed.cpp", "new.cpp"):
            os.utime(self.repository / name, ns=(checkout_ns, checkout_ns))

        restored = self.tool("restore")
        self.assertEqual((self.repository / "unchanged.cpp").stat().st_mtime_ns, BASELINE_NS)
        self.assertLess((self.repository / "unchanged.cpp").stat().st_mtime_ns, object_ns)
        self.assertGreater((self.repository / "changed.cpp").stat().st_mtime_ns, object_ns)
        self.assertGreater((self.repository / "new.cpp").stat().st_mtime_ns, object_ns)
        self.assertIn("normalized=1 changed=2", restored.stdout)

    def test_uncommitted_edit_is_never_hidden_behind_cached_output(self):
        self.tool("record")
        cached_object = self.build / "cached.o"
        cached_object.write_bytes(b"object")
        object_ns = time.time_ns() - 5_000_000_000
        os.utime(cached_object, ns=(object_ns, object_ns))
        (self.repository / "changed.cpp").write_text("working tree edit\n", encoding="utf-8")

        self.tool("restore")

        self.assertEqual((self.repository / "unchanged.cpp").stat().st_mtime_ns, BASELINE_NS)
        self.assertGreater((self.repository / "changed.cpp").stat().st_mtime_ns, object_ns)

    def test_legacy_cache_without_metadata_is_safe_noop(self):
        self.build.mkdir()
        before = (self.repository / "unchanged.cpp").stat().st_mtime_ns
        result = self.tool("restore")
        self.assertEqual((self.repository / "unchanged.cpp").stat().st_mtime_ns, before)
        self.assertIn("legacy cache", result.stdout)

    def test_malformed_or_unknown_metadata_fails_closed(self):
        self.build.mkdir()
        metadata = self.build / ".overte-ninja-checkpoint.json"
        metadata.write_text('{"schema":1,"commit":"--help","baseline_ns":946684800000000000}\n')
        malformed = self.tool("restore", check=False)
        self.assertEqual(malformed.returncode, 2)
        self.assertIn("invalid commit id", malformed.stderr)

        metadata.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "commit": "0" * 40,
                    "baseline_ns": BASELINE_NS,
                }
            )
        )
        unknown = self.tool("restore", check=False)
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("git cat-file", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
