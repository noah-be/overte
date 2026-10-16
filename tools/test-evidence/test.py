#!/usr/bin/env python3
"""Behavioral regressions for trusted, complete test input identities."""

from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("test_evidence_inputs", Path(__file__).with_name("inputs.py"))
INPUTS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(INPUTS)


def entry(content: str, mode: str = "100644", object_type: str = "blob") -> dict:
    return {"mode": mode, "type": object_type, "sha": hashlib.sha1(content.encode()).hexdigest()}


def registry() -> dict:
    definition = {
        "command": ["python", "tests/feature/test.py"], "layer": "host", "scope": "content",
        "environment": "host-qt5-qt6",
        "closure": {
            "kind": "patterns", "inputs": ["tests/feature/**", "libraries/feature/**", "tests/shared-helper.py"],
            "required": ["tests/feature/test.py", "libraries/feature/Feature.cpp"],
        },
    }
    repository = deepcopy(definition)
    repository["closure"] = {"kind": "repository", "inputs": [], "required": []}
    context = deepcopy(definition)
    context["scope"] = "candidate"
    return {
        "schema": 1, "control_inputs": ["tools/test-evidence/**", "tests/run-project-tests.py"],
        "suites": {"feature": definition, "unreviewed": repository, "context": context},
    }


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.registry = registry()
        self.tree = {
            "tools/test-evidence/inputs.py": entry("trusted verifier"),
            "tests/run-project-tests.py": entry("trusted runner"),
            "tests/feature/test.py": entry("feature driver"),
            "tests/feature/fixture.cpp": entry("fixture"),
            "tests/shared-helper.py": entry("imported helper"),
            "libraries/feature/Feature.cpp": entry("production source"),
            "libraries/feature/Feature.h": entry("production header"),
            "libraries/feature/vendor": entry("submodule commit", "160000", "commit"),
            "README.md": entry("unrelated documentation"),
        }
        self.environment = {"image": "ubuntu-24.04-20261001", "python": "3.12.12", "qt": {"major": 6, "backend": "software"}}

    def fingerprint(self, name="feature", tree=None, registry_override=None, environment=None):
        return INPUTS.suite_fingerprint(
            registry_override or self.registry, name, self.tree if tree is None else tree,
            self.environment if environment is None else environment,
        )

    def proofs(self):
        return {name: {"status": "passed", "fingerprint": self.fingerprint(name)} for name in self.registry["suites"]}

    def plan(self, tree=None, results=None, environment=None, registry_override=None):
        return INPUTS.plan_reuse(
            registry_override or self.registry, self.tree, self.tree if tree is None else tree,
            self.proofs() if results is None else results, self.environment,
            self.environment if environment is None else environment,
        )

    def test_unchanged_content_reuses_only_content_scoped_suites(self):
        plan = self.plan()
        self.assertEqual(plan["reused"], ["feature", "unreviewed"])
        self.assertEqual(plan["required"], ["context"])

    def test_complete_candidate_source_header_helper_and_fixture_differences_rerun(self):
        # No parent-delta argument exists: historical child changes remain visible.
        for path in ("libraries/feature/Feature.cpp", "libraries/feature/Feature.h",
                     "tests/shared-helper.py", "tests/feature/fixture.cpp"):
            with self.subTest(path=path):
                candidate = deepcopy(self.tree)
                candidate[path] = entry("historical child adaptation")
                self.assertIn("feature", self.plan(candidate)["required"])

    def test_deleted_optional_or_required_inputs_cannot_reuse(self):
        for path in ("libraries/feature/Feature.cpp", "libraries/feature/Feature.h"):
            with self.subTest(path=path):
                candidate = deepcopy(self.tree)
                del candidate[path]
                self.assertIn("feature", self.plan(candidate)["required"])

    def test_added_input_renamed_input_and_executable_mode_change_rerun(self):
        added = deepcopy(self.tree)
        added["libraries/feature/NewHeader.h"] = entry("new transitive input")
        renamed = deepcopy(self.tree)
        renamed["libraries/feature/Renamed.h"] = renamed.pop("libraries/feature/Feature.h")
        executable = deepcopy(self.tree)
        executable["tests/feature/test.py"]["mode"] = "100755"
        for candidate in (added, renamed, executable):
            self.assertIn("feature", self.plan(candidate)["required"])

    def test_gitlink_changes_and_symlink_type_changes_rerun(self):
        gitlink = deepcopy(self.tree)
        gitlink["libraries/feature/vendor"] = entry("different submodule commit", "160000", "commit")
        symlink = deepcopy(self.tree)
        symlink["libraries/feature/Feature.h"] = entry("some-target", "120000")
        for candidate in (gitlink, symlink):
            self.assertIn("feature", self.plan(candidate)["required"])

    def test_unchanged_symlink_cannot_hide_a_referent_outside_the_closure(self):
        tree = deepcopy(self.tree)
        tree["libraries/feature/Feature.h"] = entry("../../unowned/ActualHeader.h", "120000")
        with self.assertRaises(INPUTS.InputError):
            self.fingerprint(tree=tree)
        plan = INPUTS.plan_reuse(self.registry, tree, tree, self.proofs(), self.environment, self.environment)
        self.assertIn("feature", plan["required"])

    def test_unrelated_source_preserves_precise_reuse_but_not_repository_fallback(self):
        candidate = deepcopy(self.tree)
        candidate["README.md"] = entry("new unrelated documentation")
        plan = self.plan(candidate)
        self.assertIn("feature", plan["reused"])
        self.assertIn("unreviewed", plan["required"])

    def test_control_input_changes_invalidate_every_content_proof(self):
        candidate = deepcopy(self.tree)
        candidate["tools/test-evidence/inputs.py"] = entry("new trusted verifier")
        self.assertEqual(self.plan(candidate)["reused"], [])

    def test_runtime_toolchain_configuration_and_backend_drift_rerun(self):
        for value in ({"python": "3.13"}, {"image": "ubuntu-24.04-new"},
                      {"qt": {"major": 5, "backend": "software"}},
                      {"qt": {"major": 6, "backend": "hardware"}}, {"instrumentation": "coverage"}):
            with self.subTest(value=value):
                self.assertEqual(self.plan(environment=self.environment | value)["reused"], [])

    def test_suite_command_and_definition_changes_reject_old_proof(self):
        for field, value in (("command", ["python", "tests/feature/test.py", "--new-assertions"]),
                             ("environment", "new-host-contract"), ("layer", "quick")):
            with self.subTest(field=field):
                changed = deepcopy(self.registry)
                changed["suites"]["feature"][field] = value
                plan = self.plan(registry_override=changed)
                self.assertIn("feature", plan["required"])
                self.assertIn("unreviewed", plan["reused"])

    def test_unrelated_suite_definition_change_does_not_invalidate_precise_suite(self):
        changed = deepcopy(self.registry)
        changed["suites"]["unreviewed"]["command"].append("--new")
        self.assertEqual(self.fingerprint(), self.fingerprint(registry_override=changed))

    def test_old_parent_input_proof_is_independently_recomputed(self):
        forged = self.proofs()
        forged["feature"]["fingerprint"] = "sha256:" + "0" * 64
        self.assertIn("feature", self.plan(results=forged)["required"])

    def test_missing_failed_skipped_malformed_proof_requires_execution(self):
        proofs = [None, {}, {"status": "failed", "fingerprint": self.fingerprint()},
                  {"status": "skipped", "fingerprint": self.fingerprint()},
                  {"status": "passed", "fingerprint": "invalid"},
                  {"status": "passed", "fingerprint": self.fingerprint(), "unverified": True}]
        for proof in proofs:
            with self.subTest(proof=proof):
                results = {} if proof is None else {"feature": proof}
                self.assertIn("feature", self.plan(results=results)["required"])

    def test_unknown_suite_and_malformed_global_identity_cannot_authorize(self):
        with self.assertRaises(INPUTS.InputError):
            self.plan(results={"not-registered": {}})
        with self.assertRaises(INPUTS.InputError):
            INPUTS.suite_fingerprint(self.registry, "unknown", self.tree, self.environment)
        for environment in ({}, [], {"not-finite": float("nan")}, {1: "not-json-key"}):
            with self.subTest(environment=environment), self.assertRaises(INPUTS.InputError):
                self.fingerprint(environment=environment)

    def test_canonical_order_is_independent_of_tree_and_environment_object_order(self):
        self.assertEqual(self.fingerprint(), self.fingerprint(
            tree=dict(reversed(list(self.tree.items()))),
            environment=dict(reversed(list(self.environment.items())))))

    def test_missing_required_parent_inputs_cannot_authorize_reuse(self):
        parent = deepcopy(self.tree)
        del parent["libraries/feature/Feature.cpp"]
        plan = INPUTS.plan_reuse(self.registry, parent, self.tree, self.proofs(), self.environment, self.environment)
        self.assertIn("feature", plan["required"])

    def test_invalid_trees_fail_closed(self):
        cases = [
            {"../outside": entry("outside")}, {"/absolute": entry("outside")},
            {"a/../b": entry("outside")}, {"a//b": entry("noncanonical")},
            {"bad": {"mode": "160000", "type": "blob", "sha": "a" * 40}},
            {"bad": {"mode": "100644", "type": "blob", "sha": "not-object"}},
            {"bad": {"mode": "040000", "type": "tree", "sha": "a" * 40}},
        ]
        for tree in cases:
            with self.subTest(tree=tree), self.assertRaises(INPUTS.InputError):
                self.fingerprint(tree=tree)

    def test_selected_entries_preserve_gitlink_symlink_modes_and_sort_paths(self):
        tree = {"z": entry("commit", "160000", "commit"), "a": entry("target", "120000")}
        selected = INPUTS.selected_entries(tree, ["*"])
        self.assertEqual([item["path"] for item in selected], ["a", "z"])
        self.assertEqual([item["mode"] for item in selected], ["120000", "160000"])
        self.assertEqual(selected[-1]["type"], "commit")


class RegistryTests(unittest.TestCase):
    def load(self, source):
        with tempfile.TemporaryDirectory(prefix="overte-input-registry-") as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(source if isinstance(source, str) else json.dumps(source), encoding="utf-8")
            return INPUTS.load_registry(path)

    def test_valid_registry_round_trip(self):
        self.assertEqual(self.load(registry()), registry())

    def test_registry_rejects_unknown_fields_duplicates_unsafe_paths_and_silent_narrowing(self):
        invalid = []
        for field, value in (("extra", True), ("schema", True), ("control_inputs", []), ("suites", {})):
            changed = registry()
            changed[field] = value
            invalid.append(changed)
        for section, value in (("command", ["python3", "tests/feature/test.py"]),
                               ("command", ["/tmp/python", "tests/feature/test.py"]),
                               ("scope", "branch"), ("layer", "native"), ("extra", True)):
            changed = registry()
            changed["suites"]["feature"][section] = value
            invalid.append(changed)
        for field, value in (("kind", "unknown"), ("inputs", []),
                             ("inputs", ["../unsafe"]), ("inputs", ["same", "same"]),
                             ("required", ["outside/closure.py"]), ("required", ["tests/feature/*.py"])):
            changed = registry()
            changed["suites"]["feature"]["closure"][field] = value
            invalid.append(changed)
        changed = registry()
        changed["suites"]["unreviewed"]["closure"]["inputs"] = ["only-some-files"]
        invalid.append(changed)
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(INPUTS.InputError):
                self.load(source)
        with self.assertRaises(INPUTS.InputError):
            self.load('{"schema":1,"schema":1,"control_inputs":["a"],"suites":{}}')


class ImmutableGitTreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-input-tree-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Input identity fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.fileMode", "true")

    def git(self, *arguments):
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *arguments], cwd=self.root,
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def test_reads_immutable_commits_including_modes_symlinks_and_gitlinks(self):
        executable = self.root / "candidate.py"
        executable.write_text("raise RuntimeError('candidate must never execute')\n", encoding="utf-8")
        executable.chmod(0o755)
        (self.root / "source.cpp").write_text("original\n", encoding="utf-8")
        os.symlink("source.cpp", self.root / "source-link")
        self.git("add", ".")
        self.git("commit", "-qm", "Immutable source fixture")
        previous = self.git("rev-parse", "HEAD")
        self.git("update-index", "--add", "--cacheinfo", "160000," + previous + ",vendor")
        self.git("commit", "-qm", "Add immutable submodule fixture")
        (self.root / "source.cpp").write_text("uncommitted candidate difference\n", encoding="utf-8")
        tree = INPUTS.full_tree(self.root)
        self.assertEqual(tree["source.cpp"]["sha"], self.git("rev-parse", previous + ":source.cpp"))
        self.assertEqual(tree["candidate.py"]["mode"], "100755")
        self.assertEqual(tree["source-link"]["mode"], "120000")
        self.assertEqual(tree["vendor"], {"mode": "160000", "type": "commit", "sha": previous})
        self.assertNotIn("vendor", INPUTS.full_tree(self.root, previous))

    def test_invalid_commit_cannot_fall_back_to_current_tree(self):
        for commit in ("does-not-exist", "--all", "", "HEAD\0"):
            with self.subTest(commit=commit), self.assertRaises(INPUTS.InputError):
                INPUTS.full_tree(self.root, commit)


def load_tests(loader, tests, pattern):
    """Aggregate independently owned regressions without importing this main twice."""
    for filename in ("registry-test.py", "runtime-test.py", "execution-test.py", "qualification-producer-test.py",
                     "validate-sync-test.py", "sandbox-test.py", "sandbox-host-test.py"):
        path = Path(__file__).with_name(filename)
        spec = importlib.util.spec_from_file_location("test_evidence_" + filename.replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


if __name__ == "__main__":
    unittest.main()
