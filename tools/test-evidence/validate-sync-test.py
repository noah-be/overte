#!/usr/bin/env python3
"""Offline isolated-consumer regressions using tiny immutable suite fixtures."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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

    def validate(self, *, actual_environment=None, runtime_failure=None, execute_override=None, extra_environment=None):
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

    def test_candidate_secrets_are_removed_and_trusted_read_token_is_restored(self):
        with patch.dict(os.environ, {"GH_TOKEN": "original", "GITHUB_OUTPUT": "command-file"}):
            with VALIDATION.candidate_environment():
                self.assertNotIn("GH_TOKEN", os.environ)
                self.assertNotIn("GITHUB_OUTPUT", os.environ)
            self.assertEqual(os.environ["GH_TOKEN"], "original")
            self.assertEqual(os.environ["GITHUB_OUTPUT"], "command-file")


if __name__ == "__main__":
    unittest.main()
