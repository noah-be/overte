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
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/branch-cleanup/cleanup.py"
POLICY_PATH = ROOT / ".github/branch-cleanup.json"
FORK = "noah-be/overte"
FORK_URL = "https://github.com/noah-be/overte.git"
PERMANENT = {
    "main", "android-main", "android-phone", "android-vr", "android-vr-pico",
    "apple-main", "apple-ios", "linux-main", "windows-main",
}


def load_cleanup():
    spec = importlib.util.spec_from_file_location("branch_cleanup_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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

    def verify_archive_protection(self):
        self.events.append(("verify_archive_protection",))


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

    def test_valid_policy_binds_exact_fork_and_nine_permanent_branches(self):
        validated = self.module.validate_policy(self.policy)
        self.assertEqual(validated["repository"], FORK)
        self.assertEqual(validated["repository_id"], 1319052603)
        self.assertEqual(set(validated["permanent_branches"]), PERMANENT)
        self.assertEqual(validated["archive_tag_prefix"], "archive/merged/")

    def test_foreign_repository_or_repository_id_is_rejected(self):
        for key, value in (("repository", "overte-org/overte"), ("repository", "someone/overte"),
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

    def test_archive_prefix_and_retention_cannot_be_redirected(self):
        for key, value in (("archive_tag_prefix", "release/"), ("artifact_retention_days", 0),
                           ("artifact_retention_days", 31)):
            with self.subTest(key=key, value=value):
                with self.assertRaises(self.module.CleanupError):
                    self.module.validate_policy({**self.policy, key: value})

    def test_scope_mapping_uses_the_correct_permanent_target(self):
        scopes = {
            "main": "main", "android": "android-main", "android-main": "android-main",
            "android-phone": "android-phone", "android-vr": "android-vr",
            "android-pico": "android-vr-pico", "apple": "apple-main",
            "ios": "apple-ios", "linux": "linux-main", "windows": "windows-main",
        }
        for scope, target in scopes.items():
            with self.subTest(scope=scope):
                self.assertEqual(self.module.scope_target(f"task/{scope}/100-work"), target)
        self.assertIsNone(self.module.scope_target("mystery/unknown/work"))

    def test_integrated_current_head_is_eligible_without_an_age_delay(self):
        candidates, _ = self.select()
        self.assertEqual(candidates, [{
            "branch": self.candidate, "sha": self.sha,
            "base": "main", "base_sha": self.base_sha,
        }])

    def test_nine_permanent_branches_are_always_excluded(self):
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
        with mock.patch.object(self.github, "get", side_effect=response):
            with self.assertRaises(self.module.CleanupError):
                self.github.activity_holds([self.candidate], self.policy)

    def test_missing_active_run_inventory_fields_fail_closed(self):
        def response(suffix="", paginate=False):
            return {} if suffix.startswith("actions/runs?") else []
        with mock.patch.object(self.github, "get", side_effect=response):
            with self.assertRaises(self.module.CleanupError):
                self.github.activity_holds([self.candidate], self.policy)

    def test_github_api_requests_are_read_only_and_explicitly_bound_to_the_fork(self):
        result = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        with mock.patch.object(self.module, "run", return_value=result) as run:
            self.github.get("branches?per_page=100")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["gh", "api", "--method", "GET"])
        self.assertEqual(command[4], "repos/noah-be/overte/branches?per_page=100")
        for suffix in ("/repos/overte-org/overte", "https://github.com/overte-org/overte", "../overte"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(self.module.CleanupError):
                    self.github.get(suffix)

    def test_safe_github_compare_syntax_is_not_mistaken_for_path_traversal(self):
        endpoint = "compare/" + "a" * 40 + "..." + "b" * 40 + "?per_page=1"
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with mock.patch.object(self.module, "run", return_value=result) as run:
            self.github.get(endpoint)
        self.assertEqual(run.call_args.args[0][4], "repos/noah-be/overte/" + endpoint)

    def test_foreign_owner_or_native_unguarded_cleanup_is_rejected(self):
        valid = {"full_name": FORK, "id": 1319052603, "default_branch": "main", "delete_branch_on_merge": False}
        for change in ({"full_name": "overte-org/overte"}, {"id": 42}, {"delete_branch_on_merge": True}):
            with self.subTest(change=change):
                with mock.patch.object(self.github, "get", return_value={**valid, **change}):
                    with self.assertRaises(self.module.CleanupError):
                        self.github.verify_owner()


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
        self.tag = "archive/merged/" + self.fixture.merged_sha

    def pushes(self):
        return [event[2] for event in self.events if event[:2] == ("git", "push")]

    def assert_branch_exists(self, sha=None):
        self.assertEqual(
            self.fixture.remote_ref("refs/heads/" + self.fixture.merged_branch),
            sha or self.fixture.merged_sha,
        )

    def test_annotated_remote_archive_is_verified_before_exact_leased_deletion(self):
        self.store.backup_tags(self.candidates, self.github)
        tag_ref = "refs/tags/" + self.tag
        self.assertEqual(self.fixture.git(self.fixture.remote, "cat-file", "-t", tag_ref).stdout.strip(), "tag")
        self.assertEqual(self.fixture.rev(self.fixture.remote, tag_ref + "^{}"), self.fixture.merged_sha)
        deleted = self.store.delete(self.candidates, self.github)
        self.assertEqual(deleted, [self.fixture.merged_branch])
        self.assertIsNone(self.fixture.remote_ref("refs/heads/" + self.fixture.merged_branch))
        # Recovery reads a real archived file after the branch itself has gone.
        recovered = self.fixture.git(self.fixture.remote, "show", tag_ref + ":integrated.txt").stdout
        self.assertEqual(recovered, "integrated.txt\n")
        delete_push = self.pushes()[-1]
        self.assertIn("--atomic", delete_push)
        self.assertIn(
            "--force-with-lease=refs/heads/" + self.fixture.merged_branch + ":" + self.fixture.merged_sha,
            delete_push,
        )

    def test_owner_is_reverified_before_every_mutating_push(self):
        self.store.backup_tags(self.candidates, self.github)
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
        self.assertGreaterEqual(push_count, 2)

    def test_concurrent_new_work_is_preserved_by_the_real_remote_lease(self):
        self.store.backup_tags(self.candidates, self.github)
        new_sha = self.fixture.advance_remote_branch(self.fixture.merged_branch)
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assert_branch_exists(new_sha)

    def test_missing_archive_prevents_deletion(self):
        before = len(self.pushes())
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assertEqual(len(self.pushes()), before)
        self.assert_branch_exists()

    def test_lightweight_tag_is_not_accepted_as_a_recovery_archive(self):
        self.fixture.git(self.fixture.remote, "update-ref", "refs/tags/" + self.tag, self.fixture.merged_sha)
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assert_branch_exists()

    def test_archive_pointing_to_a_different_commit_prevents_deletion(self):
        self.fixture.git(self.fixture.remote, "tag", "-a", self.tag, self.fixture.initial, "-m", "wrong recovery commit")
        with self.assertRaises(self.module.CleanupError):
            self.store.delete(self.candidates, self.github)
        self.assert_branch_exists()

    def test_archive_protection_failure_prevents_archive_push(self):
        self.github.verify_archive_protection = mock.Mock(side_effect=self.module.CleanupError("protection unavailable"))
        with self.assertRaises(self.module.CleanupError):
            self.store.backup_tags(self.candidates, self.github)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_effective_push_url_rewrite_to_upstream_is_rejected(self):
        self.store.git("config", "url.https://github.com/overte-org/overte.git.pushInsteadOf", FORK_URL)
        with self.assertRaises(self.module.CleanupError):
            self.store.backup_tags(self.candidates, self.github)
        self.assertFalse(self.pushes())
        self.assert_branch_exists()

    def test_push_url_change_after_backup_is_rejected_before_delete(self):
        self.store.backup_tags(self.candidates, self.github)
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

    def test_rerun_after_deletion_is_a_noop_and_preserves_the_archive(self):
        self.store.backup_tags(self.candidates, self.github)
        self.store.delete(self.candidates, self.github)
        branches = [{"name": branch, "sha": self.fixture.rev(self.fixture.remote, branch), "protected": True}
                    for branch in sorted(PERMANENT)]
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        candidates, _ = self.module.select_candidates(branches, policy, {})
        self.assertFalse(candidates)
        before = len(self.pushes())
        self.assertEqual(self.store.delete(candidates, self.github), [])
        self.assertEqual(len(self.pushes()), before)
        self.assertEqual(self.fixture.rev(self.fixture.remote, "refs/tags/" + self.tag + "^{}"), self.fixture.merged_sha)

    def test_two_branch_names_at_the_same_commit_share_one_valid_archive(self):
        alias = "fix/main/integrated-alias"
        self.fixture.git(self.fixture.seed, "branch", alias, self.fixture.merged_sha)
        self.fixture.git(self.fixture.seed, "push", "-q", "fixture", f"refs/heads/{alias}:refs/heads/{alias}")
        candidates = self.candidates + [{**self.candidates[0], "branch": alias}]
        self.store.fetch(candidates)
        self.store.backup_tags(candidates, self.github)
        self.assertEqual(set(self.store.delete(candidates, self.github)), {self.fixture.merged_branch, alias})
        self.assertIsNone(self.fixture.remote_ref("refs/heads/" + alias))
        self.assertEqual(self.fixture.rev(self.fixture.remote, "refs/tags/" + self.tag + "^{}"), self.fixture.merged_sha)

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


class WorkflowSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/branch-cleanup.yml").read_text(encoding="utf-8")

    def test_runner_and_trusted_checkout_work_without_the_users_pc(self):
        self.assertIn("runs-on: ubuntu-24.04", self.source)
        self.assertNotIn("self-hosted", self.source)
        self.assertIn("repository: noah-be/overte", self.source)
        self.assertIn("ref: main", self.source)
        self.assertIn("persist-credentials: false", self.source)
        checkout = self.source.split("- name: Plan from current GitHub state", 1)[0]
        self.assertNotIn("github.event.pull_request.head.sha", checkout)

    def test_fork_identity_and_serial_execution_are_explicit(self):
        self.assertIn("github.repository == 'noah-be/overte'", self.source)
        self.assertIn("github.repository_id == '1319052603'", self.source)
        self.assertIn("group: branch-cleanup-noah-be-overte", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_artifact_upload_must_succeed_before_any_delete_step(self):
        archive = self.source.index("cleanup.py archive")
        upload = self.source.index("- name: Persist verified backup before any branch deletion")
        apply = self.source.index("cleanup.py apply")
        self.assertLess(archive, upload)
        self.assertLess(upload, apply)
        self.assertIn("if-no-files-found: error", self.source[upload:apply])
        self.assertNotIn("continue-on-error", self.source)
        self.assertIn("steps.backup.outputs.artifact-id", self.source[upload:apply])
        self.assertIn('--backup-dir "$RUNNER_TEMP/branch-cleanup/backup"', self.source[apply:])

    def test_report_mode_does_not_run_archive_or_apply(self):
        self.assertEqual(self.source.count("inputs.mode == 'apply'"), 3)
        self.assertIn("default: report", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
