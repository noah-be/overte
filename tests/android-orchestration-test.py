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
import tarfile
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
                 "tools/repository-checks/host_selection.py",
                 *gate.android().EXECUTION_FILES]
        names += [".github/android-owner-transfer.json", "tools/repository-checks/android_handoff.py",
                  "tools/repository-checks/workflows/browser-client.yml", "tools/repository-checks/workflows/browser-direct-client.yml",
                  "tools/repository-checks/workflows/npm-consumers/browser-client.yml"]
        names += [str(path.relative_to(ROOT)) for path in (ROOT / gate.OWNED).rglob("*") if path.is_file()]
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

    def workflow_files(self, *, direct=False, producer=False, owned=True, browser=False):
        packages = gate.packages()
        name = ("shared-receipt-v1" if producer else "packages-v1") + ("-direct" if direct else "") + "-android"
        if owned:
            name = "android-owned-npm5-sync-ci-v1"
        generation = next(item for item in packages.workflow_generations() if item["name"] == name)
        paths = list((ROOT / "tools/repository-checks/workflows").rglob("*.yml"))
        contents = {gate._blob(path.read_bytes())["sha"]: path.read_bytes() for path in paths}
        for relative, entry in generation["workflows"].items():
            target = self.candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents[entry["sha"]])
        callee = gate.OWNED + "/android-required.yml" if owned else gate.CALLEE
        (self.candidate / gate.WORKFLOW).write_bytes((ROOT / callee).read_bytes())
        if owned:
            if direct:
                (self.candidate / ".github/workflows/browser-direct-client.yml").write_bytes(
                    (ROOT / "tools/repository-checks/workflows/browser-direct-client.yml").read_bytes())
            transfer = gate.handoff().policy()
            for group in ("legacy_workflows", "source_contracts"):
                for target, item in transfer[group].items():
                    path = self.candidate / target
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((ROOT / item["source"]).read_bytes())
                    path.chmod(0o755 if item["mode"] == "100755" else 0o644)
            profile = {"schema": 1, "platform": "android", "suites": transfer["profiles"]["android-phone"]["required_suites"]}
            path = self.candidate / "tests/platform-profile.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(profile))
            for item in profile["suites"]:
                entrypoint = self.candidate / item["entrypoint"]
                if not entrypoint.exists():
                    entrypoint.parent.mkdir(parents=True, exist_ok=True)
                    entrypoint.write_text("# Profile fixture.\n")
        self.fixture.commit()
        return generation

    def merge(self, relative="android/phone/changed.cpp", contents="// changed\n", *, empty=False, mode=None, rename_from=None,
              additional=None):
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
                path.unlink(missing_ok=True)
                path.symlink_to("outside")
            elif contents is None:
                path.unlink()
            else:
                path.write_text(contents)
                if mode is not None: path.chmod(mode)
            for name, value in (additional or {}).items():
                extra = self.candidate / name
                extra.parent.mkdir(parents=True, exist_ok=True)
                extra.write_text(value)
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

    def lock_sources(self):
        """Actual reviewed package trees and caller wiring; no npm execution."""
        self.workflow_files()
        packages = gate.packages()
        archive = subprocess.check_output([
            "git", "archive", "--format=tar", "HEAD", "--", packages.BROWSER, packages.S3,
        ], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            for member in contents:
                destination = self.candidate / member.name
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    self.assertTrue(member.isfile())
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(contents.extractfile(member).read())
                    destination.chmod(member.mode)
        consumers = packages.load("android_lock_fixture_consumers", "tools/repository-checks/npm_consumers.py")
        self.consumer_policies = consumers.PROJECTS
        for project, policy in self.consumer_policies.items():
            target = self.candidate / project / "package-lock.json"
            value = json.loads(target.read_text())
            value["packages"][policy["node"]] = policy["old"]
            target.write_text(json.dumps(value) + "\n")
        (self.candidate / gate.POLICY).write_bytes((ROOT / gate.POLICY).read_bytes())
        self.fixture.commit()

    def lock_anchor(self):
        sources = gate._sources(self.candidate)
        self.policy["reviewed_lock_sources"]["android-phone"] = {
            "commit": self.git("rev-parse", "HEAD"), "tree": self.git("rev-parse", "HEAD^{tree}"),
            "readers": gate.lock_reader_identity(sources.entries),
            "entries": len(sources.entries) - len(gate.FOREIGN_LOCKS),
        }
        self.write_policy()

    def updated_lock(self, relative, *, unsupported=False, formatting=False):
        value = json.loads((self.candidate / relative).read_text())
        if not formatting:
            policy = self.consumer_policies[str(Path(relative).parent)]
            value["packages"][policy["node"]] = deepcopy(policy["new"])
            if unsupported:
                value["packages"][policy["node"]]["version"] = "99.0.0"
        return json.dumps(value, indent=4) + "\n"

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

    def test_exact_lock_updates_recompute_actual_mandatory_npm_owners(self):
        self.lock_sources()
        self.lock_anchor()
        for path, formatting in (("browser-client/package-lock.json", True),
                                 ("browser-client/package-lock.json", False),
                                 ("script-archive/marketplace/S3Server/package-lock.json", False)):
            with self.subTest(path=path, formatting=formatting):
                result = self.merge(path, self.updated_lock(path, formatting=formatting))
                self.assertFalse(result["required"])
                self.assertEqual(result["reason"], "reviewed-package-lock-inputs")
                self.assertEqual(result["views"], [])
                expected = gate.packages().candidate_plan(self.candidate, self.event, self.sha)
                self.assertEqual(result["lock_package_plan"], expected["plan"])
                selected = expected["dependency_profiles"]["projects"][str(Path(path).parent)]
                self.assertEqual(selected["required"], not formatting)
                sparse = self.fixture.sparse_clone("lock-sparse-" + str(self.sequence))
                self.assertEqual(gate.candidate_plan(sparse, self.event, self.sha, policy_root=self.policy_root), result)

    def test_two_lock_delta_retains_both_separate_package_owners(self):
        self.lock_sources()
        self.lock_anchor()
        browser, s3 = "browser-client/package-lock.json", "script-archive/marketplace/S3Server/package-lock.json"
        result = self.merge(browser, self.updated_lock(browser), additional={s3: self.updated_lock(s3)})
        self.assertFalse(result["required"])
        package = gate.packages().candidate_plan(self.candidate, self.event, self.sha)
        self.assertEqual(set(package["package_set"]), {"browser-client", "script-archive/marketplace/S3Server"})
        self.assertEqual(result["lock_package_plan"], package["plan"])

    def test_lock_reader_projection_binds_every_other_root_and_policy_membership(self):
        self.lock_sources()
        original = gate._sources(self.candidate).entries
        expected = gate.lock_reader_identity(original)
        policy_bytes = deepcopy(original)
        policy_bytes[gate.POLICY]["sha"] = "e" * 40
        self.assertEqual(gate.lock_reader_identity(policy_bytes), expected)
        for relative in (*[root + "new-reader.py" for root in gate.INDEPENDENT_ROOTS],
                         "android/common/tests/javascript/package-lock.json", "package.json",
                         "scripts/new-lock-reader.js", "tests/new-lock-reader.py"):
            changed = deepcopy(original)
            changed[relative] = gate._blob(b"new consumer\n")
            with self.subTest(relative=relative):
                self.assertNotEqual(gate.lock_reader_identity(changed), expected)
        for mode in (None, "100755", "120000", "160000"):
            changed = deepcopy(original)
            if mode is None:
                del changed[gate.POLICY]
            else:
                changed[gate.POLICY].update(mode=mode, type="commit" if mode == "160000" else "blob")
            with self.subTest(policy_mode=mode), self.assertRaises(ValueError):
                gate.lock_reader_identity(changed)
        before = gate._policy_identity(self.policy_root)
        self.policy["required_branches"] = []
        self.write_policy()
        self.assertNotEqual(gate._policy_identity(self.policy_root), before)

    def test_lock_omission_requires_new_anchor_and_hermetic_base_without_old_root_fallthrough(self):
        self.lock_sources()
        self.anchor()  # A legacy Browser-root anchor cannot authorize this route.
        browser = "browser-client/package-lock.json"
        self.assertTrue(self.merge(browser, self.updated_lock(browser))["required"])
        old = subprocess.check_output(["git", "cat-file", "blob",
            "de670465b44ca7be8d550274acbe92bdfc9e7acc"], cwd=ROOT)
        (self.candidate / gate.HERMETIC_METADATA_TEST).write_bytes(old)
        self.fixture.commit()
        self.lock_anchor()  # Even a matching anchor cannot review the old archive reader.
        self.anchor()
        result = self.merge(browser, (self.candidate / browser).read_text() + "\n")
        self.assertTrue(result["required"])
        self.assertIsNone(result["lock_package_plan"])

    def test_nonordinary_lock_entries_missing_inputs_and_unknown_npm_keep_complete_union(self):
        self.lock_sources()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        supported = self.updated_lock(browser)
        for mutation in ("unsupported", "malformed", "mode", "symlink", "delete", "missing-base", "executable-base"):
            with self.subTest(mutation=mutation):
                self.git("reset", "--hard", base)
                target = self.candidate / browser
                if mutation == "missing-base":
                    target.unlink()
                    self.fixture.commit()
                elif mutation == "executable-base":
                    target.chmod(0o755)
                    self.fixture.commit()
                self.lock_anchor()
                self.anchor()
                contents, mode = supported, None
                if mutation == "unsupported": contents = self.updated_lock(browser, unsupported=True)
                elif mutation == "malformed": contents = '{"unexpected":true}\n'
                elif mutation == "mode": mode = 0o755
                elif mutation == "symlink": mode = "symlink"
                elif mutation == "delete": contents = None
                elif mutation == "executable-base": mode = 0o644
                result = self.merge(browser, contents, mode=mode)
                self.assertTrue(result["required"])
                self.assertIsNone(result["lock_package_plan"])
                self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=result["views"])["executions"]), 40)

    def test_lock_plus_policy_consumer_or_ancestor_changes_keep_complete_union(self):
        self.lock_sources()
        self.lock_anchor()
        self.anchor()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        for relative in (gate.POLICY, "browser-client/new-consumer.js", "package.json",
                         "android/common/tests/javascript/package-lock.json"):
            with self.subTest(relative=relative):
                self.git("reset", "--hard", base)
                value = (self.candidate / gate.POLICY).read_text() + "\n" if relative == gate.POLICY else "{}\n"
                result = self.merge(browser, self.updated_lock(browser), additional={relative: value})
                self.assertTrue(result["required"])
                self.assertIsNone(result["lock_package_plan"])

    def test_historical_reader_or_other_npm_graph_difference_cannot_use_lock_anchor(self):
        self.lock_sources()
        self.lock_anchor()
        base = self.git("rev-parse", "HEAD")
        browser = "browser-client/package-lock.json"
        for relative in ("tools/issue-intake/new-lock-reader.py", "scripts/new-lock-reader.js",
                         "browser-client/new-consumer.js"):
            with self.subTest(relative=relative):
                self.git("reset", "--hard", base)
                target = self.candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# historical difference outside the event delta\n")
                self.fixture.commit()
                self.assertTrue(self.merge(browser, self.updated_lock(browser))["required"])

    def test_lock_only_diagnostics_and_manual_events_retain_extended_inventories(self):
        self.lock_sources()
        self.lock_anchor()
        browser = "browser-client/package-lock.json"
        self.assertFalse(self.merge(browser, self.updated_lock(browser))["required"])
        self.event["pull_request"]["labels"] = [{"name": "android-long-diagnostics"}]
        labelled = self.plan()
        self.assertTrue(labelled["required"])
        self.assertIsNone(labelled["lock_package_plan"])
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=labelled["views"])["executions"]), 45)
        event = {"repository": self.event["repository"], "ref": "refs/heads/android-phone"}
        manual = gate.candidate_plan(self.candidate, event, self.sha, event_name="workflow_dispatch", policy_root=self.policy_root)
        self.assertTrue(manual["required"])
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=manual["views"])["executions"]), 45)
        complete = list(gate.android().VIEWS) + list(gate.android().DIAGNOSTIC_VIEWS)
        self.assertEqual(len(gate.android().plan(self.candidate, "android-phone", views=complete)["executions"]), 46)

    def test_lock_omission_rejects_recomputed_package_identity_and_owner_tampering(self):
        self.lock_sources()
        self.lock_anchor()
        browser = "browser-client/package-lock.json"
        self.assertFalse(self.merge(browser, self.updated_lock(browser))["required"])
        packages = gate.packages()
        expected = packages.candidate_plan(self.candidate, self.event, self.sha)
        for mutation in ("candidate", "base", "head", "tree", "paths", "unknown", "regular", "owner", "generation"):
            changed = deepcopy(expected)
            if mutation in ("candidate", "base", "head", "tree"): changed[mutation] = "c" * 40
            elif mutation == "paths": changed["paths"] = []
            elif mutation in ("unknown", "regular"): changed[mutation] = mutation == "unknown"
            elif mutation == "owner": changed["package_set"] = []
            else: changed["consumer_generation"] = False
            with self.subTest(mutation=mutation), patch.object(gate, "packages", return_value=packages), \
                    patch.object(packages, "candidate_plan", return_value=changed):
                self.assertTrue(self.plan()["required"])
        (self.candidate / browser).write_text("dirty working tree\n")
        with self.assertRaises(ValueError): self.plan()

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
        self.assertEqual(manual["views"], list(ownership.android.DEFAULT_VIEWS) + list(ownership.android.DIAGNOSTIC_VIEWS))
        self.assertNotIn("mutation", manual["views"])
        self.assertNotIn("stability", result["views"])
        self.assertNotIn("endurance", result["views"])

    def test_complete_old_and_new_package_tuples_remain_approved_but_mixed_android_callee_fails(self):
        for direct, producer in ((False, False), (False, True), (True, False), (True, True)):
            generation = self.workflow_files(direct=direct, producer=producer, owned=False)
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
        with self.assertRaisesRegex(ValueError, "not qualified"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        with patch.object(gate, "ACTIVATION_READY", True):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)
        self.policy["activation_blockers"] = ["extended-tier-prerequisite-transfer"]
        self.write_policy()
        with self.assertRaisesRegex(ValueError, "extended-tier-prerequisite-transfer"):
            gate.admit(self.candidate, self.event, policy_root=self.policy_root)

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
                       lambda p: p["reviewed_lock_sources"].pop("android-vr"),
                       lambda p: p["reviewed_lock_sources"]["android-phone"].update(entries=True),
                       lambda p: p["reviewed_lock_sources"]["android-phone"].update(readers="sha256:unknown"),
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
