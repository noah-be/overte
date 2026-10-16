#!/usr/bin/env python3
"""Pure finite CI37 source preparation and fail-closed admission regressions."""

from copy import deepcopy
import hashlib
import json
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

    def test_shipping_profile_and_policy_remain_independently_disabled(self):
        self.assertFalse(C.SOURCE_READY)
        shipping = C.load_policy()
        self.assertFalse(shipping["enabled"])
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


if __name__ == "__main__":
    unittest.main()
