#!/usr/bin/env python3
"""Complete dormant Android ownership-transfer tests; no Android/product builds."""
from contextlib import redirect_stderr, redirect_stdout
from copy import copy, deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load("android_transfer_fixture", "tests/android-orchestration-test.py")
gate = prior.gate
handoff = load("android_transfer_subject", "tools/repository-checks/android_handoff.py")
shared, _ = gate.android()._shared()
OBSERVED = {"profile": "offline-owned-controller-fixture", "python": "isolated fixture"}


# Recreate each exact reviewed predecessor from the retained workflow plus its
# removed PR trigger. The original Git blob hash prevents any template drift.
REVIEWED_WORKFLOWS = {
    '.github/workflows/android-tests.yml': (
        '86f727401d2458814b6de6f3eaa1c7308058fa03',
        '  pull_request:\n'
        '    types: [opened, synchronize, reopened, labeled, unlabeled]\n'
        '    branches: [main, android-main, android-phone, android-vr, android-vr-pico]\n'
        '    paths:\n'
        '      - "android/**"\n'
        '      - "interface/**"\n'
        '      - "libraries/**"\n'
        '      - "scripts/**"\n'
        '      - ".github/workflows/android-tests.yml"\n'
        '      - "!**/*.md"\n'
    ),
    '.github/workflows/android-vr-tests.yml': (
        '174d58419f7d0e8ecd15e4a1ab101f72bb81877f',
        '  pull_request:\n'
        '    paths:\n'
        '      - "android/**"\n'
        '      - "interface/**"\n'
        '      - "libraries/**"\n'
        '      - "scripts/**"\n'
        '      - ".github/workflows/android-vr-tests.yml"\n'
        '      - "!**/*.md"\n'
    ),
}


def reviewed_workflow(target, current):
    expected, trigger = REVIEWED_WORKFLOWS[target]
    if "  pull_request:\n" in current or current.count("  push:\n") != 1:
        raise ValueError("retired Android workflow trigger changed")
    original = current.replace("  push:\n", trigger + "  push:\n", 1)
    if gate._blob(original.encode("utf-8"))["sha"] != expected:
        raise ValueError("reviewed original Android workflow identity changed")
    return original


class AndroidOwnerTransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture = prior.RequiredAndroidTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.candidate = self.fixture.candidate
        self.policy_root = self.fixture.policy_root
        self.directory = self.fixture.temporary

    def source(self):
        return gate._sources(self.candidate)

    def context(self):
        self.fixture.event["number"] = 17
        ref = "refs/pull/17/merge"
        return {"GITHUB_REPOSITORY": gate.REPOSITORY, "GITHUB_SHA": self.fixture.sha, "GITHUB_REF": ref,
                "GITHUB_WORKFLOW_REF": gate.REPOSITORY + "/.github/workflows/repository-checks.yml@" + ref,
                "GITHUB_WORKFLOW_SHA": self.fixture.sha}

    def owner(self):
        return handoff.platform_owner(self.candidate, self.fixture.event, self.fixture.sha,
                                      "pull_request", policy_root=self.policy_root)

    def controller(self, views, *, failure=None):
        owner = gate.android()
        current = owner.plan(self.candidate, "android-phone", views=views)
        self.fixture.fixture.active_items = current["executions"]
        observed = []
        def command(command, timeout, cancelled):
            options = [(name, item) for name, item in current["executions"].items()
                       if len(command) == len(item["command"]) and command[1] == item["command"][1]]
            if len(options) > 1:
                scaled = os.environ.get("OVERTE_JS_ENDURANCE_CYCLES") == "100"
                options = [(name, item) for name, item in options if name.endswith("-scaled") == scaled]
            self.assertEqual(len(options), 1)
            name, item = options[0]
            observed.append((name, timeout, {key: os.environ.get(key) for key in (
                "OVERTE_JS_ENDURANCE_CYCLES", "OVERTE_NATIVE_ENDURANCE_CYCLES")}))
            if name == failure:
                return 7, "Offline owner failure", ""
            return self.fixture.fixture.run_command(command, timeout, cancelled)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code, proof = owner.execute(self.candidate, "android-phone", views=views, capture=prior.ownership.runtime,
                                       run_command=command)
        return code, proof, observed

    def prepare_project(self, *, extra=False):
        self.fixture.workflow_files(browser=True)
        self.profile = json.loads((self.candidate / "tests/platform-profile.json").read_text())
        if extra:
            self.profile["suites"].append({"name": "additional-phone-contract", "interpreter": "python",
                                           "entrypoint": "android/phone/tests/additional-contract.py"})
            (self.candidate / "tests/platform-profile.json").write_text(json.dumps(self.profile))
        (self.candidate / ".gitignore").write_text("build/\n__pycache__/\n")
        for item in self.profile["suites"]:
            path = self.candidate / item["entrypoint"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if item["interpreter"] == "python":
                path.write_text('from pathlib import Path\np=Path("build/' + item["name"] + '")\np.parent.mkdir(exist_ok=True)\np.write_text("actual")\n')
            else:
                path.write_text('mkdir -p build\nprintf actual > build/' + item["name"] + '\n')
        self.registry = {"schema": 1, "control_inputs": ["tests/*.py"], "suites": {}}
        for name in ("first", "second"):
            relative = "tests/" + name + ".py"
            (self.candidate / relative).write_text('from pathlib import Path\np=Path("build/' + name + '")\np.parent.mkdir(exist_ok=True)\np.write_text("actual")\n')
            self.registry["suites"][name] = {"command": ["python", relative], "layer": "quick", "scope": "content",
                "environment": "host-qt5-qt6", "closure": {"kind": "repository", "inputs": [], "required": [relative]}}
        self.fixture.fixture.commit()
        self.fixture.merge()

    def selection(self, *, include_platform=True):
        return SimpleNamespace(candidate_selection=lambda *args: {
            "suites": list(self.registry["suites"]), "include_platform": include_platform,
            "full_host": include_platform, "reason": "offline-independent-selection"})

    def project(self, *, include_platform=True):
        with patch.object(handoff, "gate", return_value=gate), patch.object(gate, "ACTIVATION_READY", True), \
                patch.object(handoff, "host_selection", return_value=self.selection(include_platform=include_platform)), \
                patch.object(shared.inputs, "load_registry", return_value=self.registry), \
                patch.object(shared, "capture_execution_environment", return_value=OBSERVED,
                             side_effect=None if include_platform else AssertionError("partial selection must not probe Qt runtime")), \
                redirect_stdout(io.StringIO()):
            return handoff.project(self.candidate, self.fixture.event, self.fixture.sha, "pull_request",
                policy_root=self.policy_root, junit=self.directory / "project.xml", receipt_path=self.directory / "project.json",
                timeout=10, host_timeout=10)

    def test_label_and_manual_selection_preserve_critical_and_optional_variants(self):
        self.fixture.merge()
        self.assertEqual(self.fixture.plan()["views"], list(gate.android().VIEWS))
        self.fixture.event["pull_request"]["labels"] = [{"name": "android-long-diagnostics"}]
        selected = self.fixture.plan()
        self.assertEqual(selected["views"], list(gate.android().VIEWS) + list(gate.android().DIAGNOSTIC_VIEWS[:3]))
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=selected["views"])["executions"]), 45)
        self.fixture.event["pull_request"]["labels"] = []
        self.assertIn("mutation", self.fixture.plan()["views"])
        for value in (False, "false"):
            event = {"inputs": {"run_regression": value}}
            self.assertEqual(gate.event_views(event, "workflow_dispatch", True), list(gate.android().DEFAULT_VIEWS) + list(gate.android().DIAGNOSTIC_VIEWS[:3]))
        self.assertIn("regression", gate.event_views({}, "workflow_dispatch", True))
        for value in (0, 1, "yes", None, []):
            with self.assertRaises(ValueError): gate.event_views({"inputs": {"run_regression": value}}, "workflow_dispatch", True)
        self.assertEqual(gate.event_views({}, "workflow_dispatch", False), [])

    def test_selected_diagnostics_require_actual_prerequisites_and_keep_scales_timeouts(self):
        owner = gate.android()
        for view in owner.DIAGNOSTIC_VIEWS:
            with self.assertRaisesRegex(ValueError, "prerequisite"):
                owner.plan(self.candidate, "android-phone", views=[view])
        views = list(owner.SUPPORTED_VIEWS)
        code, proof, observed = self.controller(views)
        self.assertEqual(code, 0)
        self.assertEqual(len(observed), 46)
        self.assertEqual(len({name for name, _, _ in observed}), 46)
        names = [name for name, _, _ in observed]
        prerequisite_names = {item["execution"] for view in ("fast", "contracts", "coverage") for item in owner.load_policy()["views"][view].values()}
        diagnostic_names = {item["execution"] for view in owner.DIAGNOSTIC_VIEWS for item in owner.load_policy()["views"][view].values()}
        self.assertLess(max(names.index(name) for name in prerequisite_names), min(names.index(name) for name in diagnostic_names))
        rows = {name: (timeout, env) for name, timeout, env in observed}
        self.assertEqual(rows["javascript-lifecycle-endurance-scaled"], (120, {"OVERTE_JS_ENDURANCE_CYCLES": "100", "OVERTE_NATIVE_ENDURANCE_CYCLES": None}))
        self.assertEqual(rows["native-policy-endurance"], (120, {"OVERTE_JS_ENDURANCE_CYCLES": None, "OVERTE_NATIVE_ENDURANCE_CYCLES": "1000"}))
        self.assertEqual(rows["critical-policy-mutations-extended"][0], 480)
        self.assertEqual(rows["device-free-order-isolation-stability"][0], 1800)
        self.assertEqual(rows["phone-device-free-regression"][0], 480)
        self.assertEqual(owner.verify(self.candidate, "android-phone", proof, views=views, environment=prior.ownership.runtime())["verified"], "true")

    def test_failed_ordinary_prerequisite_blocks_every_selected_diagnostic_without_running_it(self):
        views = list(gate.android().SUPPORTED_VIEWS)
        code, proof, observed = self.controller(views, failure="phone-jvm-coverage")
        self.assertNotEqual(code, 0)
        self.assertEqual(len(observed), 40)
        self.assertEqual(sum(item["status"] == "blocked" for item in proof["executions"].values()), 6)
        with self.assertRaises(ValueError):
            gate.android().verify(self.candidate, "android-phone", proof, views=views, environment=prior.ownership.runtime())

    def test_failed_or_omitted_extended_owner_cannot_make_complete_union_green(self):
        views = list(gate.android().SUPPORTED_VIEWS)
        code, proof, _ = self.controller(views, failure="device-free-order-isolation-stability")
        self.assertNotEqual(code, 0)
        self.assertEqual(proof["executions"]["device-free-order-isolation-stability"]["status"], "failed")
        with self.assertRaises(ValueError): gate.android().verify(self.candidate, "android-phone", proof, views=views, environment=prior.ownership.runtime())
        code, complete, _ = self.controller(views)
        self.assertEqual(code, 0)
        del complete["executions"]["critical-policy-mutations-extended"]
        prior.ownership.sign(complete)
        with self.assertRaises(ValueError): gate.android().verify(self.candidate, "android-phone", complete, views=views, environment=prior.ownership.runtime())

    def test_final_generation_keeps_npm5_and_requires_every_bound_file(self):
        generation = self.fixture.workflow_files()
        gate.validate_owned_generation(self.candidate, "android-phone", policy_root=self.policy_root)
        self.assertEqual(gate.validate_tree_wiring(self.source().entries), generation["name"])
        self.assertEqual(len(generation["workflows"]), 5)
        self.assertTrue(gate.packages().consumer_generation(self.candidate))
        for path in generation["workflows"] | {gate.WORKFLOW: {}}:
            forged = deepcopy(self.source().entries)
            forged[path]["sha"] = "a" * 40
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.validate_tree_wiring(forged)
        generations = gate.packages().workflow_generations()
        self.assertEqual(len(generations),23)
        self.assertEqual(len([row for row in generations
                              if row['name'] != 'npm-consumers-sync-ci-budget-v1']),22)
        prior = next(row for row in generations if row['name']=='protected-producer-ci37-v1')
        self.assertEqual(len(prior['workflows']),5)
        self.assertEqual(gate.packages().validate_tree_wiring(prior['workflows']),prior['name'])
        for name in ('protected-producer-metadata-ci-v1', 'protected-producer-seven-target-ci-v1',
                     'protected-producer-original-default-v1'):
            enrolled = next(row for row in generations if row['name'] == name)
            self.assertEqual(set(enrolled['workflows']), set(gate.packages().METADATA_WORKFLOW_PATHS))
            self.assertEqual(gate.packages().validate_tree_wiring(enrolled['workflows']), name)

    def test_partial_selected_host_does_not_execute_product_or_claim_reuse(self):
        self.prepare_project()
        with patch.dict(os.environ, self.context()):
            code, proof = self.project(include_platform=False)
        self.assertEqual(code, 0)
        self.assertFalse(proof["include_platform"])
        self.assertFalse(proof["reusable"])
        self.assertIsNone(proof["environment"])
        self.assertEqual(proof["platform_results"], {})
        self.assertEqual(set(proof["results"]), set(self.registry["suites"]))
        self.assertFalse((self.candidate / "build" / handoff.PICO).exists())

    def test_unselected_android_owner_cannot_delegate_pico(self):
        self.fixture.workflow_files()
        expected = self.fixture.merge(empty=True)
        self.assertFalse(expected["required"])
        with patch.dict(os.environ, self.context()), patch.object(handoff, "gate", return_value=gate):
            self.assertEqual(self.owner(), {})

    def test_partial_execution_preserves_exact_selected_shared_subset_without_runtime_fallback(self):
        self.prepare_project()
        selection = SimpleNamespace(candidate_selection=lambda *args: {
            "suites": ["first"], "include_platform": False, "full_host": False})
        with patch.dict(os.environ, self.context()), patch.object(handoff, "gate", return_value=gate), \
                patch.object(handoff, "host_selection", return_value=selection), \
                patch.object(shared.inputs, "load_registry", return_value=self.registry), \
                patch.object(shared, "capture_execution_environment", side_effect=AssertionError("unneeded runtime")), \
                redirect_stdout(io.StringIO()):
            code, proof = handoff.project(self.candidate, self.fixture.event, self.fixture.sha, "pull_request",
                policy_root=self.policy_root, junit=self.directory / "partial.xml", receipt_path=self.directory / "partial.json",
                timeout=10, host_timeout=10)
        self.assertEqual(code, 0)
        self.assertEqual(proof["requested_suites"], ["first"])
        self.assertEqual(set(proof["results"]), {"first"})
        self.assertFalse(proof["reusable"])
        self.assertFalse((self.candidate / "build/second").exists())

    def test_deployed_npm_owner_cannot_be_disabled_by_android_composition(self):
        self.fixture.workflow_files()
        self.fixture.merge()
        packages = gate.packages()
        with patch.object(packages, "consumer_base", return_value=True), \
                patch.object(packages, "consumer_generation", return_value=False), \
                self.assertRaisesRegex(ValueError, "npm consumer ownership cannot be disabled"):
            packages.candidate_plan(self.candidate, self.fixture.event, self.fixture.sha)

    def test_handoff_prevents_unreviewed_predecessor_overwrite_and_profile_extra_loss(self):
        self.fixture.workflow_files()
        extra = {"name": "new-required-contract", "entrypoint": "android/phone/tests/new-required-contract.py", "interpreter": "python"}
        path = self.candidate / "tests/platform-profile.json"
        profile = json.loads(path.read_text());profile["suites"].append(extra);path.write_text(json.dumps(profile))
        (self.candidate / extra["entrypoint"]).write_text("# Required extra\n")
        self.fixture.fixture.commit()
        self.fixture.merge("tests/platform-profile.json", json.dumps({**profile, "suites": profile["suites"][:-1]}))
        with self.assertRaisesRegex(ValueError, "predecessor profile extra"):
            gate.validate_owned_generation(self.candidate, "android-phone", policy_root=self.policy_root,
                                           before_sha=self.fixture.event["pull_request"]["base"]["sha"])
        before = gate._sources(self.candidate)
        previous = deepcopy(before.entries)
        target = ".github/workflows/android-tests.yml"
        previous[target]["sha"] = "a" * 40
        before.entries = previous
        with self.assertRaisesRegex(ValueError, "unreviewed predecessor"):
            handoff.validate_sources(self.source(), "android-phone", policy_root=self.policy_root, previous=before)

    def test_android_main_sync_registration_cannot_bypass_complete_owner_validation(self):
        transfer = handoff.policy()
        paths = set(transfer["legacy_workflows"]) | set(transfer["source_contracts"])
        sync = json.loads((ROOT / ".github/sync-test-reuse.json").read_text())
        self.assertEqual(set(sync["reconciliation_repair_paths"]["android-main"]), paths)
        self.assertEqual(len(paths), 6)
        self.fixture.workflow_files(); self.fixture.merge()
        event = deepcopy(self.fixture.event)
        event["pull_request"]["base"]["ref"] = "android-main"
        gate.validate_execution_generation(self.candidate, event, policy_root=self.policy_root)
        plan = gate.candidate_plan(self.candidate, event, self.fixture.sha, policy_root=self.policy_root)
        self.assertTrue(plan["required"])
        self.assertEqual(len(gate.android().plan(self.candidate, "android-main", views=plan["views"])["executions"]), 40)
        # The sync registration permits inspection, never arbitrary repaired bytes.
        # Mutate immutable Git entries so this exercises the real generation and
        # source validators without executing candidate commands or building SDKs.
        source = self.source()
        previous = gate._sources(self.candidate, event["pull_request"]["base"]["sha"])
        targets = paths | {".github/workflows/repository-checks.yml", gate.WORKFLOW,
                           ".github/workflows/project-tests.yml"}
        for target in sorted(targets):
            for mutation in ("altered", "missing", "symlink"):
                changed = copy(source)
                changed.entries = deepcopy(source.entries)
                if mutation == "missing":
                    changed.entries.pop(target)
                elif mutation == "symlink":
                    changed.entries[target]["mode"] = "120000"
                else:
                    changed.entries[target]["sha"] = "a" * 40
                with self.subTest(target=target, mutation=mutation), \
                        patch.object(gate, "_sources", side_effect=lambda _candidate, commit=None:
                                     previous if commit is not None else changed), \
                        self.assertRaises(ValueError):
                    gate.validate_execution_generation(self.candidate, event, policy_root=self.policy_root)
        trusted = gate.load_policy()
        self.assertEqual(trusted["required_branches"], [])
        self.assertEqual(trusted["activation_blockers"], ["prospective-generation-hosted-qualification"])
        self.assertFalse(gate.ACTIVATION_READY)
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            gate.admit(self.candidate, event, policy_root=self.policy_root)

    def test_profile_minimum_and_unknown_extra_are_complete_and_no_alias_is_allowed(self):
        self.fixture.workflow_files()
        path = self.candidate / "tests/platform-profile.json"
        original = json.loads(path.read_text())
        for mutate in (lambda p: p["suites"].pop(), lambda p: p["suites"][0].update(entrypoint="new.py"),
                       lambda p: p["suites"].append({**p["suites"][0], "name": "duplicate-alias"})):
            changed = deepcopy(original);mutate(changed);path.write_text(json.dumps(changed));self.fixture.fixture.commit()
            with self.assertRaises(ValueError): handoff.validate_sources(self.source(), "android-phone", policy_root=self.policy_root)
        path.write_text(json.dumps(original));self.fixture.fixture.commit()
        for target in handoff.policy()["legacy_workflows"] | handoff.policy()["source_contracts"]:
            tree = deepcopy(self.source().entries)
            tree[target]["mode"] = "100644" if tree[target]["mode"] == "100755" else "100755"
            sources = self.source();sources.entries = tree
            with self.assertRaises(ValueError): handoff.validate_sources(sources, "android-phone", policy_root=self.policy_root)

    def test_internal_owned_project_executes_every_extra_once_and_records_pending_pico(self):
        self.prepare_project(extra=True)
        with patch.dict(os.environ, self.context()):
            code, proof = self.project()
        self.assertEqual(code, 0)
        self.assertEqual(proof["schema"], 2)
        self.assertFalse(proof["reusable"])
        self.assertIsNone(proof["environment"])
        self.assertEqual(proof["platform_selection"]["observed_environment"], OBSERVED)
        self.assertEqual(set(proof["platform_results"]), {item["name"] for item in self.profile["suites"]} - {handoff.PICO})
        self.assertFalse((self.candidate / "build" / handoff.PICO).exists())
        for name in set(proof["platform_results"]) | {"first", "second"}:
            self.assertEqual((self.candidate / "build" / name).read_text(), "actual")
        tree = shared.inputs.full_tree(self.candidate)
        self.assertEqual(set(shared.validate_receipt(proof, self.registry, tree)), {"first", "second"})
        with self.assertRaisesRegex(ValueError, "pending independent"):
            shared.validate_receipt(proof, self.registry, tree, require_all=True)
        tampered = deepcopy(proof);tampered["platform_selection"]["executed"].pop();tampered.pop("receipt_digest")
        tampered["receipt_digest"] = shared.digest(tampered)
        with self.assertRaises(ValueError): shared.validate_receipt(tampered, self.registry, tree)

    def test_direct_legacy_project_context_never_omits_pico(self):
        self.prepare_project()
        env = self.context();env["GITHUB_WORKFLOW_REF"] = env["GITHUB_WORKFLOW_REF"].replace("repository-checks.yml", "project-tests.yml")
        with patch.dict(os.environ, env):
            code, proof = self.project()
        self.assertEqual(code, 0)
        self.assertEqual(proof["schema"], 1)
        self.assertIn(handoff.PICO, proof["platform_results"])
        self.assertEqual((self.candidate / "build" / handoff.PICO).read_text(), "actual")

    def test_push_sync_manual_direct_and_missing_context_cannot_supply_skip_authority(self):
        self.fixture.workflow_files();self.fixture.merge();env = self.context()
        for event_name in ("push", "workflow_run", "schedule"):
            with patch.dict(os.environ, env), patch.object(handoff, "gate", return_value=gate):
                self.assertEqual(handoff.platform_owner(self.candidate, self.fixture.event, self.fixture.sha, event_name,
                                                       policy_root=self.policy_root), {})
        with patch.dict(os.environ, {**env, "GITHUB_WORKFLOW_REF": ""}):
            self.assertEqual(self.owner(), {})
        for key in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_WORKFLOW_SHA"):
            with patch.dict(os.environ, {**env, key: "forged"}), self.assertRaises(ValueError): self.owner()
        with patch.dict(os.environ, env), patch.object(handoff, "gate", return_value=gate):
            pending = self.owner()
        self.assertEqual(set(pending), {handoff.PICO})
        self.assertEqual(pending[handoff.PICO]["owner"], "required-android")
        # Execution may qualify the exact prospective owner; its pending plan
        # still cannot authorize the required outer merge gate.
        with self.assertRaisesRegex(ValueError, "not qualified"):
            gate.admit(self.candidate, self.fixture.event, policy_root=self.policy_root)

    def test_prospective_execution_success_cannot_bypass_required_activation(self):
        self.fixture.workflow_files();self.fixture.merge()
        gate.validate_execution_generation(self.candidate, self.fixture.event, policy_root=self.policy_root)
        views = gate.event_views(self.fixture.event, "pull_request", True)
        code, proof, observed = self.controller(views)
        self.assertEqual(code, 0)
        self.assertEqual(proof["conclusion"], "success")
        self.assertEqual(len(observed), 40)
        expected = self.fixture.plan()
        needs = {"route": {"result": "success", "outputs": gate.outputs(expected)},
                 "android": {"result": "success", "outputs": gate.receipt(expected)}}
        event_path = self.directory / "prospective-event.json"
        event_path.write_text(json.dumps(self.fixture.event))
        android = SimpleNamespace(activated=lambda event: False, current_source_owner=Mock(return_value=None),
            admit=lambda candidate, event: gate.admit(candidate, event, policy_root=self.policy_root))
        packages = gate.packages()
        self.assertEqual(packages.validate_wiring(self.candidate), 'android-owned-npm5-sync-ci-v1')
        package_policy = SimpleNamespace(activated=lambda event: False, validate_wiring=packages.validate_wiring)
        argv = ["check.py", "verify", "--event", str(event_path), "--candidate", str(self.candidate),
                "--sha", self.fixture.sha, "--needs-json", json.dumps(needs)]
        errors = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stderr(errors), \
                patch.object(prior.checks, "configuration", return_value=({}, {})), \
                patch.object(prior.checks, "package_policy", return_value=package_policy), \
                patch.object(prior.checks, "browser_policy", return_value=SimpleNamespace(required=lambda *args: False)), \
                patch.object(prior.checks, "android_policy", return_value=android):
            self.assertNotEqual(prior.checks.main(), 0)
        self.assertIn("not qualified", errors.getvalue())
        android.current_source_owner.assert_called_once()

    def test_unreviewed_platform_omissions_and_reusable_claims_are_rejected(self):
        self.prepare_project()
        with patch.object(shared, "capture_execution_environment", return_value=OBSERVED), \
                patch.object(shared.inputs, "load_registry", return_value=self.registry), self.assertRaises(ValueError):
            shared.execute(self.candidate, include_platform=True,
                           _platform_owner=lambda: {"android-package-store": {"owner": "forged"}})
        with patch.dict(os.environ, self.context()):
            _, receipt = self.project()
        tree = shared.inputs.full_tree(self.candidate)
        for mutate in (lambda p: p.update(reusable=True, environment=OBSERVED),
                       lambda p: p["platform_selection"]["delegated"].update(forged={}),
                       lambda p: p["platform_selection"]["delegated"][handoff.PICO].update(candidate="a" * 40)):
            changed = deepcopy(receipt)
            mutate(changed)
            changed.pop("receipt_digest")
            changed["receipt_digest"] = shared.digest(changed)
            with self.assertRaises(ValueError): shared.validate_receipt(changed, self.registry, tree)

    def test_ownership_is_rechecked_after_local_execution_and_cannot_change_silently(self):
        self.prepare_project()
        with patch.dict(os.environ, self.context()), patch.object(handoff, "gate", return_value=gate), \
                patch.object(gate, "ACTIVATION_READY", True):
            initial = self.owner()
        changed = deepcopy(initial);changed[handoff.PICO]["plan"] = "sha256:" + "0" * 64
        with patch.dict(os.environ, self.context()), \
                patch.object(handoff, "platform_owner", side_effect=[initial, changed]) as owner_check, \
                patch.object(handoff, "host_selection", return_value=self.selection()), \
                patch.object(shared.inputs, "load_registry", return_value=self.registry), \
                patch.object(shared, "capture_execution_environment", return_value=OBSERVED), \
                redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed"):
            handoff.project(self.candidate, self.fixture.event, self.fixture.sha, "pull_request",
                policy_root=self.policy_root, junit=self.directory / "changed.xml", receipt_path=self.directory / "changed.json",
                timeout=10, host_timeout=10)
        self.assertEqual(owner_check.call_count, 2)
        self.assertEqual(json.loads((self.directory / "changed.json").read_text())["conclusion"], "failure")

    def test_outer_still_requires_actual_android_success_after_predictive_profile_transfer(self):
        self.fixture.workflow_files();expected = self.fixture.merge()
        for result in ("failure", "skipped", "cancelled", None):
            with self.assertRaises(ValueError): gate.verify_outer({"result": result, "outputs": gate.receipt(expected)}, expected)
        for field in ("candidate", "plan", "inventory"):
            proof = gate.receipt(expected);proof[field] = "forged"
            with self.assertRaises(ValueError): gate.verify_outer({"result": "success", "outputs": proof}, expected)

    def remove_android_product(self):
        shutil.rmtree(self.candidate / "android")
        for path in handoff.policy()["legacy_workflows"]:
            (self.candidate / path).unlink()
        (self.candidate / "tests/platform-profile.json").write_text(
            json.dumps({"schema": 1, "platform": "shared", "suites": []}))

    def non_android_merge(self, edit=lambda: None):
        base = self.fixture.git("rev-parse", "HEAD")
        self.fixture.git("checkout", "-qb", "non-android-topic")
        edit()
        self.fixture.git("add", "-A")
        self.fixture.git("commit", "--allow-empty", "-qm", "Non-Android source fixture")
        head = self.fixture.git("rev-parse", "HEAD")
        self.fixture.git("checkout", "-q", "android-phone")
        self.fixture.git("merge", "--no-ff", "-qm", "Exact non-Android candidate", "non-android-topic")
        self.fixture.sha = self.fixture.git("rev-parse", "HEAD")
        repository = {"full_name": gate.REPOSITORY, "id": gate.REPOSITORY_ID}
        self.fixture.event = {"repository": repository, "pull_request": {
            "base": {"ref": "main", "sha": base, "repo": repository},
            "head": {"ref": "non-android-topic", "sha": head, "repo": repository}}}

    def test_non_android_target_cannot_waive_present_android_product(self):
        self.fixture.workflow_files();self.fixture.merge()
        for branch in ("main", "apple-main", "apple-ios"):
            with self.subTest(branch=branch):
                self.fixture.event["pull_request"]["base"]["ref"] = branch
                with self.assertRaisesRegex(ValueError, "unexpected Android ownership"):
                    gate.admit(self.candidate, self.fixture.event, policy_root=self.policy_root)
                with self.assertRaisesRegex(ValueError, "unexpected Android ownership"):
                    self.fixture.plan()

    def test_non_android_bootstrap_requires_absence_in_both_complete_git_trees(self):
        self.fixture.workflow_files()
        self.remove_android_product();self.fixture.fixture.commit()
        self.non_android_merge()
        # Sparse working files cannot hide source: both complete maps come from Git.
        for branch in ("main", "apple-main", "apple-ios"):
            with self.subTest(branch=branch):
                self.fixture.event["pull_request"]["base"]["ref"] = branch
                gate.admit(self.candidate, self.fixture.event, policy_root=self.policy_root)
                self.assertFalse(self.fixture.plan()["required"])
                with patch.dict(os.environ, self.context()), patch.object(handoff, "gate", return_value=gate):
                    self.assertEqual(self.owner(), {})
        manual = {"repository": self.fixture.event["repository"], "ref": "refs/heads/main"}
        gate.admit(self.candidate, manual, policy_root=self.policy_root)
        self.assertFalse(gate.candidate_plan(self.candidate, manual, self.fixture.sha,
            event_name="workflow_dispatch", policy_root=self.policy_root)["required"])

    def test_non_android_candidate_deletion_cannot_hide_android_predecessor(self):
        self.fixture.workflow_files()
        self.non_android_merge(self.remove_android_product)
        self.assertFalse(any(path.startswith("android/") for path in self.source().entries))
        for operation in (lambda: gate.admit(self.candidate, self.fixture.event, policy_root=self.policy_root),
                          self.fixture.plan):
            with self.assertRaisesRegex(ValueError, "unexpected Android ownership"):
                operation()

    def test_non_android_bootstrap_rejects_added_mixed_and_nonregular_ownership(self):
        self.fixture.workflow_files()
        self.remove_android_product();self.fixture.fixture.commit()
        self.non_android_merge()
        for relative, mode, kind in (("android/source.cpp", "100644", "blob"),
                                     ("android", "120000", "blob"),
                                     ("android", "160000", "commit"),
                                     (".github/workflows/android-tests.yml", "100644", "blob"),
                                     (".github/workflows/android-vr-tests.yml", "120000", "blob")):
            with self.subTest(path=relative, mode=mode):
                before = gate._sources(self.candidate, self.fixture.event["pull_request"]["base"]["sha"])
                current = self.source()
                current.entries[relative] = {"mode": mode, "type": kind, "sha": "a" * 40}
                with self.assertRaisesRegex(ValueError, "unexpected Android ownership"):
                    gate.validate_non_android_absence(current, before)
        for mode, kind in (("120000", "blob"), ("160000", "commit"), ("100755", "blob")):
            with self.subTest(profile_mode=mode):
                current = self.source()
                current.entries["tests/platform-profile.json"].update(mode=mode, type=kind)
                with self.assertRaisesRegex(ValueError, "regular shared platform profile"):
                    gate.validate_non_android_absence(current)
        current = self.source();current.entries.pop("tests/platform-profile.json")
        with self.assertRaisesRegex(ValueError, "regular shared platform profile"):
            gate.validate_non_android_absence(current)

    def test_non_android_bootstrap_rejects_android_malformed_or_mixed_profile(self):
        self.fixture.workflow_files()
        self.remove_android_product();self.fixture.fixture.commit()
        self.non_android_merge()
        absent = self.source()
        for profile in ({"schema": 1, "platform": "android", "suites": []},
                        {"schema": 1, "platform": "shared", "suites": [{"name": "hidden-android"}]},
                        {"schema": True, "platform": "shared", "suites": []},
                        {"schema": 1, "platform": "ios", "suites": []},
                        {"schema": 1, "platform": "shared", "suites": [], "omit_android": True}):
            with self.subTest(profile=profile):
                (self.candidate / "tests/platform-profile.json").write_text(json.dumps(profile))
                self.fixture.fixture.commit()
                current = self.source()
                for source, before in ((current, absent), (absent, current)):
                    with self.assertRaisesRegex(ValueError, "unreviewed platform profile"):
                        gate.validate_non_android_absence(source, before)

    def test_workflows_handle_label_changes_preserve_parallel_common_and_retire_only_legacy_pr(self):
        document = handoff.policy()
        for target, entry in document["legacy_workflows"].items():
            current = (ROOT / entry["source"]).read_text()
            self.assertNotRegex(current, r"(?m)^  pull_request:$")
            self.assertEqual(entry["reviewed_blob"], REVIEWED_WORKFLOWS[target][0])
            original = reviewed_workflow(target, current)
            self.assertEqual(current, original[:original.index("  pull_request:\n")] + original[original.index("  push:\n"):])
            with self.assertRaisesRegex(ValueError, "identity changed"):
                reviewed_workflow(target, current + "\n")
        for name in ("repository-checks.yml",):
            text = (ROOT / handoff.OWNED / name).read_text()
            workflow = yaml.safe_load(text)
            trigger = workflow.get("on", workflow.get(True))
            self.assertIn("labeled", trigger["pull_request"]["types"])
            self.assertIn("unlabeled", trigger["pull_request"]["types"])
            self.assertEqual(workflow["jobs"]["project"]["needs"], "route")
            self.assertEqual(workflow["jobs"]["android"]["needs"], "route")
            self.assertIn("android", workflow["jobs"]["repository-checks"]["needs"])
        project = (ROOT / handoff.OWNED / "project-tests.yml").read_text()
        self.assertIn("trusted/tools/repository-checks/android_handoff.py", project)
        self.assertNotIn("--exclude", project)
        self.assertNotIn("continue-on-error", (ROOT / handoff.OWNED / "android-required.yml").read_text())


class SyncOwnerIntegrationTests(unittest.TestCase):
    """Actual owner/Sync execution; topology attestation has separate API regressions."""
    def setUp(self):
        self.transfer = AndroidOwnerTransferTests(methodName="runTest")
        self.transfer.setUp()
        self.addCleanup(self.transfer.doCleanups)
        self.transfer.prepare_project(extra=True)
        self.candidate = self.transfer.candidate
        self.directory = self.transfer.directory
        self.fixture = self.transfer.fixture
        self.fixture.event["number"] = 17
        self.repository = {"full_name": gate.REPOSITORY, "id": gate.REPOSITORY_ID}
        self.pr = deepcopy(self.fixture.event["pull_request"])
        self.pr.update(number=17, state="open", mergeable=True, merge_commit_sha=self.fixture.sha, labels=[])
        self.pr["head"]["ref"] = "android-main"
        self.calls = []
        self.api = SimpleNamespace(json=self.api_read)
        self.request = SimpleNamespace(repository=gate.REPOSITORY, repository_id=gate.REPOSITORY_ID,
            number=17, base="android-phone", base_sha=self.pr["base"]["sha"], head="android-main",
            head_sha=self.pr["head"]["sha"], head_repository_id=gate.REPOSITORY_ID, merge_sha=self.fixture.sha,
            parent="android-main", parent_sha=self.pr["head"]["sha"], profile="android-phone",
            classification="direct", repair_paths=(), changed_paths=tuple(self.fixture.plan()["paths"]))
        self.args = SimpleNamespace(candidate=self.candidate, repository=gate.REPOSITORY, pull_request=17,
            mode="fallback", profile="android-phone", base_sha=self.request.base_sha, head_sha=self.request.head_sha,
            merge_sha=self.request.merge_sha, junit=self.directory / "sync.xml", receipt=self.directory / "sync.json")
        self.validation = load("android_owned_actual_sync_validator", "tools/test-evidence/validate-sync.py")
        self.transport = SimpleNamespace(load_config=lambda: {"repository": gate.REPOSITORY, "repository_id": gate.REPOSITORY_ID},
            classify_event=lambda event, config, api: self.request,
            branch_sha=lambda api, repository, branch: self.request.base_sha if branch == self.request.base else self.request.parent_sha)
        original_loader = self.validation._trusted_module
        self.enterContext(patch.object(self.validation, "_gate", return_value=self.transport))
        self.enterContext(patch.object(self.validation, "_trusted_module", side_effect=lambda name, path:
            handoff if name == "sync_android_platform_owner" else original_loader(name, path)))
        self.enterContext(patch.object(handoff, "gate", return_value=gate))
        self.enterContext(patch.object(shared.inputs, "load_registry", return_value=self.transfer.registry))
        self.enterContext(patch.object(shared, "capture_execution_environment", return_value=OBSERVED))
        self.enterContext(patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": gate.REPOSITORY + "/.github/workflows/sync-validation.yml@refs/heads/main"}))

    def api_read(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "repos/" + gate.REPOSITORY:
            return deepcopy(self.repository)
        if endpoint == "repos/" + gate.REPOSITORY + "/pulls/17":
            return deepcopy(self.pr)
        prefix = "repos/" + gate.REPOSITORY
        if endpoint == prefix + "/commits/refs/pull/17/merge":
            return {"sha": self.request.merge_sha, "parents": [
                {"sha": self.request.base_sha}, {"sha": self.request.head_sha}]}
        if endpoint == prefix + "/compare/" + "b" * 40 + "..." + self.request.base_sha + "?per_page=1":
            # The explicit stale-source negative is an unrelated snapshot,
            # not a valid ancestor or an unregistered transport exception.
            return {"status": "diverged", "ahead_by": 1, "behind_by": 1, "total_commits": 1,
                    "base_commit": {"sha": "b" * 40}, "merge_base_commit": {"sha": "c" * 40},
                    "commits": [{"sha": self.request.head_sha}], "files": []}
        raise AssertionError("unregistered authenticated source-PR transport")

    def validate(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return self.validation.validate_sync(self.args, api=self.api)

    def refresh_candidate(self):
        self.fixture.fixture.commit()
        head = self.fixture.git("rev-parse", "HEAD")
        tree = self.fixture.git("rev-parse", "HEAD^{tree}")
        merge = self.fixture.git("commit-tree", tree, "-p", self.request.base_sha, "-p", head,
                                 "-m", "Exact source-PR merge after fixture change")
        self.fixture.git("checkout", "--quiet", "--detach", merge)
        self.fixture.sha = merge
        self.pr["head"]["sha"] = head
        self.pr["merge_commit_sha"] = merge
        self.request.head_sha = self.request.parent_sha = self.args.head_sha = head
        self.request.merge_sha = self.args.merge_sha = merge
        self.request.changed_paths = tuple(self.fixture.git("diff", "--name-only", self.request.base_sha, merge).splitlines())

    def test_stale_sync_snapshot_recomputes_actual_android_owner_without_native_event_rewrite(self):
        snapshot='1'*40;original_snapshot='2'*40
        self.pr['base']['sha']=snapshot;self.request.event_base_sha=original_snapshot
        prefix='repos/'+gate.REPOSITORY
        extra={
            prefix+'/commits/refs/pull/17/merge':{'sha':self.request.merge_sha,'parents':[
                {'sha':self.request.base_sha},{'sha':self.request.head_sha}]},
            prefix+'/branches/'+self.request.base:{'name':self.request.base,'protected':True,
                'commit':{'sha':self.request.base_sha}},
        }
        from urllib.parse import quote
        extra[prefix+'/git/ref/heads/'+quote(self.request.head,safe='')]={
            'ref':'refs/heads/'+self.request.head,'object':{'type':'commit','sha':self.request.head_sha}}
        for observed in (snapshot,original_snapshot):
            extra[prefix+'/compare/'+observed+'...'+self.request.base_sha+'?per_page=1']={
                'status':'ahead','ahead_by':40,'behind_by':0,'total_commits':40,
                'base_commit':{'sha':observed},'merge_base_commit':{'sha':observed},
                'commits':[{'sha':'3'*40}],'files':[]}
        def read(endpoint):
            return deepcopy(extra[endpoint]) if endpoint in extra else self.api_read(endpoint)
        api=SimpleNamespace(json=read);before=deepcopy(self.pr)
        with patch.object(shared,'execute',side_effect=AssertionError('selection must not execute')):
            selected=handoff.sync_platform_owner(self.candidate,self.request,api,policy_root=self.transfer.policy_root)
        self.assertEqual(set(selected),{handoff.PICO});self.assertEqual(selected[handoff.PICO]['owner'],'required-android')
        self.assertEqual(self.pr,before)
        extra[prefix+'/compare/'+original_snapshot+'...'+self.request.base_sha+'?per_page=1']['status']='diverged'
        with self.assertRaises(ValueError):
            handoff.sync_platform_owner(self.candidate,self.request,api,policy_root=self.transfer.policy_root)

    def test_sync_executes_all_shared_and_every_remaining_profile_extra_once(self):
        before = {name: value for name, value in os.environ.items() if name.startswith("GITHUB_")}
        result = self.validate()
        observed = result["execution"]
        self.assertEqual(set(result["executed_suites"]), {"first", "second"})
        self.assertEqual(observed["schema"], 2)
        self.assertFalse(observed["reusable"])
        self.assertIsNone(observed["environment"])
        self.assertEqual(set(result["pending_platform_owners"]), {handoff.PICO})
        self.assertFalse(result["reusable"])
        self.assertFalse(result["qualification"])
        self.assertEqual(result["reused_suites"], [])
        self.assertIsNone(result["parent_evidence"])
        self.assertEqual(set(observed["platform_results"]), {item["name"] for item in self.transfer.profile["suites"]} - {handoff.PICO})
        for name in set(observed["platform_results"]) | {"first", "second"}:
            self.assertEqual((self.candidate / "build" / name).read_text(), "actual")
        self.assertFalse((self.candidate / "build" / handoff.PICO).exists())
        self.assertEqual({name: value for name, value in os.environ.items() if name.startswith("GITHUB_")}, before)
        with self.assertRaisesRegex(ValueError, "pending independent"):
            shared.validate_receipt(observed, self.transfer.registry, shared.inputs.full_tree(self.candidate), require_all=True)
        self.assertGreaterEqual(self.calls.count("repos/" + gate.REPOSITORY + "/pulls/17"), 3)

    def test_prerequisite_selection_binds_pending_owner_without_execution(self):
        with patch.object(shared, "execute", side_effect=AssertionError("planning cannot execute commands")):
            selected = self.validation.select_sync(self.args, api=self.api)
        self.assertEqual(selected["lane"], "complete")
        self.assertTrue(selected["full_host"])
        self.assertFalse(selected["reusable"])
        self.assertEqual(set(selected["pending_platform_owners"]), {handoff.PICO})
        self.assertIn("platform_owner_policy", selected)
        self.args.expected_selection = selected["selection"]
        self.assertEqual(self.validate()["ci_selection"], selected)

    def test_actual_candidate_generation_change_after_commands_fails_closed(self):
        original_execute = shared.execute
        def changed_generation(*args, **kwargs):
            result = original_execute(*args, **kwargs)
            (self.candidate / ".github/workflows/repository-checks.yml").write_text("unreviewed caller\n")
            return result
        with patch.object(shared, "execute", side_effect=changed_generation), \
                self.assertRaisesRegex(shared.ExecutionError, "immutable tracked inputs"):
            self.validate()
        self.assertFalse(self.args.receipt.exists())

    def test_foreign_or_stale_actual_api_source_cannot_omit_a_command(self):
        original = deepcopy(self.pr)
        mutations = [lambda p: p.update(state="closed"), lambda p: p.update(merge_commit_sha="f" * 40),
                     lambda p: p["base"].update(sha="b" * 40), lambda p: p["head"].update(sha="a" * 40),
                     lambda p: p["head"]["repo"].update(full_name="foreign/repository"),
                     lambda p: p.update(mergeable=None), lambda p: p.pop("labels")]
        for mutate in mutations:
            self.pr = deepcopy(original); mutate(self.pr)
            with self.subTest(pr=self.pr), patch.object(shared, "execute") as execute, self.assertRaises(ValueError):
                self.validate()
            execute.assert_not_called()
        self.pr = original

    def test_real_shared_failure_cannot_publish_pending_success(self):
        (self.candidate / "tests/first.py").write_text("raise RuntimeError('real selected suite failure')\n")
        self.refresh_candidate()
        with self.assertRaisesRegex(ValueError, "selected shared or product"):
            self.validate()
        self.assertFalse(self.args.receipt.exists())

    def test_real_remaining_product_failure_cannot_publish_pending_success(self):
        item = next(item for item in self.transfer.profile["suites"] if item["name"] != handoff.PICO)
        (self.candidate / item["entrypoint"]).write_text("raise RuntimeError('real profile suite failure')\n")
        self.refresh_candidate()
        with self.assertRaisesRegex(ValueError, "selected shared or product"):
            self.validate()
        self.assertFalse(self.args.receipt.exists())

    def test_actual_label_or_permanent_ref_drift_rejects_success_after_commands(self):
        original_execute = shared.execute
        def changed_labels(*args, **kwargs):
            result = original_execute(*args, **kwargs)
            self.pr["labels"] = [{"name": "android-long-diagnostics"}]
            return result
        with patch.object(shared, "execute", side_effect=changed_labels), self.assertRaisesRegex(ValueError, "labels changed"):
            self.validate()
        self.assertFalse(self.args.receipt.exists())
        self.pr["labels"] = []
        self.transport.branch_sha = lambda *args: "f" * 40
        with self.assertRaisesRegex(ValueError, "branch moved"):
            self.validate()
        self.assertFalse(self.args.receipt.exists())

    def test_forged_pending_plan_or_missing_product_result_cannot_publish_success(self):
        original_execute = shared.execute
        for mutation in ("pending-plan", "missing-product"):
            def forged(*args, **kwargs):
                status, returned = original_execute(*args, **kwargs)
                observed = deepcopy(returned)
                if mutation == "pending-plan":
                    observed["platform_selection"]["delegated"][handoff.PICO]["plan"] = "sha256:" + "0" * 64
                else:
                    observed["platform_results"].pop(next(iter(observed["platform_results"])))
                observed["receipt_digest"] = shared.digest({key: value for key, value in observed.items() if key != "receipt_digest"})
                shared._write_receipt(kwargs["receipt_path"], observed)
                return status, observed
            with self.subTest(mutation=mutation), patch.object(shared, "execute", side_effect=forged), self.assertRaises(ValueError):
                self.validate()
            self.assertFalse(self.args.receipt.exists())

    def test_legacy_sync_generation_executes_its_pico_profile_in_full(self):
        self.fixture.workflow_files(owned=False)
        # workflow_files commits the fixture; form its actual new source-PR merge.
        head = self.fixture.git("rev-parse", "HEAD")
        tree = self.fixture.git("rev-parse", "HEAD^{tree}")
        merge = self.fixture.git("commit-tree", tree, "-p", self.request.base_sha, "-p", head,
                                 "-m", "Exact legacy source-PR merge")
        self.fixture.git("checkout", "--quiet", "--detach", merge)
        self.pr["head"]["sha"] = head; self.pr["merge_commit_sha"] = merge
        self.request.head_sha = self.request.parent_sha = self.args.head_sha = head
        self.request.merge_sha = self.args.merge_sha = merge
        result = self.validate()
        self.assertEqual(result["execution"]["schema"], 1)
        self.assertNotIn("pending_platform_owners", result)
        self.assertEqual(set(result["execution"]["platform_results"]), {item["name"] for item in self.transfer.profile["suites"]})
        self.assertEqual((self.candidate / "build" / handoff.PICO).read_text(), "actual")

    def test_missing_mandatory_repository_gate_cannot_supply_skip_authority(self):
        with patch.object(self.validation, "_repository_owner_policy", return_value={}), \
                patch.object(shared, "execute") as execute, self.assertRaisesRegex(ValueError, "mandatory canonical"):
            self.validate()
        execute.assert_not_called()

    def test_pending_sync_success_never_substitutes_for_android_execution(self):
        result = self.validate()
        expected = gate.candidate_plan(self.candidate, {"repository": self.repository, "number": 17,
            "pull_request": self.pr}, self.request.merge_sha)
        for conclusion in ("failure", "skipped", "cancelled", None):
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                gate.verify_outer({"result": conclusion, "outputs": {}}, expected)
        with self.assertRaises(ValueError):
            gate.verify_outer({"result": "success", "outputs": result["pending_platform_owners"]}, expected)
        with self.assertRaisesRegex(ValueError, "blocked"):
            gate.admit(self.candidate, {"repository": self.repository, "pull_request": self.pr})


if __name__ == "__main__":
    unittest.main()
