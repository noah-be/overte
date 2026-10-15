#!/usr/bin/env python3
"""Real-Git regressions for dormant trusted Browser CPU-history selection."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/repository-checks/browser_cpu.py"
SPEC = importlib.util.spec_from_file_location("browser_cpu_selection", HELPER)
BROWSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BROWSER)
def reviewed_legacy_fixture():
    """Recover the immutable reviewed fixture without assuming activation state."""
    current = BROWSER.canonical_workflow().decode()
    assert current.count('jobs:\n') == current.count('  browser:\n') == current.count('\n  verify:\n') == 1
    legacy = (current[:current.index('jobs:\n') + len('jobs:\n')]
              + current[current.index('  browser:\n'):current.index('\n  verify:\n')])
    selection = "    needs: route\n    if: needs.route.outputs.mode == 'full'\n"
    assert legacy.count(selection) == 2
    legacy = legacy.replace(selection, '')
    audit = ("      - name: Audit changed browser package inputs\n"
             "        if: needs.route.outputs.audit == 'true'\n"
             "        run: npm audit --audit-level=high\n")
    assert legacy.count(audit) == 1
    legacy = legacy.replace(audit, '')
    start, end = legacy.index('  workflow_call:\n'), legacy.index('  workflow_dispatch:\n')
    legacy = (legacy[:start] + "  pull_request:\n    paths:\n      - 'browser-client/**'\n      - '.github/workflows/browser-client.yml'\n" + legacy[end:]).encode()
    assert BROWSER._blob(legacy) == BROWSER.REVIEWED_WORKFLOW
    return legacy


LEGACY = reviewed_legacy_fixture()


def reviewed_outer_fixture(template=None):
    """Reverse only the exact approved addition; never read mutable active bytes."""
    current = (template if template is not None else BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE)).decode()
    additions = (
        "      browser_mode: ${{ steps.plan.outputs.browser_mode }}\n"
        "      browser_candidate: ${{ steps.plan.outputs.browser_candidate }}\n"
        "      browser_plan: ${{ steps.plan.outputs.browser_plan }}\n",
        "  browser-client:\n    needs: route\n"
        "    if: needs.route.outputs.browser_mode == 'cpu' || needs.route.outputs.browser_mode == 'full'\n"
        "    uses: ./.github/workflows/browser-client.yml\n    with:\n"
        "      expected_candidate: ${{ needs.route.outputs.browser_candidate }}\n"
        "      expected_plan: ${{ needs.route.outputs.browser_plan }}\n",
        "    - browser-client\n",
    )
    for addition in additions:
        assert current.count(addition) == 1
        current = current.replace(addition, '', 1)
    value = current.encode()
    assert BROWSER._blob(value) == '81400ce4f8ce5eee1a7d95976378bc03e2d6fb05' == BROWSER.REVIEWED_OUTER
    return value


LEGACY_OUTER = reviewed_outer_fixture()
REAL_BOUNDARY = BROWSER.REVIEWED_BOUNDARY
REAL_BROWSER_BOUNDARY = BROWSER.REVIEWED_BROWSER_BOUNDARY


class BrowserCpuTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Browser selection fixture")
        self.git("config", "user.email", "browser-selection@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("CMakeLists.txt", b"project(BrowserFixture)\n")
        self.write("browser-client/package.json", b'{"scripts":{"test":"node --test"}}\n')
        self.write("browser-client/package-lock.json", b'{"lockfileVersion":3}\n')
        self.write("browser-client/src/Main.ts", b"export const production = true;\n")
        self.write(BROWSER.WORKFLOW, LEGACY)
        self.write(BROWSER.OUTER_WORKFLOW, LEGACY_OUTER)
        configuration = json.loads(BROWSER.trusted_bytes(BROWSER.CONFIGURATION))
        configuration['browser_client_required_branches'] = []
        self.write(BROWSER.CONFIGURATION, (json.dumps(configuration, indent=2) + '\n').encode())
        for path in BROWSER.CPU_PATHS:
            self.write(path, b"Reviewed CPU fixture source\n")
        self.base = self.commit("Create isolated reviewed Browser readers")
        # Explicit isolated fixture review; never refresh production anchors.
        reviewed = BROWSER.review_boundary(self.root, self.base)
        anchor = reviewed["boundary"]
        replacement = patch.object(BROWSER, "REVIEWED_BOUNDARY", anchor)
        replacement.start()
        self.addCleanup(replacement.stop)
        browser_anchor = patch.object(BROWSER, 'REVIEWED_BROWSER_BOUNDARY', reviewed['browser_boundary'])
        browser_anchor.start()
        self.addCleanup(browser_anchor.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=True, check=True, timeout=30).stdout.strip()

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message, *, stage=True):
        if stage:
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def classify(self, candidate, base=None):
        return BROWSER.classify(BROWSER.snapshot(self.root, base or self.base),
                                BROWSER.snapshot(self.root, candidate))

    def activate_fixture(self):
        self.write(BROWSER.WORKFLOW, BROWSER.canonical_workflow())
        self.write(BROWSER.OUTER_WORKFLOW, BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE))
        self.base = self.commit("Integrate exact reviewed fixture orchestration")

    def merge(self, changes, *, base=None):
        base = base or self.base
        self.git("checkout", "-q", "--detach", base)
        for path, data in changes.items():
            self.write(path, data)
        head = self.commit("Change reviewed fixture inputs")
        self.git("checkout", "-q", "-B", "merge-fixture", base)
        self.git("merge", "-q", "--no-ff", "-m", "Merge exact browser fixture", head)
        candidate = self.git("rev-parse", "HEAD")
        event = {"repository": dict(BROWSER.REPOSITORY), "pull_request": {
            "base": {"repo": dict(BROWSER.REPOSITORY), "ref": "main", "sha": base},
            "head": {"repo": dict(BROWSER.REPOSITORY), "ref": "fix/main/cpu-fixture", "sha": head}}}
        return event, candidate

    def needs(self, outputs):
        cpu = outputs["mode"] == "cpu"
        return {"route": {"result": "success", "outputs": deepcopy(outputs)},
                "cpu": {"result": "success" if cpu else "skipped"},
                "browser": {"result": "success" if outputs["mode"] == "full" else "skipped"},
                "native-journey": {"result": "success" if outputs["mode"] == "full" else "skipped"}}

    def test_all_twelve_exact_cpu_inputs_and_approved_bootstrap_select_cpu(self):
        changes = {path: b"Updated exact CPU history source\n" for path in BROWSER.CPU_PATHS}
        changes[BROWSER.WORKFLOW] = BROWSER.canonical_workflow()
        changes[BROWSER.OUTER_WORKFLOW] = BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE)
        config = json.loads(BROWSER.trusted_bytes(BROWSER.CONFIGURATION))
        config['browser_client_required_branches'] = ['main']
        changes[BROWSER.CONFIGURATION] = (json.dumps(config, indent=2) + '\n').encode()
        event, candidate = self.merge(changes)
        selection = self.classify(candidate)
        self.assertEqual(selection["mode"], "cpu")
        self.assertEqual(selection["reason"], "approved-workflow-bootstrap-and-cpu-history")
        self.assertEqual(len(selection["changes"]), 15)
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        self.assertEqual(outputs["mode"], "cpu")
        self.assertEqual(outputs["audit"], "false")
        self.assertEqual(BROWSER.verify(event, "pull_request", self.root, candidate, self.needs(outputs)),
                         {"candidate": candidate, "plan": outputs["plan"], "verified": "true"})

    def test_only_exact_workflow_bootstrap_bytes_can_be_admitted(self):
        event, candidate = self.merge({BROWSER.WORKFLOW: BROWSER.canonical_workflow()})
        self.assertEqual(self.classify(candidate)["mode"], "full")
        with self.assertRaisesRegex(ValueError, "paired"):
            BROWSER.route(event, "pull_request", self.root, candidate)
        for workflow in (LEGACY + b"\n# Unknown workflow\n", BROWSER.canonical_workflow() + b"\n# Candidate skip\n"):
            event, candidate = self.merge({BROWSER.WORKFLOW: workflow, next(iter(BROWSER.CPU_PATHS)): b"Updated\n"})
            self.assertEqual(self.classify(candidate)["mode"], "full")
            with self.assertRaisesRegex(ValueError, "trusted canonical"):
                BROWSER.route(event, "pull_request", self.root, candidate)

    def test_regular_cpu_only_changes_are_git_data_never_imported(self):
        self.activate_fixture()
        event, candidate = self.merge({path: b"throw new Error('candidate must never execute in router');\n"
                                       for path in BROWSER.CPU_PATHS})
        self.assertEqual(self.classify(candidate)["mode"], "cpu")
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate)["mode"], "cpu")

    def test_other_mixed_unknown_package_and_product_inputs_stay_full(self):
        self.activate_fixture()
        cpu = next(iter(BROWSER.CPU_PATHS))
        for path in ("browser-client/src/Main.ts", "browser-client/package.json", "browser-client/package-lock.json",
                     "browser-client/vite.config.mjs", "browser-client/native-input/Input.cpp",
                     "browser-client/tests/new.test.mjs", "browser-client/tests/fixtures/unknown.json",
                     "browser-client/lab/manage.py", "browser-client/tools/trusted-network/src/launcher.c",
                     "browser-client/gateway/server.mjs", "cmake/compiler.cmake", "new/unknown",
                     "tools/repository-checks/browser_cpu.py"):
            with self.subTest(path=path):
                event, candidate = self.merge({cpu: b"CPU change\n", path: b"Other or unknown input\n"})
                outputs = BROWSER.route(event, "pull_request", self.root, candidate)
                self.assertEqual(outputs["mode"], "full")
                self.assertEqual(outputs["audit"], str(path in BROWSER.PACKAGE_PATHS).lower())
                BROWSER.verify(event, "pull_request", self.root, candidate, self.needs(outputs))

    def test_missing_selected_results_skips_and_earlier_failures_cannot_green(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for name in BROWSER.JOBS:
            for status in (None, "failure", "cancelled", "timed_out", "pending", "neutral"):
                with self.subTest(job=name, status=status):
                    needs = self.needs(outputs)
                    needs[name]["result"] = status
                    with self.assertRaises(ValueError):
                        BROWSER.verify(event, "pull_request", self.root, candidate, needs)
            needs = self.needs(outputs)
            del needs[name]
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)
        needs = self.needs(outputs)
        needs["cpu"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            BROWSER.verify(event, "pull_request", self.root, candidate, needs)
        # Unselected heavy-job failures also remain failures; never hide them
        # behind a later CPU selection or failed-only rerun's retained result.
        for name in ("browser", "native-journey"):
            needs = self.needs(outputs)
            needs[name]["result"] = "failure"
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_full_route_requires_both_existing_heavy_jobs(self):
        self.activate_fixture()
        event, candidate = self.merge({"browser-client/src/Main.ts": b"Production change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for name in ("browser", "native-journey"):
            needs = self.needs(outputs)
            needs[name]["result"] = "skipped"
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_forged_plan_mode_audit_tree_and_candidate_cannot_replace_recomputation(self):
        self.activate_fixture()
        event, candidate = self.merge({"browser-client/src/Main.ts": b"Production change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for field, value in (("mode", "cpu"), ("audit", "true"), ("tree", "f" * 40),
                             ("candidate", self.base), ("plan", "sha256:" + "0" * 64), ("base", "")):
            needs = self.needs(outputs)
            needs["route"]["outputs"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_repository_merge_parent_head_and_checkout_are_independent(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        for side, field, value in (("repository", "full_name", "overte-org/overte"),
                                  ("repository", "id", 42), ("base", "sha", "f" * 40),
                                  ("head", "sha", self.base)):
            changed = deepcopy(event)
            target = changed["repository"] if side == "repository" else changed["pull_request"][side]
            target[field] = value
            with self.subTest(side=side, field=field), self.assertRaises(ValueError):
                BROWSER.route(changed, "pull_request", self.root, candidate)
        with self.assertRaises(ValueError):
            BROWSER.route(event, "pull_request", self.root, event["pull_request"]["head"]["sha"])
        with self.assertRaises(ValueError):
            BROWSER.route(event, "pull_request_target", self.root, candidate)

    def test_reader_then_cpu_changes_stay_full_without_automatic_anchor_refresh(self):
        self.activate_fixture()
        self.write("CMakeLists.txt", b"file(READ browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs APP_INPUT)\n")
        integrated = self.commit("Integrate a new reader of a formerly independent fixture")
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"Later CPU source change\n"}, base=integrated)
        selection = self.classify(candidate, integrated)
        self.assertEqual(selection["mode"], "full")
        self.assertEqual(selection["reason"], "reader-boundary-not-reviewed")
        self.assertNotEqual(selection["base_boundary"], BROWSER.REVIEWED_BOUNDARY)
        self.assertNotEqual(selection["candidate_boundary"], BROWSER.REVIEWED_BOUNDARY)
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate)["mode"], "full")

    def test_modes_symlinks_and_gitlinks_anywhere_disable_cpu_selection(self):
        self.activate_fixture()
        path = next(iter(BROWSER.CPU_PATHS))
        self.write(path, b"CPU mode-only change\n")
        (self.root / path).chmod(0o755)
        mode = self.commit("Make a CPU input executable")
        self.assertEqual(self.classify(mode)["mode"], "full")
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "source-link").symlink_to(path)
        linked = self.commit("Add a source alias")
        anchor = BROWSER.review_boundary(self.root, linked)["boundary"]
        self.write(path, b"Changed through unchanged alias\n")
        later = self.commit("Change alias referent")
        with patch.object(BROWSER, "REVIEWED_BOUNDARY", anchor):
            self.assertEqual(self.classify(later, linked)["mode"], "full")
        self.git("checkout", "-q", "--detach", self.base)
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",vendor/dependency")
        gitlink = self.commit("Add uninspected submodule", stage=False)
        self.assertEqual(self.classify(gitlink)["mode"], "full")

    def test_deletion_rename_and_new_history_path_are_not_lost(self):
        self.activate_fixture()
        paths = sorted(BROWSER.CPU_PATHS)
        (self.root / paths[0]).unlink()
        deleted = self.commit("Delete exact CPU input")
        self.assertEqual(self.classify(deleted)["mode"], "cpu")
        self.git("checkout", "-q", "--detach", self.base)
        self.git("mv", paths[0], paths[0] + ".unknown")
        renamed = self.commit("Rename CPU input into unknown path")
        selection = self.classify(renamed)
        self.assertEqual(selection["mode"], "full")
        self.assertEqual(len(selection["changes"]), 2)

    def test_worktree_index_and_replacement_refs_cannot_supply_candidate(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        expected = BROWSER.route(event, "pull_request", self.root, candidate)
        self.write("browser-client/src/Main.ts", b"Staged local production change\n")
        self.git("add", "browser-client/src/Main.ts")
        self.write(BROWSER.WORKFLOW, b"Unstaged candidate orchestration\n")
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate), expected)
        self.git("reset", "--hard", "-q", candidate)
        self.write("browser-client/src/Main.ts", b"Replacement production bytes\n")
        replacement = self.commit("Create replacement object")
        self.git("replace", candidate, replacement)
        self.git("checkout", "-q", "--detach", candidate)
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate), expected)

    def test_empty_unknown_and_truncated_inventory_cannot_select_cpu(self):
        self.assertEqual(self.classify(self.base)["mode"], "full")
        for value in ("HEAD", "0" * 40, "a" * 39, None):
            with self.subTest(revision=value), self.assertRaises((ValueError, subprocess.SubprocessError)):
                BROWSER.snapshot(self.root, value)
        original = BROWSER.git
        def truncated(repository, *args):
            return b"100644 blob " + b"a" * 40 + b"\tREADME.md" if args[0] == "ls-tree" else original(repository, *args)
        with patch.object(BROWSER, "git", side_effect=truncated), self.assertRaises(ValueError):
            BROWSER.snapshot(self.root, self.base)

    def test_manual_dispatch_preserves_full_scope_and_diagnostics_are_not_required_proof(self):
        self.activate_fixture()
        event = {"repository": dict(BROWSER.REPOSITORY), "ref": "refs/heads/main", "inputs": {"startup_diagnostics": "true"}}
        with patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch'}):
            outputs = BROWSER.route(event, "workflow_dispatch", self.root, self.base)
            self.assertEqual(outputs["mode"], "full")
            self.assertEqual(BROWSER.verify(event, "workflow_dispatch", self.root, self.base, self.needs(outputs))["verified"],
                             "diagnostic-only")

    def test_each_actual_external_source_reader_requires_full_browser_validation(self):
        self.activate_fixture()
        self.assertEqual(len(BROWSER.EXTERNAL_INPUTS), 29)
        for path in sorted(BROWSER.EXTERNAL_INPUTS):
            with self.subTest(path=path):
                event, candidate = self.merge({path: b'Changed actual external Browser input\n'})
                outputs = BROWSER.route(event, 'pull_request', self.root, candidate)
                self.assertEqual(outputs['mode'], 'full')
                BROWSER.verify(event, 'pull_request', self.root, candidate, self.needs(outputs))

    def test_known_independent_native_host_and_documentation_changes_skip_all_browser_jobs(self):
        self.activate_fixture()
        for path in ('libraries/shared/src/Other.cpp', 'CMakeLists.txt', 'docs/unrelated.md',
                     'tools/release/unrelated.py', 'tests/unrelated-test.py', 'server-console/index.js'):
            with self.subTest(path=path):
                event, candidate = self.merge({path: b'Independent repository input\n'})
                outputs = BROWSER.route(event, 'pull_request', self.root, candidate)
                self.assertEqual(outputs['mode'], 'skip')
                self.assertTrue(all(value['result'] == 'skipped' for name, value in self.needs(outputs).items() if name != 'route'))
                BROWSER.verify(event, 'pull_request', self.root, candidate, self.needs(outputs))
                BROWSER.verify_outer({'result': 'skipped', 'outputs': {}}, BROWSER.outer_outputs(outputs), outputs)

    def test_later_independent_edits_cannot_skip_after_any_browser_or_cpu_reader_change(self):
        self.activate_fixture()
        for reader in ('browser-client/src/Main.ts', next(iter(BROWSER.CPU_PATHS))):
            self.git('checkout', '-q', '--detach', self.base)
            self.write(reader, b'Reader now consumes libraries/shared/src/Other.cpp\n')
            integrated = self.commit('Integrate an unreviewed reader')
            event, candidate = self.merge({'libraries/shared/src/Other.cpp': b'Later external change\n'}, base=integrated)
            self.assertEqual(BROWSER.route(event, 'pull_request', self.root, candidate)['mode'], 'full')

    def test_target_ref_is_bound_even_when_seven_branches_share_the_same_base_commit(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b'CPU change\n'})
        branches = json.loads((ROOT / '.github/branch-policy.json').read_text())['branches']
        self.assertEqual(len(branches), 7)
        plans = set()
        for branch in branches:
            changed = deepcopy(event); changed['pull_request']['base']['ref'] = branch
            outputs = BROWSER.route(changed, 'pull_request', self.root, candidate)
            self.assertEqual(outputs['target'], branch); plans.add(outputs['plan'])
        self.assertEqual(len(plans), 7)

    def test_trusted_activation_uses_actual_base_push_or_manual_branch_and_ignores_candidate_settings(self):
        branches = json.loads((ROOT / '.github/branch-policy.json').read_text())['branches']
        original = BROWSER.trusted_bytes
        config = json.loads(original(BROWSER.CONFIGURATION)); config['browser_client_required_branches'] = ['main']
        def trusted(relative, policy_root=ROOT):
            return (json.dumps(config, indent=2) + '\n').encode() if relative == BROWSER.CONFIGURATION else original(relative, policy_root)
        with patch.object(BROWSER, 'trusted_bytes', side_effect=trusted):
            for branch in branches:
                payload = {'repository': dict(BROWSER.REPOSITORY), 'pull_request': {
                    'base': {'ref': branch, 'repo': dict(BROWSER.REPOSITORY)}, 'head': {'ref': 'main'}}}
                self.assertEqual(BROWSER.activated(payload, 'pull_request'), branch == 'main')
                self.assertEqual(BROWSER.required(None, payload, None, 'pull_request'), branch == 'main')
                for event_name in ('push', 'workflow_dispatch'):
                    payload = {'repository': dict(BROWSER.REPOSITORY), 'ref': 'refs/heads/' + branch}
                    with patch.dict('os.environ', {'GITHUB_REF': 'refs/heads/' + branch, 'GITHUB_REF_TYPE': 'branch'}):
                        self.assertEqual(BROWSER.activated(payload, event_name), branch == 'main')
            for ref in (None, 'main', 'refs/tags/main', 'refs/heads/', 'refs/heads/a..b', 'refs/heads/a//b'):
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    BROWSER.activated({'repository': dict(BROWSER.REPOSITORY), 'ref': ref}, 'push')
            foreign = {'repository': dict(BROWSER.REPOSITORY), 'pull_request': {
                'base': {'ref': 'main', 'repo': {'full_name': 'overte-org/overte', 'id': 42}}}}
            with self.assertRaises(ValueError): BROWSER.activated(foreign, 'pull_request')
            with patch.dict('os.environ', {'GITHUB_REF': 'refs/tags/main', 'GITHUB_REF_TYPE': 'tag'}), self.assertRaises(ValueError):
                BROWSER.activated({'repository': dict(BROWSER.REPOSITORY), 'ref': 'refs/heads/main'}, 'workflow_dispatch')
        self.assertFalse(BROWSER.activated({'repository': dict(BROWSER.REPOSITORY)}, 'workflow_dispatch'))

    def test_exact_paired_transfer_and_protected_base_prevent_partial_deployment_or_rollback(self):
        event, candidate = self.merge({BROWSER.WORKFLOW: BROWSER.canonical_workflow()})
        self.assertTrue(BROWSER.required(self.root, event, candidate, 'pull_request'))
        with self.assertRaisesRegex(ValueError, 'paired'):
            BROWSER.route(event, 'pull_request', self.root, candidate)
        self.activate_fixture()
        event, candidate = self.merge({BROWSER.WORKFLOW: LEGACY,
            BROWSER.OUTER_WORKFLOW: LEGACY_OUTER})
        self.assertTrue(BROWSER.required(self.root, event, candidate, 'pull_request'))
        with self.assertRaisesRegex(ValueError, 'canonical'):
            BROWSER.route(event, 'pull_request', self.root, candidate)

    def test_outer_required_receipt_rejects_missing_failure_diagnostic_and_forged_selection(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b'CPU change\n'})
        outputs = BROWSER.route(event, 'pull_request', self.root, candidate)
        receipt = {'candidate': candidate, 'plan': outputs['plan'], 'verified': 'true'}
        BROWSER.verify_outer({'result': 'success', 'outputs': receipt}, BROWSER.outer_outputs(outputs), outputs)
        for status in ('failure', 'cancelled', 'skipped', None):
            with self.assertRaises(ValueError): BROWSER.verify_outer({'result': status, 'outputs': receipt}, BROWSER.outer_outputs(outputs), outputs)
        for key, value in (('candidate', self.base), ('plan', 'forged'), ('verified', 'diagnostic-only')):
            forged = dict(receipt); forged[key] = value
            with self.assertRaises(ValueError): BROWSER.verify_outer({'result': 'success', 'outputs': forged}, BROWSER.outer_outputs(outputs), outputs)
        changed = BROWSER.outer_outputs(outputs); changed['browser_mode'] = 'skip'
        with self.assertRaises(ValueError): BROWSER.verify_outer({'result': 'success', 'outputs': receipt}, changed, outputs)

    def test_unselected_outer_receipts_accept_only_absent_or_known_empty_outputs(self):
        self.activate_fixture()
        event, candidate = self.merge({'docs/unrelated.md': b'Independent documentation\n'})
        plan = BROWSER.route(event, 'pull_request', self.root, candidate)
        self.assertEqual(plan['mode'], 'skip')
        for outputs in ({}, {'candidate': '', 'plan': '', 'verified': ''}):
            BROWSER.verify_outer({'result': 'skipped', 'outputs': outputs}, BROWSER.outer_outputs(plan), plan)
        for outputs in ({'verified': 'true'}, {'plan': plan['plan']}, {'unapproved': ''}, None):
            with self.subTest(outputs=outputs), self.assertRaises(ValueError):
                BROWSER.verify_outer({'result': 'skipped', 'outputs': outputs}, BROWSER.outer_outputs(plan), plan)

    def test_actual_outer_cli_recomputes_candidate_and_receipt_without_executing_candidate_policy(self):
        self.activate_fixture()
        for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml'):
            self.write('.github/workflows/' + name, (ROOT / '.github/workflows' / name).read_bytes())
        self.base = self.commit('Install complete approved package sibling workflows')
        event, candidate = self.merge({'browser-client/src/Main.ts': b'throw new Error("never execute router input");\n'})
        spec = importlib.util.spec_from_file_location('browser_outer_test', ROOT / 'tools/repository-checks/check.py')
        checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
        packages = checks.package_policy(); package_plan = packages.candidate_plan(self.root, event, candidate)
        with patch.object(BROWSER, 'REVIEWED_BOUNDARY', REAL_BOUNDARY), patch.object(BROWSER, 'REVIEWED_BROWSER_BOUNDARY', REAL_BROWSER_BOUNDARY):
            plan = BROWSER.route(event, 'pull_request', self.root, candidate)
        config, branches = checks.configuration()
        outputs = {**checks.plan(event, ['browser-client/src/Main.ts'], config, branches), 'native': 'skip',
                   **packages.outputs(package_plan), **BROWSER.outer_outputs(plan)}
        needs = {'route': {'result': 'success', 'outputs': outputs},
                 'project': {'result': 'success', 'outputs': packages.receipt(package_plan)},
                 'documentation': {'result': 'success'}, 'workflow-security': {'result': 'skipped'},
                 'native': {'result': 'skipped'}, 'browser-client': {'result': 'success',
                     'outputs': {'candidate': candidate, 'plan': plan['plan'], 'verified': 'true'}}}
        event_path = Path(self.directory.name) / 'event.json'; event_path.write_text(json.dumps(event))
        command = [sys.executable, str(ROOT / 'tools/repository-checks/check.py'), 'verify', '--candidate', str(self.root),
                   '--sha', candidate, '--event', str(event_path), '--needs-json']
        environment = dict(os.environ, GITHUB_EVENT_NAME='pull_request')
        for mutation in ('valid', 'candidate', 'plan', 'diagnostic', 'missing'):
            actual = deepcopy(needs)
            if mutation in ('candidate', 'plan'): actual['browser-client']['outputs'][mutation] = '0' * 40
            elif mutation == 'diagnostic': actual['browser-client']['outputs']['verified'] = 'diagnostic-only'
            elif mutation == 'missing': del actual['browser-client']
            result = subprocess.run(command + [json.dumps(actual)], capture_output=True, text=True, timeout=30,
                                    env=environment)
            self.assertEqual(result.returncode == 0, mutation == 'valid', result.stderr)
        for expected_candidate, expected_plan, success in ((candidate, plan['plan'], True),
                (self.base, plan['plan'], False), (candidate, 'forged', False), ('', '', False)):
            output = Path(self.directory.name) / 'callee-output.txt'
            result = subprocess.run([sys.executable, str(HELPER), 'route', '--candidate', str(self.root),
                '--sha', candidate, '--event', str(event_path), '--event-name', 'pull_request', '--output', str(output),
                '--expected-candidate', expected_candidate, '--expected-plan', expected_plan],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode == 0, success, result.stderr)


class CanonicalTemplateTests(unittest.TestCase):
    def job(self, text, name):
        body = text.split("\n  " + name + ":\n", 1)[1]
        return re.split(r"\n  [A-Za-z][A-Za-z0-9_-]*:\n", body, maxsplit=1)[0]

    def test_existing_browser_and_native_job_scopes_are_preserved_exactly(self):
        old = LEGACY.decode()
        new = BROWSER.canonical_workflow().decode()
        for name in ("browser", "native-journey"):
            body = self.job(new, name)
            body = body.replace("    needs: route\n    if: needs.route.outputs.mode == 'full'\n", "", 1)
            body = body.replace("      - name: Audit changed browser package inputs\n        if: needs.route.outputs.audit == 'true'\n        run: npm audit --audit-level=high\n", "", 1)
            self.assertEqual(body.strip(), self.job(old, name).strip())

    def test_cpu_lane_retains_real_fixture_prerequisites_and_avoids_product_work(self):
        body = self.job(BROWSER.canonical_workflow().decode(), "cpu")
        for required in ("ffmpeg", "xvfb", "xauth", "bubblewrap", "slirp4netns", "iproute2", "gcc", "libssl-dev",
                         "apparmor-profiles", "tools/prepare-apparmor-userns.py", "prepare_signed_library.py",
                         "tools/trusted-network/workflow/build.py", "tools/trusted-network/workflow/install.py",
                         "OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP=1", "run: npm test", "run: npm ci",
                         "test_runner.py", "test_chrome_scope.py"):
            self.assertIn(required, body)
        for forbidden in ("npm run build", "vite build", "playwright install", "qtbase5-dev", "build-native-input.py",
                          "manage.py prepare", "run-core-journey.sh", "pulseaudio --start"):
            self.assertNotIn(forbidden, body)

    def test_route_and_final_recompute_in_independent_trusted_jobs(self):
        text = BROWSER.canonical_workflow().decode()
        for name, command in (("route", "route"), ("verify", "verify")):
            body = self.job(text, name)
            self.assertIn("ref: ${{ github.event.repository.default_branch }}", body)
            self.assertIn("trusted/tools/repository-checks/browser_cpu.py " + command, body)
            self.assertIn('--event "$GITHUB_EVENT_PATH" --event-name "$GITHUB_EVENT_NAME"', body)
            self.assertIn("persist-credentials: false", body)
        self.assertIn("needs: [route, cpu, browser, native-journey]", text)
        self.assertIn("if: always()", self.job(text, "verify"))

    def test_workflow_generation_is_exact_and_never_activates_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "browser-client.yml"
            result = subprocess.run([sys.executable, str(HELPER), "workflow", "--output", str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), BROWSER.canonical_workflow())
        self.assertEqual(BROWSER._blob(LEGACY), BROWSER.REVIEWED_WORKFLOW)

    def test_sole_automatic_owner_has_local_reusable_source_and_independent_outer_receipt(self):
        import yaml
        text = BROWSER.canonical_workflow().decode()
        callee = yaml.safe_load(text)
        events = callee.get('on', callee.get(True))
        self.assertEqual(set(events), {'workflow_call', 'workflow_dispatch'})
        self.assertEqual(events['workflow_call']['inputs'], {
            name: {'type': 'string', 'required': True} for name in ('expected_candidate', 'expected_plan')})
        self.assertEqual(events['workflow_call']['outputs'], {
            name: {'value': '${{ jobs.verify.outputs.' + name + ' }}'} for name in ('candidate', 'plan', 'verified')})
        route = self.job(text, 'route')
        self.assertIn('--expected-candidate "$EXPECTED_CANDIDATE" --expected-plan "$EXPECTED_PLAN"', route)
        caller = yaml.safe_load(BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE))['jobs']
        call = caller['browser-client']
        self.assertEqual(call['uses'], './.github/workflows/browser-client.yml')
        self.assertEqual(call['needs'], 'route')
        self.assertEqual(call['with'], {'expected_candidate': '${{ needs.route.outputs.browser_candidate }}',
                                       'expected_plan': '${{ needs.route.outputs.browser_plan }}'})
        self.assertEqual(caller['repository-checks']['if'], 'always()')
        self.assertIn('browser-client', caller['repository-checks']['needs'])
        self.assertEqual(callee['permissions'], {'contents': 'read'})
        self.assertNotIn('secrets:', text)
        # The same regression remains valid after the separately reviewed
        # atomic activation; no intermediate or unknown active shape is valid.
        active = (ROOT / BROWSER.WORKFLOW).read_bytes()
        outer = (ROOT / BROWSER.OUTER_WORKFLOW).read_bytes()
        targets = json.loads(BROWSER.trusted_bytes(BROWSER.CONFIGURATION))['browser_client_required_branches']
        if active == LEGACY:
            self.assertEqual(outer, LEGACY_OUTER)
            self.assertEqual(targets, [])
        else:
            self.assertEqual(active, BROWSER.canonical_workflow())
            self.assertEqual(outer, BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE))
            branches = json.loads((ROOT / '.github/branch-policy.json').read_text())['branches']
            self.assertTrue(targets)
            self.assertEqual(len(targets), len(set(targets)))
            self.assertTrue(set(targets) <= set(branches))

    def test_legacy_outer_fixture_refuses_any_unknown_change_or_partial_inverse(self):
        canonical = BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE)
        self.assertEqual(BROWSER._blob(LEGACY_OUTER), BROWSER.REVIEWED_OUTER)
        for value in (canonical + b'\n# unreviewed change\n',
                      canonical.replace(b'    - browser-client\n', b'', 1),
                      canonical.replace(b'      browser_plan:', b'      unreviewed_browser_plan:', 1)):
            with self.subTest(template=value[:40]), self.assertRaises(AssertionError):
                reviewed_outer_fixture(value)

    def test_browser_package_generation_is_additive_complete_and_never_combines_approved_siblings(self):
        spec = importlib.util.spec_from_file_location('browser_packages_test', ROOT / 'tools/repository-checks/package_checks.py')
        packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
        generations = packages.workflow_generations()
        self.assertTrue({'packages-v1', 'packages-v1-direct'} <= {row['name'] for row in generations})
        approved = next(row['workflows'] for row in generations if row['name'] == 'packages-browser')
        self.assertEqual(approved[BROWSER.OUTER_WORKFLOW], {'mode': '100644', 'type': 'blob',
            'sha': BROWSER._blob(BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE))})
        self.assertEqual(packages.validate_tree_wiring(approved), 'packages-browser')
        for path in approved:
            bad = deepcopy(approved); bad[path]['sha'] = '0' * 40
            with self.assertRaises(ValueError): packages.validate_tree_wiring(bad)
        other = next(row['workflows'] for row in generations if row['name'] == 'shared-receipt-v1')
        mixed = deepcopy(approved); mixed['.github/workflows/project-tests.yml'] = other['.github/workflows/project-tests.yml']
        with self.assertRaises(ValueError): packages.validate_tree_wiring(mixed)


if __name__ == "__main__":
    unittest.main()
