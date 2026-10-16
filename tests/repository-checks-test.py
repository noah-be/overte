#!/usr/bin/env python3
"""Negative routing, merge identity and aggregate-result regressions."""

from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_checks", ROOT / "tools/repository-checks/check.py")
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)
CONFIG, BRANCHES = CHECKS.configuration()
TOOL_SPEC = importlib.util.spec_from_file_location(
    "tool_dependencies_test", ROOT / "tools/repository-checks/tool_dependencies.py")
TOOLS = importlib.util.module_from_spec(TOOL_SPEC)
TOOL_SPEC.loader.exec_module(TOOLS)
PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "package_checks_test", ROOT / "tools/repository-checks/package_checks.py")
PACKAGES = importlib.util.module_from_spec(PACKAGE_SPEC)
PACKAGE_SPEC.loader.exec_module(PACKAGES)
CONSUMER_SPEC = importlib.util.spec_from_file_location(
    "npm_consumers_test", ROOT / "tools/repository-checks/npm_consumers.py")
CONSUMERS = importlib.util.module_from_spec(CONSUMER_SPEC)
CONSUMER_SPEC.loader.exec_module(CONSUMERS)


def event(base="main", head="fix/main/example", fork=False):
    repository = {"id": CONFIG["repository_id"], "full_name": CONFIG["repository"]}
    return {"repository": repository, "pull_request": {
        "base": {"ref": base, "repo": repository, "sha": "1" * 40},
        "head": {"ref": head, "repo": {"id": 123, "full_name": "contributor/fork"} if fork else repository,
                 "sha": "2" * 40}}}


def results(mode="full", security="true"):
    return {"route": {"result": "success", "outputs": {"mode": mode, "security": security, "native": "full"}},
            "project": {"result": "success" if mode in {"full", "tool-dependencies"} else "skipped"},
            "documentation": {"result": "success"},
            "native": {"result": "success"},
            "workflow-security": {"result": "success" if security == "true" else "skipped"}}


def inactive_browser_trusted_checkout(test):
    """Run historical CLI contracts with explicit disposable trusted policy.

    A real sparse clone retains immutable omitted requirement blobs. Only this
    fixture's Browser activation list changes; actual ROOT is never modified.
    Dedicated Browser tests exercise the current activated required handoff.
    """
    directory = tempfile.TemporaryDirectory(prefix='overte-inactive-browser-policy-')
    test.addCleanup(directory.cleanup)
    trusted = Path(directory.name) / 'trusted'
    subprocess.run(['git', 'clone', '-q', '--shared', '--no-checkout', str(ROOT), str(trusted)],
                   check=True, capture_output=True)
    subprocess.run(['git', '-C', str(trusted), 'sparse-checkout', 'set', '--cone', '.github',
                    'tools/repository-checks', 'tools/test-evidence', 'tools/native-tests',
                    'tools/ios-build-qualification'], check=True, capture_output=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', '-C', str(trusted), 'checkout', '-q', '--detach', revision],
                   check=True, capture_output=True)
    original = (ROOT / '.github/repository-checks.json').read_bytes()
    policy = trusted / '.github/repository-checks.json'
    config = json.loads(policy.read_bytes())
    config['browser_client_required_branches'] = []
    policy.write_text(json.dumps(config, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('inactive_browser_repository_checks',
                                                trusted / 'tools/repository-checks/check.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    test.assertEqual(checks.configuration()[0]['browser_client_required_branches'], [])
    test.assertEqual((ROOT / '.github/repository-checks.json').read_bytes(), original)
    return trusted, checks.package_policy()


class MetadataEditTests(unittest.TestCase):
    """Dormant edit routing must preserve the original required check result."""

    TEMPLATES = ROOT / 'tools/repository-checks/workflows/metadata-edits'

    def edited(self, changes=None):
        payload = event()
        payload.update(action='edited', number=17, changes=changes or {'title': {'from': 'Previous title'}})
        payload['pull_request'].update(number=17, state='open', title='Current title', body='Current description')
        return payload

    def test_only_complete_known_title_and_body_edits_are_metadata(self):
        for changes in ({'title': {'from': 'Old'}}, {'body': {'from': 'Old'}}, {'body': {'from': None}},
                        {'title': {'from': ''}, 'body': {'from': 'Old'}}):
            for name in ('pull_request', 'pull_request_target'):
                with self.subTest(changes=changes, name=name):
                    self.assertTrue(CHECKS.metadata_edit(self.edited(changes), name))
        payload = self.edited({'body': {'from': 'Removed description'}})
        payload['pull_request']['body'] = None
        self.assertTrue(CHECKS.metadata_edit(payload, 'pull_request'))

    def test_retarget_unknown_and_malformed_changes_keep_normal_qualification(self):
        changes = ({}, None, [], 'title', {'base': {'ref': {'from': 'old'}, 'sha': {'from': '1' * 40}}},
                   {'title': {'from': 'Old'}, 'base': {}}, {'title': {'from': 'Old'}, 'future': {}},
                   {'title': {}}, {'title': {'from': 'Old', 'extra': True}}, {'title': {'from': None}},
                   {'body': {'from': False}}, {'body': 'old'}, {'unknown': {'from': 'Old'}})
        for change in changes:
            payload = self.edited(); payload['changes'] = change
            with self.subTest(changes=change):
                self.assertFalse(CHECKS.metadata_edit(payload, 'pull_request'))
        payload = self.edited(); payload.pop('changes')
        self.assertFalse(CHECKS.metadata_edit(payload, 'pull_request'))

    def test_missing_or_foreign_server_context_does_not_omit_required_jobs(self):
        original = self.edited()
        for name in ('workflow_dispatch', 'push', 'schedule', '', None):
            self.assertFalse(CHECKS.metadata_edit(original, name))
        for replace in ('number', 'state', 'action', 'repository', 'base-repo', 'head-sha', 'base-sha', 'title'):
            payload = deepcopy(original)
            if replace == 'number': payload['number'] = True
            elif replace == 'state': payload['pull_request']['state'] = 'closed'
            elif replace == 'action': payload['action'] = 'synchronize'
            elif replace == 'repository': payload['repository'] = {'id': 1319052603, 'full_name': 'overte-org/overte'}
            elif replace == 'base-repo': payload['pull_request']['base']['repo'] = None
            elif replace in ('head-sha', 'base-sha'): payload['pull_request'][replace.split('-')[0]]['sha'] = '0' * 40
            else: payload['pull_request']['title'] = []
            with self.subTest(replace=replace):
                self.assertFalse(CHECKS.metadata_edit(payload, 'pull_request'))

    def test_malformed_json_files_keep_normal_routing_without_a_qualification_claim(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'event.json'
            payload = self.edited()
            for raw in ('{', '{}', json.dumps(payload).replace('"edited"', '"edited", "action": "edited"', 1),
                        json.dumps(payload).replace('"Previous title"', 'NaN', 1), ' ' * 1_000_001):
                path.write_text(raw)
                with self.subTest(raw=raw[:35]):
                    self.assertEqual(CHECKS.classify_metadata_event(path, 'pull_request'),
                        {'kind': 'pr-metadata-classification', 'qualification': False,
                         'metadata_edit': False, 'metadata_only': 'false'})
            path.unlink()
            self.assertEqual(CHECKS.classify_metadata_event(path, 'pull_request')['metadata_only'], 'false')

    def test_classifier_cli_never_invokes_configuration_candidate_routing_or_verification(self):
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as name:
            path, output = Path(name) / 'event.json', Path(name) / 'outputs'
            path.write_text(json.dumps(self.edited()))
            command = ['check.py', 'metadata-event', '--event', str(path), '--event-name', 'pull_request',
                       '--output', str(output)]
            with patch.object(sys, 'argv', command), patch.object(CHECKS, 'configuration') as config, \
                    patch.object(CHECKS, 'plan') as plan, patch.object(CHECKS, 'verify') as verify, \
                    redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(CHECKS.main(), 0)
            config.assert_not_called(); plan.assert_not_called(); verify.assert_not_called()
            self.assertEqual(output.read_text(), 'metadata_only=false\n')
            classification = json.loads(printed.getvalue())
            self.assertIs(classification['qualification'], False)
            self.assertIs(classification['metadata_edit'], True)

    def test_complete_text_edit_cannot_preserve_unverified_old_policy_success(self):
        # Strict checks may retain a canonical success on H while trusted main
        # changes P1 -> P2 without changing a child PR's base B or source H.
        # Even a complete server event cannot authenticate that old result.
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'event.json'
            for changes in ({'title': {'from': 'Old'}}, {'body': {'from': 'Old'}},
                            {'title': {'from': 'Old'}, 'body': {'from': 'Old'}}):
                payload = self.edited(changes)
                payload['pull_request']['base']['ref'] = 'android-phone'
                original = deepcopy(payload)
                path.write_text(json.dumps(payload))
                result = CHECKS.classify_metadata_event(path, 'pull_request')
                self.assertIs(result['metadata_edit'], True)
                self.assertEqual(result['metadata_only'], 'false')
                self.assertIs(result['qualification'], False)
                self.assertEqual(json.loads(path.read_text()), original)

    def test_actual_classifier_failure_is_nonzero_and_emits_no_metadata_output(self):
        from contextlib import redirect_stderr
        import io
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / 'outputs'
            command = ['check.py', 'metadata-event', '--event', str(Path(name) / 'event.json'),
                       '--event-name', 'pull_request_target', '--output', str(output)]
            with patch.object(sys, 'argv', command), \
                    patch.object(CHECKS, 'classify_metadata_event', side_effect=OSError('classifier unavailable')), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(CHECKS.main(), 1)
            self.assertFalse(output.exists())

    def test_metadata_output_is_not_an_aggregate_or_package_success_receipt(self):
        needs = results()
        needs['route']['outputs']['metadata_only'] = 'true'
        for job in ('project', 'native', 'documentation', 'workflow-security'):
            for outcome in ('failure', 'skipped', 'cancelled'):
                broken = deepcopy(needs); broken[job]['result'] = outcome
                with self.subTest(job=job, outcome=outcome), self.assertRaises(ValueError):
                    CHECKS.verify(broken)
        for outcome in ('failure', 'cancelled', 'skipped'):
            broken = deepcopy(needs); broken['route']['result'] = outcome
            with self.subTest(route=outcome), self.assertRaises(ValueError):
                CHECKS.verify(broken)
        missing = deepcopy(needs); missing['route']['outputs'] = {}
        with self.assertRaises(ValueError): CHECKS.verify(missing)

    def workflows(self):
        import yaml
        return {name: yaml.safe_load((self.TEMPLATES / (name + '.yml')).read_text())
                for name in ('repository-checks', 'sync-test-reuse')}

    def test_dormant_workflows_isolate_metadata_concurrency_before_job_classification(self):
        import yaml
        suffix = "-${{ github.event.action == 'edited' && !github.event.changes.base && " \
                 "(github.event.changes.title || github.event.changes.body) && github.run_id || 'qualification' }}"
        for name, workflow in self.workflows().items():
            with self.subTest(workflow=name):
                self.assertTrue(workflow['concurrency']['group'].endswith(suffix))
                self.assertIs(workflow['concurrency']['cancel-in-progress'], True)
                self.assertNotIn('needs.', workflow['concurrency']['group'])
                if name == 'repository-checks':
                    previous = yaml.safe_load((ROOT / PACKAGES.CONSUMER_TEMPLATES / 'repository-checks.yml').read_text())
                    expected_events = previous.get('on', previous.get(True))
                else:
                    # Exact protected pre-metadata 2478d9e event contract. Do
                    # not depend on historical Git objects in hosted checkouts.
                    expected_events = {'pull_request_target': {
                        'types': ['opened', 'reopened', 'synchronize', 'edited'],
                        'branches': ['main', 'android-main', 'android-phone', 'android-vr',
                                     'android-vr-pico', 'apple-main', 'apple-ios']},
                        'workflow_dispatch': None}
                self.assertEqual(workflow.get('on', workflow.get(True)), expected_events)

    def test_repository_metadata_skips_all_work_with_distinct_names_and_unchanged_real_verifier(self):
        import yaml
        future = self.workflows()['repository-checks']['jobs']
        previous = yaml.safe_load((ROOT / PACKAGES.CONSUMER_TEMPLATES / 'repository-checks.yml').read_text())['jobs']
        for name in ('native', 'project', 'documentation', 'workflow-security', 'repository-checks'):
            job = deepcopy(future[name])
            self.assertEqual(job.pop('name'), "${{ needs.route.result == 'success' && needs.route.outputs.metadata_only == 'true' && '" + name +
                             " (metadata unchanged)' || '" + name + "' }}")
            original = deepcopy(previous[name]); original.pop('name', None)
            condition = original.pop('if', None)
            guard = "needs.route.outputs.metadata_only != 'true'"
            expected = ("always() && (needs.route.result != 'success' || " + guard + ')' if name == 'repository-checks' else
                        guard + ' && (' + condition + ')' if name == 'project' else
                        guard + ' && ' + condition if condition else guard)
            self.assertEqual(job.pop('if'), expected)
            self.assertEqual(job, original)
        route = deepcopy(future['route'])
        self.assertEqual(route['outputs'].pop('metadata_only'), '${{ steps.event.outputs.metadata_only }}')
        classifier = route['steps'].pop(1)
        self.assertEqual(classifier['id'], 'event')
        self.assertIn('check.py metadata-event', classifier['run'])
        for step in route['steps'][1:]:
            self.assertEqual(step.pop('if'), "steps.event.outputs.metadata_only != 'true'")
        self.assertEqual(route, previous['route'])

    def test_sync_metadata_cannot_dispatch_and_classifier_failure_retains_a_failing_required_name(self):
        import yaml
        jobs = self.workflows()['sync-test-reuse']['jobs']
        job = deepcopy(jobs['sync-test-reuse'])
        self.assertEqual(job.pop('name'), "${{ needs.classify.result == 'success' && needs.classify.outputs.metadata_only == 'true' && "
                         "'sync-test-reuse (metadata unchanged)' || 'sync-test-reuse' }}")
        self.assertEqual(job.pop('if'), "always() && (needs.classify.result != 'success' || needs.classify.outputs.metadata_only != 'true')")
        self.assertEqual(job.pop('needs'), 'classify')
        failure = job['steps'].pop(0)
        self.assertEqual(failure['env'], {'CLASSIFICATION_RESULT': '${{ needs.classify.result }}'})
        self.assertEqual(failure['run'], 'test "$CLASSIFICATION_RESULT" = success')
        for state in ('success', 'failure', 'cancelled', 'skipped', ''):
            observed = subprocess.run(['sh', '-c', failure['run']], env={'CLASSIFICATION_RESULT': state},
                                      capture_output=True, timeout=5)
            self.assertEqual(observed.returncode, 0 if state == 'success' else 1)
        # Normalize only the already asserted metadata guard/name/first step.
        # The remaining complete six-step job must retain protected 2478d9e's
        # exact semantics even after ROOT itself deploys this successor.
        normalized = (json.dumps(job, sort_keys=True, separators=(',', ':')) + '\n').encode()
        self.assertEqual(hashlib.sha256(normalized).hexdigest(),
                         '3d28170e8016afbed93a758e00a9842888c90ef252b0b74df23d7d4c9a4b6f33')
        active = (ROOT / '.github/workflows/sync-test-reuse.yml').read_bytes()
        successor = (self.TEMPLATES / 'sync-test-reuse.yml').read_bytes()
        if active == successor:
            self.assertIn(PACKAGES.validate_wiring(ROOT),
                          ('npm-consumers-metadata-edits-v1', 'android-owned-npm5-sync-ci-v1'))
            self.assertEqual(yaml.safe_load(active)['jobs']['sync-test-reuse']['name'],
                "${{ needs.classify.result == 'success' && needs.classify.outputs.metadata_only == 'true' && "
                "'sync-test-reuse (metadata unchanged)' || 'sync-test-reuse' }}")
        else:
            identity = hashlib.sha1(b'blob ' + str(len(active)).encode() + b'\0' + active).hexdigest()
            self.assertEqual(identity, '59a19621ac160fc5c48d5323e4e61490e83f708a')
            self.assertEqual(yaml.safe_load(active)['jobs']['sync-test-reuse']['name'], 'sync-test-reuse')
        classify = jobs['classify']
        self.assertEqual(classify['outputs'], {'metadata_only': '${{ steps.event.outputs.metadata_only }}'})
        self.assertIn('check.py metadata-event', classify['steps'][-1]['run'])
        self.assertEqual(classify['steps'][0]['with']['ref'], '${{ github.event.repository.default_branch }}')
        self.assertIs(classify['steps'][0]['with']['persist-credentials'], False)

    def test_new_caller_requires_exact_complete_five_workflow_generation(self):
        import hashlib
        source = (self.TEMPLATES / 'repository-checks.yml').read_bytes()
        identity = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
        generations = PACKAGES.workflow_generations()
        future = next(g for g in generations if g['name'] == 'npm-consumers-metadata-edits-v1')
        previous = next(g for g in generations if g['name'] == 'npm-consumers-sync-ci-v1')
        self.assertEqual(set(future['workflows']), set(PACKAGES.CONSUMER_WORKFLOW_PATHS))
        self.assertEqual([name for name in future['workflows'] if future['workflows'][name] != previous['workflows'][name]],
                         ['.github/workflows/repository-checks.yml'])
        self.assertEqual(future['workflows']['.github/workflows/repository-checks.yml']['sha'], identity)
        self.assertEqual(future['workflows']['.github/workflows/sync-validation.yml']['sha'],
                         '55d08b65a987224ce576459cede693cfd49375f6')
        self.assertEqual(PACKAGES.validate_tree_wiring(future['workflows']), future['name'])
        for change in ('missing', 'unknown', 'legacy-sync'):
            tree = deepcopy(future['workflows'])
            if change == 'missing': tree.pop('.github/workflows/browser-client.yml')
            elif change == 'unknown': tree['.github/workflows/repository-checks.yml']['sha'] = 'a' * 40
            else:
                tree['.github/workflows/sync-validation.yml']['sha'] = next(
                    g for g in generations if g['name'] == 'npm-consumers-v1')['workflows']['.github/workflows/sync-validation.yml']['sha']
            with self.subTest(change=change), self.assertRaises(ValueError):
                PACKAGES.validate_tree_wiring(tree)



class NativeCallerSchedulingTests(unittest.TestCase):
    """Evaluate actual caller guards with GitHub's transitive default status.

    GitHub workflow-syntax documents skipped ancestors throughout the needs
    chain; expressions documents implicit success() unless a status function
    occurs. This bounded fixture models those rules, not a hosted execution.
    """

    def setUp(self):
        import yaml
        self.jobs = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/producers/repository-checks.yml').read_text())['jobs']
        self.outputs = {'metadata_only': 'false', 'native': 'skip', 'package_host_mode': 'full',
                        'package_set': '[]', 'android_required': 'false', 'security': 'true'}
        self.states = {'metadata-source': 'skipped', 'route': 'success'}

    def scheduled(self, name, *, expression=None, cancelled=False):
        def ancestors(job):
            needs = self.jobs[job].get('needs', [])
            if isinstance(needs, str): needs = [needs]
            return set(needs) | {item for parent in needs for item in ancestors(parent)}
        expression = self.jobs[name]['if'] if expression is None else expression
        successful = all(self.states[item] == 'success' for item in ancestors(name))
        if not re.search(r'\b(?:always|cancelled|failure|success)\s*\(', expression) and not successful:
            return False
        expression = re.sub(r'!(?!=)', 'not ', expression.replace('&&', ' and ').replace('||', ' or '))
        context = {'needs': {'route': {'result': self.states['route'], 'outputs': self.outputs}}}
        functions = {'always': True, 'cancelled': cancelled, 'success': successful,
                     'failure': any(self.states[item] == 'failure' for item in ancestors(name))}
        def evaluate(node):
            if isinstance(node, ast.Constant): return node.value
            if isinstance(node, ast.Name): return context[node.id]
            if isinstance(node, ast.Attribute): return evaluate(node.value)[node.attr]
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.args and not node.keywords:
                return functions[node.func.id]
            if isinstance(node, ast.BoolOp):
                values = (evaluate(value) for value in node.values)
                if isinstance(node.op, ast.And): return all(values)
                if isinstance(node.op, ast.Or): return any(values)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): return not evaluate(node.operand)
            if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
                left, right = evaluate(node.left), evaluate(node.comparators[0])
                if isinstance(node.ops[0], ast.Eq): return left == right
                if isinstance(node.ops[0], ast.NotEq): return left != right
            raise AssertionError('unreviewed scheduling expression')
        return bool(evaluate(ast.parse(expression, mode='eval').body))

    def test_normal_pr_selected_jobs_survive_skipped_metadata_ancestor(self):
        self.assertEqual(self.jobs['route']['needs'], 'metadata-source')
        self.assertIn('always()', self.jobs['route']['if'])
        self.assertEqual({name for name in ('native', 'project', 'android', 'workflow-security') if self.scheduled(name)},
                         {'project', 'workflow-security'})
        for name in ('project', 'workflow-security'):
            # Removing the explicit status function reproduces the incident,
            # even though direct route succeeded and its selector is true.
            old = self.jobs[name]['if'].split("needs.route.result == 'success' && ", 1)[1]
            self.assertFalse(self.scheduled(name, expression=old))

    def test_each_existing_route_selector_remains_necessary(self):
        for changes, expected in (({'native': 'configure'}, {'native', 'project', 'workflow-security'}),
                ({'android_required': 'true'}, {'android', 'project', 'workflow-security'}),
                ({'package_host_mode': 'skip', 'security': 'false'}, set()),
                ({'package_host_mode': 'tool-dependencies'}, {'project', 'workflow-security'}),
                ({'package_host_mode': 'skip', 'package_set': '["browser"]'}, {'project', 'workflow-security'})):
            with self.subTest(changes=changes), patch.dict(self.outputs, changes):
                self.assertEqual({name for name in ('native', 'project', 'android', 'workflow-security') if self.scheduled(name)}, expected)

    def test_bad_route_metadata_and_cancellation_never_start_workloads(self):
        self.outputs.update(native='full', android_required='true')
        for state in ('failure', 'cancelled', 'skipped', ''):
            self.states['route'] = state
            for name in ('native', 'project', 'android', 'workflow-security'):
                with self.subTest(state=state, job=name): self.assertFalse(self.scheduled(name))
        self.states['route'] = 'success'
        for name in ('native', 'project', 'android', 'workflow-security'):
            with self.subTest(cancelled=True, job=name): self.assertFalse(self.scheduled(name, cancelled=True))
        self.outputs['metadata_only'] = 'true'
        for name in ('native', 'project', 'android', 'workflow-security'):
            with self.subTest(metadata=True, job=name): self.assertFalse(self.scheduled(name))

    def test_required_aggregate_keeps_its_failure_path_and_real_verifier(self):
        aggregate = self.jobs['repository-checks']
        self.assertEqual(aggregate['if'], "always() && (needs.route.result != 'success' || needs.route.outputs.metadata_only != 'true')")
        self.assertTrue({'route', 'native', 'project', 'android', 'documentation', 'workflow-security', 'workflow-contracts'} <= set(aggregate['needs']))
        self.assertEqual(aggregate['steps'][0]['with']['ref'], '${{ github.event.repository.default_branch }}')
        self.assertIn('python3 tools/repository-checks/check.py verify', aggregate['steps'][-1]['run'])


class NativeMetadataContextTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('native_metadata_marker_tests',
            ROOT / 'tools/repository-checks/metadata_context.py')
        self.marker = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.marker)
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()
        self.git = git; git('init', '--quiet'); git('config', 'user.name', 'Metadata fixture')
        git('config', 'user.email', 'metadata@example.invalid')
        target = self.root / self.marker.SOURCE; target.parent.mkdir(parents=True)
        target.write_bytes((ROOT / self.marker.SOURCE).read_bytes())
        git('add', '.'); git('commit', '--quiet', '-m', 'Immutable marker fixture')
        self.base = git('rev-parse', 'HEAD')
        self.event = MetadataEditTests().edited({'title': {'from': 'Old'}, 'body': {'from': 'Old'}})
        self.event['pull_request']['base']['sha'] = self.base
        self.environment = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'noah-l-frank/overte',
            'GITHUB_REPOSITORY_ID': '1319052603', 'GITHUB_EVENT_NAME': 'pull_request',
            'GITHUB_REF': 'refs/pull/17/merge', 'GITHUB_BASE_REF': 'main',
            'GITHUB_HEAD_REF': self.event['pull_request']['head']['ref'], 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_RUN_ID': '123', 'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24',
            'GITHUB_SHA': '3' * 40, 'GITHUB_WORKFLOW_SHA': '3' * 40, 'GITHUB_JOB': 'recognize',
            'GITHUB_WORKFLOW_REF': 'noah-l-frank/overte/.github/workflows/repository-checks.yml@refs/pull/17/merge'}

    def test_disabled_marker_never_claims_a_nonproducer_or_qualification(self):
        with patch.object(self.marker,'SOURCE_READY',False):
            result = self.marker.recognize(self.event, self.environment, root=self.root)
        self.assertEqual(result['metadata_intent'], 'false'); self.assertFalse(result['qualification'])
        self.assertTrue(result['metadata_edit']); self.assertNotIn('run_id', result)

    def test_actual_git_source_and_native_context_bind_marker_without_qualification(self):
        with patch.object(self.marker, 'SOURCE_READY', True):
            result = self.marker.recognize(self.event, self.environment, root=self.root)
        self.assertEqual(result['metadata_intent'], 'true'); self.assertFalse(result['qualification'])
        self.assertEqual(result['base'], self.base)
        self.assertEqual(result['helper_blob'], self.git('rev-parse', 'HEAD:' + self.marker.SOURCE))
        for changes in ({'title': {'from': 'Old'}}, {'body': {'from': None}}, {'base': {}}):
            event_copy = deepcopy(self.event); event_copy['changes'] = changes
            self.assertEqual(self.marker.event_only(event_copy, 'pull_request'),
                             CHECKS.metadata_edit(event_copy, 'pull_request'))

    def test_marker_rejects_foreign_native_context_and_source_mutation(self):
        for key, value in [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_BASE_REF', 'apple-ios'),
                           ('GITHUB_SHA', '0' * 40), ('GITHUB_WORKFLOW_SHA', '4' * 40),
                           ('GITHUB_WORKFLOW_REF', 'foreign/repo/.github/workflows/codeql.yml@refs/pull/17/merge'),
                           ('GITHUB_JOB', 'project-tests')]:
            environment = {**self.environment, key: value}
            with self.subTest(key=key), patch.object(self.marker, 'SOURCE_READY', True), \
                    self.assertRaises(self.marker.MetadataUnavailable):
                self.marker.recognize(self.event, environment, root=self.root)
        target = self.root / self.marker.SOURCE; target.write_text(target.read_text() + '# changed\n')
        with patch.object(self.marker, 'SOURCE_READY', True), self.assertRaises(self.marker.MetadataUnavailable):
            self.marker.recognize(self.event, self.environment, root=self.root)

    def test_marked_classifier_retains_only_explicit_non_authoritative_proof(self):
        event_file = self.root / 'event.json'; event_file.write_text(json.dumps(self.event))
        proof = {'metadata_only': 'true', 'qualification': False, 'kind': 'authenticated-test-fixture'}
        with patch.dict(os.environ, {'NATIVE_METADATA_INTENT': 'true'}), \
                patch.object(CHECKS, '_retained_metadata', return_value=proof) as retained:
            result = CHECKS.classify_metadata_event(event_file, 'pull_request')
        self.assertEqual(result['metadata_only'], 'true'); self.assertFalse(result['qualification'])
        retained.assert_called_once_with(self.event)
        for invalid in ({'metadata_only': 'true', 'qualification': True}, {'metadata_only': 'false', 'qualification': False}):
            with patch.dict(os.environ, {'NATIVE_METADATA_INTENT': 'true'}), \
                    patch.object(CHECKS, '_retained_metadata', return_value=invalid), self.assertRaises(ValueError):
                CHECKS.classify_metadata_event(event_file, 'pull_request')

    def test_marked_missing_proof_fails_small_without_producer_fallback(self):
        event_file = self.root / 'event.json'; event_file.write_text(json.dumps(self.event))
        with patch.dict(os.environ, {'NATIVE_METADATA_INTENT': 'true'}), \
                patch.object(CHECKS, '_retained_metadata', side_effect=ValueError('proof unavailable')), \
                patch.object(CHECKS, 'plan') as ordinary, self.assertRaises(ValueError):
            CHECKS.classify_metadata_event(event_file, 'pull_request')
        ordinary.assert_not_called()
        changed = deepcopy(self.event); changed['changes']['base'] = {}; event_file.write_text(json.dumps(changed))
        with patch.dict(os.environ, {'NATIVE_METADATA_INTENT': 'true'}), \
                patch.object(CHECKS, '_retained_metadata') as retained, self.assertRaises(ValueError):
            CHECKS.classify_metadata_event(event_file, 'pull_request')
        retained.assert_not_called()

    def test_unmarked_existing_workflows_keep_ordinary_qualification(self):
        event_file = self.root / 'event.json'; event_file.write_text(json.dumps(self.event))
        for intent in ('', 'false'):
            with patch.dict(os.environ, {'NATIVE_METADATA_INTENT': intent}), \
                    patch.object(CHECKS, '_retained_metadata') as retained:
                self.assertEqual(CHECKS.classify_metadata_event(event_file, 'pull_request')['metadata_only'], 'false')
            retained.assert_not_called()

    def test_tiny_workflow_uses_an_isolated_interpreter_and_real_native_source_edge(self):
        import yaml
        template = yaml.safe_load((ROOT / self.marker.SOURCE_TEMPLATE).read_text())
        job = template['jobs']['recognize']; steps = job['steps']
        self.assertEqual(steps[0]['with']['ref'], '${{ github.event.pull_request.base.sha }}')
        self.assertEqual(steps[0]['with']['sparse-checkout'], self.marker.SOURCE)
        self.assertFalse(steps[0]['with']['sparse-checkout-cone-mode'])
        self.assertIn('python3 -I -S -B trusted/' + self.marker.SOURCE, steps[1]['run'])
        self.assertEqual(steps[2]['name'], self.marker.MARKER_STEP)
        self.assertEqual(steps[2]['if'], "steps.context.outputs.metadata_intent == 'true'")
        self.assertEqual(steps[2]['run'], ':')
        self.assertNotIn('upload-artifact', json.dumps(template))


class RoutingTests(unittest.TestCase):
    def test_current_account_name_keeps_exact_repository_and_base_identity(self):
        self.assertEqual(CONFIG['repository'], 'noah-l-frank/overte')
        self.assertEqual(CONFIG['repository_id'], 1319052603)
        self.assertEqual(CHECKS.plan(event(), ['a.cpp'], CONFIG, BRANCHES)['mode'], 'full')
        for side in ('repository', 'base'):
            for change in ({'full_name': 'noah-be/overte'}, {'id': 42},
                           {'full_name': 'overte-org/overte'}):
                candidate = deepcopy(event())
                identity = (candidate['repository'] if side == 'repository'
                            else candidate['pull_request']['base']['repo'])
                identity.update(change)
                with self.subTest(side=side, change=change), self.assertRaises(ValueError):
                    CHECKS.plan(candidate, ['a.cpp'], CONFIG, BRANCHES)
        # A stale head name cannot claim same-repository sync delegation, even
        # with the real numeric repository ID.
        candidate = deepcopy(event('android-main', 'main'))
        candidate['pull_request']['head']['repo'] = {
            'full_name': 'noah-be/overte', 'id': 1319052603}
        self.assertEqual(CHECKS.plan(candidate, ['a.cpp'], CONFIG, BRANCHES)['mode'], 'full')

    def test_rename_does_not_bootstrap_the_old_default_branch_router(self):
        legacy = {**CONFIG, 'repository': 'noah-be/overte'}
        with self.assertRaisesRegex(ValueError, 'repository identity mismatch'):
            CHECKS.plan(event(), ['.github/repository-checks.json'], legacy, BRANCHES)
        manual = {'repository': deepcopy(event()['repository'])}
        with self.assertRaisesRegex(ValueError, 'repository mismatch'):
            CHECKS.native_required(legacy, manual)
        self.assertTrue(CHECKS.native_required(CONFIG, manual))
        manual['repository']['full_name'] = 'noah-be/overte'
        with self.assertRaisesRegex(ValueError, 'repository mismatch'):
            CHECKS.native_required(CONFIG, manual)

    def test_tool_manifests_select_only_the_affected_projects(self):
        for project in TOOLS.PROJECTS:
            for filename in ("package.json", "package-lock.json"):
                route = CHECKS.plan(event(), [f"{project}/{filename}", "docs/change.md"], CONFIG, BRANCHES)
                self.assertEqual(route, {"mode": "tool-dependencies", "security": "false",
                                         "tool_projects": project})
        route = CHECKS.plan(event(), sorted(TOOLS.MANIFESTS), CONFIG, BRANCHES)
        self.assertEqual(route["tool_projects"], "server-console,tools/jsdoc")

    def test_tool_route_does_not_cover_source_build_unknown_or_nonregular_changes(self):
        manifests = ["tools/jsdoc/package-lock.json"]
        for path in ("interface/src/Application.cpp", "tools/jsdoc/CMakeLists.txt",
                     "tools/jsdoc/plugins/hifi.js", "tools/jsdoc/unknown.json", "server-console/src/main.js",
                     "tools/repository-checks/tool_dependencies.py", ".github/workflows/project-tests.yml",
                     "browser-client/package-lock.json", "docs/image.png"):
            self.assertEqual(CHECKS.plan(event(), manifests + [path], CONFIG, BRANCHES)["mode"], "full")
        self.assertEqual(CHECKS.plan(event(), manifests, CONFIG, BRANCHES,
                                     documentation_safe=False)["mode"], "full")
        route = CHECKS.plan(event("android-main", "main"), manifests, CONFIG, BRANCHES)
        self.assertEqual(route["mode"], "delegated-sync")
        self.assertNotIn("tool_projects", route)

    def test_previously_uncovered_and_unknown_paths_run_project_checks(self):
        for path in ("CMakeLists.txt", "cmake/compiler.cmake", "assignment-client/src/Agent.cpp",
                     "domain-server/src/DomainServer.cpp", "ice-server/src/main.cpp",
                     "plugins/example.cpp", "tools/new-tool.py", "new-area/future.unknown",
                     "android/reintroduced.cpp"):
            with self.subTest(path=path):
                self.assertEqual(CHECKS.plan(event(), [path], CONFIG, BRANCHES)["mode"], "full")

    def test_only_markdown_can_take_documentation_route(self):
        self.assertEqual(CHECKS.plan(event(), ["README.md", "docs/a.md"], CONFIG, BRANCHES),
                         {"mode": "documentation", "security": "false"})
        for paths in ([], ["docs/a.md", "docs/image.png"], ["README.md", "tools/check.py"]):
            self.assertEqual(CHECKS.plan(event(), paths, CONFIG, BRANCHES)["mode"], "full")
        self.assertEqual(CHECKS.plan(event(), ["README.md"], CONFIG, BRANCHES,
                                     documentation_safe=False)["mode"], "full")

    def test_governance_and_security_changes_require_security_checks(self):
        for path in (".github/workflows/new.yml", ".github/repository-checks.json",
                     ".github/rulesets/README.md", "tools/repository-checks/check.py",
                     "tools/workflow-security/check-action-pins.py"):
            self.assertEqual(CHECKS.plan(event(), [path], CONFIG, BRANCHES)["security"], "true")

    def test_only_same_repository_direct_edges_or_scoped_reconciliations_delegate(self):
        for target, value in BRANCHES.items():
            if not value["parent"]:
                continue
            for head in (value["parent"], f"reconcile/{value['scope']}/reviewed-merge"):
                self.assertEqual(CHECKS.plan(event(target, head), ["a.cpp"], CONFIG, BRANCHES)["mode"],
                                 "delegated-sync")
                self.assertEqual(CHECKS.plan(event(target, head, fork=True), ["a.cpp"], CONFIG, BRANCHES)["mode"],
                                 "full")
        for base, head in (("main", "android-main"), ("android-phone", "main"),
                           ("android-phone", "apple-main"), ("android-phone", "sync/android-phone/x"),
                           ("android-phone", "reconcile/android/x")):
            self.assertEqual(CHECKS.plan(event(base, head), ["a.cpp"], CONFIG, BRANCHES)["mode"], "full")

    def test_foreign_base_and_invalid_paths_fail(self):
        wrong = deepcopy(event())
        wrong["repository"]["full_name"] = "overte-org/overte"
        with self.assertRaises(ValueError):
            CHECKS.plan(wrong, ["a.cpp"], CONFIG, BRANCHES)
        for path in ("../escape.md", "/absolute.md", "bad\x00name", ""):
            with self.assertRaises(ValueError):
                CHECKS.plan(event(), [path], CONFIG, BRANCHES)


class AggregateTests(unittest.TestCase):
    def test_tool_checks_cannot_be_skipped_or_hide_a_failure(self):
        for conclusion in ("skipped", "cancelled", "failure", "neutral", "pending"):
            candidate = results("tool-dependencies", "false")
            candidate["project"]["result"] = conclusion
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)

    def test_valid_full_documentation_and_delegated_modes(self):
        for mode in CHECKS.MODES:
            for security in ("true", "false"):
                self.assertEqual(CHECKS.verify(results(mode, security))["status"], "PASS")
        self.assertEqual(CHECKS.verify(results("delegated-sync"))["delegated_requirement"], "sync-test-reuse")

    def test_failure_cancellation_missing_and_required_skips_fail(self):
        for job in results():
            for result in ("failure", "cancelled", "skipped", "neutral", "pending", None):
                with self.subTest(job=job, result=result):
                    candidate = results()
                    candidate[job]["result"] = result
                    with self.assertRaises(ValueError):
                        CHECKS.verify(candidate)
            candidate = results()
            del candidate[job]
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)

    def test_invalid_route_and_unexpected_executions_do_not_hide_failures(self):
        for outputs in ({}, {"mode": "ordinary", "security": "false"},
                        {"mode": "full", "security": "maybe"}):
            candidate = results()
            candidate["route"]["outputs"] = outputs
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)
        candidate = results("documentation", "false")
        candidate["project"]["result"] = "failure"
        with self.assertRaises(ValueError):
            CHECKS.verify(candidate)

    def test_scoped_native_activation_uses_the_trusted_base_not_head(self):
        config = {**CONFIG, "native_required": False, "native_required_branches": ["main"]}
        legacy = results()
        del legacy["native"]
        del legacy["route"]["outputs"]["native"]
        for head in ("fix/main/example", "apple-ios", "main"):
            self.assertTrue(CHECKS.native_required(config, event("main", head)))
            with self.assertRaises(ValueError):
                CHECKS.verify(legacy, CHECKS.native_required(config, event("main", head)))
        for target in ("apple-main", "apple-ios", "android-main", "android-phone"):
            self.assertFalse(CHECKS.native_required(config, event(target, "main")))
            self.assertEqual(CHECKS.verify(legacy, CHECKS.native_required(config, event(target)))["status"], "PASS")
        manual = {"repository": event()["repository"], "ref": "refs/heads/main"}
        self.assertTrue(CHECKS.native_required(config, manual))
        self.assertTrue(CHECKS.native_required({**config, "native_required": True}, event("apple-ios")))
        self.assertFalse(CHECKS.native_required({**config, "native_required_branches": []}, None))
        for invalid in (None, {}, {"repository": {"full_name": "overte-org/overte", "id": 1}}):
            with self.assertRaises(ValueError):
                CHECKS.native_required(config, invalid)
        wrong = deepcopy(event())
        wrong["pull_request"]["base"]["repo"] = {"full_name": "contributor/fork", "id": 123}
        with self.assertRaises(ValueError):
            CHECKS.native_required(config, wrong)

    def test_legacy_cli_inherits_the_runner_event_for_scoped_activation(self):
        trusted, _ = inactive_browser_trusted_checkout(self)
        legacy = results()
        del legacy["native"]
        del legacy["route"]["outputs"]["native"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'event.json'
            for target in ('main', 'apple-ios'):
                payload = event(target)
                path.write_text(json.dumps(payload))
                result = subprocess.run([sys.executable, str(trusted / 'tools/repository-checks/check.py'),
                                         'verify', '--needs-json', json.dumps(legacy)],
                                        env={**os.environ, 'GITHUB_EVENT_PATH': str(path)}, capture_output=True)
                self.assertEqual(result.returncode == 0, not CHECKS.native_required(CONFIG, payload),
                                 result.stderr.decode())

    def test_cli_returns_nonzero_for_failed_aggregate(self):
        candidate = results()
        candidate["documentation"]["result"] = "failure"
        result = subprocess.run([sys.executable, str(ROOT / "tools/repository-checks/check.py"),
                                 "verify", "--needs-json", json.dumps(candidate)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_manifest_keeps_both_aggregate_and_independent_sync_gate_required(self):
        manifest = json.loads((ROOT / ".github/rulesets/permanent-branches.json").read_text())
        required = next(rule for rule in manifest["rules"] if rule["type"] == "required_status_checks")
        entries = required["parameters"]["required_status_checks"]
        self.assertEqual({item["context"] for item in entries}, set(CONFIG["required_contexts"]))
        self.assertTrue(all(item["integration_id"] == 15368 for item in entries))
        source = (ROOT / ".github/workflows/repository-checks.yml").read_text()
        self.assertIn("if: always()", source)
        import yaml
        jobs = yaml.safe_load(source)['jobs']
        dependencies = set(jobs['repository-checks']['needs'])
        required_jobs = {'route', 'project', 'documentation', 'workflow-security'}
        self.assertTrue(required_jobs <= dependencies)
        generation = PACKAGES.validate_wiring(ROOT)
        metadata_callers = {
            'npm-consumers-metadata-edits-v1': 'metadata-edits/repository-checks.yml',
            'android-owned-npm5-sync-ci-v1': 'android-owned/repository-checks.yml',
            'protected-producer-metadata-ci-v1': 'producers/repository-checks.yml',
            'protected-producer-seven-target-ci-v1': 'producers/repository-checks.yml',
        }
        metadata = generation in metadata_callers
        if metadata:
            self.assertEqual(source, (ROOT / 'tools/repository-checks/workflows' / metadata_callers[generation]).read_text())
        protected = generation in ('protected-producer-metadata-ci-v1', 'protected-producer-seven-target-ci-v1')
        if generation == 'android-owned-npm5-sync-ci-v1' or protected:
            spec = importlib.util.spec_from_file_location('aggregate_android_generation',
                ROOT / 'tools/repository-checks/android_gate.py')
            android = importlib.util.module_from_spec(spec); spec.loader.exec_module(android)
            tree = {}
            paths = PACKAGES.METADATA_WORKFLOW_PATHS if protected else PACKAGES.CONSUMER_WORKFLOW_PATHS
            for relative in (*paths, '.github/workflows/android-required.yml'):
                path = ROOT / relative
                self.assertTrue(path.is_file() and not path.is_symlink() and not path.stat().st_mode & 0o111)
                tree[relative] = android._blob(path.read_bytes())
            self.assertEqual(android.validate_tree_wiring(tree), generation)
            self.assertEqual(dependencies, required_jobs | {'native', 'android'})
        else:
            self.assertTrue(dependencies <= required_jobs | {'native', 'direct-browser', 'browser-client'})
        if CONFIG.get('native_required', False) or 'main' in CONFIG.get('native_required_branches', []):
            self.assertIn('native', dependencies)
        if 'main' in CONFIG.get('direct_browser_required_branches', []):
            self.assertIn('direct-browser', dependencies)
        if 'main' in CONFIG.get('browser_client_required_branches', []):
            self.assertIn('browser-client', dependencies)
        if metadata:
            self.assertEqual(jobs['repository-checks']['if'],
                "always() && (needs.route.result != 'success' || needs.route.outputs.metadata_only != 'true')")
            for name in dependencies - {'route'} | {'repository-checks'}:
                self.assertEqual(jobs[name]['name'],
                    "${{ needs.route.result == 'success' && needs.route.outputs.metadata_only == 'true' && '" + name +
                    " (metadata unchanged)' || '" + name + "' }}")
        else:
            self.assertEqual(jobs['repository-checks']['if'], 'always()')
        self.assertNotIn("paths:", source)
        self.assertNotIn("secrets:", source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn(": write", source)

    def test_reusable_concurrency_groups_do_not_cancel_the_caller(self):
        workflows = ROOT / ".github/workflows"
        groups = []
        for name in ("repository-checks.yml", "project-tests.yml", "documentation-checks.yml", "workflow-security.yml"):
            text = (workflows / name).read_text()
            groups.append(text.split("  group: ", 1)[1].splitlines()[0])
        self.assertEqual(len(groups), len(set(groups)))
        self.assertTrue(all("github.workflow" not in group for group in groups))

    def test_new_governance_inputs_are_bound_to_parent_qualification(self):
        import fnmatch
        reuse = json.loads((ROOT / ".github/sync-test-reuse.json").read_text())
        for path in (".github/repository-checks.json", ".github/repository-health.json",
                     "tools/repository-checks/check.py", "tools/repository-maintenance/check.py",
                     "tools/repository-policy/check.py", "tools/repository-health/check.py",
                     "tests/requirements-repository.txt"):
            self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in reuse["qualified_inputs"]), path)



class NativeOwnerAggregateTests(unittest.TestCase):
    """Claim strings cannot replace current original native receipt authority."""
    def setUp(self):
        self.plan = {'candidate': 'a' * 40, 'plan': 'b' * 64, 'host_mode': 'full',
                     'tool_projects': [], 'package_set': []}
        self.needs = results()
        self.needs['route']['outputs'].update(PACKAGES.outputs(self.plan))
        self.needs['project']['outputs'] = {**PACKAGES.receipt(self.plan),
            'documentation_verified': 'true', 'workflow_contracts_verified': 'true'}
        self.needs['documentation']['result'] = 'skipped'
        self.needs['workflow-contracts'] = {'result': 'skipped', 'outputs': {}}
        self.proof = {'kind': 'current-original-pr-owners', 'qualification': False,
                      'reusable': False, 'verified': True,
                      'suites': sorted(CHECKS._NATIVE_DOCUMENTATION | {'workflow-contracts'})}
        self.calls = []
        def verify(candidate, event_, environment, adapter, *, demanded):
            self.calls.append((candidate, event_, set(demanded)))
            return deepcopy(self.proof)
        controller = SimpleNamespace(verify_current_owners=verify,
                                    producer_api=SimpleNamespace(Adapter=lambda: object()))
        self.enterContext(patch.object(CHECKS, 'native_owner_policy', return_value=controller))
        self.policy = SimpleNamespace(validate_wiring=lambda _: CHECKS._NATIVE_OWNER_GENERATION)
        self.enterContext(patch.object(CHECKS, 'package_policy', side_effect=lambda: self.policy))

    def bound(self, needs=None):
        return CHECKS.bound_project_owners(self.needs if needs is None else needs,
                                          ROOT, event(), 'a' * 40)

    def aggregate(self, represented):
        with patch.object(CHECKS, 'package_policy', return_value=PACKAGES):
            return CHECKS.verify(represented, package_plan=self.plan)

    def test_exact_native_owner_maps_passed_commands_without_mutating_original_jobs(self):
        original = deepcopy(self.needs)
        with self.assertRaises(ValueError):
            self.aggregate(self.needs)
        represented, proof = self.bound()
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')
        self.assertEqual(self.needs, original)
        self.assertEqual(represented['project']['outputs'], PACKAGES.receipt(self.plan))
        self.assertEqual(self.calls[0][2], CHECKS._NATIVE_DOCUMENTATION | {'workflow-contracts'})
        self.assertEqual(proof, self.proof)

    def test_only_exact_future22_adds_native_owner_semantics_without_changing21(self):
        for generation in (CHECKS._NATIVE_OWNER_GENERATION, 'protected-producer-original-default-v1'):
            self.policy.validate_wiring=lambda _,value=generation:value
            with self.subTest(generation=generation):
                represented,proof=self.bound()
                self.assertEqual(self.aggregate(represented)['status'],'PASS')
                self.assertEqual(proof,self.proof)
        self.policy.validate_wiring=lambda _:'protected-producer-original-default-v1-neighbor'
        with self.assertRaises(ValueError):self.bound()

    def test_false_claims_keep_real_standalone_checks_and_do_not_read_native_api(self):
        for key in CHECKS._NATIVE_OWNER_OUTPUTS:
            self.needs['project']['outputs'][key] = 'false'
        self.needs['documentation']['result'] = 'success'
        self.needs['workflow-contracts']['result'] = 'success'
        represented, proof = self.bound()
        self.assertIsNone(proof)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')
        self.needs['documentation']['result'] = 'skipped'
        represented, _ = self.bound()
        with self.assertRaises(ValueError): self.aggregate(represented)

    def test_unselected_security_needs_no_unused_contract_proof(self):
        self.needs['project']['outputs']['documentation_verified'] = 'false'
        self.needs['documentation']['result'] = 'success'
        self.needs['route']['outputs']['security'] = 'false'
        self.needs['workflow-security']['result'] = 'skipped'
        represented, proof = self.bound()
        self.assertIsNone(proof)
        self.assertFalse(self.calls)
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')

    def test_foreign_mixed_missing_or_malformed_claims_cannot_delegate(self):
        for generation in ('protected-producer-metadata-ci-v1', 'unknown', None):
            self.policy.validate_wiring = lambda _, value=generation: value
            with self.subTest(generation=generation), self.assertRaises(ValueError): self.bound()
        self.policy.validate_wiring = lambda _: CHECKS._NATIVE_OWNER_GENERATION
        for value in ('', 'TRUE', '1', True, None, []):
            wrong = deepcopy(self.needs); wrong['project']['outputs']['documentation_verified'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.bound(wrong)
        for key in (*self.needs['project']['outputs'], 'unknown_owner'):
            wrong = deepcopy(self.needs)
            if key == 'unknown_owner': wrong['project']['outputs'][key] = 'false'
            else: del wrong['project']['outputs'][key]
            with self.subTest(key=key), self.assertRaises(ValueError): self.bound(wrong)
        self.assertFalse(self.calls)

    def test_native_failure_missing_command_or_nonproof_result_never_maps_docs(self):
        for change in ({'verified': False}, {'qualification': True}, {'reusable': True},
                       {'kind': 'completed-foreign-owner'}, {'suites': ['documentation']}):
            original = deepcopy(self.proof); self.proof.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.bound()
            self.proof = original
        with patch.object(CHECKS, 'native_owner_policy', side_effect=ValueError('native proof unavailable')):
            with self.assertRaises(ValueError): self.bound()

    def test_native_docs_require_precisely_skipped_standalone_not_hidden_failure(self):
        for result_ in ('failure', 'cancelled', 'success', None):
            wrong = deepcopy(self.needs); wrong['documentation']['result'] = result_
            with self.subTest(result=result_), self.assertRaises(ValueError): self.bound(wrong)
        for result_ in ('failure', 'cancelled', 'skipped', None):
            wrong = deepcopy(self.needs); wrong['project']['result'] = result_
            with self.subTest(project=result_), self.assertRaises(ValueError): self.bound(wrong)

    def test_native_owner_preserves_all_other_job_and_exact_package_failures(self):
        represented, _ = self.bound()
        for job in ('native', 'workflow-security', 'project', 'route'):
            for state in ('failure', 'cancelled', 'skipped'):
                wrong = deepcopy(represented); wrong[job]['result'] = state
                with self.subTest(job=job, state=state), self.assertRaises(ValueError): self.aggregate(wrong)
        for key in PACKAGES.receipt(self.plan):
            wrong = deepcopy(represented); wrong['project']['outputs'][key] = 'forged'
            with self.subTest(key=key), self.assertRaises(ValueError): self.aggregate(wrong)

    def test_contract_fallback_is_required_without_native_proof_and_never_hides_failure(self):
        self.needs['project']['outputs'].update(documentation_verified='false', workflow_contracts_verified='false')
        self.needs['documentation']['result'] = 'success'
        for state in ('skipped', 'failure', 'cancelled', 'neutral', None):
            self.needs['workflow-contracts']['result'] = state
            with self.subTest(state=state), self.assertRaises(ValueError): self.bound()
        self.needs['workflow-contracts']['result'] = 'success'
        represented, proof = self.bound()
        self.assertIsNone(proof)
        self.assertFalse(self.calls)
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')
        self.needs['project']['result'] = 'skipped'
        self.needs['project']['outputs'] = {}
        self.plan['host_mode'] = 'documentation'
        self.needs['route']['outputs'].update(PACKAGES.outputs(self.plan))
        represented, proof = self.bound()
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')
        self.assertIsNone(proof)

    def test_native_contract_claim_requires_the_fallback_job_to_be_precisely_skipped(self):
        for changes in ({'result': 'success'}, {'result': 'failure'}, {'result': 'cancelled'},
                        {'outputs': {'unknown': ''}}, {'outputs': 'malformed'}):
            wrong = deepcopy(self.needs); wrong['workflow-contracts'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.bound(wrong)
        wrong = deepcopy(self.needs); del wrong['workflow-contracts']
        with self.assertRaises(ValueError): self.bound(wrong)
        self.assertFalse(self.calls)

    def test_fresh_isolated_current_owner_imports_stay_inside_the_fixed_controller_graph(self):
        # The actual outer CLI calls this boundary BEFORE loading unrelated
        # browser/Android routers. A fresh interpreter catches real imports;
        # parent unittest mocks or ambient PYTHONPATH cannot make it pass.
        program = r"""
import importlib.util, json, sys
from pathlib import Path
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('fresh_owner_checks',root/'tools/repository-checks/check.py')
checks=importlib.util.module_from_spec(spec);sys.modules[spec.name]=checks;spec.loader.exec_module(checks)
producer=checks.native_owner_policy()
allowed=set(producer.controller_sources(producer._host_policy()))
reached=set()
for module in tuple(sys.modules.values()):
    source=getattr(module,'__file__',None)
    if source and Path(source).resolve().is_relative_to(root):
        reached.add(Path(source).resolve().relative_to(root).as_posix())
assert reached <= allowed, sorted(reached-allowed)
assert 'tools/repository-checks/check.py' in reached
assert 'tools/test-evidence/source_admission.py' in reached
assert 'tools/repository-checks/browser_cpu.py' not in reached
assert 'tools/repository-checks/android_gate.py' not in reached
print(json.dumps(sorted(reached)))
"""
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', program, str(ROOT)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tools/test-evidence/producer_workflow.py', json.loads(result.stdout))

    def test_unselected_project_retains_the_existing_documentation_route(self):
        self.plan['host_mode'] = 'documentation'
        self.needs = results('documentation', 'false')
        self.needs['route']['outputs'].update(PACKAGES.outputs(self.plan))
        self.needs['project']['outputs'] = {}
        self.needs['workflow-contracts'] = {'result': 'skipped', 'outputs': {}}
        represented, proof = self.bound()
        self.assertIsNone(proof)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.aggregate(represented)['status'], 'PASS')


class DirectBrowserTests(unittest.TestCase):
    def test_prospective_transport_wiring_requires_selected_jobs_and_shared_fixtures(self):
        import ast
        import yaml
        templates = ROOT / 'tools/repository-checks/workflows'
        workflow = yaml.safe_load((templates / 'browser-direct-client.yml').read_text())
        caller = yaml.safe_load((templates / 'repository-checks.yml').read_text())
        triggers = workflow.get('on', workflow.get(True))
        self.assertIn('workflow_call', triggers)
        self.assertNotIn('pull_request', triggers, 'The aggregate replaces the standalone PR consumer')
        jobs = workflow['jobs']
        self.assertEqual(set(jobs['verify']['needs']), {'route', 'browser', 'native'})
        self.assertEqual(jobs['verify']['if'], 'always()')
        for lane, output in (('browser', 'direct_browser'), ('native', 'direct_native')):
            self.assertEqual(jobs[lane]['needs'], 'route')
            self.assertEqual(jobs[lane]['if'], f"needs.route.outputs.{output} == 'true'")
        verifier = next(step for step in jobs['verify']['steps'] if step.get('id') == 'verify')
        self.assertIn('trusted/tools/repository-checks/check.py direct-verify', verifier['run'])
        self.assertIn('--needs-json "$DIRECT_RESULTS"', verifier['run'])
        self.assertIn('--sha "$GITHUB_SHA"', verifier['run'])
        self.assertIn('direct-browser', caller['jobs']['repository-checks']['needs'])
        consumer = caller['jobs']['direct-browser']
        self.assertEqual(consumer['uses'], './.github/workflows/browser-direct-client.yml')
        self.assertEqual(consumer['permissions'], {'contents': 'read', 'packages': 'read'})
        self.assertEqual(set(consumer['with']), {'expected_candidate', 'expected_plan',
                                                'browser_required', 'native_required'})
        aggregate = caller['jobs']['repository-checks']['steps'][-1]
        self.assertIn('--candidate candidate --sha "$GITHUB_SHA"', aggregate['run'])
        # These browser JSON files are read by actual C++ tests, so an extension-
        # only frontend exemption would silently miss a required native consumer.
        fixtures = set()
        for source in (ROOT / 'tests/browser-direct-transport/src').glob('*.cpp'):
            fixtures.update(re.findall(r'QFINDTESTDATA\("\.\./\.\./\.\./(browser-direct-client/[^\"]+)"\)',
                                       source.read_text()))
        self.assertTrue(fixtures)
        for fixture in fixtures:
            selected = CHECKS.direct_browser_plan([fixture])
            self.assertTrue(selected['browser'] and selected['native'], fixture)
        driver = ast.parse((ROOT / 'browser-direct-client/tools/ci-native.py').read_text())
        for node in ast.walk(driver):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith(('tools/native-tests/', 'tools/conan-profiles/'))):
                self.assertTrue(CHECKS.direct_browser_plan([node.value])['native'], node.value)

    def test_push_routing_cannot_omit_transitive_dependencies(self):
        import yaml
        workflow = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/browser-direct-client.yml').read_text())
        events = workflow.get('on', workflow.get(True))
        push = events['push']
        self.assertEqual(set(push), {'branches'})
        self.assertEqual(set(push['branches']), set(BRANCHES))
        for path in ('LICENSE', 'interface/resources/meshes/mannequin/mannequin.fbx',
                     'libraries/shared/src/Constants.h', 'libraries/avatars/src/AvatarData.cpp',
                     'libraries/audio/src/AudioConstants.h', 'tools/native-tests/packages.py',
                     'CMakeLists.txt', 'conanfile.py'):
            selected = CHECKS.direct_browser_plan([path])
            self.assertTrue(selected['browser'] or selected['native'], path)

    def candidate_plan(self, browser=True, native=False):
        return {"browser": browser, "native": native, "candidate": "a" * 40, "plan": "b" * 64}

    def inner_results(self, selected):
        return {"route": {"result": "success", "outputs": CHECKS.direct_outputs(selected)},
                **{lane: {"result": "success" if selected[lane] else "skipped"}
                   for lane in ("browser", "native")}}

    def outer_results(self, selected):
        candidate = results()
        candidate["route"]["outputs"].update(CHECKS.direct_outputs(selected))
        candidate["direct-browser"] = {"result": "success", "outputs": {
            "verified": "true", "candidate": selected["candidate"], "plan": selected["plan"]}}
        if not selected["browser"] and not selected["native"]:
            candidate["direct-browser"] = {"result": "skipped", "outputs": {}}
        return candidate

    def test_frontend_docs_and_lab_tools_do_not_build_native_products(self):
        for path in ("browser-direct-client/src/world.ts", "browser-direct-client/src/style.css",
                     "browser-direct-client/package-lock.json", "browser-direct-client/lab/build-native.py",
                     "browser-direct-client/e2e/native-build-evidence.test.py", "browser-direct-client/README.md"):
            with self.subTest(path=path):
                self.assertFalse(CHECKS.direct_browser_plan([path])["native"])
        self.assertTrue(CHECKS.direct_browser_plan(["browser-direct-client/src/world.ts"])["browser"])
        self.assertFalse(CHECKS.direct_browser_plan(["browser-direct-client/README.md"])["browser"])
        for path in ("tools/repository-checks/check.py", "tests/repository-checks-test.py", "docs/ci.md",
                     "tools/test-evidence/execution.py", "tools/test-evidence/fixture.json"):
            self.assertEqual(CHECKS.direct_browser_plan([path]),
                             {"browser": False, "native": False, "reasons": {"browser": [], "native": []}})
        for path in CHECKS.DIRECT_UNRELATED_NATIVE_TOOLS:
            selected = CHECKS.direct_browser_plan([path])
            self.assertFalse(selected["browser"] or selected["native"], path)

    def test_s3_npm_manifests_do_not_select_optional_browser_or_native_products(self):
        manifests = ["script-archive/marketplace/S3Server/package.json",
                     "script-archive/marketplace/S3Server/package-lock.json"]
        empty = {"browser": False, "native": False,
                 "reasons": {"browser": [], "native": []}}
        self.assertEqual(CHECKS.direct_browser_plan(manifests), empty)
        for path in manifests:
            self.assertEqual(CHECKS.direct_browser_plan([path]), empty)
            self.assertTrue(CHECKS.direct_browser_plan([path], False)["native"])
            self.assertTrue(CHECKS.direct_browser_plan([path, "libraries/shared/src/AABox.cpp"])["native"])
        for name in ("CMakeLists.txt", "input.cmake", "resources.qrc", "unknown.json", "new.cpp"):
            self.assertTrue(CHECKS.direct_browser_plan(
                [*manifests, f"script-archive/marketplace/S3Server/{name}"])["native"])
        browser = CHECKS.direct_browser_plan(
            [*manifests, "browser-direct-client/package-lock.json"])
        self.assertTrue(browser["browser"])
        self.assertFalse(browser["native"])

    def test_native_fixtures_libraries_and_complete_build_context_require_transport(self):
        paths = sorted(CHECKS.DIRECT_NATIVE_FIXTURES) + [
            "libraries/avatars/src/AvatarData.cpp", "libraries/audio/src/AudioConstants.h",
            "libraries/shared/src/GLMHelpers.h", "libraries/script-engine/src/ScriptEngine.cpp",
            "libraries/model-networking/src/ModelCache.cpp", "libraries/new-component/src/input.h",
            "domain-server/src/LocalUserPolicy.h", "assignment-client/src/entities/BrowserEntityProjection.h",
            "tests/browser-direct-transport/src/WebRTCTransportTests.cpp", "tests/networking/src/PacketTests.cpp",
            "cmake/macros/TargetDataChannel.cmake", "CMakeLists.txt", "conanfile.py", "conan.lock",
            ".github/native-tests.json", "tools/native-tests/conan-linux.lock", "tools/conan-profiles/linux",
            "browser-direct-client/tools/ci-native.py", "browser-direct-client/lab/new.cpp",
            "browser-direct-client/lab/CMakeLists.txt", "browser-direct-client/new.unknown",
            "tools/test-evidence/new.cpp", "tools/test-evidence/new.unknown"]
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(CHECKS.direct_browser_plan([path])["native"])
        for path in CHECKS.DIRECT_NATIVE_FIXTURES:
            self.assertTrue(CHECKS.direct_browser_plan([path])["browser"])
        mixed = CHECKS.direct_browser_plan(["browser-direct-client/src/world.ts", paths[0]])
        self.assertTrue(mixed["browser"] and mixed["native"])

    def test_browser_generation_assets_and_nonregular_unknown_inputs_are_not_omitted(self):
        for path in CHECKS.DIRECT_BROWSER_ASSETS | {"libraries/networking/src/udt/PacketHeaders.cpp"}:
            self.assertTrue(CHECKS.direct_browser_plan([path])["browser"], path)
        for paths, regular in (([], True), (["browser-direct-client/README.md"], False),
                               (["unowned/new-input"], True)):
            selected = CHECKS.direct_browser_plan(paths, regular)
            self.assertTrue(selected["browser"] and selected["native"])
        self.assertFalse(CHECKS.direct_browser_plan([], verified_empty=True)["native"])
        with self.assertRaises(ValueError):
            CHECKS.direct_browser_plan(["a"], verified_empty=True)
        for path in ("../outside", "/absolute", "", "bad\x00path", "bad\\path", 123):
            with self.subTest(path=path), self.assertRaises(ValueError):
                CHECKS.direct_browser_plan([path])

    def test_inner_selected_failure_skip_missing_and_misbound_route_fail(self):
        selected = self.candidate_plan(True, True)
        good = self.inner_results(selected)
        self.assertEqual(CHECKS.verify_direct(good, selected)["verified"], "true")
        for lane in ("route", "browser", "native"):
            for conclusion in ("failure", "skipped", "cancelled", None):
                bad = deepcopy(good)
                bad[lane]["result"] = conclusion
                with self.subTest(lane=lane, conclusion=conclusion), self.assertRaises(ValueError):
                    CHECKS.verify_direct(bad, selected)
            bad = deepcopy(good)
            del bad[lane]
            with self.assertRaises(ValueError):
                CHECKS.verify_direct(bad, selected)
        for field in CHECKS.direct_outputs(selected):
            bad = deepcopy(good)
            bad["route"]["outputs"][field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHECKS.verify_direct(bad, selected)
        unselected = self.candidate_plan(True, False)
        good = self.inner_results(unselected)
        self.assertEqual(CHECKS.verify_direct(good, unselected)["verified"], "true")
        good["native"]["result"] = "success"
        with self.assertRaises(ValueError):
            CHECKS.verify_direct(good, unselected)

    def test_outer_receipt_is_required_even_before_branch_activation(self):
        selected = self.candidate_plan()
        good = self.outer_results(selected)
        self.assertEqual(CHECKS.verify(good, direct_plan=selected)["status"], "PASS")
        with self.assertRaises(ValueError):
            CHECKS.verify(good)
        for field in ("candidate", "plan", "verified"):
            bad = deepcopy(good)
            bad["direct-browser"]["outputs"][field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHECKS.verify(bad, direct_plan=selected)
        for conclusion in ("failure", "skipped", "cancelled", None):
            bad = deepcopy(good)
            bad["direct-browser"]["result"] = conclusion
            with self.assertRaises(ValueError):
                CHECKS.verify(bad, direct_plan=selected)
        good["route"]["outputs"]["direct_native"] = "true"
        with self.assertRaises(ValueError):
            CHECKS.verify(good, direct_plan=selected)
        empty = self.candidate_plan(False, False)
        self.assertEqual(CHECKS.verify(self.outer_results(empty), direct_plan=empty)["status"], "PASS")

    def test_only_trusted_base_activation_permits_legacy_omission(self):
        config = {**CONFIG, "direct_browser_required_branches": ["main"]}
        self.assertFalse(CHECKS.direct_browser_required({**config, "direct_browser_required_branches": []}, None))
        for head in ("fix/main/example", "apple-ios", "main"):
            self.assertTrue(CHECKS.direct_browser_required(config, event("main", head)))
        for base in ("apple-ios", "android-main", "android-vr-pico"):
            self.assertFalse(CHECKS.direct_browser_required(config, event(base, "main")))
        self.assertEqual(CHECKS.verify(results(), require_direct=False)["status"], "PASS")
        with self.assertRaisesRegex(ValueError, "aggregate missing"):
            CHECKS.verify(results(), require_direct=True)
        for payload in (None, {}, {"repository": {"full_name": "overte-org/overte", "id": 1}}):
            with self.assertRaises(ValueError):
                CHECKS.direct_browser_required(config, payload)
        bad = event()
        bad["pull_request"]["base"]["repo"] = {"full_name": "contributor/fork", "id": 12}
        with self.assertRaises(ValueError):
            CHECKS.direct_browser_required(config, bad)

    def test_candidate_plan_cli_rechecks_exact_merge_tree_and_trusted_templates(self):
        trusted, trusted_packages = inactive_browser_trusted_checkout(self)
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null",
                                                "-c", "commit.gpgsign=false", *args],
                                               cwd=candidate, text=True, stderr=subprocess.PIPE).strip()
            git("init", "-q", "--initial-branch=main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            workflows = candidate / ".github/workflows"
            workflows.mkdir(parents=True)
            for name in CHECKS.DIRECT_WORKFLOWS:
                (workflows / name).write_bytes((ROOT / "tools/repository-checks/workflows" / name).read_bytes())
            # Exercise the approved combined generation once the trusted main
            # policy requires package receipts; legacy byte compatibility has
            # independent inactive-policy coverage below.
            for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml'):
                (workflows / name).write_bytes((PACKAGES.TEMPLATES / name).read_bytes())
            (workflows / 'repository-checks.yml').write_bytes(
                (PACKAGES.TEMPLATES / 'repository-checks-direct.yml').read_bytes())
            source = candidate / "browser-direct-client/lab/manage.py"
            source.parent.mkdir(parents=True)
            source.write_text("# before\n")
            git("add", ".")
            git("commit", "-qm", "Base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "fix/main/example")
            source.write_text("# after\n")
            git("add", ".")
            git("commit", "-qm", "Head")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "-qm", "Candidate", "fix/main/example")
            sha = git("rev-parse", "HEAD")
            payload = event()
            payload["pull_request"]["base"]["sha"] = base
            payload["pull_request"]["head"]["sha"] = head
            selected = CHECKS.direct_candidate_plan(candidate, payload, sha)
            self.assertTrue(selected["browser"])
            self.assertFalse(selected["native"])
            push = {"repository": payload["repository"], "before": base, "after": sha}
            pushed = CHECKS.direct_candidate_plan(candidate, push, sha)
            self.assertTrue(pushed["browser"])
            self.assertFalse(pushed["native"])
            empty = CHECKS.direct_candidate_plan(candidate, {**push, "before": sha}, sha)
            self.assertFalse(empty["browser"] or empty["native"])
            with self.assertRaises(ValueError):
                CHECKS.direct_candidate_plan(candidate, {**push, "after": head}, sha)
            CHECKS.validate_direct_wiring(candidate)
            event_file, output = candidate / "event.json", candidate / "outputs"
            event_file.write_text(json.dumps(payload))
            common = ["--event", str(event_file), "--candidate", str(candidate), "--sha", sha]
            command = [sys.executable, str(trusted / "tools/repository-checks/check.py")]
            run = subprocess.run(command + ["direct-plan", *common, "--output", str(output),
                                           "--expected-candidate", sha, "--expected-plan", selected["plan"],
                                           "--expected-browser", "true", "--expected-native", "false"], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            run = subprocess.run(command + ["direct-plan", *common, "--output", str(output),
                                           "--expected-candidate", sha, "--expected-plan", selected["plan"],
                                           "--expected-browser", "true", "--expected-native", "true"], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            run = subprocess.run(command + ["direct-verify", *common, "--output", str(output),
                                           "--needs-json", json.dumps(self.inner_results(selected))], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            outer = self.outer_results(selected)
            package_plan = trusted_packages.candidate_plan(candidate, payload, sha)
            outer['route']['outputs'].update(PACKAGES.outputs(package_plan))
            outer['project']['outputs'] = PACKAGES.receipt(package_plan)
            run = subprocess.run(command + ["verify", *common, "--needs-json", json.dumps(outer)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            outer["direct-browser"]["outputs"]["plan"] = "0" * 64
            run = subprocess.run(command + ["verify", *common, "--needs-json", json.dumps(outer)], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            with self.assertRaises(ValueError):
                CHECKS.direct_candidate_plan(candidate, payload, head)
            changed = workflows / "browser-direct-client.yml"
            changed.write_text(changed.read_text().replace("    if: always()", "    if: false"))
            with self.assertRaises(ValueError):
                CHECKS.validate_direct_wiring(candidate)
            changed.unlink()
            changed.symlink_to(ROOT / "tools/repository-checks/workflows/browser-direct-client.yml")
            with self.assertRaises(ValueError):
                CHECKS.validate_direct_wiring(candidate)


class ToolDependencyTests(unittest.TestCase):
    def test_push_inventory_uses_both_sides_and_exact_commit_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                                                '-c', 'commit.gpgsign=false', *args], cwd=root, text=True).strip()
            git('init', '-q', '--initial-branch=main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'tools/jsdoc').mkdir(parents=True)
            manifest = root / 'tools/jsdoc/package-lock.json'
            manifest.write_text('{}')
            (root / 'native.cpp').write_text('initial source')
            git('add', '.')
            git('commit', '-qm', 'Base')
            base = git('rev-parse', 'HEAD')
            manifest.write_text('{"updated":true}')
            git('commit', '-qam', 'Tool update')
            updated = git('rev-parse', 'HEAD')
            payload = {'repository': event()['repository'], 'before': base, 'after': updated}
            self.assertEqual(TOOLS.push_projects(root, payload), ('tools/jsdoc',))
            for repository in ({'full_name': 'noah-be/overte', 'id': 1319052603},
                               {'full_name': 'noah-l-frank/overte', 'id': 42}):
                with self.subTest(repository=repository), self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    TOOLS.push_projects(root, {**payload, 'repository': repository})
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'before': '9' * 40}), ())
            with self.assertRaises(ValueError):
                TOOLS.push_projects(root, {**payload, 'after': base})
            with self.assertRaises(ValueError):
                TOOLS.push_projects(root, {**payload, 'repository': {'full_name': 'overte-org/overte', 'id': 1}})
            manifest.chmod(0o755)
            git('commit', '-qam', 'Executable manifest')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            manifest.chmod(0o644)
            (root / 'native.cpp').write_text('source')
            git('add', '.')
            git('commit', '-qm', 'Mixed source update')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            git('mv', 'native.cpp', 'server-console-package-lock.md')
            git('commit', '-qm', 'Rename source to Markdown')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            self.assertEqual(TOOLS.push_projects(root, {}), ())

    def test_unknown_duplicate_and_empty_projects_are_rejected_before_execution(self):
        with patch.object(TOOLS.subprocess, "run") as run:
            for projects in ([], ["browser-client"], ["tools/jsdoc", "tools/jsdoc"], ["../tools/jsdoc"]):
                with self.assertRaises(ValueError):
                    TOOLS.run(ROOT, projects)
            run.assert_not_called()

    def test_install_or_audit_failure_stops_before_behavior_checks(self):
        for fail_at in (0, 1):
            failure = subprocess.CalledProcessError(1, "npm")
            with patch.object(TOOLS.subprocess, "run", side_effect=[None] * fail_at + [failure]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    TOOLS.run(ROOT, ["server-console"])
                self.assertEqual(run.call_count, fail_at + 1)

    def test_dependency_install_disables_scripts_and_the_audit_includes_all_severities(self):
        with patch.object(TOOLS.subprocess, "run") as run:
            TOOLS.run(ROOT, ["server-console"])
            calls = [call.args[0] for call in run.call_args_list]
            self.assertIn("--ignore-scripts", calls[0])
            self.assertEqual(calls[1], ("npm", "audit", "--audit-level=low"))
            self.assertEqual(calls[2], ("npm", "test"))
            self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))


class PackageChecksTests(unittest.TestCase):
    def selected(self, paths, regular=True, **kwargs):
        return PACKAGES.select(paths, regular, **kwargs)

    def test_browser_manifests_require_internal_opt_in_and_select_the_exact_package_union(self):
        browser = PACKAGES.BROWSER
        s3 = PACKAGES.S3
        for name in ('package.json', 'package-lock.json'):
            path = browser + '/' + name
            self.assertEqual(self.selected([path])['host_mode'], 'full')
            self.assertEqual(self.selected([path])['package_set'], [])
            self.assertEqual(TOOLS.affected_projects([path], include_s3=True), ())
            with self.assertRaises(ValueError):
                TOOLS.validate_projects([browser], include_s3=True)
            self.assertEqual(self.selected([path], include_browser=True), {
                'host_mode': 'package-dependencies', 'tool_projects': [], 'package_set': [browser]})
        paths = [browser + '/package-lock.json', s3 + '/package-lock.json']
        self.assertEqual(self.selected(paths, include_browser=True), {
            'host_mode': 'package-dependencies', 'tool_projects': [], 'package_set': [s3, browser]})
        paths += ['server-console/package.json', 'tools/jsdoc/package-lock.json']
        self.assertEqual(self.selected(paths, include_browser=True), {
            'host_mode': 'tool-dependencies', 'tool_projects': ['server-console', 'tools/jsdoc'],
            'package_set': [s3, browser]})

    def test_browser_opt_in_never_weakens_mixed_unknown_or_nonregular_fallback(self):
        manifests = [PACKAGES.BROWSER + '/package-lock.json', PACKAGES.S3 + '/package-lock.json']
        for extra in ('native.cpp', 'browser-client/src/changed.ts', 'browser-client/package-extra.json',
                      'browser-client/.npmrc', 'unknown', 'tools/repository-checks/check.py'):
            selected = self.selected([*manifests, extra], include_browser=True)
            self.assertEqual(selected['host_mode'], 'full', extra)
            self.assertEqual(selected['package_set'], [PACKAGES.S3, PACKAGES.BROWSER])
        for options in ({'regular': False}, {'unknown': True}):
            selected = self.selected(manifests, include_browser=True, **options)
            self.assertEqual(selected['host_mode'], 'full')
            self.assertEqual(selected['package_set'], [PACKAGES.S3, PACKAGES.BROWSER])
        self.assertEqual(self.selected([], unknown=True, include_browser=True)['package_set'], [PACKAGES.S3])
        self.assertEqual(self.selected(manifests, legacy_mode='delegated-sync', include_browser=True)['host_mode'],
                         'delegated-sync')

    def test_browser_profile_uses_existing_scripts_once_and_propagates_each_failure(self):
        expected = [('npm', 'ci', '--ignore-scripts', '--no-fund', '--no-audit'),
                    ('npm', 'audit', '--audit-level=low'), ('npm', 'run', 'build'), ('npm', 'test')]
        with patch.object(TOOLS.subprocess, 'run') as run:
            TOOLS.run(ROOT, [PACKAGES.BROWSER], include_browser=True)
        self.assertEqual([call.args[0] for call in run.call_args_list], expected)
        self.assertTrue(all(call.kwargs['cwd'] == ROOT / PACKAGES.BROWSER and call.kwargs['check']
                            for call in run.call_args_list))
        for failure in range(len(expected)):
            with self.subTest(failure=failure), patch.object(TOOLS.subprocess, 'run',
                    side_effect=[None] * failure + [subprocess.CalledProcessError(1, 'npm')]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    TOOLS.run(ROOT, [PACKAGES.BROWSER], include_browser=True)
                self.assertEqual(run.call_count, failure + 1)

    def test_browser_profile_rejects_unreviewed_lifecycle_or_script_changes_before_install(self):
        original = json.loads((ROOT / 'browser-client/package.json').read_text())
        for name in (*TOOLS.BROWSER_MANIFEST_SCRIPTS, 'postbuild', 'pretest', 'posttest'):
            with self.subTest(script=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                package = root / PACKAGES.BROWSER
                package.mkdir()
                manifest = deepcopy(original)
                manifest['scripts'][name] = 'node -e "process.exit(0)"'
                (package / 'package.json').write_text(json.dumps(manifest))
                (package / 'package-lock.json').write_text('{}')
                with patch.object(TOOLS.subprocess, 'run') as run, self.assertRaises(ValueError):
                    TOOLS.run(root, [PACKAGES.BROWSER], include_browser=True)
                run.assert_not_called()
        with patch.object(TOOLS.subprocess, 'run') as run, self.assertRaises(ValueError):
            TOOLS.run(ROOT, [PACKAGES.BROWSER, PACKAGES.BROWSER], include_browser=True)
        run.assert_not_called()

    def test_browser_and_s3_union_executes_each_package_once_without_unrelated_tool_commands(self):
        with patch.object(TOOLS.subprocess, 'run') as run:
            TOOLS.run(ROOT, [PACKAGES.S3, PACKAGES.BROWSER], include_s3=True, include_browser=True)
        for project, count in ((PACKAGES.S3, 3), (PACKAGES.BROWSER, 4)):
            calls = [call.args[0] for call in run.call_args_list if call.kwargs['cwd'] == ROOT / project]
            self.assertEqual(len(calls), count)
            self.assertEqual(sum(command[:2] == ('npm', 'ci') for command in calls), 1)
            self.assertEqual(sum(command[:2] == ('npm', 'audit') for command in calls), 1)
            self.assertEqual(sum(command[:2] == ('npm', 'test') for command in calls), 1)
        self.assertEqual(len(run.call_args_list), 7)

    def test_browser_candidate_plan_and_execution_require_trusted_opt_in_not_event_json(self):
        root, git, base = self.fixture()
        browser = root / PACKAGES.BROWSER
        browser.mkdir()
        (browser / 'package.json').write_bytes((ROOT / 'browser-client/package.json').read_bytes())
        (browser / 'package-lock.json').write_text('{}')
        git('add', '.'); git('commit', '-qm', 'Add ordinary browser fixture manifests')
        base = git('rev-parse', 'HEAD')
        (browser / 'package-lock.json').write_text('{"updated":true}')
        git('commit', '-qam', 'Browser fixture lock update'); head = git('rev-parse', 'HEAD')
        payload = self.push(base, head)
        payload['include_browser'] = True
        payload['browser_client_required_branches'] = ['main']
        legacy = PACKAGES.candidate_plan(root, payload, head)
        self.assertEqual((legacy['host_mode'], legacy['package_set']), ('full', []))
        selected = PACKAGES.candidate_plan(root, payload, head, include_browser=True)
        self.assertEqual((selected['host_mode'], selected['package_set']), ('package-dependencies', [PACKAGES.BROWSER]))
        self.assertNotEqual(selected['plan'], legacy['plan'])
        seen = []
        def run(candidate, projects, **options):
            self.assertNotIn('GH_TOKEN', os.environ)
            self.assertNotIn('GITHUB_OUTPUT', os.environ)
            seen.append((candidate, projects, options))
        with patch.object(PACKAGES, 'tools', return_value=SimpleNamespace(run=run)), patch.dict(os.environ,
                {'GH_TOKEN': 'private', 'GITHUB_OUTPUT': 'private-command'}):
            self.assertEqual(PACKAGES.execute(root, selected, 'package-checks', include_browser=True),
                             PACKAGES.receipt(selected, 'package-checks'))
            self.assertEqual(os.environ['GH_TOKEN'], 'private')
        self.assertEqual(seen, [(root, [PACKAGES.BROWSER], {'include_s3': True, 'include_browser': True})])
        for outcome in ('failure', 'cancelled', 'skipped'):
            needs = self.needs(selected)
            needs['package-checks']['result'] = outcome
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                PACKAGES.verify(needs, selected)

    def test_legacy_capabilities_stay_bounded_under_explicit_inactive_policy(self):
        path = PACKAGES.S3 + '/package-lock.json'
        self.assertEqual(TOOLS.affected_projects([path]), ())
        with self.assertRaises(ValueError):
            TOOLS.validate_projects([PACKAGES.S3])
        self.assertEqual(CHECKS.plan(event(), [path], CONFIG, BRANCHES)['mode'], 'full')
        policy = SimpleNamespace(configuration=lambda: ({**CONFIG, 'package_checks_required_branches': []}, BRANCHES))
        with patch.object(PACKAGES, 'load', return_value=policy):
            for branch in BRANCHES:
                self.assertFalse(PACKAGES.activated(event(branch)))
                self.assertFalse(PACKAGES.activated({'repository': event()['repository'], 'ref': 'refs/heads/' + branch}))
        self.assertEqual(CHECKS.verify(results())['status'], 'PASS')

    def test_exact_s3_manifests_bound_the_package_lane_without_host_setup(self):
        for name in ('package.json', 'package-lock.json'):
            selected = self.selected([PACKAGES.S3 + '/' + name, 'docs/change.md'])
            self.assertEqual(selected, {'host_mode': 'package-dependencies', 'tool_projects': [],
                                        'package_set': [PACKAGES.S3]})
        selected = self.selected([PACKAGES.S3 + '/package-lock.json', 'tools/jsdoc/package.json'])
        self.assertEqual(selected['host_mode'], 'tool-dependencies')
        self.assertEqual(selected['tool_projects'], ['tools/jsdoc'])
        self.assertEqual(selected['package_set'], [PACKAGES.S3])

    def test_mixed_browser_native_unknown_source_and_nonregular_inputs_keep_both_owners(self):
        manifest = PACKAGES.S3 + '/package-lock.json'
        for path in ('browser-client/package-lock.json', 'browser-direct-client/src/world.ts',
                     'libraries/shared/src/AABox.cpp', 'CMakeLists.txt', 'new/unknown',
                     PACKAGES.S3 + '/index.js', PACKAGES.S3 + '/test.js',
                     PACKAGES.S3 + '/unknown.json', PACKAGES.S3 + '/CMakeLists.txt'):
            selected = self.selected([manifest, path])
            self.assertEqual(selected['host_mode'], 'full', path)
            self.assertEqual(selected['package_set'], [PACKAGES.S3], path)
        self.assertEqual(self.selected([manifest], False)['host_mode'], 'full')
        self.assertEqual(self.selected([], unknown=True)['package_set'], [PACKAGES.S3])
        self.assertEqual(self.selected([manifest], unknown=True)['host_mode'], 'full')
        self.assertEqual(self.selected([])['host_mode'], 'full')
        self.assertEqual(self.selected(['browser-client/package.json'])['package_set'], [])
        delegated = self.selected([manifest, 'tools/jsdoc/package-lock.json'], legacy_mode='delegated-sync')
        self.assertEqual(delegated['host_mode'], 'delegated-sync')
        self.assertEqual(delegated['tool_projects'], [])
        self.assertEqual(delegated['package_set'], [PACKAGES.S3])

    def test_package_paths_cannot_escape_or_smuggle_untrusted_selection(self):
        for path in ('../escape', '/absolute', 'a/../b', 'a//b', 'a\\b', '', None, 'bad\0name'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected([path])
        for projects in ([PACKAGES.S3, PACKAGES.S3], ['unknown'], ['../server-console']):
            with self.assertRaises(ValueError):
                TOOLS.validate_projects(projects, include_s3=True)

    def test_s3_executes_one_complete_audit_and_real_functional_command(self):
        with patch.object(TOOLS.subprocess, 'run') as run:
            TOOLS.run(ROOT, [PACKAGES.S3], include_s3=True)
        self.assertEqual([c.args[0] for c in run.call_args_list], [
            ('npm', 'ci', '--ignore-scripts', '--no-fund', '--no-audit'),
            ('npm', 'audit', '--audit-level=low'), ('npm', 'test')])
        self.assertTrue(all(c.kwargs['cwd'] == ROOT / PACKAGES.S3 and c.kwargs['check']
                            for c in run.call_args_list))
        for failure in range(3):
            with self.subTest(failure=failure), patch.object(TOOLS.subprocess, 'run',
                    side_effect=[None] * failure + [subprocess.CalledProcessError(1, 'npm')]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    TOOLS.run(ROOT, [PACKAGES.S3], include_s3=True)
                self.assertEqual(run.call_count, failure + 1)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='overte-package-contract-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git', '-c', 'commit.gpgsign=false', *args],
                                           cwd=root, text=True, stderr=subprocess.PIPE).strip()
        git('init', '-q', '--initial-branch=main')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        for name in PACKAGES.TEMPLATE_NAMES:
            if name == 'repository-checks-direct.yml':
                continue
            path = root / '.github/workflows' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((PACKAGES.TEMPLATES / name).read_bytes())
        folder = root / PACKAGES.S3
        folder.mkdir(parents=True)
        for name in ('package.json', 'package-lock.json'):
            (folder / name).write_text('{}')
        (root / '.gitignore').write_text('node_modules/\n')
        (root / 'native.cpp').write_text('source')
        git('add', '.'); git('commit', '-qm', 'Base fixture')
        return root, git, git('rev-parse', 'HEAD')

    def push(self, base, head):
        return {'repository': event()['repository'], 'before': base, 'after': head, 'ref': 'refs/heads/main'}

    def test_immutable_push_selection_covers_added_deleted_renamed_modes_and_missing_history(self):
        for change in ('add', 'edit', 'delete', 'rename', 'executable', 'symlink', 'submodule'):
            root, git, base = self.fixture()
            path = root / PACKAGES.S3 / 'package-lock.json'
            if change == 'add':
                path.unlink(); git('commit', '-qam', 'Before new manifest'); base = git('rev-parse', 'HEAD')
                path.write_text('{"new":true}')
            elif change == 'edit': path.write_text('{"changed":true}')
            elif change == 'delete': path.unlink()
            elif change == 'rename': git('mv', 'native.cpp', PACKAGES.S3 + '/README.md')
            elif change == 'executable': path.chmod(0o755)
            elif change == 'symlink': path.unlink(); path.symlink_to('package.json')
            else:
                path.unlink(); git('add', '-u')
                git('update-index', '--add', '--cacheinfo', '160000,' + base + ',' + PACKAGES.S3 + '/package-lock.json')
            if change != 'submodule': git('add', '-A')
            git('commit', '-qm', 'Changed package fixture')
            head = git('rev-parse', 'HEAD')
            plan = PACKAGES.candidate_plan(root, self.push(base, head), head)
            self.assertEqual(plan['host_mode'], 'package-dependencies' if change in ('add', 'edit', 'delete') else 'full', change)
            self.assertEqual(plan['package_set'], [PACKAGES.S3], change)
            self.assertEqual(plan['tree'], git('rev-parse', 'HEAD^{tree}'))
            unknown = PACKAGES.candidate_plan(root, self.push('9' * 40, head), head)
            self.assertTrue(unknown['unknown'])
            self.assertEqual(unknown['host_mode'], 'full')
            self.assertEqual(unknown['package_set'], [PACKAGES.S3])
            with self.assertRaises(ValueError): PACKAGES.candidate_plan(root, self.push(base, head), base)
        empty = PACKAGES.candidate_plan(root, self.push(head, head), head)
        self.assertEqual(empty['host_mode'], 'full')

    def test_exact_merge_and_foreign_head_candidate_cannot_change_identity(self):
        root, git, base = self.fixture()
        git('checkout', '-qb', 'fix/main/fixture')
        (root / PACKAGES.S3 / 'package-lock.json').write_text('{"updated":true}')
        git('commit', '-qam', 'Package change')
        head = git('rev-parse', 'HEAD')
        git('checkout', '-q', 'main'); git('merge', '-q', '--no-ff', '--no-edit', 'fix/main/fixture')
        merge = git('rev-parse', 'HEAD')
        payload = event(fork=True)
        payload['pull_request']['base']['sha'] = base
        payload['pull_request']['head']['sha'] = head
        plan = PACKAGES.candidate_plan(root, payload, merge)
        self.assertEqual(plan['host_mode'], 'package-dependencies')
        payload['pull_request']['base']['sha'] = head
        with self.assertRaises(ValueError): PACKAGES.candidate_plan(root, payload, merge)
        with self.assertRaises(ValueError): PACKAGES.candidate_plan(root, self.push(base, merge), head)
        payload = self.push(base, merge); payload['repository'] = {'full_name': 'overte-org/overte', 'id': 1}
        with self.assertRaises(ValueError): PACKAGES.candidate_plan(root, payload, merge)

    def plan(self, host='package-dependencies', packages=True):
        return {'candidate': 'a' * 40, 'plan': 'b' * 64, 'host_mode': host,
                'tool_projects': ['tools/jsdoc'] if host == 'tool-dependencies' else [],
                'package_set': [PACKAGES.S3] if packages else []}

    def needs(self, plan):
        result = {'route': {'result': 'success', 'outputs': PACKAGES.outputs(plan)}}
        for lane, selected in (('project-tests', plan['host_mode'] == 'full'),
                               ('tool-dependencies', plan['host_mode'] == 'tool-dependencies'),
                               ('package-checks', bool(plan['package_set']))):
            result[lane] = {'result': 'success' if selected else 'skipped',
                            'outputs': PACKAGES.receipt(plan, lane) if selected and lane != 'project-tests' else {}}
        return result

    def test_inner_verifier_requires_every_selected_lane_and_exact_receipts(self):
        for host in ('full', 'tool-dependencies', 'package-dependencies', 'delegated-sync', 'documentation'):
            plan = self.plan(host)
            needs = self.needs(plan)
            self.assertEqual(PACKAGES.verify(needs, plan), PACKAGES.receipt(plan))
            for job in needs:
                for outcome in ('failure', 'cancelled', 'skipped', 'neutral'):
                    if outcome == needs[job]['result']: continue
                    modified = deepcopy(needs); modified[job]['result'] = outcome
                    with self.subTest(host=host, job=job, outcome=outcome), self.assertRaises(ValueError):
                        PACKAGES.verify(modified, plan)
                modified = deepcopy(needs); del modified[job]
                with self.assertRaises(ValueError): PACKAGES.verify(modified, plan)
            for key in ('package_candidate', 'package_plan', 'package_verified', 'package_lane'):
                modified = deepcopy(needs); modified['package-checks']['outputs'][key] = 'forged'
                with self.assertRaises(ValueError): PACKAGES.verify(modified, plan)
            modified = deepcopy(needs); modified['route']['outputs']['package_set'] = '[]'
            with self.assertRaises(ValueError): PACKAGES.verify(modified, plan)

    def protected_workflow_fixture(self, name='protected-producer-metadata-ci-v1'):
        root,git,_=self.fixture()
        generation=next(row for row in PACKAGES.workflow_generations() if row['name']==name)
        contents={hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest():raw
                  for path in (ROOT/'tools/repository-checks/workflows').rglob('*.yml')
                  for raw in (path.read_bytes(),)}
        for relative,entry in generation['workflows'].items():
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(contents[entry['sha']])
        git('add','--all');git('commit','-qm','Install complete protected workflow fixture')
        self.assertEqual(PACKAGES.validate_wiring(root),name)
        return root,git,git('rev-parse','HEAD')

    def test_protected_route_accepts_only_actual_complete_flag_bearing_generations(self):
        names={'protected-shared-producer-v1','protected-producer-postmerge-original-e-v1',
               'protected-producer-ci37-v1','protected-producer-metadata-ci-v1',
               'protected-producer-seven-target-ci-v1'}
        self.assertEqual(PACKAGES._PROTECTED_ROUTE_GENERATIONS,names)
        for name in (*sorted(names),'postmerge-original-e-v1','npm-consumers-v1'):
            root,_,_=self.protected_workflow_fixture(name)
            plan=self.plan('full');needs=self.needs(plan)
            needs['route']['outputs']['protected_full']='false'
            with self.subTest(generation=name):
                with self.assertRaises(ValueError):PACKAGES.verify(needs,plan)
                if name in names:
                    original=deepcopy(needs)
                    self.assertEqual(PACKAGES.verify_protected_route(needs,plan,root),PACKAGES.receipt(plan))
                    self.assertEqual(needs,original)
                else:
                    with self.assertRaises(ValueError):PACKAGES.verify_protected_route(needs,plan,root)
                    del needs['route']['outputs']['protected_full']
                    self.assertEqual(PACKAGES.verify(needs,plan),PACKAGES.receipt(plan))

    def test_protected_route_rejects_bad_flags_plan_drift_skips_and_receipt_changes(self):
        root,_,_=self.protected_workflow_fixture()
        for host in ('full','tool-dependencies','package-dependencies','documentation','delegated-sync'):
            plan=self.plan(host);needs=self.needs(plan)
            needs['route']['outputs']['protected_full']='false'
            self.assertEqual(PACKAGES.verify_protected_route(needs,plan,root),PACKAGES.receipt(plan))
            for flag in ('true',True,False,'','TRUE','1',None):
                changed=deepcopy(needs);changed['route']['outputs']['protected_full']=flag
                with self.subTest(host=host,flag=flag):
                    if flag=='true' and type(flag) is str and host=='full':
                        self.assertEqual(PACKAGES.verify_protected_route(changed,plan,root),PACKAGES.receipt(plan))
                    else:
                        with self.assertRaises(ValueError):PACKAGES.verify_protected_route(changed,plan,root)
            for key in (*PACKAGES.outputs(plan),'unknown-extra','protected_full'):
                changed=deepcopy(needs)
                if key=='protected_full':del changed['route']['outputs'][key]
                else:changed['route']['outputs'][key]='forged'
                with self.subTest(host=host,key=key),self.assertRaises(ValueError):
                    PACKAGES.verify_protected_route(changed,plan,root)
            for job in needs:
                for result in ('failure','cancelled','skipped','neutral'):
                    if result==needs[job]['result']:continue
                    changed=deepcopy(needs);changed[job]['result']=result
                    with self.subTest(host=host,job=job,result=result),self.assertRaises(ValueError):
                        PACKAGES.verify_protected_route(changed,plan,root)
            changed=deepcopy(needs);changed['package-checks']['outputs']['package_plan']='forged'
            with self.assertRaises(ValueError):PACKAGES.verify_protected_route(changed,plan,root)
        target=root/'.github/workflows/pr-metadata-context.yml'
        target.write_bytes(target.read_bytes()+b'\n')
        with self.assertRaises(ValueError):PACKAGES.verify_protected_route(needs,plan,root)

    def test_protected_route_cli_recomputes_current_six_workflow_plan_and_verifies_raw_needs(self):
        import yaml
        root,git,base=self.protected_workflow_fixture()
        recipe=yaml.safe_load((root/'.github/workflows/project-tests.yml').read_bytes())
        declared=set(recipe['jobs']['route']['outputs'])
        # Native event/output files are runner-owned and outside the candidate.
        directory=Path(self.enterContext(tempfile.TemporaryDirectory(prefix='protected-route-cli-')))
        for path in ('native.cpp','README.md'):
            target=root/path;target.write_text('Updated fixture source.\n')
            git('add','--all');git('commit','-qm','Update selected fixture input')
            head=git('rev-parse','HEAD');payload=self.push(base,head)
            plan=PACKAGES.candidate_plan(root,payload,head)
            self.assertEqual(plan['host_mode'],'full' if path=='native.cpp' else 'documentation')
            needs=self.needs(plan);needs['route']['outputs']['protected_full']='false'
            self.assertEqual(set(needs['route']['outputs']),declared)
            event_file=directory/'event.json';event_file.write_text(json.dumps(payload))
            output=directory/'verified-output'
            command=[sys.executable,str(ROOT/'tools/repository-checks/package_checks.py'),'verify',
                '--candidate',str(root),'--event',str(event_file),'--sha',head,'--output',str(output)]
            variants=[(deepcopy(needs),True)]
            if plan['host_mode']=='full':
                protected=deepcopy(needs);protected['route']['outputs']['protected_full']='true'
                variants.append((protected,True))
            for mutate in (lambda n:n['route']['outputs'].update(protected_full='true' if path=='README.md' else 'TRUE'),
                           lambda n:n['route']['outputs'].update(unknown='forged'),
                           lambda n:n['route']['outputs'].update(package_plan='forged'),
                           lambda n:n['project-tests'].update(result='skipped' if path=='native.cpp' else 'success')):
                changed=deepcopy(needs);mutate(changed);variants.append((changed,False))
            for document,success in variants:
                output.unlink(missing_ok=True)
                run=subprocess.run([*command,'--needs-json',json.dumps(document)],capture_output=True,text=True)
                with self.subTest(path=path,success=success,outputs=document['route']['outputs']):
                    self.assertEqual(run.returncode==0,success,run.stderr)
                    if success:
                        self.assertEqual(json.loads(run.stdout),PACKAGES.receipt(plan))
                        self.assertEqual(dict(line.split('=',1) for line in output.read_text().splitlines()),PACKAGES.receipt(plan))
                    else:self.assertFalse(output.exists())
            # The documentation case must be a separate complete B→M delta;
            # an earlier native edit must never disappear from the whole union.
            base=head

    def test_outer_verifier_recomputes_proof_and_preserves_legacy_shape(self):
        plan = self.plan()
        needs = results(); needs['route']['outputs'].update(PACKAGES.outputs(plan))
        needs['project']['outputs'] = PACKAGES.receipt(plan)
        self.assertEqual(CHECKS.verify(needs, package_plan=plan)['status'], 'PASS')
        with self.assertRaises(ValueError): CHECKS.verify(needs)
        with self.assertRaises(ValueError): CHECKS.verify(results(), require_packages=True, package_plan=plan)
        for mutation in ('receipt', 'route', 'skipped', 'failure', 'cancelled'):
            modified = deepcopy(needs)
            if mutation == 'receipt': modified['project']['outputs']['package_candidate'] = 'c' * 40
            elif mutation == 'route': modified['route']['outputs']['package_set'] = '[]'
            else: modified['project']['result'] = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                CHECKS.verify(modified, package_plan=plan)
        # Delegated syncs retain their separate gate and still require S3 here.
        needs['route']['outputs']['mode'] = 'delegated-sync'
        plan['host_mode'] = 'delegated-sync'; needs['route']['outputs'].update(PACKAGES.outputs(plan))
        self.assertEqual(CHECKS.verify(needs, package_plan=plan)['status'], 'PASS')
        self.assertEqual(CHECKS.verify(results())['status'], 'PASS')

    def test_exact_templates_reject_any_changed_owner_and_keep_browser_generation(self):
        root, git, base = self.fixture()
        PACKAGES.validate_wiring(root)
        self.assertTrue(PACKAGES.has_staged_caller(root))
        for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml', 'repository-checks.yml'):
            path = root / '.github/workflows' / name; original = path.read_bytes()
            path.write_bytes(original + b'\n# different owner\n')
            with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)
            path.write_bytes(original)
        caller = root / '.github/workflows/repository-checks.yml'
        caller.write_bytes((PACKAGES.TEMPLATES / 'repository-checks-direct.yml').read_bytes())
        browser = root / '.github/workflows/browser-direct-client.yml'
        browser.write_bytes((ROOT / 'tools/repository-checks/workflows/browser-direct-client.yml').read_bytes())
        CHECKS.validate_direct_wiring(root)
        caller.write_bytes((ROOT / 'tools/repository-checks/workflows/repository-checks.yml').read_bytes())
        CHECKS.validate_direct_wiring(root)
        self.assertFalse(PACKAGES.has_staged_caller(root))
        with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)
        caller.unlink(); caller.symlink_to(ROOT / 'tools/repository-checks/workflows/repository-checks.yml')
        with self.assertRaises(ValueError): CHECKS.validate_direct_wiring(root)

    def test_api_tree_wiring_requires_exact_blobs_and_regular_modes(self):
        import hashlib
        tree = {}
        for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml', 'repository-checks.yml'):
            value = (PACKAGES.TEMPLATES / name).read_bytes()
            tree['.github/workflows/' + name] = {'type': 'blob', 'mode': '100644',
                'sha': hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()}
        PACKAGES.validate_tree_wiring(tree)
        for name in tree:
            for mutation in ({'sha': 'a' * 40}, {'mode': '120000'}, {'type': 'commit'}, {'mode': '100755'}):
                modified = deepcopy(tree); modified[name].update(mutation)
                with self.assertRaises(ValueError): PACKAGES.validate_tree_wiring(modified)

    def test_execution_is_bound_to_clean_candidate_and_restores_trusted_environment(self):
        root, git, base = self.fixture()
        plan = PACKAGES.candidate_plan(root, self.push(base, base), base)
        plan['package_set'] = [PACKAGES.S3]
        seen = []
        def run(candidate, projects, **kwargs):
            self.assertNotIn('GH_TOKEN', os.environ)
            self.assertNotIn('GITHUB_OUTPUT', os.environ)
            self.assertNotIn('ACTIONS_RUNTIME_TOKEN', os.environ)
            seen.append((candidate, projects, kwargs))
        with patch.object(PACKAGES, 'tools', return_value=SimpleNamespace(run=run)), patch.dict(os.environ,
                {'GH_TOKEN': 'private', 'GITHUB_OUTPUT': 'private-command', 'ACTIONS_RUNTIME_TOKEN': 'private'}):
            self.assertEqual(PACKAGES.execute(root, plan, 'package-checks'), PACKAGES.receipt(plan, 'package-checks'))
            self.assertEqual(os.environ['GH_TOKEN'], 'private')
            self.assertEqual(os.environ['GITHUB_OUTPUT'], 'private-command')
        self.assertEqual(seen, [(root, [PACKAGES.S3], {'include_s3': True})])
        (root / PACKAGES.S3 / 'package.json').write_text('dirty')
        with self.assertRaises(ValueError): PACKAGES.execute(root, plan, 'package-checks')
        git('checkout', '--', PACKAGES.S3 + '/package.json')
        path = root / PACKAGES.S3 / 'package.json'; path.unlink(); path.symlink_to('package-lock.json')
        git('add', '-A'); git('commit', '-qm', 'Symlink fixture')
        plan['candidate'] = git('rev-parse', 'HEAD')
        with self.assertRaises(ValueError): PACKAGES.execute(root, plan, 'package-checks')

    def test_cli_recomputes_caller_expectations_and_never_receipts_failed_execution(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        root, git, base = self.fixture()
        (root / PACKAGES.S3 / 'package-lock.json').write_text('{"updated":true}')
        git('commit', '-qam', 'Package update'); head = git('rev-parse', 'HEAD')
        plan = PACKAGES.candidate_plan(root, self.push(base, head), head)
        with tempfile.TemporaryDirectory() as directory:
            event_file = Path(directory) / 'event.json'; event_file.write_text(json.dumps(self.push(base, head)))
            output = Path(directory) / 'output'
            argv = ['package_checks.py', 'run', '--candidate', str(root), '--event', str(event_file),
                    '--sha', head, '--output', str(output), '--expected-candidate', head,
                    '--expected-plan', plan['plan']]
            def failure(*args, **kwargs):
                raise subprocess.CalledProcessError(1, 'npm audit')
            helper = SimpleNamespace(affected_projects=TOOLS.affected_projects, run=failure)
            with patch.object(PACKAGES, 'tools', return_value=helper), patch.object(sys, 'argv', argv), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(PACKAGES.main(), 1)
            self.assertFalse(output.exists(), 'Failure must not publish an execution receipt')
            for option, value in (('--expected-candidate', 'c' * 40), ('--expected-plan', 'c' * 64)):
                args = list(argv); args[args.index(option) + 1] = value
                with patch.object(sys, 'argv', args), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(PACKAGES.main(), 1)
                self.assertFalse(output.exists())

    def test_outer_cli_independently_recomputes_the_candidate_instead_of_trusting_outputs(self):
        trusted, trusted_packages = inactive_browser_trusted_checkout(self)
        root, git, base = self.fixture()
        (root / PACKAGES.S3 / 'package-lock.json').write_text('{"updated":true}')
        git('commit', '-qam', 'Package update'); head = git('rev-parse', 'HEAD')
        payload = self.push(base, head)
        plan = trusted_packages.candidate_plan(root, payload, head)
        needs = results(); needs['route']['outputs'].update(PACKAGES.outputs(plan))
        needs['project']['outputs'] = PACKAGES.receipt(plan)
        with tempfile.TemporaryDirectory() as directory:
            event_file = Path(directory) / 'event.json'; event_file.write_text(json.dumps(payload))
            for forged in (False, True):
                candidate = deepcopy(needs)
                if forged:
                    candidate['route']['outputs']['package_plan'] = 'c' * 64
                    candidate['project']['outputs']['package_plan'] = 'c' * 64
                result = subprocess.run([sys.executable, str(trusted / 'tools/repository-checks/check.py'),
                    'verify', '--candidate', str(root), '--event', str(event_file), '--sha', head,
                    '--needs-json', json.dumps(candidate)], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, not forged, result.stderr)

    def test_activation_matrix_binds_each_pr_push_and_manual_to_its_actual_target(self):
        self.assertEqual(len(BRANCHES), 7)
        policy = SimpleNamespace(configuration=lambda: ({'package_checks_required_branches': ['main']}, BRANCHES))
        with patch.object(PACKAGES, 'load', return_value=policy):
            for branch in BRANCHES:
                expected = branch == 'main'
                for head in BRANCHES:
                    with self.subTest(kind='PR', branch=branch, head=head):
                        # Top-level/head refs must never override the PR base.
                        payload = event(branch, head, fork=True); payload['ref'] = 'refs/heads/main'
                        self.assertEqual(PACKAGES.activated(payload), expected)
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main'}):
                    self.assertEqual(PACKAGES.activated({'repository': event()['repository'],
                        'ref': 'refs/heads/' + branch, 'before': '1' * 40, 'after': '2' * 40}), expected)
                for ref in ('refs/heads/' + branch, branch):
                    with self.subTest(kind='manual', branch=branch, ref=ref), patch.dict(os.environ, {
                            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/' + branch,
                            'GITHUB_REF_TYPE': 'branch'}):
                        self.assertEqual(PACKAGES.activated({'repository': event()['repository'], 'ref': ref,
                                                            'inputs': {}, 'workflow': '.github/workflows/repository-checks.yml'}), expected)

    def test_activation_rejects_foreign_missing_malformed_tag_and_conflicting_manual_identity(self):
        policy = SimpleNamespace(configuration=lambda: ({'package_checks_required_branches': ['main']}, BRANCHES))
        with patch.object(PACKAGES, 'load', return_value=policy):
            for identity in ({'full_name': 'overte-org/overte', 'id': CONFIG['repository_id']},
                             {'full_name': CONFIG['repository'], 'id': 42}, None):
                bad = event(); bad['repository'] = identity
                with self.subTest(identity=identity), self.assertRaises(ValueError): PACKAGES.activated(bad)
                bad = event(); bad['pull_request']['base']['repo'] = identity
                with self.assertRaises(ValueError): PACKAGES.activated(bad)
            for ref in (None, '', 'main', 'refs/tags/main', 'refs/pull/1/merge', 'refs/heads/',
                        'refs/heads/main\n', 'refs/heads/main..old', 'refs/heads/-main',
                        'refs/heads/.main', 'refs/heads/main.lock', 'refs/heads/main@{1}',
                        'refs/heads/a//b', 'refs/heads/a b', 'refs/heads/a?b', 'https://github.com/other/main'):
                with self.subTest(ref=ref), patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push'}), self.assertRaises(ValueError):
                    PACKAGES.activated({'repository': event()['repository'], 'ref': ref})
            for value in (None, [], {}, {'base': {}}, {'base': {'repo': event()['repository'], 'ref': 'refs/heads/main'}}):
                with self.subTest(pr=value), self.assertRaises(ValueError):
                    PACKAGES.activated({'repository': event()['repository'], 'pull_request': value})
            for runner_ref, ref_type in (('refs/heads/apple-ios', 'branch'), ('refs/tags/main', 'tag')):
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': runner_ref,
                                            'GITHUB_REF_TYPE': ref_type}), self.assertRaises(ValueError):
                    PACKAGES.activated({'repository': event()['repository'], 'ref': 'main'})

    def test_templates_bind_required_orchestration_and_no_unrelated_package_setup(self):
        import yaml
        d = yaml.safe_load((PACKAGES.TEMPLATES / 'project-tests.yml').read_text())
        jobs = d['jobs']; final = jobs['project-results']
        self.assertEqual(final['if'], 'always()')
        self.assertEqual(set(final['needs']), {'route', 'project-tests', 'tool-dependencies', 'package-checks'})
        self.assertEqual(jobs['project-tests']['if'], "needs.route.outputs.package_host_mode == 'full'")
        self.assertEqual(jobs['package-checks']['if'], "needs.route.outputs.package_set != '[]'")
        for lane in ('route', 'tool-dependencies', 'package-checks', 'project-results'):
            steps = jobs[lane]['steps']
            self.assertEqual(steps[0]['with']['ref'], '${{ github.event.repository.default_branch }}')
            self.assertEqual(steps[0]['with']['path'], 'trusted')
            self.assertEqual(steps[1]['with']['path'], 'candidate')
            self.assertIn('trusted/tools/repository-checks/package_checks.py', steps[-1]['run'])
            self.assertTrue(all(s['with']['persist-credentials'] is False for s in steps if s.get('uses', '').startswith('actions/checkout@')))
        package = jobs['package-checks']['steps']
        self.assertEqual(package[2]['with'], {'node-version': '22'})
        self.assertEqual(len(package), 4)
        self.assertEqual(d['permissions'], {'contents': 'read'})
        for name in ('repository-checks.yml', 'repository-checks-direct.yml'):
            caller = yaml.safe_load((PACKAGES.TEMPLATES / name).read_text())['jobs']
            self.assertIn("needs.route.outputs.package_set != '[]'", caller['project']['if'])
            self.assertIn('--candidate candidate --sha "$GITHUB_SHA"', caller['repository-checks']['steps'][-1]['run'])
            self.assertIn('project', caller['repository-checks']['needs'])
            self.assertIn('tools/test-evidence', caller['route']['steps'][0]['with']['sparse-checkout'])
            self.assertEqual(set(caller['project']['with']), {'dependency_projects', 'expected_candidate', 'expected_package_plan'})
        parent = yaml.safe_load((PACKAGES.TEMPLATES / 'parent-qualification.yml').read_text())
        steps = parent['jobs']['qualify-parent']['steps']
        package = steps[-1]
        self.assertEqual(package['if'], "steps.route.outputs.package_set != '[]'")
        self.assertIn('--lane package-checks', package['run'])
        for step in steps:
            if step.get('name') in ('Set up Python', 'Set up Java', 'Install QML and portable C++ contract prerequisites'):
                self.assertEqual(step['if'], "steps.route.outputs.package_host_mode == 'full'")


class NpmConsumerSelectionTests(unittest.TestCase):
    """Exercise source-bound decisions with actual immutable Git objects."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='overte-npm-consumer-selection-')
        self.addCleanup(directory.cleanup)
        self.outer = Path(directory.name)
        self.root = self.outer / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.policies = deepcopy(CONSUMERS.PROJECTS)
        for project, policy in self.policies.items():
            folder = self.root / project
            folder.mkdir(parents=True)
            (folder / 'package.json').write_text('{"private":true}\n')
            (folder / 'consumer.js').write_text('module.exports = 1;\n')
            self.write_lock(project, policy['old'])
        self.base = self.commit()
        snapshot = CONSUMERS._snapshot(self.root, self.base)
        for project, policy in self.policies.items():
            policy['complement'] = CONSUMERS._digest(CONSUMERS._complement(snapshot, project))
            policy['entries'] = 2
            policy['graph'] = CONSUMERS._digest(CONSUMERS._graph(self.lock(project), policy['node']))
        patched = patch.dict(CONSUMERS.PROJECTS, self.policies, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', *args], cwd=self.root,
            stderr=subprocess.PIPE, text=True).strip()

    def commit(self):
        self.git('add', '--all')
        self.git('commit', '-qm', 'Update immutable fixture')
        return self.git('rev-parse', 'HEAD')

    def lock(self, project):
        return json.loads((self.root / project / 'package-lock.json').read_text())

    def write_lock(self, project, dependency=None, *, value=None):
        policy = self.policies[project]
        value = value if value is not None else {'name': 'fixture', 'lockfileVersion': 3,
            'packages': {'': {'name': 'fixture'}, policy['node']: dependency,
                         'node_modules/unchanged': {'version': '1.0.0'}}}
        (self.root / project / 'package-lock.json').write_text(json.dumps(value) + '\n')

    def update(self, *projects):
        for project in projects or self.policies:
            self.write_lock(project, self.policies[project]['new'])

    def selected(self, base=None):
        return CONSUMERS.select(self.root, base or self.base, self.commit())

    def assert_profiles(self, result, browser, s3):
        self.assertFalse(result['unknown'])
        self.assertEqual({p: r['profile'] for p, r in result['projects'].items()},
                         {CONSUMERS.BROWSER: browser, CONSUMERS.S3: s3})

    def test_exact_dependency_updates_have_independent_owners(self):
        self.update()
        result = self.selected()
        self.assert_profiles(result, 'source-map-postcss-v1', 'proxy-addr-express-v1')
        for project, selected in result['projects'].items():
            self.assertTrue(selected['required'])
            self.assertEqual(selected['changed_nodes'], [self.policies[project]['node']])
            self.assertEqual(selected['execution'], 'not-performed')

    def test_one_package_update_does_not_select_the_other(self):
        self.update(CONSUMERS.S3)
        self.assert_profiles(self.selected(), 'none', 'proxy-addr-express-v1')

    def test_unrelated_ci_native_and_symlink_inputs_do_not_expand_package_owners(self):
        self.update()
        (self.root / 'native.cpp').write_text('int value;\n')
        (self.root / 'ci.py').write_text('print(1)\n')
        (self.root / 'unrelated-link').symlink_to('native.cpp')
        self.assert_profiles(self.selected(), 'source-map-postcss-v1', 'proxy-addr-express-v1')

    def test_changed_consumer_requires_full_for_its_package_only(self):
        self.update()
        (self.root / CONSUMERS.BROWSER / 'consumer.js').write_text('module.exports = 2;\n')
        self.assert_profiles(self.selected(), 'full', 'proxy-addr-express-v1')

    def test_historical_consumer_difference_cannot_use_a_new_reader_anchor(self):
        (self.root / CONSUMERS.BROWSER / 'consumer.js').write_text('module.exports = 99;\n')
        historical = self.commit()
        self.update()
        self.assert_profiles(self.selected(historical), 'full', 'proxy-addr-express-v1')

    def test_other_dependency_changes_invalidate_the_focused_profile(self):
        self.update()
        lock = self.lock(CONSUMERS.BROWSER)
        lock['packages']['node_modules/unchanged']['version'] = '2.0.0'
        self.write_lock(CONSUMERS.BROWSER, value=lock)
        self.assert_profiles(self.selected(), 'full', 'proxy-addr-express-v1')

    def test_equal_unreviewed_historical_lock_graph_is_not_a_reviewed_profile(self):
        lock = self.lock(CONSUMERS.BROWSER)
        lock['packages']['node_modules/unchanged']['version'] = '9.0.0'
        self.write_lock(CONSUMERS.BROWSER, value=lock)
        historical = self.commit()
        lock['packages'][self.policies[CONSUMERS.BROWSER]['node']] = self.policies[CONSUMERS.BROWSER]['new']
        self.write_lock(CONSUMERS.BROWSER, value=lock)
        self.assert_profiles(self.selected(historical), 'full', 'none')

    def test_new_root_postcss_config_requires_browser_verification(self):
        (self.root / 'postcss.config.cjs').write_text('module.exports = {};\n')
        self.assert_profiles(self.selected(), 'full', 'none')

    def test_new_root_npm_config_selects_both_packages(self):
        (self.root / '.npmrc').write_text('legacy-peer-deps=true\n')
        self.assert_profiles(self.selected(), 'full', 'full')

    def test_postcss_config_directory_symlink_cannot_escape_discovery(self):
        (self.root / '.config').symlink_to('/tmp', target_is_directory=True)
        self.assert_profiles(self.selected(), 'full', 'none')

    def test_unchanged_historical_config_does_not_start_unrelated_browser_tests(self):
        (self.root / 'postcss.config.cjs').write_text('module.exports = {};\n')
        historical = self.commit()
        (self.root / 'native.cpp').write_text('int value;\n')
        self.assert_profiles(self.selected(historical), 'none', 'none')

    def test_lock_formatting_with_identical_reviewed_semantics_requires_no_execution(self):
        project = CONSUMERS.BROWSER
        (self.root / project / 'package-lock.json').write_text(json.dumps(self.lock(project), indent=4))
        result = self.selected()
        self.assert_profiles(result, 'none', 'none')
        self.assertEqual(result['projects'][project]['reason'], 'reviewed-lockfile-format-only')

    def test_dependency_downgrade_is_not_an_approved_security_update(self):
        self.update()
        upgraded = self.commit()
        self.write_lock(CONSUMERS.BROWSER, self.policies[CONSUMERS.BROWSER]['old'])
        self.assert_profiles(self.selected(upgraded), 'full', 'none')

    def test_lock_symlink_and_mode_changes_require_full_for_affected_package(self):
        for mode in ('symlink', 'executable'):
            with self.subTest(mode=mode):
                self.git('reset', '--hard', self.base)
                path = self.root / CONSUMERS.BROWSER / 'package-lock.json'
                if mode == 'symlink':
                    path.unlink()
                    path.symlink_to('package.json')
                else:
                    path.chmod(0o755)
                self.assert_profiles(self.selected(), 'full', 'none')

    def test_duplicate_fields_nonfinite_and_malformed_json_cannot_omit_execution(self):
        for content in ('{"lockfileVersion":3,"lockfileVersion":3,"packages":{}}',
                        '{"lockfileVersion":3,"packages":{},"bad":NaN}', '{'):
            with self.subTest(content=content):
                self.git('reset', '--hard', self.base)
                (self.root / CONSUMERS.BROWSER / 'package-lock.json').write_text(content)
                self.assert_profiles(self.selected(), 'full', 'none')

    def test_invalid_commit_identity_is_unknown_and_never_a_pass(self):
        for base in ('HEAD', '0' * 40, None):
            with self.subTest(base=base):
                result = CONSUMERS.select(self.root, base, self.base)
                self.assertTrue(result['unknown'])
                for value in result['projects'].values():
                    self.assertEqual(value['profile'], 'full')
                    self.assertTrue(value['required'])
                    self.assertEqual(value['execution'], 'not-performed')

    def run_consumers(self, selection, projects=None, *, failure=None, node='v22.23.3', npm='10.9.9'):
        self.commands = []
        real_run = CONSUMERS.subprocess.run
        def process(arguments, **kwargs):
            if arguments[0] == 'git':
                return real_run(arguments, **kwargs)
            self.commands.append(list(arguments))
            environment = kwargs['env']
            self.assertEqual(environment['NODE_OPTIONS'], '')
            self.assertEqual(environment['NODE_PATH'], '')
            for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_OUTPUT', 'ACTIONS_RUNTIME_TOKEN',
                        'npm_config_registry', 'NPM_CONFIG_REGISTRY'):
                self.assertNotIn(key, environment)
            for key in ('NPM_CONFIG_USERCONFIG', 'NPM_CONFIG_GLOBALCONFIG'):
                self.assertEqual(Path(environment[key]).read_text(), '')
            if arguments[0].endswith('/npm') and arguments[1:] != ['--version']:
                self.assertEqual(arguments[-3:], ['--prefix', str(kwargs['cwd']), '--workspaces=false'])
            if failure and arguments[1:3] == failure:
                raise subprocess.CalledProcessError(1, arguments)
            if arguments[1:] == ['--version']:
                return SimpleNamespace(stdout=(node if arguments[0].endswith('node') else npm) + '\n')
            return SimpleNamespace(returncode=0)
        with patch.object(CONSUMERS.subprocess, 'run', side_effect=process), \
                patch.object(CONSUMERS.shutil, 'which', side_effect=lambda name, **kwargs: '/reviewed/bin/' + name):
            return CONSUMERS.run(self.root, selection, projects or list(self.policies))

    def test_focused_execution_has_one_install_and_audit_per_package_and_no_build(self):
        self.update()
        selection = self.selected()
        private = {'GH_TOKEN': 'fixture-secret', 'GITHUB_OUTPUT': 'fixture-command',
                   'ACTIONS_RUNTIME_TOKEN': 'fixture-token', 'NODE_OPTIONS': '--bad-fixture-option',
                   'NODE_PATH': '/fixture/path', 'npm_config_registry': 'https://example.invalid'}
        with patch.dict(os.environ, private):
            result = self.run_consumers(selection)
            self.assertEqual(os.environ['GH_TOKEN'], private['GH_TOKEN'])
        self.assertTrue(result['verified'])
        self.assertEqual(result['application_builds'], 0)
        commands = [args[1:-3] if args[0].endswith('/npm') else args[1:] for args in self.commands[2:]]
        self.assertEqual(commands.count(['ci', '--ignore-scripts', '--no-fund', '--no-audit']), 2)
        self.assertEqual(commands.count(['audit', '--audit-level=low']), 2)
        self.assertEqual(commands.count(['test', '--ignore-scripts']), 1)
        self.assertEqual(len(commands), 7)
        self.assertTrue(all('build' not in args and 'playwright' not in args and 'vite' not in args
                            for args in commands))

    def test_security_audit_failure_stops_probes_and_prevents_a_receipt(self):
        self.update()
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_consumers(self.selected(), failure=['audit', '--audit-level=low'])
        self.assertEqual([args[1] for args in self.commands], ['--version', '--version', 'ci', 'audit'])

    def test_unqualified_node_or_npm_cannot_execute_a_focused_profile(self):
        self.update()
        selection = self.selected()
        for versions in ({'node': 'v24.1.0'}, {'node': 'v22.11.0'}, {'npm': '11.0.0'}):
            with self.subTest(versions=versions), self.assertRaises(CONSUMERS.ConsumerError):
                self.run_consumers(selection, **versions)
            self.assertEqual(len(self.commands), 2)

    def test_forged_selection_is_recomputed_before_any_package_process(self):
        self.update()
        selection = self.selected()
        selection['projects'][CONSUMERS.BROWSER]['boundary'] = {}
        with self.assertRaises(CONSUMERS.ConsumerError):
            self.run_consumers(selection)
        self.assertEqual(self.commands, [])

    def test_ignored_materialized_npm_config_cannot_override_git_inventory(self):
        (self.root / '.gitignore').write_text('.npmrc\n')
        self.base = self.commit()
        self.update()
        selection = self.selected()
        (self.root / CONSUMERS.BROWSER / '.npmrc').write_text('registry=https://example.invalid\n')
        with self.assertRaises(CONSUMERS.ConsumerError):
            self.run_consumers(selection)
        self.assertEqual(self.commands, [])

    def test_external_workspace_and_project_config_are_disabled_by_explicit_package_prefix(self):
        self.update()
        selection = self.selected()
        (self.outer / 'package.json').write_text(json.dumps({'private': True,
            'workspaces': ['repo/browser-client', 'repo/script-archive/marketplace/S3Server']}))
        (self.outer / '.npmrc').write_text('registry=http://127.0.0.1:9/\nignore-scripts=false\n')
        result = self.run_consumers(selection)
        self.assertTrue(result['verified'])
        self.assertEqual(result['application_builds'], 0)

    def test_candidate_plan_keeps_focus_opt_in_internal_and_mixed_host_owner_independent(self):
        self.update()
        (self.root / 'native.cpp').write_text('int value;\n')
        head = self.commit()
        payload = {'repository': event()['repository'], 'before': self.base,
                   'after': head, 'ref': 'refs/heads/main', 'include_consumers': True}
        real_load = PACKAGES.load
        def load(name, relative):
            return CONSUMERS if relative.endswith('/npm_consumers.py') else real_load(name, relative)
        with patch.object(PACKAGES, 'load', side_effect=load):
            legacy = PACKAGES.candidate_plan(self.root, payload, head)
            focused = PACKAGES.candidate_plan(self.root, payload, head, include_consumers=True)
        self.assertNotIn('dependency_profiles', legacy)
        self.assertEqual(legacy['package_set'], [CONSUMERS.S3])
        self.assertEqual(focused['host_mode'], 'full')
        self.assertEqual(focused['package_set'], [CONSUMERS.S3, CONSUMERS.BROWSER])
        self.assertEqual(focused['dependency_profiles']['projects'][CONSUMERS.BROWSER]['profile'],
                         'source-map-postcss-v1')
        self.assertNotEqual(focused['plan'], legacy['plan'])

    def test_package_execution_never_duplicates_focused_projects_in_legacy_runner(self):
        self.update()
        head = self.commit()
        payload = {'repository': event()['repository'], 'before': self.base,
                   'after': head, 'ref': 'refs/heads/main'}
        real_load = PACKAGES.load
        def load(name, relative):
            return CONSUMERS if relative.endswith('/npm_consumers.py') else real_load(name, relative)
        with patch.object(PACKAGES, 'load', side_effect=load):
            plan = PACKAGES.candidate_plan(self.root, payload, head, include_consumers=True)
            with patch.object(CONSUMERS, 'run', return_value={'verified': True}) as focused, \
                    patch.object(TOOLS, 'run') as legacy, patch.object(PACKAGES, 'tools', return_value=TOOLS):
                self.assertEqual(PACKAGES.execute(self.root, plan, 'package-checks'),
                                 PACKAGES.receipt(plan, 'package-checks'))
            self.assertEqual(focused.call_count, 1)
            self.assertEqual(focused.call_args.args[2], [CONSUMERS.S3, CONSUMERS.BROWSER])
            legacy.assert_not_called()

    def install_consumer_callers(self):
        # This fixture deliberately starts at the complete npm-consumers-v1
        # predecessor, independent of the real checkout's active generation.
        sources = {
            'project-tests.yml': 'host/project-tests.yml',
            'parent-qualification.yml': 'host/parent-qualification.yml',
            'sync-validation.yml': 'packages/sync-validation.yml',
            'repository-checks.yml': 'npm-consumers/repository-checks.yml',
            'browser-client.yml': 'npm-consumers/browser-client.yml',
        }
        self.assertEqual(set(sources), {Path(path).name for path in PACKAGES.CONSUMER_WORKFLOW_PATHS})
        for name, relative in sources.items():
            path = self.root / '.github/workflows' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / 'tools/repository-checks/workflows' / relative).read_bytes())
        self.assertEqual(PACKAGES.validate_wiring(self.root), 'npm-consumers-v1')
        self.base = self.commit()

    def automatic_plan(self, base=None, **kwargs):
        head = self.commit()
        payload = {'repository': event()['repository'], 'before': base or self.base,
                   'after': head, 'ref': 'refs/heads/main'}
        real_load = PACKAGES.load
        def load(name, relative):
            return CONSUMERS if relative.endswith('/npm_consumers.py') else real_load(name, relative)
        with patch.object(PACKAGES, 'load', side_effect=load):
            return PACKAGES.candidate_plan(self.root, payload, head, **kwargs)

    def test_complete_consumer_generation_automatically_enables_required_focused_owner(self):
        self.install_consumer_callers()
        self.update(CONSUMERS.BROWSER)
        plan = self.automatic_plan()
        self.assertTrue(plan['consumer_generation'])
        self.assertEqual(plan['host_mode'], 'package-dependencies')
        self.assertEqual(plan['package_set'], [CONSUMERS.BROWSER])
        self.assertEqual(PACKAGES.browser_outputs(plan)['browser_npm_only'], 'true')
        needs = PackageChecksTests.needs(self, plan)
        self.assertEqual(PACKAGES.verify(needs, plan), PACKAGES.receipt(plan))
        for outcome in ('failure', 'cancelled', 'skipped'):
            changed = deepcopy(needs); changed['package-checks']['result'] = outcome
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                PACKAGES.verify(changed, plan)
        changed = deepcopy(needs)
        changed['package-checks']['outputs']['package_plan'] = '0' * 64
        with self.assertRaises(ValueError):
            PACKAGES.verify(changed, plan)

    def test_format_only_reviewed_lock_omits_both_legacy_jobs_and_all_package_execution(self):
        self.install_consumer_callers()
        path = self.root / CONSUMERS.BROWSER / 'package-lock.json'
        path.write_text(json.dumps(self.lock(CONSUMERS.BROWSER), indent=4))
        plan = self.automatic_plan()
        self.assertEqual(plan['package_set'], [])
        self.assertEqual(plan['host_mode'], 'package-dependencies')
        self.assertEqual(PACKAGES.browser_outputs(plan)['browser_npm_only'], 'true')
        needs = results()
        needs['route']['outputs'].update(PACKAGES.outputs(plan))
        needs['project'] = {'result': 'skipped', 'outputs': {}}
        self.assertEqual(CHECKS.verify(needs, package_plan=plan)['status'], 'PASS')

    def test_supported_lock_with_unrelated_ci_keeps_host_and_package_owners_independent(self):
        self.install_consumer_callers()
        self.update()
        (self.root / 'ci.py').write_text('print(1)\n')
        plan = self.automatic_plan()
        self.assertEqual(plan['host_mode'], 'full')
        self.assertEqual(plan['package_set'], [CONSUMERS.S3, CONSUMERS.BROWSER])
        self.assertEqual(PACKAGES.browser_outputs(plan)['browser_npm_only'], 'true')

    def test_unsupported_dependency_or_changed_browser_consumer_retains_full_legacy_jobs(self):
        self.install_consumer_callers()
        for change in ('dependency', 'consumer'):
            with self.subTest(change=change):
                self.git('reset', '--hard', self.base)
                self.update(CONSUMERS.BROWSER)
                if change == 'dependency':
                    lock = self.lock(CONSUMERS.BROWSER)
                    lock['packages']['node_modules/unchanged']['version'] = '2.0.0'
                    self.write_lock(CONSUMERS.BROWSER, value=lock)
                else:
                    (self.root / CONSUMERS.BROWSER / 'consumer.js').write_text('module.exports = 2;\n')
                plan = self.automatic_plan()
                self.assertEqual(plan['host_mode'], 'full')
                self.assertEqual(PACKAGES.browser_outputs(plan)['browser_npm_only'], 'false')

    def test_consumer_workflow_mutation_or_missing_file_cannot_enable_omission(self):
        self.install_consumer_callers()
        for mutation in ('content', 'missing', 'symlink'):
            with self.subTest(mutation=mutation):
                self.git('reset', '--hard', self.base)
                path = self.root / '.github/workflows/browser-client.yml'
                if mutation == 'content':
                    path.write_bytes(path.read_bytes() + b'\n# unapproved\n')
                else:
                    path.unlink()
                    if mutation == 'symlink':
                        path.symlink_to('repository-checks.yml')
                with self.assertRaises(ValueError):
                    self.automatic_plan()

    def test_deployed_protected_generation_rejects_rollback_and_internal_opt_out(self):
        self.install_consumer_callers()
        self.update(CONSUMERS.BROWSER)
        with self.assertRaises(ValueError):
            self.automatic_plan(include_consumers=False)
        path = self.root / '.github/workflows/repository-checks.yml'
        path.write_bytes((PACKAGES.TEMPLATES / 'repository-checks.yml').read_bytes())
        with self.assertRaises(ValueError):
            self.automatic_plan()

    def test_prepared_workflows_preserve_all_legacy_steps_and_fail_to_full(self):
        import hashlib
        import yaml
        # Reviewed normalized job bodies from protected pre-deployment 3cdee920.
        # Keep this invariant after the active file itself becomes the new pair;
        # comparing the deployed template with itself would lose that evidence.
        legacy = {
            'browser': '4574371f2035432bd44919ed152ab1a3af54b930e05eb48071bb1530e720ffe8',
            'native-journey': 'f18fb63f1e67d7c6109587a62bfd9bfc79782dde3e006887c2e0cf476f5818bc',
        }
        future = yaml.safe_load((ROOT / PACKAGES.CONSUMER_TEMPLATES / 'browser-client.yml').read_text())
        self.assertEqual(future['permissions'], {'contents': 'read'})
        for name in ('browser', 'native-journey'):
            job = deepcopy(future['jobs'][name])
            self.assertEqual(job.pop('needs'), 'npm-route')
            condition = job.pop('if')
            self.assertIn('!cancelled()', condition)
            self.assertIn("github.event_name != 'pull_request'", condition)
            self.assertIn("needs.npm-route.result != 'success'", condition)
            self.assertIn("needs.npm-route.outputs.browser_npm_only != 'true'", condition)
            normalized = (json.dumps(job, sort_keys=True, separators=(',', ':')) + '\n').encode()
            self.assertEqual(hashlib.sha256(normalized).hexdigest(), legacy[name])
        route = future['jobs']['npm-route']
        self.assertEqual(route['if'], "github.event_name == 'pull_request'")
        self.assertIn('package_checks.py browser-route', route['steps'][-1]['run'])
        caller = yaml.safe_load((ROOT / PACKAGES.CONSUMER_TEMPLATES / 'repository-checks.yml').read_text())
        self.assertIn("package_host_mode == 'full'", caller['jobs']['project']['if'])

    def test_selective_sync_successor_requires_the_complete_five_workflow_owner(self):
        self.install_consumer_callers()
        sync = self.root / '.github/workflows/sync-validation.yml'
        previous = (PACKAGES.TEMPLATES / 'sync-validation.yml').read_bytes()
        if sync.read_bytes() != previous:
            sync.write_bytes(previous)
            self.base = self.commit()
        self.assertEqual(PACKAGES.validate_wiring(self.root), 'npm-consumers-v1')
        sync.write_bytes((ROOT / 'tools/repository-checks/workflows/sync-ci-selection.yml').read_bytes())
        self.update()
        plan = self.automatic_plan()
        self.assertEqual(PACKAGES.validate_wiring(self.root), 'npm-consumers-sync-ci-v1')
        self.assertTrue(plan['consumer_generation'])
        self.assertEqual(set(plan['package_set']), {CONSUMERS.S3, CONSUMERS.BROWSER})
        self.assertEqual(PACKAGES.browser_outputs(plan)['browser_npm_only'], 'true')
        needs = PackageChecksTests.needs(self, plan)
        self.assertEqual(PACKAGES.verify(needs, plan), PACKAGES.receipt(plan))
        browser = self.root / '.github/workflows/browser-client.yml'
        browser.unlink()
        with self.assertRaises(ValueError):
            PACKAGES.validate_wiring(self.root)
        browser.write_bytes((ROOT / PACKAGES.CONSUMER_TEMPLATES / 'browser-client.yml').read_bytes())
        sync.write_bytes(sync.read_bytes() + b'\n# Unapproved caller\n')
        with self.assertRaises(ValueError):
            PACKAGES.validate_wiring(self.root)


class CandidateTests(unittest.TestCase):
    def test_exact_merge_paths_and_stale_candidate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c",
                                                 "core.hooksPath=/dev/null", *args], cwd=root,
                                                text=True, stderr=subprocess.PIPE).strip()
            git("init", "-q", "--initial-branch=main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "README.md").write_text("# Initial\n")
            git("add", ".")
            git("commit", "-qm", "Base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "fix/main/example")
            (root / "README.md").write_text("# Changed\n")
            git("commit", "-qam", "Documentation")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "--no-edit", "fix/main/example")
            merge = git("rev-parse", "HEAD")
            value = event()
            value["pull_request"]["base"]["sha"] = base
            value["pull_request"]["head"]["sha"] = head
            self.assertEqual(CHECKS.changed_paths(root, value, merge), (["README.md"], True))
            with self.assertRaises(ValueError):
                CHECKS.changed_paths(root, value, head)
            value["pull_request"]["base"]["sha"] = head
            with self.assertRaises(ValueError):
                CHECKS.changed_paths(root, value, merge)
            git("checkout", "-q", "fix/main/example")
            (root / "README.md").chmod(0o755)
            git("commit", "-qam", "Executable Markdown is not documentation only")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            base = git("rev-parse", "HEAD")
            git("merge", "--no-ff", "--no-edit", "fix/main/example")
            merge = git("rev-parse", "HEAD")
            value["pull_request"]["base"]["sha"] = base
            value["pull_request"]["head"]["sha"] = head
            self.assertEqual(CHECKS.changed_paths(root, value, merge), (["README.md"], False))


if __name__ == "__main__":
    unittest.main()
