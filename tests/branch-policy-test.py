#!/usr/bin/env python3
"""Tests for the permanent branch hierarchy and pull-request policy."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/branch-policy/check.py"
POLICY = ROOT / ".github/branch-policy.json"
SPEC = importlib.util.spec_from_file_location("branch_policy", CHECKER)
assert SPEC and SPEC.loader
BRANCH_POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRANCH_POLICY
SPEC.loader.exec_module(BRANCH_POLICY)


class BranchPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.branches = BRANCH_POLICY.load_policy(POLICY)

    def test_expected_hierarchy_is_complete(self):
        self.assertEqual(
            set(self.branches),
            {
                "main", "android-main", "android-phone", "android-vr",
                "android-vr-pico", "android-vr-quest", "apple-main",
                "apple-ios", "apple-macos",
            },
        )

    def test_every_child_accepts_its_direct_parent(self):
        for branch in self.branches.values():
            if branch.parent:
                self.assertEqual(
                    BRANCH_POLICY.classify_pull_request(self.branches, branch.name, branch.parent),
                    "downstream-sync",
                )

    def test_scoped_feature_and_promotion_are_accepted(self):
        self.assertEqual(
            BRANCH_POLICY.classify_pull_request(
                self.branches, "android-vr-pico", "feature/android-pico/controllers"
            ),
            "scoped-change",
        )
        self.assertEqual(
            BRANCH_POLICY.classify_pull_request(
                self.branches, "android-vr", "promote/android-vr/openxr-fix"
            ),
            "promotion",
        )

    def test_scoped_sync_and_reconciliation_are_accepted(self):
        for head in (
            "sync/android-pico/android-vr-refresh",
            "reconcile/android-pico/android-vr-refresh",
        ):
            with self.subTest(head=head):
                self.assertEqual(
                    BRANCH_POLICY.classify_pull_request(
                        self.branches, "android-vr-pico", head
                    ),
                    "scoped-change",
                )

    def test_sync_for_wrong_target_scope_is_rejected(self):
        with self.assertRaises(BRANCH_POLICY.PolicyError):
            BRANCH_POLICY.classify_pull_request(
                self.branches,
                "android-vr-pico",
                "sync/android-quest/android-vr-refresh",
            )

    def test_child_to_parent_and_sibling_merges_are_blocked(self):
        blocked = (
            ("android-vr", "android-vr-pico"),
            ("android-vr-pico", "android-vr-quest"),
            ("apple-main", "apple-ios"),
            ("main", "android-main"),
        )
        for base, head in blocked:
            with self.subTest(base=base, head=head):
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.classify_pull_request(self.branches, base, head)

    def test_wrong_scope_is_blocked(self):
        with self.assertRaises(BRANCH_POLICY.PolicyError):
            BRANCH_POLICY.classify_pull_request(
                self.branches, "android-vr", "feature/android-pico/controllers"
            )

    def test_policy_rejects_inconsistent_relationships(self):
        document = json.loads(POLICY.read_text(encoding="utf-8"))
        document["branches"]["android-vr"]["parent"] = "apple-main"
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "policy.json"
            invalid.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(BRANCH_POLICY.PolicyError):
                BRANCH_POLICY.load_policy(invalid)

    def test_cli_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "check-pr", "--base", "main",
             "--head", "feature/android-pico/wrong-layer"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("branch policy violation", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
