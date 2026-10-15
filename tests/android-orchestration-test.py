#!/usr/bin/env python3
"""Offline exact-event Android required-owner contracts; no product builds."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("android_gate_test_subject", "tools/repository-checks/android_gate.py")
ownership = load("android_owner_fixture", "tests/android-ci-test.py")
checks = load("android_outer_test_subject", "tools/repository-checks/check.py")


class RequiredAndroidTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ownership.AndroidOwnershipTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.candidate = self.fixture.candidate
        self.temporary = Path(self.fixture.temporary.name)
        self.git = self.fixture.git
        self.policy_root = self.temporary / "policy"
        names = [gate.POLICY, ".github/android-checks.json", ".github/package-workflow-generations.json",
                 ".github/branch-policy.json",
                 "tools/repository-checks/android_gate.py", "tools/repository-checks/check.py",
                 "tools/repository-checks/package_checks.py", gate.CALLEE, *gate.CALLERS,
                 *gate.android().EXECUTION_FILES]
        for relative in set(names):
            target = self.policy_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.policy = gate.load_policy()
        self.policy["required_branches"] = ["android-phone"]
        self.policy["activation_blockers"] = []
        self.write_policy()
        self.sequence = 0

    def write_policy(self):
        (self.policy_root / gate.POLICY).write_text(json.dumps(self.policy))

    def workflow_files(self, *, direct=False, producer=False):
        packages = gate.packages()
        name = ("shared-receipt-v1" if producer else "packages-v1") + ("-direct" if direct else "") + "-android"
        generation = next(item for item in packages.workflow_generations() if item["name"] == name)
        paths = list((ROOT / "tools/repository-checks/workflows").rglob("*.yml"))
        contents = {gate._blob(path.read_bytes())["sha"]: path.read_bytes() for path in paths}
        for relative, entry in generation["workflows"].items():
            target = self.candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[entry["sha"]])
        (self.candidate / gate.WORKFLOW).write_bytes((ROOT / gate.CALLEE).read_bytes())
        self.fixture.commit()
        return generation

    def merge(self, relative="android/phone/changed.cpp", contents="// changed\n", *, empty=False, mode=None, rename_from=None):
        base = self.git("rev-parse", "HEAD")
        self.sequence += 1
        task = "task" + str(self.sequence)
        self.git("checkout", "-qb", task)
        if empty:
            self.git("commit", "--allow-empty", "-qm", "Empty source delta")
        else:
            path = self.candidate / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if rename_from is not None:
                (self.candidate / rename_from).rename(path)
            elif mode == "gitlink":
                self.git("update-index", "--add", "--cacheinfo", "160000," + base + "," + relative)
            elif mode == "symlink":
                path.symlink_to("outside")
            elif contents is None:
                path.unlink()
            else:
                path.write_text(contents)
                if mode is not None: path.chmod(mode)
            if mode == "gitlink":
                self.git("commit", "-qm", "Foreign gitlink fixture")
            else:
                self.fixture.commit()
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "android-phone")
        self.git("merge", "--no-ff", "-qm", "Exact candidate fixture", task)
        sha = self.git("rev-parse", "HEAD")
        repository = {"full_name": gate.REPOSITORY, "id": gate.REPOSITORY_ID}
        self.event = {"repository": repository, "pull_request": {
            "base": {"ref": "android-phone", "sha": base, "repo": repository},
            "head": {"ref": "task/android/change", "sha": head, "repo": repository}}}
        self.sha = sha
        return self.plan()

    def plan(self, **kwargs):
        return gate.candidate_plan(self.candidate, self.event, self.sha, policy_root=self.policy_root, **kwargs)

    def anchor(self):
        self.policy["reviewed_sources"]["android-phone"]["readers"] = gate.reader_identity(gate._sources(self.candidate).entries)
        self.write_policy()

    def test_exact_pr_selects_forty_distinct_owners_and_all_current_phone_cases(self):
        result = self.merge()
        self.assertTrue(result["required"])
        self.assertEqual(result["views"], list(ownership.android.VIEWS))
        owner = gate.android().plan(self.candidate, "android-phone", views=result["views"])
        self.assertEqual(len(owner["executions"]), 40)
        self.assertEqual(len(owner["executions"]["phone-robolectric-launcher"]["cases"]), 116)
        self.assertIn("critical-policy-mutations", owner["executions"])
        self.assertEqual(result["owner_plan"], owner["plan"])
        self.assertNotIn("shared", owner["executions"])

    def test_parent_sync_and_reconcile_names_never_waive_critical_mutation(self):
        self.merge()
        for name in ("main", "android-main", "reconcile/android-phone/current", "feature/android-phone/current"):
            self.event["pull_request"]["head"]["ref"] = name
            self.assertIn("mutation", self.plan()["views"])
            self.assertTrue(self.plan()["required"])

    def test_forged_event_candidate_parent_target_and_foreign_repository_fail(self):
        self.merge()
        for mutate in (lambda e: e["repository"].update(id=1),
                       lambda e: e["pull_request"]["base"].update(sha="a" * 40),
                       lambda e: e["pull_request"]["head"].update(sha="b" * 40),
                       lambda e: e["pull_request"]["base"]["repo"].update(full_name="overte-org/overte")):
            event = deepcopy(self.event)
            mutate(event)
            with self.assertRaises(ValueError):
                gate.candidate_plan(self.candidate, event, self.sha, policy_root=self.policy_root)
        with self.assertRaises(ValueError):
            gate.candidate_plan(self.candidate, self.event, "c" * 40, policy_root=self.policy_root)
        with self.assertRaises(ValueError):
            self.plan(event_name="push")
        self.event["pull_request"]["base"]["ref"] = "unknown-target"
        with self.assertRaises(ValueError): self.plan()
        self.event["pull_request"]["base"]["ref"] = "android-phone"
        (self.candidate / "android/common/tests/suite/catalog.json").write_text("dirty")
        with self.assertRaises(ValueError): self.plan()

    def test_independent_browser_delta_requires_both_full_reader_anchors_and_regular_modes(self):
        self.anchor()
        result = self.merge("browser-client/src/example.ts", "export const x=1;\n")
        self.assertFalse(result["required"])
        self.assertEqual(result["reason"], "reviewed-independent-inputs")
        self.assertEqual(result["views"], [])
        sparse = self.fixture.sparse_clone()
        self.assertEqual(gate.candidate_plan(sparse, self.event, self.sha, policy_root=self.policy_root), result)
        self.policy["reviewed_sources"]["android-phone"]["readers"] = "sha256:" + "0" * 64
        self.write_policy()
        self.assertTrue(self.plan()["required"])

    def test_historical_reader_change_then_browser_change_cannot_use_old_anchor(self):
        self.anchor()
        reader = self.candidate / "android/common/tests/new-reader.py"
        reader.write_text("# now observes browser assets\n")
        self.fixture.commit()
        self.assertTrue(self.merge("browser-client/asset.txt", "changed")["required"])

    def test_real_deletion_and_rename_keep_both_change_sides(self):
        self.anchor()
        self.assertFalse(self.merge("browser-client/deleted.txt", "browser fixture")["required"])
        deleted = self.merge("browser-client/deleted.txt", None)
        self.assertFalse(deleted["required"])
        self.assertEqual(deleted["paths"], ["browser-client/deleted.txt"])
        self.assertFalse(self.merge("browser-client/rename.txt", "browser fixture")["required"])
        renamed = self.merge("scripts/packaged.md", rename_from="browser-client/rename.txt")
        self.assertTrue(renamed["required"])
        self.assertEqual(renamed["paths"], ["browser-client/rename.txt", "scripts/packaged.md"])

    def test_packaged_markdown_unknown_and_ancestor_package_inputs_stay_complete(self):
        self.anchor()
        for relative in ("BUILD_ANDROID.md", "scripts/packaged.md", "package.json", "new-root-file"):
            with self.subTest(relative=relative):
                self.assertTrue(self.merge(relative, "new immutable input")["required"])
        # Even an unrelated subsequent delta cannot hide a historical new reader.
        self.assertTrue(self.merge("browser-client/asset.txt", "browser fixture")["required"])

    def test_symlink_and_gitlink_in_independent_root_never_receive_skip(self):
        self.anchor()
        self.assertTrue(self.merge("browser-client/unsafe", mode="symlink")["required"])
        self.assertTrue(self.merge("browser-client/foreign", mode="gitlink")["required"])

    def test_verified_empty_and_manual_variants_preserve_existing_meaning(self):
        result = self.merge(empty=True)
        self.assertFalse(result["required"])
        self.assertEqual(result["reason"], "verified-empty-tree-delta")
        event = {"repository": self.event["repository"], "ref": "refs/heads/android-phone"}
        manual = gate.candidate_plan(self.candidate, event, self.sha, event_name="workflow_dispatch", policy_root=self.policy_root)
        self.assertTrue(manual["required"])
        self.assertEqual(manual["views"], list(ownership.android.DEFAULT_VIEWS))
        self.assertNotIn("mutation", manual["views"])
        self.assertNotIn("stability", result["views"])
        self.assertNotIn("endurance", result["views"])

    def test_complete_old_and_new_package_tuples_remain_approved_but_mixed_android_callee_fails(self):
        for direct, producer in ((False, False), (False, True), (True, False), (True, True)):
            generation = self.workflow_files(direct=direct, producer=producer)
            self.assertEqual(gate.validate_tree_wiring(gate._sources(self.candidate).entries), generation["name"])
        original = deepcopy(gate._sources(self.candidate).entries)
        for mutate in (lambda t: t.pop(gate.WORKFLOW),
                       lambda t: t[gate.WORKFLOW].update(mode="100755"),
                       lambda t: t[gate.WORKFLOW].update(mode="120000"),
                       lambda t: t[gate.WORKFLOW].update(type="commit", mode="160000"),
                       lambda t: t[gate.WORKFLOW].update(sha="a" * 40),
                       lambda t: t[".github/workflows/repository-checks.yml"].update(sha="b" * 40)):
            tree = deepcopy(original)
            mutate(tree)
            with self.assertRaises(ValueError): gate.validate_tree_wiring(tree)

    def test_default_policy_explicitly_blocks_live_admission_and_candidate_cannot_enable_it(self):
        self.workflow_files()
        self.merge()
        self.assertTrue(gate.has_staged_caller(self.candidate))
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            gate.admit(self.candidate, self.event)
        # Trusted test policy enables only the fake fixture target.
        with self.assertRaisesRegex(ValueError, "not implemented"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        with patch.object(gate, "ACTIVATION_READY", True):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        self.policy["activation_blockers"] = ["extended-tier-prerequisite-transfer"]
        self.write_policy()
        with self.assertRaisesRegex(ValueError, "extended-tier-prerequisite-transfer"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)

    def test_staged_detection_works_without_execution_runtime_in_trusted_sparse_checkout(self):
        trusted = self.temporary / 'legacy-trusted-sparse'
        for relative in ('tools/repository-checks/android_gate.py', 'tools/repository-checks/android.py', *gate.CALLERS):
            target = trusted / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        sparse_gate = load('legacy_sparse_android_gate', str(trusted / 'tools/repository-checks/android_gate.py'))
        caller = self.candidate / '.github/workflows/repository-checks.yml'
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text('# legacy non-Android caller\n')
        self.fixture.commit()
        with patch.object(sparse_gate, '_sources', side_effect=AssertionError('execution must remain unloaded')):
            self.assertFalse(sparse_gate.has_staged_caller(self.candidate, policy_root=trusted))
            # A dirty file cannot manufacture ownership absent from Git HEAD.
            caller.write_bytes((ROOT / gate.CALLERS[0]).read_bytes())
            self.assertFalse(sparse_gate.has_staged_caller(self.candidate, policy_root=trusted))
            self.fixture.commit()
            self.assertTrue(sparse_gate.has_staged_caller(self.candidate, policy_root=trusted))
            self.assertTrue(sparse_gate.has_staged_caller(self.fixture.sparse_clone(), policy_root=trusted))
            caller.chmod(0o755)
            self.fixture.commit()
            self.assertFalse(sparse_gate.has_staged_caller(self.candidate, policy_root=trusted))

    def test_untrusted_candidate_flags_and_corrupt_trusted_policy_cannot_authorize_activation(self):
        self.workflow_files()
        candidate_policy = self.candidate / gate.POLICY
        candidate_policy.write_text(json.dumps(self.policy))
        self.fixture.commit()
        self.merge()
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            gate.admit(self.candidate, self.event)
        for mutate in (lambda p: p["activation_blockers"].append("unknown"),
                       lambda p: p["required_branches"].append("unknown"),
                       lambda p: p["independent_roots"].append("scripts/"),
                       lambda p: p["workflow_generations"].append(deepcopy(p["workflow_generations"][0]))):
            value = deepcopy(self.policy)
            mutate(value)
            (self.policy_root / gate.POLICY).write_text(json.dumps(value))
            with self.assertRaises(ValueError): gate.load_policy(self.policy_root)
        self.write_policy()
        before = self.plan()["policy"]
        helper = self.policy_root / "tools/repository-checks/android-host-prepare.sh"
        helper.write_text(helper.read_text() + "# reviewed preparation change\n")
        self.assertNotEqual(self.plan()["policy"], before)

    def test_inner_and_outer_recompute_results_and_reject_skips_failures_omissions_tampering(self):
        expected = self.merge()
        route = {"result": "success", "outputs": gate.outputs(expected)}
        executed = {"result": "success", "outputs": gate.receipt(expected)}
        needs = {"route": route, "execute": executed}
        self.assertEqual(gate.verify_inner(needs, expected), gate.receipt(expected))
        for change in (lambda n: n.pop("execute"), lambda n: n["route"].update(result="failure"),
                       lambda n: n["execute"].update(result="skipped"),
                       lambda n: n["execute"].update(result="failure"),
                       lambda n: n["execute"]["outputs"].update(inventory="sha256:" + "a" * 64),
                       lambda n: n["route"]["outputs"].update(android_plan="sha256:" + "b" * 64),
                       lambda n: n["execute"]["outputs"].update(candidate="c" * 40)):
            altered = deepcopy(needs)
            change(altered)
            with self.assertRaises(ValueError): gate.verify_inner(altered, expected)
        # The required outer aggregate cannot silently omit its Android owner.
        baseline = {name: {"result": "skipped"} for name in ("project", "workflow-security", "native")}
        baseline.update(route={"result": "success", "outputs": {"mode": "documentation", "security": "false", "native": "skip", **gate.outputs(expected)}},
                        documentation={"result": "success"}, android=executed)
        self.assertEqual(checks.verify(baseline, require_native=False, android_plan=expected, require_android=True)["status"], "PASS")
        del baseline["android"]
        with self.assertRaises(ValueError): checks.verify(baseline, require_native=False, android_plan=expected, require_android=True)

    def test_real_trusted_controller_runs_complete_union_once_and_requires_all_cases(self):
        self.workflow_files()
        expected = self.merge()
        self.fixture.active_items = gate.android().plan(self.candidate, "android-phone", views=expected["views"])["executions"]
        with patch.object(gate, "ACTIVATION_READY", True), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = gate.run(self.candidate, self.event, self.sha, event_name="pull_request", policy_root=self.policy_root,
                receipt_path=self.temporary / "execution.json", reports=self.temporary / "reports",
                expected_outputs=gate.outputs(expected), run_command=self.fixture.run_command, capture=ownership.runtime)
        self.assertEqual(result, gate.receipt(expected))
        self.assertEqual(len(self.fixture.calls), 40)
        self.assertEqual(len(set(self.fixture.calls)), 40)
        actual = json.loads((self.temporary / "execution.json").read_text())
        self.assertEqual(len(actual["executions"]["phone-robolectric-launcher"]["cases"]), 116)
        self.assertEqual(actual["conclusion"], "success")
        tampered = gate.outputs(expected) | {"android_inventory": "sha256:" + "0" * 64}
        with patch.object(gate, "ACTIVATION_READY", True), self.assertRaises(ValueError):
            gate.run(self.candidate, self.event, self.sha, event_name="pull_request", policy_root=self.policy_root,
                receipt_path=self.temporary / "bad.json", reports=self.temporary / "bad", expected_outputs=tampered)

    def test_deleted_current_phone_focus_class_cannot_reduce_mandatory_inventory(self):
        path = self.candidate / "android/phone/apps/phoneInterface/src/test/java/org/overte/phone/PhoneEmbeddedWebFocusRobolectricTest.java"
        path.unlink()
        self.fixture.commit()
        with self.assertRaisesRegex(ValueError, "missing"):
            gate.android().plan(self.candidate, "android-phone", views=["coverage"])

    def test_pinned_quality_tools_use_only_external_trusted_layout_and_effective_context(self):
        runtime = gate.android()._shared()[1]
        venv = self.temporary / "venv"
        quality = venv / "overte-static-quality"
        for relative, version in (("bin/shellcheck", "ShellCheck - shell script analysis tool\nversion: 0.11.0"),
                                  ("ruff-venv/bin/ruff", "ruff 0.15.22")):
            path = quality / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/sh\nprintf '%s\\n' '" + version + "'\n")
            path.chmod(0o755)
        owner = gate.android()
        with patch.object(owner.sys, "prefix", str(venv)):
            identity = owner._quality_identity(runtime)
            self.assertEqual(identity["ruff"]["version"], "ruff 0.15.22")
            with patch.dict(os.environ, {"OVERTE_STATIC_QUALITY_TOOLS_DIR": "/candidate/evil"}):
                with owner.process_environment(self.temporary / "report"):
                    self.assertEqual(os.environ["OVERTE_STATIC_QUALITY_TOOLS_DIR"], str(quality))
                self.assertEqual(os.environ["OVERTE_STATIC_QUALITY_TOOLS_DIR"], "/candidate/evil")
            (quality / "bin/shellcheck").write_text("#!/bin/sh\nprintf 'version: 0.10.0\\n'\n")
            with self.assertRaises(ValueError): owner._quality_identity(runtime)
        for name in ("quality", "gcovr"):
            identity = ownership.runtime()
            del identity[name]
            with self.assertRaises(ValueError): owner.validate_environment(identity)

    def test_canonical_workflow_routes_before_setup_and_runs_only_trusted_full_union(self):
        template = (ROOT / gate.CALLEE).read_text()
        value = yaml.safe_load(template)
        jobs = value["jobs"]
        self.assertEqual(set(jobs), {"route", "execute", "verify"})
        self.assertEqual(jobs["execute"]["if"], "needs.route.outputs.android_required == 'true'")
        self.assertEqual(jobs["verify"]["if"], "always()")
        self.assertEqual(jobs["verify"]["needs"], ["route", "execute"])
        self.assertNotIn("setup-", json.dumps(jobs["route"]))
        self.assertNotIn("setup-", json.dumps(jobs["verify"]))
        self.assertIn("java-version: 21", template)
        self.assertIn("node-version: 22", template)
        self.assertIn('android-host-prepare.sh "$RUNNER_TEMP/android-host-venv"', template)
        self.assertIn('"$RUNNER_TEMP/android-host-venv/bin/python" trusted/tools/repository-checks/android_gate.py run', template)
        self.assertNotIn("./candidate/", template)
        self.assertNotIn("continue-on-error", template)
        for step in jobs["execute"]["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                self.assertFalse(step["with"]["persist-credentials"])
        prepare = (ROOT / "tools/repository-checks/android-host-prepare.sh").read_text()
        self.assertIn("gcovr==8.4", prepare)
        self.assertIn("--require-hashes", prepare)
        self.assertIn("sha256sum --check --status", prepare)
        self.assertNotIn("candidate", "\n".join(line for line in prepare.splitlines() if not line.startswith("#")))


if __name__ == "__main__":
    unittest.main()
