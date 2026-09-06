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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/branch-policy/check.py"
DRIFT_CHECKER = ROOT / "tools/branch-policy/drift.py"
POLICY = ROOT / ".github/branch-policy.json"
ARCHIVED_BRANCH_RETIREMENT = ROOT / ".github/rulesets/retirements/archived-branches.json"
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
BASE_SHA = "3" * 40
PARENT_SHA = "4" * 40
RECONCILIATION_SHA = "5" * 40
PRIVILEGED_BLOB_SHA = "6" * 40
PRIVILEGED_ENTRIES = (
    (".github/branch-policy.json", "100644", "blob", PRIVILEGED_BLOB_SHA),
    ("tools/branch-policy/check.py", "100755", "blob", "7" * 40),
)


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


class FakeReconciliationApi:
    def __init__(
        self,
        *,
        base,
        parent,
        base_branch,
        parent_branch,
        parents=None,
        comparisons=None,
        parent_entries=PRIVILEGED_ENTRIES,
        head_entries=PRIVILEGED_ENTRIES,
        failure=None,
        branch_sequences=None,
    ):
        self.shas = {base_branch: base, parent_branch: parent}
        self.parents = parents or (base, parent)
        self.comparisons = comparisons or {}
        self.parent = parent
        self.head_entries = head_entries
        self.parent_entries = parent_entries
        self.failure = failure
        self.branch_sequences = branch_sequences or {}
        self.calls = []

    def branch_sha(self, repository, branch):
        self.calls.append(("branch", branch))
        if self.failure == "branch":
            raise BRANCH_POLICY.PolicyError("simulated GitHub API failure")
        sequence = self.branch_sequences.get(branch)
        if sequence:
            return sequence.pop(0)
        return self.shas[branch]

    def commit_parents(self, repository, commit):
        self.calls.append(("parents", commit))
        if self.failure == "commit":
            raise BRANCH_POLICY.PolicyError("simulated commit API failure")
        return self.parents

    def compare(self, repository, ancestor, head):
        self.calls.append(("compare", ancestor))
        if self.failure == "compare":
            raise BRANCH_POLICY.PolicyError("simulated compare API failure")
        return self.comparisons.get(
            ancestor,
            {
                "status": "ahead",
                "behind_by": 0,
                "base_commit": {"sha": ancestor},
                "merge_base_commit": {"sha": ancestor},
            },
        )

    def tree_entries(self, repository, commit):
        self.calls.append(("tree", commit))
        if self.failure == "tree":
            raise BRANCH_POLICY.PolicyError("simulated incomplete tree API response")
        return self.parent_entries if commit == self.parent else self.head_entries


class BranchPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.branches = BRANCH_POLICY.load_policy(POLICY)
        cls.dependabot_targets = BRANCH_POLICY.load_dependabot_targets(POLICY)

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

        plan = json.loads(ARCHIVED_BRANCH_RETIREMENT.read_text(encoding="utf-8"))
        ruleset = plan["ruleset_retirement"]["expected_current"]
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

    def test_scoped_sync_is_an_ordinary_scoped_change(self):
        self.assertEqual(
            BRANCH_POLICY.classify_pull_request(
                self.branches,
                "android-vr-pico",
                "sync/android-pico/android-vr-refresh",
            ),
            "scoped-change",
        )

    def test_exact_task_namespace_is_accepted_on_every_permanent_base(self):
        for branch in self.branches.values():
            head = f"task/{branch.scope}/123-maintenance-policy"
            with self.subTest(base=branch.name, head=head):
                self.assertEqual(
                    BRANCH_POLICY.classify_pull_request(
                        self.branches, branch.name, head
                    ),
                    "task",
                )

    def test_malformed_or_wrong_scope_task_names_are_rejected_on_every_base(self):
        for branch in self.branches.values():
            other_scope = next(
                candidate.scope
                for candidate in self.branches.values()
                if candidate.scope != branch.scope
            )
            cases = (
                f"task/{other_scope}/123-change",
                f"task/{branch.scope}/0-change",
                f"task/{branch.scope}/01-change",
                f"task/{branch.scope}/123-",
                f"task/{branch.scope}/123-Upper",
                f"task/{branch.scope}/123-two--parts",
                f"task/{branch.scope}/123-two_parts",
                f"task/{branch.scope}/123-two.parts",
                f"task/{branch.scope}/123/nested",
            )
            for head in cases:
                with self.subTest(base=branch.name, head=head):
                    with self.assertRaises(BRANCH_POLICY.PolicyError):
                        BRANCH_POLICY.classify_pull_request(
                            self.branches, branch.name, head
                        )

    def test_legacy_names_remain_accepted_on_every_permanent_base(self):
        legacy_kinds = (
            "feature", "fix", "docs", "refactor",
            "test", "tests", "ci", "sync",
        )
        for branch in self.branches.values():
            for kind in legacy_kinds:
                head = f"{kind}/{branch.scope}/transition-compatible"
                with self.subTest(base=branch.name, head=head):
                    self.assertEqual(
                        BRANCH_POLICY.classify_pull_request(
                            self.branches, branch.name, head
                        ),
                        "scoped-change",
                    )
            self.assertEqual(
                BRANCH_POLICY.classify_pull_request(
                    self.branches,
                    branch.name,
                    f"promote/{branch.scope}/transition-compatible",
                ),
                "promotion",
            )

    def test_task_namespace_requires_the_event_repository(self):
        head = "task/main/123-maintenance-policy"
        self.assertEqual(
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="main",
                head=head,
                repository_id=100,
                base_repository_id=100,
                head_repository_id=100,
                head_sha=CURRENT_SHA,
            ),
            "task",
        )
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "event repository"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="main",
                head=head,
                repository_id=100,
                base_repository_id=100,
                head_repository_id=200,
                head_sha=CURRENT_SHA,
            )

    def test_genuine_dependabot_security_update_is_accepted(self):
        result = BRANCH_POLICY.evaluate_pull_request(
            self.branches,
            base="main",
            head="dependabot/npm_and_yarn/tools/jsdoc/markdown-it-14.1.0",
            repository_id=100,
            base_repository_id=100,
            head_repository_id=100,
            head_sha=CURRENT_SHA,
            dependabot_targets=self.dependabot_targets,
            pr_author_login="dependabot[bot]",
            pr_author_type="Bot",
        )
        self.assertEqual(result, "dependabot-security")

    def test_dependabot_same_repository_and_fork_spoofs_are_rejected(self):
        cases = (
            {"pr_author_login": "maintainer", "pr_author_type": "User"},
            {"pr_author_login": "dependabot[bot]", "pr_author_type": "User"},
            {
                "pr_author_login": "dependabot[bot]",
                "pr_author_type": "Bot",
                "head_repository_id": 200,
            },
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base="main",
                        head="dependabot/gradle/android/common/tests/robolectric/junit-4.14",
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=case.get("head_repository_id", 100),
                        head_sha=CURRENT_SHA,
                        dependabot_targets=self.dependabot_targets,
                        pr_author_login=case["pr_author_login"],
                        pr_author_type=case["pr_author_type"],
                    )

    def test_dependabot_wrong_base_prefix_directory_or_nested_dependency_is_rejected(self):
        cases = (
            ("android-main", "dependabot/npm_and_yarn/tools/jsdoc/pkg-1.0"),
            ("main", "dependabot/npm/tools/jsdoc/pkg-1.0"),
            ("main", "dependabot/npm_and_yarn/unknown/pkg-1.0"),
            ("main", "dependabot/npm_and_yarn/tools/jsdoc/scope/pkg-1.0"),
            ("main", "dependabot/npm_and_yarn/tools/jsdoc/"),
        )
        for base, head in cases:
            with self.subTest(base=base, head=head):
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base=base,
                        head=head,
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=100,
                        head_sha=CURRENT_SHA,
                        dependabot_targets=self.dependabot_targets,
                        pr_author_login="dependabot[bot]",
                        pr_author_type="Bot",
                    )

    def test_exact_reconciliation_names_are_classified_separately(self):
        cases = (
            ("android-main", "reconcile/android/main-refresh"),
            ("apple-main", "reconcile/apple/main-refresh"),
            ("apple-ios", "reconcile/ios/apple-refresh"),
        )
        for base, head in cases:
            with self.subTest(base=base, head=head):
                self.assertEqual(
                    BRANCH_POLICY.classify_pull_request(self.branches, base, head),
                    "reconciliation",
                )

    def test_reconciliation_wrong_scope_root_empty_or_nested_name_is_rejected(self):
        cases = (
            ("apple-main", "reconcile/ios/main-refresh"),
            ("main", "reconcile/main/child-refresh"),
            ("apple-main", "reconcile/apple/"),
            ("apple-main", "reconcile/apple/nested/name"),
        )
        for base, head in cases:
            with self.subTest(base=base, head=head):
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.classify_pull_request(self.branches, base, head)

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
                changed_files=("tools/branch-policy/check.py",),
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
                changed_files=(".github/workflows/branch-sync.yml",),
            )

    def test_direct_parent_sync_requires_the_current_parent_sha(self):
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "current parent SHA"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="apple-main",
                head="main",
                repository_id=100,
                base_repository_id=100,
                head_repository_id=100,
                head_sha=CURRENT_SHA,
                changed_files=("tools/branch-policy/check.py",),
            )

    def test_privileged_changes_from_forks_or_to_child_branches_are_rejected(self):
        privileged = (".github/workflows/branch-sync.yml",)
        cases = (
            dict(base="main", head="ci/main/replace-policy", head_repository_id=200),
            dict(base="android-main", head="ci/android/replace-policy", head_repository_id=100),
            dict(base="apple-main", head="sync/apple/main-refresh", head_repository_id=100),
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

    def test_privileged_changes_are_allowed_for_same_repository_main_prs(self):
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

    def test_maintenance_paths_are_privileged_without_prefix_confusion(self):
        privileged = (
            ".github/maintenance-policy.json",
            "tools/maintenance/contracts.py",
            "tests/maintenance/policy/test_policy.py",
        )
        ordinary = (
            ".github/maintenance-policy.json.bak",
            "tools/maintenance-extra/contracts.py",
            "tests/maintenance-extra/test_policy.py",
        )
        for path in privileged:
            with self.subTest(path=path):
                self.assertTrue(BRANCH_POLICY.changes_privileged_policy((path,)))
        for path in ordinary:
            with self.subTest(path=path):
                self.assertFalse(BRANCH_POLICY.changes_privileged_policy((path,)))

    def test_maintenance_paths_follow_existing_privileged_transfer_rules(self):
        paths = (
            ".github/maintenance-policy.json",
            "tools/maintenance/contracts.py",
            "tests/maintenance/policy/test_policy.py",
        )
        for path in paths:
            with self.subTest(path=path, route="main-task"):
                self.assertEqual(
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base="main",
                        head="task/main/123-maintenance-policy",
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=100,
                        head_sha=CURRENT_SHA,
                        changed_files=(path,),
                    ),
                    "task",
                )

            with self.subTest(path=path, route="child-task-rejected"):
                with self.assertRaisesRegex(
                    BRANCH_POLICY.PolicyError, "privileged policy"
                ):
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base="android-main",
                        head="task/android/123-maintenance-policy",
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=100,
                        head_sha=CURRENT_SHA,
                        changed_files=(path,),
                    )

            with self.subTest(path=path, route="verified-forward-sync"):
                self.assertEqual(
                    BRANCH_POLICY.evaluate_pull_request(
                        self.branches,
                        base="android-main",
                        head="main",
                        repository_id=100,
                        base_repository_id=100,
                        head_repository_id=100,
                        head_sha=CURRENT_SHA,
                        expected_head_sha=CURRENT_SHA,
                        changed_files=(path,),
                    ),
                    "downstream-sync",
                )

    def test_direct_parent_sync_may_carry_privileged_policy(self):
        for branch in self.branches.values():
            if branch.parent is None:
                continue
            with self.subTest(base=branch.name, head=branch.parent):
                result = BRANCH_POLICY.evaluate_pull_request(
                    self.branches,
                    base=branch.name,
                    head=branch.parent,
                    repository_id=100,
                    base_repository_id=100,
                    head_repository_id=100,
                    head_sha=CURRENT_SHA,
                    expected_head_sha=CURRENT_SHA,
                    changed_files=("tools/branch-policy/check.py",),
                )
                self.assertEqual(result, "downstream-sync")

    def reconciliation_api(self, base, parent, base_branch, parent_branch, **kwargs):
        return FakeReconciliationApi(
            base=base,
            parent=parent,
            base_branch=base_branch,
            parent_branch=parent_branch,
            **kwargs,
        )

    def attest(
        self,
        *,
        base,
        head,
        api,
        repository_id=100,
        base_repository_id=100,
        head_repository_id=100,
    ):
        return BRANCH_POLICY.attest_reconciliation(
            self.branches,
            base=base,
            head=head,
            repository="noah-be/overte",
            repository_id=repository_id,
            base_repository_id=base_repository_id,
            head_repository_id=head_repository_id,
            head_sha=RECONCILIATION_SHA,
            api=api,
        )

    def test_valid_android_and_apple_reconciliations_are_attested(self):
        cases = (
            ("android-main", "main", "reconcile/android/main-refresh"),
            ("apple-ios", "apple-main", "reconcile/ios/apple-refresh"),
        )
        for base, parent, head in cases:
            with self.subTest(base=base, head=head):
                api = self.reconciliation_api(
                    BASE_SHA, PARENT_SHA, base, parent
                )
                attestation = self.attest(base=base, head=head, api=api)
                result = BRANCH_POLICY.evaluate_pull_request(
                    self.branches,
                    base=base,
                    head=head,
                    repository_id=100,
                    base_repository_id=100,
                    head_repository_id=100,
                    head_sha=RECONCILIATION_SHA,
                    changed_files=("tools/branch-policy/check.py",),
                    reconciliation_attestation=attestation,
                )
                self.assertEqual(result, "reconciliation")

    def test_reconciliation_without_internal_attestation_is_rejected(self):
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "trusted API"):
            BRANCH_POLICY.evaluate_pull_request(
                self.branches,
                base="apple-main",
                head="reconcile/apple/main-refresh",
                repository_id=100,
                base_repository_id=100,
                head_repository_id=100,
                head_sha=RECONCILIATION_SHA,
            )

    def test_reconciliation_from_a_fork_or_foreign_base_is_rejected_before_api(self):
        cases = (
            {"head_repository_id": 200},
            {"base_repository_id": 200, "head_repository_id": 200},
        )
        for identifiers in cases:
            with self.subTest(identifiers=identifiers):
                api = self.reconciliation_api(
                    BASE_SHA, PARENT_SHA, "apple-main", "main"
                )
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "event repository"):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                        **identifiers,
                    )
                self.assertEqual(api.calls, [])

    def test_stale_base_or_parent_merge_parent_is_rejected(self):
        cases = (
            (STALE_SHA, PARENT_SHA),
            (BASE_SHA, STALE_SHA),
        )
        for first_parent, second_parent in cases:
            with self.subTest(parents=(first_parent, second_parent)):
                api = self.reconciliation_api(
                    BASE_SHA,
                    PARENT_SHA,
                    "apple-main",
                    "main",
                    parents=(first_parent, second_parent),
                )
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "direct merge"):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                    )

    def test_missing_base_or_parent_ancestry_is_rejected(self):
        invalid = {
            "status": "diverged",
            "behind_by": 1,
            "base_commit": {"sha": BASE_SHA},
            "merge_base_commit": {"sha": STALE_SHA},
        }
        for missing in (BASE_SHA, PARENT_SHA):
            with self.subTest(missing=missing):
                api = self.reconciliation_api(
                    BASE_SHA,
                    PARENT_SHA,
                    "apple-main",
                    "main",
                    comparisons={missing: invalid},
                )
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "not an ancestor"):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                    )

    def test_skipped_hierarchy_level_is_rejected(self):
        api = self.reconciliation_api(
            BASE_SHA,
            PARENT_SHA,
            "apple-ios",
            "apple-main",
            parents=(BASE_SHA, CURRENT_SHA),
        )
        with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "direct merge"):
            self.attest(
                base="apple-ios",
                head="reconcile/ios/main-refresh",
                api=api,
            )

    def test_changed_deleted_added_mode_or_blob_privileged_entry_is_rejected(self):
        changed_cases = {
            "changed": (
                (".github/branch-policy.json", "100644", "blob", "8" * 40),
                PRIVILEGED_ENTRIES[1],
            ),
            "deleted": PRIVILEGED_ENTRIES[:-1],
            "added": PRIVILEGED_ENTRIES
            + (("tools/branch-policy/extra.py", "100644", "blob", "8" * 40),),
            "mode": (
                PRIVILEGED_ENTRIES[0],
                ("tools/branch-policy/check.py", "100644", "blob", "7" * 40),
            ),
            "blob": (
                PRIVILEGED_ENTRIES[0],
                ("tools/branch-policy/check.py", "100755", "blob", "8" * 40),
            ),
        }
        for kind, head_entries in changed_cases.items():
            with self.subTest(kind=kind):
                api = self.reconciliation_api(
                    BASE_SHA,
                    PARENT_SHA,
                    "apple-main",
                    "main",
                    head_entries=head_entries,
                )
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "privileged tree"):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                    )

    def test_api_compare_and_incomplete_tree_errors_fail_closed(self):
        for failure in ("branch", "commit", "compare", "tree"):
            with self.subTest(failure=failure):
                api = self.reconciliation_api(
                    BASE_SHA,
                    PARENT_SHA,
                    "apple-main",
                    "main",
                    failure=failure,
                )
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                    )

    def test_base_or_parent_ref_drift_during_attestation_is_rejected(self):
        cases = (
            {
                "apple-main": [BASE_SHA, STALE_SHA],
                "main": [PARENT_SHA, PARENT_SHA],
            },
            {
                "apple-main": [BASE_SHA, BASE_SHA],
                "main": [PARENT_SHA, STALE_SHA],
            },
        )
        for branch_sequences in cases:
            with self.subTest(branch_sequences=branch_sequences):
                api = self.reconciliation_api(
                    BASE_SHA,
                    PARENT_SHA,
                    "apple-main",
                    "main",
                    branch_sequences=branch_sequences,
                )
                with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "moved"):
                    self.attest(
                        base="apple-main",
                        head="reconcile/apple/main-refresh",
                        api=api,
                    )

    def test_production_api_rejects_invalid_json_and_incomplete_trees(self):
        api = BRANCH_POLICY.GitHubBranchApi()
        completed = subprocess.CompletedProcess(
            args=["gh", "api"], returncode=0, stdout="not-json", stderr=""
        )
        with mock.patch.object(BRANCH_POLICY.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "invalid JSON"):
                api._request("repos/example/project", "test response")

        for document in (
            {"truncated": True, "tree": []},
            {"truncated": False},
        ):
            with self.subTest(document=document):
                with mock.patch.object(api, "_request", return_value=document):
                    with self.assertRaisesRegex(BRANCH_POLICY.PolicyError, "incomplete"):
                        api.tree_entries("example/project", CURRENT_SHA)

    def test_production_tree_parser_rejects_duplicates_mode_and_blob_errors(self):
        api = BRANCH_POLICY.GitHubBranchApi()
        entry = {
            "path": ".github/branch-policy.json",
            "mode": "100644",
            "type": "blob",
            "sha": PRIVILEGED_BLOB_SHA,
        }
        documents = (
            {"truncated": False, "tree": [entry, entry]},
            {
                "truncated": False,
                "tree": [{**entry, "mode": "invalid"}],
            },
            {
                "truncated": False,
                "tree": [{**entry, "sha": "not-a-sha"}],
            },
        )
        for document in documents:
            with self.subTest(document=document):
                with mock.patch.object(api, "_request", return_value=document):
                    with self.assertRaises(BRANCH_POLICY.PolicyError):
                        api.tree_entries("example/project", CURRENT_SHA)

    def test_production_compare_parser_rejects_malformed_or_diverged_results(self):
        invalid_documents = (
            {},
            {
                "status": "diverged",
                "behind_by": 1,
                "base_commit": {"sha": BASE_SHA},
                "merge_base_commit": {"sha": STALE_SHA},
            },
            {
                "status": "ahead",
                "behind_by": 0,
                "base_commit": {"sha": STALE_SHA},
                "merge_base_commit": {"sha": BASE_SHA},
            },
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(BRANCH_POLICY.PolicyError):
                    BRANCH_POLICY.require_ancestor_comparison(document, BASE_SHA)

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

    def test_push_observation_is_pending_not_accepted_and_strict_default_still_fails(self):
        drifts = [BRANCH_DRIFT.Drift('main', 'android-main', CURRENT_SHA, 3, 'diverged')]
        self.assertEqual(BRANCH_DRIFT.result_status(drifts), ('DRIFT', 1))
        self.assertEqual(BRANCH_DRIFT.result_status(drifts, True), ('PENDING_PROPAGATION', 0))
        self.assertEqual(BRANCH_DRIFT.result_status([], True), ('SYNCHRONIZED', 0))

    def test_unbound_push_observation_fails_before_any_network_read(self):
        result = subprocess.run([sys.executable, str(DRIFT_CHECKER), '--repository',
                                 'noah-be/overte', '--observe-push'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires one explicit parent', result.stderr)

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
