#!/usr/bin/env python3
"""Negative selection coverage against the real trusted host program closure."""
from copy import deepcopy
import importlib.util
import json
import contextlib
import io
import signal
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('host_impact_tests', ROOT / 'tools/repository-checks/host_selection.py')
HOST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOST)


class HostSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = HOST.inputs.full_tree(ROOT, 'HEAD')
        cls.registry = HOST.inputs.load_registry(ROOT / '.github/test-suites.json')
        cls.quick = {name for name, suite in cls.registry['suites'].items() if suite['layer'] == 'quick'}
        cls.all_names = set(cls.registry['suites'])

    def setUp(self):
        # Fixtures model a reviewed generation even on future product commits.
        # A changed production generation must fall back, not fail its PR.
        self.review = patch.object(HOST, 'REVIEWED_PROGRAMS', HOST.program_digest(self.tree))
        self.review.start()
        self.addCleanup(self.review.stop)

    def selected(self, paths, *, tree=None, regular=True, unknown=False, trusted_tree=None):
        return HOST.select(self.tree if tree is None else tree, paths, regular,
                           unknown=unknown, trusted_tree=self.tree if trusted_tree is None else trusted_tree)

    def test_reviewed_generation_binds_actual_reader_inventory(self):
        tree=deepcopy(self.tree)
        del tree['tests/device/contracts/tablet/pages.json']
        self.assertNotEqual(HOST.program_digest(tree), HOST.REVIEWED_PROGRAMS)

    def test_cleanup_and_ci_tests_keep_every_quick_contract_and_omit_production_host(self):
        for paths in (['tools/branch-cleanup/cleanup.py'], ['tests/branch-cleanup-test.py'],
                      ['tools/branch-cleanup/adoption.py', 'tests/branch-cleanup-test.py',
                       '.github/workflows/branch-cleanup.yml', 'docs/AUTOMATIC_BRANCH_CLEANUP.md'],
                      ['tools/repository-checks/check.py'], ['tests/workflow-contract-test.py'],
                      ['tools/ios-build-qualification/check.py', 'tests/ios-build-qualification-test.py']):
            with self.subTest(paths=paths):
                plan=self.selected(paths)
                self.assertEqual(set(plan['suites']), self.quick)
                self.assertFalse(plan['full_host'])
                self.assertNotIn('device-control-plane-full',plan['suites'])

    def test_unknown_product_setup_shadow_and_mixed_changes_keep_full_host(self):
        for path in ('interface/src/Application.cpp','libraries/audio-client/src/AudioClient.cpp',
                     'tests/device/catalog.json','tests/run-project-tests.py','tests/run-unittest-suite.py',
                     'tests/requirements-host.txt','.github/workflows/project-tests.yml',
                     'tests/json.py','json.py','tests/sitecustomize.py','PhoneLoadingDiagnostics.h',
                     'unknown/data.bin','provenance/artifact_identity.py','tools/sbom/verify-artifact-identity.py',
                     'browser-client/package-lock.json','script-archive/marketplace/S3Server/package-lock.json'):
            with self.subTest(path=path):
                result=self.selected(['tools/branch-cleanup/cleanup.py',path])
                self.assertTrue(result['full_host'])
                self.assertEqual(set(result['suites']),self.all_names)

    def test_new_reader_historical_child_dependency_or_optional_header_prevents_omission(self):
        for path in ('tests/device/new_reader.py','tests/device/contracts/tablet/pages.json',
                     'libraries/shared/src/new-input.h','interface/resources/qml/new.qml',
                     'scripts/system/new.js','tests/run-unittest-suite.py','tests/platform-profile.json',
                     'domain-server/src/new.h','tools/sbom/new-reader.py',
                     'tests/json.py','tests/json/__init__.py','json.py','json/__init__.py',
                     'PhoneLoadingDiagnostics.h','QCoreApplication'):
            with self.subTest(path=path):
                tree=deepcopy(self.tree)
                tree[path]={'mode':'100644','type':'blob','sha':'a'*40}
                result=self.selected(['tools/branch-cleanup/cleanup.py'],tree=tree)
                self.assertTrue(result['full_host'])
                self.assertEqual(result['reason'],'host-reader-generation-not-reviewed')

    def test_changed_trusted_reader_cannot_resume_old_dependency_exclusion(self):
        tree=deepcopy(self.tree)
        tree['tests/device/run_control_plane_tests.py']['sha']='b'*40
        result=self.selected(['tools/branch-cleanup/cleanup.py'],trusted_tree=tree)
        self.assertTrue(result['full_host'])

    def test_deleted_reader_and_nonregular_reader_fail_closed(self):
        for mode in ('deleted','120000','160000'):
            with self.subTest(mode=mode):
                tree=deepcopy(self.tree);path='tests/device/run_control_plane_tests.py'
                if mode=='deleted': del tree[path]
                else: tree[path]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=tree)['full_host'])

    def test_unknown_nonregular_and_empty_inventory_cannot_get_quick_only(self):
        for kwargs in ({'regular':False},{'unknown':True}):
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],**kwargs)['full_host'])
        self.assertTrue(self.selected([])['full_host'])

    def test_staged_workflow_uses_trusted_selection_and_conditions_qt_setup(self):
        import yaml
        path=ROOT/'tools/repository-checks/workflows/host/project-tests.yml'
        d=yaml.safe_load(path.read_text());job=d['jobs']['project-tests'];steps=job['steps']
        self.assertEqual(steps[0]['with']['ref'],'${{ github.event.repository.default_branch }}')
        self.assertEqual(steps[0]['with']['path'],'trusted')
        self.assertEqual(steps[1]['with']['path'],'candidate')
        self.assertTrue(all(s['with']['persist-credentials'] is False for s in steps if 'checkout@' in s.get('uses','')))
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        self.assertEqual(qt['if'],"steps.host.outputs.full_host == 'true'")
        select=next(s for s in steps if s.get('id')=='host')
        run=next(s for s in steps if s['name']=='Run independently selected host contracts')
        for s in (select,run):
            self.assertIn('trusted/tools/repository-checks/host_selection.py',s['run'])
            self.assertIn('--expected-plan "$EXPECTED_PLAN"',s['run'])
        self.assertEqual(d['permissions'],{'contents':'read'})
        self.assertEqual(d['jobs']['project-results']['if'],'always()')
        self.assertIn('project-tests',d['jobs']['project-results']['needs'])

    def cli(self, runner_result=0, expected='c'*64, cancel=False):
        plan={'candidate':'a'*40,'plan':'c'*64,'host_mode':'full',
              'paths':['tools/branch-cleanup/cleanup.py'],'regular':True,'unknown':False}
        policy=SimpleNamespace(validate_wiring=Mock(),candidate_plan=Mock(return_value=plan))
        def run(args,suites,cancelled):
            self.assertEqual({suite[0] for suite in suites},self.quick)
            if cancel:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                self.assertEqual(cancelled,[signal.SIGTERM])
            return runner_result
        controller=SimpleNamespace(Suite=lambda *args:args,run_suites=Mock(side_effect=run))
        with tempfile.TemporaryDirectory() as folder:
            event=Path(folder)/'event.json';event.write_text('{}')
            argv=['host_selection.py','--candidate',str(ROOT),'--event',str(event),'--sha','a'*40,
                  '--expected-plan',expected,'--junit',str(Path(folder)/'result.xml')]
            before=signal.getsignal(signal.SIGTERM)
            with patch.object(sys,'argv',argv),patch.object(HOST,'package_policy',return_value=policy), \
                 patch.object(HOST.execution,'_runner',return_value=controller), \
                 patch.object(HOST.execution,'checkout_identity',return_value=('a'*40,'b'*40)), \
                 patch.object(HOST.inputs,'full_tree',return_value=self.tree), \
                 patch.object(HOST.execution,'platform_suites',return_value=[]), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=HOST.main()
            self.assertIs(signal.getsignal(signal.SIGTERM),before)
        return result,controller

    def test_cli_rejects_mismatched_candidate_plan_before_executing_any_command(self):
        result,controller=self.cli(expected='d'*64)
        self.assertEqual(result,1)
        controller.run_suites.assert_not_called()

    def test_cli_propagates_selected_suite_failure_instead_of_publishing_success(self):
        result,controller=self.cli(runner_result=7)
        self.assertEqual(result,7)
        controller.run_suites.assert_called_once()

    def test_cli_cancellation_is_forwarded_and_signal_handler_restored(self):
        result,controller=self.cli(runner_result=143,cancel=True)
        self.assertEqual(result,143)
        controller.run_suites.assert_called_once()


if __name__=='__main__':
    unittest.main()
