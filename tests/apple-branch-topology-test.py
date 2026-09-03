#!/usr/bin/env python3
"""Self-tests for Apple parent/target path ownership."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECK = Path(__file__).with_name("apple-branch-topology-check.py")
WORKFLOW = CHECK.parents[1] / ".github/workflows/apple-branch-topology.yml"
MACOS_WORKFLOW = CHECK.parents[1] / ".github/workflows/macos-bootstrap.yml"
SPEC = importlib.util.spec_from_file_location("apple_topology", CHECK)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


POLICY = {
    "schemaVersion": 1,
    "parentOwnedPrefixes": ["tests/device/"],
    "parentOwnedFiles": [
        ".github/workflows/apple-branch-topology.yml",
        "docs/BRANCH_WORKFLOW.md",
        "tests/apple-branch-path-ownership.json",
        "tests/apple-branch-topology-check.py",
        "tests/apple-branch-topology-test.py",
    ],
    "targets": {
        "apple-ios": {
            "ownedPrefixes": [
                "tests/device/adapters/appium/",
                "tests/device/ios/",
                "tests/device/jenkins/",
            ],
            "ownedFiles": ["tests/device/TOOLCHAIN.md"],
        },
    },
}


def run(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def revision(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


class AppleBranchTopologyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="apple-topology-test-")
        self.repo = Path(self.temporary.name)
        run(self.repo, "init", "-q")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "tests/device").mkdir(parents=True)
        (self.repo / "tests/device/core").write_text("v1\n")
        self.write("tests/apple-branch-path-ownership.json", json.dumps(POLICY))
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "apple main")
        self.apple_main = revision(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path: str, content: str) -> None:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    def commit(self, path: str, content: str) -> str:
        self.write(path, content)
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", path)
        return revision(self.repo)

    def validate(self, head: str, target: str = "apple-ios") -> list[str]:
        return MODULE.validate(self.repo, self.apple_main, head, target)

    def test_ios_owned_directory_change_is_allowed(self):
        head = self.commit("tests/device/ios/backend.py", "ios\n")
        self.assertEqual([], self.validate(head))

    def test_ios_owned_appium_directory_is_allowed(self):
        head = self.commit("tests/device/adapters/appium/adapter.py", "ios\n")
        self.assertEqual([], self.validate(head))

    def test_macos_is_not_an_active_apple_target(self):
        self.assertEqual(
            ["unsupported Apple target: apple-macos"],
            self.validate(self.apple_main, "apple-macos"),
        )
        self.assertNotIn(
            "apple-macos",
            WORKFLOW.read_text(encoding="utf-8"),
        )
        macos_workflow = MACOS_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(macos_workflow, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(
            macos_workflow,
            r"(?m)^  (push|pull_request|pull_request_target):$",
        )

    def test_exact_ios_owned_file_is_allowed(self):
        head = self.commit("tests/device/TOOLCHAIN.md", "ios pins\n")
        self.assertEqual([], self.validate(head))

    def test_owned_file_near_miss_is_rejected(self):
        head = self.commit("tests/device/TOOLCHAIN.md.bak", "not owned\n")
        self.assertTrue(any("apple-main-owned path" in error
                            for error in self.validate(head)))

    def test_shared_harness_edit_is_rejected(self):
        head = self.commit("tests/device/core", "changed directly\n")
        self.assertTrue(any("apple-main-owned path" in error
                            for error in self.validate(head)))

    def test_shared_harness_add_is_rejected(self):
        head = self.commit("tests/device/new_common.py", "new\n")
        self.assertTrue(any("apple-main-owned path" in error
                            for error in self.validate(head)))

    def test_shared_harness_delete_is_rejected(self):
        (self.repo / "tests/device/core").unlink()
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "delete shared")
        self.assertTrue(any("apple-main-owned path" in error
                            for error in self.validate(revision(self.repo))))

    def test_shared_to_owned_rename_is_rejected(self):
        (self.repo / "tests/device/ios").mkdir(parents=True)
        run(self.repo, "mv", "tests/device/core", "tests/device/ios/core")
        run(self.repo, "commit", "-qm", "rename shared into owned")
        self.assertTrue(any("tests/device/core" in error
                            for error in self.validate(revision(self.repo))))

    def test_parent_policy_change_is_rejected(self):
        head = self.commit(
            "tests/apple-branch-path-ownership.json",
            json.dumps({**POLICY, "schemaVersion": 2}),
        )
        self.assertTrue(any("apple-main-owned path" in error
                            for error in self.validate(head)))

    def test_policy_is_loaded_from_parent_not_head(self):
        weakened = json.loads(json.dumps(POLICY))
        weakened["targets"]["apple-ios"]["ownedPrefixes"].append("tests/device/")
        self.write("tests/apple-branch-path-ownership.json", json.dumps(weakened))
        self.write("tests/device/core", "changed\n")
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "try to weaken policy")
        errors = self.validate(revision(self.repo))
        self.assertTrue(any("tests/device/core" in error for error in errors))

    def test_symlink_in_owned_directory_is_rejected(self):
        destination = self.repo / "tests/device/ios/secret-link"
        destination.parent.mkdir(parents=True)
        os.symlink("../../outside", destination)
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "symlink")
        self.assertTrue(any("unsafe Git object type" in error
                            for error in self.validate(revision(self.repo))))

    def test_malformed_parent_policy_fails_closed(self):
        self.apple_main = self.commit(
            "tests/apple-branch-path-ownership.json", "{not json\n"
        )
        head = self.commit("tests/device/ios/backend.py", "ios\n")
        self.assertTrue(any("invalid apple-main ownership policy" in error
                            for error in self.validate(head)))

    def test_parent_cannot_delegate_entire_shared_scope(self):
        weakened = json.loads(json.dumps(POLICY))
        weakened["targets"]["apple-ios"]["ownedPrefixes"] = ["tests/device/"]
        self.apple_main = self.commit(
            "tests/apple-branch-path-ownership.json", json.dumps(weakened)
        )
        head = self.commit("tests/device/ios/backend.py", "ios\n")
        self.assertTrue(any("cannot own an entire parent prefix" in error
                            for error in self.validate(head)))

    def test_non_normalized_policy_path_fails_closed(self):
        malformed = json.loads(json.dumps(POLICY))
        malformed["targets"]["apple-ios"]["ownedPrefixes"] = [
            "tests/device//ios/"
        ]
        self.apple_main = self.commit(
            "tests/apple-branch-path-ownership.json", json.dumps(malformed)
        )
        head = self.commit("tests/device/ios/backend.py", "ios\n")
        self.assertTrue(any("normalized directory prefixes" in error
                            for error in self.validate(head)))

    def test_missing_parent_policy_fails_closed(self):
        (self.repo / "tests/apple-branch-path-ownership.json").unlink()
        run(self.repo, "add", "-A")
        run(self.repo, "commit", "-qm", "remove policy")
        self.apple_main = revision(self.repo)
        head = self.commit("tests/device/ios/backend.py", "ios\n")
        self.assertTrue(any("cannot load" in error for error in self.validate(head)))

    def test_unknown_target_is_rejected(self):
        self.assertTrue(any("unsupported Apple target" in error
                            for error in self.validate(self.apple_main, "other")))

    def test_head_without_apple_main_ancestry_is_rejected(self):
        run(self.repo, "checkout", "--orphan", "direct-main")
        run(self.repo, "rm", "-qrf", ".")
        self.write("direct", "main\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "direct main")
        self.assertTrue(any("current apple-main history" in error
                            for error in self.validate(revision(self.repo))))


if __name__ == "__main__":
    unittest.main()
