#!/usr/bin/env python3
"""Offline isolated-consumer regressions using tiny immutable suite fixtures."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest

import execution
import inputs
import runtime


SPEC = importlib.util.spec_from_file_location("test_isolated_sync_validation", Path(__file__).with_name("validate-sync.py"))
VALIDATION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(VALIDATION)


class EvidenceError(ValueError):
    pass


class FakeApi:
    def __init__(self, repository, pr):
        self.repository, self.pr = repository, pr
        self.calls = []

    def json(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "repos/noah-l-frank/overte":
            return deepcopy(self.repository)
        if endpoint == "repos/noah-l-frank/overte/pulls/42":
            return deepcopy(self.pr)
        raise AssertionError("unregistered read-only API fixture")


class IsolatedConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-sync-consumer-")
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.candidate = self.output / "candidate"
        self.candidate.mkdir()
        (self.candidate / "tests").mkdir()
        (self.candidate / "libraries").mkdir()
        for directory in ("ios", "interface"):
            (self.candidate / directory).mkdir()
            (self.candidate / directory / ".keep").write_text("fixture root\n", encoding="utf-8")
        (self.candidate / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        (self.candidate / "tests/platform-profile.json").write_text(
            json.dumps({"schema": 1, "platform": "shared", "suites": []}), encoding="utf-8")
        (self.candidate / "tests/control.py").write_text("# Trusted fixture control identity\n", encoding="utf-8")
        for name in ("alpha", "beta"):
            (self.candidate / "tests" / (name + ".py")).write_text(
                "from pathlib import Path\nimport os\n"
                "with Path(os.environ['FIXTURE_EXECUTION_LOG']).open('a') as log:\n"
                f"    log.write('{name}\\n')\n"
                "assert not any(os.environ.get(key) for key in ('GH_TOKEN','GITHUB_TOKEN','GITHUB_OUTPUT','GITHUB_ENV','GITHUB_PATH','GITHUB_STATE'))\n"
                f"assert os.environ.get('FIXTURE_FAIL_{name.upper()}') != '1'\n",
                encoding="utf-8")
            (self.candidate / "libraries" / (name + ".cpp")).write_text("candidate implementation\n", encoding="utf-8")
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Isolated consumer fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "Create immutable consumer fixture")
        self.commit, self.tree_sha = execution.checkout_identity(self.candidate)
        self.tree = inputs.full_tree(self.candidate)
        self.environment = {"toolchain": "prepared-test-host", "qt": "6", "backend": "software"}
        self.registry = {"schema": 1, "control_inputs": ["tests/control.py"], "suites": {}}
        for name in ("alpha", "beta"):
            self.registry["suites"][name] = {
                "command": ["python", "tests/" + name + ".py"], "layer": "quick", "scope": "content",
                "environment": "fixture-host", "closure": {"kind": "patterns",
                    "inputs": ["tests/" + name + ".py", "libraries/" + name + ".cpp"],
                    "required": ["tests/" + name + ".py", "libraries/" + name + ".cpp"]},
            }
        self.repository = {"full_name": "noah-l-frank/overte", "id": 1319052603}
        self.base, self.parent = "b" * 40, "a" * 40
        self.pr = {"number": 42, "state": "open", "mergeable": True, "merge_commit_sha": self.commit,
                   "base": {"ref": "apple-main", "sha": self.base},
                   "head": {"ref": "main", "sha": self.parent, "repo": {"id": 1319052603}}}
        self.request = SimpleNamespace(
            repository="noah-l-frank/overte", repository_id=1319052603, number=42,
            base="apple-main", base_sha=self.base, head="main", head_sha=self.parent,
            head_repository_id=1319052603, merge_sha=self.commit, parent="main", parent_sha=self.parent,
            profile="apple-family", classification="direct", repair_paths=(), changed_paths=("libraries/alpha.cpp",),
        )
        self.args = SimpleNamespace(candidate=self.candidate, repository="noah-l-frank/overte", pull_request=42,
                                    mode="reuse", profile="apple-family", base_sha=self.base,
                                    head_sha=self.parent, merge_sha=self.commit,
                                    junit=self.output / "results.xml", receipt=self.output / "validation.json")
        self.api = FakeApi(self.repository, self.pr)
        self.evidence = self.make_evidence()
        self.gate = SimpleNamespace(
            load_config=lambda: {"repository": "noah-l-frank/overte", "repository_id": 1319052603},
            effective_pr_context=lambda event, api: None,
            classify_event=lambda event, config, api: self.request,
            verify_evidence=lambda api, config, request: deepcopy(self.evidence),
            branch_sha=lambda api, repository, branch: self.base if branch == "apple-main" else self.parent,
            parse_time=lambda value, label: datetime.fromisoformat(value.replace("Z", "+00:00")),
            EvidenceError=EvidenceError,
            GateError=ValueError,
            paginate_pull_files=lambda *arguments: [{"filename": "libraries/alpha.cpp", "status": "modified"}],
            changed_paths=lambda documents: {item[key] for item in documents for key in ("filename", "previous_filename") if key in item},
        )
        self.log = self.output / "executed.log"

    def git(self, *arguments):
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *arguments], cwd=self.candidate,
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def make_evidence(self, parent_tree=None):
        parent_tree = self.tree if parent_tree is None else parent_tree
        now = datetime.now(timezone.utc)
        return {
            "environment": self.environment, "parent_inputs": deepcopy(parent_tree), "candidate_inputs": deepcopy(self.tree),
            "results": {"suites": {name: {"status": "passed", "fingerprint": inputs.suite_fingerprint(
                self.registry, name, parent_tree, self.environment)} for name in self.registry["suites"]}},
            "evidence_digest": "sha256:" + "e" * 64, "parent_branch": "main", "parent_commit": self.parent,
            "parent_tree": "f" * 40, "workflow": {"run_id": 9001, "run_attempt": 3},
            "qualified_at": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

    def validate(self, *, actual_environment=None, runtime_failure=None, execute_override=None,
                 ci_execute_override=None, extra_environment=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(VALIDATION, "_gate", return_value=self.gate))
            stack.enter_context(patch.object(inputs, "load_registry", return_value=deepcopy(self.registry)))
            runtime_options = {"side_effect": runtime_failure} if runtime_failure is not None else {
                "return_value": self.environment if actual_environment is None else actual_environment}
            stack.enter_context(patch.object(runtime, "capture_host_environment", **runtime_options))
            stack.enter_context(patch.dict(os.environ, {"FIXTURE_EXECUTION_LOG": str(self.log),
                "GH_TOKEN": "trusted-read-token", "GITHUB_TOKEN": "trusted-read-token",
                "GITHUB_OUTPUT": "private-output", "GITHUB_ENV": "private-environment",
                "GITHUB_PATH": "private-path", "GITHUB_STATE": "private-state", **(extra_environment or {})}))
            if execute_override is not None:
                stack.enter_context(patch.object(execution, "execute", side_effect=execute_override))
            if ci_execute_override is not None:
                stack.enter_context(patch.object(VALIDATION, "_execute_ci", side_effect=ci_execute_override))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            return VALIDATION.validate_sync(self.args, api=self.api)

    def executed(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_full_reuse_empty_product_profile_executes_zero_shared_tests(self):
        result = self.validate()
        self.assertEqual(result["mode"], "reuse")
        self.assertEqual(result["reused_suites"], ["alpha", "beta"])
        self.assertEqual(result["executed_suites"], [])
        self.assertEqual(self.executed(), [])
        self.assertEqual(result["parent_evidence"]["workflow"], {"run_id": 9001, "run_attempt": 3})
        self.assertEqual(result["parent_evidence"]["expires_at"], self.evidence["expires_at"])
        self.assertEqual(json.loads(self.args.receipt.read_text()), result)

    def test_pre_reuse_and_execution_capture_observe_the_same_effective_child_environment(self):
        captures = []

        def capture():
            captures.append({name: os.environ.get(name) for name in (
                "PATH", "VIRTUAL_ENV", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
                "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_OUTPUT",
            )})
            return self.environment

        result = self.validate(runtime_failure=capture)
        self.assertEqual(len(captures), 3, "pre-reuse, before-execution and after-execution observations are required")
        self.assertTrue(all(value == captures[0] for value in captures))
        self.assertEqual(captures[0]["GIT_CONFIG_COUNT"], "2")
        self.assertTrue(captures[0]["PATH"].startswith(str(Path(VALIDATION.sys.executable).parent) + os.pathsep))
        self.assertIsNone(captures[0]["GH_TOKEN"])
        self.assertEqual(result["reused_suites"], ["alpha", "beta"])

    def test_normal_reuse_keeps_exactly_one_token_free_branch_differential(self):
        original = VALIDATION._differential
        calls = []

        def differential(candidate, request, documents):
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("GITHUB_OUTPUT", os.environ)
            calls.append(request.profile)
            return original(candidate, request, documents)

        with patch.object(VALIDATION, "_differential", side_effect=differential):
            result = self.validate()
        self.assertEqual(calls, ["apple-family"])
        self.assertEqual(result["reused_suites"], ["alpha", "beta"])

    def test_normal_reuse_cannot_skip_a_failed_branch_differential(self):
        with patch.object(VALIDATION, "_differential", side_effect=ValueError("invalid changed JSON")), self.assertRaises(ValueError):
            self.validate()
        self.assertEqual(self.executed(), [])
        self.assertFalse(self.args.receipt.exists())

    def test_historical_child_source_difference_executes_only_affected_suite(self):
        parent_tree = deepcopy(self.tree)
        parent_tree["libraries/alpha.cpp"]["sha"] = "d" * 40
        self.evidence = self.make_evidence(parent_tree)
        result = self.validate()
        self.assertEqual(result["mode"], "partial-reuse")
        self.assertEqual(result["reused_suites"], ["beta"])
        self.assertEqual(result["executed_suites"], ["alpha"])
        self.assertEqual(self.executed(), ["alpha"])

    def test_actual_runtime_difference_forces_complete_shared_execution(self):
        result = self.validate(actual_environment=self.environment | {"qt": "5"})
        self.assertEqual(result["mode"], "fallback")
        self.assertEqual(result["reused_suites"], [])
        self.assertEqual(set(self.executed()), {"alpha", "beta"})

    def test_missing_or_unsupported_proof_falls_back_without_matching_unknown(self):
        self.gate.verify_evidence = lambda *arguments: (_ for _ in ()).throw(EvidenceError("unavailable"))
        result = self.validate()
        self.assertEqual(result["reused_suites"], [])
        self.assertEqual(set(self.executed()), {"alpha", "beta"})

    def test_unknown_actual_runtime_executes_all_without_reusable_identity(self):
        result = self.validate(runtime_failure=runtime.RuntimeIdentityError("unsupported runtime"))
        self.assertEqual(result["reused_suites"], [])
        self.assertEqual(set(self.executed()), {"alpha", "beta"})
        self.assertFalse(result["execution"]["reusable"])
        self.assertIsNone(result["execution"]["environment"])

    def test_explicit_fallback_never_requires_parent_artifact(self):
        self.args.mode = "fallback"
        self.gate.verify_evidence = lambda *arguments: (_ for _ in ()).throw(AssertionError("must not read proof"))
        result = self.validate()
        self.assertEqual(result["mode"], "fallback")
        self.assertEqual(set(self.executed()), {"alpha", "beta"})

    def test_selected_failure_cannot_emit_successful_validation_receipt(self):
        self.args.mode = "fallback"
        with self.assertRaises(VALIDATION.ValidationError):
            self.validate(extra_environment={"FIXTURE_FAIL_ALPHA": "1"})
        self.assertFalse(self.args.receipt.exists())

    def test_missing_persisted_execution_receipt_cannot_authorize_success(self):
        with self.assertRaises(VALIDATION.ValidationError):
            self.validate(execute_override=lambda *arguments, **keywords: (0, {"conclusion": "success"}))
        self.assertFalse(self.args.receipt.exists())

    def test_unexecuted_required_suite_cannot_hide_in_success_receipt(self):
        original = execution.execute
        self.args.mode = "fallback"

        def omit(candidate, **options):
            options["suite_names"] = ["alpha"]
            return original(candidate, **options)

        with self.assertRaises(VALIDATION.ValidationError):
            self.validate(execute_override=omit)
        self.assertFalse(self.args.receipt.exists())

    def test_actual_execution_environment_change_rejects_remaining_reuse_without_retry(self):
        original = execution.execute

        def drift(candidate, **options):
            with patch.object(runtime, "capture_host_environment", return_value=self.environment | {"qt": "5"}):
                return original(candidate, **options)

        with self.assertRaises(VALIDATION.ValidationError):
            self.validate(execute_override=drift)
        self.assertEqual(self.executed(), [])

    def test_execution_expansion_to_all_shared_removes_effective_reuse(self):
        original = execution.execute

        def fallback(candidate, **options):
            with patch.object(runtime, "capture_host_environment", side_effect=runtime.RuntimeIdentityError("unsupported")):
                return original(candidate, **options)

        result = self.validate(execute_override=fallback)
        self.assertEqual(result["reused_suites"], [])
        self.assertEqual(set(result["executed_suites"]), {"alpha", "beta"})
        self.assertFalse(result["execution"]["reusable"])

    def test_ordinary_nonmatching_or_repair_reuse_cannot_run(self):
        for scenario in ("ordinary", "wrong-profile", "repair", "wrong-commit"):
            with self.subTest(scenario=scenario):
                old_classifier, old_profile, old_repairs, old_merge = self.gate.classify_event, self.args.profile, self.request.repair_paths, self.args.merge_sha
                if scenario == "ordinary":
                    self.gate.classify_event = lambda *arguments: None
                elif scenario == "wrong-profile":
                    self.args.profile = "apple-ios"
                elif scenario == "repair":
                    self.request.repair_paths = ("ios/source.cpp",)
                else:
                    self.args.merge_sha = "c" * 40
                with self.assertRaises(VALIDATION.ValidationError):
                    self.validate()
                self.gate.classify_event, self.args.profile, self.request.repair_paths, self.args.merge_sha = old_classifier, old_profile, old_repairs, old_merge
        self.assertEqual(self.executed(), [])

    def test_local_candidate_tree_must_match_verified_api_tree(self):
        self.evidence["candidate_inputs"]["libraries/alpha.cpp"]["sha"] = "d" * 40
        with self.assertRaises(VALIDATION.ValidationError):
            self.validate()
        self.assertEqual(self.executed(), [])

    def test_live_parent_or_pull_request_drift_after_execution_fails_closed(self):
        original = execution.execute

        def moved(candidate, **options):
            result = original(candidate, **options)
            self.api.pr["head"]["sha"] = "d" * 40
            return result

        with self.assertRaises(VALIDATION.ValidationError):
            self.validate(execute_override=moved)
        self.assertFalse(self.args.receipt.exists())

    def test_final_parent_ref_and_original_expiry_are_rechecked(self):
        self.gate.branch_sha = lambda api, repository, branch: self.base if branch == "apple-main" else "d" * 40
        with self.assertRaises(VALIDATION.ValidationError):
            self.validate()
        self.assertFalse(self.args.receipt.exists())
        self.gate.branch_sha = lambda api, repository, branch: self.base if branch == "apple-main" else self.parent
        self.evidence["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        # The fake verifier deliberately omits expiry validation so this tests
        # the consumer's final check rather than the already-tested live gate.
        with self.assertRaises(VALIDATION.ValidationError):
            self.validate()
        self.assertFalse(self.args.receipt.exists())

    def test_platform_suites_always_execute_even_with_full_shared_reuse(self):
        profile = {"schema": 1, "platform": "android", "suites": [
            {"name": "product", "entrypoint": "tests/product.py", "interpreter": "python"}]}
        (self.candidate / "tests/platform-profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (self.candidate / "tests/product.py").write_text(
            "from pathlib import Path\nimport os\nPath(os.environ['FIXTURE_EXECUTION_LOG']).write_text('product\\n')\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "Add declared product fixture")
        self.commit, self.tree_sha = execution.checkout_identity(self.candidate)
        self.tree = inputs.full_tree(self.candidate)
        self.request.merge_sha = self.args.merge_sha = self.api.pr["merge_commit_sha"] = self.commit
        self.evidence = self.make_evidence()
        result = self.validate()
        self.assertEqual(result["reused_suites"], ["alpha", "beta"])
        self.assertEqual(self.executed(), ["product"])
        self.assertEqual(set(result["execution"]["platform_results"]), {"product"})

    def test_bounded_documentation_skips_host_capture_and_execution(self):
        self.args.profile = self.request.profile = "documentation"
        self.request.changed_paths = ("README.md",)
        documents = [{"filename": "README.md", "status": "modified"}]
        self.gate.paginate_pull_files = lambda *arguments: documents
        self.gate.changed_paths = lambda documents: {item["filename"] for item in documents}
        with patch.object(VALIDATION, "_differential") as differential, \
                patch.object(execution, "execute", side_effect=AssertionError("host execution is unnecessary")):
            result = self.validate(runtime_failure=AssertionError("host capture is unnecessary"))
        differential.assert_called_once()
        self.assertEqual(result["mode"], "documentation")
        self.assertIsNone(result["execution"])
        self.assertTrue(self.args.junit.exists())

    def test_bounded_tool_profile_uses_only_trusted_token_free_tool_helper(self):
        self.args.profile = self.request.profile = "tool-dependencies"
        self.request.changed_paths = ("server-console/package-lock.json",)
        documents = [{"filename": self.request.changed_paths[0], "status": "modified"}]
        self.gate.paginate_pull_files = lambda *arguments: documents
        self.gate.changed_paths = lambda documents: {item["filename"] for item in documents}
        observations = []

        def run(candidate, projects):
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("GITHUB_OUTPUT", os.environ)
            observations.append((candidate, projects))

        self.gate.tool_dependencies = SimpleNamespace(affected_projects=lambda paths: ("server-console",), run=run)
        with patch.object(VALIDATION, "_differential") as differential, \
                patch.object(execution, "execute", side_effect=AssertionError("host execution is unnecessary")):
            result = self.validate(runtime_failure=AssertionError("host capture is unnecessary"))
        differential.assert_called_once()
        self.assertEqual(observations, [(self.candidate, ["server-console"])])
        self.assertEqual(result["bounded_projects"], ["server-console"])
        self.assertIsNone(result["execution"])

    def test_s3_sync_names_external_required_owner_without_duplicate_or_fake_pass(self):
        from unittest.mock import Mock
        s3 = 'script-archive/marketplace/S3Server'
        for mixed in (False, True):
            self.args.profile = self.request.profile = 'tool-dependencies'
            paths = [s3 + '/package-lock.json'] + (['server-console/package.json'] if mixed else [])
            self.request.changed_paths = tuple(paths)
            self.gate.paginate_pull_files = lambda *arguments: [{'filename': path, 'status': 'modified'} for path in paths]
            self.gate.changed_paths = lambda documents: {item['filename'] for item in documents}
            run = Mock()
            selector = Mock(return_value=(s3, 'server-console') if mixed else (s3,))
            self.gate.tool_dependencies = SimpleNamespace(affected_projects=selector, run=run)
            self.gate.package_checks = SimpleNamespace(activated=Mock(return_value=True), validate_wiring=Mock())
            with patch.object(VALIDATION, '_differential') as differential:
                result = self.validate(runtime_failure=AssertionError('host capture is unnecessary'))
            differential.assert_called_once()
            self.assertEqual(result['external_package_set'], [s3])
            self.assertEqual(result['bounded_projects'], ['server-console'] if mixed else [])
            self.assertEqual(result['executed_suites'], [])
            self.assertNotIn(s3, self.args.junit.read_text())
            self.gate.package_checks.validate_wiring.assert_called_once_with(self.candidate)
            selector.assert_called_once_with(paths, include_s3=True)
            if mixed: run.assert_called_once_with(self.candidate, ['server-console'])
            else: run.assert_not_called()
        self.gate.package_checks.activated.return_value = False
        with patch.object(VALIDATION, '_differential'), self.assertRaisesRegex(VALIDATION.ValidationError, 'not activated'):
            self.validate()
        self.gate.package_checks.activated.return_value = True
        self.gate.package_checks.validate_wiring.side_effect = ValueError('unapproved owner')
        with patch.object(VALIDATION, '_differential'), self.assertRaisesRegex(ValueError, 'unapproved owner'):
            self.validate()

    def test_candidate_secrets_are_removed_and_trusted_read_token_is_restored(self):
        with patch.dict(os.environ, {"GH_TOKEN": "original", "GITHUB_OUTPUT": "command-file"}):
            with VALIDATION.candidate_environment():
                self.assertNotIn("GH_TOKEN", os.environ)
                self.assertNotIn("GITHUB_OUTPUT", os.environ)
            self.assertEqual(os.environ["GH_TOKEN"], "original")
            self.assertEqual(os.environ["GITHUB_OUTPUT"], "command-file")

    def ci_fixture(self, *, npm=False, quick_beta=False):
        """Review a tiny immutable reader graph; run only real fixture commands."""
        self.registry["suites"]["beta"]["layer"] = "quick" if quick_beta else "host"
        path = self.candidate / ".github/test-suites.json"
        path.parent.mkdir(); path.write_text(json.dumps(self.registry))
        path = self.candidate / "tools/branch-cleanup/cleanup.py"
        path.parent.mkdir(parents=True); path.write_text("# Reviewed CI implementation\n")
        if npm:
            path = self.candidate / "browser-client/package-lock.json"
            path.parent.mkdir(); path.write_text('{"fixture-version":"old"}\n')
        self.git("add", "."); self.git("commit", "-qm", "Create reviewed selective fixture")
        self.base = self.git("rev-parse", "HEAD")
        self.ci_base_tree = inputs.full_tree(self.candidate, self.base)
        (self.candidate / "tools/branch-cleanup/cleanup.py").write_text("# Changed CI implementation\n")
        if npm:
            (self.candidate / "browser-client/package-lock.json").write_text('{"fixture-version":"new"}\n')
        self.git("add", "."); self.git("commit", "-qm", "Change independent CI inputs")
        self.parent = self.git("rev-parse", "HEAD")
        self.ci_refresh()
        self.args.mode = "fallback"
        real_loader = VALIDATION._trusted_module
        self.ci_host = real_loader("fixture_sync_ci_host", VALIDATION.ROOT / "tools/repository-checks/host_selection.py")
        reviewed = self.ci_host.program_digest(self.ci_base_tree, self.candidate)
        self.ci_host.REVIEWED_PROGRAMS = reviewed
        self.ci_host.REVIEWED_CHILD_PROGRAMS = {"apple-main": reviewed}
        actual_select = self.ci_host.select
        self.ci_host.select = lambda *args, **kwargs: actual_select(*args, **{**kwargs, "trusted_root": self.candidate})
        self.ci_packages = SimpleNamespace(validate_wiring=Mock(return_value="npm-consumers-v1"),
            consumer_generation=Mock(return_value=True), has_staged_caller=Mock(return_value=True),
            activated=Mock(return_value=False), candidate_plan=Mock(side_effect=self.ci_package_plan),
            run=Mock(side_effect=AssertionError("external npm owner must not run twice")))
        self.ci_host.package_policy = lambda: self.ci_packages
        real_tree = inputs.full_tree
        def full_tree(root, commit="HEAD"):
            return deepcopy(self.ci_base_tree) if Path(root).resolve() == VALIDATION.ROOT else real_tree(root, commit)
        for replacement in (patch.object(inputs, "full_tree", side_effect=full_tree),
                patch.object(VALIDATION, "_trusted_module", side_effect=lambda name, path:
                    self.ci_host if name == "sync_ci_host_policy" else real_loader(name, path))):
            replacement.start(); self.addCleanup(replacement.stop)
        self.evidence = self.make_evidence()

    def ci_refresh(self):
        self.git("add", ".")
        tree = self.git("write-tree")
        self.commit = self.git("commit-tree", tree, "-p", self.base, "-p", self.parent,
                               "-m", "Create immutable exact-parent merge fixture")
        self.git("reset", "--hard", self.commit)
        self.tree_sha = tree; self.tree = inputs.full_tree(self.candidate, self.commit)
        paths = self.git("diff", "--name-only", self.base, self.commit).splitlines()
        self.request.base_sha = self.base; self.request.head_sha = self.parent
        self.request.parent_sha = self.parent; self.request.merge_sha = self.commit
        self.request.changed_paths = tuple(paths)
        self.pr["base"].update(sha=self.base, repo=self.repository)
        self.pr["head"].update(sha=self.parent, repo=self.repository)
        self.pr["merge_commit_sha"] = self.commit
        self.args.base_sha = self.base; self.args.head_sha = self.parent; self.args.merge_sha = self.commit
        self.gate.paginate_pull_files = lambda *arguments: [{"filename": path, "status": "modified"}
                                                           for path in self.request.changed_paths]

    def ci_package_plan(self, candidate, event, source):
        projects, profiles = [], {}
        lock = "browser-client/package-lock.json"
        if lock in self.request.changed_paths:
            projects = ["browser-client"]
            profiles = {"browser-client": {"profile": "source-map-postcss-v1", "required": True,
                "changed_paths": [lock], "reason": "reviewed-single-dependency-security-update"}}
        return {"unknown": False, "consumer_generation": True, "base": self.base, "head": self.parent,
            "candidate": source, "tree": self.tree_sha, "paths": list(self.request.changed_paths),
            "regular": True, "package_set": projects, "plan": "a" * 64, "policy": {"fixture": "b" * 64},
            "dependency_profiles": {"unknown": False, "base": {"revision": self.base},
                "candidate": {"revision": source, "tree": self.tree_sha}, "projects": profiles}}

    def ci_prepare(self):
        with patch.object(VALIDATION, "_gate", return_value=self.gate), \
                patch.object(inputs, "load_registry", return_value=deepcopy(self.registry)):
            selected = VALIDATION.select_sync(self.args, api=self.api)
        self.args.expected_selection = selected["selection"]
        return selected

    def test_ci_prerequisite_selection_does_not_capture_runtime_or_execute_commands(self):
        self.ci_fixture()
        with patch.object(execution, "_runner", side_effect=AssertionError("selection cannot execute")), \
                patch.object(runtime, "capture_host_environment", side_effect=AssertionError("no Qt setup yet")):
            selected = self.ci_prepare()
        self.assertEqual((selected["lane"], selected["full_host"]), ("affected-ci", False))
        self.assertEqual(selected["suites"], ["alpha"])
        self.assertEqual(selected["omitted_suites"], ["beta"])
        self.assertIs(selected["reusable"], False)
        self.assertFalse(self.args.receipt.exists())
        self.assertEqual(self.executed(), [])

    def test_partial_ci_selection_cannot_claim_pending_platform_execution(self):
        self.ci_fixture()
        with patch.object(VALIDATION, "_sync_platform_owner", side_effect=AssertionError("partial CI cannot delegate product commands")):
            selected = self.ci_prepare()
            result = self.validate()
        self.assertEqual(selected["lane"], "affected-ci")
        self.assertNotIn("pending_platform_owners", selected)
        self.assertNotIn("pending_platform_owners", result)

    def test_ci_execution_observes_exact_selected_commands_without_reuse_or_product_run(self):
        self.ci_fixture(); selected = self.ci_prepare()
        with patch.object(execution, "execute", side_effect=AssertionError("complete executor must remain separate")), \
                patch.object(VALIDATION, "_differential") as differential:
            result = self.validate(runtime_failure=AssertionError("CI omission does not use cached runtime proof"))
        differential.assert_called_once()
        self.assertEqual(self.executed(), ["alpha"])
        self.assertEqual(result["mode"], "affected-ci")
        self.assertEqual(result["reused_suites"], [])
        self.assertEqual(result["executed_suites"], ["alpha"])
        self.assertIsNone(result["parent_evidence"])
        self.assertEqual(result["ci_selection"], selected)
        self.assertEqual(result["execution"]["producer"], VALIDATION.CI_EXECUTION_PRODUCER)
        self.assertIs(result["execution"]["reusable"], False)
        self.assertIs(result["execution"]["include_platform"], False)
        self.assertEqual(result["execution"]["results"], [{"name": "alpha", "status": "passed",
            "command": self.registry["suites"]["alpha"]["command"]}])

    def test_ci_sync_leaves_exact_npm_ownership_external_without_duplicate_or_fake_result(self):
        self.ci_fixture(npm=True); self.ci_prepare()
        with patch.object(VALIDATION, "_differential"):
            result = self.validate(runtime_failure=AssertionError("no reusable environment needed"))
        self.assertEqual(result["external_package_set"], ["browser-client"])
        self.assertEqual(result["executed_suites"], ["alpha"])
        self.assertNotIn("browser-client", json.dumps(result["execution"]["results"]))
        self.ci_packages.run.assert_not_called()

    def test_ci_missing_owner_repairs_or_changed_product_readers_select_complete_fallback(self):
        self.ci_fixture(npm=True)
        self.ci_packages.consumer_generation.return_value = False
        self.assertEqual(self.ci_prepare()["lane"], "complete")
        self.ci_packages.consumer_generation.return_value = True
        self.request.repair_paths = ("libraries/alpha.cpp",)
        self.assertEqual(self.ci_prepare()["lane"], "complete")
        self.request.repair_paths = ()
        (self.candidate / "libraries/beta.cpp").write_text("Changed native reader\n")
        self.ci_refresh()
        self.assertEqual(self.ci_prepare()["lane"], "complete")

    def test_ci_requires_bound_fork_configuration_and_mandatory_package_owner(self):
        self.ci_fixture(npm=True)
        selected = self.ci_prepare()
        self.assertEqual(selected["lane"], "affected-ci")
        path = VALIDATION.ROOT / ".github/repository-checks.json"
        import hashlib
        self.assertEqual(selected["policy"][".github/repository-checks.json"], hashlib.sha256(path.read_bytes()).hexdigest())
        valid = {"repository": self.repository["full_name"], "repository_id": self.repository["id"],
                 "required_contexts": ["repository-checks"]}
        for config in ({**valid, "required_contexts": []}, {**valid, "repository": "other/overte"},
                       {**valid, "repository_id": True}, {**valid, "repository_id": 1}, None):
            with self.subTest(config=config), patch.object(VALIDATION, "_repository_owner_policy", return_value=config):
                self.assertEqual(self.ci_prepare()["lane"], "complete")
        with patch.object(VALIDATION, "_repository_owner_policy", side_effect=FileNotFoundError("missing policy")):
            self.assertEqual(self.ci_prepare()["lane"], "complete")
        self.ci_packages.has_staged_caller.return_value = False
        self.assertEqual(self.ci_prepare()["lane"], "complete")
        self.ci_packages.activated.return_value = True
        self.assertEqual(self.ci_prepare()["lane"], "affected-ci")
        self.ci_packages.activated.return_value = False
        self.ci_packages.has_staged_caller.return_value = True
        self.ci_packages.consumer_generation.return_value = False
        self.assertEqual(self.ci_prepare()["lane"], "complete")
        self.ci_packages.consumer_generation.return_value = True
        owner = self.ci_package_plan(self.candidate, {}, self.commit)
        owner["package_set"] = []
        with patch.object(self.ci_packages, "candidate_plan", return_value=owner):
            self.assertEqual(self.ci_prepare()["lane"], "complete")

    def test_ci_stale_prerequisite_or_differential_failure_prevents_execution(self):
        self.ci_fixture(); self.ci_prepare()
        self.args.expected_selection = "sha256:" + "0" * 64
        with self.assertRaises(VALIDATION.ValidationError): self.validate()
        self.assertEqual(self.executed(), [])
        self.ci_prepare()
        with patch.object(VALIDATION, "_differential", side_effect=ValueError("changed contract")), \
                self.assertRaises(ValueError): self.validate()
        self.assertEqual(self.executed(), [])

    def test_ci_failed_selected_command_cannot_emit_a_successful_sync_receipt(self):
        self.ci_fixture(); self.ci_prepare()
        with patch.object(VALIDATION, "_differential"), self.assertRaises(VALIDATION.ValidationError):
            self.validate(extra_environment={"FIXTURE_FAIL_ALPHA": "1"})
        self.assertEqual(self.executed(), ["alpha"])
        self.assertFalse(self.args.receipt.exists())

    def test_ci_diagnostic_missing_or_forged_execution_receipt_never_qualifies(self):
        self.ci_fixture(); self.ci_prepare()
        real_execute = VALIDATION._execute_ci
        for mutation in ("missing", "diagnostic", "omitted", "command", "candidate", "selection", "reusable"):
            def execute(*args, **kwargs):
                status, receipt = real_execute(*args, **kwargs)
                path = args[-1]
                if mutation == "missing": Path(path).unlink(); return status, receipt
                receipt = deepcopy(receipt)
                if mutation == "diagnostic": receipt = {"kind": "host-impact-selection", "reusable": False}
                elif mutation == "omitted": receipt["results"] = []
                elif mutation == "command": receipt["results"][0]["command"] = ["python", "tests/beta.py"]
                elif mutation == "candidate": receipt["candidate_commit"] = "0" * 40
                elif mutation == "selection": receipt["selection"] = "sha256:" + "0" * 64
                else: receipt["reusable"] = True
                receipt.pop("receipt_digest", None); receipt["receipt_digest"] = execution.digest(receipt)
                execution._write_receipt(path, receipt)
                return status, receipt
            with self.subTest(mutation=mutation), patch.object(VALIDATION, "_differential"), \
                    self.assertRaises(VALIDATION.ValidationError):
                self.validate(ci_execute_override=execute)
            self.assertFalse(self.args.receipt.exists())

    def test_ci_final_live_branch_drift_cannot_emit_success(self):
        self.ci_fixture(); self.ci_prepare()
        real_execute = VALIDATION._execute_ci
        def execute(*args, **kwargs):
            result = real_execute(*args, **kwargs)
            self.gate.branch_sha = lambda *args: "0" * 40
            return result
        with patch.object(VALIDATION, "_differential"), self.assertRaises(VALIDATION.ValidationError):
            self.validate(ci_execute_override=execute)
        self.assertEqual(self.executed(), ["alpha"])
        self.assertFalse(self.args.receipt.exists())

    def test_staged_ci_workflow_selects_before_qt_and_binds_both_execution_paths(self):
        import yaml
        workflow = VALIDATION.ROOT / "tools/repository-checks/workflows/sync-ci-selection.yml"
        data = yaml.safe_load(workflow.read_text()); steps = data["jobs"]["validate"]["steps"]
        selection = next(step for step in steps if step.get("id") == "select")
        self.assertIn("--select-only", selection["run"])
        for name in ("Set up candidate Java", "Install candidate host prerequisites"):
            step = next(step for step in steps if step["name"] == name)
            self.assertGreater(steps.index(step), steps.index(selection))
            self.assertEqual(step["if"], "(steps.select.outputs.consumer_setup != 'none' || steps.select.outputs.native_setup == '') && steps.select.outputs.full_host == 'true' && !(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')")
        executions = [step for step in steps if "--expected-selection" in step.get("run", "")]
        self.assertEqual(len(executions), 3)
        self.assertEqual({step['name'] for step in executions}, {
            'Verify bounded synchronization without product setup',
            'Verify exact candidate suites and complete runtime identity',
            'Validate the exact unchanged synchronization without test execution'})
        for step in executions:
            self.assertEqual(step["env"]["EXPECTED_SELECTION"], "${{ steps.select.outputs.selection }}")
            self.assertIn('trusted/tools/test-evidence/validate-sync.py', step["run"])
            if step['name'] == 'Verify exact candidate suites and complete runtime identity':
                self.assertIn('"$SYNC_VALIDATOR_PYTHON" -B ', step['run'])
                self.assertEqual(step['env']['SYNC_VALIDATOR_PYTHON'],
                    "${{ steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.native_setup != '' && 'python3' || 'build/host-tests-env/bin/python' }}")
                self.assertEqual(step['env']['EXPECTED_NATIVE_SETUP'], '${{ steps.select.outputs.native_setup }}')
                self.assertIn('--expected-native-setup "$EXPECTED_NATIVE_SETUP"', step['run'])
            else:
                self.assertIn('python3 -B ', step['run'])
                if step['name'] == 'Validate the exact unchanged synchronization without test execution':
                    self.assertEqual(step['if'], "steps.select.outputs.lane == 'verified-empty'")
                    self.assertEqual(step['env']['EXPECTED_EMPTY_SETUP'], '${{ steps.select.outputs.empty_setup }}')
                    self.assertIn('--expected-empty-setup "$EXPECTED_EMPTY_SETUP"', step['run'])
                    self.assertNotIn('--expected-native-setup', step['run'])
                    self.assertNotIn('SYNC_VALIDATOR_PYTHON', step['env'])
        self.assertEqual(data["permissions"], {"actions": "read", "checks": "read", "contents": "read", "pull-requests": "read"})
        # The source-preparation PR still runs the deployed historical recipe.
        # The distinct prospective recipe above is not deployed by changing a
        # canonical source leaf. Authenticate the active blob against complete
        # reviewed catalog data; never rewrite an old row to the new template.
        import hashlib
        catalog=json.loads((VALIDATION.ROOT/'.github/package-workflow-generations.json').read_bytes())['generations']
        active=(VALIDATION.ROOT/'.github/workflows/sync-validation.yml').read_bytes()
        active_entry={'mode':'100644','type':'blob','sha':hashlib.sha1(
            b'blob '+str(len(active)).encode()+b'\0'+active).hexdigest()}
        self.assertTrue(any(row['workflows'].get('.github/workflows/sync-validation.yml')==active_entry
            for row in catalog))
        # Materialize the future six-path tuple as ordinary immutable fixture
        # data. Its enrollment belongs to source composition, not this test.
        sources={'.github/workflows/project-tests.yml':
                'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
            '.github/workflows/parent-qualification.yml':
                'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
            '.github/workflows/repository-checks.yml':
                'tools/repository-checks/workflows/producers/repository-checks.yml',
            '.github/workflows/sync-validation.yml':str(workflow.relative_to(VALIDATION.ROOT)),
            '.github/workflows/browser-client.yml':'.github/workflows/browser-client.yml',
            '.github/workflows/pr-metadata-context.yml':
                'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml'}
        with tempfile.TemporaryDirectory(prefix='sync-future-tuple-') as temporary:
            snapshot=Path(temporary)
            for path,relative in sources.items():
                target=snapshot/path;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((VALIDATION.ROOT/relative).read_bytes());target.chmod(0o644)
            self.assertEqual(yaml.safe_load((snapshot/'.github/workflows/sync-validation.yml').read_bytes()),data)
            self.assertEqual(len(list((snapshot/'.github/workflows').iterdir())),6)
            future=next((row for row in catalog if row['name']=='protected-producer-original-default-v1'),None)
            if future is not None:
                for path in sources:
                    raw=(snapshot/path).read_bytes()
                    self.assertEqual(future['workflows'][path],{'mode':'100644','type':'blob',
                        'sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()},path)
        gate = yaml.safe_load((VALIDATION.ROOT / '.github/workflows/sync-test-reuse.yml').read_text())
        self.assertEqual(gate['permissions'], {'actions':'write','checks':'read','contents':'read','pull-requests':'read'})
        trusted = gate['jobs']['sync-test-reuse']['steps'][0]
        self.assertEqual(trusted['with']['ref'], '${{ github.event.repository.default_branch }}')
        self.assertIs(trusted['with']['persist-credentials'], False)
        self.assertNotIn('secrets', gate['jobs']['sync-test-reuse'])
        invocations=[step['run'] for step in gate['jobs']['sync-test-reuse']['steps']
            if 'tools/sync-test-reuse/' in step.get('run','')]
        self.assertEqual(len(invocations),3)
        self.assertTrue(all('python3 -B ' in command for command in invocations))


class NativeParentConsumerTests(unittest.TestCase):
    """Actual tiny candidate commands; native API admission is a typed seam."""
    def setUp(self):
        self.fixture=IsolatedConsumerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.native_type=VALIDATION._gate().NativeParentEvidence
        self.fixture.gate.NativeParentEvidence=self.native_type
        self.fixture.gate.native_parent_evidence=Mock(side_effect=lambda *args:deepcopy(self.fixture.evidence))
        self.bind_native()

    def bind_native(self, parent_tree=None):
        f=self.fixture
        f.evidence=self.native_type(f.make_evidence(parent_tree) | {
            'kind':'original-native-parent-v1','original_commit':'e'*40,
            'original_git_context':{'fixture':'original immutable M'},
            'original_proof':{'verified':True,'run_id':100,'attempt':1,
                'receipt_sha256':'1'*64,'expires_at':'kept in outer evidence'}})

    def test_complete_native_reuse_has_no_unused_consumer_e_or_execution_receipt(self):
        f=self.fixture
        result=f.validate(runtime_failure=AssertionError('no unused consumer E'),
            execute_override=lambda *a,**k:(_ for _ in ()).throw(AssertionError('no unused execution')))
        self.assertEqual(result['mode'],'reuse')
        self.assertEqual(result['reused_suites'],['alpha','beta'])
        self.assertEqual(result['executed_suites'],[])
        self.assertIsNone(result['execution'])
        self.assertEqual(f.executed(),[])
        self.assertFalse(Path(str(f.args.receipt)+'.execution.json').exists())
        self.assertEqual(result['parent_evidence']['original_commit'],'e'*40)
        self.assertEqual(result['parent_evidence']['parent_commit'],f.parent)
        self.assertFalse(result['parent_evidence']['qualification'])
        self.assertFalse(result['parent_evidence']['reusable'])
        self.assertEqual(result['parent_evidence']['expires_at'],f.evidence['expires_at'])
        self.assertNotIn('workflow',result['parent_evidence'])
        f.gate.native_parent_evidence.assert_called_once()
        import xml.etree.ElementTree as ET
        names=[item.attrib['name'] for item in ET.parse(f.args.junit).iter('testcase')]
        self.assertEqual(names,['sync-differential'])

    def test_historical_child_change_executes_only_affected_suite_under_its_actual_runtime(self):
        f=self.fixture
        parent=deepcopy(f.tree);parent['libraries/alpha.cpp']['sha']='c'*40
        self.bind_native(parent)
        result=f.validate(actual_environment=f.environment | {'qt':'different consumer runtime'})
        self.assertEqual(result['reused_suites'],['beta'])
        self.assertEqual(result['executed_suites'],['alpha'])
        self.assertEqual(f.executed(),['alpha'])
        self.assertEqual(result['execution']['environment']['qt'],'different consumer runtime')
        self.assertEqual(result['parent_evidence']['reused_results'],{'beta':f.evidence['results']['suites']['beta']})
        f.gate.native_parent_evidence.assert_called_once()

    def test_native_common_reuse_never_omits_actual_platform_commands(self):
        f=self.fixture
        profile=f.candidate/'tests/platform-profile.json'
        profile.write_text(json.dumps({'schema':1,'platform':'android','suites':[
            {'name':'product-fixture','interpreter':'python','entrypoint':'tests/product.py'}]}))
        (f.candidate/'tests/product.py').write_text('from pathlib import Path\nimport os\nPath(os.environ["FIXTURE_EXECUTION_LOG"]).write_text("product\\n")\n')
        f.git('add','.');f.git('commit','-qm','Declare required fixture platform')
        f.commit,f.tree_sha=execution.checkout_identity(f.candidate)
        f.tree=inputs.full_tree(f.candidate)
        f.request.merge_sha=f.commit;f.pr['merge_commit_sha']=f.commit;f.args.merge_sha=f.commit
        self.bind_native()
        result=f.validate()
        self.assertEqual(result['reused_suites'],['alpha','beta'])
        self.assertEqual(result['executed_suites'],[])
        self.assertEqual(f.executed(),['product'])
        self.assertEqual(set(result['execution']['platform_results']),{'product-fixture'})
        self.assertTrue(result['execution']['include_platform'])

    def test_after_start_missing_changed_or_expired_native_proof_is_hard_failure_without_retry(self):
        f=self.fixture
        parent=deepcopy(f.tree);parent['libraries/alpha.cpp']['sha']='c'*40
        self.bind_native(parent)
        f.gate.native_parent_evidence.side_effect=EvidenceError('native publisher unavailable')
        with self.assertRaisesRegex(VALIDATION.ValidationError,'became unavailable'):
            f.validate()
        self.assertEqual(f.executed(),['alpha'])
        self.assertFalse(f.args.receipt.exists())
        f.gate.native_parent_evidence.assert_called_once()

    def test_changed_native_bookend_is_rejected_even_without_workload(self):
        f=self.fixture
        changed=deepcopy(f.evidence);changed['original_proof']['receipt_sha256']='0'*64
        f.gate.native_parent_evidence.side_effect=None
        f.gate.native_parent_evidence.return_value=changed
        with self.assertRaisesRegex(VALIDATION.ValidationError,'proof changed'):
            f.validate(runtime_failure=AssertionError('no unused consumer E'))
        self.assertEqual(f.executed(),[])
        self.assertFalse(f.args.receipt.exists())

    def test_untyped_legacy_json_kind_cannot_bypass_consumer_runtime_comparison(self):
        f=self.fixture
        f.evidence=dict(f.evidence)
        result=f.validate(actual_environment=f.environment | {'qt':'different consumer runtime'})
        self.assertEqual(result['mode'],'fallback')
        self.assertEqual(set(f.executed()),{'alpha','beta'})
        f.gate.native_parent_evidence.assert_not_called()

    def test_expired_native_proof_during_validation_cannot_publish_success(self):
        f=self.fixture
        f.evidence['expires_at']='2020-01-01T00:00:00Z'
        with self.assertRaisesRegex(VALIDATION.ValidationError,'expired'):
            f.validate(runtime_failure=AssertionError('no unused consumer E'))
        self.assertFalse(f.args.receipt.exists())

    def test_missing_native_admission_keeps_real_full_fallback(self):
        f=self.fixture
        f.gate.verify_evidence=lambda *args:(_ for _ in ()).throw(EvidenceError('missing original native proof'))
        result=f.validate()
        self.assertEqual(result['mode'],'fallback')
        self.assertEqual(set(f.executed()),{'alpha','beta'})
        f.gate.native_parent_evidence.assert_not_called()


class ArtifactNamespaceSelectionTests(unittest.TestCase):
    def selected(self, **changes):
        value = {'schema': 1, 'kind': 'sync-ci-selection', 'reusable': False,
            'selection': 'sha256:' + '1' * 64, 'lane': 'affected-ci',
            'full_host': False, 'suites': ['workflow-contracts'],
            'profile': 'apple-family', 'requested_mode': 'reuse'}
        value.update(changes)
        return value

    def test_namespace_utility_follows_actual_selected_owners_not_full_host(self):
        for owner in ('project-runner', 'device-control-plane-full',
                      'project-runner-candidate-' + 'a' * 12,
                      'device-control-plane-full-candidate-' + 'b' * 12):
            for full_host in (False, True):
                selected = self.selected(suites=['workflow-contracts', owner], full_host=full_host)
                original = deepcopy(selected)
                with self.subTest(owner=owner, full_host=full_host):
                    self.assertTrue(VALIDATION.requires_artifact_namespace(selected))
                    self.assertEqual(selected, original)
        for full_host in (False, True):
            self.assertFalse(VALIDATION.requires_artifact_namespace(
                self.selected(full_host=full_host)))
        self.assertTrue(VALIDATION.requires_artifact_namespace(
            self.selected(lane='complete', full_host=True, suites=[])))
        for profile in ('documentation', 'tool-dependencies'):
            self.assertFalse(VALIDATION.requires_artifact_namespace(self.selected(
                lane='legacy-bounded', full_host=False, suites=[], profile=profile)))

    def test_unknown_or_malformed_setup_never_omits_namespace_utility(self):
        values = [None, [], {}, self.selected(lane='unknown'), self.selected(schema=True),
            self.selected(suites=[]), self.selected(suites=('project-runner',)),
            self.selected(suites=['workflow-contracts', 'workflow-contracts']),
            self.selected(suites=['foreign/module']), self.selected(full_host='false'),
            self.selected(selection='sha256:' + 'G' * 64),
            self.selected(consumer_setup='none'),
            self.selected(consumer_setup='none', native_setup='sha256:' + '2' * 64, suites=[]),
            self.selected(consumer_setup='unknown'),
            self.selected(consumer_setup='none', native_setup='invalid'),
            self.selected(native_setup='sha256:' + '2' * 64),
            self.selected(empty_setup='sha256:' + '1' * 64),
            self.selected(lane='complete', full_host=False),
            self.selected(lane='legacy-bounded', suites=[], profile='apple-family'),
            self.selected(lane='legacy-bounded', suites=[], profile='documentation', requested_mode='fallback')]
        for selected in values:
            original = deepcopy(selected)
            with self.subTest(selected=selected):
                self.assertTrue(VALIDATION.requires_artifact_namespace(selected))
                self.assertEqual(selected, original)

    def test_select_only_adds_utility_output_without_mutating_selection_or_receipt(self):
        for selected, expected in ((self.selected(suites=['project-runner']), 'true'),
                                   (self.selected(), 'false')):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'output'
                original = deepcopy(selected)
                argv = ['--candidate', directory, '--repository', 'noah-l-frank/overte',
                    '--pull-request', '42', '--mode', 'reuse', '--profile', 'apple-family',
                    '--base-sha', 'a' * 40, '--head-sha', 'b' * 40, '--merge-sha', 'c' * 40,
                    '--junit', str(Path(directory) / 'unused.xml'),
                    '--receipt', str(Path(directory) / 'unused.json'), '--select-only', '--output', str(output)]
                rendered = io.StringIO()
                with patch.object(VALIDATION, 'select_sync', return_value=selected) as select, \
                        patch.object(VALIDATION, 'validate_sync', side_effect=AssertionError('selection cannot execute')) as execute, \
                        redirect_stdout(rendered), redirect_stderr(io.StringIO()):
                    self.assertEqual(VALIDATION.main(argv), 0)
                select.assert_called_once(); execute.assert_not_called()
                self.assertEqual(selected, original)
                self.assertEqual(json.loads(rendered.getvalue()), original)
                fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
                self.assertEqual(fields.pop('requires_artifact_namespace'), expected)
                self.assertEqual(fields, {'selection': original['selection'], 'lane': original['lane'],
                    'full_host': str(original['full_host']).lower(), 'consumer_setup': 'required',
                    'native_setup': '', 'empty_setup': ''})
                self.assertFalse((Path(directory) / 'unused.xml').exists())
                self.assertFalse((Path(directory) / 'unused.json').exists())


class NativeZeroCommandSetupTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeParentConsumerTests()
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.fixture = self.native.fixture

    def prepare(self, *, affected=False):
        f = self.fixture
        if affected:
            f.ci_fixture(); f.args.mode = 'reuse'; self.native.bind_native()
        selected = f.ci_prepare()
        f.args.expected_native_setup = selected.get('native_setup', '')
        return selected

    def test_namespace_output_recognizes_actual_native_zero_and_partial_proof_loss(self):
        selected = self.prepare()
        original = deepcopy(selected)
        self.assertEqual(selected['consumer_setup'], 'none')
        self.assertFalse(VALIDATION.requires_artifact_namespace(selected))
        self.assertEqual(selected, original)
        f = self.fixture
        parent_tree = deepcopy(f.tree)
        parent_tree['libraries/alpha.cpp']['sha'] = 'd' * 40
        self.native.bind_native(parent_tree)
        partial = self.prepare()
        self.assertEqual(partial['lane'], 'complete')
        self.assertNotIn('consumer_setup', partial)
        self.assertNotIn('native_setup', partial)
        self.assertTrue(VALIDATION.requires_artifact_namespace(partial))
        affected = self.prepare(affected=True)
        self.assertEqual(affected['lane'], 'affected-ci')
        self.assertEqual(affected['consumer_setup'], 'none')
        original = deepcopy(affected)
        self.assertFalse(VALIDATION.requires_artifact_namespace(affected))
        self.assertEqual(affected, original)
        self.assertEqual(f.executed(), [])

    def test_early_lookup_is_stdlib_only_and_does_not_change_pure_selection(self):
        f = self.fixture
        with patch.object(execution,'execute',side_effect=AssertionError('no execution during setup plan')), \
                patch.object(execution,'capture_execution_environment',side_effect=AssertionError('no unused consumer E')):
            selected = self.prepare()
        self.assertEqual(selected['consumer_setup'], 'none')
        self.assertTrue(selected['native_setup'].startswith('sha256:'))
        with patch.object(inputs,'load_registry',return_value=f.registry):
            source = VALIDATION._ci_selection(f.args,f.request,f.candidate,(f.commit,f.tree_sha),f.registry,f.api)
        self.assertEqual({key:value for key,value in selected.items() if key not in {'consumer_setup','native_setup'}}, source)
        self.assertEqual(f.executed(), [])

    def test_no_setup_complete_and_selected_paths_revalidate_native_proof_around_differential(self):
        # Separate real candidates keep selection-policy and typed-proof seams
        # explicit; neither path needs a venv, Qt installation or consumer E.
        for affected in (False, True):
            if affected:
                self.native.doCleanups(); self.setUp()
            f = self.fixture; selected = self.prepare(affected=affected)
            self.assertEqual(selected['consumer_setup'],'none')
            f.gate.native_parent_evidence.reset_mock()
            f.gate.verify_evidence = lambda *a: (_ for _ in ()).throw(AssertionError('no legacy capsule'))
            def differential(*args):
                self.assertEqual(f.gate.native_parent_evidence.call_count, 1, 'fresh native proof precedes differential')
            with patch.object(VALIDATION,'_differential',side_effect=differential) as check:
                result = f.validate(runtime_failure=AssertionError('no unused consumer E'),
                    execute_override=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no unprepared fallback')),
                    ci_execute_override=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no selected command')))
            check.assert_called_once()
            self.assertEqual(f.gate.native_parent_evidence.call_count,2)
            self.assertIsNone(result['execution'])
            self.assertEqual(result['executed_suites'],[])
            self.assertEqual(f.executed(),[])

    def test_missing_initial_proof_keeps_existing_setup_and_real_execution(self):
        f = self.fixture
        f.gate.native_parent_evidence.side_effect = EvidenceError('no current native proof')
        selected = self.prepare()
        self.assertNotIn('consumer_setup',selected)
        self.assertEqual(f.args.expected_native_setup,'')
        f.gate.verify_evidence = lambda *a: (_ for _ in ()).throw(EvidenceError('no legacy proof'))
        result = f.validate()
        self.assertEqual(set(result['executed_suites']),{'alpha','beta'})
        self.assertEqual(set(f.executed()),{'alpha','beta'})

    def test_marker_without_proof_or_changed_expired_required_proof_never_runs_unprepared_commands(self):
        f = self.fixture; self.prepare()
        original = deepcopy(f.evidence)
        changed = deepcopy(original); changed['original_proof']['receipt_sha256']='0'*64
        expired = deepcopy(original); expired['expires_at']='2020-01-01T00:00:00Z'
        required = deepcopy(original); del required['results']['suites']['alpha']
        for value in (EvidenceError('proof unavailable'), dict(original), changed, expired, required):
            f.gate.native_parent_evidence.side_effect = [value]
            with self.subTest(value=type(value).__name__), patch.object(VALIDATION,'_differential') as differential, \
                    self.assertRaises(VALIDATION.ValidationError):
                f.validate(execute_override=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no unprepared fallback')))
            differential.assert_not_called()
            self.assertEqual(f.executed(),[])
            self.assertFalse(f.args.receipt.exists())

    def test_original_proof_expiry_or_ref_drift_after_differential_is_hard_failure(self):
        f = self.fixture; self.prepare()
        original = deepcopy(f.evidence)
        def differential(*args):
            f.evidence['original_proof']['receipt_sha256']='0'*64
        with patch.object(VALIDATION,'_differential',side_effect=differential), self.assertRaises(VALIDATION.ValidationError):
            f.validate()
        self.assertEqual(f.executed(),[])
        self.assertFalse(f.args.receipt.exists())
        f.evidence=deepcopy(original)
        def expired(*args): f.evidence['expires_at']='2020-01-01T00:00:00Z'
        with patch.object(VALIDATION,'_differential',side_effect=expired), self.assertRaises(VALIDATION.ValidationError): f.validate()
        self.assertEqual(f.executed(),[])
        self.assertFalse(f.args.receipt.exists())
        f.evidence=deepcopy(original)
        def moved(*args): f.api.pr['head']['sha']='f'*40
        with patch.object(VALIDATION,'_differential',side_effect=moved), self.assertRaises(VALIDATION.ValidationError): f.validate()
        self.assertEqual(f.executed(),[])
        self.assertFalse(f.args.receipt.exists())

    def test_nonempty_current_platform_cannot_schedule_no_setup(self):
        f = self.fixture
        profile=f.candidate/'tests/platform-profile.json'
        profile.write_text(json.dumps({'schema':1,'platform':'android','suites':[
            {'name':'product','entrypoint':'tests/product.py','interpreter':'python'}]}))
        (f.candidate/'tests/product.py').write_text('raise AssertionError("unprepared product must not run")\n')
        f.git('add','.');f.git('commit','-qm','Declare actual product requirement')
        f.commit,f.tree_sha=execution.checkout_identity(f.candidate);f.tree=inputs.full_tree(f.candidate)
        f.request.merge_sha=f.args.merge_sha=f.api.pr['merge_commit_sha']=f.commit
        self.native.bind_native()
        selected=self.prepare()
        self.assertNotIn('consumer_setup',selected)
        f.args.expected_native_setup='sha256:'+'0'*64
        with self.assertRaises(VALIDATION.ValidationError): f.validate()
        self.assertEqual(f.executed(),[])

    def test_workflow_skips_all_unused_setup_and_missing_required_venv_cannot_silently_fall_back(self):
        import yaml
        path=VALIDATION.ROOT/'tools/repository-checks/workflows/sync-ci-selection.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['validate']['steps']
        for name in ('Set up candidate Python','Set up candidate Node.js','Set up candidate Java',
                'Install candidate host prerequisites','Prepare isolated shared and product Python validators'):
            self.assertTrue(next(step for step in steps if step['name']==name)['if'].startswith("(steps.select.outputs.consumer_setup != 'none' || steps.select.outputs.native_setup == '') && "))
        step=next(step for step in steps if step['name']=='Verify exact candidate suites and complete runtime identity')
        self.assertEqual(step['env']['SYNC_VALIDATOR_PYTHON'],
            "${{ steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.native_setup != '' && 'python3' || 'build/host-tests-env/bin/python' }}")
        f=self.fixture; binary=f.output/'bin';binary.mkdir()
        fake=binary/'python3';fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FIXTURE_VALIDATOR_ARGS"\n');fake.chmod(0o755)
        environment={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],
            'SYNC_VALIDATOR_PYTHON':'python3','EXPECTED_NATIVE_SETUP':'sha256:'+'1'*64,
            'FIXTURE_VALIDATOR_ARGS':str(f.output/'args')}
        # The exact workflow command can run without its missing venv. The fake
        # interpreter observes argument transport only, never asserts authority.
        result=subprocess.run(['bash','-e','-o','pipefail','-c',step['run']],cwd=f.output,env=environment,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        arguments=(f.output/'args').read_text().splitlines()
        self.assertEqual(arguments[:2],['-B','trusted/tools/test-evidence/validate-sync.py'])
        self.assertEqual(arguments[arguments.index('--expected-native-setup')+1],environment['EXPECTED_NATIVE_SETUP'])
        environment['SYNC_VALIDATOR_PYTHON']='build/host-tests-env/bin/python'
        result=subprocess.run(['bash','-e','-o','pipefail','-c',step['run']],cwd=f.output,env=environment,capture_output=True)
        self.assertNotEqual(result.returncode,0)


class NativeSelectedParentConsumerTests(unittest.TestCase):
    """Real selected fixture commands plus independently supplied typed proof."""
    def setUp(self):
        self.fixture = IsolatedConsumerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.native_type = VALIDATION._gate().NativeParentEvidence
        self.fixture.gate.NativeParentEvidence = self.native_type
        self.fixture.gate.native_parent_evidence = Mock(side_effect=lambda *args: deepcopy(self.fixture.evidence))

    def prepare(self, *, two_selected=False, npm=False, parent_tree=None):
        f = self.fixture
        if two_selected:
            (f.candidate / 'tests/gamma.py').write_text('raise AssertionError("unselected must never run")\n')
            (f.candidate / 'libraries/gamma.cpp').write_text('unselected fixture input\n')
            f.registry['suites']['gamma'] = deepcopy(f.registry['suites']['beta'])
            f.registry['suites']['gamma'].update(command=['python','tests/gamma.py'], layer='host',
                closure={'kind':'patterns','inputs':['tests/gamma.py','libraries/gamma.cpp'],
                    'required':['tests/gamma.py','libraries/gamma.cpp']})
        # Declare both suites before constructing reviewed immutable B/M;
        # changing command definitions after review correctly selects fallback.
        f.ci_fixture(npm=npm, quick_beta=two_selected)
        f.args.mode = 'reuse'
        selected = f.ci_prepare()
        self.bind_native(parent_tree)
        # These counters describe final validation; early no-setup scheduling
        # has its own typed-proof tests and cannot authorize this invocation.
        f.gate.native_parent_evidence.reset_mock()
        return selected

    def bind_native(self, parent_tree=None):
        f = self.fixture
        f.evidence = self.native_type(f.make_evidence(parent_tree) | {
            'kind':'original-native-parent-v1','original_commit':'e'*40,
            'original_git_context':{'fixture':'original immutable M'},
            'original_proof':{'verified':True,'run_id':100,'attempt':1,'receipt_sha256':'1'*64}})

    def test_exact_selected_native_reuse_does_no_unused_execution_or_consumer_capture(self):
        f = self.fixture; selected = self.prepare(npm=True)
        with patch.object(VALIDATION,'_differential') as differential:
            result = f.validate(runtime_failure=AssertionError('no consumer E'),
                ci_execute_override=lambda *a,**k: (_ for _ in ()).throw(AssertionError('no remaining command')))
        differential.assert_called_once()
        self.assertEqual(selected['suites'], ['alpha'])
        self.assertEqual(result['reused_suites'], ['alpha'])
        self.assertEqual(result['executed_suites'], [])
        self.assertEqual(result['not_selected_suites'], ['beta'])
        self.assertEqual(result['external_package_set'], ['browser-client'])
        self.assertIsNone(result['execution'])
        self.assertFalse(Path(str(f.args.receipt)+'.ci-execution.json').exists())
        self.assertEqual(result['parent_evidence']['original_commit'], 'e'*40)
        self.assertFalse(result['parent_evidence']['qualification'])
        self.assertFalse(result['parent_evidence']['reusable'])
        self.assertEqual(set(result['parent_evidence']['reused_results']), {'alpha'})
        self.assertEqual(f.executed(), [])
        f.ci_packages.run.assert_not_called()
        self.assertEqual(f.gate.native_parent_evidence.call_count, 2)
        import xml.etree.ElementTree as ET
        self.assertEqual([x.attrib['name'] for x in ET.parse(f.args.junit).iter('testcase')], ['sync-differential'])

    def test_historical_child_difference_executes_only_selected_required_intersection(self):
        f = self.fixture; self.prepare(two_selected=True)
        parent = deepcopy(f.tree); parent['libraries/alpha.cpp']['sha'] = 'c'*40
        self.bind_native(parent)
        result = f.validate(runtime_failure=AssertionError('no unused consumer E'))
        self.assertEqual(result['reused_suites'], ['beta'])
        self.assertEqual(result['executed_suites'], ['alpha'])
        self.assertEqual(result['not_selected_suites'], ['gamma'])
        self.assertEqual(f.executed(), ['alpha'])
        self.assertEqual(result['execution']['requested_suites'], ['alpha'])
        self.assertEqual(result['execution']['selection'], f.args.expected_selection)
        self.assertFalse(result['execution']['reusable'])
        self.assertEqual(set(result['parent_evidence']['reused_results']), {'beta'})

    def test_missing_native_proof_executes_existing_selected_work_once(self):
        f = self.fixture; self.prepare()
        f.gate.native_parent_evidence.side_effect = EvidenceError('no original publisher')
        result = f.validate(runtime_failure=AssertionError('CI fallback does not need reusable E'))
        self.assertEqual(f.executed(), ['alpha'])
        self.assertEqual(result['reused_suites'], [])
        self.assertEqual(result['not_selected_suites'], ['beta'])
        self.assertIsNone(result['parent_evidence'])
        f.gate.native_parent_evidence.assert_called_once()

    def test_untyped_or_unselected_only_proof_cannot_skip_selected_work(self):
        f = self.fixture; self.prepare()
        f.evidence = dict(f.evidence)
        result = f.validate()
        self.assertEqual(result['executed_suites'], ['alpha'])
        self.assertEqual(result['reused_suites'], [])
        self.assertIsNone(result['parent_evidence'])
        f.log.unlink(); self.bind_native()
        # beta is passed but not selected. It cannot compensate for alpha.
        del f.evidence['results']['suites']['alpha']
        result = f.validate()
        self.assertEqual(f.executed(), ['alpha'])
        self.assertEqual(result['reused_suites'], [])
        self.assertIsNone(result['parent_evidence'])

    def test_original_proof_or_expiry_change_after_execution_is_hard_failure(self):
        f = self.fixture; self.prepare(two_selected=True)
        parent = deepcopy(f.tree); parent['libraries/alpha.cpp']['sha'] = 'c'*40
        self.bind_native(parent)
        changed = deepcopy(f.evidence); changed['original_proof']['receipt_sha256'] = '0'*64
        for final in (EvidenceError('publisher missing'), changed):
            f.gate.native_parent_evidence.side_effect = [deepcopy(f.evidence), final]
            with self.subTest(final=type(final).__name__), self.assertRaises(VALIDATION.ValidationError):
                f.validate()
            self.assertEqual(f.executed(), ['alpha'])
            self.assertFalse(f.args.receipt.exists())
            f.log.unlink()
        f.gate.native_parent_evidence.side_effect = lambda *args: deepcopy(f.evidence)
        f.evidence['expires_at'] = '2020-01-01T00:00:00Z'
        with self.assertRaisesRegex(VALIDATION.ValidationError, 'expired'):
            f.validate()
        self.assertEqual(f.executed(), ['alpha'])
        self.assertFalse(f.args.receipt.exists())

    def test_source_or_expected_selection_mismatch_blocks_before_commands(self):
        f = self.fixture; self.prepare()
        f.evidence['candidate_inputs']['libraries/alpha.cpp']['sha'] = 'c'*40
        with self.assertRaisesRegex(VALIDATION.ValidationError, 'verified native API inputs'): f.validate()
        self.assertEqual(f.executed(), [])
        self.bind_native(); f.args.expected_selection = 'sha256:'+'0'*64
        with self.assertRaisesRegex(VALIDATION.ValidationError, 'prerequisite plan'): f.validate()
        self.assertEqual(f.executed(), [])

    def test_selected_failure_never_retries_or_borrows_unselected_pass(self):
        f = self.fixture; self.prepare(two_selected=True)
        parent = deepcopy(f.tree); parent['libraries/alpha.cpp']['sha'] = 'c'*40
        self.bind_native(parent)
        with self.assertRaises(VALIDATION.ValidationError):
            f.validate(extra_environment={'FIXTURE_FAIL_ALPHA':'1'})
        self.assertEqual(f.executed(), ['alpha'])
        self.assertFalse(f.args.receipt.exists())
        f.gate.native_parent_evidence.assert_called_once()

    def test_internal_remaining_subset_cannot_expand_reorder_or_repeat_selection(self):
        f = self.fixture; selected = self.prepare(two_selected=True)
        for names in (['gamma'], ['beta','alpha'], ['alpha','alpha'], 'alpha'):
            with self.subTest(names=names), self.assertRaises(VALIDATION.ValidationError):
                VALIDATION._ci_commands(selected, f.registry, suite_names=names)
        self.assertEqual(VALIDATION._ci_commands(selected, f.registry),
            {name:f.registry['suites'][name]['command'] for name in ('alpha','beta')})



class VerifiedEmptyConsumerTests(unittest.TestCase):
    """Dispatch proof is a narrow fixture; differential/source books are real."""
    def workflow_fixture_generation(self, root):
        # Classify complete ordinary endpoint bytes against the actual trusted
        # catalog. A matching synchronization leaf alone cannot select22.
        source=Path(__file__).resolve().parents[1]/'repository-checks/package_checks.py'
        packages=VALIDATION._trusted_module('verified_empty_fixture_packages',source)
        generation=packages.validate_wiring(root)
        self.assertIn(generation,{'npm-consumers-sync-ci-v1','protected-producer-original-default-v1'})
        return packages,generation

    def setUp(self):
        self.fixture=IsolatedConsumerTests('runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;f.request.changed_paths=()
        f.gate.paginate_pull_files=lambda *args:[]
        self.proof={'schema':1,'kind':'verified-empty-sync-v1','reusable':False,'qualification':False,
            'immutable':{'base':f.base,'head':f.parent,'candidate':f.commit,'tree':f.tree_sha},
            'native':{'job_id':702},'source':{'controller':'fixed actual default'}}
        f.gate.verified_empty_sync=Mock(side_effect=lambda *args:deepcopy(self.proof))
        f.gate.native_parent_evidence=Mock(side_effect=AssertionError('no prior test proof'))
        f.gate.verify_evidence=lambda *args:(_ for _ in ()).throw(AssertionError('no qualification capsule'))
        self.stack=self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(VALIDATION,'_gate',return_value=f.gate))
        self.stack.enter_context(patch.object(inputs,'load_registry',return_value=f.registry))

    def prepare(self):
        f=self.fixture;selected=VALIDATION.select_sync(f.args,api=f.api)
        f.args.expected_selection=selected['selection']
        f.args.expected_empty_setup=selected.get('empty_setup','')
        return selected

    def run_without_tests(self):
        f=self.fixture
        with patch.object(execution,'execute',side_effect=AssertionError('no candidate command')), \
                patch.object(execution,'capture_execution_environment',side_effect=AssertionError('no unused E')), \
                patch.object(VALIDATION,'_execute_ci',side_effect=AssertionError('no CI command')), \
                patch.object(VALIDATION,'_bounded_junit',side_effect=AssertionError('no fictitious JUnit suite')), \
                patch.object(VALIDATION,'_native_zero_setup',side_effect=AssertionError('no prior-proof setup')):
            return VALIDATION.validate_sync(f.args,api=f.api)

    def test_namespace_output_recognizes_only_exact_verified_empty_marker(self):
        selected = self.prepare()
        original = deepcopy(selected)
        self.assertFalse(VALIDATION.requires_artifact_namespace(selected))
        self.assertEqual(selected, original)
        for name, value in (('empty_setup', 'sha256:' + 'f' * 64),
                            ('consumer_setup', 'required'), ('full_host', True),
                            ('native_setup', 'sha256:' + 'e' * 64)):
            changed = deepcopy(selected); changed[name] = value
            with self.subTest(field=name):
                self.assertTrue(VALIDATION.requires_artifact_namespace(changed))
        self.assertEqual(self.fixture.executed(), [])

    def test_early_empty_selection_and_final_validation_need_no_test_or_original_E(self):
        f=self.fixture
        with patch.object(execution,'execute',side_effect=AssertionError('no early candidate command')), \
                patch.object(execution,'capture_execution_environment',side_effect=AssertionError('no early E')), \
                patch.object(VALIDATION,'_native_zero_setup',side_effect=AssertionError('not native reused evidence')):
            selected=self.prepare()
        self.assertEqual(selected['lane'],'verified-empty');self.assertFalse(selected['full_host'])
        self.assertEqual(selected['consumer_setup'],'none');self.assertEqual(selected['empty_setup'],selected['selection'])
        self.assertNotIn('native_setup',selected);self.assertEqual(selected['suites'],[])
        with patch.object(VALIDATION,'_differential',wraps=VALIDATION._differential) as actual:
            result=self.run_without_tests()
        actual.assert_called_once();self.assertEqual(result['mode'],'verified-empty')
        self.assertEqual(result['kind'],'sync-no-execution-validation-v1')
        self.assertIsNone(result['execution']);self.assertIsNone(result['parent_evidence'])
        self.assertFalse(result['reusable']);self.assertFalse(result['qualification'])
        self.assertEqual(result['executed_suites'],[]);self.assertEqual(result['reused_suites'],[])
        self.assertFalse(f.args.junit.exists());self.assertEqual(f.executed(),[])
        self.assertEqual(json.loads(f.args.receipt.read_bytes()),result)
        self.assertGreaterEqual(f.gate.verified_empty_sync.call_count,4)
        f.gate.native_parent_evidence.assert_not_called()

    def test_forged_marker_prior_native_marker_and_nonempty_selection_cannot_skip_work(self):
        f=self.fixture;self.prepare()
        for kind in ('missing','changed','prior-native','no-proof','not-empty'):
            f.args.expected_empty_setup=self.proof_selection=f.args.expected_selection
            f.args.expected_native_setup=''
            f.gate.verified_empty_sync.side_effect=lambda *args:deepcopy(self.proof)
            if kind=='missing':f.args.expected_empty_setup=''
            elif kind=='changed':f.args.expected_empty_setup='sha256:'+'f'*64
            elif kind=='prior-native':f.args.expected_native_setup='sha256:'+'e'*64
            elif kind=='no-proof':f.gate.verified_empty_sync.side_effect=lambda *args:None
            else:f.request.changed_paths=('libraries/alpha.cpp',)
            with self.subTest(kind=kind),self.assertRaises(VALIDATION.ValidationError):self.run_without_tests()
            self.assertFalse(f.args.receipt.exists());self.assertEqual(f.executed(),[])
        f.request.changed_paths=()

    def test_missing_initial_proof_retains_default_setup_not_an_empty_execution_claim(self):
        f=self.fixture;f.gate.verified_empty_sync.return_value=None;f.gate.verified_empty_sync.side_effect=None
        # Avoid the independently existing native reuse lookup. Its absence is
        # unrelated to no-change source equality and cannot authorize omission.
        with patch.object(VALIDATION,'_native_zero_setup',return_value=(None,None)):
            selected=VALIDATION.select_sync(f.args,api=f.api)
        self.assertEqual(selected['lane'],'complete');self.assertTrue(selected['full_host'])
        self.assertNotIn('consumer_setup',selected);self.assertNotIn('empty_setup',selected)
        self.assertEqual(f.executed(),[])

    def test_source_or_ref_bookend_drift_after_real_differential_fails_without_fallback(self):
        f=self.fixture;self.prepare()
        original=deepcopy(self.proof)
        for kind in ('source','ref','tree'):
            self.proof=deepcopy(original)
            f.api.pr=deepcopy(f.pr)
            def differential(*args):
                if kind=='source':self.proof['source']['controller']='changed default'
                elif kind=='ref':f.api.pr['head']['sha']='f'*40
                else:self.proof['immutable']['tree']='f'*40
            with self.subTest(kind=kind),patch.object(VALIDATION,'_differential',side_effect=differential), \
                    self.assertRaises(VALIDATION.ValidationError):self.run_without_tests()
            self.assertFalse(f.args.receipt.exists());self.assertEqual(f.executed(),[])

    def test_future_workflow_gates_all_setup_and_uses_distinct_final_source_proof(self):
        import yaml
        path=VALIDATION.ROOT/'tools/repository-checks/workflows/sync-ci-selection.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['validate']['steps']
        for name in ('Set up candidate Python','Set up candidate Node.js','Set up candidate Java',
                'Install candidate host prerequisites','Prepare isolated shared and product Python validators'):
            condition=next(step['if'] for step in steps if step['name']==name)
            self.assertIn("!(steps.select.outputs.lane == 'verified-empty' && steps.select.outputs.consumer_setup == 'none' && steps.select.outputs.empty_setup != '')",condition)
            self.assertIn("steps.select.outputs.native_setup == ''",condition)
        step=next(row for row in steps if row['name']=='Validate the exact unchanged synchronization without test execution')
        self.assertEqual(step['if'],"steps.select.outputs.lane == 'verified-empty'")
        self.assertTrue(step['run'].startswith('python3 -B '))
        self.assertIn('--expected-empty-setup "$EXPECTED_EMPTY_SETUP"',step['run'])
        self.assertNotIn('--expected-native-setup',step['run'])
        normal=next(row for row in steps if row['name']=='Verify exact candidate suites and complete runtime identity')
        self.assertIn("steps.select.outputs.lane != 'verified-empty'",normal['if'])
        active=(VALIDATION.ROOT/'.github/workflows/sync-validation.yml').read_text()
        packages,generation=self.workflow_fixture_generation(VALIDATION.ROOT)
        if generation=='protected-producer-original-default-v1':
            self.assertEqual(active,path.read_text())
            self.assertIn('expected-empty-setup',active)
            # Bind every independently stored canonical endpoint as well as the
            # deployed complete catalog; no old catalog row is rewritten.
            sources={'.github/workflows/project-tests.yml':'producers/protected-project-tests-android-platform.yml',
                '.github/workflows/parent-qualification.yml':'producers/parent-qualification-android-platform.yml',
                '.github/workflows/repository-checks.yml':'producers/repository-checks.yml',
                '.github/workflows/sync-validation.yml':'sync-ci-selection.yml',
                '.github/workflows/browser-client.yml':'npm-consumers/browser-client.yml',
                '.github/workflows/pr-metadata-context.yml':'metadata-edits/pr-metadata-context.yml'}
            self.assertEqual(set(sources),set(packages.METADATA_WORKFLOW_PATHS))
            for target,relative in sources.items():
                self.assertEqual((VALIDATION.ROOT/target).read_bytes(),
                    (VALIDATION.ROOT/'tools/repository-checks/workflows'/relative).read_bytes(),target)
        else:
            self.assertNotIn('expected-empty-setup',active)

    def test_empty_workflow_state_rejects_altered_missing_alias_mode_and_mixed_recipes(self):
        import shutil
        packages,generation=self.workflow_fixture_generation(VALIDATION.ROOT)
        reviewed=next(row for row in packages.workflow_generations() if row['name']==generation)
        self.assertEqual(set(reviewed['workflows']),set(packages.CONSUMER_WORKFLOW_PATHS
            if generation=='npm-consumers-sync-ci-v1' else packages.METADATA_WORKFLOW_PATHS))
        sync='.github/workflows/sync-validation.yml'
        for kind in ('altered','missing','alias','mode','mixed'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(prefix='sync-whole-generation-') as temporary:
                snapshot=Path(temporary)
                for relative in reviewed['workflows']:
                    target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(VALIDATION.ROOT/relative,target);target.chmod(0o644)
                self.assertEqual(packages.validate_wiring(snapshot),generation)
                target=snapshot/sync
                if kind=='altered':target.write_text(target.read_text()+'\n# unreviewed recipe\n')
                elif kind=='missing':target.unlink()
                elif kind=='alias':
                    saved=target.with_suffix('.fixture');target.rename(saved);target.symlink_to(saved.name)
                elif kind=='mode':target.chmod(0o755)
                elif generation=='npm-consumers-sync-ci-v1':
                    target.write_bytes((VALIDATION.ROOT/'tools/repository-checks/workflows/sync-ci-selection.yml').read_bytes())
                else:
                    (snapshot/'.github/workflows/project-tests.yml').write_bytes(
                        (VALIDATION.ROOT/'tools/repository-checks/workflows/host/project-tests.yml').read_bytes())
                with self.assertRaises(ValueError):packages.validate_wiring(snapshot)


class EffectiveBaseConsumerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = IsolatedConsumerTests('test_full_reuse_empty_product_profile_executes_zero_shared_tests')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_fresh_api_snapshot_is_forwarded_separately_from_original_snapshot_and_live_base(self):
        f = self.fixture; f.ci_fixture(quick_beta=True)
        original_snapshot = f.git('rev-parse', f.base + '^')
        f.request.event_base_sha = original_snapshot
        contexts = []
        def current_context(api, request, *, event_pr=None):
            observed = f.pr if event_pr is None else event_pr
            value = {'base': request.base_sha, 'head': request.head_sha, 'candidate': request.merge_sha,
                     'event_base': observed['base']['sha']}
            contexts.append(deepcopy(value))
            return SimpleNamespace(planning=lambda: dict(value))
        f.gate.recheck_effective_request = current_context
        def plan(candidate, event, source, *, pr_context):
            self.assertEqual(event['pull_request']['base']['sha'], f.base)
            self.assertEqual(pr_context, {'base': f.base, 'head': f.parent, 'candidate': f.commit, 'event_base': f.base})
            self.assertNotEqual(pr_context['event_base'], original_snapshot)
            return f.ci_package_plan(candidate, event, source)
        f.ci_packages.candidate_plan.side_effect = plan
        selected = f.ci_prepare()
        self.assertEqual(selected['lane'], 'affected-ci')
        self.assertTrue(contexts)
        self.assertEqual(f.request.event_base_sha, original_snapshot)
        self.assertEqual(f.executed(), [])

    def test_candidate_differential_uses_complete_live_inventory_and_missing_paths_fail_before_commands(self):
        f = self.fixture; f.request.event_base_sha = 'c' * 40
        documents = [{'filename': 'libraries/alpha.cpp', 'status': 'modified'}]
        f.gate.immutable_change_documents = Mock(return_value=documents)
        f.gate.paginate_pull_files = Mock(side_effect=AssertionError('capped PR files cannot replace live inventory'))
        with patch.object(VALIDATION, '_differential') as differential:
            VALIDATION._candidate_differential(f.candidate, f.request, f.gate, f.api)
            differential.assert_called_once_with(f.candidate, f.request, documents)
        f.gate.immutable_change_documents.return_value = []
        with patch.object(VALIDATION, '_differential') as differential:
            with self.assertRaises(VALIDATION.ValidationError):
                VALIDATION._candidate_differential(f.candidate, f.request, f.gate, f.api)
            differential.assert_not_called()
        f.gate.paginate_pull_files.assert_not_called()
        self.assertEqual(f.executed(), [])


if __name__ == "__main__":
    unittest.main()
