"""Exercise source identity against real Git index/worktree transitions."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scope import Scope


class SourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        (self.root / "ios").mkdir()
        self.source = self.root / "ios/source.cpp"
        self.source.write_text("int fixture;\n")
        self.git("add", "ios/source.cpp")
        self.findings = []
        self.ctx = SimpleNamespace(inventories={}, add=lambda *args, **kwargs: self.findings.append((args, kwargs)))
        for target, value in (("scope.ROOT", self.root), ("scope.git", self.git)):
            item = patch(target, value)
            item.start()
            self.addCleanup(item.stop)
        self.scope = Scope(self.ctx)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL).decode()

    def assert_changed(self):
        self.scope.verify_unchanged(self.ctx)
        self.assertTrue(self.findings)
        self.assertTrue(all(f[0][:2] == ("source-changed", "FAIL") for f in self.findings))

    def test_new_untracked_source_is_detected(self):
        (self.root / "ios/new.cpp").write_text("int additional;\n")
        self.assert_changed()

    def test_new_staged_source_is_detected(self):
        (self.root / "ios/new.cpp").write_text("int additional;\n")
        self.git("add", "ios/new.cpp")
        self.assert_changed()

    def test_symlink_to_identical_bytes_is_not_same_source(self):
        target = self.root / "same-bytes"
        target.write_bytes(self.source.read_bytes())
        self.source.unlink()
        self.source.symlink_to(target)
        self.assert_changed()

    def test_executable_mode_change_is_detected(self):
        self.source.chmod(0o755)
        self.assert_changed()

    def test_deleted_tracked_file_is_detected(self):
        self.source.unlink()
        self.assert_changed()

    def test_unrelated_platform_path_does_not_expand_scope(self):
        (self.root / "android").mkdir()
        (self.root / "android/local.txt").write_text("unrelated platform\n")
        self.scope.verify_unchanged(self.ctx)
        self.assertEqual(self.findings, [])


if __name__ == "__main__":
    unittest.main()
