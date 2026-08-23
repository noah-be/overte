#!/usr/bin/env python3
"""Self-tests for the Apple branch topology policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECK = Path(__file__).with_name("apple-branch-topology-check.py")
SPEC = importlib.util.spec_from_file_location("apple_topology", CHECK)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def run(repo: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(repo), *arguments], check=True,
                   stdout=subprocess.DEVNULL)


class AppleBranchTopologyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="apple-topology-test-")
        self.repo = Path(self.temporary.name)
        run(self.repo, "init", "-q")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "tests/device").mkdir(parents=True)
        (self.repo / "tests/device/core").write_text("v1\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "apple main")
        self.apple_main = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()

    def tearDown(self):
        self.temporary.cleanup()

    def commit(self, path: str, content: str) -> str:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", path)
        return subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()

    def test_target_specific_adapter_change_is_allowed(self):
        head = self.commit("ios/device-tests/adapter.py", "adapter\n")
        self.assertEqual([], MODULE.validate(self.repo, self.apple_main, head))

    def test_shared_harness_change_is_rejected(self):
        head = self.commit("tests/device/core", "changed directly\n")
        self.assertTrue(any("tests/device differs" in error
                            for error in MODULE.validate(self.repo, self.apple_main, head)))

    def test_head_without_apple_main_ancestry_is_rejected(self):
        run(self.repo, "checkout", "--orphan", "direct-main")
        run(self.repo, "rm", "-qrf", ".")
        (self.repo / "direct").write_text("main\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "direct main")
        head = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.assertTrue(any("current apple-main history" in error
                            for error in MODULE.validate(self.repo, self.apple_main, head)))


if __name__ == "__main__":
    unittest.main()
