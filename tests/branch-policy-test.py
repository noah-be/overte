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
DRIFT_CHECKER = ROOT / "tools/branch-policy/drift.py"
POLICY = ROOT / ".github/branch-policy.json"
ARCHIVED_BRANCH_RULESET = ROOT / ".github/rulesets/archived-branches.json"
SPEC = importlib.util.spec_from_file_location("branch_policy", CHECKER)
assert SPEC and SPEC.loader
BRANCH_POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRANCH_POLICY
SPEC.loader.exec_module(BRANCH_POLICY)
sys.path.insert(0, str(CHECKER.parent))
DRIFT_SPEC = importlib.util.spec_from_file_location("branch_drift", DRIFT_CHECKER)
assert DRIFT_SPEC and DRIFT_SPEC.loader
BRANCH_DRIFT = importlib.util.module_from_spec(DRIFT_SPEC)
sys.modules[DRIFT_SPEC.name] = BRANCH_DRIFT
DRIFT_SPEC.loader.exec_module(BRANCH_DRIFT)
sys.path.pop(0)

CURRENT_SHA = "1" * 40
STALE_SHA = "2" * 40


class FakeBranchApi:
    def __init__(self, *, sha=CURRENT_SHA, comparisons=None, failure=None):
        self.sha = sha
        self.comparisons = comparisons or {}
        self.failure = failure

    def branch_sha(self, repository, branch):
        if self.failure == "branch":
            raise BRANCH_DRIFT.ApiError("simulated branch API failure")
        return self.sha

    def compare(self, repository, child, parent_sha):
        if self.failure == "compare":
            raise BRANCH_DRIFT.ApiError("simulated compare API failure")
        return self.comparisons.get(child, {"ahead_by": 0, "status": "identical"})


class BranchPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.branches = BRANCH_POLICY.load_policy(POLICY)

    def test_expected_hierarchy_is_complete(self):
        self.assertEqual(
            set(self.branches),
            {
                "main", "android-main", "android-phone", "android-vr",
                "android-vr-pico", "apple-main", "apple-ios", "linux-main",
                "windows-main",
            },
        )

    def test_retired_targets_are_frozen_outside_the_active_hierarchy(self):
        archived_targets = {
            "android-vr-quest": "feature/android-quest/controllers",
            "apple-macos": "feature/macos/rendering",
        }
        for target, head in archived_targets.items():
            with self.subTest(target=target):
                self.assertNotIn(target, self.branches)
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.classify_pull_request(
                        self.branches,
                        target,
                        head,
                    )

        ruleset = json.loads(ARCHIVED_BRANCH_RULESET.read_text(encoding="utf-8"))
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertEqual(
            ruleset["conditions"]["ref_name"]["include"],
            [
                "refs/heads/android-vr-quest",
                "refs/heads/apple-macos",
                "refs/heads/backup/**",
            ],
        )
        self.assertEqual(
            {rule["type"] for rule in ruleset["rules"]},
            {"deletion", "non_fast_forward", "update"},
        )
        update = next(rule for rule in ruleset["rules"] if rule["type"] == "update")
        self.assertEqual(
            update["parameters"], {"update_allows_fetch_and_merge": False}
        )

    def test_desktop_operating_system_branches_are_direct_main_children(self):
        self.assertEqual(self.branches["linux-main"].parent, "main")
        self.assertEqual(self.branches["windows-main"].parent, "main")
        self.assertEqual(self.branches["linux-main"].scope, "linux")
        self.assertEqual(self.branches["windows-main"].scope, "windows")
        for target in ("linux-main", "windows-main"):
            self.assertEqual(
                BRANCH_POLICY.classify_pull_request(self.branches, target, "main"),
                "downstream-sync",
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

    def test_archived_quest_scope_is_rejected(self):
        with self.assertRaises(BRANCH_POLICY.PolicyError):
            BRANCH_POLICY.classify_pull_request(
                self.branches,
                "android-vr-pico",
                "sync/android-quest/android-vr-refresh",
            )

    def test_child_to_parent_and_sibling_merges_are_blocked(self):
        blocked = (
            ("android-vr", "android-vr-pico"),
            ("android-vr-pico", "android-phone"),
            ("apple-main", "apple-ios"),
            ("main", "android-main"),
            ("main", "linux-main"),
            ("linux-main", "windows-main"),
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

    def test_foreign_fork_with_head_branch_main_is_rejected(self):
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "base repository"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="android-main",
                head="main",
                repository_id=100,
                base_repository_id=100,
                head_repository_id=200,
                head_sha=CURRENT_SHA,
                expected_head_sha=CURRENT_SHA,
            )

    def test_same_parent_branch_name_with_wrong_repository_id_is_rejected(self):
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "base repository"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="android-vr",
                head="android-main",
                repository_id=100,
                base_repository_id=100,
                head_repository_id=101,
                head_sha=CURRENT_SHA,
                expected_head_sha=CURRENT_SHA,
            )

    def test_stale_parent_sha_is_rejected(self):
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "stale parent SHA"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="android-main",
                head="main",
                repository_id=100,
                base_repository_id=100,
                head_repository_id=100,
                head_sha=STALE_SHA,
                expected_head_sha=CURRENT_SHA,
            )

    def test_privileged_changes_from_forks_or_to_child_branches_are_rejected(self):
        privileged = (".github/workflows/branch-sync.yml",)
        cases = (
            dict(base="main", head="ci/main/replace-policy", head_repository_id=200),
            dict(base="android-main", head="ci/android/replace-policy", head_repository_id=100),
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "privileged policy"):
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base=case["base"],
                        head=case["head"],
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=case["head_repository_id"],
                        head_sha=CURRENT_SHA,
                        changed_files=privileged,
                    )

    def test_privileged_changes_are_allowed_only_for_same_repository_main_prs(self):
        result = BRANCH_POLICY.evaluate_pull_request(
            self.branches,
            base="main",
            head="ci/main/replace-policy",
            repository_id=100,
            base_repository_id=100,
            head_repository_id=100,
            head_sha=CURRENT_SHA,
            changed_files=("tools/branch-policy/check.py",),
        )
        self.assertEqual(result, "scoped-change")

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
             "--head", "feature/android-pico/wrong-layer",
             "--repository-id", "100",
             "--base-repository-id", "100", "--head-repository-id", "100",
             "--head-sha", CURRENT_SHA],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("branch policy violation", result.stdout)


class BranchDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.branches = BRANCH_POLICY.load_policy(POLICY)

    def test_reports_drift_without_a_pull_request_candidate(self):
        api = FakeBranchApi(
            comparisons={"android-main": {"ahead_by": 3, "status": "ahead"}}
        )
        drifts = BRANCH_DRIFT.scan_parent(
            self.branches, api, "noah-be/overte", "main", CURRENT_SHA
        )
        self.assertEqual(
            [(item.parent, item.child, item.ahead_by) for item in drifts],
            [("main", "android-main", 3)],
        )

    def test_stale_push_parent_sha_fails_closed(self):
        with self.assertRaisesRegex(BRANCH_DRIFT.PolicyError, "stale parent SHA"):
            BRANCH_DRIFT.scan_parent(
                self.branches,
                FakeBranchApi(),
                "noah-be/overte",
                "main",
                STALE_SHA,
            )

    def test_branch_api_and_compare_errors_fail_closed(self):
        for failure in ("branch", "compare"):
            with self.subTest(failure=failure):
                with self.assertRaises(BRANCH_DRIFT.ApiError):
                    BRANCH_DRIFT.scan_parent(
                        self.branches,
                        FakeBranchApi(failure=failure),
                        "noah-be/overte",
                        "main",
                        CURRENT_SHA,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
