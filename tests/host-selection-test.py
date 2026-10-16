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

    def selected(self, paths, *, tree=None, regular=True, unknown=False, trusted_tree=None,
                 target='main', base_tree=None, package_paths=()):
        return HOST.select(self.tree if tree is None else tree, paths, regular,
                           unknown=unknown, trusted_tree=self.tree if trusted_tree is None else trusted_tree,
                           target=target, base_tree=base_tree, package_paths=package_paths)

    def package_plan(self, path='browser-client/package-lock.json', *, formatting=False):
        project, profile = HOST.PACKAGE_LOCKS[path]
        return {'base': 'a'*40, 'candidate': 'b'*40, 'tree': 'c'*40,
                'consumer_generation': True, 'paths': [path],
                'package_set': [] if formatting else [project],
                'dependency_profiles': {'unknown': False, 'base': {'revision': 'a'*40},
                    'candidate': {'revision': 'b'*40, 'tree': 'c'*40}, 'projects': {
                        project: {'profile': 'none' if formatting else profile,
                                  'required': not formatting, 'changed_paths': [path],
                                  'reason': 'reviewed-lockfile-format-only' if formatting else
                                      'reviewed-single-dependency-security-update'}}}}

    def test_package_paths_require_complete_matching_independent_owner(self):
        for path in HOST.PACKAGE_LOCKS:
            for formatting in (False, True):
                plan = self.package_plan(path, formatting=formatting)
                self.assertEqual(HOST.package_owned_paths(plan), (path,))
                for mutation in ('generation', 'candidate', 'tree', 'base', 'unknown', 'profile', 'paths', 'owner'):
                    changed = deepcopy(plan)
                    project = HOST.PACKAGE_LOCKS[path][0]
                    profile = changed['dependency_profiles']['projects'][project]
                    if mutation == 'generation': changed['consumer_generation'] = False
                    elif mutation in {'candidate', 'tree', 'base'}: changed[mutation] = 'd'*40
                    elif mutation == 'unknown': changed['dependency_profiles']['unknown'] = True
                    elif mutation == 'profile': profile['profile'] = 'full'
                    elif mutation == 'paths': profile['changed_paths'].append(project + '/consumer.js')
                    elif formatting: profile['reason'] = 'unchanged-package-inputs'
                    else: changed['package_set'] = []
                    with self.subTest(path=path, formatting=formatting, mutation=mutation):
                        self.assertEqual(HOST.package_owned_paths(changed), ())

    def test_mixed_ci_and_owned_locks_keep_reviewed_production_graph_without_full_host(self):
        paths = tuple(HOST.PACKAGE_LOCKS)
        candidate = deepcopy(self.tree)
        for path in paths:
            candidate[path]['sha'] = 'b'*40
        selected = self.selected(['tools/branch-cleanup/cleanup.py', *paths],
                                 tree=candidate, base_tree=self.tree, package_paths=paths)
        self.assertEqual(set(selected['suites']), self.ci_quick)
        self.assertFalse(selected['full_host'])
        self.assertFalse(selected['include_platform'])
        self.assertEqual(selected['package_owned_paths'], sorted(paths))
        self.assertNotIn('results', selected)
        self.assertEqual(HOST.program_digest(candidate), HOST.REVIEWED_PROGRAMS)

    def test_ci_only_after_integrated_npm_update_keeps_the_same_reader_boundary(self):
        reviewed = deepcopy(self.tree)
        for path in HOST.PACKAGE_LOCKS:
            reviewed[path]['sha'] = 'a' * 40
        previous = deepcopy(self.tree)
        candidate = deepcopy(previous)
        changed = 'tools/branch-cleanup/cleanup.py'
        candidate[changed]['sha'] = 'b' * 40
        with patch.object(HOST, 'REVIEWED_PROGRAMS', HOST.program_digest(reviewed)):
            result = self.selected([changed], tree=candidate, base_tree=previous, trusted_tree=reviewed)
        self.assertFalse(result['full_host'])
        self.assertFalse(result['include_platform'])
        self.assertNotIn('package_owned_paths', result)
        # A reader identity is not permission to omit changed package checks.
        for path in HOST.PACKAGE_LOCKS:
            self.assertTrue(self.selected([changed, path], tree=candidate, base_tree=reviewed)['full_host'])
        appium = 'tests/device/ios/package-lock.json'
        drift = deepcopy(candidate)
        drift[appium] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
        self.assertNotEqual(HOST.program_digest(drift), HOST.program_digest(candidate))

    def test_owned_locks_do_not_hide_historical_or_new_product_differences(self):
        path = 'browser-client/package-lock.json'
        for reader in ('tests/platform-profile.json', 'scripts/system/chat.js',
                       'libraries/shared/src/new-package-reader.h'):
            candidate = deepcopy(self.tree)
            candidate[path]['sha'] = 'b'*40
            candidate[reader] = {'mode': '100644', 'type': 'blob', 'sha': 'c'*40}
            with self.subTest(reader=reader):
                selected = self.selected(['tools/branch-cleanup/cleanup.py', path], tree=candidate,
                                         base_tree=self.tree, package_paths=(path,))
                self.assertTrue(selected['full_host'])
                self.assertTrue(selected['include_platform'])

    def test_owned_locks_keep_required_changed_control_plane_owner(self):
        path = 'browser-client/package-lock.json'
        candidate = deepcopy(self.tree); candidate[path]['sha'] = 'b'*40
        previous = deepcopy(self.tree); previous[HOST.CONTROL_PLANE]['sha'] = 'c'*40
        selected = self.selected([HOST.CONTROL_PLANE, path], tree=candidate,
                                 base_tree=previous, package_paths=(path,))
        self.assertEqual(set(selected['suites']), self.ci_quick | {'device-control-plane-full'})
        self.assertTrue(selected['full_host'])
        self.assertFalse(selected['include_platform'])

    def test_owned_locks_require_ordinary_complete_base_inputs_and_regular_inventory(self):
        path = 'browser-client/package-lock.json'
        for mode in ('missing', '100755', '120000', '160000'):
            for side in ('base', 'candidate'):
                candidate, previous = deepcopy(self.tree), deepcopy(self.tree)
                changed = candidate if side == 'candidate' else previous
                if mode == 'missing': del changed[path]
                else: changed[path] = {'mode': mode, 'type': 'commit' if mode == '160000' else 'blob', 'sha': 'b'*40}
                with self.subTest(mode=mode, side=side):
                    self.assertTrue(self.selected([path], tree=candidate, base_tree=previous,
                                                  package_paths=(path,))['full_host'])
        self.assertTrue(self.selected([path], package_paths=(path,))['full_host'])
        self.assertTrue(self.selected([path], base_tree=self.tree, package_paths=(path,), regular=False)['full_host'])
        with self.assertRaises(ValueError):
            self.selected(['interface/src/Application.cpp'], package_paths=('interface/src/Application.cpp',))

    def test_reviewed_generation_binds_actual_reader_inventory(self):
        tree=deepcopy(self.tree)
        del tree['tests/device/contracts/tablet/pages.json']
        self.assertNotEqual(HOST.program_digest(tree), HOST.REVIEWED_PROGRAMS)

    def test_finite_ci_executables_have_separate_complete_ordinary_inventory(self):
        previous = deepcopy(self.tree)
        paths = sorted(HOST.CI_EXECUTABLE_PATHS)
        for path in paths:
            self.assertEqual(previous[path]['mode'], '100755')
            previous[path]['sha'] = 'b' * 40
        plan = {'unknown': False, 'regular': False, 'paths': paths}
        self.assertTrue(HOST.regular_ci_inventory(plan, previous, self.tree))
        selected = self.selected(paths, regular=False, base_tree=previous)
        self.assertFalse(selected['full_host'])
        self.assertFalse(selected['include_platform'])
        self.assertIn('project-runner', selected['suites'])
        for changes in ({'unknown': True}, {'paths': paths[:-1]}):
            self.assertFalse(HOST.regular_ci_inventory({**plan, **changes}, previous, self.tree))
        self.assertFalse(HOST.regular_ci_inventory(plan, None, self.tree))
        drift = deepcopy(previous)
        drift['unowned/input.py'] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
        self.assertFalse(HOST.regular_ci_inventory(plan, drift, self.tree))
        self.assertTrue(self.selected(paths, regular=False, base_tree=drift)['full_host'])

    def test_ci_executable_waiver_rejects_modes_missing_files_and_unknown_executables(self):
        path = 'tests/project-suite-self-test.py'
        previous = deepcopy(self.tree)
        previous[path]['sha'] = 'b' * 40
        plan = {'unknown': False, 'regular': False, 'paths': [path]}
        for side in ('base', 'candidate'):
            for mode in ('missing', '100644', '120000', '160000'):
                base, candidate = deepcopy(previous), deepcopy(self.tree)
                changed = base if side == 'base' else candidate
                if mode == 'missing':
                    del changed[path]
                else:
                    changed[path]['mode'] = mode
                    changed[path]['type'] = 'commit' if mode == '160000' else 'blob'
                with self.subTest(side=side, mode=mode):
                    self.assertFalse(HOST.regular_ci_inventory(plan, base, candidate))
        for extra in ('tools/branch-cleanup/cleanup.py', 'docs/NEW.md'):
            candidate = deepcopy(self.tree)
            candidate[extra] = {'mode': '100755', 'type': 'blob', 'sha': 'c' * 40}
            self.assertFalse(HOST.regular_ci_inventory({**plan, 'paths': [path, extra]}, previous, candidate))

    def test_two_separate_npm_owners_compose_with_the_finite_executable_inventory(self):
        previous, candidate = deepcopy(self.tree), deepcopy(self.tree)
        executable = 'tests/project-suite-self-test.py'
        previous[executable]['sha'] = 'b' * 40
        plan = self.package_plan()
        for path in HOST.PACKAGE_LOCKS:
            item = self.package_plan(path)
            plan['dependency_profiles']['projects'].update(item['dependency_profiles']['projects'])
            candidate[path]['sha'] = 'c' * 40
        plan.update({'unknown': False, 'regular': False,
                     'paths': [executable, *HOST.PACKAGE_LOCKS],
                     'package_set': [value[0] for value in HOST.PACKAGE_LOCKS.values()]})
        self.assertTrue(HOST.regular_ci_inventory(plan, previous, candidate))
        result = self.selected(plan['paths'], regular=False, tree=candidate, base_tree=previous,
                               package_paths=HOST.package_owned_paths(plan))
        self.assertFalse(result['full_host'])
        self.assertEqual(set(result['package_owned_paths']), set(HOST.PACKAGE_LOCKS))
        plan['package_set'] = []
        self.assertFalse(HOST.regular_ci_inventory(plan, previous, candidate))

    def test_cleanup_and_ci_tests_keep_ci_contracts_and_omit_production_contracts(self):
        for paths in (['tools/branch-cleanup/cleanup.py'], ['tests/branch-cleanup-test.py'],
                      ['tools/branch-cleanup/adoption.py', 'tests/branch-cleanup-test.py',
                       '.github/workflows/branch-cleanup.yml', 'docs/AUTOMATIC_BRANCH_CLEANUP.md'],
                      ['tools/repository-checks/check.py'], ['tests/workflow-contract-test.py'],
                      ['.github/workflows/project-tests.yml'],
                      ['.github/workflows/parent-qualification.yml'],
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
                tree=deepcopy(self.tree)
                if path == 'tests/run-project-tests.py':
                    tree[path]['sha']='b'*40  # A changed implementation is not an owned-path waiver.
                result=self.selected(['tools/branch-cleanup/cleanup.py',path],tree=tree)
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
        for mode in ('deleted','100755','120000','160000'):
            for side in ('candidate','trusted'):
                with self.subTest(mode=mode,side=side):
                    tree=deepcopy(self.tree);path='tests/device/run_control_plane_tests.py'
                    if mode=='deleted': del tree[path]
                    else: tree[path]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                    result=self.selected(['tools/branch-cleanup/cleanup.py'],
                                         tree=tree if side=='candidate' else self.tree,
                                         trusted_tree=tree if side=='trusted' else self.tree)
                    self.assertTrue(result['full_host'])
                    self.assertTrue(result['include_platform'])

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

    def test_six_child_graphs_are_target_specific_and_initial_launcher_owner_is_required(self):
        targets=set(HOST.REVIEWED_CHILD_PROGRAMS)
        self.assertEqual(targets,{'apple-main','apple-ios','android-main','android-phone','android-vr','android-vr-pico'})
        # Genuine full parent integration brings the common reporter fix to VR;
        # its product reader graph then equals Android-main's graph. Contextual
        # execution/provenance still belongs to each independently checked target.
        self.assertEqual(HOST.REVIEWED_CHILD_PROGRAMS['android-main'], HOST.REVIEWED_CHILD_PROGRAMS['android-vr'])
        self.assertEqual(len(set(HOST.REVIEWED_CHILD_PROGRAMS.values())),5)
        # Portable graph fixtures do not require historical objects in shallow CI.
        # The six actual immutable topic trees are separately checked locally.
        for index,target in enumerate(sorted(targets)):
            with self.subTest(target=target):
                child=deepcopy(self.tree)
                child['tests/platform-profile.json']['sha']=str(index+1)*40
                digest=HOST.program_digest(child)
                previous=deepcopy(child);previous[HOST.CONTROL_PLANE]['sha']='a'*40
                with patch.dict(HOST.REVIEWED_CHILD_PROGRAMS,{target:digest}):
                    initial=self.selected([HOST.CONTROL_PLANE,'tools/branch-cleanup/cleanup.py'],
                                          tree=child,target=target,base_tree=previous)
                    self.assertEqual(set(initial['suites']),self.ci_quick|{'device-control-plane-full'})
                    self.assertTrue(initial['full_host'])
                    self.assertFalse(initial['include_platform'])
                    later=self.selected(['tools/branch-cleanup/cleanup.py'],tree=child,target=target,base_tree=child)
                    self.assertEqual(set(later['suites']),self.ci_quick)
                    self.assertFalse(later['full_host'])
                    self.assertFalse(later['include_platform'])
                    self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=child,target='main')['include_platform'])

    def test_only_explicitly_reviewed_predecessor_reader_generations_remain_compatible(self):
        previous = deepcopy(self.tree)
        previous['tools/test-evidence/validate-sync.py']['sha'] = 'b' * 40
        with patch.dict(HOST.REVIEWED_PREDECESSORS, {'main': HOST.program_digest(previous)}):
            selected = self.selected(['tools/branch-cleanup/cleanup.py'], tree=previous)
            self.assertFalse(selected['full_host'])
            changed = deepcopy(previous)
            changed['libraries/shared/src/new-reader.cpp'] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'], tree=changed)['full_host'])

    def test_immutable_launcher_difference_requires_owner_even_without_caller_path_hint(self):
        previous=deepcopy(self.tree);previous[HOST.CONTROL_PLANE]['sha']='b'*40
        selected=self.selected(['tools/branch-cleanup/cleanup.py'],base_tree=previous)
        self.assertIn('device-control-plane-full',selected['suites'])
        self.assertTrue(selected['full_host'])

    def test_exact_ci_admissions_do_not_waive_neighboring_tests_or_runtime_readers(self):
        self.assertEqual(len(HOST.CI_ROLLOUT_PATHS),32)
        for path in ('tools/test-evidence/new-reader.py','tests/project-suite-self-test-extra.py',
                     '.github/workflows/repository-checks-extra.yml'):
            self.assertTrue(self.selected([path])['include_platform'],path)
        for path in ('tests/run-project-tests.py','tools/test-evidence/execution.py',
                     'tools/test-evidence/inputs.py','tools/test-evidence/validate-sync.py'):
            changed=deepcopy(self.tree);changed[path]['sha']='b'*40
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=changed)['include_platform'],path)

    def test_both_consumed_platform_readmes_and_optional_membership_remain_bound(self):
        reviewed=deepcopy(self.tree)
        docs=('android/vr/common/openxr/README.md','android/phone/device-tests/parity/fixtures/README.md')
        for path in docs:
            reviewed[path]={'mode':'100644','type':'blob','sha':'a'*40}
        with patch.object(HOST,'REVIEWED_PROGRAMS',HOST.program_digest(reviewed)):
            for path in (*docs,'tests/platform-profile.json','libraries/shared/src/PhoneLoadingDiagnostics.h',
                         'tests/json.py','tests/json/__init__.py','json.py','json/__init__.py'):
                for side in ('candidate','trusted'):
                    with self.subTest(path=path,side=side):
                        changed=deepcopy(reviewed)
                        changed[path]={'mode':'100644','type':'blob','sha':'b'*40}
                        result=self.selected(['tools/branch-cleanup/cleanup.py'],
                                             tree=changed if side=='candidate' else reviewed,
                                             trusted_tree=changed if side=='trusted' else reviewed)
                        self.assertEqual(set(result['suites']),self.all_names)
                        self.assertTrue(result['include_platform'])
            for path in docs:
                for mode in ('deleted','100755','120000','160000','rename'):
                    changed=deepcopy(reviewed)
                    if mode=='deleted':del changed[path]
                    elif mode=='rename':changed[path+'.new']=changed.pop(path)
                    else:changed[path]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                    self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=changed,
                                                  trusted_tree=reviewed)['include_platform'],(path,mode))

    def test_excluded_ci_symlink_or_gitlink_cannot_get_partial_verification(self):
        for mode in ('120000','160000'):
            for side in ('candidate','trusted'):
                changed=deepcopy(self.tree)
                changed['tools/branch-cleanup/cleanup.py']={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                result=self.selected(['tests/branch-cleanup-test.py'],
                                     tree=changed if side=='candidate' else self.tree,
                                     trusted_tree=changed if side=='trusted' else self.tree)
                self.assertTrue(result['include_platform'])

    def test_target_comes_from_server_base_or_push_ref_not_head_branch(self):
        self.assertEqual(HOST.target_branch({'pull_request':{'base':{'ref':'apple-ios'},'head':{'ref':'main'}}}),'apple-ios')
        self.assertEqual(HOST.target_branch({'ref':'refs/heads/android-phone'}),'android-phone')
        self.assertIsNone(HOST.target_branch({'ref':'refs/tags/main'}))
        self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],target='unknown')['include_platform'])

    def cli(self, runner_result=0, expected='c'*64, cancel=False, new_command=False,
            select_only=False, full_host=False, control_changed=False, platform=False):
        plan={'candidate':'a'*40,'plan':'c'*64,'host_mode':'full',
              'paths':(['interface/src/Application.cpp'] if full_host else
                       [HOST.CONTROL_PLANE] if control_changed else ['tools/branch-cleanup/cleanup.py']),
              'regular':True,'unknown':False}
        proposed=deepcopy(self.registry)
        if new_command:
            proposed['suites']['new-host-contract']=deepcopy(proposed['suites']['branch-cleanup'])
            proposed['suites']['new-host-contract']['layer']='host'
            proposed['suites']['new-host-contract']['command']=['python','tests/new-required-host-contract.py']
        policy=SimpleNamespace(validate_wiring=Mock(),candidate_plan=Mock(return_value=plan))
        def run(args,suites,cancelled):
            if new_command or full_host:
                self.assertTrue(self.all_names <= {suite[0] for suite in suites})
                if platform:
                    self.assertIn('fixture-platform',{suite[0] for suite in suites})
                if new_command:
                    self.assertEqual(sum(command[-1]=='tests/new-required-host-contract.py' for _,_,command in suites),1)
            else:
                expected_names=self.ci_quick | ({'device-control-plane-full'} if control_changed else set())
                self.assertEqual({suite[0] for suite in suites},expected_names)
                self.assertEqual(args.host_timeout,900)
                if control_changed:
                    command=next(command for name,_,command in suites if name=='device-control-plane-full')
                    self.assertIn('--require-qml',command)
            if cancel:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                self.assertEqual(cancelled,[signal.SIGTERM])
            return runner_result
        controller=SimpleNamespace(Suite=lambda *args:args,run_suites=Mock(side_effect=run))
        with tempfile.TemporaryDirectory() as folder:
            event=Path(folder)/'event.json';event.write_text('{"ref":"refs/heads/main"}')
            argv=['host_selection.py','--candidate',str(ROOT),'--event',str(event),'--sha','a'*40,
                  '--expected-plan',expected,'--junit',str(Path(folder)/'result.xml')]
            output=Path(folder)/'selection.txt'
            report=Path(folder)/'selection.json'
            argv += ['--selection-report',str(report)]
            if select_only:
                argv += ['--select-only','--output',str(output)]
            before=signal.getsignal(signal.SIGTERM)
            with patch.object(sys,'argv',argv),patch.object(HOST,'package_policy',return_value=policy), \
                 patch.object(HOST.execution,'_runner',return_value=controller), \
                 patch.object(HOST.execution,'checkout_identity',return_value=('a'*40,'b'*40)), \
                 patch.object(HOST.inputs,'full_tree',return_value=self.tree), \
                 patch.object(HOST.execution,'platform_suites',return_value=(
                     [('fixture-platform',['python','tests/fixture-platform.py'])] if platform else [])), \
                 patch.object(HOST,'candidate_registry',return_value=proposed), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=HOST.main()
            controller.selection_output=output.read_text() if output.exists() else None
            controller.selection_report=json.loads(report.read_text()) if report.exists() else None
            self.assertIs(signal.getsignal(signal.SIGTERM),before)
        return result,controller

    def test_new_candidate_host_command_forces_prerequisites_before_execution(self):
        result,controller=self.cli(new_command=True,select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=false\n')
        self.assertFalse(controller.selection_report['complete_receipt_required'])
        controller.run_suites.assert_not_called()

    def test_partial_host_owner_keeps_qt_without_claiming_full_receipt(self):
        result,controller=self.cli(control_changed=True,select_only=True,platform=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=false\n')
        report=controller.selection_report
        self.assertFalse(report['complete_receipt_required'])
        self.assertFalse(report['reusable'])
        self.assertEqual(set(report['selection']['suites']),self.ci_quick|{'device-control-plane-full'})
        self.assertEqual(report['selection']['platform_suites'],[])
        self.assertEqual(report['selection']['omitted_platform_suites'],['fixture-platform'])
        controller.run_suites.assert_not_called()

    def test_partial_host_owner_failure_blocks_and_unchanged_platform_is_not_executed(self):
        result,controller=self.cli(control_changed=True,platform=True,runner_result=1)
        self.assertEqual(result,1)
        controller.run_suites.assert_called_once()

    def test_real_runner_preserves_qml_requirement_900_seconds_and_host_failure(self):
        runner=HOST.execution._runner()
        command=tuple(self.registry['suites']['device-control-plane-full']['command'])
        suite=runner.Suite('device-control-plane-full','host',command)
        args=SimpleNamespace(timeout=240,host_timeout=900,native_build_dir=None,junit=None,fail_fast=False)
        with patch.object(runner,'run_command',return_value=(1,'fake selected host failure','')) as execute, \
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            status=runner.run_suites(args,[suite],[])
        self.assertEqual(status,1)
        actual,timeout,cancelled=execute.call_args.args
        self.assertIn('--require-qml',actual)
        self.assertEqual(actual[-2:],['--timeout-seconds','900'])
        self.assertEqual(timeout,900)
        self.assertEqual(cancelled,[])

    def test_full_fallback_executes_declared_platform_instead_of_waiving_it(self):
        result,controller=self.cli(full_host=True,platform=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_report['selection']['platform_suites'],['fixture-platform'])
        self.assertEqual(controller.selection_report['selection']['omitted_platform_suites'],[])

    def test_partial_parent_plan_cannot_claim_full_or_reused_execution(self):
        result,controller=self.cli(select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=false\ncomplete_receipt=false\n')
        report=controller.selection_report
        self.assertFalse(report['reusable'])
        self.assertEqual(report['kind'],'host-impact-selection')
        self.assertEqual(report['candidate'],'a'*40)
        self.assertEqual(set(report['selection']['suites']),self.ci_quick)
        self.assertEqual(set(report['omitted_suites']),self.all_names-self.ci_quick)
        self.assertNotIn('results',report)
        controller.run_suites.assert_not_called()

    def test_product_parent_plan_keeps_legacy_complete_receipt_route(self):
        result,controller=self.cli(select_only=True,full_host=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=true\n')
        self.assertTrue(controller.selection_report['complete_receipt_required'])
        self.assertEqual(controller.selection_report['omitted_suites'],[])
        controller.run_suites.assert_not_called()

    def test_parent_template_keeps_full_receipts_separate_from_partial_execution(self):
        import yaml
        path=ROOT/'tools/repository-checks/workflows/host/parent-qualification.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['qualify-parent']['steps']
        selection=next(s for s in steps if s.get('id')=='host')
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        full=next(s for s in steps if s['name']=='Run complete host qualification')
        partial=next(s for s in steps if s['name']=='Run independently selected parent host contracts')
        self.assertLess(steps.index(selection),steps.index(qt))
        self.assertEqual(qt['if'],"steps.host.outputs.full_host == 'true'")
        self.assertEqual(full['if'],"steps.host.outputs.complete_receipt == 'true'")
        self.assertIn("steps.host.outputs.complete_receipt == 'false'",partial['if'])
        self.assertIn('trusted/tools/test-evidence/run.py',full['run'])
        self.assertIn('trusted/tools/repository-checks/host_selection.py',partial['run'])
        for name in ('Create content-addressed qualification evidence','Upload immutable qualification evidence'):
            step=next(s for s in steps if s['name']==name)
            self.assertEqual(step['if'],"steps.host.outputs.complete_receipt == 'true'")
        upload=next(s for s in steps if s['name']=='Upload qualification test reports')
        self.assertIn('host-selection.json',upload['with']['path'])
        self.assertIn("always()",upload['if'])
        generation=next(g for g in HOST.package_policy().workflow_generations() if g['name']=='parent-host-impact-v1')
        import hashlib
        raw=path.read_bytes()
        expected=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.assertEqual(generation['workflows']['.github/workflows/parent-qualification.yml']['sha'],expected)

    def test_parent_impact_report_cannot_replace_full_sync_qualification(self):
        source=ROOT/'tools/test-evidence/validate-sync-test.py'
        spec=importlib.util.spec_from_file_location('parent_sync_consumer_fixture',source)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case=module.IsolatedConsumerTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        gate=module.VALIDATION._gate()
        diagnostic={'schema':1,'kind':'host-impact-selection','reusable':False,
                    'candidate':case.parent,'tree':case.tree_sha,
                    'selection':{'suites':['alpha'],'full_host':False},'omitted_suites':['beta']}
        request=SimpleNamespace(repository='noah-l-frank/overte',repository_id=1319052603,
                                parent='main',parent_sha=case.parent)
        def verify(*arguments):
            with patch.object(gate,'artifact_evidence',return_value=({},diagnostic)):
                try:
                    return gate.verify_evidence(object(),{},request)
                except gate.EvidenceError as error:
                    self.assertIn('mismatched schema',str(error))
                    raise
        case.gate.verify_evidence=verify
        case.gate.EvidenceError=gate.EvidenceError
        result=case.validate()
        self.assertEqual(result['mode'],'fallback')
        self.assertEqual(result['reused_suites'],[])
        self.assertEqual(set(case.executed()),{'alpha','beta'})
        self.assertTrue(result['execution']['include_platform'])

    def test_parent_execution_route_rejects_missing_or_contradictory_outputs(self):
        import yaml
        import subprocess
        path=ROOT/'tools/repository-checks/workflows/host/parent-qualification.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['qualify-parent']['steps']
        check=next(s for s in steps if s['name']=='Require a complete host execution route')
        select=next(s for s in steps if s.get('id')=='host')
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        self.assertLess(steps.index(select),steps.index(check))
        self.assertLess(steps.index(check),steps.index(qt))
        for full in ('true','false','','unknown'):
            for complete in ('true','false','','unknown'):
                actual=subprocess.run(['/bin/bash','-c',check['run']],capture_output=True,
                                      env={'FULL_HOST':full,'COMPLETE_RECEIPT':complete})
                self.assertEqual(actual.returncode==0,(full,complete) in {
                    ('true','true'),('true','false'),('false','false')},(full,complete))

    def test_new_candidate_command_is_required_and_failure_blocks_merging(self):
        result,controller=self.cli(new_command=True,runner_result=1)
        self.assertEqual(result,1)
        controller.run_suites.assert_called_once()

    def test_cli_rejects_mismatched_candidate_plan_before_executing_any_command(self):
        result,controller=self.cli(expected='d'*64)
        self.assertEqual(result,1)
        self.assertIsNone(controller.selection_report)
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
