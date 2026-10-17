#!/usr/bin/env python3
"""Offline safety tests for the fork's branch cleanup automation."""

from __future__ import annotations

import copy
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/branch-cleanup/cleanup.py"
POLICY_PATH = ROOT / ".github/branch-cleanup.json"
FORK = "noah-l-frank/overte"
FORK_URL = "https://github.com/noah-l-frank/overte.git"
PERMANENT = {
    "main", "android-main", "android-phone", "android-vr", "android-vr-pico",
    "apple-main", "apple-ios",
}


def load_cleanup():
    spec = importlib.util.spec_from_file_location("branch_cleanup_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_adoption():
    cleanup = load_cleanup()
    spec = importlib.util.spec_from_file_location("branch_adoption_under_test", SCRIPT.with_name("adoption.py"))
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"cleanup": cleanup}):
        spec.loader.exec_module(module)
    return module


class LocalGitFixture:
    """A real commit graph and bare remote; no network or user Git config."""

    def __init__(self, root: Path):
        self.root = root
        self.seed = root / "seed"
        self.remote = root / "remote.git"
        self.seed.mkdir()
        self.env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Cleanup Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Cleanup Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        for key in (
            "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CONFIG_COUNT",
        ):
            self.env.pop(key, None)
        self.git(self.seed, "init", "-q", "--initial-branch=main")
        self.git(self.seed, "commit", "-q", "--allow-empty", "-m", "initial")
        self.initial = self.rev(self.seed, "HEAD")
        for branch in sorted(PERMANENT - {"main"}):
            self.git(self.seed, "branch", branch)
        self.merged_branch = "task/main/100-integrated"
        self.merged_sha = self.commit_branch(self.merged_branch, "main", "integrated.txt")
        self.git(self.seed, "checkout", "-q", "main")
        self.git(self.seed, "merge", "-q", "--no-ff", self.merged_branch, "-m", "merge integrated work")
        self.main_sha = self.rev(self.seed, "HEAD")
        self.unmerged_branch = "task/main/101-unmerged"
        self.unmerged_sha = self.commit_branch(self.unmerged_branch, "main", "unmerged.txt")
        self.git(self.seed, "checkout", "-q", "main")
        self.git(self.root, "init", "-q", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.seed, "remote", "add", "fixture", str(self.remote))
        self.git(self.seed, "push", "-q", "fixture", "--all")

    def git(self, directory: Path, *args: str, check: bool = True):
        return subprocess.run(
            ["git", "-C", str(directory), *args], env=self.env,
            text=True, capture_output=True, check=check,
        )

    def rev(self, directory: Path, ref: str) -> str:
        return self.git(directory, "rev-parse", ref).stdout.strip()

    def commit_branch(self, branch: str, parent: str, filename: str) -> str:
        self.git(self.seed, "checkout", "-q", "-b", branch, parent)
        (self.seed / filename).write_text(filename + "\n", encoding="utf-8")
        self.git(self.seed, "add", filename)
        self.git(self.seed, "commit", "-q", "-m", filename)
        return self.rev(self.seed, "HEAD")

    def remote_ref(self, ref: str) -> str | None:
        result = self.git(self.remote, "rev-parse", "--verify", ref, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def advance_remote_branch(self, branch: str) -> str:
        self.git(self.seed, "checkout", "-q", branch)
        self.git(self.seed, "commit", "-q", "--allow-empty", "-m", "new work after snapshot")
        sha = self.rev(self.seed, "HEAD")
        self.git(self.seed, "push", "-q", "fixture", f"refs/heads/{branch}:refs/heads/{branch}")
        return sha


class OfflineGitTransport:
    """Redirect only an already-authorized transport to a temporary bare repo."""

    def __init__(self, fixture: LocalGitFixture, events: list, error_type):
        self.fixture = fixture
        self.events = events
        self.error_type = error_type

    def __call__(self, args, **kwargs):
        args = [str(value) for value in args]
        if not args or args[0] != "git":
            raise AssertionError("tests prohibit non-Git subprocesses and live GitHub calls")
        original = tuple(args)
        transports = {"clone", "fetch", "push", "ls-remote"}
        command = next((value for value in args[1:] if value in transports), None)
        self.events.append(("git", command, original))
        if command:
            routed = False
            for index, value in enumerate(args):
                if value in ("cleanup", FORK_URL):
                    args[index] = str(self.fixture.remote)
                    routed = True
                elif value.startswith(("https://", "http://", "ssh://", "git@")):
                    raise AssertionError("production transport used an unauthorized repository")
            # Local bundle verification legitimately fetches from local paths.
            if not routed and not any(
                str(self.fixture.root) in value for value in args
            ):
                raise AssertionError("tests prohibit a transport outside their fixture")
        check = kwargs.pop("check", True)
        kwargs.setdefault("text", True)
        kwargs.setdefault("capture_output", True)
        kwargs["env"] = {**kwargs.get("env", {}), **self.fixture.env}
        result = subprocess.run(args, check=False, **kwargs)
        if check and result.returncode:
            raise self.error_type("offline Git operation failed")
        return result


class FakeGithubOwner:
    def __init__(self, events: list):
        self.events = events

    def verify_owner(self):
        self.events.append(("verify_owner",))
        return {"full_name": FORK, "id": 1319052603}


class PolicyAndSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.candidate = "task/main/100-integrated"
        self.sha = "a" * 40
        self.base_sha = "b" * 40
        self.branches = [
            {"name": branch, "sha": self.base_sha, "protected": True}
            for branch in sorted(PERMANENT)
        ] + [{"name": self.candidate, "sha": self.sha, "protected": False}]
        self.comparisons = {
            self.candidate: {
                "status": "ahead", "behind_by": 0,
                "merge_base_commit": {"sha": self.sha},
            }
        }

    def select(self, **kwargs):
        return self.module.select_candidates(
            kwargs.get("branches", self.branches),
            kwargs.get("policy", self.policy),
            kwargs.get("comparisons", self.comparisons),
            kwargs.get("holds"),
        )

    def assert_not_eligible(self, **kwargs):
        try:
            candidates, _ = self.select(**kwargs)
        except self.module.CleanupError:
            return
        self.assertNotIn(self.candidate, [item["branch"] for item in candidates])

    def test_valid_policy_binds_exact_fork_and_seven_permanent_branches(self):
        validated = self.module.validate_policy(self.policy)
        self.assertEqual(validated["repository"], FORK)
        self.assertEqual(validated["repository_id"], 1319052603)
        self.assertEqual(set(validated["permanent_branches"]), PERMANENT)
        self.assertNotIn("archive_tag_prefix", validated)

    def test_foreign_repository_or_repository_id_is_rejected(self):
        for key, value in (("repository", "overte-org/overte"), ("repository", "someone/overte"),
                           ("repository", "noah-be/overte"),
                           ("repository_id", 42), ("repository_id", "1319052603")):
            with self.subTest(key=key, value=value):
                policy = {**self.policy, key: value}
                with self.assertRaises(self.module.CleanupError):
                    self.module.validate_policy(policy)

    def test_permanent_branch_exemptions_cannot_be_weakened(self):
        for name in PERMANENT:
            with self.subTest(removed=name):
                policy = copy.deepcopy(self.policy)
                policy["permanent_branches"].remove(name)
                with self.assertRaises(self.module.CleanupError):
                    self.module.validate_policy(policy)

    def test_backup_retention_cannot_be_changed(self):
        for key, value in (("artifact_retention_days", 0), ("artifact_retention_days", 31)):
            with self.subTest(key=key, value=value):
                with self.assertRaises(self.module.CleanupError):
                    self.module.validate_policy({**self.policy, key: value})

    def test_scope_mapping_uses_the_correct_permanent_target(self):
        scopes = {
            "main": "main", "android": "android-main", "android-main": "android-main",
            "android-phone": "android-phone", "android-vr": "android-vr",
            "android-pico": "android-vr-pico", "apple": "apple-main",
            "ios": "apple-ios",
        }
        for scope, target in scopes.items():
            with self.subTest(scope=scope):
                self.assertEqual(self.module.scope_target(f"task/{scope}/100-work"), target)
        self.assertIsNone(self.module.scope_target("mystery/unknown/work"))

    def test_retired_desktop_scopes_do_not_authorize_automatic_cleanup(self):
        for scope in ("linux", "windows"):
            self.assertIsNone(self.module.scope_target(f"fix/{scope}/old-work"))
        self.assertEqual(self.module.scope_target("fix/main/desktop-work"), "main")

    def test_integrated_current_head_is_eligible_without_an_age_delay(self):
        candidates, _ = self.select()
        self.assertEqual(candidates, [{
            "branch": self.candidate, "sha": self.sha,
            "base": "main", "base_sha": self.base_sha,
        }])

    def test_seven_permanent_branches_are_always_excluded(self):
        comparisons = {
            item["name"]: {"status": "identical", "behind_by": 0,
                           "merge_base_commit": {"sha": item["sha"]}}
            for item in self.branches
        }
        candidates, _ = self.select(comparisons=comparisons)
        self.assertFalse(PERMANENT & {item["branch"] for item in candidates})

    def test_unprotected_permanent_target_stops_all_cleanup(self):
        for row in self.branches:
            if row["name"] == "main":
                row["protected"] = False
        with self.assertRaises(self.module.CleanupError):
            self.select()

    def test_any_additional_currently_protected_branch_is_retained(self):
        self.branches[-1]["protected"] = True
        self.assert_not_eligible()

    def test_every_configured_legacy_hold_is_retained(self):
        branches = self.branches + [
            {"name": branch, "sha": self.sha, "protected": False}
            for branch in self.policy["holds"]
        ]
        comparisons = {
            item["name"]: {"status": "ahead", "behind_by": 0,
                           "merge_base_commit": {"sha": item["sha"]}}
            for item in branches
        }
        candidates, holds = self.select(branches=branches, comparisons=comparisons)
        self.assertFalse(set(self.policy["holds"]) & {item["branch"] for item in candidates})
        self.assertTrue(set(self.policy["holds"]) <= set(holds))

    def test_open_pr_head_base_and_keep_label_holds_exclude_candidates(self):
        for reason in ("open_pr_head", "open_pr_base", "keep_label"):
            with self.subTest(reason=reason):
                candidates, holds = self.select(holds={self.candidate: [reason]})
                self.assertFalse(candidates)
                self.assertIn(self.candidate, holds)

    def test_unmerged_diverged_or_stale_head_proof_cannot_authorize_deletion(self):
        cases = (
            {"status": "behind", "behind_by": 1, "merge_base_commit": {"sha": self.sha}},
            {"status": "diverged", "behind_by": 1, "merge_base_commit": {"sha": "c" * 40}},
            {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": "c" * 40}},
            {"status": "ahead", "behind_by": 1, "merge_base_commit": {"sha": self.sha}},
            {},
        )
        for comparison in cases:
            with self.subTest(comparison=comparison):
                self.assert_not_eligible(comparisons={self.candidate: comparison})

    def test_missing_ancestry_proof_is_not_treated_as_merged(self):
        self.assert_not_eligible(comparisons={})

    def test_missing_protection_status_does_not_mean_unprotected(self):
        del self.branches[-1]["protected"]
        self.assert_not_eligible()

    def test_duplicate_branch_snapshot_is_rejected(self):
        self.branches.append(dict(self.branches[-1]))
        with self.assertRaises(self.module.CleanupError):
            self.select()

    def test_plan_requires_protected_target_history_without_reading_tag_rules(self):
        github = mock.Mock(spec=self.module.Github)
        github.branches.return_value = self.branches
        github.open_pr_holds.return_value = {}
        github.comparisons.return_value = self.comparisons
        github.activity_holds.return_value = {}
        github.workflow_holds.return_value = {}
        github.get.return_value = [{"type": "deletion"}, {"type": "non_fast_forward"}]
        plan = self.module.make_plan(github, self.policy)
        self.assertEqual(plan["candidate_count"], 1)
        github.get.assert_called_once_with("rules/branches/main")
        for rules in ([], [{"type": "deletion"}], [{"type": "non_fast_forward"}]):
            with self.subTest(rules=rules):
                github.get.return_value = rules
                with self.assertRaisesRegex(self.module.CleanupError, "target_history_not_protected"):
                    self.module.make_plan(github, self.policy)


class GithubActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.github = self.module.Github()
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.candidate = {"branch": "task/main/100-integrated", "sha": "a" * 40,
                          "base": "main", "base_sha": "b" * 40}

    def test_open_pr_head_and_base_are_held_only_for_the_authorized_repository(self):
        head, base, foreign = "task/main/head", "task/main/base", "task/main/foreign"
        prs = [
            {"head": {"ref": head, "repo": {"id": 1319052603}},
             "base": {"ref": base, "repo": {"id": 1319052603}}},
            {"head": {"ref": foreign, "repo": {"id": 123}},
             "base": {"ref": "main", "repo": {"id": 1319052603}}},
        ]
        with mock.patch.object(self.github, "get", return_value=prs) as get:
            holds = self.github.open_pr_holds({head, base, foreign})
        self.assertEqual(set(holds), {head, base})
        self.assertIn("state=open", get.call_args.args[0])
        self.assertTrue(get.call_args.kwargs["paginate"])

    def inactive_responses(self, suffix="", paginate=False):
        if suffix.startswith("actions/runs?"):
            return {"total_count": 0, "workflow_runs": []}
        return []

    def test_keep_label_queries_the_current_account_head(self):
        calls = []
        def response(suffix='', paginate=False):
            calls.append(suffix)
            if suffix.startswith('pulls?state=all&head='):
                self.assertIn('head=noah-l-frank%3A', suffix)
                return [{'labels': [{'name': self.policy['keep_label']}]}]
            return self.inactive_responses(suffix, paginate)
        with mock.patch.object(self.github, 'get', side_effect=response):
            holds = self.github.activity_holds([self.candidate], self.policy)
        self.assertIn('keep_branch_label', holds[self.candidate['branch']])
        self.assertEqual(sum(call.startswith('pulls?state=all&head=') for call in calls), 1)

    def active_run(self, **changes):
        return {
            "id": 987,
            "path": ".github/workflows/ios-bootstrap.yml",
            "head_branch": "ci/ios/999-unrelated",
            "head_sha": "c" * 40,
            "pull_requests": [],
            **changes,
        }

    def holds_with_runs(self, runs, candidates=None):
        def response(suffix="", paginate=False):
            if suffix.startswith("actions/runs?status=queued&"):
                return {"total_count": len(runs), "workflow_runs": runs}
            return self.inactive_responses(suffix, paginate)
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "1234"}):
            with mock.patch.object(self.github, "get", side_effect=response):
                return self.github.activity_holds(candidates or [self.candidate], self.policy)

    def test_fresh_plan_releases_ci_hold_after_the_last_related_run_finishes(self):
        branches = [{"name": name, "sha": self.candidate["base_sha"], "protected": True}
                    for name in sorted(PERMANENT)]
        branches.append({"name": self.candidate["branch"], "sha": self.candidate["sha"], "protected": False})
        comparison = {"status": "ahead", "behind_by": 0,
                      "merge_base_commit": {"sha": self.candidate["sha"]}}
        active = [self.active_run(head_branch=self.candidate["base"])]

        def response(suffix="", paginate=False):
            if suffix.startswith("actions/runs?status=in_progress&"):
                return {"total_count": len(active), "workflow_runs": list(active)}
            if suffix == "rules/branches/main":
                return [{"type": "deletion"}, {"type": "non_fast_forward"}]
            return self.inactive_responses(suffix, paginate)

        with mock.patch.object(self.github, "verify_owner"), \
                mock.patch.object(self.github, "branches", return_value=branches), \
                mock.patch.object(self.github, "comparisons", return_value={self.candidate["branch"]: comparison}), \
                mock.patch.object(self.github, "workflow_holds", return_value={}), \
                mock.patch.object(self.github, "get", side_effect=response):
            plan = self.module.make_plan(self.github, self.policy)
            self.assertEqual(plan["candidate_count"], 0)
            self.assertIn("github_actions_still_active", plan["held"][self.candidate["branch"]])
            active.clear()
            plan = self.module.make_plan(self.github, self.policy)
            self.assertEqual(plan["candidates"], [self.candidate])

    def test_active_run_on_candidate_or_intended_base_reserves_the_candidate(self):
        matches = (
            {"head_branch": self.candidate["branch"]},
            {"head_sha": self.candidate["sha"]},
            {"head_branch": self.candidate["base"]},
            {"head_sha": self.candidate["base_sha"]},
        )
        for change in matches:
            with self.subTest(change=change):
                holds = self.holds_with_runs([self.active_run(**change)])
                self.assertIn(self.candidate["branch"], holds)

    def test_unrelated_queued_ios_run_does_not_block_main_branch_cleanup(self):
        run = self.active_run(pull_requests=[{
            "head": {"ref": "ci/ios/999-unrelated", "sha": "c" * 40},
            "base": {"ref": "apple-ios", "sha": "d" * 40},
        }])
        self.assertEqual(self.holds_with_runs([run]), {})

    def test_active_pull_request_run_matches_candidate_and_base_refs_or_shas(self):
        selectors = (
            {"ref": self.candidate["branch"]}, {"sha": self.candidate["sha"]},
            {"ref": self.candidate["base"]}, {"sha": self.candidate["base_sha"]},
        )
        for side in ("head", "base"):
            for selector in selectors:
                with self.subTest(side=side, selector=selector):
                    pr = {
                        "head": {"ref": "ci/ios/999-unrelated", "sha": "c" * 40},
                        "base": {"ref": "apple-ios", "sha": "d" * 40},
                    }
                    pr[side].update(selector)
                    holds = self.holds_with_runs([self.active_run(pull_requests=[pr])])
                    self.assertIn(self.candidate["branch"], holds)

    def test_missing_or_invalid_run_identity_stops_all_cleanup(self):
        other = {"branch": "task/android-phone/999-work", "sha": "e" * 40,
                 "base": "android-phone", "base_sha": "f" * 40}
        variants = (
            ("head_branch", None), ("head_sha", None),
            ("head_branch", ""), ("head_branch", 123), ("head_sha", "not-a-sha"),
        )
        for key, value in variants:
            with self.subTest(key=key, value=value):
                run = self.active_run()
                if value is None:
                    del run[key]
                else:
                    run[key] = value
                with self.assertRaises(self.module.CleanupError):
                    self.holds_with_runs([run], [self.candidate, other])

    def test_keep_label_on_a_closed_or_merged_pr_still_reserves_the_branch(self):
        def response(suffix="", paginate=False):
            if suffix.startswith("pulls?state=all&head="):
                return [{"state": "closed", "labels": [{"name": "keep-branch"}]}]
            return self.inactive_responses(suffix, paginate)
        with mock.patch.object(self.github, "get", side_effect=response):
            holds = self.github.activity_holds([self.candidate], self.policy)
        self.assertIn(self.candidate["branch"], holds)

    def test_incomplete_active_run_inventory_fails_closed(self):
        def response(suffix="", paginate=False):
            if suffix.startswith("actions/runs?"):
                return {"total_count": 2, "workflow_runs": []}
            return []
        with mock.patch.object(self.github, "get", side_effect=response) as get, \
                mock.patch.object(self.module.time, "sleep") as sleep:
            with self.assertRaisesRegex(self.module.CleanupError, "active_run_listing_incomplete"):
                self.github.activity_holds([self.candidate], self.policy)
        self.assertEqual(sleep.call_args_list, [mock.call(2), mock.call(5), mock.call(10)])
        self.assertEqual(sum(call.args[0].startswith("actions/runs?") for call in get.call_args_list), 20)

    def test_transient_inventory_mismatch_reloads_all_states_and_honors_new_activity(self):
        for running in (False, True):
            with self.subTest(running=running):
                attempts = []
                active = [self.active_run(head_branch=self.candidate["branch"])] if running else []

                def response(suffix="", paginate=False):
                    if suffix.startswith("actions/runs?status=queued&"):
                        attempts.append(suffix)
                        return {"total_count": 1, "workflow_runs": []} if len(attempts) < 3 else {
                            "total_count": len(active), "workflow_runs": active}
                    return self.inactive_responses(suffix, paginate)

                with mock.patch.object(self.github, "get", side_effect=response) as get, \
                        mock.patch.object(self.module.time, "sleep") as sleep:
                    held = self.github.activity_holds([self.candidate], self.policy)
                self.assertEqual(sleep.call_args_list, [mock.call(2), mock.call(5)])
                self.assertEqual(sum(call.args[0].startswith("actions/runs?") for call in get.call_args_list), 15)
                self.assertEqual(self.candidate["branch"] in held, running)
                if running:
                    self.assertIn("github_actions_still_active", held[self.candidate["branch"]])

    def test_missing_active_run_inventory_fields_fail_closed(self):
        for invalid in ({}, {"total_count": True, "workflow_runs": []},
                        {"total_count": -1, "workflow_runs": []},
                        {"total_count": "0", "workflow_runs": []},
                        {"total_count": 0, "workflow_runs": None}):
            with self.subTest(invalid=invalid):
                def response(suffix="", paginate=False):
                    return invalid if suffix.startswith("actions/runs?") else []
                with mock.patch.object(self.github, "get", side_effect=response), \
                        mock.patch.object(self.module.time, "sleep") as sleep:
                    with self.assertRaisesRegex(self.module.CleanupError, "active_run_listing_invalid"):
                        self.github.activity_holds([self.candidate], self.policy)
                sleep.assert_not_called()

    def test_github_api_requests_are_read_only_and_explicitly_bound_to_the_fork(self):
        result = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        with mock.patch.object(self.module, "run", return_value=result) as run:
            self.github.get("branches?per_page=100")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["gh", "api", "--method", "GET"])
        self.assertEqual(command[4], "repos/noah-l-frank/overte/branches?per_page=100")
        for suffix in ("/repos/overte-org/overte", "https://github.com/overte-org/overte", "../overte"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(self.module.CleanupError):
                    self.github.get(suffix)

    def test_safe_github_compare_syntax_is_not_mistaken_for_path_traversal(self):
        endpoint = "compare/" + "a" * 40 + "..." + "b" * 40 + "?per_page=1"
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with mock.patch.object(self.module, "run", return_value=result) as run:
            self.github.get(endpoint)
        self.assertEqual(run.call_args.args[0][4], "repos/noah-l-frank/overte/" + endpoint)

    def test_foreign_owner_or_native_unguarded_cleanup_is_rejected(self):
        valid = {"full_name": FORK, "id": 1319052603, "default_branch": "main", "delete_branch_on_merge": False}
        for change in ({"full_name": "overte-org/overte"}, {"full_name": "noah-be/overte"},
                       {"id": 42}, {"delete_branch_on_merge": True}):
            with self.subTest(change=change):
                with mock.patch.object(self.github, "get", return_value={**valid, **change}):
                    with self.assertRaises(self.module.CleanupError):
                        self.github.verify_owner()


class GithubReleaseReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.github = self.module.Github()
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.candidate = {"branch": "task/main/100-integrated", "sha": "a" * 40,
                          "base": "main", "base_sha": "b" * 40}
        self.release = {"target_commitish": self.candidate["sha"], "tag_name": "release-v1+2"}
        self.reference = {"ref": "refs/tags/release-v1+2",
                          "object": {"type": "commit", "sha": self.candidate["sha"]}}
        self.annotations = {}
        self.deployments = []

    def response(self, suffix="", paginate=False):
        if suffix == "releases?per_page=100":
            return [self.release]
        if suffix == "deployments?per_page=100":
            return self.deployments
        if suffix == "git/ref/tags/release-v1%2B2":
            return self.reference
        if suffix.startswith("git/tags/"):
            return self.annotations[suffix.removeprefix("git/tags/")]
        if suffix.startswith("git/"):
            raise AssertionError("unexpected Git object endpoint")
        return GithubActivityTests.inactive_responses(self, suffix, paginate)

    def holds(self):
        with mock.patch.object(self.github, "get", side_effect=self.response):
            return self.github.activity_holds([self.candidate], self.policy)

    def assert_release_hold(self):
        self.assertIn("release_reference", self.holds()[self.candidate["branch"]])

    def test_lightweight_release_tag_retains_the_exact_integrated_commit(self):
        self.assertEqual(self.holds(), {})

    def test_annotated_and_nested_tags_use_only_fork_object_endpoints(self):
        first, second = "c" * 40, "d" * 40
        self.reference["object"] = {"type": "tag", "sha": first,
                                    "url": "https://api.github.com/repos/overte-org/overte/git/tags/" + first}
        self.annotations[first] = {"sha": first, "object": {"type": "tag", "sha": second}}
        self.annotations[second] = {"sha": second, "object": {"type": "commit", "sha": self.candidate["sha"]}}
        with mock.patch.object(self.github, "get", side_effect=self.response) as get:
            self.assertEqual(self.github.activity_holds([self.candidate], self.policy), {})
        object_calls = [call.args[0] for call in get.call_args_list if call.args[0].startswith("git/")]
        self.assertEqual(object_calls, ["git/ref/tags/release-v1%2B2", "git/tags/" + first, "git/tags/" + second])

    def test_different_tag_commit_keeps_release_hold(self):
        self.reference["object"]["sha"] = "c" * 40
        self.assert_release_hold()

    def test_named_branch_release_keeps_hold_without_tag_lookup(self):
        for target in (self.candidate["branch"], "refs/heads/" + self.candidate["branch"]):
            with self.subTest(target=target):
                self.release["target_commitish"] = target
                with mock.patch.object(self.github, "release_tag_commit") as resolve:
                    self.assert_release_hold()
                resolve.assert_not_called()

    def test_deployment_hold_is_not_removed_by_release_tag_evidence(self):
        self.deployments = [{"ref": self.candidate["sha"]}]
        self.assertEqual(self.holds(), {self.candidate["branch"]: ["deployment_reference"]})

    def test_missing_or_invalid_tag_names_keep_hold_without_api_lookup(self):
        for name in (None, "", "../other", "bad name", "refs/../other", 42):
            with self.subTest(name=name):
                self.release["tag_name"] = name
                with mock.patch.object(self.github, "get", side_effect=self.response) as get:
                    holds = self.github.activity_holds([self.candidate], self.policy)
                self.assertIn("release_reference", holds[self.candidate["branch"]])
                self.assertFalse(any(call.args[0].startswith("git/") for call in get.call_args_list))

    def test_unavailable_tag_api_aborts_assessment(self):
        def response(suffix="", paginate=False):
            if suffix.startswith("git/"):
                raise self.module.CleanupError("tag API unavailable")
            return self.response(suffix, paginate)
        with mock.patch.object(self.github, "get", side_effect=response):
            with self.assertRaises(self.module.CleanupError):
                self.github.activity_holds([self.candidate], self.policy)

    def test_malformed_or_mismatched_tag_metadata_keeps_hold(self):
        cases = (
            None, [], {},
            {"ref": "refs/tags/another", "object": {"type": "commit", "sha": self.candidate["sha"]}},
            {"ref": "refs/tags/release-v1+2", "object": None},
            {"ref": "refs/tags/release-v1+2", "object": {"type": "blob", "sha": self.candidate["sha"]}},
            {"ref": "refs/tags/release-v1+2", "object": {"type": "commit", "sha": "invalid"}},
        )
        for reference in cases:
            with self.subTest(reference=reference):
                self.reference = reference
                self.assert_release_hold()

    def test_annotation_identity_must_match_requested_object(self):
        oid = "c" * 40
        self.reference["object"] = {"type": "tag", "sha": oid}
        self.annotations[oid] = {"sha": "d" * 40, "object": {"type": "commit", "sha": self.candidate["sha"]}}
        self.assert_release_hold()

    def test_annotation_cycles_and_excessive_depth_keep_hold(self):
        first = "c" * 40
        self.reference["object"] = {"type": "tag", "sha": first}
        self.annotations[first] = {"sha": first, "object": {"type": "tag", "sha": first}}
        self.assert_release_hold()
        oids = [f"{index:040x}" for index in range(1, 10)]
        self.reference["object"] = {"type": "tag", "sha": oids[0]}
        self.annotations = {oid: {"sha": oid, "object": {"type": "tag", "sha": next_oid}}
                            for oid, next_oid in zip(oids, oids[1:])}
        with mock.patch.object(self.github, "get", side_effect=self.response) as get:
            holds = self.github.activity_holds([self.candidate], self.policy)
        self.assertIn("release_reference", holds[self.candidate["branch"]])
        self.assertEqual(sum(call.args[0].startswith("git/tags/") for call in get.call_args_list), 8)

    def test_moved_tag_is_rechecked_on_next_assessment(self):
        self.assertEqual(self.holds(), {})
        self.reference["object"]["sha"] = "c" * 40
        self.assert_release_hold()

    def test_release_exception_still_requires_full_ancestry_and_target_history_protection(self):
        branches = [{"name": name, "sha": self.candidate["base_sha"], "protected": True}
                    for name in sorted(PERMANENT)]
        branches.append({"name": self.candidate["branch"], "sha": self.candidate["sha"], "protected": False})
        comparison = {"status": "ahead", "behind_by": 0,
                      "merge_base_commit": {"sha": self.candidate["sha"]}}
        rules = [{"type": "deletion"}, {"type": "non_fast_forward"}]

        def response(suffix="", paginate=False):
            return rules if suffix == "rules/branches/main" else self.response(suffix, paginate)

        with mock.patch.object(self.github, "verify_owner"), \
                mock.patch.object(self.github, "branches", return_value=branches), \
                mock.patch.object(self.github, "comparisons", return_value={self.candidate["branch"]: comparison}), \
                mock.patch.object(self.github, "workflow_holds", return_value={}), \
                mock.patch.object(self.github, "get", side_effect=response):
            self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 1)
            for incomplete in ([], [{"type": "deletion"}], [{"type": "non_fast_forward"}]):
                rules = incomplete
                with self.assertRaisesRegex(self.module.CleanupError, "target_history_not_protected"):
                    self.module.make_plan(self.github, self.policy)
            rules = [{"type": "deletion"}, {"type": "non_fast_forward"}]
            comparison["merge_base_commit"] = {"sha": "c" * 40}
            self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)


class GithubWorkflowReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.github = self.module.Github()
        self.name = "task/main/100-integrated"
        self.candidates = [{"branch": self.name, "sha": "a" * 40, "base": "main", "base_sha": "b" * 40}]
        self.branches = [{"name": branch, "sha": f"{index:040x}", "protected": True}
                         for index, branch in enumerate(sorted(PERMANENT), 1)]
        self.path = ".github/workflows/example.yml"

    def responses(self, content):
        raw = content.encode("utf-8")
        oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False).hexdigest()
        entry = {"type": "file", "path": self.path, "sha": oid, "name": "example.yml"}
        file = {**entry, "encoding": "base64", "content": base64.encodebytes(raw).decode("ascii")}

        def response(endpoint):
            if endpoint.startswith("contents/.github/workflows?"):
                return [entry]
            if endpoint.startswith("contents/" + self.path + "?"):
                return file
            raise AssertionError("unexpected workflow API endpoint")

        return response

    def test_no_candidates_does_not_read_repository_workflows(self):
        with mock.patch.object(self.github, "get") as get:
            self.assertEqual(self.github.workflow_holds([], self.branches), {})
        get.assert_not_called()

    def test_plain_and_urlencoded_references_reserve_branch_without_returning_file_contents(self):
        for reference in (self.name, self.name.replace("/", "%2F")):
            with self.subTest(reference=reference):
                content = "# synthetic-private-marker\nname: Example\nref: " + reference + "\n"
                with mock.patch.object(self.github, "get", side_effect=self.responses(content)) as get:
                    holds = self.github.workflow_holds(self.candidates, self.branches)
                self.assertIn(self.name, holds)
                self.assertNotIn("synthetic-private-marker", json.dumps(holds))
                allowed_refs = {row["sha"] for row in self.branches}
                for call in get.call_args_list:
                    self.assertIn("?ref=", call.args[0])
                    self.assertIn(call.args[0].split("?ref=", 1)[1], allowed_refs)

    def test_nonreferencing_workflow_does_not_create_a_hold(self):
        with mock.patch.object(self.github, "get", side_effect=self.responses("name: unrelated\n")):
            self.assertEqual(self.github.workflow_holds(self.candidates, self.branches), {})

    def test_unknown_directory_and_corrupt_file_payloads_fail_closed(self):
        good = self.responses("ref: " + self.name + "\n")
        variants = ("directory_object", "symlink", "bad_base64", "wrong_hash", "wrong_path")
        for variant in variants:
            def response(endpoint, variant=variant):
                result = copy.deepcopy(good(endpoint))
                if "workflows?" in endpoint:
                    if variant == "directory_object":
                        return {}
                    if variant == "symlink":
                        result[0]["type"] = "symlink"
                elif variant == "bad_base64":
                    result["content"] = "!not base64!"
                elif variant == "wrong_hash":
                    result["content"] = base64.b64encode(b"unrelated content").decode()
                elif variant == "wrong_path":
                    result["path"] = ".github/workflows/different.yml"
                return result
            with self.subTest(variant=variant):
                with mock.patch.object(self.github, "get", side_effect=response):
                    with self.assertRaises(self.module.CleanupError):
                        self.github.workflow_holds(self.candidates, self.branches)


class ImmutableApiCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cleanup-immutable-cache-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.module.ImmutableReadCache(self.root, "123", "1")
        self.github = self.client()
        self.path = ".github/workflows/example.yml"
        self.revision = "a" * 40
        self.contents = "contents/" + self.path + "?ref=" + self.revision
        self.compare = "compare/" + "b" * 40 + "..." + "c" * 40 + "?per_page=1"
        self.integrated = {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": "b" * 40}}
        self.unmerged = {"status": "diverged", "behind_by": 1, "merge_base_commit": {"sha": "d" * 40}}
        self.content = self.file("ref: task/main/retained\n")
        self.responses, self.calls = {}, []
        self.real_run = self.module.run
        context = mock.patch.object(self.module, "run", side_effect=self.response)
        context.start(); self.addCleanup(context.stop)

    def client(self, cache=None):
        client = self.module.Github()
        client.cache = cache or self.cache
        client.cache_checked = True
        client._cache_statistics["state"] = "enabled"
        return client

    def file(self, source):
        raw = source.encode()
        return {"type": "file", "path": ".github/workflows/example.yml",
                "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                "encoding": "base64", "content": base64.b64encode(raw).decode(), "size": len(raw)}

    def response(self, command, **kwargs):
        if command[:2] == ["git", "check-ref-format"]:
            return self.real_run(command, **kwargs)
        self.assertEqual(command[:4], ["gh", "api", "--method", "GET"])
        prefix = "repos/" + FORK
        self.assertTrue(command[4] == prefix or command[4].startswith(prefix + "/"))
        endpoint = command[4][len(prefix):].removeprefix("/")
        self.calls.append(endpoint)
        value = self.responses[endpoint]
        if isinstance(value, BaseException):
            raise value
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(value), stderr="")

    def entry(self, endpoint):
        request = self.cache.request(endpoint, False)
        return self.cache.directory / (hashlib.sha256(self.cache.canonical(request)).hexdigest() + ".json")

    def test_same_sha_reuses_disk_across_clients_but_new_sha_path_and_compare_pair_refetch(self):
        alternate = "contents/.github/workflows/other.yml?ref=" + self.revision
        other_file = {**self.content, "path": ".github/workflows/other.yml"}
        changed = self.contents.replace(self.revision, "d" * 40)
        new_pair = self.compare.replace("c" * 40, "e" * 40)
        self.responses = {self.contents: self.content, changed: self.content, alternate: other_file,
                          self.compare: self.integrated, new_pair: self.integrated}
        for endpoint in self.responses:
            expected = self.github.get(endpoint)
            fresh = self.client(self.module.ImmutableReadCache(self.root, "123", "1"))
            self.assertEqual(fresh.get(endpoint), expected)
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(set(self.calls), set(self.responses))

    def test_mutable_owner_refs_activity_rules_and_paginated_requests_are_always_fresh(self):
        mutable = ("", "branches?per_page=100", "git/ref/tags/release", "pulls?state=open",
                   "actions/runs?status=queued", "rules/branches/main", "deployments", "releases",
                   "contents/.github/workflows?ref=main", "compare/main...feature?per_page=1")
        self.responses = {endpoint: {} for endpoint in mutable}
        for endpoint in mutable:
            self.github.get(endpoint); self.github.get(endpoint)
            self.assertEqual(self.calls.count(endpoint), 2)
        self.responses[self.contents] = [[self.content]]
        self.github.get(self.contents, paginate=True); self.github.get(self.contents, paginate=True)
        self.assertEqual(self.calls.count(self.contents), 2)
        self.assertEqual(list(self.cache.directory.iterdir()), [])

    def test_immutable_reads_never_cache_or_return_mutable_user_urls_or_permission_metadata(self):
        compare = {**self.integrated, "base_commit": {"author": {"login": "mutable-user"}}, "permissions": {"admin": True}}
        content = {**self.content, "download_url": "mutable-url", "permissions": {"admin": True}}
        self.responses = {self.compare: compare, self.contents: content}
        for endpoint, expected in ((self.compare, self.integrated), (self.contents, self.content)):
            self.assertEqual(self.github.get(endpoint), expected)
            self.assertEqual(self.client().get(endpoint), expected)
            source = self.entry(endpoint).read_text()
            for mutable in ("permissions", "mutable-user", "mutable-url"):
                self.assertNotIn(mutable, source)
        self.assertEqual(len(self.calls), 2)

    def test_fresh_owner_setting_can_block_after_cached_immutable_reads(self):
        self.responses[self.compare] = self.integrated
        self.github.get(self.compare)
        self.responses[""] = {"full_name": FORK, "id": 1319052603, "default_branch": "main", "delete_branch_on_merge": False}
        self.github.verify_owner()
        self.responses[""]["delete_branch_on_merge"] = True
        with self.assertRaisesRegex(self.module.CleanupError, "native_cleanup"):
            self.github.verify_owner()
        self.assertEqual(self.calls.count(""), 2)

    def test_workflow_passes_share_only_immutable_reads_and_changed_heads_refetch(self):
        branches = [{"name": name, "sha": str(index) * 40} for index, name in enumerate(sorted(PERMANENT), 1)]
        directory = [{key: self.content[key] for key in ("type", "path", "sha")}]
        for branch in branches:
            self.responses["contents/.github/workflows?ref=" + branch["sha"]] = directory
            self.responses["contents/" + self.path + "?ref=" + branch["sha"]] = self.content
        candidates = [{"branch": "task/main/retained"}]
        first = self.github.workflow_holds(candidates, branches)
        self.assertIn("task/main/retained", first)
        self.assertEqual(len(self.calls), 8)  # Seven directories, one shared exact blob.
        self.assertEqual(self.client().workflow_holds(candidates, branches), first)
        self.assertEqual(len(self.calls), 8)
        branches[0]["sha"] = "f" * 40
        self.responses["contents/.github/workflows?ref=" + "f" * 40] = directory
        self.responses["contents/" + self.path + "?ref=" + "f" * 40] = self.content
        self.assertEqual(self.github.workflow_holds(candidates, branches), first)
        self.assertEqual(len(self.calls), 10)

    def test_corrupt_workflow_directory_cannot_remove_a_live_hold(self):
        branch_sha = "e" * 40
        directory = "contents/.github/workflows?ref=" + branch_sha
        self.responses = {directory: [{key: self.content[key] for key in ("type", "path", "sha")}],
                          self.contents.replace(self.revision, branch_sha): self.content}
        branches = [{"name": name, "sha": branch_sha} for name in PERMANENT]
        candidates = [{"branch": "task/main/retained"}]
        self.assertIn("task/main/retained", self.github.workflow_holds(candidates, branches))
        path = self.entry(directory)
        value = json.loads(path.read_text()); value["value"] = []
        path.write_text(json.dumps(value))  # Its old digest cannot certify an omitted workflow.
        self.assertIn("task/main/retained", self.client().workflow_holds(candidates, branches))
        self.assertEqual(self.calls.count(directory), 2)

    def test_corrupt_integration_result_refetches_and_cannot_select_unmerged_work(self):
        self.responses[self.compare] = self.integrated
        self.github.get(self.compare)
        path = self.entry(self.compare)
        envelope = json.loads(path.read_text()); envelope["value"]["behind_by"] = 99
        path.write_text(json.dumps(envelope))
        self.responses[self.compare] = self.unmerged
        branches = [{"name": name, "sha": "c" * 40, "protected": True} for name in PERMANENT]
        branches += [{"name": "task/main/not-integrated", "sha": "b" * 40, "protected": False}]
        policy = json.loads(POLICY_PATH.read_text())
        comparisons = self.client().comparisons(branches, policy, {})
        selected, held = self.module.select_candidates(branches, policy, comparisons)
        self.assertEqual(selected, [])
        self.assertIn("not_fully_integrated", held["task/main/not-integrated"])
        self.assertEqual(self.calls.count(self.compare), 2)

    def test_missing_api_or_invalid_fresh_blob_never_becomes_a_successful_cache_entry(self):
        for value in (self.module.CleanupError("synthetic_api_failure"),
                      {**self.content, "content": base64.b64encode(b"omitted hold").decode()}):
            self.responses[self.contents] = value
            for _ in range(2):
                with self.assertRaises(self.module.CleanupError): self.github.get(self.contents)
            self.assertFalse(self.entry(self.contents).exists())
        self.assertEqual(self.calls.count(self.contents), 4)

    def test_corrupt_entries_refetch_and_failed_refetch_stays_fatal(self):
        self.responses[self.compare] = self.integrated
        self.github.get(self.compare)
        path = self.entry(self.compare)
        original = path.read_bytes()
        for data in (b"not json", b'{"schema":1,"schema":1}', original.replace(b'"123"', b'"999"'),
                     b"x" * (self.cache.MAX_ENTRY + 1)):
            path.write_bytes(data)
            self.assertEqual(self.client().get(self.compare), self.integrated)
        path.write_text("damaged")
        self.responses[self.compare] = self.module.CleanupError("rate_limited")
        with self.assertRaisesRegex(self.module.CleanupError, "rate_limited"):
            self.client().get(self.compare)

    def test_cache_symlink_hardlink_and_public_entry_are_refetched_without_following(self):
        self.responses[self.compare] = self.integrated
        self.github.get(self.compare)
        path = self.entry(self.compare)
        outside = self.root / "protected.json"
        outside.write_text("outside marker")
        path.unlink(); path.symlink_to(outside)
        self.assertEqual(self.client().get(self.compare), self.integrated)
        self.assertEqual(outside.read_text(), "outside marker")
        path.unlink(); os.link(outside, path)
        self.assertEqual(self.client().get(self.compare), self.integrated)
        self.assertEqual(outside.read_text(), "outside marker")
        path.chmod(0o644)
        self.assertEqual(self.client().get(self.compare), self.integrated)
        self.assertEqual(self.calls.count(self.compare), 4)

    def test_private_root_and_attempt_are_mandatory_and_new_attempt_does_not_reuse(self):
        self.responses[self.compare] = self.integrated
        self.github.get(self.compare)
        other = self.module.ImmutableReadCache(self.root, "123", "2")
        self.assertEqual(self.client(other).get(self.compare), self.integrated)
        self.assertEqual(len(self.calls), 2)
        alias = self.root / "alias"; alias.symlink_to(self.root, target_is_directory=True)
        for root, run, attempt in ((alias, "123", "1"), (self.root, "main", "1"), (self.root, "123", "0")):
            with self.assertRaises(self.module.CleanupError): self.module.ImmutableReadCache(root, run, attempt)
        self.cache.directory.chmod(0o755)
        with self.assertRaises(self.module.CleanupError): self.module.ImmutableReadCache(self.root, "123", "1")
        before = len(self.calls)
        with self.assertRaises(self.module.CleanupError): self.github.get(self.compare)
        self.assertEqual(len(self.calls), before)

    def test_cache_bounds_fall_back_to_fresh_observations(self):
        self.responses[self.compare] = self.integrated
        self.cache.MAX_ENTRY = 10
        self.assertEqual(self.github.get(self.compare), self.integrated)
        self.assertEqual(self.github.get(self.compare), self.integrated)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.entry(self.compare).exists())

    def test_private_cache_below_trusted_sticky_temp_retains_real_cache_hits(self):
        shared = self.root / "sticky-temp"
        shared.mkdir()
        shared.chmod(0o1777)
        private = shared / "private-runner-temp"
        private.mkdir(mode=0o700)
        cache = self.module.ImmutableReadCache(private, "123", "1")
        self.responses[self.compare] = self.integrated
        client = self.client(cache)
        self.assertEqual(client.get(self.compare), self.integrated)
        self.assertEqual(client.get(self.compare), self.integrated)
        self.assertEqual(self.calls, [self.compare])
        self.assertEqual(stat.S_IMODE(cache.directory.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600
                            for path in cache.directory.iterdir()))

    def test_shared_writable_nonsticky_ancestors_remain_rejected(self):
        shared = self.root / "unprotected-temp"
        shared.mkdir()
        private = shared / "private-runner-temp"
        private.mkdir(mode=0o700)
        for mode in (0o777, 0o770):
            shared.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(
                    self.module.CleanupError, "unsafe_immutable_cache_ancestor"):
                self.module.ImmutableReadCache(private, "123", "1")

    def test_sticky_ancestor_does_not_allow_an_aliased_descendant(self):
        shared = self.root / "sticky-temp"
        shared.mkdir()
        shared.chmod(0o1777)
        alias = shared / "aliased-private"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(self.module.CleanupError, "unsafe_immutable_cache_ancestor"):
            self.module.ImmutableReadCache(alias, "123", "1")

    def test_opt_in_requires_exact_trusted_runner_context_and_default_is_disabled(self):
        self.responses[self.compare] = self.integrated
        with mock.patch.dict(os.environ, {"BRANCH_CLEANUP_IMMUTABLE_CACHE": ""}):
            ordinary = self.module.Github()
            ordinary.get(self.compare); ordinary.get(self.compare)
            self.assertIsNone(ordinary.cache)
        context = {"BRANCH_CLEANUP_IMMUTABLE_CACHE": "1", "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": FORK, "GITHUB_REPOSITORY_ID": "1319052603", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "RUNNER_TEMP": str(self.root), "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_WORKFLOW_REF": FORK + "/.github/workflows/branch-cleanup.yml@refs/heads/main"}
        with mock.patch.dict(os.environ, context):
            trusted = self.module.Github(); trusted.get(self.compare); trusted.get(self.compare)
            self.assertIsNotNone(trusted.cache)
            with mock.patch.dict(os.environ, {"GITHUB_WORKFLOW_REF": "foreign"}), self.assertRaises(self.module.CleanupError):
                self.module.Github().get(self.compare)
        self.assertEqual(len(self.calls), 3)

    def test_unavailable_optional_cache_keeps_fresh_original_api_and_failures(self):
        self.responses[self.compare] = self.integrated
        context = {"BRANCH_CLEANUP_IMMUTABLE_CACHE": "1", "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": FORK, "GITHUB_REPOSITORY_ID": "1319052603", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "RUNNER_TEMP": str(self.root), "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_WORKFLOW_REF": FORK + "/.github/workflows/branch-cleanup.yml@refs/heads/main"}
        self.cache.directory.chmod(0o755)
        with mock.patch.dict(os.environ, context):
            github = self.module.Github()
            self.assertEqual(github.get(self.compare), self.integrated)
            self.assertIsNone(github.cache)
            self.responses[self.compare] = self.unmerged
            self.assertEqual(github.get(self.compare), self.unmerged)
            self.responses[self.compare] = self.module.CleanupError("rate_limited")
            with self.assertRaisesRegex(self.module.CleanupError, "rate_limited"): github.get(self.compare)
        self.assertEqual(self.calls.count(self.compare), 3)
        self.assertEqual(github.cache_statistics(), {"state": "unavailable", "hits": 0, "misses": 0,
            "fresh_api_invocations": {"contents": 0, "compare": 3, "other": 0}})

    def test_public_git_encoding_ignores_ambient_config_and_writes_no_objects(self):
        raw = b"public fixed workflow source\n"
        before = set(self.root.iterdir())
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "extensions.objectFormat",
                                         "GIT_CONFIG_VALUE_0": "sha256", "GIT_DIR": str(self.root / "not-a-repository")}):
            value = self.cache.blob_identity(raw)
        self.assertEqual(value, hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())
        self.assertEqual(set(self.root.iterdir()), before)

    def test_telemetry_counts_cache_outcomes_and_cli_invocations_without_http_page_claims(self):
        self.responses = {self.compare: self.integrated, self.contents: self.content,
                          "branches?per_page=100": [[1], [2]]}
        for endpoint in (self.compare, self.contents):
            self.github.get(endpoint); self.github.get(endpoint)
        self.assertEqual(self.github.get("branches?per_page=100", paginate=True), [1, 2])
        expected = {"state": "enabled", "hits": 2, "misses": 2,
                    "fresh_api_invocations": {"contents": 1, "compare": 1, "other": 1}}
        self.assertEqual(self.github.cache_statistics(), expected)
        modified = self.github.cache_statistics()
        modified["fresh_api_invocations"]["compare"] = 999
        self.assertEqual(self.github.cache_statistics(), expected)
        self.responses[self.compare] = self.module.CleanupError("synthetic_failure")
        with mock.patch.dict(os.environ, {"BRANCH_CLEANUP_IMMUTABLE_CACHE": ""}):
            ordinary = self.module.Github()
            with self.assertRaises(self.module.CleanupError): ordinary.get(self.compare)
        self.assertEqual(ordinary.cache_statistics(), {"state": "disabled", "hits": 0, "misses": 0,
            "fresh_api_invocations": {"contents": 0, "compare": 1, "other": 0}})


class GitBackupsAndDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-branch-cleanup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = LocalGitFixture(Path(self.temporary.name))
        self.events = []
        self.github = FakeGithubOwner(self.events)
        transport = OfflineGitTransport(self.fixture, self.events, self.module.CleanupError)
        patch = mock.patch.object(self.module, "run", side_effect=transport)
        patch.start()
        self.addCleanup(patch.stop)
        self.store_dir = self.fixture.root / "cleanup.git"
        self.store = self.module.GitStore(self.store_dir)
        self.candidates = [{
            "branch": self.fixture.merged_branch,
            "sha": self.fixture.merged_sha,
            "base": "main", "base_sha": self.fixture.main_sha,
        }]
        self.store.fetch(self.candidates)

    def pushes(self):
        return [event[2] for event in self.events if event[:2] == ("git", "push")]

    def assert_branch_exists(self, sha=None):
        self.assertEqual(
            self.fixture.remote_ref("refs/heads/" + self.fixture.merged_branch),
            sha or self.fixture.merged_sha,
        )

    def test_exact_leased_deletion_creates_no_tags_and_preserves_existing_tags(self):
        self.fixture.git(self.fixture.remote, "tag", "-a", "existing-release",
                         self.fixture.initial, "-m", "Existing release")
        before = self.fixture.git(self.fixture.remote, "show-ref", "--tags").stdout
        deleted = self.store.delete(self.candidates, self.github)
        self.assertEqual(deleted, [self.fixture.merged_branch])
        self.assertIsNone(self.fixture.remote_ref("refs/heads/" + self.fixture.merged_branch))
        self.assertEqual(self.fixture.git(self.fixture.remote, "show-ref", "--tags").stdout, before)
        self.assertEqual(len(self.pushes()), 1)
        delete_push = self.pushes()[0]
        self.assertIn("--atomic", delete_push)
        self.assertIn(
            "--force-with-lease=refs/heads/" + self.fixture.merged_branch + ":" + self.fixture.merged_sha,
            delete_push,
        )
        self.assertFalse(any("refs/tags/" in value for value in delete_push))

    def test_owner_is_reverified_before_every_mutating_push(self):
        self.store.delete(self.candidates, self.github)
        previous_push = -1
        push_count = 0
        for index, event in enumerate(self.events):
            if event[:2] != ("git", "push"):
                continue
            push_count += 1
            self.assertIn(("verify_owner",), self.events[previous_push + 1:index])
            self.assertTrue("cleanup" in event[2] or FORK_URL in event[2])
            previous_push = index
        self.assertEqual(push_count, 1)

    def test_concurrent_new_work_is_preserved_by_the_real_remote_lease(self):
        new_sha = self.fixture.advance_remote_branch(self.fixture.merged_branch)
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assert_branch_exists(new_sha)

    def test_effective_push_url_rewrite_to_upstream_is_rejected(self):
        self.store.git("config", "url.https://github.com/overte-org/overte.git.pushInsteadOf", FORK_URL)
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_push_url_change_after_backup_is_rejected_before_delete(self):
        before = len(self.pushes())
        self.store.git("remote", "set-url", "--push", "cleanup", "https://github.com/overte-org/overte.git")
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assertEqual(len(self.pushes()), before)
        self.assert_branch_exists()

    def test_verified_bundle_can_restore_the_candidate_without_the_remote(self):
        bundle = self.fixture.root / "recovery.bundle"
        self.module.create_bundle(self.store_dir, self.candidates, bundle)
        restore = self.fixture.root / "restored.git"
        result = self.module.verify_bundle(bundle, self.candidates, restore)
        self.assertIsInstance(result, dict)
        self.assertEqual(self.fixture.git(restore, "show", self.fixture.merged_sha + ":integrated.txt").stdout,
                         "integrated.txt\n")
        self.fixture.git(restore, "fsck", "--full", "--strict")
        self.assertFalse(self.pushes())

    def test_corrupt_bundle_is_rejected_and_leaves_the_remote_branch_intact(self):
        bundle = self.fixture.root / "recovery.bundle"
        self.module.create_bundle(self.store_dir, self.candidates, bundle)
        data = bytearray(bundle.read_bytes())
        data[-12] ^= 1
        bundle.write_bytes(data)
        with self.assertRaises(self.module.CleanupError):
            self.module.verify_bundle(bundle, self.candidates, self.fixture.root / "corrupt-restore.git")
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_failed_bundle_creation_cannot_delete_a_branch(self):
        bundle = self.fixture.root / "unwritable.bundle"
        bundle.mkdir()
        with self.assertRaises(self.module.CleanupError):
            self.module.create_bundle(self.store_dir, self.candidates, bundle)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_bundle_with_wrong_candidate_sha_is_rejected(self):
        bundle = self.fixture.root / "recovery.bundle"
        self.module.create_bundle(self.store_dir, self.candidates, bundle)
        wrong = [{**self.candidates[0], "sha": self.fixture.unmerged_sha}]
        with self.assertRaises(self.module.CleanupError):
            self.module.verify_bundle(bundle, wrong, self.fixture.root / "wrong-restore.git")
        self.assert_branch_exists()

    def test_rerun_after_deletion_is_a_noop(self):
        self.store.delete(self.candidates, self.github)
        branches = [{"name": branch, "sha": self.fixture.rev(self.fixture.remote, branch), "protected": True}
                    for branch in sorted(PERMANENT)]
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        candidates, _ = self.module.select_candidates(branches, policy, {})
        self.assertFalse(candidates)
        before = len(self.pushes())
        self.assertEqual(self.store.delete(candidates, self.github), [])
        self.assertEqual(len(self.pushes()), before)

    def test_two_branch_names_at_the_same_commit_are_deleted_atomically(self):
        alias = "fix/main/integrated-alias"
        self.fixture.git(self.fixture.seed, "branch", alias, self.fixture.merged_sha)
        self.fixture.git(self.fixture.seed, "push", "-q", "fixture", f"refs/heads/{alias}:refs/heads/{alias}")
        candidates = self.candidates + [{**self.candidates[0], "branch": alias}]
        self.store.fetch(candidates)
        self.assertEqual(set(self.store.delete(candidates, self.github)), {self.fixture.merged_branch, alias})
        self.assertIsNone(self.fixture.remote_ref("refs/heads/" + alias))

    def test_incremental_bundle_requiring_missing_history_is_rejected(self):
        bundle = self.fixture.root / "incremental.bundle"
        self.store.git("bundle", "create", str(bundle), "refs/heads/" + self.fixture.merged_branch,
                       "^" + self.fixture.initial)
        with self.assertRaises(self.module.CleanupError):
            self.module.verify_bundle(bundle, self.candidates, self.fixture.root / "incremental-restore.git")
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_bundle_restore_requires_a_new_independent_repository(self):
        bundle = self.fixture.root / "recovery.bundle"
        self.module.create_bundle(self.store_dir, self.candidates, bundle)
        with self.assertRaises(self.module.CleanupError):
            self.module.verify_bundle(bundle, self.candidates, self.store_dir)

    def test_real_ancestry_selects_integrated_work_and_retains_unmerged_commits(self):
        lines = self.fixture.git(self.fixture.remote, "for-each-ref", "--format=%(refname:short) %(objectname)",
                                 "refs/heads/").stdout.splitlines()
        branches = [{"name": name, "sha": sha, "protected": name in PERMANENT}
                    for name, sha in (line.split() for line in lines)]
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        github = self.module.Github()

        def compare(endpoint):
            self.assertTrue(endpoint.startswith("compare/"))
            candidate, target = endpoint.removeprefix("compare/").split("?", 1)[0].split("...")
            ancestor = self.fixture.git(self.fixture.remote, "merge-base", "--is-ancestor", candidate, target,
                                        check=False).returncode == 0
            merge_base = self.fixture.git(self.fixture.remote, "merge-base", candidate, target).stdout.strip()
            return {"status": "ahead" if ancestor else "diverged", "behind_by": 0 if ancestor else 1,
                    "merge_base_commit": {"sha": merge_base}}

        with mock.patch.object(github, "get", side_effect=compare):
            comparisons = github.comparisons(branches, policy, {})
        candidates, held = self.module.select_candidates(branches, policy, comparisons)
        self.assertEqual([row["branch"] for row in candidates], [self.fixture.merged_branch])
        self.assertIn(self.fixture.unmerged_branch, held)

    def test_stale_trusted_checkout_cannot_supply_cleanup_code(self):
        self.module.verify_checkout(self.fixture.seed, self.fixture.main_sha)
        with self.assertRaises(self.module.CleanupError):
            self.module.verify_checkout(self.fixture.seed, self.fixture.initial)


class ApplyRecoveryTests(unittest.TestCase):
    """Exercise the entry point and real Git operations with an offline API."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_cleanup()

    setUp = GitBackupsAndDeletionTests.setUp
    pushes = GitBackupsAndDeletionTests.pushes
    assert_branch_exists = GitBackupsAndDeletionTests.assert_branch_exists

    def prepare_apply(self):
        policy = json.loads(POLICY_PATH.read_text())
        self.plan = dict(schema=1, repository=FORK, repository_id=1319052603,
                         source_sha=self.fixture.main_sha, candidates=self.candidates,
                         policy_sha256=hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
                         held={}, candidate_count=1)
        self.plan_path = self.fixture.root / "plan.json"
        self.report_path = self.fixture.root / "report.json"
        self.module.write_json(self.plan_path, self.plan)
        self.bundle = self.fixture.root / "recovery.bundle"
        self.module.create_bundle(self.store_dir, self.candidates, self.bundle)
        verified = self.module.verify_bundle(self.bundle, self.candidates, self.fixture.root / "verified.git")
        self.manifest = dict(verified, repository=FORK, candidates=self.candidates,
                             plan_sha256=self.module.digest(self.plan_path), source_sha=self.plan["source_sha"])
        self.module.write_json(self.fixture.root / "manifest.json", self.manifest)
        self.artifact = dict(workflow_run={"id": 123}, name="branch-cleanup-backup-123-1",
                             expired=False, size_in_bytes=100, digest="sha256:" + "c" * 64)

    def apply(self, artifact=None, plans=None, main=None):
        def get(endpoint):
            if main is not None and endpoint == "git/ref/heads/main":
                return {"object": {"sha": main}}
            if main is not None and endpoint.startswith("compare/"):
                revision = endpoint.split("/", 1)[1].split("...", 1)[0]
                ancestor = self.fixture.git(self.fixture.seed, "merge-base", "--is-ancestor",
                                            revision, main, check=False).returncode == 0
                return {"status": "ahead" if ancestor else "diverged", "behind_by": 0 if ancestor else 1,
                        "merge_base_commit": {"sha": revision if ancestor else self.fixture.initial}}
            self.assertEqual(endpoint, "actions/artifacts/456")
            self.events.append(("verify_artifact",))
            return self.artifact if artifact is None else artifact

        self.github.get = get
        argv = [str(SCRIPT), "apply", "--plan", str(self.plan_path),
                "--report", str(self.report_path), "--backup-dir", str(self.fixture.root),
                "--backup-artifact-id", "456", "--backup-artifact-digest", "c" * 64]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(self.module, "Github", return_value=self.github), \
                mock.patch.object(self.module, "trusted_runtime"), \
                mock.patch.object(self.module, "verify_checkout"), \
                mock.patch.object(self.module, "make_plan", side_effect=plans or [self.plan, self.plan]), \
                mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                                             "GITHUB_STEP_SUMMARY": ""}):
            result = self.module.main()
        return result, json.loads(self.report_path.read_text())

    def test_uploaded_independent_bundle_allows_deletion_without_any_tag_operations(self):
        self.prepare_apply()
        result, report = self.apply()
        self.assertEqual(result, 0)
        self.assertEqual(report["deleted"], [self.fixture.merged_branch])
        self.assertEqual(report["backup_artifact_id"], 456)
        self.assertNotIn("archive_tags", report)
        self.assertEqual(len(self.pushes()), 1)
        self.assertFalse(any("tag" in event[2] or any("refs/tags/" in arg for arg in event[2])
                             for event in self.events if event[0] == "git"))
        self.assertEqual(self.fixture.git(self.fixture.remote, "for-each-ref", "refs/tags").stdout, "")
        # The same uploaded bundle remains sufficient after the remote ref is gone.
        self.module.verify_bundle(self.bundle, self.candidates, self.fixture.root / "recovery-after-delete.git")

    def test_missing_backup_blocks_apply_before_remote_mutation(self):
        self.prepare_apply()
        self.bundle.unlink()
        result, _ = self.apply()
        self.assertEqual(result, 1)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_expired_wrong_run_or_digest_artifact_blocks_apply(self):
        self.prepare_apply()
        for change in ({"expired": True}, {"workflow_run": {"id": 124}},
                       {"digest": "sha256:" + "d" * 64}, {"name": "wrong"}, {"size_in_bytes": 0}):
            with self.subTest(change=change):
                result, report = self.apply(artifact={**self.artifact, **change})
                self.assertEqual(result, 1)
                self.assertEqual(report["error"], "uploaded_backup_not_verified")
                self.assertFalse(self.pushes())
                self.assert_branch_exists()

    def test_corruption_with_updated_manifest_still_fails_independent_restore(self):
        self.prepare_apply()
        data = bytearray(self.bundle.read_bytes())
        data[-12] ^= 1
        self.bundle.write_bytes(data)
        self.manifest["sha256"] = self.module.digest(self.bundle)
        self.module.write_json(self.fixture.root / "manifest.json", self.manifest)
        result, _ = self.apply()
        self.assertEqual(result, 1)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_new_activity_before_delete_blocks_apply(self):
        self.prepare_apply()
        changed = {**self.plan, "candidates": [], "held": {self.fixture.merged_branch: ["open_pull_request_head"]}}
        result, report = self.apply(plans=[self.plan, changed])
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "deferred")
        self.assertEqual(report["reason"], "activity_changed_before_delete")
        self.assertNotIn("error", report)
        self.assertEqual(report["held"][self.fixture.merged_branch], ["open_pull_request_head"])
        self.assertFalse(self.pushes())
        self.assert_branch_exists()


    def test_confirmed_main_advance_before_or_after_restore_defers_without_deleting(self):
        self.prepare_apply()
        current = self.fixture.advance_remote_branch("main")
        changed = {**self.plan, "source_sha": current}
        for plans, reason in (([changed], "trusted_main_or_policy_changed"),
                              ([self.plan, changed], "trusted_main_changed_before_delete")):
            with self.subTest(reason=reason):
                result, report = self.apply(plans=plans, main=current)
                self.assertEqual(result, 0)
                self.assertEqual(report["status"], "deferred")
                self.assertEqual(report["reason"], reason)
                self.assertEqual(report["deferred_details"]["current_main_sha"], current)
                self.assertNotIn("error", report)
                self.assertFalse(self.pushes())
                self.assert_branch_exists()

    def test_policy_mismatch_and_unproven_main_change_remain_real_failures(self):
        self.prepare_apply()
        for change, main in (({"policy_sha256": "c" * 64}, None),
                             ({"source_sha": self.fixture.initial}, self.fixture.initial)):
            with self.subTest(change=change):
                result, report = self.apply(plans=[{**self.plan, **change}], main=main)
                self.assertEqual(result, 1)
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(report["error"], "trusted_main_or_policy_changed")
                self.assertFalse(self.pushes())
                self.assert_branch_exists()


class ExpectedDeferralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adoption = load_adoption()
        cls.module = cls.adoption.cleanup

    def setUp(self):
        self.previous, self.current = "a" * 40, "b" * 40
        self.github = mock.Mock(spec=self.module.Github)
        self.github.get.side_effect = self.response
        self.policy = json.loads(POLICY_PATH.read_text())

    def response(self, endpoint):
        if endpoint == "git/ref/heads/main":
            return {"object": {"sha": self.current}}
        self.assertEqual(endpoint, f"compare/{self.previous}...{self.current}?per_page=1")
        return {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": self.previous}}

    def run_entry(self, adoption=False, failure=None):
        with tempfile.TemporaryDirectory() as directory:
            report, output, summary, plan = (Path(directory) / name for name in
                                             ("report.json", "output", "summary", "plan.json"))
            plan.write_text("stale plan must not survive a deferral")
            argv = ["adoption.py", "--report", str(report)] if adoption else [
                "cleanup.py", "plan", "--report", str(report), "--output", str(plan)]
            result = subprocess.CompletedProcess([], 0, stdout=self.previous + "\n", stderr="")
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_OUTPUT": str(output),
                                                "GITHUB_STEP_SUMMARY": str(summary)}, clear=True), \
                    mock.patch.object(self.module, "Github", return_value=self.github), \
                    mock.patch.object(self.module, "run", return_value=result), \
                    mock.patch.object(self.module, "make_plan", return_value={"source_sha": self.current}), \
                    mock.patch.object(self.adoption, "discover", return_value=([], {}, self.current)), \
                    mock.patch.object(self.adoption.Graph, "fetch") as fetch, \
                    mock.patch.object(self.adoption.Writer, "reconcile") as write:
                if failure:
                    self.github.get.side_effect = failure
                code = self.adoption.main() if adoption else self.module.main()
                fetch.assert_not_called()
                write.assert_not_called()
            return (code, json.loads(report.read_text()), output.read_text() if output.exists() else "",
                    summary.read_text() if summary.exists() else "", plan.exists())

    def test_plan_defers_with_zero_output_and_removes_stale_plan(self):
        code, report, output, summary, plan_exists = self.run_entry()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "deferred")
        self.assertEqual(report["reason"], "trusted_checkout_is_stale")
        self.assertNotIn("error", report)
        self.assertEqual(report["candidate_count"], 0)
        self.assertIn("candidate_count=0\n", output)
        self.assertIn("deferred=true\n", output)
        self.assertIn("Expected deferral", summary)
        self.assertFalse(plan_exists)
        self.github.verify_owner.assert_called_once()

    def test_adoption_defers_and_signals_the_workflow_to_skip_deletion_planning(self):
        code, report, output, summary, _ = self.run_entry(adoption=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "deferred")
        self.assertNotIn("error", report)
        self.assertIn("deferred=true\n", output)
        self.assertIn("main_advanced=false\n", output)
        self.assertIn("Expected deferral", summary)

    def test_api_errors_and_unproven_or_malformed_ancestry_stay_red(self):
        for adoption in (False, True):
            for proof in ({}, {"status": "diverged", "behind_by": 1},
                          {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": "c" * 40}},
                          {"status": "ahead", "behind_by": 0, "merge_base_commit": None},
                          {"status": "ahead", "behind_by": False, "merge_base_commit": {"sha": self.previous}},
                          self.module.CleanupError("github_api_unavailable")):
                with self.subTest(adoption=adoption, proof=proof):
                    def response(endpoint):
                        if endpoint == "git/ref/heads/main":
                            return {"object": {"sha": self.current}}
                        if isinstance(proof, Exception):
                            raise proof
                        return proof
                    code, report, output, _, _ = self.run_entry(adoption=adoption, failure=response)
                    self.assertEqual(code, 1)
                    self.assertEqual(report["status"], "blocked")
                    self.assertIn("error", report)
                    self.assertNotIn("deferred=true", output)

    def test_foreign_owner_is_a_real_failure_even_when_main_ancestry_looks_valid(self):
        self.github.verify_owner.side_effect = self.module.CleanupError("repository_ownership_mismatch")
        for adoption in (False, True):
            code, report, _, _, _ = self.run_entry(adoption=adoption)
            self.assertEqual(code, 1)
            self.assertEqual(report["error"], "repository_ownership_mismatch")

    def test_a_second_main_advance_requires_proof_for_both_earlier_snapshots(self):
        newest = "c" * 40
        for retained in (False, True):
            with self.subTest(retained=retained):
                def response(endpoint):
                    if endpoint == "git/ref/heads/main":
                        return {"object": {"sha": newest}}
                    revision = endpoint.split("/", 1)[1].split("...", 1)[0]
                    self.assertIn(revision, (self.previous, self.current))
                    self.assertIn("..." + newest, endpoint)
                    return {"status": "ahead" if retained or revision == self.previous else "diverged",
                            "behind_by": 0, "merge_base_commit": {"sha": revision}}
                self.github.get.side_effect = response
                with self.assertRaises(self.module.CleanupError) as caught:
                    self.module.defer_main_change(self.github, self.previous, self.current, "main_changed")
                self.assertEqual(isinstance(caught.exception, self.module.CleanupDeferred), retained)

    def test_app_write_is_stopped_before_mutation_on_a_confirmed_main_change(self):
        writer = self.adoption.Writer(self.github, ROOT, "offline-app-token", "overte-test")
        result = subprocess.CompletedProcess([], 0, stdout=self.previous + "\n", stderr="")
        with mock.patch.object(self.module, "trusted_runtime"), \
                mock.patch.object(self.module, "run", return_value=result) as run:
            with self.assertRaises(self.module.CleanupDeferred):
                writer.write("pulls", "POST", {"head": "example"})
        self.assertTrue(all(call.args[0][0] == "git" for call in run.call_args_list))


class AdoptedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adoption = load_adoption()
        cls.module = cls.adoption.cleanup

    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text())
        self.row = dict(branch="fix/main/adopted-source", sha="a" * 40,
                        base="main", base_sha="b" * 40, pr=123)
        self.github = mock.Mock(spec=self.module.Github)
        self.pr = dict(number=123, state="closed", closed_at="2026-10-15T00:00:00Z", draft=False,
                       head=dict(ref=self.row["branch"], sha=self.row["sha"],
                                 repo=dict(id=1319052603, full_name=FORK)),
                       base=dict(ref="main", sha=self.row["base_sha"],
                                 repo=dict(id=1319052603, full_name=FORK)))
        self.branches = [dict(name=name, sha=self.row["base_sha"], protected=True)
                         for name in sorted(PERMANENT)]
        self.branches.append(dict(name=self.row["branch"], sha=self.row["sha"], protected=False))
        self.github.branches.return_value = self.branches
        self.github.get.return_value = [self.pr]
        self.github.activity_holds.return_value = {}
        self.github.workflow_holds.return_value = {}
        self.plan = dict(held={self.row["branch"]: ["not_fully_integrated"]}, source_sha="b" * 40)

    def discover(self):
        with mock.patch.object(self.module, "make_plan", return_value=self.plan):
            return self.adoption.discover(self.github, self.policy)

    def test_only_a_completed_same_repository_exact_head_pr_is_considered(self):
        self.assertEqual(self.discover()[0], [self.row])
        for changes in (dict(state="open"), dict(draft=True), dict(closed_at=None),
                        dict(head={**self.pr["head"], "sha": "c" * 40}),
                        dict(head={**self.pr["head"], "repo": dict(id=1, full_name="foreign/repo")})):
            with self.subTest(changes=changes):
                self.github.get.return_value = [{**self.pr, **changes}]
                self.assertEqual(self.discover()[0], [])

    def test_latest_pr_state_and_consumer_holds_are_honored(self):
        self.github.get.return_value = [self.pr, {**self.pr, "number": 124, "state": "open"}]
        self.assertFalse(self.discover()[0])
        self.github.get.return_value = [self.pr]
        for method in ("activity_holds", "workflow_holds"):
            with self.subTest(method=method):
                getattr(self.github, method).return_value = {self.row["branch"]: ["consumer_hold"]}
                self.assertFalse(self.discover()[0])
                getattr(self.github, method).return_value = {}

    def test_generated_history_branches_do_not_recursively_generate_prs(self):
        name = self.adoption.maintenance_branch(self.row)
        self.plan["held"] = {name: ["not_fully_integrated"]}
        self.assertFalse(self.discover()[0])
        self.github.get.assert_not_called()

    def test_negative_cache_identity_changes_when_source_target_or_pr_changes(self):
        original = self.adoption.fingerprint(self.row)
        for key, value in (("sha", "c" * 40), ("base_sha", "d" * 40), ("pr", 124)):
            self.assertNotEqual(original, self.adoption.fingerprint({**self.row, key: value}))

    def test_writes_use_the_app_token_only_in_the_environment_and_recheck_ownership(self):
        writer = self.adoption.Writer(self.github, ROOT, "offline-app-token", "overte-test")
        self.github.get.return_value = {"object": {"sha": self.row["base_sha"]}}
        result = subprocess.CompletedProcess([], 0, stdout='{"ok": true}', stderr="")
        with mock.patch.object(self.module, "trusted_runtime") as runtime, \
                mock.patch.object(self.module, "verify_current_checkout") as checkout, \
                mock.patch.object(self.module, "run", return_value=result) as run:
            self.assertEqual(writer.write("pulls", "POST", {"head": "example"}), {"ok": True})
        runtime.assert_called_once()
        self.github.verify_owner.assert_called_once()
        checkout.assert_called_once_with(ROOT, self.row["base_sha"], self.github)
        self.assertIn("repos/" + FORK + "/pulls", run.call_args.args[0])
        self.assertNotIn("offline-app-token", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.kwargs["env"], {"GH_TOKEN": "offline-app-token"})

    def test_missing_app_identity_and_foreign_owner_prevent_writes(self):
        self.github.get.return_value = {"object": {"sha": self.row["base_sha"]}}
        with mock.patch.object(self.module, "trusted_runtime"), \
                mock.patch.object(self.module, "verify_current_checkout"), \
                mock.patch.object(self.module, "run") as run:
            for token, slug in (("", "overte-test"), ("token", ""), ("token", "../foreign")):
                with self.assertRaises(self.module.CleanupError):
                    self.adoption.Writer(self.github, ROOT, token, slug).write("pulls", "POST", {})
            self.github.verify_owner.side_effect = self.module.CleanupError("foreign_repository")
            with self.assertRaises(self.module.CleanupError):
                self.adoption.Writer(self.github, ROOT, "token", "overte-test").write("pulls", "POST", {})
            run.assert_not_called()

    def guard_responses(self, suffix, **kwargs):
        if suffix == "pulls/123":
            return self.pr
        if suffix == "rules/branches/main":
            return [dict(type=kind, ruleset_id=5, parameters=dict(
                strict_required_status_checks_policy=True,
                required_status_checks=[dict(context=context, integration_id=15368) for context in
                                        ("repository-checks", "branch-policy", "sync-test-reuse", "dependency-release-policy")]))
                for kind in ("deletion", "non_fast_forward", "pull_request", "required_status_checks")]
        if suffix == "rulesets/5":
            return dict(bypass_actors=[])
        raise AssertionError(suffix)

    def test_guard_requires_current_heads_completion_holds_and_strict_rules_without_bypass(self):
        writer = self.adoption.Writer(self.github, ROOT, "token", "overte-test")
        self.github.get.side_effect = self.guard_responses
        writer.guard(self.row, self.policy)
        for key in ("sha", "base_sha"):
            with self.subTest(key=key), self.assertRaises(self.module.CleanupError):
                writer.guard({**self.row, key: "c" * 40}, self.policy)
        for method in ("activity_holds", "workflow_holds"):
            getattr(self.github, method).return_value = {self.row["branch"]: ["hold"]}
            with self.assertRaises(self.module.CleanupError):
                writer.guard(self.row, self.policy)
            getattr(self.github, method).return_value = {}
        original = self.guard_responses
        for changed in (dict(bypass_actors=[dict(actor_type="Integration", actor_id=1)]),):
            self.github.get.side_effect = lambda suffix, **kw: changed if suffix == "rulesets/5" else original(suffix, **kw)
            with self.assertRaises(self.module.CleanupError):
                writer.guard(self.row, self.policy)

    def test_conflicts_and_changed_trees_are_the_only_cacheable_verdicts(self):
        self.assertEqual(self.adoption.NEGATIVE, {"merge_conflict", "tree_changes", "issue_closing_reference"})
        self.assertNotIn("adopted", self.adoption.NEGATIVE)
        self.assertNotIn("integrated", self.adoption.NEGATIVE)

    def test_cache_does_not_authorize_positive_proofs_or_other_versions(self):
        import io
        import zipfile
        key = self.adoption.fingerprint(self.row)
        self.github.get.side_effect = [
            {"workflow_runs": [{"id": 1, "run_attempt": 1}]},
            {"artifacts": [{"id": 5, "name": "branch-cleanup-report-1-1", "size_in_bytes": 100,
                            "expired": False}]}]
        for version, verdict in (("v1", "adopted"), ("v1", "integrated"), ("v2", "merge_conflict")):
            with self.subTest(version=version, verdict=verdict):
                payload = io.BytesIO()
                with zipfile.ZipFile(payload, "w") as archive:
                    archive.writestr("adoption.json", json.dumps(dict(repository=FORK, version=version,
                                                                   negative={key: verdict})))
                self.github.get.side_effect = [
                    {"workflow_runs": [{"id": 1, "run_attempt": 1}]},
                    {"artifacts": [{"id": 5, "name": "branch-cleanup-report-1-1", "size_in_bytes": 100,
                                    "expired": False}]}]
                result = subprocess.CompletedProcess([], 0, stdout=payload.getvalue(), stderr=b"")
                with mock.patch.object(self.adoption.subprocess, "run", return_value=result):
                    self.assertEqual(self.adoption.load_negative_cache(self.github, "v1"), {})

    def test_report_mode_and_missing_app_never_mutate_even_with_a_positive_proof(self):
        for apply, environment in ((False, {"ADOPTION_APP_TOKEN": "token", "ADOPTION_APP_SLUG": "overte-test"}),
                                   (True, {})):
            with self.subTest(apply=apply), tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "report.json"
                args = ["adoption.py", "--report", str(report)] + (["--apply"] if apply else [])
                with mock.patch.object(sys, "argv", args), mock.patch.dict(os.environ, environment, clear=True), \
                        mock.patch.object(self.adoption, "discover", return_value=([self.row], {}, "b" * 40)), \
                        mock.patch.object(self.adoption, "load_negative_cache", return_value={}), \
                        mock.patch.object(self.adoption.Graph, "fetch"), \
                        mock.patch.object(self.adoption.Graph, "proof", return_value=("adopted", "d" * 40)), \
                        mock.patch.object(self.adoption.Writer, "reconcile") as reconcile:
                    self.assertEqual(self.adoption.main(), 0)
                    reconcile.assert_not_called()
                saved = json.loads(report.read_text())
                self.assertEqual(saved["results"][self.row["branch"]], "adopted")
                self.assertFalse(saved["main_advanced"])

    def test_waiting_pr_does_not_starve_other_targets_and_only_one_mutation_is_allowed(self):
        rows = [dict(self.row, pr=number, branch=f"fix/main/source-{number}") for number in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as directory:
            args = ["adoption.py", "--report", str(Path(directory) / "report.json"), "--apply"]
            with mock.patch.object(sys, "argv", args), \
                    mock.patch.dict(os.environ, {"ADOPTION_APP_TOKEN": "token", "ADOPTION_APP_SLUG": "overte-test"}, clear=True), \
                    mock.patch.object(self.adoption, "discover", return_value=(rows, {}, "b" * 40)), \
                    mock.patch.object(self.adoption, "load_negative_cache", return_value={}), \
                    mock.patch.object(self.adoption.Graph, "fetch"), \
                    mock.patch.object(self.adoption.Graph, "proof", return_value=("adopted", "d" * 40)), \
                    mock.patch.object(self.adoption.Writer, "reconcile", side_effect=[
                        ("waiting_for_required_checks", False, False),
                        ("created_waiting_for_checks", False, True)]) as reconcile:
                self.assertEqual(self.adoption.main(), 0)
                self.assertEqual(reconcile.call_count, 2)

    def test_independent_readiness_requires_the_latest_check_on_the_exact_head_and_app(self):
        writer = self.adoption.Writer(self.github, ROOT, "token", "overte-test")
        required = [{"context": "repository-checks", "integration_id": 15368}]
        pr = {**self.pr, "state": "open"}
        good = dict(id=10, name="repository-checks", app={"id": 15368}, head_sha=self.row["sha"],
                    status="completed", conclusion="success")
        state = dict(headRefOid=self.row["sha"], baseRefOid=self.row["base_sha"], baseRefName="main",
                     mergeStateStatus="CLEAN", reviewDecision=None, closingIssuesReferences={"totalCount": 0})
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps({"data": {"repository": {
            "nameWithOwner": FORK, "pullRequest": state}}}), stderr="")
        with mock.patch.object(self.module, "run", return_value=result):
            self.github.get.side_effect = None
            self.github.get.return_value = {"total_count": 1, "check_runs": [good]}
            self.assertTrue(writer.ready(pr, self.row, required))
            for changes in (dict(app={"id": 1}), dict(head_sha="c" * 40), dict(status="in_progress"),
                            dict(conclusion="failure"), dict(conclusion="skipped")):
                with self.subTest(changes=changes):
                    self.github.get.return_value = {"total_count": 1, "check_runs": [{**good, **changes}]}
                    self.assertFalse(writer.ready(pr, self.row, required))
            self.github.get.return_value = {"total_count": 2, "check_runs": [
                {**good, "id": 9, "conclusion": "failure"}, good]}
            self.assertTrue(writer.ready(pr, self.row, required))

    def test_independent_readiness_honors_required_reviews_and_rejects_head_changes(self):
        writer = self.adoption.Writer(self.github, ROOT, "token", "overte-test")
        self.github.get.return_value = {"total_count": 0, "check_runs": []}
        self.github.get.side_effect = None
        state = dict(headRefOid=self.row["sha"], baseRefOid=self.row["base_sha"], baseRefName="main",
                     mergeStateStatus="CLEAN", reviewDecision="REVIEW_REQUIRED", closingIssuesReferences={"totalCount": 0})
        def output(value):
            return subprocess.CompletedProcess([], 0, stdout=json.dumps({"data": {"repository": {
                "nameWithOwner": FORK, "pullRequest": value}}}), stderr="")
        with mock.patch.object(self.module, "run", return_value=output(state)):
            self.assertFalse(writer.ready(self.pr, self.row, []))
        with mock.patch.object(self.module, "run", return_value=output({**state, "headRefOid": "c" * 40})):
            with self.assertRaises(self.module.CleanupError):
                writer.ready(self.pr, self.row, [])


class AdoptedHistoryPullRequestTests(unittest.TestCase):
    setUpClass = classmethod(AdoptedHistoryTests.setUpClass.__func__)
    def setUp(self):
        AdoptedHistoryTests.setUp(self)
        self.tree = "d" * 40
        self.head = "c" * 40
        self.branch = self.adoption.maintenance_branch(self.row)
        self.graph = mock.Mock(spec=self.adoption.Graph)
        self.graph.git.return_value = self.row["base_sha"] + " " + self.row["sha"]
        self.graph.proof.return_value = ("adopted", self.tree)
        self.history_pr = {**self.pr, "number": 321, "state": "open", "draft": False,
                           "user": {"login": "overte-test[bot]"}, "labels": [],
                           "head": {**self.pr["head"], "ref": self.branch, "sha": self.head},
                           "mergeable": True, "mergeable_state": "clean"}
        self.saved_pr = self.history_pr
        self.prs = [self.history_pr]
        self.writes = []
        self.recorded = None
        self.writer = self.adoption.Writer(self.github, ROOT, "token", "overte-test")
        self.writer.guard = mock.Mock()
        self.writer.ready = mock.Mock(return_value=True)
        self.writer.write = mock.Mock(side_effect=self.write_response)
        self.github.get.side_effect = self.response

    def response(self, suffix, **kwargs):
        if suffix.startswith("pulls?state=all&head="):
            return self.prs
        if suffix == "pulls/321":
            return self.saved_pr
        if suffix == "issues/321/labels":
            return [{"name": "type: task"}]
        if suffix.startswith("git/ref/heads/"):
            return {"object": {"sha": self.head}}
        if suffix.startswith("git/commits/"):
            if self.recorded and suffix.endswith(self.head):
                return self.recorded
            return dict(tree={"sha": self.tree}, parents=[{"sha": self.row["base_sha"]}, {"sha": self.head}])
        raise AssertionError(suffix)

    def write_response(self, suffix, method, payload):
        self.writes.append((suffix, method, payload))
        if suffix == "git/commits":
            self.recorded = dict(sha=self.head, tree={"sha": payload["tree"]},
                                 parents=[{"sha": sha} for sha in payload["parents"]])
            return self.recorded
        if suffix.startswith("git/refs"):
            return {"ref": payload.get("ref", "refs/heads/" + self.branch), "object": {"sha": payload["sha"]}}
        if suffix == "pulls":
            return {"number": 321}
        if suffix == "issues/321/labels":
            return [{"name": "type: task"}]
        if suffix == "pulls/321/merge":
            self.saved_pr = {**self.history_pr, "merged": True, "merge_commit_sha": "e" * 40}
            return {"merged": True}
        raise AssertionError(suffix)

    def reconcile(self):
        return self.writer.reconcile(self.row, self.tree, self.graph, self.policy)

    def test_only_a_clean_checked_pr_is_merged_with_the_exact_head(self):
        self.assertEqual(self.reconcile(), ("integrated", True, True))
        self.assertEqual(self.writes, [("pulls/321/merge", "PUT", {"sha": self.head, "merge_method": "merge"})])
        self.assertEqual(self.writer.guard.call_count, 2)
        self.graph.verify_record.assert_called_once_with(self.head, self.row)
        self.graph.proof.assert_called_once_with(self.row)

    def test_pending_failed_unknown_and_conflicting_prs_are_not_merged(self):
        for state in ("blocked", "behind", "dirty", "unstable", "unknown"):
            with self.subTest(state=state):
                self.saved_pr = {**self.history_pr, "mergeable_state": state}
                self.assertEqual(self.reconcile(), ("waiting_for_required_checks", False, False))
        self.assertFalse(self.writes)

    def test_human_closed_draft_and_keep_prs_do_not_spawn_replacements(self):
        for changes, expected in (({"state": "closed"}, "previous_adoption_pr_closed"),
                                  ({"draft": True}, "adoption_pr_held"),
                                  ({"labels": [{"name": "keep-branch"}]}, "adoption_pr_held")):
            with self.subTest(changes=changes):
                self.prs = [{**self.history_pr, **changes}]
                self.assertEqual(self.reconcile(), (expected, False, False))
        self.assertFalse(self.writes)

    def test_fresh_pr_head_or_keep_request_changes_prevent_merge(self):
        for changes in ({"head": {**self.history_pr["head"], "sha": "f" * 40}},
                        {"labels": [{"name": "keep-branch"}]}, {"draft": True}):
            with self.subTest(changes=changes):
                self.saved_pr = {**self.history_pr, **changes}
                with self.assertRaises(self.module.CleanupError):
                    self.reconcile()
        self.assertFalse(self.writes)

    def test_failed_final_proof_prevents_merge_even_when_checks_are_green(self):
        self.graph.proof.return_value = ("tree_changes", None)
        with self.assertRaises(self.module.CleanupError):
            self.reconcile()
        self.assertFalse(self.writes)

    def test_new_pr_preserves_the_source_and_target_and_is_labeled(self):
        self.prs = []
        self.assertEqual(self.reconcile(), ("created_waiting_for_checks", False, True))
        self.assertEqual([path for path, _, _ in self.writes],
                         ["git/commits", "git/refs", "pulls", "issues/321/labels"])
        self.assertEqual(self.writes[0][2]["parents"], [self.row["base_sha"], self.row["sha"]])
        self.assertEqual(self.writes[0][2]["tree"], self.tree)
        self.assertEqual(self.writes[1][2]["ref"], "refs/heads/" + self.branch)
        self.assertEqual(self.writes[-1][2]["labels"], ["type: task"])

    def test_stale_history_branch_is_refreshed_without_force_or_merge(self):
        self.graph.git.return_value = "e" * 40 + " " + self.row["sha"]
        self.assertEqual(self.reconcile(), ("refreshed_waiting_for_checks", False, True))
        self.assertEqual([path for path, _, _ in self.writes],
                         ["git/commits", "git/refs/heads/" + self.branch.replace("/", "%2F")])
        self.assertIs(self.writes[-1][2]["force"], False)
        self.assertEqual(self.writes[0][2]["parents"], [self.row["base_sha"], self.head])


class AdoptedHistoryGitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adoption = load_adoption()
        cls.module = cls.adoption.cleanup

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adopted-history-test-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = LocalGitFixture(Path(self.temp.name))
        self.events = []
        transport = OfflineGitTransport(self.fixture, self.events, self.module.CleanupError)
        self.patch = mock.patch.object(self.module, "run", side_effect=transport)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.graph = self.adoption.Graph(self.fixture.root / "proof.git")
        self.row = dict(branch=self.fixture.unmerged_branch, sha=self.fixture.unmerged_sha,
                        base="main", base_sha=self.fixture.main_sha, pr=123)

    def fetch(self):
        self.graph.fetch({self.row["branch"]: self.row["sha"], "main": self.row["base_sha"]})

    def adopt_source(self):
        f = self.fixture
        f.git(f.seed, "checkout", "-q", "main")
        f.git(f.seed, "commit", "-q", "--allow-empty", "-m", "independent target progress")
        f.git(f.seed, "cherry-pick", self.row["sha"])
        self.row["base_sha"] = f.rev(f.seed, "HEAD")
        f.git(f.seed, "push", "-q", "fixture", "main")

    def test_normal_merge_proves_cherry_picked_work_without_source_ancestry(self):
        self.adopt_source()
        self.fetch()
        verdict, tree = self.graph.proof(self.row)
        self.assertEqual(verdict, "adopted")
        self.assertEqual(tree, self.fixture.git(self.fixture.seed, "rev-parse", "HEAD^{tree}").stdout.strip())
        self.assertEqual(self.fixture.git(self.fixture.remote, "merge-base", "--is-ancestor",
                                         self.row["sha"], self.row["base_sha"], check=False).returncode, 1)
        self.assertFalse(any(event[1] == "push" for event in self.events))
        self.assertFalse((self.graph.path / "index").exists())

    def test_unadopted_work_and_conflicts_never_authorize_history_integration(self):
        self.fetch()
        self.assertEqual(self.graph.proof(self.row), ("tree_changes", None))
        f = self.fixture
        f.git(f.seed, "checkout", "-q", "main")
        (f.seed / "unmerged.txt").write_text("different target implementation\n")
        f.git(f.seed, "add", "unmerged.txt")
        f.git(f.seed, "commit", "-q", "-m", "different target payload")
        self.row["base_sha"] = f.rev(f.seed, "HEAD")
        f.git(f.seed, "push", "-q", "fixture", "main")
        self.fetch()
        self.assertEqual(self.graph.proof(self.row), ("merge_conflict", None))

    def test_mode_changes_remain_real_changes_even_when_file_bytes_match(self):
        self.adopt_source()
        f = self.fixture
        f.git(f.seed, "checkout", "-q", self.row["branch"])
        f.git(f.seed, "update-index", "--chmod=+x", "unmerged.txt")
        f.git(f.seed, "commit", "-q", "-m", "unique executable mode")
        self.row["sha"] = f.rev(f.seed, "HEAD")
        f.git(f.seed, "push", "-q", "fixture", self.row["branch"])
        self.fetch()
        verdict, tree = self.graph.proof(self.row)
        self.assertIn(verdict, self.adoption.NEGATIVE)
        self.assertIsNone(tree)

    def test_commit_closing_keywords_cannot_complete_issues_via_history_integration(self):
        self.adopt_source()
        f = self.fixture
        f.git(f.seed, "checkout", "-q", self.row["branch"])
        f.git(f.seed, "commit", "-q", "--allow-empty", "-m", "Fixes #123")
        self.row["sha"] = f.rev(f.seed, "HEAD")
        f.git(f.seed, "push", "-q", "fixture", self.row["branch"])
        self.fetch()
        self.assertEqual(self.graph.proof(self.row), ("issue_closing_reference", None))

    def test_record_chain_preserves_original_commits_and_rejects_extra_payload(self):
        self.adopt_source()
        self.fetch()
        verdict, tree = self.graph.proof(self.row)
        self.assertEqual(verdict, "adopted")
        message = "Record adopted history\n\n" + self.adoption.MARKER + json.dumps(self.row)
        head = self.graph.command("-c", "user.name=Offline Test", "-c", "user.email=test@example.invalid",
                                  "commit-tree", tree, "-p", self.row["base_sha"], "-p", self.row["sha"],
                                  "-m", message).stdout.strip()
        self.graph.verify_record(head, self.row)
        self.assertEqual(self.graph.command("merge-base", "--is-ancestor", self.row["sha"], head).returncode, 0)
        with self.assertRaises(self.module.CleanupError):
            self.graph.verify_record(head, {**self.row, "sha": "c" * 40})
        bad_tree = self.graph.git("rev-parse", self.fixture.initial + "^{tree}").strip()
        bad = self.graph.command("-c", "user.name=Offline Test", "-c", "user.email=test@example.invalid",
                                 "commit-tree", bad_tree, "-p", self.row["base_sha"], "-p", self.row["sha"],
                                 "-m", message).stdout.strip()
        with self.assertRaises(self.module.CleanupError):
            self.graph.verify_record(bad, self.row)

    def test_refresh_preserves_the_previous_record_and_original_source(self):
        self.adopt_source()
        self.fetch()
        tree = self.graph.proof(self.row)[1]
        def record(previous):
            message = self.adoption.MARKER + json.dumps(self.row)
            return self.graph.command("-c", "user.name=Offline Test", "-c", "user.email=test@example.invalid",
                                      "commit-tree", tree, "-p", self.row["base_sha"], "-p", previous,
                                      "-m", message).stdout.strip()
        previous = record(self.row["sha"])
        f = self.fixture
        f.git(f.seed, "commit", "-q", "--allow-empty", "-m", "later protected target")
        self.row["base_sha"] = f.rev(f.seed, "HEAD")
        f.git(f.seed, "push", "-q", "fixture", "main")
        self.fetch()
        refreshed = record(previous)
        self.graph.verify_record(refreshed, self.row)
        self.graph.command("merge-base", "--is-ancestor", previous, refreshed)
        self.graph.command("merge-base", "--is-ancestor", self.row["sha"], refreshed)


class CleanupPreflightTests(unittest.TestCase):
    def setUp(self):
        self.module = load_cleanup()
        temporary = tempfile.TemporaryDirectory(prefix="cleanup-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report = self.root / "report.json"
        self.outputs = self.root / "outputs"

    def plan(self, failure=None, *, stale=True, github=None):
        plan = dict(source_sha="a" * 40, candidate_count=2, held={}, candidates=[{}, {}])
        adapter = github if github is not None else mock.Mock()
        def response(endpoint=""):
            if not endpoint:
                return {"full_name": FORK, "id": 1319052603,
                        "default_branch": "main", "delete_branch_on_merge": False}
            if endpoint == "git/ref/heads/main":
                return {"object": {"sha": "a" * 40}}
            self.assertEqual(endpoint, "compare/" + "b" * 40 + "..." + "a" * 40 + "?per_page=1")
            return {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": "b" * 40}}
        with mock.patch.object(sys, "argv", [str(SCRIPT), "plan", "--output", str(self.root / "plan.json"),
                                             "--report", str(self.report)]), \
                mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_OUTPUT": str(self.outputs)}, clear=True), \
                mock.patch.object(self.module, "Github", return_value=adapter), \
                mock.patch.object(adapter, "get", side_effect=response), \
                mock.patch.object(self.module, "make_plan", **({"side_effect": failure} if failure else {"return_value": plan})), \
                mock.patch.object(self.module, "run", return_value=subprocess.CompletedProcess([], 0, stdout=("b" if stale else "a") * 40)), \
                mock.patch.object(self.module, "GitStore", side_effect=AssertionError("preflight never mutates")):
            return self.module.main(), json.loads(self.report.read_text())

    def test_stale_plan_defers_without_authorizing_its_earlier_candidates(self):
        result, report = self.plan()
        self.assertEqual(result, 0)
        self.assertEqual((report["status"], report["reason"], report["candidate_count"], report["deleted"]),
                         ("deferred", "trusted_checkout_is_stale", 0, []))
        self.assertNotIn("error", report)
        self.assertFalse((self.root / "plan.json").exists())
        self.assertEqual(dict(line.split("=", 1) for line in self.outputs.read_text().splitlines()),
                         {"deferred": "true", "candidate_count": "0"})

    def test_plan_report_retains_only_fixed_adapter_counters(self):
        github = self.module.Github()
        with mock.patch.dict(os.environ, {"BRANCH_CLEANUP_IMMUTABLE_CACHE": ""}), \
                mock.patch.object(self.module, "run", return_value=subprocess.CompletedProcess([], 0, stdout="[]")):
            github.get("actions/runs?private=synthetic-private-marker")
        for stale in (False, True):
            _, report = self.plan(stale=stale, github=github)
            self.assertEqual(report["immutable_api_cache"], github.cache_statistics())
            self.assertEqual(report["immutable_api_cache"]["fresh_api_invocations"]["other"], 1)
            self.assertNotIn("synthetic-private-marker", json.dumps(report))
            self.assertNotIn("actions/runs", json.dumps(report))

    def test_fresh_plan_retains_candidates_but_genuine_errors_remain_red(self):
        code, report = self.plan(stale=False)
        self.assertEqual((code, report["status"], report["candidate_count"]), (0, "planned", 2))
        for reason in ("github_api_get_actions_runs_http_403_forbidden", "active_run_listing_incomplete",
                       "permanent_branch_unprotected", "trusted_checkout_is_stale"):
            with self.subTest(reason=reason):
                code, report = self.plan(self.module.CleanupError(reason))
                self.assertEqual((code, report["status"], report["error"]), (1, "blocked", reason))

    def test_backup_and_apply_require_an_exact_initial_checkout(self):
        for command in ("backup", "apply"):
            args = [str(SCRIPT), command, "--plan", str(self.root / "plan.json")]
            args += ["--output-dir", str(self.root / "backup")] if command == "backup" else [
                "--report", str(self.report), "--backup-dir", str(self.root / "backup"),
                "--backup-artifact-id", "1", "--backup-artifact-digest", "a" * 64]
            with self.subTest(command=command), mock.patch.object(sys, "argv", args), \
                    mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(self.module, "Github"), \
                    mock.patch.object(self.module, "trusted_runtime"), \
                    mock.patch.object(self.module, "load_plan", return_value={"source_sha": "a" * 40}), \
                    mock.patch.object(self.module, "run", return_value=subprocess.CompletedProcess([], 0, stdout="b" * 40)), \
                    mock.patch.object(self.module, "GitStore", side_effect=AssertionError("no mutation")):
                self.assertEqual(self.module.main(), 1)
            self.assertFalse((self.root / "backup").exists())
        self.assertEqual(json.loads(self.report.read_text())["status"], "blocked")
        self.assertEqual(json.loads(self.report.read_text())["error"], "trusted_checkout_is_stale")

    def test_api_failure_labels_are_actionable_without_exposing_payloads_or_credentials(self):
        for stderr, status, category in (
                ("gh: denied (HTTP 401)", "401", "unauthorized"),
                ("gh: Resource not accessible by integration (HTTP 403)", "403", "forbidden"),
                ("gh: secondary rate limit (HTTP 403)", "403", "rate_limited"),
                ("gh: not found (HTTP 404)", "404", "not_found"),
                ("gh: retry later (HTTP 429)", "429", "rate_limited"),
                ("gh: unavailable (HTTP 503)", "503", "server_error"),
                ("failed without an HTTP response", "unknown", "cli_error")):
            result = subprocess.CompletedProcess([], 1, stdout="private response", stderr=stderr + " secret-token https://signed/private?auth=secret")
            with self.subTest(status=status), mock.patch.object(self.module.subprocess, "run", return_value=result), \
                    self.assertRaises(self.module.CleanupError) as error:
                self.module.Github().get("actions/runs?status=in_progress&private=secret")
            self.assertEqual(str(error.exception), f"github_api_get_actions_runs_http_{status}_{category}")
        error = self.module.api_failure(["gh", "api", "--method", "POST", "repos/" + FORK + "/pulls", "--input", "-"], result)
        self.assertEqual(str(error), "github_api_post_pulls_http_unknown_cli_error")
        error = self.module.api_failure(["gh", "api", "graphql", "-f", "query=private source"], result)
        self.assertEqual(str(error), "github_api_post_graphql_http_unknown_cli_error")

    def test_adoption_preflight_deferral_skips_cache_graph_and_writes(self):
        adoption = load_adoption()
        with mock.patch.object(sys, "argv", ["adoption.py", "--report", str(self.report), "--apply"]), \
                mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_OUTPUT": str(self.outputs)}, clear=True), \
                mock.patch.object(adoption, "discover", return_value=([{}], {}, "a" * 40)), \
                mock.patch.object(adoption.cleanup, "run", return_value=subprocess.CompletedProcess([], 0, stdout="b" * 40)), \
                mock.patch.object(adoption.cleanup, "Github") as github, mock.patch.object(adoption, "load_negative_cache") as cache, \
                mock.patch.object(adoption, "Graph") as graph, mock.patch.object(adoption, "Writer") as writer:
            def response(endpoint):
                if endpoint == "git/ref/heads/main":
                    return {"object": {"sha": "a" * 40}}
                self.assertEqual(endpoint, "compare/" + "b" * 40 + "..." + "a" * 40 + "?per_page=1")
                return {"status": "ahead", "behind_by": 0, "merge_base_commit": {"sha": "b" * 40}}
            github.return_value.get.side_effect = response
            self.assertEqual(adoption.main(), 0)
        cache.assert_not_called(); graph.assert_not_called(); writer.assert_not_called()
        saved = json.loads(self.report.read_text())
        self.assertEqual(saved["status"], "deferred")
        self.assertEqual(saved["reason"], "trusted_checkout_is_stale")
        self.assertEqual(saved["deferred_details"]["current_main_sha"], "a" * 40)
        self.assertFalse(saved["main_advanced"])
        self.assertIn("deferred=true", self.outputs.read_text())

    def test_adoption_reports_retain_counters_on_success_and_preflight_deferral(self):
        adoption = load_adoption()
        github = adoption.cleanup.Github()
        with mock.patch.dict(os.environ, {"BRANCH_CLEANUP_IMMUTABLE_CACHE": ""}), \
                mock.patch.object(adoption.cleanup, "run", return_value=subprocess.CompletedProcess([], 0, stdout="[]")):
            github.get("actions/runs?private=synthetic-private-marker")
        for stale in (False, True):
            with mock.patch.object(sys, "argv", ["adoption.py", "--report", str(self.report)]), \
                    mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True), \
                    mock.patch.object(adoption.cleanup, "Github", return_value=github), \
                    mock.patch.object(adoption, "discover", return_value=([], {}, "a" * 40)), \
                    mock.patch.object(adoption.cleanup, "verify_current_checkout", side_effect=(
                        adoption.cleanup.CleanupDeferred("trusted_checkout_is_stale") if stale else None)), \
                    mock.patch.object(adoption, "load_negative_cache", return_value={}), \
                    mock.patch.object(adoption, "Writer"), mock.patch.object(adoption, "Graph"):
                self.assertEqual(adoption.main(), 0)
            report = json.loads(self.report.read_text())
            self.assertEqual(report["immutable_api_cache"], github.cache_statistics())
            self.assertNotIn("synthetic-private-marker", json.dumps(report))

    def test_adoption_errors_after_preflight_and_generic_api_errors_remain_failures(self):
        adoption = load_adoption()
        for preflight in (True, False):
            error = adoption.cleanup.CleanupError("github_api_get_branches_http_403_forbidden") if preflight \
                else adoption.cleanup.CleanupError("github_api_get_actions_artifacts_http_403_forbidden")
            with self.subTest(preflight=preflight), mock.patch.object(sys, "argv", ["adoption.py", "--report", str(self.report)]), \
                    mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True), \
                    mock.patch.object(adoption.cleanup, "Github"), \
                    mock.patch.object(adoption, "discover", **({"side_effect": error} if preflight else {"return_value": ([], {}, "a" * 40)})), \
                    mock.patch.object(adoption.cleanup, "verify_current_checkout"), \
                    mock.patch.object(adoption, "load_negative_cache", side_effect=error):
                self.assertEqual(adoption.main(), 1)
            self.assertEqual(json.loads(self.report.read_text())["status"], "blocked")
            self.assertEqual(json.loads(self.report.read_text())["error"], str(error))


class TerminalRetryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_cleanup()
        self.github = self.module.Github()
        self.policy = json.loads(POLICY_PATH.read_text())
        self.revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.repository = {"id": 1319052603, "full_name": FORK}
        self.rows = [{"name": name, "sha": self.revision, "protected": True} for name in sorted(PERMANENT)]
        self.branch = "fix/main/earlier-closed-source"
        self.rows.append({"name": self.branch, "sha": "a" * 40, "protected": False})
        self.closed = {self.branch: [self.closed_pr(self.branch, "main", "a" * 40)]}
        self.open_prs, self.active, self.requests = [], [], []
        self.runs = {700: self.push_run(700, 350930890)}
        self.signal = {"action": "completed", "repository": self.repository,
                       "workflow_run": copy.deepcopy(self.runs[700])}
        self.source_changes, self.reference_changes, self.comparisons = {}, {}, {}
        self.integrated = True
        self.enterContext(mock.patch.object(self.github, "get", side_effect=self.response))
        self.enterContext(mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "999"}))

    def closed_pr(self, branch, target, sha):
        return {"number": 13, "state": "closed", "closed_at": "2026-10-16T04:29:46Z", "labels": [],
                "head": {"ref": branch, "sha": sha, "repo": self.repository},
                "base": {"ref": target, "repo": self.repository}}

    def push_run(self, identifier, workflow, target="main"):
        name, filename = self.module.TERMINAL_WORKFLOWS[workflow]
        return {"id": identifier, "run_attempt": 1, "workflow_id": workflow, "event": "push",
                "status": "completed", "conclusion": "success", "head_branch": target,
                "head_sha": self.revision, "name": name, "path": ".github/workflows/" + filename,
                "repository": self.repository, "head_repository": self.repository, "pull_requests": []}

    def manual_run(self, identifier=700, target="main", revision=None, workflow=386334598):
        return {**self.push_run(identifier, workflow, target), "event": "workflow_dispatch",
                "head_sha": revision or self.revision}

    def response(self, suffix="", paginate=False):
        self.requests.append((suffix, paginate))
        if not suffix:
            return {**self.repository, "default_branch": "main", "delete_branch_on_merge": False}
        if suffix == "branches?per_page=100":
            self.assertTrue(paginate)
            return [{**row, "commit": {"sha": row["sha"]}} for row in copy.deepcopy(self.rows)]
        if suffix.startswith("actions/runs/"):
            return copy.deepcopy(self.runs[int(suffix.rsplit("/", 1)[1])])
        if suffix.startswith("actions/workflows/"):
            identifier = int(suffix.rsplit("/", 1)[1])
            name, filename = self.module.TERMINAL_WORKFLOWS[identifier]
            return {"id": identifier, "name": name, "path": ".github/workflows/" + filename}
        if suffix.startswith("contents/.github/workflows?"):
            return []
        if suffix.startswith("contents/.github/workflows/"):
            path = suffix.split("?", 1)[0][9:]
            name = next(name for name, filename in self.module.TERMINAL_WORKFLOWS.values()
                        if path.endswith("/" + filename))
            raw = self.source_changes.get(path, ("name: " + name + "\non:\n  push:\n").encode())
            return {"path": path, "type": "file", "sha": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), "size": len(raw),
                "encoding": "base64", "content": base64.b64encode(raw).decode()}
        if suffix == "pulls?state=open&per_page=100":
            self.assertTrue(paginate)
            return copy.deepcopy(self.open_prs)
        if suffix.startswith(("pulls?state=closed&", "pulls?state=all&")):
            self.assertTrue(paginate)
            query = self.module.urllib.parse.parse_qs(suffix.split("?", 1)[1])
            branch = query["head"][0].removeprefix("noah-l-frank:")
            return copy.deepcopy(self.closed.get(branch, []))
        if suffix.startswith("actions/runs?status="):
            state = self.module.urllib.parse.parse_qs(suffix.split("?", 1)[1])["status"][0]
            runs = [run for run in self.active if run.get("status") == state]
            return {"total_count": len(runs), "workflow_runs": copy.deepcopy(runs)}
        if suffix.startswith("git/ref/heads/"):
            target = self.module.urllib.parse.unquote(suffix.removeprefix("git/ref/heads/"))
            sha = self.reference_changes.get(target, next(row["sha"] for row in self.rows if row["name"] == target))
            return {"ref": "refs/heads/" + target, "object": {"type": "commit", "sha": sha}}
        if suffix.startswith("compare/"):
            first = suffix[8:].split("...", 1)[0]
            integrated = self.comparisons.get(first, self.integrated)
            return {"status": "ahead" if integrated else "diverged", "behind_by": 0 if integrated else 1,
                    "merge_base_commit": {"sha": first}}
        if suffix.startswith("rules/branches/"):
            return [{"type": "deletion"}, {"type": "non_fast_forward"}]
        if suffix in ("deployments?per_page=100", "releases?per_page=100", "issues?state=open&per_page=100"):
            return []
        raise AssertionError("unregistered cleanup API request: " + suffix)

    def retry(self, run=700):
        self.signal["workflow_run"] = copy.deepcopy(self.runs[run])
        return self.module.terminal_retry(self.github, self.policy, self.signal)

    def main_sync_hints(self, targets):
        scopes = {"main": "main", "android-main": "android", "android-phone": "android-phone",
                  "android-vr": "android-vr", "android-vr-pico": "android-pico",
                  "apple-main": "apple", "apple-ios": "ios"}
        self.rows = [row for row in self.rows if row["protected"]]
        for index, row in enumerate(self.rows, 1):
            if row["name"] != "main":
                row["sha"] = format(index, "040x")
        self.closed = {}
        hints = {}
        for target in targets:
            branch = "fix/" + scopes[target] + "/manual-sync-held-source"
            head = hashlib.sha1(branch.encode()).hexdigest()
            base = next(row["sha"] for row in self.rows if row["name"] == target)
            self.rows.append({"name": branch, "sha": head, "protected": False})
            self.closed[branch] = [self.closed_pr(branch, target, head)]
            hints[target] = {"branch": branch, "sha": head, "base": target, "base_sha": base}
        self.open_prs, self.active, self.requests = [], [], []
        self.source_changes, self.reference_changes, self.comparisons = {}, {}, {}
        self.runs[700] = dict(self.manual_run(workflow=350930895, revision="f" * 40),
                              name="Sync validation gate-600-attempt-1")
        return hints

    def test_main_sync_completion_retries_child_with_its_actual_protected_base(self):
        hints = self.main_sync_hints(["apple-ios"])
        with mock.patch.object(self.github, "activity_holds", wraps=self.github.activity_holds) as activity:
            result = self.retry()
        self.assertTrue(result["retry"])
        self.assertEqual(result["hint_count"], 1)
        self.assertEqual((result["target"], result["target_sha"], result["trigger_source_sha"]),
                         ("main", self.revision, "f" * 40))
        self.assertEqual(activity.call_args.args[0], [hints["apple-ios"]])
        head = self.module.urllib.parse.quote("noah-l-frank:" + hints["apple-ios"]["branch"], safe="")
        self.assertIn(("pulls?state=closed&head=" + head + "&base=apple-ios&per_page=100", True), self.requests)
        self.assertIn(("git/ref/heads/apple-ios", False), self.requests)
        self.assertIn(("git/ref/heads/main", False), self.requests)
        self.assertNotIn("candidates", result)
        self.assertNotIn("candidate_count", result)

    def test_main_sync_completion_considers_exactly_the_seven_recognized_targets(self):
        hints = self.main_sync_hints(sorted(PERMANENT))
        unknown = "fix/unknown/manual-sync-held-source"
        self.rows.append({"name": unknown, "sha": "e" * 40, "protected": False})
        self.closed[unknown] = [self.closed_pr(unknown, "apple-ios", "e" * 40)]
        with mock.patch.object(self.github, "activity_holds", wraps=self.github.activity_holds) as activity:
            result = self.retry()
        self.assertTrue(result["retry"])
        self.assertEqual(result["hint_count"], 7)
        self.assertEqual(sorted(activity.call_args.args[0], key=lambda row: row["base"]),
                         [hints[target] for target in sorted(PERMANENT)])
        queries = [self.module.urllib.parse.parse_qs(path.split("?", 1)[1])
                   for path, _ in self.requests if path.startswith("pulls?state=closed&")]
        self.assertEqual({query["base"][0] for query in queries}, PERMANENT)
        self.assertEqual(len(queries), 7)
        self.assertEqual({path for path, _ in self.requests if path.startswith("git/ref/heads/")},
                         {"git/ref/heads/" + target for target in PERMANENT})
        self.assertFalse(any(unknown in row["branch"] for row in activity.call_args.args[0]))

    def test_main_sync_completion_rechecks_child_targets_and_original_main(self):
        for target in ("main", "apple-ios", "android-main"):
            self.main_sync_hints(["apple-ios", "android-main"])
            self.reference_changes[target] = "e" * 40
            with self.subTest(moved=target):
                result = self.retry()
                self.assertFalse(result["retry"])
                self.assertEqual(result["reason"], "terminal_target_changed")
        for change in ({"ref": "refs/heads/main"}, {"object": {"type": "tag", "sha": "e" * 40}},
                       {"object": {"type": "commit", "sha": "invalid"}}):
            self.main_sync_hints(["apple-ios"])
            original = self.response
            def altered(path="", paginate=False):
                value = original(path, paginate)
                return {**value, **change} if path == "git/ref/heads/apple-ios" else value
            with self.subTest(reference=change), mock.patch.object(self.github, "get", side_effect=altered), \
                    self.assertRaisesRegex(self.module.CleanupError, "invalid_terminal_current_target"):
                self.retry()

    def test_only_authenticated_main_sync_dispatch_expands_retry_targets(self):
        for workflow in (350930894, 386334598):
            self.main_sync_hints(["apple-ios"])
            self.runs[700] = self.manual_run(workflow=workflow)
            with self.subTest(other_manual=workflow):
                self.assertEqual(self.retry()["reason"], "no_current_closed_pr_hint")
        self.main_sync_hints(["apple-ios"])
        self.runs[700] = self.manual_run(target="apple-main", workflow=350930895)
        self.assertEqual(self.retry()["reason"], "no_current_closed_pr_hint")
        for change in ({"event": "push"}, {"event": "pull_request"},
                       {"head_branch": "fix/main/unprotected"},
                       {"head_repository": {"id": 1, "full_name": "foreign/fork"}}):
            self.main_sync_hints(["apple-ios"])
            self.runs[700].update(change)
            with self.subTest(untrusted=change), self.assertRaises(self.module.CleanupError):
                self.retry()

    def test_main_sync_child_hints_preserve_current_head_and_remaining_activity_holds(self):
        for case in ("head_changed", "open", "explicit", "keep", "active"):
            hint = self.main_sync_hints(["apple-ios"])["apple-ios"]
            policy = copy.deepcopy(self.policy)
            if case == "head_changed":
                self.rows[-1]["sha"] = "e" * 40
            elif case == "open":
                self.open_prs = [dict(self.closed[hint["branch"]][0], state="open", closed_at=None)]
            elif case == "explicit":
                policy["holds"][hint["branch"]] = "Required work remains active"
            elif case == "keep":
                self.closed[hint["branch"]][0]["labels"] = [{"name": "keep-branch"}]
            else:
                self.active = [dict(self.manual_run(800, target="apple-ios", workflow=330869250),
                                    status="in_progress", conclusion=None)]
            self.signal["workflow_run"] = copy.deepcopy(self.runs[700])
            with self.subTest(held=case):
                result = self.module.terminal_retry(self.github, policy, self.signal)
                self.assertFalse(result["retry"])
                self.assertEqual(result["reason"], "terminal_candidates_still_held"
                                 if case in {"keep", "active"} else "no_current_closed_pr_hint")

    def test_main_sync_child_hint_cannot_prove_integration_or_retirement(self):
        self.main_sync_hints(["apple-ios"])
        self.runs[700].update(head_sha=self.revision, conclusion="failure")
        self.integrated = False
        result = self.retry()
        self.assertTrue(result["retry"])
        self.assertNotIn("candidates", result)
        self.assertNotIn("candidate_count", result)
        self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)

    def test_real_api_context_and_older_closed_heads_produce_only_a_hint(self):
        self.closed[self.branch].insert(0, self.closed_pr(self.branch, "main", "b" * 40))
        result = self.retry()
        self.assertTrue(result["retry"])
        self.assertEqual(result["hint_count"], 1)
        self.assertNotIn("candidates", result)
        self.assertNotIn("candidate_count", result)
        self.assertEqual(self.signal["workflow_run"]["pull_requests"], [])
        self.assertTrue(any("state=closed&head=noah-l-frank%3A" in path and paginated
                            for path, paginated in self.requests))

    def test_any_current_push_completion_survives_reversed_delivery_and_pending_replacement(self):
        self.runs[701] = self.push_run(701, 349116380)
        for order in ((700, 701), (701, 700)):
            for identifier in order:
                with self.subTest(order=order, identifier=identifier):
                    self.assertTrue(self.retry(identifier)["retry"])
        # The existing mutex serializes actual retirement; subsequent callbacks
        # see the changed resource, not an event-election winner or durable pass.
        self.rows = [row for row in self.rows if row["name"] != self.branch]
        for identifier in (701, 700):
            self.assertFalse(self.retry(identifier)["retry"])

    def test_parent_leaf_and_codeql_callbacks_cover_all_seven_actual_targets(self):
        scopes = {"main": "main", "android-main": "android", "android-phone": "android-phone",
                  "android-vr": "android-vr", "android-vr-pico": "android-pico", "apple-main": "apple", "apple-ios": "ios"}
        for target, scope in scopes.items():
            branch = "fix/" + scope + "/earlier-source"
            self.rows = [row for row in self.rows if row["protected"]]
            self.rows.append({"name": branch, "sha": "a" * 40, "protected": False})
            self.closed = {branch: [self.closed_pr(branch, target, "a" * 40)]}
            workflow = 330551824 if target in {"android-phone", "android-vr-pico", "apple-ios"} else 350930890
            self.runs[700] = self.push_run(700, workflow, target)
            with self.subTest(target=target):
                self.assertTrue(self.retry()["retry"])

    def test_all_actual_activity_states_and_old_source_native_runs_hold_retry(self):
        for state in ("queued", "in_progress", "waiting", "pending", "requested"):
            self.active = [{"id": 800, "status": state, "path": ".github/workflows/native-tests.yml",
                            "head_branch": "main", "head_sha": "f" * 40, "pull_requests": []}]
            with self.subTest(state=state):
                self.assertFalse(self.retry()["retry"])
        self.active.clear()
        self.assertTrue(self.retry()["retry"])

    def test_active_manual_or_pr_relationship_is_checked_beyond_trigger_names(self):
        self.active = [{"id": 800, "status": "in_progress", "event": "workflow_dispatch",
                        "path": ".github/workflows/unlisted-device-diagnostic.yml", "head_branch": "test/ios/elsewhere",
                        "head_sha": "f" * 40, "pull_requests": [{"base": {"ref": "main"}}]}]
        self.assertFalse(self.retry()["retry"])
        self.active[0]["pull_requests"] = []
        self.assertTrue(self.retry()["retry"])

    def test_missing_exact_closed_head_and_keep_open_or_explicit_holds_do_not_retry(self):
        original = copy.deepcopy(self.closed)
        for closed in ({}, {self.branch: [self.closed_pr(self.branch, "main", "b" * 40)]}):
            self.closed = closed
            self.assertFalse(self.retry()["retry"])
        self.closed = original
        self.closed[self.branch][0]["labels"] = [{"name": "keep-branch"}]
        self.assertFalse(self.retry()["retry"])
        self.closed = copy.deepcopy(original)
        self.open_prs = [{"head": {"ref": self.branch, "repo": self.repository},
                          "base": {"ref": "main", "repo": self.repository}}]
        self.assertFalse(self.retry()["retry"])
        self.open_prs.clear()
        self.policy["holds"][self.branch] = "unfinished local work"
        self.assertFalse(self.retry()["retry"])

    def test_closed_unintegrated_hint_never_substitutes_for_the_full_ancestry_plan(self):
        self.integrated = False
        self.assertTrue(self.retry()["retry"])
        plan = self.module.make_plan(self.github, self.policy)
        self.assertEqual(plan["candidate_count"], 0)
        self.assertEqual(plan["held"][self.branch], ["not_fully_integrated"])

    def test_terminal_failure_can_wake_but_cannot_prove_integration(self):
        self.runs[700]["conclusion"] = "failure"
        self.integrated = False
        self.assertTrue(self.retry()["retry"])
        self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)

    def test_actual_sync_validation_dynamic_run_names_only_wake_a_current_retry(self):
        # These are the public names of the two completed PR1336/1337 validators.
        for identifier, gate in ((38965939432, 38965857534), (38965923127, 38965838299)):
            with self.subTest(run=identifier):
                name = f"Sync validation gate-{gate}-attempt-1"
                self.runs[identifier] = dict(self.manual_run(identifier, workflow=350930895),
                                             name=name, display_title=name, conclusion="failure")
                self.active = [dict(self.runs[identifier], id=800, status="in_progress", conclusion=None)]
                self.assertEqual(self.retry(identifier)["reason"], "terminal_candidates_still_held")
                self.active.clear()
                result = self.retry(identifier)
                self.assertTrue(result["retry"])
                self.assertEqual((result["trigger_run"], result["trigger_attempt"]), (identifier, 1))
                self.assertNotIn("candidates", result)
                self.assertNotIn("candidate_count", result)
                self.assertIn(("contents/.github/workflows/sync-validation.yml?ref=" + self.revision, False),
                              self.requests)
                self.integrated = False
                self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)

    def test_dynamic_run_name_does_not_replace_static_registration_or_source_identity(self):
        self.runs[700] = dict(self.manual_run(workflow=350930895),
                              name="Sync validation gate-38965857534-attempt-1")
        original = self.response
        for changes in ({"id": 350930894}, {"name": "Unreviewed workflow"},
                        {"path": ".github/workflows/sync-test-reuse.yml"}):
            def altered(suffix="", paginate=False):
                value = original(suffix, paginate)
                return dict(value, **changes) if suffix == "actions/workflows/350930895" else value
            with self.subTest(registration=changes), mock.patch.object(self.github, "get", side_effect=altered), \
                    self.assertRaisesRegex(self.module.CleanupError, "terminal_workflow_registration_changed"):
                self.retry()
        self.source_changes[self.runs[700]["path"]] = (
            b"name: Sync validation gate-38965857534-attempt-1\non:\n  workflow_dispatch:\n")
        with self.assertRaisesRegex(self.module.CleanupError, "terminal_workflow_source_name_changed"):
            self.retry()

    def test_dynamic_run_name_is_still_bound_to_the_actual_event_and_has_a_valid_shape(self):
        self.runs[700] = dict(self.manual_run(workflow=350930895),
                              name="Sync validation gate-38965857534-attempt-1")
        self.signal["workflow_run"] = dict(self.runs[700], name="Sync validation gate-1-attempt-1")
        with self.assertRaisesRegex(self.module.CleanupError, "invalid_terminal_push_run"):
            self.module.terminal_retry(self.github, self.policy, self.signal)
        for name in (None, "", 7, {}, []):
            self.runs[700]["name"] = name
            with self.subTest(name=name), self.assertRaisesRegex(self.module.CleanupError,
                                                               "invalid_terminal_push_run"):
                self.retry()

    def documentation_completion(self):
        identifier = 499999999
        filename = self.module.DOCUMENTATION_PUSH_FILENAME
        path = ".github/workflows/" + filename
        self.runs[700] = dict(self.push_run(700, 331326815), workflow_id=identifier, path=path)
        registration = {"id": identifier, "name": "Documentation checks", "path": path, "state": "active"}
        numeric = dict(registration)
        original = self.response
        def response(suffix="", paginate=False):
            if suffix == "actions/workflows/" + filename:
                return copy.deepcopy(registration)
            if suffix == "actions/workflows/" + str(identifier):
                return copy.deepcopy(numeric)
            if suffix.startswith("contents/" + path + "?ref="):
                raw = self.source_changes.get(path, b"name: Documentation checks\non:\n  push:\n")
                return {"path": path, "type": "file", "sha": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), "size": len(raw),
                    "encoding": "base64", "content": base64.b64encode(raw).decode()}
            return original(suffix, paginate)
        self.enterContext(mock.patch.object(self.github, "get", side_effect=response))
        return registration, numeric

    def test_new_documentation_push_registration_only_wakes_current_full_ancestry_plan(self):
        self.documentation_completion()
        self.assertTrue(self.retry()["retry"])
        self.integrated = False
        self.assertTrue(self.retry()["retry"], "completion supplies a hint, never integration authority")
        self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)
        self.assertEqual(self.module.make_plan(self.github, self.policy)["held"][self.branch],
                         ["not_fully_integrated"])
        self.source_changes[self.runs[700]["path"]] = b"name: Foreign checker\non: push\n"
        with self.assertRaisesRegex(self.module.CleanupError, "source_name_changed"):
            self.retry()

    def test_new_documentation_registration_and_native_context_are_exact(self):
        registration, numeric = self.documentation_completion()
        for target in self.module.DOCUMENTATION_PUSH_TARGETS:
            self.runs[700]["head_branch"] = target
            self.signal["workflow_run"] = copy.deepcopy(self.runs[700])
            self.assertEqual(self.module.terminal_run(self.github, self.signal)["head_branch"], target)
        self.runs[700]["head_branch"] = "main"
        original = dict(self.runs[700])
        for changes in ({"event": "workflow_dispatch"}, {"event": "pull_request"},
                        {"head_branch": "android-main"}, {"head_branch": "apple-main"},
                        {"path": ".github/workflows/documentation-push-owner-other.yml"},
                        {"name": "Unreviewed checker"}, {"workflow_id": True},
                        {"head_repository": {"id": 1, "full_name": "foreign/fork"}}):
            self.runs[700] = dict(original, **changes)
            with self.subTest(native=changes), self.assertRaises(self.module.CleanupError):
                self.retry()
        self.runs[700] = original
        for object_ in (registration, numeric):
            saved = dict(object_)
            for key, value in (("id", 7), ("name", "Unreviewed checker"),
                               ("path", ".github/workflows/documentation-checks.yml"),
                               ("state", "disabled_manually")):
                object_[key] = value
                with self.subTest(registration=object_ is registration, field=key), \
                        self.assertRaises(self.module.CleanupError):
                    self.retry()
                object_.clear(); object_.update(saved)

    def test_active_new_documentation_push_holds_cleanup_before_a_retry_hint(self):
        self.documentation_completion()
        self.active = [dict(self.runs[700], id=701, status="in_progress", conclusion=None)]
        self.assertEqual(self.retry()["reason"], "terminal_candidates_still_held")

    def test_foreign_repositories_events_and_workflow_identities_fail_closed(self):
        original = copy.deepcopy(self.runs[700])
        variants = [dict(event="pull_request"), dict(event="workflow_dispatch"), dict(status="in_progress"),
                    dict(workflow_id=123), dict(path=".github/workflows/branch-cleanup.yml"),
                    dict(name=None), dict(head_branch="test/main/not-permanent"),
                    dict(repository={"id": 1, "full_name": "overte-org/overte"}),
                    dict(head_repository={"id": 1, "full_name": "foreign/fork"})]
        for changes in variants:
            self.runs[700] = dict(copy.deepcopy(original), **changes)
            with self.subTest(changes=changes), self.assertRaises(self.module.CleanupError):
                self.retry()
        self.runs[700] = original
        self.signal["repository"] = {"id": 1, "full_name": "foreign/fork"}
        with self.assertRaises(self.module.CleanupError):
            self.retry()

    def test_unretained_callback_and_target_movement_do_not_retry(self):
        self.runs[700]["head_sha"] = "f" * 40
        self.comparisons["f" * 40] = False
        self.assertEqual(self.retry()["reason"], "terminal_source_not_retained")
        self.runs[700]["head_sha"] = self.revision
        self.reference_changes["main"] = "f" * 40
        self.assertEqual(self.retry()["reason"], "terminal_target_changed")

    def test_last_manual_completion_retries_current_heads_after_old_source_activity_clears(self):
        old = "f" * 40
        self.active = [{**self.manual_run(800, revision=old), "status": "in_progress", "conclusion": None}]
        self.assertEqual(self.retry()["reason"], "terminal_candidates_still_held")
        self.active.clear()
        self.runs[700] = self.manual_run(revision=old)
        with mock.patch.object(self.github, "activity_holds", wraps=self.github.activity_holds) as activity:
            result = self.retry()
        self.assertTrue(result["retry"])
        self.assertEqual((result["trigger_source_sha"], result["target_sha"], result["source_sha"]),
                         (old, self.revision, self.revision))
        self.assertEqual(activity.call_args.args[0], [{"branch": self.branch, "sha": "a" * 40,
                                                       "base": "main", "base_sha": self.revision}])
        self.assertIn(("compare/" + old + "..." + self.revision + "?per_page=1", False), self.requests)
        self.assertIn(("contents/.github/workflows/shared-sandbox-host-diagnostic.yml?ref=" + old, False), self.requests)
        self.assertNotIn("candidates", result)

    def test_retained_older_push_completion_is_also_only_a_current_hint(self):
        self.runs[700]["head_sha"] = "f" * 40
        result = self.retry()
        self.assertTrue(result["retry"])
        self.assertEqual(result["target_sha"], self.revision)
        self.assertEqual(result["trigger_source_sha"], "f" * 40)
        self.reference_changes["main"] = "e" * 40
        self.assertEqual(self.retry()["reason"], "terminal_target_changed")

    def test_manual_owner_event_main_target_attempt_and_workflow_identity_are_finite(self):
        original = self.manual_run()
        variants = [dict(event="push"), dict(event="pull_request"), dict(head_branch="apple-ios"),
                    dict(workflow_id=350930890), dict(path=".github/workflows/project-tests.yml"),
                    dict(name=None), dict(status="in_progress", conclusion=None),
                    dict(head_repository={"id": 1, "full_name": "foreign/fork"})]
        for changes in variants:
            self.runs[700] = {**copy.deepcopy(original), **changes}
            with self.subTest(changes=changes), self.assertRaises(self.module.CleanupError):
                self.retry()
        self.runs[700] = original
        self.signal["workflow_run"] = {**copy.deepcopy(original), "run_attempt": 2}
        with self.assertRaises(self.module.CleanupError):
            self.module.terminal_retry(self.github, self.policy, self.signal)

    def test_all_reviewed_manual_holders_wake_only_their_actual_current_permanent_target(self):
        expected = {330869250, 330869251, 330556274, 340529251, 372770820, 371274083,
                    373796501, 359712487, 331326815, 357615945, 367914894, 330643004,
                    330644216, 330643006, 330551824, 366778169, 350430503, 386334598,
                    350930894, 350930895}
        self.assertEqual(self.module.MANUAL_TERMINAL_WORKFLOWS, expected)
        self.assertNotIn(355150779, self.module.TERMINAL_WORKFLOWS, "cleanup must not wake itself")
        scopes = {"main": "main", "android-main": "android", "android-phone": "android-phone",
                  "android-vr": "android-vr", "android-vr-pico": "android-pico", "apple-main": "apple", "apple-ios": "ios"}
        for workflow in sorted(expected - {386334598}):
            for target, scope in scopes.items():
                branch = "fix/" + scope + "/manual-held-source"
                self.rows = [row for row in self.rows if row["protected"]]
                self.rows.append({"name": branch, "sha": "a" * 40, "protected": False})
                self.closed = {branch: [self.closed_pr(branch, target, "a" * 40)]}
                self.runs[700] = self.manual_run(target=target, revision="f" * 40, workflow=workflow)
                with self.subTest(workflow=workflow, target=target):
                    result = self.retry()
                    self.assertTrue(result["retry"])
                    self.assertEqual((result["target"], result["target_sha"], result["trigger_source_sha"]),
                                     (target, self.revision, "f" * 40))
                    self.assertNotIn("candidates", result)

    def test_registered_event_sets_do_not_admit_manual_only_pushes_or_cleanup_recursion(self):
        self.assertEqual(self.module.PUSH_TERMINAL_WORKFLOWS,
                         {330519645, 331117401, 340529251, 372770820, 373796501, 349116380,
                          359712487, 331326815, 330869252, 350930890, 330551824, 347471831})
        self.assertEqual(set(self.module.TERMINAL_WORKFLOWS), self.module.PUSH_TERMINAL_WORKFLOWS
                         | self.module.MANUAL_TERMINAL_WORKFLOWS)
        self.assertEqual(len(self.module.PUSH_TERMINAL_WORKFLOWS & self.module.MANUAL_TERMINAL_WORKFLOWS), 6)
        for workflow in self.module.MANUAL_TERMINAL_WORKFLOWS - self.module.PUSH_TERMINAL_WORKFLOWS:
            self.runs[700] = self.push_run(700, workflow)
            with self.subTest(workflow=workflow), self.assertRaises(self.module.CleanupError):
                self.retry()
        self.runs[700] = {**self.manual_run(), "workflow_id": 355150779}
        with self.assertRaises(self.module.CleanupError):
            self.retry()

    def test_other_manual_holders_do_not_admit_unprotected_targets_or_waive_remaining_activity(self):
        self.runs[700] = self.manual_run(target="feature/main/unprotected", workflow=367914894)
        with self.assertRaises(self.module.CleanupError):
            self.retry()
        self.runs[700] = self.manual_run(revision="f" * 40, workflow=367914894)
        self.active = [{**self.manual_run(800, revision="e" * 40, workflow=330869250),
                        "status": "in_progress", "conclusion": None}]
        self.assertEqual(self.retry()["reason"], "terminal_candidates_still_held")

    def test_older_manual_hint_still_holds_all_activity_states_and_current_topic_head(self):
        self.runs[700] = self.manual_run(revision="f" * 40)
        for state in ("queued", "in_progress", "waiting", "pending", "requested"):
            self.active = [{**self.manual_run(800, revision="e" * 40), "status": state, "conclusion": None}]
            with self.subTest(state=state):
                self.assertEqual(self.retry()["reason"], "terminal_candidates_still_held")
        self.active.clear()
        self.rows[-1]["sha"] = "b" * 40
        self.assertEqual(self.retry()["reason"], "no_current_closed_pr_hint")

    def test_retained_source_requires_complete_exact_ancestry_not_only_a_zero_behind_count(self):
        self.runs[700] = self.manual_run(revision="f" * 40)
        original = self.response
        for change in ({"status": "diverged"}, {"behind_by": 1}, {"merge_base_commit": {"sha": "e" * 40}},
                       {"behind_by": False}, {"merge_base_commit": {}}, {"status": "unknown"}):
            def altered(suffix="", paginate=False):
                value = original(suffix, paginate)
                return {**value, **change} if suffix.startswith("compare/") else value
            with self.subTest(change=change), mock.patch.object(self.github, "get", side_effect=altered):
                if change in ({"status": "diverged"}, {"behind_by": 1}, {"merge_base_commit": {"sha": "e" * 40}}):
                    self.assertEqual(self.retry()["reason"], "terminal_source_not_retained")
                else:
                    with self.assertRaisesRegex(self.module.CleanupError, "invalid_terminal_source_ancestry"):
                        self.retry()

    def test_manual_failure_can_only_wake_the_unchanged_full_ancestry_plan(self):
        self.runs[700] = self.manual_run(revision="f" * 40)
        self.runs[700]["conclusion"] = "failure"
        self.comparisons["f" * 40] = True
        self.integrated = False
        self.assertTrue(self.retry()["retry"])
        self.assertEqual(self.module.make_plan(self.github, self.policy)["candidate_count"], 0)

    def test_old_manual_cli_cannot_emit_authority_from_a_stale_trusted_checkout(self):
        old = self.revision
        for row in self.rows:
            if row["name"] == "main":
                row["sha"] = "f" * 40
        self.runs[700] = self.manual_run(revision=old)
        self.signal["workflow_run"] = copy.deepcopy(self.runs[700])
        code, result, output = self.cli_retry()
        self.assertEqual((code, output, result["status"]), (0, "retry=false\n", "deferred"))
        self.assertEqual(result["deleted"], [])

    def test_payload_cannot_impersonate_the_actual_api_attempt_or_source(self):
        for field, value in (("run_attempt", 2), ("head_sha", "f" * 40), ("name", "spoofed owner")):
            self.signal["workflow_run"] = copy.deepcopy(self.runs[700])
            self.signal["workflow_run"][field] = value
            with self.subTest(field=field), self.assertRaises(self.module.CleanupError):
                self.module.terminal_retry(self.github, self.policy, self.signal)

    def test_changed_workflow_source_name_or_corrupt_blob_cannot_start_a_retry(self):
        self.source_changes[self.runs[700]["path"]] = b"name: Unreviewed owner\non: push\n"
        with self.assertRaisesRegex(self.module.CleanupError, "source_name_changed"):
            self.retry()
        self.source_changes.clear()
        original = self.response
        def corrupt(suffix="", paginate=False):
            value = original(suffix, paginate)
            if suffix.startswith("contents/.github/workflows/"):
                value["sha"] = "f" * 40
            return value
        with mock.patch.object(self.github, "get", side_effect=corrupt), \
                self.assertRaisesRegex(self.module.CleanupError, "blob_mismatch"):
            self.retry()

    def test_incomplete_activity_inventory_never_means_quiet(self):
        original = self.response
        def incomplete(suffix="", paginate=False):
            return {"total_count": 1, "workflow_runs": []} if suffix.startswith("actions/runs?status=") else original(suffix, paginate)
        with mock.patch.object(self.github, "get", side_effect=incomplete), mock.patch.object(self.module.time, "sleep"), \
                self.assertRaisesRegex(self.module.CleanupError, "active_run_listing_incomplete"):
            self.retry()

    def cli_retry(self, event_name="workflow_run"):
        with tempfile.TemporaryDirectory(prefix="cleanup-terminal-cli-") as temporary:
            directory = Path(temporary)
            event, output, report = (directory / name for name in ("event.json", "output", "retry.json"))
            event.write_text(json.dumps(self.signal))
            context = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                       "GIT_CONFIG_VALUE_0": str(ROOT),
                       "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": FORK, "GITHUB_REPOSITORY_ID": "1319052603",
                       "GITHUB_EVENT_NAME": event_name, "GITHUB_RUN_ID": "999",
                       "GITHUB_WORKFLOW_REF": FORK + "/.github/workflows/branch-cleanup.yml@refs/heads/main"}
            with mock.patch.dict(os.environ, context, clear=True), mock.patch.object(self.module, "Github", return_value=self.github), \
                    mock.patch.object(sys, "argv", [str(SCRIPT), "retry", "--event", str(event), "--output", str(output), "--report", str(report)]), \
                    mock.patch.object(self.module, "make_plan", side_effect=AssertionError("hint cannot authorize a plan")), \
                    mock.patch.object(self.module, "GitStore", side_effect=AssertionError("preflight cannot touch backup or refs")):
                code = self.module.main()
            return code, json.loads(report.read_text()), output.read_text() if output.exists() else ""

    def test_read_only_retry_cli_never_plans_backs_up_or_deletes(self):
        code, result, output = self.cli_retry()
        self.assertEqual((code, output), (0, "retry=true\n"))
        self.assertEqual((result["status"], result["deleted"]), ("retry-ready", []))
        self.assertNotIn("backup_artifact_id", result)
        self.rows = [row for row in self.rows if row["name"] != self.branch]
        code, result, output = self.cli_retry()
        self.assertEqual((code, output, result["status"]), (0, "retry=false\n", "retry-held"))

    def test_stale_trusted_checkout_or_wrong_runner_event_never_outputs_retry_authority(self):
        code, result, output = self.cli_retry(event_name="workflow_dispatch")
        self.assertEqual((code, output, result["status"]), (1, "", "blocked"))
        for row in self.rows:
            if row["name"] == "main":
                row["sha"] = "f" * 40
        self.runs[700]["head_sha"] = "f" * 40
        self.signal["workflow_run"] = copy.deepcopy(self.runs[700])
        code, result, output = self.cli_retry()
        self.assertEqual((code, output, result["status"]), (0, "retry=false\n", "deferred"))
        self.assertEqual(result["deleted"], [])


class WorkflowSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/branch-cleanup.yml").read_text(encoding="utf-8")

    def test_runner_and_trusted_checkout_work_without_the_users_pc(self):
        self.assertIn("runs-on: ubuntu-24.04", self.source)
        self.assertNotIn("self-hosted", self.source)
        self.assertIn("repository: noah-l-frank/overte", self.source)
        self.assertIn("ref: main", self.source)
        self.assertIn("persist-credentials: false", self.source)
        checkout = self.source.split("- name: Plan from current GitHub state", 1)[0]
        self.assertNotIn("github.event.pull_request.head.sha", checkout)

    def test_fork_identity_and_serial_execution_are_explicit(self):
        self.assertIn("github.repository == 'noah-l-frank/overte'", self.source)
        self.assertIn("github.repository_id == '1319052603'", self.source)
        self.assertIn("group: branch-cleanup-noah-be-overte", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_artifact_upload_must_succeed_before_any_delete_step(self):
        backup = self.source.index("cleanup.py backup")
        upload = self.source.index("- name: Persist verified backup before any branch deletion")
        apply = self.source.index("cleanup.py apply")
        self.assertLess(backup, upload)
        self.assertLess(upload, apply)
        self.assertIn("if-no-files-found: error", self.source[upload:apply])
        self.assertNotIn("continue-on-error", self.source)
        self.assertIn("steps.backup.outputs.artifact-id", self.source[upload:apply])
        self.assertIn('--backup-dir "$RUNNER_TEMP/branch-cleanup/backup"', self.source[apply:])

    def test_report_mode_does_not_run_backup_or_apply(self):
        self.assertEqual(self.source.count("inputs.mode == 'apply'"), 5)
        self.assertIn("default: report", self.source)

    def test_verified_history_deferral_skips_planning_without_hiding_failures(self):
        plan = self.source.split("- name: Plan from current GitHub state", 1)[1].split(
            "- name: Build and verify a self-contained Git backup", 1)[0]
        self.assertIn("if: steps.history.outputs.deferred != 'true'", plan)
        self.assertNotIn("continue-on-error", self.source)

    def test_adoption_uses_a_scoped_app_and_runs_before_the_original_delete_plan(self):
        app = self.source.index("- name: Create repository-scoped history integration token")
        assess = self.source.index("adoption.py")
        plan = self.source.index("cleanup.py plan")
        self.assertLess(app, assess)
        self.assertLess(assess, plan)
        token = self.source[app:assess]
        self.assertIn("owner: noah-l-frank", token)
        self.assertIn("repositories: overte", token)
        self.assertIn("permission-contents: write", token)
        self.assertIn("permission-pull-requests: write", token)
        self.assertNotIn("permission-administration", token)
        self.assertNotIn("permission-checks", token)
        self.assertIn("inputs.mode == 'apply'", token)
        self.assertIn("github.workflow_ref == 'noah-l-frank/overte/.github/workflows/branch-cleanup.yml@refs/heads/main'", self.source)

    def test_closed_manual_schedule_and_finite_push_retry_keep_trusted_execution(self):
        module = load_cleanup()
        retry = self.source.split("  workflow_run:\n", 1)[1].split("  schedule:", 1)[0]
        names = re.findall(r"^      - (.+)$", retry, re.M)
        dynamic = 'Sync validation gate-*-attempt-*'
        self.assertEqual(set(names), {name for name, _ in module.TERMINAL_WORKFLOWS.values()} | {dynamic})
        self.assertEqual(len(names), 27)
        import fnmatch
        for name in ('Sync validation gate-38978630943-attempt-1',
                     'Sync validation gate-38965857534-attempt-2'):
            self.assertTrue(fnmatch.fnmatchcase(name, dynamic))
        for name in ('Automatic branch cleanup', 'Unreviewed workflow',
                     'Sync validation other', 'Other gate-1-attempt-1'):
            self.assertFalse(fnmatch.fnmatchcase(name, dynamic))
        self.assertNotIn('*', names)
        self.assertIn("types: [completed]", retry)
        branches = re.search(r"branches: \[([^]]+)\]", retry).group(1).split(", ")
        self.assertEqual(set(branches), PERMANENT)
        self.assertIn("  pull_request_target:\n    types: [closed]", self.source)
        self.assertIn('cron: "7,22,37,52 * * * *"', self.source)
        self.assertIn("  workflow_dispatch:", self.source)
        self.assertNotIn("github.event.workflow_run.head_sha", self.source)
        self.assertNotIn("github.event.workflow_run.conclusion", self.source)

    def test_terminal_preflight_precedes_token_and_adoption_and_can_only_gate_full_plan(self):
        retry = self.source.index("cleanup.py retry")
        token = self.source.index("- name: Create repository-scoped history integration token")
        history = self.source.index("- name: Assess adopted work and maintain checked history PRs")
        plan = self.source.index("- name: Plan from current GitHub state")
        self.assertLess(retry, token)
        self.assertLess(token, history)
        for block in (self.source[token:history], self.source[history:plan]):
            self.assertIn("github.event_name != 'workflow_run'", block)
        self.assertIn("steps.retry.outputs.retry == 'true'", self.source[plan:])
        self.assertIn("github.event.workflow_run.event == 'push'", self.source)
        self.assertIn("github.event.workflow_run.workflow_id == 386334598", self.source)
        self.assertIn("github.event.workflow_run.event == 'workflow_dispatch'", self.source)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.source)
        manual = re.search(r"contains\(fromJSON\('(\[[0-9,]+\])'\), github.event.workflow_run.workflow_id\)", self.source)
        self.assertIsNotNone(manual)
        self.assertEqual(set(json.loads(manual.group(1))), load_cleanup().MANUAL_TERMINAL_WORKFLOWS - {386334598})

    def test_preflight_adoption_deferral_skips_plan_and_existing_zero_candidate_dependents(self):
        plan = self.source.split("- name: Plan from current GitHub state", 1)[1].split("- name: Build and verify", 1)[0]
        self.assertIn("if: steps.history.outputs.deferred != 'true'", plan)
        self.assertEqual(self.source.count("fromJSON(steps.plan.outputs.candidate_count || '0') > 0"), 3)
        self.assertIn("if: always()", self.source.split("- name: Retain plan and outcome", 1)[1])

    def test_terminal_context_still_requires_trusted_main(self):
        module = load_cleanup()
        context = {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": FORK,
            "GITHUB_REPOSITORY_ID": "1319052603", "GITHUB_EVENT_NAME": "workflow_run",
            "GITHUB_WORKFLOW_REF": FORK + "/.github/workflows/branch-cleanup.yml@refs/heads/main",
        }
        with mock.patch.dict(os.environ, context, clear=True):
            module.trusted_runtime()
            for change in ({"GITHUB_ACTIONS": "false"}, {"GITHUB_REPOSITORY": "overte-org/overte"},
                           {"GITHUB_REPOSITORY_ID": "1"}, {"GITHUB_EVENT_NAME": "push"},
                           {"GITHUB_WORKFLOW_REF": FORK + "/.github/workflows/branch-cleanup.yml@refs/heads/untrusted"}):
                with self.subTest(change=change), mock.patch.dict(os.environ, change):
                    with self.assertRaises(module.CleanupError):
                        module.trusted_runtime()


if __name__ == "__main__":
    unittest.main(verbosity=2)
