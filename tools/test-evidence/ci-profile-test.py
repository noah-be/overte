#!/usr/bin/env python3
"""Pure finite CI37 source preparation and fail-closed admission regressions."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ci_profile as C
import inputs


class ProfileFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = inputs.load_registry(C.ROOT / ".github/test-suites.json")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="overte-ci37-pinned-source-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        pinned = self.root / C.PINNED_SOURCE
        pinned.parent.mkdir()
        pinned.write_text('{"reviewed_lock_sources":{"fixture":{"readers":"initial"}}}\n', encoding="utf-8")
        self.entry = {"mode": "100644", "type": "blob", "sha": "a" * 40}
        self.tree = {path: deepcopy(self.entry) for path in (
            C.POLICY, ".github/test-suites.json", "README.md", "tests/PROJECT_TESTING.md",
            "docs/BRANCH_WORKFLOW.md", ".github/workflows/project-tests.yml",
            ".github/workflows/repository-checks.yml", ".github/workflows/parent-qualification.yml",
            ".github/workflows/sync-validation.yml", ".github/workflows/browser-client.yml",
            ".github/workflows/codeql.yml", "tools/branch-policy/check.py",
            "tools/test-evidence/runtime.py", "tests/run-project-tests.py",
            "tests/native-registration-test.py", "tests/CMakeLists.txt",
            "cmake/macros/SetupHifiTestCase.cmake", "libraries/example/src/Example.cpp",
            "browser-client/package-lock.json",
        )}
        self.tree[C.PINNED_SOURCE] = C._pinned_source_entry(self.root)
        self.blobs = {}
        self.cleanup = json.loads((C.ROOT / C.DATA_PATH).read_bytes())
        self.tree[C.DATA_PATH] = self.blob(json.dumps(self.cleanup).encode())
        self.selection = {"suites": list(C.SUITES), "reason": "reviewed-ci-only-inputs",
                          "full_host": False, "include_platform": False}
        self.policy = {"schema": 1, "enabled": False, "profile": C.PROFILE,
                       "epoch": "ubuntu24-ci37-source-fixture-v1", "suites": list(C.SUITES),
                       "not_before": "2026-10-16T00:00:00Z", "max_age_seconds": 259200,
                       "definition_digest": C.definition_digest(self.registry),
                       "generation_digest": C.generation(self.tree, self.registry)}

    def blob(self, raw):
        sha = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        self.blobs[sha] = raw
        return {"mode":"100644","type":"blob","sha":sha}

    def admit(self, *, candidate=None, trusted=None, selection=None, registry=None, **options):
        return C.validate_selection(
            self.selection if selection is None else selection,
            self.tree if candidate is None else candidate,
            self.tree if trusted is None else trusted,
            self.registry if registry is None else registry,
            policy=self.policy, require_enabled=False, root=self.root,
            read_blob=options.pop("read_blob",self.blobs.__getitem__), **options)


class CIProfileTests(ProfileFixture):
    def test_exact_source_preparation_returns_only_reviewed_profile_bindings(self):
        result = self.admit()
        self.assertEqual(result, {
            "schema": 2, "profile": "ubuntu24-ci37-v1", "epoch": self.policy["epoch"],
            "suites": list(C.SUITES), "definition_digest": self.policy["definition_digest"],
            "generation_digest": self.policy["generation_digest"],
            "policy_digest": C.policy_identity(self.policy),
            "pinned_source": {"path": C.PINNED_SOURCE, **self.tree[C.PINNED_SOURCE]},
        })
        self.assertEqual(len(result["suites"]), 37)

    def test_shipping_controlled_attempt_still_requires_both_independent_gates(self):
        self.assertTrue(C.SOURCE_READY)
        shipping = C.load_policy()
        self.assertTrue(shipping["enabled"])
        self.assertEqual(shipping["suites"], list(C.SUITES))
        for source_ready, enabled in ((False, False), (False, True), (True, False)):
            policy = {**self.policy, "enabled": enabled}
            with self.subTest(source=source_ready, policy=enabled), patch.object(C, "SOURCE_READY", source_ready):
                with self.assertRaises(C.CIProfileError):
                    C.validate_selection(self.selection, self.tree, self.tree, self.registry, policy=policy,root=self.root)

    def test_default_admission_checks_both_reviewed_activation_gates(self):
        policy = {**self.policy, "enabled": True}
        with patch.object(C, "SOURCE_READY", True):
            self.assertEqual(C.validate_selection(self.selection, self.tree, self.tree, self.registry,
                                                policy=policy,root=self.root,read_blob=self.blobs.__getitem__)["suites"], list(C.SUITES))

    def test_extra_missing_reordered_product_and_platform_owners_are_rejected(self):
        variants = [list(C.SUITES[:-1]), list(reversed(C.SUITES)),
                    [*C.SUITES, "codeql-remediation"], [*C.SUITES, "pico4-device-free"],
                    [*C.SUITES[:-1], "device-control-plane-full"], tuple(C.SUITES)]
        for suites in variants:
            with self.subTest(suites=suites), self.assertRaises(C.CIProfileError):
                self.admit(selection={**self.selection, "suites": suites})

    def test_full_control_plane_unknown_reason_and_extra_selection_fields_fail(self):
        variants = [{"full_host": True}, {"full_host": 0}, {"include_platform": True},
                    {"reason": "reviewed-ci-with-control-plane-update"}, {"reason": []},
                    {"platform": {}}, {"extra_commands": []}]
        for change in variants:
            with self.subTest(change=change), self.assertRaises(C.CIProfileError):
                self.admit(selection={**self.selection, **change})

    def test_only_known_regular_main_plan_can_use_ci37(self):
        for options in ({"target": "apple-ios"}, {"target": None}, {"regular": False},
                        {"regular": 1}, {"unknown": True}, {"unknown": 0}):
            with self.subTest(options=options), self.assertRaises(C.CIProfileError):
                self.admit(**options)

    def test_changed_command_closure_import_definition_and_control_inputs_fail(self):
        for field, value in (
                ("command", ["python", "tests/changed-reader.py"]),
                ("environment", "new-runtime"),
                ("closure", {"kind": "repository", "inputs": [], "required": []})):
            registry = deepcopy(self.registry)
            definition = registry["suites"]["producer-proof"]
            definition.pop("python_imports", None)
            definition[field] = value
            with self.subTest(field=field), self.assertRaises(C.CIProfileError):
                self.admit(registry=registry)
        registry = deepcopy(self.registry)
        registry["control_inputs"].append("new-lookup/**")
        with self.assertRaises(C.CIProfileError):
            self.admit(registry=registry)

    def test_extra_commands_and_truncated_registry_fail(self):
        registry = deepcopy(self.registry)
        registry["suites"]["new-command"] = deepcopy(registry["suites"]["producer-proof"])
        with self.assertRaises(C.CIProfileError):
            self.admit(registry=registry)
        registry = deepcopy(self.registry)
        del registry["suites"]["safe-landing-lifecycle"]
        with self.assertRaises(C.CIProfileError):
            self.admit(registry=registry)

    def test_renamed_product_owner_or_changed_host_layer_cannot_fake_complete_registry(self):
        registry = deepcopy(self.registry)
        definition = registry["suites"].pop("safe-landing-lifecycle")
        registry["suites"]["unknown-host-owner"] = definition
        self.assertEqual(len(registry["suites"]), 60)
        with self.assertRaises(C.CIProfileError):
            self.admit(registry=registry)
        registry = deepcopy(self.registry)
        registry["suites"]["safe-landing-lifecycle"]["layer"] = "quick"
        with self.assertRaises(C.CIProfileError):
            self.admit(registry=registry)

    def test_changed_sources_native_registration_and_product_inputs_fail(self):
        for path in ("tools/branch-policy/check.py", "tools/test-evidence/runtime.py",
                     "tests/run-project-tests.py", "tests/native-registration-test.py",
                     "tests/CMakeLists.txt", "cmake/macros/SetupHifiTestCase.cmake",
                     "libraries/example/src/Example.cpp", ".github/test-suites.json"):
            candidate = deepcopy(self.tree)
            candidate[path]["sha"] = "b" * 40
            with self.subTest(path=path), self.assertRaises(C.CIProfileError):
                self.admit(candidate=candidate)

    def test_new_import_shadow_native_module_package_ancestor_and_lookup_membership_fail(self):
        for path in ("tests/json.py", "tests/sitecustomize.py", "tests/new.pyc", "tests/new.pyo",
                     "tests/new.so", "tests/new.pyd", "tests/new.pth", "package.json",
                     "tools/package.json", "tests/new/CMakeLists.txt", "docs/new.md"):
            candidate = deepcopy(self.tree)
            candidate[path] = deepcopy(self.entry)
            with self.subTest(path=path), self.assertRaises(C.CIProfileError):
                self.admit(candidate=candidate)

    def test_deleted_inputs_and_modes_remain_bound(self):
        for path in ("tests/native-registration-test.py", "README.md"):
            candidate = deepcopy(self.tree)
            del candidate[path]
            with self.subTest(deleted=path), self.assertRaises(C.CIProfileError):
                self.admit(candidate=candidate)
        candidate = deepcopy(self.tree)
        candidate["tools/branch-policy/check.py"]["mode"] = "100755"
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=candidate)

    def test_aliases_gitlinks_and_executable_data_fail_before_execution(self):
        for path, mode, kind in (("tests/json.py", "120000", "blob"),
                                 ("new-module", "160000", "commit"),
                                 ("README.md", "100755", "blob")):
            candidate = deepcopy(self.tree)
            candidate[path] = {**self.entry, "mode": mode, "type": kind}
            with self.subTest(path=path, mode=mode), self.assertRaises(C.CIProfileError):
                self.admit(candidate=candidate)

    def test_only_exact_reviewed_documentation_bytes_may_change(self):
        for path in ("README.md", "tests/PROJECT_TESTING.md", "docs/BRANCH_WORKFLOW.md"):
            candidate = deepcopy(self.tree)
            candidate[path]["sha"] = "b" * 40
            with self.subTest(path=path):
                self.assertEqual(self.admit(candidate=candidate)["generation_digest"],
                                 self.policy["generation_digest"])
        candidate = deepcopy(self.tree)
        candidate["tests/PROJECT_TESTING.mdx"] = deepcopy(self.entry)
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=candidate)

    def test_all_active_workflow_bytes_remain_executable_generation_inputs(self):
        for path in (".github/workflows/project-tests.yml", ".github/workflows/repository-checks.yml",
                     ".github/workflows/parent-qualification.yml", ".github/workflows/sync-validation.yml",
                     ".github/workflows/browser-client.yml", ".github/workflows/codeql.yml"):
            candidate = deepcopy(self.tree)
            candidate[path]["sha"] = "b" * 40
            with self.subTest(path=path), self.assertRaises(C.CIProfileError):
                self.admit(candidate=candidate)

    def test_drift_in_trusted_generation_or_both_trees_cannot_create_new_admission(self):
        changed = deepcopy(self.tree)
        changed["tests/native-registration-test.py"]["sha"] = "b" * 40
        with self.assertRaises(C.CIProfileError):
            self.admit(trusted=changed)
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=changed, trusted=changed)

    def test_policy_self_exclusion_cannot_authorize_policy_changes_or_absence(self):
        candidate = deepcopy(self.tree)
        candidate[C.POLICY]["sha"] = "b" * 40
        self.assertEqual(C.generation(candidate, self.registry), self.policy["generation_digest"])
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=candidate)
        candidate.pop(C.POLICY)
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=candidate, trusted=candidate)

    def test_exact_android_anchor_cycle_converges_and_keeps_complete_pinned_identity(self):
        first = self.admit()
        pinned = self.root / C.PINNED_SOURCE
        pinned.write_text(json.dumps({"reviewed_lock_sources": {"fixture": {
            "readers": self.policy["generation_digest"]}}}) + "\n", encoding="utf-8")
        settled = deepcopy(self.tree)
        settled[C.PINNED_SOURCE] = C._pinned_source_entry(self.root)
        self.assertNotEqual(settled[C.PINNED_SOURCE], self.tree[C.PINNED_SOURCE])
        self.assertEqual(C.generation(settled, self.registry), self.policy["generation_digest"])
        self.assertEqual(C.generation(settled, self.registry), C.generation(self.tree, self.registry))
        with self.assertRaises(C.CIProfileError):
            self.admit()  # The actual protected bytes changed; the old pin cannot qualify.
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=settled)  # Candidate/trusted disagreement remains forbidden.
        current = self.admit(candidate=settled, trusted=settled)
        self.assertNotEqual(current["pinned_source"], first["pinned_source"])
        self.assertEqual(current["generation_digest"], first["generation_digest"])
        settled["tests/native-registration-test.py"]["sha"] = "b" * 40
        self.assertNotEqual(C.generation(settled, self.registry), self.policy["generation_digest"])
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=settled, trusted=settled)

    def test_pinned_source_is_one_exact_ordinary_leaf_and_both_trees_must_match_actual_bytes(self):
        candidate = deepcopy(self.tree)
        candidate[C.PINNED_SOURCE]["sha"] = "b" * 40
        self.assertEqual(C.generation(candidate,self.registry), self.policy["generation_digest"])
        with self.assertRaises(C.CIProfileError):self.admit(candidate=candidate,trusted=candidate)
        for path in (C.PINNED_SOURCE, ".github/unrelated-policy.json"):
            candidate = deepcopy(self.tree)
            if path == C.PINNED_SOURCE:
                candidate.pop(path)
            else:
                candidate[path] = deepcopy(self.entry)
            with self.subTest(path=path),self.assertRaises(C.CIProfileError):self.admit(candidate=candidate)

    def test_pinned_actual_file_alias_nonregular_executable_oversized_and_parent_alias_fail(self):
        pinned = self.root / C.PINNED_SOURCE
        original = pinned.read_bytes()
        pinned.chmod(0o755)
        with self.assertRaises(C.CIProfileError):self.admit()
        pinned.chmod(0o644)
        pinned.write_bytes(b"x" * 1_000_001)
        with self.assertRaises(C.CIProfileError):self.admit()
        pinned.unlink();pinned.mkdir()
        with self.assertRaises(C.CIProfileError):self.admit()
        pinned.rmdir()
        target = self.root / "actual.json";target.write_bytes(original)
        pinned.symlink_to(target)
        with self.assertRaises(C.CIProfileError):self.admit()
        pinned.unlink();pinned.parent.rmdir()
        actual = self.root / "config";actual.mkdir()
        (actual / pinned.name).write_bytes(original)
        pinned.parent.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(C.CIProfileError):self.admit()

    def test_package_reason_requires_finite_independent_owner_and_still_binds_lock_bytes(self):
        selected = {**self.selection, "reason": "reviewed-ci-and-package-owners",
                    "package_owned_paths": ["browser-client/package-lock.json"]}
        self.assertEqual(self.admit(selection=selected)["suites"], list(C.SUITES))
        for paths in ([], ["unknown/package-lock.json"], ["browser-client/package-lock.json"] * 2, [[]]):
            with self.subTest(paths=paths), self.assertRaises(C.CIProfileError):
                self.admit(selection={**selected, "package_owned_paths": paths})
        candidate = deepcopy(self.tree)
        candidate["browser-client/package-lock.json"]["sha"] = "b" * 40
        with self.assertRaises(C.CIProfileError):
            self.admit(candidate=candidate, selection=selected)

    def test_invalid_tree_and_source_preparation_mode_are_rejected(self):
        for tree in (None, [], {}, {"../escape.py": self.entry}, {"bad.py": {}}):
            with self.subTest(tree=tree), self.assertRaises(C.CIProfileError):
                C.generation(tree, self.registry)
        with self.assertRaises(C.CIProfileError):
            C.validate_selection(self.selection, self.tree, self.tree, self.registry,
                                 policy=self.policy, require_enabled=0)


class CleanupDataTests(ProfileFixture):
    def data_tree(self, value=None, *, raw=None):
        tree = deepcopy(self.tree)
        tree[C.DATA_PATH] = self.blob(json.dumps(self.cleanup if value is None else value).encode() if raw is None else raw)
        return tree

    def test_valid_holds_change_source_fingerprints_without_changing_original_runtime_binding(self):
        value = deepcopy(self.cleanup)
        value["holds"] = {"fix/main/held-branch":"Keep until its verified dependent PR has merged."}
        changed = self.data_tree(value)
        self.assertNotEqual(changed[C.DATA_PATH],self.tree[C.DATA_PATH])
        self.assertEqual(C.generation(changed,self.registry),self.policy["generation_digest"])
        self.assertEqual(self.admit(candidate=changed),self.admit())
        original, candidate = deepcopy(self.tree),deepcopy(changed)
        for path in self.registry["suites"]["branch-cleanup"]["closure"]["required"]:
            original.setdefault(path,deepcopy(self.entry));candidate.setdefault(path,deepcopy(self.entry))
        environment = {"fixture":"unchanged original runtime"}
        self.assertNotEqual(inputs.suite_fingerprint(self.registry,"branch-cleanup",original,environment),
                            inputs.suite_fingerprint(self.registry,"branch-cleanup",candidate,environment))

    def test_every_guard_authenticates_both_complete_blobs_even_when_unchanged(self):
        reads = []
        def read(sha):
            reads.append(sha)
            return self.blobs[sha]
        self.admit(read_blob=read)
        self.assertEqual(reads,[self.tree[C.DATA_PATH]["sha"]]*2)
        reads.clear()
        value = deepcopy(self.cleanup);value["holds"]={"fix/main/review":"Await dependent work."}
        changed = self.data_tree(value)
        self.admit(candidate=changed,read_blob=read)
        self.assertEqual(reads,[self.tree[C.DATA_PATH]["sha"],changed[C.DATA_PATH]["sha"]])

    def test_closed_fixed_contract_rejects_unknown_and_changed_policy_fields_on_either_side(self):
        variants = ({"schema":True},{"schema":2},{"repository":"overte-org/overte"},
            {"repository_id":1319052603.0},{"keep_label":"another-label"},{"artifact_retention_days":31},
            {"artifact_retention_days":30.0},{"permanent_branches":list(reversed(self.cleanup["permanent_branches"]))},
            {"execute":"unreviewed-command"},{"holds":[]})
        for change in variants:
            tree = self.data_tree({**self.cleanup,**change})
            for side in ("candidate","trusted"):
                with self.subTest(change=change,side=side),self.assertRaises(C.CIProfileError):
                    self.admit(**{side:tree})
        missing=deepcopy(self.cleanup);missing.pop("keep_label")
        with self.assertRaises(C.CIProfileError):self.admit(candidate=self.data_tree(missing))

    def test_bounded_plain_holds_and_pure_git_branch_syntax(self):
        for branch in ("fix/main/review","legacy-café","fix/main/"+"x"*231):
            value={**self.cleanup,"holds":{branch:"r"*512}}
            self.admit(candidate=self.data_tree(value))
        value={**self.cleanup,"holds":{f"fix/main/review-{number}":"Await review." for number in range(128)}}
        self.admit(candidate=self.data_tree(value))
        value["holds"]["fix/main/too-many"]="Await review."
        with self.assertRaises(C.CIProfileError):self.admit(candidate=self.data_tree(value))
        for branch in ("", "@", "HEAD", "-option", "/start", "end/", "double//slash", "dot/../escape",
                "dot/.hidden", "suffix.lock", "suffix.lock/nested", "trailing.", "range..name", "log@{1}",
                "has space", "has\\slash", "has[glob", "has?glob", "has*glob", "has~tilde", "has^caret",
                "has:colon", "has\nnewline", "fix/main/"+"x"*232, "x"*121+"é"*60):
            value={**self.cleanup,"holds":{branch:"Await review."}}
            with self.subTest(branch=branch),self.assertRaises(C.CIProfileError):self.admit(candidate=self.data_tree(value))

    def test_blank_unbounded_control_and_structured_reasons_fail(self):
        for reason in ("", "   ", "\u00a0", "x"*513, "line\nbreak", "tab\tbreak", "delete\x7f", "next\x85line",
                "hidden\u200bformat", "surrogate\ud800", None, {}, ["nested"], 1):
            value={**self.cleanup,"holds":{"fix/main/review":reason}}
            with self.subTest(reason=repr(reason)),self.assertRaises(C.CIProfileError):
                self.admit(candidate=self.data_tree(value))

    def test_duplicate_nonfinite_invalid_utf8_and_recursive_json_fail(self):
        duplicate=json.dumps(self.cleanup).replace('"holds": {}','"holds": {}, "holds": {}')
        duplicate_hold=json.dumps(self.cleanup).replace('"holds": {}','"holds": {"fix/main/x":"one","fix/main/x":"two"}')
        for raw in (duplicate.encode(),duplicate_hold.encode(),b'\xff',b'{}',b'['*2000+b'0'+b']'*2000,
                    json.dumps(self.cleanup).replace('"holds": {}','"holds": NaN').encode(),
                    json.dumps(self.cleanup).replace('"holds": {}','"holds": Infinity').encode()):
            with self.subTest(raw=raw[:80]),self.assertRaises(C.CIProfileError):self.admit(candidate=self.data_tree(raw=raw))

    def test_immutable_reader_cannot_supply_claimed_hash_wrong_type_unbounded_or_missing_bytes(self):
        for reader in (None, lambda _sha:b"{}", lambda _sha:"text",lambda _sha:bytearray(b"{}"),
                       lambda _sha:b"x"*64_001):
            with self.subTest(reader=reader),self.assertRaises(C.CIProfileError):self.admit(read_blob=reader)
        def unavailable(_sha):raise OSError("unavailable fixture object")
        with self.assertRaises(C.CIProfileError):self.admit(read_blob=unavailable)
        with self.assertRaises(C.CIProfileError):self.admit(candidate=self.data_tree(raw=b" "*64_001))

    def test_only_exact_existing_ordinary_cleanup_data_path_is_admitted(self):
        for mutation in ("missing","executable","alias","gitlink","sha256","neighbor"):
            changed=deepcopy(self.tree)
            if mutation=="missing":changed.pop(C.DATA_PATH)
            elif mutation=="executable":changed[C.DATA_PATH]["mode"]="100755"
            elif mutation=="alias":changed[C.DATA_PATH]["mode"]="120000"
            elif mutation=="gitlink":changed[C.DATA_PATH].update(mode="160000",type="commit")
            elif mutation=="sha256":changed[C.DATA_PATH]["sha"]="b"*64
            else:changed[".github/branch-cleanup-extra.json"]=deepcopy(self.entry)
            with self.subTest(mutation=mutation),self.assertRaises(C.CIProfileError):self.admit(candidate=changed)


class PolicyFileTests(ProfileFixture):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="overte-ci37-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / C.POLICY
        self.path.parent.mkdir()
        self.write()

    def write(self, value=None):
        self.path.write_text(json.dumps(self.policy if value is None else value), encoding="utf-8")

    def test_fixed_policy_load_is_strict_and_retains_disabled_state(self):
        self.assertEqual(C.load_policy(self.root), self.policy)
        for change in ({"schema": True}, {"schema": 2}, {"enabled": "false"},
                       {"profile": "ubuntu24-host-qt5-qt6-v1"}, {"suites": list(reversed(C.SUITES))},
                       {"generation_digest": "unknown"}, {"epoch": ""}, {"force": True},
                       {"not_before": "2026-02-30T00:00:00Z"}, {"not_before": "2026-10-16"},
                       {"max_age_seconds": True}, {"max_age_seconds": 259201}):
            self.write({**self.policy, **change})
            with self.subTest(change=change), self.assertRaises(C.CIProfileError):
                C.load_policy(self.root)

    def test_duplicate_fields_oversized_missing_and_alias_policy_fail(self):
        for raw in ('{"schema":1,"schema":1}', " " * 32_001, "not-json"):
            self.path.write_text(raw, encoding="utf-8")
            with self.subTest(raw=raw[:30]), self.assertRaises(C.CIProfileError):
                C.load_policy(self.root)
        self.path.unlink()
        with self.assertRaises(C.CIProfileError):
            C.load_policy(self.root)
        target = self.root / "policy.json"
        target.write_text(json.dumps(self.policy), encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises(C.CIProfileError):
            C.load_policy(self.root)

    def test_policy_parent_alias_is_rejected(self):
        self.path.unlink()
        self.path.parent.rmdir()
        target = self.root / "config"
        target.mkdir()
        (target / self.path.name).write_text(json.dumps(self.policy), encoding="utf-8")
        self.path.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaises(C.CIProfileError):
            C.load_policy(self.root)


class DiagnosticActualSourceTests(unittest.TestCase):
    """Actual immutable Git inventory, no suite or host identity execution."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        required={p for name in C.SUITES for p in self.registry['suites'][name]['closure']['required']}
        for p in required:self.write(p,b'fixed diagnostic source fixture\n')
        self.write('.github/test-suites.json',json.dumps(self.registry).encode())
        self.write(C.PINNED_SOURCE,(C.ROOT/C.PINNED_SOURCE).read_bytes())
        self.write(C.DATA_PATH,(C.ROOT/C.DATA_PATH).read_bytes())
        self.policy={key:value for key,value in C.load_policy().items() if key!='generation_kind'}
        self.policy.update(enabled=True,generation_digest='sha256:'+'f'*64,
                           epoch='diagnostic-legacy-whole-tree-fixture',
                           definition_digest=C.definition_digest(self.registry))
        self.write(C.POLICY,json.dumps(self.policy).encode())
        self.git('init','-q','--initial-branch=main')
        self.git('config','user.name','Diagnostic fixture');self.git('config','user.email','fixture@example.invalid')
        self.commit()
        self.selection={'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs',
                        'full_host':False,'include_platform':False}

    def write(self,path,raw):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(0o644)

    def git(self,*arguments):
        return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',
            *arguments],cwd=self.root,stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git('add','--all');self.git('commit','-qm','Complete immutable diagnostic source')
        self.source=self.git('rev-parse','HEAD');self.tree=inputs.full_tree(self.root,self.source)

    def blob(self,oid):
        return subprocess.check_output(['git','cat-file','blob',oid],cwd=self.root)

    def binding(self,**options):
        return C.diagnostic_selection(options.pop('selection',self.selection),
            options.pop('candidate',self.tree),options.pop('trusted',self.tree),
            options.pop('registry',self.registry),source=options.pop('source',self.source),
            source_root=self.root,root=self.root,read_blob=self.blob,**options)

    def test_actual_git_source_can_measure_while_shipping_generation_stays_future_and_unchanged(self):
        before=(self.root/C.POLICY).read_bytes()
        value=self.binding()
        self.assertEqual(value['kind'],C.DIAGNOSTIC_KIND)
        self.assertEqual(value['source_commit'],self.source)
        self.assertEqual(value['source_tree'],self.git('rev-parse','HEAD^{tree}'))
        self.assertEqual(value['production_policy_digest'],C.policy_identity(self.policy))
        self.assertEqual(value['actual_selection']['generation_digest'],C.generation(self.tree,self.registry))
        self.assertNotEqual(value['actual_selection']['generation_digest'],self.policy['generation_digest'])
        self.assertEqual((self.root/C.POLICY).read_bytes(),before)
        with patch.object(C,'SOURCE_READY',True),self.assertRaises(C.CIProfileError):
            C.validate_selection(self.selection,self.tree,self.tree,self.registry,policy=self.policy,
                root=self.root,read_blob=self.blob)

    def test_changed_source_inventory_registry_and_requested_owner_cannot_be_measured(self):
        changed=deepcopy(self.tree);changed['unknown.py']={'mode':'100644','type':'blob','sha':'a'*40}
        registry=deepcopy(self.registry);registry['suites'][C.SUITES[0]]['command'].append('--unreviewed')
        for options in ({'source':'a'*40},{'candidate':changed},{'trusted':changed},{'registry':registry},
                {'selection':{**self.selection,'suites':[*C.SUITES,'device-control-plane-full']}},
                {'selection':{**self.selection,'include_platform':True}}):
            with self.subTest(options=list(options)),self.assertRaises(C.CIProfileError):self.binding(**options)
        self.git('commit','--allow-empty','-qm','Different commit with same tree')
        with self.assertRaises(C.CIProfileError):self.binding()

    def test_actual_protected_policy_and_registry_blob_modes_and_aliases_are_mandatory(self):
        for relative in (C.POLICY,'.github/test-suites.json'):
            path=self.root/relative;raw=path.read_bytes()
            try:
                path.write_bytes(raw+b'\n')
                with self.assertRaises(C.CIProfileError):self.binding()
                path.write_bytes(raw);path.chmod(0o755)
                with self.assertRaises(C.CIProfileError):self.binding()
                path.chmod(0o644);path.unlink();alias=self.root/'outside';alias.write_bytes(raw);path.symlink_to(alias)
                with self.assertRaises(C.CIProfileError):self.binding()
            finally:
                path.unlink();path.write_bytes(raw);path.chmod(0o644)
        missing=next(p for n in C.SUITES for p in self.registry['suites'][n]['closure']['required']
                     if p not in {C.POLICY,C.PINNED_SOURCE,C.DATA_PATH,'.github/test-suites.json'})
        (self.root/missing).unlink();self.commit()
        with self.assertRaises(C.CIProfileError):self.binding()

    def test_diagnostic_binding_cannot_enter_production_even_when_actual_generation_matches(self):
        import runtime_ci
        self.policy['generation_digest']=C.generation(self.tree,self.registry)
        self.write(C.POLICY,json.dumps(self.policy).encode());self.commit()
        value=self.binding()
        self.assertEqual(value['actual_selection']['generation_digest'],self.policy['generation_digest'])
        with patch.object(runtime_ci.ci_profile,'validate_selection',side_effect=AssertionError('no production conversion')):
            with self.assertRaises(runtime_ci.CIEnvironmentError):
                runtime_ci.validate_environment({'selection':value},None,None,None,self.selection,
                    self.tree,self.tree,self.registry,root=self.root,read_blob=self.blob)

    def test_committed_registry_definitions_and_policy_schema_cannot_be_redefined(self):
        changed=deepcopy(self.registry)
        changed['suites'][C.SUITES[0]]['command'].append('--new-recipe')
        self.write('.github/test-suites.json',json.dumps(changed).encode());self.commit()
        with self.assertRaises(C.CIProfileError):self.binding(registry=changed)
        self.write('.github/test-suites.json',json.dumps(self.registry).encode())
        self.write(C.POLICY,json.dumps({**self.policy,'diagnostic_generation_override':'unreviewed'}).encode())
        self.commit()
        with self.assertRaises(C.CIProfileError):self.binding()


class ControllerGenerationTests(unittest.TestCase):
    """Real small immutable D repository; no runtime/kernel/tool measurement."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ci37-controller-manifest-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'trusted';self.root.mkdir()
        self.registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        policy=C.load_policy(C.ROOT)
        self.policy={key:value for key,value in policy.items() if key!='generation_digest'}
        self.policy.update(generation_kind=C.CONTROLLER_KIND,epoch=C.CONTROLLER_EPOCH,enabled=True)
        required=set(C.controller_paths())|{C.DATA_PATH}
        for name in C.SUITES:required.update(self.registry['suites'][name]['closure']['required'])
        self.blobs={}
        # This repository models protected main D, independently of the
        # platform branch executing the test. Child B/M profiles are applied
        # separately by SevenTargetProfileTests.trees below.
        shared_profile=(json.dumps({'schema':1,'platform':'shared','suites':[]},indent=2)+'\n').encode()
        self.assertEqual(self.blob(shared_profile)['sha'],'d63537504c20204de9d35d9be61da72a56df59c3')
        for name in sorted(required):
            source=C.ROOT/name
            if name==C.POLICY:raw=json.dumps(self.policy,sort_keys=True).encode()
            elif name=='tests/platform-profile.json':raw=shared_profile
            else:raw=source.read_bytes()
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            path.chmod(0o755 if source.stat().st_mode&0o111 else 0o644)
            self.blobs[self.blob(raw)['sha']]=raw
        self.git('init','--quiet')
        self.git('add','--all')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','Immutable protected fixture')
        self.source=self.git('rev-parse','HEAD').decode().strip()
        self.manifest=C.capture_controller_manifest(self.root,self.source)
        self.trusted=deepcopy(self.manifest['entries']);self.candidate=deepcopy(self.trusted)
        self.assertEqual(self.trusted['tests/platform-profile.json'],self.blob(shared_profile))
        self.selection={'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs','full_host':False,'include_platform':False}

    @staticmethod
    def blob(raw):
        return {'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}

    def git(self,*args):
        env={name:value for name,value in os.environ.items() if not name.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
        return subprocess.check_output(['/usr/bin/git','-c','core.hooksPath=/dev/null',*args],
            cwd=self.root,env=env,stderr=subprocess.PIPE,timeout=10)

    def binding(self,**kwargs):
        return C.validate_selection(self.selection,self.candidate,self.trusted,self.registry,
            root=self.root,read_blob=self.blobs.__getitem__,**kwargs)

    def test_real_immutable_D_manifest_allows_changed_CI_test_without_rebinding_candidate_to_D(self):
        self.candidate['tests/branch-cleanup-test.py']=self.blob(b'changed candidate test bytes\n')
        before=self.binding();after=self.binding(controller_manifest=self.manifest)
        self.assertEqual(before,after)
        self.assertEqual(before['generation_kind'],C.CONTROLLER_KIND)
        self.assertNotEqual(C.generation(self.candidate,self.registry),C.generation(self.trusted,self.registry))
        self.assertEqual(before['generation_digest'],C.controller_generation(self.trusted,self.registry))
        self.assertNotIn('source_commit',before);self.assertNotIn('source_tree',before)
        self.assertEqual(C._controller_tree_identity(self.trusted),self.git('rev-parse','HEAD^{tree}').decode().strip())
        with self.assertRaises(C.CIProfileError):self.binding(controller_manifest={**self.manifest,'source_tree':'f'*40})

    def test_dynamic_controller_generation_changes_after_legitimate_protected_source_update_without_policy_reseal(self):
        first=self.binding()
        path=self.root/'tools/test-evidence/runtime_ci.py';path.write_bytes(path.read_bytes()+b'\n# Reviewed controller update\n')
        self.git('add','--all');self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m','Reviewed protected controller update')
        self.source=self.git('rev-parse','HEAD').decode().strip()
        self.manifest=C.capture_controller_manifest(self.root,self.source)
        self.trusted=deepcopy(self.manifest['entries']);self.candidate=deepcopy(self.trusted)
        next_binding=self.binding()
        self.assertNotEqual(first['generation_digest'],next_binding['generation_digest'])
        self.assertEqual(first['policy_digest'],next_binding['policy_digest'])
        self.assertNotIn('generation_digest',self.policy)

    def test_capture_records_actual_commit_object_identity_before_constructing_manifest(self):
        import base64
        raw=self.git('cat-file','commit',self.source)
        actual=hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.assertEqual(actual,self.source)
        self.assertEqual(self.manifest['source_commit'],actual)
        self.assertEqual(base64.b64decode(self.manifest['commit_object']),raw)
        # Even a correctly sized object returned after the actual HEAD check
        # must independently hash to the admitted native immutable identity.
        changed=raw[:-1]+(b'X' if raw[-1:]!=b'X' else b'Y')
        original=C._controller_git
        def read(root,*args):
            return changed if args==('cat-file','commit',self.source) else original(root,*args)
        with patch.object(C,'_controller_git',side_effect=read), \
             patch.object(C,'_validate_controller_manifest',side_effect=AssertionError('mismatched object reached manifest')) as validate:
            with self.assertRaisesRegex(C.CIProfileError,'actual controller commit differs'):
                C.capture_controller_manifest(self.root,self.source)
            validate.assert_not_called()

    def test_manifest_rebound_actual_source_mode_alias_membership_and_tree_are_rejected(self):
        import base64
        for change in ('commit','commit-body','tree','lookup','missing','mode','alias','actual'):
            manifest=deepcopy(self.manifest)
            if change=='commit':manifest['source_commit']='f'*40
            elif change=='commit-body':manifest['commit_object']='not canonical base64'
            elif change=='tree':manifest['source_tree']='f'*40
            elif change=='lookup':manifest['entries']['tools/test-evidence/shadow.so']=self.blob(b'shadow')
            elif change=='missing':del manifest['entries']['tools/test-evidence/producer.py']
            elif change in ('mode','alias'):
                manifest['entries']['tools/test-evidence/producer.py']['mode']='100755' if change=='mode' else '120000'
            else:
                path=self.root/'tools/test-evidence/producer.py';original=path.read_bytes();path.write_bytes(b'changed actual bytes')
            if change not in ('commit','commit-body','tree','alias'):
                manifest['source_tree']=C._controller_tree_identity(manifest['entries'])
                body=base64.b64decode(manifest['commit_object'])
                body=b'tree '+manifest['source_tree'].encode()+b'\n'+body.split(b'\n',1)[1]
                manifest['commit_object']=base64.b64encode(body).decode('ascii')
                manifest['source_commit']=hashlib.sha1(b'commit '+str(len(body)).encode()+b'\0'+body).hexdigest()
            with self.subTest(change=change),self.assertRaises(C.CIProfileError):self.binding(controller_manifest=manifest)
            if change=='actual':path.write_bytes(original)
        with self.assertRaises(C.CIProfileError):C.capture_controller_manifest(self.root,'f'*40)

    def test_exact_selection_actual_registry_policy_platform_and_Android_pins_remain_mandatory(self):
        for name in ('.github/test-suites.json',C.POLICY,C.PINNED_SOURCE,'tests/platform-profile.json'):
            original=deepcopy(self.candidate[name]);self.candidate[name]=self.blob(b'changed declaration')
            with self.subTest(name=name),self.assertRaises(C.CIProfileError):self.binding()
            self.candidate[name]=original
        self.candidate['unknown/alias']={'mode':'120000','type':'blob','sha':'f'*40}
        with self.assertRaises(C.CIProfileError):self.binding()
        del self.candidate['unknown/alias']
        for field,value in (('full_host',True),('include_platform',True),('suites',list(C.SUITES)[1:])):
            old=self.selection[field];self.selection[field]=value
            with self.subTest(field=field),self.assertRaises(C.CIProfileError):self.binding()
            self.selection[field]=old
        with self.assertRaises(C.CIProfileError):self.binding(target='apple-ios')

    def test_namespace_epoch_and_legacy_whole_tree_semantics_are_not_interchangeable(self):
        for changed in ({**self.policy,'generation_kind':'other'}, {**self.policy,'epoch':'old-epoch'},
                        {**self.policy,'generation_digest':'sha256:'+'a'*64}):
            with self.assertRaises(C.CIProfileError):C._validate_policy(changed)
        legacy={key:value for key,value in self.policy.items() if key!='generation_kind'}
        legacy['generation_digest']=C.generation(self.trusted,self.registry)
        self.assertEqual(C._validate_policy(legacy),legacy)
        self.candidate['tests/branch-cleanup-test.py']=self.blob(b'candidate differs')
        with self.assertRaises(C.CIProfileError):self.binding(policy=legacy)

    def test_projection_requires_native_expectedD_then_authenticates_actual_readonly_controller_copy(self):
        import sandbox_shared as S
        projection=Path(self.temp.name)/'projection';projection.mkdir()
        names=C.controller_paths()
        with patch.object(S,'ROOT',self.root):
            with self.assertRaises(S.host.Unavailable):S.project_policy(projection,names)
            with self.assertRaises(C.CIProfileError):S.project_policy(projection,names,trusted_source='f'*40)
            result=S.project_policy(projection,names,trusted_source=self.source)
        self.assertIn(C.CONTROLLER_MANIFEST,result)
        manifest_path=projection/C.CONTROLLER_MANIFEST
        self.assertEqual(manifest_path.stat().st_mode&0o777,0o444)
        self.assertEqual(json.loads(manifest_path.read_bytes())['entries'],self.trusted)
        self.assertEqual(C._validate_controller_manifest(self.manifest,projection),self.trusted)
        # Real mode/content projection; UID assertion is covered with an
        # explicit root-owner fixture when this unit process is unprivileged.
        if os.geteuid()==0:
            self.assertEqual(C.load_controller_projection(projection),self.manifest)
        manifest_path.chmod(0o644)
        with self.assertRaises(C.CIProfileError):C.load_controller_projection(projection)

    def test_capture_validates_controller_manifest_before_any_runtime_measurement(self):
        import runtime_ci as R
        self.candidate['tests/branch-cleanup-test.py']=self.blob(b'candidate test changed')
        with patch.object(R,'_measure_ci_environment',side_effect=lambda binding,**kw:{'selection':binding}) as measure:
            result=R.capture_ci_environment(self.selection,self.candidate,self.trusted,self.registry,
                root=self.root,read_blob=self.blobs.__getitem__,controller_manifest=self.manifest)
            self.assertEqual(result['selection'],self.binding());self.assertEqual(measure.call_count,1)
            with self.assertRaises(R.CIEnvironmentError):R.capture_ci_environment(
                self.selection,self.candidate,self.trusted,self.registry,root=self.root,read_blob=self.blobs.__getitem__)
            self.assertEqual(measure.call_count,1)
            with self.assertRaises(R.CIEnvironmentError):R.capture_ci_environment(
                self.selection,self.candidate,self.candidate,self.registry,root=self.root,
                read_blob=self.blobs.__getitem__,controller_manifest={**self.manifest,'source_tree':'f'*40})
            self.assertEqual(measure.call_count,1)

    def test_probe_uses_sealed_D_manifest_not_the_candidate_as_its_trusted_tree(self):
        import runtime_ci as R
        import sandbox
        spec=importlib.util.spec_from_file_location('controller_generation_probe',C.ROOT/'tools/test-evidence/sandbox_probe.py')
        probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        self.candidate['tests/branch-cleanup-test.py']=self.blob(b'changed candidate implementation')
        binding={'source':'e'*40,'runtime_profile':C.PROFILE,'selection':self.selection,'profile_binding':self.binding()}
        real_path=Path
        def path(name):
            value=str(name)
            if value=='/overte-policy':return self.root
            if value.startswith('/overte-policy/'):return self.root/value.removeprefix('/overte-policy/')
            return real_path(value)
        with patch.object(probe,'Path',side_effect=path),patch.object(inputs,'full_tree',return_value=self.candidate), \
             patch.object(C,'load_controller_projection',return_value=self.manifest), \
             patch.object(sandbox,'_git',side_effect=lambda root,*args,**kwargs:self.blobs[args[2]]), \
             patch.object(R,'_measure_ci_environment',side_effect=lambda binding,**kw:{'selection':binding}), \
             patch.object(R,'capture_ci_environment',wraps=R.capture_ci_environment) as capture:
            self.assertEqual(probe.shared_environment(binding)['selection'],binding['profile_binding'])
            self.assertEqual(capture.call_args.args[1],self.candidate)
            self.assertEqual(capture.call_args.args[2],self.trusted)
            self.assertNotEqual(capture.call_args.args[1],capture.call_args.args[2])
            self.assertEqual(capture.call_args.kwargs['controller_manifest'],self.manifest)
            with self.assertRaises(R.CIEnvironmentError):
                probe.shared_environment({**binding,'profile_binding':{'downgraded':'legacy'}})

    def test_manual_namespace_stays_production_inadmissible_in_controller_mode(self):
        import runtime_ci as R
        diagnostic=C.diagnostic_selection(self.selection,self.trusted,self.trusted,self.registry,
            root=self.root,source=self.source,source_root=self.root,read_blob=self.blobs.__getitem__,
            controller_manifest=self.manifest)
        self.assertEqual(diagnostic['kind'],C.DIAGNOSTIC_KIND)
        self.assertEqual(diagnostic['actual_selection']['generation_kind'],C.CONTROLLER_KIND)
        with self.assertRaisesRegex(R.CIEnvironmentError,'manual diagnostic'):
            R.validate_environment({'selection':diagnostic},None,None,None,
                self.selection,self.trusted,self.trusted,self.registry,root=self.root)


class RetainedOriginalDefaultTests(unittest.TestCase):
    """Actual immutable B != D + complete projected source, no E/tool probe."""
    def setUp(self):
        import sandbox
        import source_admission as S
        self.sandbox,self.S=sandbox,S
        fixture=ControllerGenerationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.root=fixture.root;self.registry=fixture.registry
        self.base=fixture.source;self.before=deepcopy(fixture.trusted)
        (self.root/'noncontroller-original-D.txt').write_bytes(b'actual full original D manifest member\n')
        fixture.git('add','--all')
        fixture.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','Distinct original protected default D')
        self.default=fixture.git('rev-parse','HEAD').decode().strip()
        self.manifest=C.capture_controller_manifest(self.root,self.default)
        self.tree=self.manifest['source_tree']
        self.binding={'repository':'noah-l-frank/overte','repository_id':1319052603,'pull_request':17,
            'head_repository_id':1319052603,'base_ref':'apple-ios','base_sha':self.base,
            'head_ref':'fixture-topic','head_sha':'2'*40,'merge_sha':'3'*40,'merge_tree':self.tree,
            'merge_parents':[self.base,'2'*40]}
        self.git_context={'profile':'streamed-candidate-source-v1','commits':{
            '3'*40:{'commit':'3'*40,'tree':self.tree,'parents':[self.base,'2'*40]},
            self.base:{'commit':self.base,'tree':C._controller_tree_identity(self.before),'parents':[]},
            '2'*40:{'commit':'2'*40,'tree':'4'*40,'parents':[]}},'shallow':[]}
        spec=importlib.util.spec_from_file_location('retained_source_protocol_fixture',C.ROOT/'tools/test-evidence/producer-test.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.environment=module.isolated_codec_environment()
        self.selection={'suites':list(self.registry['suites']),'full_host':True,'include_platform':True,'reason':'fixture-full'}
        self.admission={**S.compatibility(self.before,self.manifest['entries'],'apple-ios',
            read_actual=lambda name:S.actual_bytes(self.root,name),actual_imports=S.actual_import_inventory(self.root)),
            'base':self.base,'default':self.default}
        self.context={'source':'3'*40,'run_id':100,'run_attempt':1,'profile':'manual-shared-host-compatibility-v1',
            'snapshot':'sha256:'+'1'*64,'git_context':self.git_context,'runtime_profile':'ubuntu24-host-qt5-qt6-v1',
            'selection':self.selection,'profile_binding':None,'registry':C._digest(self.registry),
            'prepared':self.environment['prepared']['roots'],
            'outside_namespaces':{name:index+100 for index,name in enumerate(('user','mnt','pid','net','ipc','uts'))}}
        self.projection=self.root.parent/'projection';self.projection.mkdir(mode=0o755)
        for name in C.controller_paths():
            sandbox._write_source(self.projection,name,(self.root/name).read_bytes(),executable=name=='tests/run-project-tests.py')
        sandbox._write_source(self.projection,C.CONTROLLER_MANIFEST,inputs._canonical(self.manifest))
        self.context['projection']=C._digest(sandbox._files(self.projection))
        sandbox._write_source(self.projection,'context.json',inputs._canonical({'shared_host':self.context}))
        self.inventory=sandbox._files(self.projection)
        self.envelope=C.capture_retained_source(self.manifest,self.inventory,self.context,self.admission,root=self.root)

    def validate(self,value=None,base=None,default=None):
        return C.validate_retained_source(self.envelope if value is None else value,
            self.before if base is None else base,self.manifest['entries'] if default is None else default,
            native_binding=self.binding,run_id=100,registry=self.registry,selection=self.selection,
            environment=self.environment,root=self.root)

    def test_original_distinct_D_and_complete_manifest_projection_are_retained_without_E_changes(self):
        original=deepcopy(self.environment)
        self.assertNotEqual(self.base,self.default)
        self.assertEqual(self.validate(),self.envelope)
        self.assertEqual(self.envelope['default_commit'],self.default)
        self.assertEqual(self.envelope['default_tree'],self.tree)
        self.assertEqual(self.envelope['manifest_digest'],C._digest(self.manifest))
        self.assertEqual(self.envelope['projection_digest'],C._digest(self.inventory))
        self.assertIn('context.json',self.inventory)
        self.assertIn(C.CONTROLLER_MANIFEST,self.inventory)
        self.assertEqual(self.environment,original)
        self.assertLess(len(inputs._canonical(self.envelope)),200_000)

    def test_whole_manifest_noncontroller_content_and_native_source_cannot_be_substituted(self):
        changed=deepcopy(self.manifest['entries'])
        changed['noncontroller-original-D.txt']['sha']='e'*40
        with self.assertRaises(C.CIProfileError):self.validate(default=changed)
        for field,value in (('default_commit',self.base),('default_tree','f'*40),
                ('manifest_digest','sha256:'+'0'*64),('commit_object','!invalid-base64!')):
            envelope=deepcopy(self.envelope);envelope[field]=value
            with self.subTest(field=field),self.assertRaises(C.CIProfileError):self.validate(envelope)
        for field,value in (('source','9'*40),('run_id',101),('run_attempt',2),('registry','sha256:'+'0'*64)):
            envelope=deepcopy(self.envelope);envelope['binding'][field]=value
            with self.subTest(binding=field),self.assertRaises(C.CIProfileError):self.validate(envelope)

    def test_complete_context_modes_membership_and_projection_digest_are_not_excluded(self):
        for mutation in ('projection','pre-context','outside-namespace','extra-context','source-mode','extra-projected-file'):
            envelope=deepcopy(self.envelope)
            if mutation=='projection':envelope['projection_digest']='sha256:'+'0'*64
            elif mutation=='pre-context':envelope['binding']['projection']='sha256:'+'0'*64
            elif mutation=='outside-namespace':envelope['binding']['outside_namespaces']['mnt']+=1
            elif mutation=='extra-context':envelope['binding']['new_unbound_input']=True
            else:
                inventory=deepcopy(self.inventory)
                if mutation=='source-mode':inventory['tools/test-evidence/execution.py']['mode']=0o555
                else:inventory['unreviewed.txt']={'mode':0o444,'size':0,'sha256':hashlib.sha256(b'').hexdigest()}
                with self.subTest(mutation=mutation),self.assertRaises(C.CIProfileError):
                    C.capture_retained_source(self.manifest,inventory,self.context,self.admission,root=self.root)
                continue
            with self.subTest(mutation=mutation),self.assertRaises(C.CIProfileError):self.validate(envelope)

    def test_original_base_current_controller_import_and_enrolled_profile_remain_required(self):
        for name in ('tools/test-evidence/execution.py','tests/platform-profile.json'):
            before=deepcopy(self.before);before[name]['sha']='e'*40
            with self.subTest(name=name),self.assertRaises(ValueError):self.validate(base=before)
        before=deepcopy(self.before);before['tools/test-evidence/unreviewed.py']=self.fixture.blob(b'# new import\n')
        with self.assertRaises(ValueError):self.validate(base=before)
        path=self.root/'tools/test-evidence/execution.py';raw=path.read_bytes()
        path.write_bytes(raw+b'\n# changed after source capture\n')
        try:
            with self.assertRaises(C.CIProfileError):self.validate()
        finally:path.write_bytes(raw)

    def test_actual_immutable_API_reader_uses_original_D_not_consumer_default(self):
        import producer_api as A
        import producer_workflow as W
        outer=self
        records={self.default:(self.tree,[]),**{oid:(entry['tree'],entry['parents']) for oid,entry in self.git_context['commits'].items()}}
        maps={self.tree:self.manifest['entries'],C._controller_tree_identity(self.before):self.before}
        calls=[]
        class Api:
            def json(self,endpoint):
                calls.append(endpoint)
                prefix=A.PREFIX+'/git/commits/'
                if not endpoint.startswith(prefix):raise AssertionError('no currentdefault lookup or live request')
                oid=endpoint[len(prefix):];tree,parents=records[oid]
                return {'sha':oid,'tree':{'sha':tree},'parents':[{'sha':item} for item in parents]}
            def immutable_tree(self,oid):
                calls.append('immutable:'+oid)
                return {'sha':oid,'truncated':False,'tree':[{'path':name,**entry} for name,entry in maps[oid].items()]}
        receipt={'schema':4,'protected_source':self.envelope,'environment':self.environment}
        adapter=A.Adapter(Api())
        actual=W.retained_receipt_source(receipt,self.binding,adapter,self.registry,self.selection,100,root=self.root)
        self.assertEqual(actual,self.envelope)
        self.assertTrue(any(self.default in name for name in calls))
        self.assertFalse(any('heads/main' in name or 'branches/main' in name for name in calls))
        with self.assertRaises(ValueError):W.retained_receipt_source({'schema':3},self.binding,adapter,self.registry,self.selection,100,root=self.root)

    def test_only_exact_unenrolled_future_generation_can_emit_new_child_receipt(self):
        import producer_workflow as W
        from types import SimpleNamespace
        for generation, target, expected in (('protected-producer-seven-target-ci-v1','main',3),
                (C.RETAINED_SOURCE_GENERATION,'apple-ios',4),(C.RETAINED_SOURCE_GENERATION,'main',4)):
            policy=SimpleNamespace(package_policy=lambda:SimpleNamespace(validate_tree_wiring=lambda tree:generation))
            self.assertEqual(W.execution_schema(policy,{},target),expected)
        for generation in ('protected-producer-seven-target-ci-v1','unknown'):
            policy=SimpleNamespace(package_policy=lambda:SimpleNamespace(validate_tree_wiring=lambda tree:generation))
            with self.subTest(generation=generation),self.assertRaises(W.PreExecutionUnavailable):W.execution_schema(policy,{},'apple-ios')



class SevenTargetProfileTests(unittest.TestCase):
    """Real compact immutable D; only source/data validation, no runtime query."""
    def setUp(self):
        import source_admission
        self.S=source_admission
        fixture=ControllerGenerationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.root=fixture.root;self.registry=fixture.registry;self.blobs=fixture.blobs
        self.policy={**fixture.policy,'generation_kind':C.SEVEN_CONTROLLER_KIND,'epoch':C.SEVEN_CONTROLLER_EPOCH}
        for name in inputs.AFFECTED_AUTHORITY:
            path=self.root/name
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((C.ROOT/name).read_bytes())
                path.chmod(0o755 if name=='tests/run-project-tests.py' else 0o644)
        (self.root/C.POLICY).write_bytes(json.dumps(self.policy,sort_keys=True).encode())
        tree=inputs.full_tree(self.root,'HEAD')
        self.assertEqual(tree[self.S.PROFILE],self.S.ordinary(self.S.TARGET_PROFILES['main']))
        for name in inputs.AFFECTED_AUTHORITY|{C.POLICY}:
            tree[name]=fixture.blob((self.root/name).read_bytes())
            if name=='tests/run-project-tests.py':tree[name]['mode']='100755'
        graph=json.loads((C.ROOT/inputs.AFFECTED_POLICY).read_bytes());graph['schema']=2
        native=graph['suites']['device-control-plane-full']
        native['native_independent_paths']=sorted(set(native['native_independent_paths'])&set(tree)|{inputs.AFFECTED_POLICY})
        native['reviewed_reader_digest']=inputs.device_reader_digest(tree,native['native_independent_paths'])
        graph['lookup_digest']=inputs.affected_lookup_digest(tree)
        graph['targets']={}
        for target,sha in self.S.TARGET_PROFILES.items():
            current={**tree,self.S.PROFILE:self.S.ordinary(sha)}
            graph['targets'][target]={'profile':self.S.ordinary(sha),
                'lookup_digest':inputs.affected_lookup_digest(current),
                'reader_digest':inputs.device_reader_digest(current,native['native_independent_paths'])}
        self.raw=(json.dumps(graph,indent=2)+'\n').encode()
        (self.root/inputs.AFFECTED_POLICY).write_bytes(self.raw)
        fixture.git('add','--all');fixture.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m','Finite seven-target protected fixture')
        self.source=fixture.git('rev-parse','HEAD').decode().strip()
        self.manifest=C.capture_controller_manifest(self.root,self.source)
        self.trusted=self.manifest['entries']
        for name in (C.POLICY,inputs.AFFECTED_POLICY):
            raw=(self.root/name).read_bytes();self.blobs[fixture.blob(raw)['sha']]=raw
        self.selection=deepcopy(fixture.selection)

    def trees(self,target='main'):
        base=deepcopy(self.trusted);base[self.S.PROFILE]=self.S.ordinary(self.S.TARGET_PROFILES[target])
        candidate=deepcopy(base);candidate['tests/branch-cleanup-test.py']=self.f.blob(b'changed candidate test\n')
        return base,candidate

    def admit(self,target='main',*,base=None,candidate=None,selection=None,trusted=None,**kw):
        before,current=self.trees(target if target in self.S.TARGET_PROFILES else 'main')
        return C.validate_selection(self.selection if selection is None else selection,
            current if candidate is None else candidate,self.trusted if trusted is None else trusted,self.registry,
            root=self.root,target=target,base_tree=before if base is None else base,
            read_blob=self.blobs.__getitem__,controller_manifest=self.manifest,**kw)

    def subset(self,target='main'):
        base,candidate=self.trees(target)
        plan=inputs.plan_affected(self.registry,self.raw,base,candidate,self.trusted,target=target)
        selected={'suites':[name for name in C.SUITES if name in plan['required']],
            'reason':'protected-ci-dependencies','full_host':False,'include_platform':False,'affected':plan}
        self.assertTrue(set(selected['suites'])<set(C.SUITES));self.assertTrue(selected['suites'])
        return base,candidate,selected

    def test_all_seven_exact_profiles_share_one_actualD_environment_class(self):
        bindings=[]
        for target in self.S.TARGET_PROFILES:
            with self.subTest(target=target):bindings.append(self.admit(target))
        self.assertTrue(all(value==bindings[0] for value in bindings))
        self.assertEqual(bindings[0]['suites'],list(C.SUITES))
        self.assertEqual(bindings[0]['generation_kind'],C.SEVEN_CONTROLLER_KIND)
        self.assertNotIn('selection_target',bindings[0])

    def test_all_seven_graph_proved_subsets_keep_fixed37_runtime_definition(self):
        for target in self.S.TARGET_PROFILES:
            base,candidate,selected=self.subset(target)
            with self.subTest(target=target):
                self.assertEqual(self.admit(target,base=base,candidate=candidate,selection=selected),self.admit(target))
                self.assertNotIn('device-control-plane-full',selected['suites'])

    def test_wrong_profile_unknown_target_nonordinary_and_historical_source_refuse(self):
        for target in self.S.TARGET_PROFILES:
            for side in ('base','candidate'):
                for change in ('profile','mode','source','import-shadow','alias'):
                    base,candidate=self.trees(target);tree=base if side=='base' else candidate
                    if change=='profile':tree[self.S.PROFILE]=self.f.blob(b'unknown platform')
                    elif change=='mode':tree[self.S.PROFILE]['mode']='100755'
                    elif change=='source':tree['tools/test-evidence/runtime_ci.py']=self.f.blob(b'foreign controller')
                    elif change=='import-shadow':tree['tools/test-evidence/shadow.py']=self.f.blob(b'unknown import')
                    else:tree['unrelated-alias']={'mode':'120000','type':'blob','sha':'f'*40}
                    # Candidate code may legitimately change; original B and
                    # negative import membership must remain protected.
                    if side=='candidate' and change in ('source','import-shadow'):continue
                    with self.subTest(target=target,side=side,change=change),self.assertRaises(ValueError):
                        self.admit(target,base=base,candidate=candidate)
        with self.assertRaises(ValueError):self.admit('unknown')

    def test_subset_names_plan_authority_membership_and_setup_cannot_be_claimed(self):
        base,candidate,selected=self.subset()
        for change in ('drop','extra','reverse','empty','full','platform','plan','graph','native-shadow'):
            value=deepcopy(selected);current=deepcopy(candidate)
            if change=='drop':value['suites']=value['suites'][1:]
            elif change=='extra':value['suites'].append('device-control-plane-full')
            elif change=='reverse':value['suites'].reverse()
            elif change=='empty':value['suites']=[]
            elif change=='full':value['full_host']=True
            elif change=='platform':value['include_platform']=True
            elif change=='plan':value['affected']['required']=value['suites']
            elif change=='graph':current[inputs.AFFECTED_POLICY]=self.f.blob(b'unprotected graph')
            else:current['cassert']=self.f.blob(b'historical native shadow')
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.admit(base=base,candidate=current,selection=value)

    def test_base_pinned_data_and_policy_cannot_be_substituted(self):
        for name in (C.POLICY,C.PINNED_SOURCE,C.DATA_PATH,'.github/test-suites.json'):
            base,candidate=self.trees();base[name]=self.f.blob(b'untrusted original data')
            with self.subTest(name=name),self.assertRaises((ValueError,KeyError)):
                self.admit(base=base,candidate=candidate)

    def test_probe_derives_B_from_actual_ordered_merge_parents_before_capture(self):
        import runtime_ci as R
        import sandbox
        spec=importlib.util.spec_from_file_location('seven_target_probe',C.ROOT/'tools/test-evidence/sandbox_probe.py')
        probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        base,candidate,selection=self.subset('android-phone');binding=self.admit('android-phone',selection=selection)
        context={'source':'e'*40,'runtime_profile':C.PROFILE,'selection':selection,'profile_binding':binding,
            'selection_target':'android-phone','selection_base':'a'*40}
        real_path=Path
        def path(name):
            value=str(name)
            if value=='/overte-policy':return self.root
            if value.startswith('/overte-policy/'):return self.root/value.removeprefix('/overte-policy/')
            return real_path(value)
        with patch.object(probe,'Path',side_effect=path), \
             patch.object(inputs,'full_tree',side_effect=lambda root,oid:candidate if oid=='e'*40 else base), \
             patch.object(C,'load_controller_projection',return_value=self.manifest), \
             patch.object(sandbox,'_raw_commit_identity',return_value={'parents':['a'*40,'b'*40]}) as identity, \
             patch.object(sandbox,'_git',side_effect=lambda root,*args,**kw:self.blobs[args[2]]), \
             patch.object(R,'_measure_ci_environment',side_effect=lambda value,**kw:{'selection':value}) as measure:
            self.assertEqual(probe.shared_environment(context),{'selection':binding})
            identity.assert_called_once_with(Path('/work'),'e'*40);measure.assert_called_once()
            measure.reset_mock()
            with self.assertRaises(ValueError):probe.shared_environment({**context,'selection_base':'c'*40})
            measure.assert_not_called()

    def test_graph_schema2_closed_targets_and_role_specific_readers_are_mandatory(self):
        original=json.loads(self.raw)
        for change in ('missing-target','unknown-target','unknown-field','profile','lookup','reader','native-row'):
            value=deepcopy(original)
            if change=='missing-target':del value['targets']['apple-ios']
            elif change=='unknown-target':value['targets']['other']=value['targets']['main']
            elif change=='unknown-field':value['targets']['main']['force']=True
            elif change=='profile':value['targets']['android-phone']['profile']=value['targets']['main']['profile']
            elif change=='lookup':value['targets']['main']['lookup_digest']='sha256:'+'f'*64
            elif change=='reader':value['targets']['main']['reader_digest']='sha256:'+'f'*64
            else:value['suites']['device-control-plane-full']=[]
            with self.subTest(change=change),self.assertRaises(inputs.InputError):inputs._validate_dependencies(value,self.registry)
        base,candidate=self.trees('android-phone')
        base['cassert']=self.f.blob(b'historical native include shadow')
        candidate['cassert']=base['cassert']
        plan=inputs.plan_affected(self.registry,self.raw,base,candidate,self.trusted,target='android-phone')
        self.assertIn('device-control-plane-full',plan['required'])
        # A child tree cannot stand in for actual shared-profile D, even when
        # the same Python object is supplied in two argument roles.
        with self.assertRaises(inputs.InputError):
            inputs.plan_affected(self.registry,self.raw,base,candidate,base,target='android-phone')

    def test_real_router_and_producer_admit_seven_qt_free_subsets_only_under_enrollment(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        import producer_workflow as W
        router=W._host_policy()
        default_digest=router.program_digest(self.trusted,self.root)
        target_digests={target:router.program_digest(self.trees(target)[0],self.root) for target in self.S.TARGET_PROFILES}
        package=SimpleNamespace(validate_tree_wiring=lambda tree:C.RETAINED_SOURCE_GENERATION)
        with ExitStack() as stack:
            for name,value in (('ROOT',self.root),('REVIEWED_PROGRAMS',default_digest),
                               ('REVIEWED_CHILD_PROGRAMS',target_digests)):
                stack.enter_context(patch.object(router,name,value))
            stack.enter_context(patch.object(router,'package_policy',return_value=package))
            for target in self.S.TARGET_PROFILES:
                base,candidate=self.trees(target)
                with self.subTest(target=target):
                    profile=W.selection_profile(router,self.registry,candidate,base,self.trusted,
                        root=self.root,target=target,read_blob=self.blobs.__getitem__)
                    self.assertEqual(profile['profile'],C.PROFILE)
                    self.assertEqual(profile['selection']['reason'],'protected-ci-dependencies')
                    self.assertFalse(profile['selection']['full_host'])
                    self.assertFalse(profile['selection']['include_platform'])
                    self.assertEqual(profile['binding']['suites'],list(C.SUITES))
            base,candidate=self.trees('apple-ios')
            with patch.object(package,'validate_tree_wiring',return_value='protected-producer-seven-target-ci-v1'), \
                 self.assertRaises(W.PreExecutionUnavailable):
                W.selection_profile(router,self.registry,candidate,base,self.trusted,
                    root=self.root,target='apple-ios',read_blob=self.blobs.__getitem__)
            # Legacy namespace preserves the prior early return, even with a
            # graph present: no new graph parse/hash/setup on old CI37 routes.
            with patch.object(router,'_qt_free_dependency_namespace',return_value=False), \
                 patch.object(inputs,'load_dependencies',side_effect=AssertionError('legacy graph must not load')):
                value=router.select(candidate,['tests/branch-cleanup-test.py'],True,base_tree=base,
                    trusted_tree=self.trusted,candidate_root=self.root,trusted_root=self.root,target='apple-ios')
            self.assertEqual(value['suites'],list(C.SUITES));self.assertFalse(value['full_host'])

    def test_full_child_subset_preserves_required_android_platform_owner(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        import producer_workflow as W
        router=W._host_policy()
        package=SimpleNamespace(validate_tree_wiring=lambda tree:C.RETAINED_SOURCE_GENERATION)
        with ExitStack() as stack:
            stack.enter_context(patch.object(router,'ROOT',self.root))
            stack.enter_context(patch.object(router,'package_policy',return_value=package))
            for target in self.S.TARGET_PROFILES:
                base,candidate=self.trees(target)
                candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=self.f.blob(b'changed control reader')
                with self.subTest(target=target):
                    profile=W.selection_profile(router,self.registry,candidate,base,self.trusted,
                        root=self.root,target=target,read_blob=self.blobs.__getitem__)
                    self.assertEqual(profile['profile'],W.FULL_PROFILE)
                    self.assertTrue(profile['selection']['full_host'])
                    self.assertEqual(profile['selection']['reason'],'protected-affected-dependencies')
                    self.assertEqual(profile['selection']['include_platform'],target.startswith('android-'))
                    self.assertTrue(set(profile['suites'])<set(self.registry['suites']))
                    self.assertIsNone(profile['binding'])

    def test_full_runtime_projection_also_retains_manifest_with_new_policy_kind(self):
        import sandbox
        import sandbox_shared as shared
        names=C.controller_paths()
        destination=self.root.parent/'full-policy';destination.mkdir()
        with patch.object(shared,'ROOT',self.root):
            projected=shared.project_policy(destination,names,trusted_source=self.source)
        self.assertIn(C.CONTROLLER_MANIFEST,projected)
        self.assertEqual(json.loads((destination/C.CONTROLLER_MANIFEST).read_bytes()),self.manifest)
        self.assertEqual(projected,sandbox._files(destination))
        other=self.root.parent/'missing-source';other.mkdir()
        with patch.object(shared,'ROOT',self.root),self.assertRaises(ValueError):
            shared.project_policy(other,names)

    def test_source4_new_binding_is_closed_and_matches_native_original_B(self):
        import sandbox
        base,candidate=self.trees('apple-ios')
        binding=self.admit('apple-ios')
        git_context={'profile':'streamed-candidate-source-v1','commits':{
            '3'*40:{'commit':'3'*40,'tree':C._controller_tree_identity(candidate),'parents':[self.source,'2'*40]},
            self.source:{'commit':self.source,'tree':self.manifest['source_tree'],'parents':[]},
            '2'*40:{'commit':'2'*40,'tree':'4'*40,'parents':[]}},'shallow':[]}
        selection=deepcopy(self.selection)
        context={'source':'3'*40,'run_id':100,'run_attempt':1,'profile':'manual-shared-host-compatibility-v1',
            'snapshot':'sha256:'+'1'*64,'git_context':git_context,'runtime_profile':C.PROFILE,
            'selection':selection,'profile_binding':binding,'registry':C._digest(self.registry),
            'prepared':{name:'sha256:'+'a'*64 for name in (inputs.ISOLATED_VENV,
                '/opt/hostedtoolcache/Python/3.12.15/x64','/opt/hostedtoolcache/node/22.23.3/x64')},
            'outside_namespaces':{name:index+100 for index,name in enumerate(('user','mnt','pid','net','ipc','uts'))},
            'selection_target':'apple-ios','selection_base':self.source}
        projection=self.root.parent/'retained-seven';projection.mkdir()
        for name in C.controller_paths():sandbox._write_source(projection,name,(self.root/name).read_bytes(),
            executable=name=='tests/run-project-tests.py')
        sandbox._write_source(projection,C.CONTROLLER_MANIFEST,inputs._canonical(self.manifest))
        context['projection']=C._digest(sandbox._files(projection))
        sandbox._write_source(projection,'context.json',inputs._canonical({'shared_host':context}))
        admission={**self.S.compatibility(base,self.trusted,'apple-ios',
            read_actual=lambda name:self.S.actual_bytes(self.root,name),actual_imports=self.S.actual_import_inventory(self.root)),
            'base':self.source,'default':self.source}
        envelope=C.capture_retained_source(self.manifest,sandbox._files(projection),context,admission,root=self.root)
        native={'base_ref':'apple-ios','base_sha':self.source,'merge_sha':'3'*40,
            'merge_tree':C._controller_tree_identity(candidate)}
        environment={'profile':C.PROFILE,'selection':binding,'python':{'version':'3.12.15'},
            'tools':{'node':{'version':'v22.23.3'}}}
        def validate(value=envelope,native_binding=native):
            return C.validate_retained_source(value,base,self.trusted,native_binding=native_binding,
                run_id=100,registry=self.registry,selection=selection,environment=environment,root=self.root)
        self.assertEqual(validate(),envelope)
        for field,value in (('selection_base','a'*40),('selection_target','android-phone')):
            changed=deepcopy(envelope);changed['binding'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate(changed)
        for change in ('missing','unknown','legacy-extra'):
            changed=deepcopy(envelope)
            if change=='missing':del changed['binding']['selection_base']
            elif change=='unknown':changed['binding']['force']=True
            else:changed['binding']['profile_binding']['generation_kind']=C.CONTROLLER_KIND
            with self.subTest(change=change),self.assertRaises(ValueError):C.retained_source_shape(changed)

    def test_child_current_owner_claims_keep_exact_prepared_selection_and_source4(self):
        from types import SimpleNamespace
        import producer_workflow as W
        import postmerge
        for target in self.S.TARGET_PROFILES:
            base,candidate,selection=self.subset(target)
            source={**self.S.compatibility(base,self.trusted,target,
                read_actual=lambda name:self.S.actual_bytes(self.root,name),actual_imports=self.S.actual_import_inventory(self.root)),
                'base':'a'*40,'default':self.source}
            context={'binding':{'base_ref':target,'base_sha':'a'*40},'refs':{'default':self.source},
                'source_context':source,'profile':C.PROFILE,'profile_binding':self.admit(target,selection=selection),
                'selected':selection,'registry':self.registry,
                'plan':{'owners':{'shared-host':{'suites':selection['suites'],'include_platform':False}}},
                'policy':SimpleNamespace(producer=SimpleNamespace(required_execution_schema=4,
                    controller_digest=source['controller_digest']))}
            with self.subTest(target=target):self.assertTrue(W._owner_target_supported(context))
            if target=='main':continue  # Existing main behavior is unchanged.
            for change in ('schema','names','platform','kind','source'):
                changed=deepcopy(context)
                if change=='schema':changed['policy'].producer.required_execution_schema=3
                elif change=='names':changed['plan']['owners']['shared-host']['suites']=selection['suites'][1:]
                elif change=='platform':
                    changed['plan']['owners']['shared-host']['include_platform']=True
                    changed['source_context']['target_profile']=self.S.ordinary(self.S.TARGET_PROFILES['android-phone'])
                elif change=='kind':changed['profile_binding']['generation_kind']=C.CONTROLLER_KIND
                else:changed['source_context']['base']='f'*40
                with self.subTest(target=target,change=change):self.assertFalse(W._owner_target_supported(changed))
            full={'selection':{'suites':selection['affected']['required'],
                'reason':'protected-affected-dependencies','full_host':True,
                'include_platform':target.startswith('android-'),'affected':selection['affected']},
                'profile':W.FULL_PROFILE,'binding':None}
            self.assertTrue(postmerge._affected_receipt_selection(full,self.registry,target))
            bad=deepcopy(full);bad['selection']['affected']['target']='unknown'
            with self.assertRaises(ValueError):postmerge._affected_receipt_selection(bad,self.registry,target)

    def test_parent_runtime_context_reads_only_newkind_original_B(self):
        import producer_workflow as W
        with patch.object(inputs,'full_tree',side_effect=AssertionError('no unused old-kind base read')):
            self.assertEqual(W._ci_runtime_context({},Path('/candidate')), {})
            self.assertEqual(W._ci_runtime_context({'profile_binding':{'generation_kind':C.CONTROLLER_KIND}},Path('/candidate')), {})
        context={'profile_binding':{'generation_kind':C.SEVEN_CONTROLLER_KIND},
            'binding':{'base_ref':'android-phone','base_sha':'a'*40,'merge_sha':'b'*40}}
        base,_=self.trees('android-phone')
        with patch.object(inputs,'full_tree',return_value=base) as reader:
            self.assertEqual(W._ci_runtime_context(context,Path('/candidate')),
                {'target':'android-phone','base_tree':base})
        reader.assert_called_once_with(Path('/candidate'),'a'*40)

    def test_legacy_kind_and_version_epoch_remain_separate(self):
        for value in ({**self.policy,'epoch':C.CONTROLLER_EPOCH},{**self.policy,'generation_kind':[]},
                      {**self.policy,'generation_kind':'unknown'}):
            with self.assertRaises(ValueError):C._validate_policy(value)
        self.assertFalse(C.controller_policy({'generation_kind':[]}))
        self.assertFalse(C.controller_policy({'generation_kind':'unknown'}))
        self.assertTrue(C.controller_policy(self.policy))


class OriginalSourcePreselectionTests(unittest.TestCase):
    """Original dependency derivation is data, never current runtime authority."""
    def setUp(self):
        self.f=SevenTargetProfileTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_original_fixed_subject_subset_is_rederived_even_when_current_D_subject_changes(self):
        f=self.f
        base,candidate,selected=f.subset('apple-ios')
        self.assertNotIn('producer-proof',selected['suites'])
        old=deepcopy(f.trusted)
        path=f.root/'tools/test-evidence/producer-test.py'
        path.write_bytes(path.read_bytes()+b'\n# current protected unit-test body only\n')
        f.f.git('add','--all');f.f.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m','Current protected fixed-subject update')
        manifest=C.capture_controller_manifest(f.root,f.f.git('rev-parse','HEAD').decode().strip())
        current_plan=inputs.plan_affected(f.registry,f.raw,base,candidate,manifest['entries'],target='apple-ios')
        self.assertIn('producer-proof',current_plan['required'])
        kwargs=dict(target='apple-ios',base_tree=base,root=f.root,read_blob=f.blobs.__getitem__,controller_manifest=manifest)
        provisional=C.preliminary_reuse_selection(selected,candidate,old,f.registry,**kwargs)
        self.assertEqual(provisional['generation_digest'],C.controller_generation(manifest['entries'],f.registry))
        self.assertNotEqual(provisional['generation_digest'],C.controller_generation(old,f.registry))
        with self.assertRaises(ValueError):C.validate_selection(selected,candidate,old,f.registry,**kwargs)
        import runtime_ci
        with self.assertRaises(runtime_ci.CIEnvironmentError):runtime_ci.validate_original_environment(
            provisional,{},None,None,None,selected,candidate,old,f.registry,root=f.root)

    def test_preselection_cannot_ignore_import_mode_new_members_or_executable_controller_changes(self):
        f=self.f;base,candidate,selected=f.subset('apple-ios')
        for change in ('mode','member','controller'):
            tree=deepcopy(f.trusted)
            if change=='mode':tree['tools/test-evidence/producer-test.py']['mode']='100755'
            elif change=='member':tree['tools/test-evidence/new.py']=f.f.blob(b'new import')
            else:tree['tools/test-evidence/producer.py']=f.f.blob(b'changed production controller')
            with self.subTest(change=change),self.assertRaises(ValueError):C.reuse_controller_precheck(
                base,tree,'apple-ios',root=f.root)


if __name__ == "__main__":
    unittest.main()
