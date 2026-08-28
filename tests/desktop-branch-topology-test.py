#!/usr/bin/env python3
"""Self-tests for main-owned and desktop-target-owned E2E paths."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECK = Path(__file__).with_name("desktop-branch-topology-check.py")
SPEC = importlib.util.spec_from_file_location("desktop_topology", CHECK)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

POLICY = {
    "schemaVersion": 1,
    "parentOwnedPrefixes": ["tests/device/"],
    "parentOwnedFiles": [
        ".github/workflows/desktop-branch-topology.yml",
        "docs/BRANCH_WORKFLOW.md",
        "tests/desktop-branch-path-ownership.json",
        "tests/desktop-branch-topology-check.py",
        "tests/desktop-branch-topology-test.py",
    ],
    "targets": {
        "linux-main": {
            "ownedPrefixes": ["tests/device/adapters/linux/"],
            "ownedFiles": [],
        },
        "windows-main": {
            "ownedPrefixes": ["tests/device/adapters/windows/"],
            "ownedFiles": [],
        },
    },
}


def run(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def revision(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


class DesktopBranchTopologyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-topology-test-")
        self.repo = Path(self.temporary.name)
        run(self.repo, "init", "-q")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "user.email", "test@example.invalid")
        self.write("tests/device/core", "v1\n")
        self.write("tests/desktop-branch-path-ownership.json", json.dumps(POLICY))
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "main")
        self.main_revision = revision(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path: str, content: str) -> None:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def commit(self, path: str, content: str) -> str:
        self.write(path, content)
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", path)
        return revision(self.repo)

    def validate(self, head: str, target: str = "linux-main") -> list[str]:
        return MODULE.validate(self.repo, self.main_revision, head, target)

    def test_linux_adapter_change_is_owned_only_by_linux(self):
        head = self.commit("tests/device/adapters/linux/adapter.py", "linux\n")
        self.assertEqual([], self.validate(head))
        self.assertTrue(any("main-owned path" in error
                            for error in self.validate(head, "windows-main")))

    def test_windows_adapter_change_is_owned_only_by_windows(self):
        head = self.commit("tests/device/adapters/windows/adapter.py", "windows\n")
        self.assertEqual([], self.validate(head, "windows-main"))
        self.assertTrue(any("main-owned path" in error for error in self.validate(head)))

    def test_shared_harness_change_is_rejected(self):
        head = self.commit("tests/device/core", "changed\n")
        self.assertTrue(any("main-owned path" in error for error in self.validate(head)))

    def test_parent_policy_change_is_rejected(self):
        head = self.commit(
            "tests/desktop-branch-path-ownership.json",
            json.dumps({**POLICY, "schemaVersion": 2}),
        )
        self.assertTrue(any("main-owned path" in error for error in self.validate(head)))

    def test_policy_is_loaded_from_main_not_head(self):
        weakened = json.loads(json.dumps(POLICY))
        weakened["targets"]["linux-main"]["ownedPrefixes"] = ["tests/device/"]
        self.write("tests/desktop-branch-path-ownership.json", json.dumps(weakened))
        self.write("tests/device/core", "changed\n")
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "weaken policy")
        self.assertTrue(any("tests/device/core" in error
                            for error in self.validate(revision(self.repo))))

    def test_symlink_in_owned_directory_is_rejected(self):
        destination = self.repo / "tests/device/adapters/linux/secret-link"
        destination.parent.mkdir(parents=True)
        os.symlink("../../../outside", destination)
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "symlink")
        self.assertTrue(any("unsafe Git object type" in error
                            for error in self.validate(revision(self.repo))))

    def test_malformed_main_policy_fails_closed(self):
        self.main_revision = self.commit(
            "tests/desktop-branch-path-ownership.json", "{not json\n"
        )
        head = self.commit("tests/device/adapters/linux/adapter.py", "linux\n")
        self.assertTrue(any("invalid main ownership policy" in error
                            for error in self.validate(head)))

    def test_unknown_target_is_rejected(self):
        self.assertTrue(any("unsupported desktop target" in error
                            for error in self.validate(self.main_revision, "other")))

    def test_head_without_main_ancestry_is_rejected(self):
        run(self.repo, "checkout", "--orphan", "unrelated")
        run(self.repo, "rm", "-qrf", ".")
        self.write("unrelated", "branch\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "unrelated")
        self.assertTrue(any("current main history" in error
                            for error in self.validate(revision(self.repo))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
