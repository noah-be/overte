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
        cls.ci_quick = cls.quick - HOST.PRODUCT_QUICK_SUITES
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

    def test_cleanup_and_ci_tests_keep_ci_contracts_and_omit_production_contracts(self):
        for paths in (['tools/branch-cleanup/cleanup.py'], ['tests/branch-cleanup-test.py'],
                      ['tools/branch-cleanup/adoption.py', 'tests/branch-cleanup-test.py',
                       '.github/workflows/branch-cleanup.yml', 'docs/AUTOMATIC_BRANCH_CLEANUP.md'],
                      ['tools/repository-checks/check.py'], ['tests/workflow-contract-test.py'],
                      ['.github/workflows/project-tests.yml'],
                      ['.github/workflows/codeql.yml', '.github/codeql/codeql-config.yml'],
                      ['tools/ios-build-qualification/check.py', 'tests/ios-build-qualification-test.py']):
            with self.subTest(paths=paths):
                plan=self.selected(paths)
                self.assertEqual(set(plan['suites']), self.ci_quick)
                self.assertFalse(plan['full_host'])
                self.assertNotIn('device-control-plane-full',plan['suites'])

    def test_qt_script_contracts_are_required_for_product_changes_and_omitted_for_ci_only(self):
        self.assertEqual(self.registry['suites']['shared-script-behavior']['layer'],'host')
        ci=self.selected(['tools/branch-cleanup/cleanup.py'])
        self.assertNotIn('shared-script-behavior',ci['suites'])
        product=self.selected(['scripts/system/chat.js'])
        self.assertIn('shared-script-behavior',product['suites'])
        self.assertTrue(product['full_host'])

    def test_product_quick_groups_are_omitted_only_with_complete_unchanged_inputs(self):
        ci=self.selected(['tools/branch-cleanup/cleanup.py'])
        self.assertFalse(set(ci['suites']) & HOST.PRODUCT_QUICK_SUITES)
        product=self.selected(['scripts/system/chat.js'])
        self.assertTrue(HOST.PRODUCT_QUICK_SUITES <= set(product['suites']))
        self.assertTrue(product['full_host'])

    def test_unknown_product_setup_shadow_and_mixed_changes_keep_full_host(self):
        for path in ('interface/src/Application.cpp','libraries/audio-client/src/AudioClient.cpp',
                     'tests/device/catalog.json','tests/run-project-tests.py','tests/run-unittest-suite.py',
                     'tests/requirements-host.txt','.github/workflows/unreviewed-host.yml',
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

    def test_new_candidate_tests_are_added_without_replacing_required_commands(self):
        candidate=deepcopy(self.registry)
        original=list(self.registry['suites']['branch-cleanup']['command'])
        candidate['suites']['branch-cleanup']['command'] += ['--new-required-variant']
        candidate['suites']['new-contract']=deepcopy(candidate['suites']['branch-cleanup'])
        candidate['suites']['new-contract']['command']=['python','tests/new-contract.py']
        extra=HOST.additional_suites(candidate,self.registry)
        self.assertEqual(len(extra),2)
        self.assertEqual(self.registry['suites']['branch-cleanup']['command'],original)
        self.assertIn('branch-cleanup',self.ci_quick)
        self.assertTrue(any(command==original+['--new-required-variant'] for _,_,command in extra))
        self.assertTrue(any(command==['python','tests/new-contract.py'] for _,_,command in extra))

    def test_duplicate_candidate_aliases_execute_the_same_command_context_at_most_once(self):
        candidate=deepcopy(self.registry)
        candidate['suites']['alias']=deepcopy(candidate['suites']['branch-cleanup'])
        self.assertEqual(HOST.additional_suites(candidate,self.registry),[])
        candidate['suites']['alias']['command']=['python','tests/new-contract.py']
        candidate['suites']['second-alias']=deepcopy(candidate['suites']['alias'])
        self.assertEqual(len(HOST.additional_suites(candidate,self.registry)),1)

    def test_new_unsupported_test_context_cannot_get_a_successful_partial_gate(self):
        for field,value in (('environment','unreviewed-sdk'),('command',['unreviewed-executable','test'])):
            candidate=deepcopy(self.registry)
            candidate['suites']['new-contract']=deepcopy(candidate['suites']['branch-cleanup'])
            candidate['suites']['new-contract'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                HOST.additional_suites(candidate,self.registry)

    def cli(self, runner_result=0, expected='c'*64, cancel=False, new_command=False, select_only=False):
        plan={'candidate':'a'*40,'plan':'c'*64,'host_mode':'full',
              'paths':['tools/branch-cleanup/cleanup.py'],'regular':True,'unknown':False}
        proposed=deepcopy(self.registry)
        if new_command:
            proposed['suites']['new-host-contract']=deepcopy(proposed['suites']['branch-cleanup'])
            proposed['suites']['new-host-contract']['layer']='host'
            proposed['suites']['new-host-contract']['command']=['python','tests/new-required-host-contract.py']
        policy=SimpleNamespace(validate_wiring=Mock(),candidate_plan=Mock(return_value=plan))
        def run(args,suites,cancelled):
            if new_command:
                self.assertTrue(self.all_names <= {suite[0] for suite in suites})
                self.assertEqual(sum(command[-1]=='tests/new-required-host-contract.py' for _,_,command in suites),1)
            else:
                self.assertEqual({suite[0] for suite in suites},self.ci_quick)
            if cancel:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                self.assertEqual(cancelled,[signal.SIGTERM])
            return runner_result
        controller=SimpleNamespace(Suite=lambda *args:args,run_suites=Mock(side_effect=run))
        with tempfile.TemporaryDirectory() as folder:
            event=Path(folder)/'event.json';event.write_text('{}')
            argv=['host_selection.py','--candidate',str(ROOT),'--event',str(event),'--sha','a'*40,
                  '--expected-plan',expected,'--junit',str(Path(folder)/'result.xml')]
            output=Path(folder)/'selection.txt'
            if select_only:
                argv += ['--select-only','--output',str(output)]
            before=signal.getsignal(signal.SIGTERM)
            with patch.object(sys,'argv',argv),patch.object(HOST,'package_policy',return_value=policy), \
                 patch.object(HOST.execution,'_runner',return_value=controller), \
                 patch.object(HOST.execution,'checkout_identity',return_value=('a'*40,'b'*40)), \
                 patch.object(HOST.inputs,'full_tree',return_value=self.tree), \
                 patch.object(HOST.execution,'platform_suites',return_value=[]), \
                 patch.object(HOST,'candidate_registry',return_value=proposed), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=HOST.main()
            controller.selection_output=output.read_text() if output.exists() else None
            self.assertIs(signal.getsignal(signal.SIGTERM),before)
        return result,controller

    def test_new_candidate_host_command_forces_prerequisites_before_execution(self):
        result,controller=self.cli(new_command=True,select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\n')
        controller.run_suites.assert_not_called()

    def test_new_candidate_command_is_required_and_failure_blocks_merging(self):
        result,controller=self.cli(new_command=True,runner_result=1)
        self.assertEqual(result,1)
        controller.run_suites.assert_called_once()

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
