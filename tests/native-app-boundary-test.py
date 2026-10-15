#!/usr/bin/env python3
"""Real-Git app closure and independent required-owner identity regressions."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BROWSER = load('app_boundary_browser', 'tools/repository-checks/browser_cpu.py')
APP = BROWSER.app_inputs()
OWNER = load('app_boundary_native_owner', 'tools/native-tests/browser-owner.py')
NATIVE = load('app_boundary_native_router', 'tools/native-tests/check.py')
SELECT = load('app_boundary_native_selection', 'tools/native-tests/select.py')
GATE = load('app_boundary_final', 'tools/repository-checks/check.py')


class AppBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='overte-app-boundary-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root, self.trusted = self.directory / 'candidate', self.directory / 'trusted'
        self.root.mkdir(); self.trusted.mkdir()
        for relative in ('.github', 'tools/repository-checks', 'tools/test-evidence',
                         'tools/native-tests', 'tools/ios-build-qualification'):
            shutil.copytree(ROOT / relative, self.trusted / relative,
                            ignore=shutil.ignore_patterns('__pycache__'))
        for relative in (*APP.CODE_INPUTS, 'tests/requirements-host.txt', 'tests/requirements-repository.txt',
                         'tests/run-project-tests.py', 'tests/platform-profile.json',
                         'tools/sbom/requirements-validation.txt', 'tools/sync-test-reuse/qualification.py'):
            destination = self.trusted / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        browser = load('fixture_current_browser', self.trusted / 'tools/repository-checks/browser_cpu.py')
        app = browser.app_inputs()
        owner = load('fixture_current_owner', self.trusted / 'tools/native-tests/browser-owner.py')
        native = load('fixture_current_native', self.trusted / 'tools/native-tests/check.py')
        gate = load('fixture_current_final', self.trusted / 'tools/repository-checks/check.py')
        context = patch.dict(globals(), BROWSER=browser, APP=app, OWNER=owner, NATIVE=native, GATE=gate)
        context.start(); self.addCleanup(context.stop)
        self.config_path = self.trusted / BROWSER.CONFIGURATION
        config = json.loads(self.config_path.read_text())
        config['browser_client_required_branches'] = ['main']
        self.config_path.write_text(json.dumps(config, indent=2) + '\n')
        self.ledger = json.loads((self.trusted / APP.POLICY).read_text())
        self.ledger['enabled'] = True
        self.ledger_path = self.trusted / APP.POLICY
        self.save_ledger()
        self.profile, self.profile_identity = OWNER.load_profile()
        for context in (patch.object(APP, 'ACTIVATION_READY', True),
                        patch.object(GATE, 'browser_policy', return_value=BROWSER),
                        patch.object(NATIVE, 'repository_checks', return_value=GATE),
                        patch.object(NATIVE, 'browser_ownership', return_value=OWNER),
                        patch.object(OWNER, 'load_profile', return_value=(self.profile, self.profile_identity))):
            context.start(); self.addCleanup(context.stop)
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'user.name', 'App reader fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.fileMode', 'true')
        self.write(BROWSER.WORKFLOW, BROWSER.canonical_workflow(self.trusted))
        self.write(BROWSER.OUTER_WORKFLOW, BROWSER.trusted_bytes(BROWSER.OUTER_TEMPLATE, self.trusted))
        for name in ('project-tests.yml', 'parent-qualification.yml', 'sync-validation.yml'):
            self.write('.github/workflows/' + name, (ROOT / '.github/workflows' / name).read_bytes())
        for name in APP.owner_sources(self.trusted):
            self.write(name, (self.trusted / name).read_bytes())
            (self.root / name).chmod(0o755 if name == 'tests/run-project-tests.py' else 0o644)
        for name, source in {
            'CMakeLists.txt': 'project(ReviewedReaderFixture)\n',
            'conanfile.py': 'from conan import ConanFile\n',
            'tools/shadergen.py': 'import json\n',
            'interface/resources/resources.qrc': '<RCC/>\n',
            'interface/resources/README.md': 'Packaged Markdown\n',
            'browser-client/src/world.ts': 'export const world = true;\n',
            'tools/branch-cleanup/cleanup.py': 'raise RuntimeError("not executed")\n',
            'tools/test-evidence/sandbox.py': 'raise RuntimeError("not executed")\n',
            'tests/run-project-tests.py': 'raise RuntimeError("not executed")\n',
        }.items():
            self.write(name, source.encode())
        (self.root / 'tests/run-project-tests.py').chmod(0o755)
        self.base = self.commit('Reviewed immutable application readers and independent owner')
        self.reviewed = self.boundary(self.base)
        self.ledger['reader_boundary'] = self.reviewed
        self.save_ledger()

    def save_ledger(self):
        self.ledger_path.write_text(json.dumps(self.ledger, indent=2) + '\n')

    def git(self, *arguments):
        return subprocess.check_output(['git', *arguments], cwd=self.root,
                                       stderr=subprocess.PIPE, text=True).strip()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def commit(self, message):
        self.git('add', '-A'); self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def boundary(self, revision):
        return APP.boundary(BROWSER.snapshot(self.root, revision), self.profile, BROWSER, self.trusted)

    def merge(self, changes, *, base=None):
        base = base or self.base
        self.git('checkout', '-q', '--detach', base)
        for name, data in changes.items():
            if data is None:
                (self.root / name).unlink()
            else:
                self.write(name, data)
        head = self.commit('Change immutable fixture inputs')
        self.git('checkout', '-q', '-B', 'fixture-merge', base)
        self.git('merge', '-q', '--no-ff', '-m', 'Exact app-reader candidate', head)
        sha = self.git('rev-parse', 'HEAD')
        repository = deepcopy(BROWSER.REPOSITORY)
        return {'repository': repository, 'pull_request': {
            'base': {'ref': 'main', 'repo': repository, 'sha': base},
            'head': {'ref': 'fix/main/app-reader-fixture', 'repo': repository, 'sha': head}}}, sha

    def test_known_ci_edits_do_not_stale_app_closure_or_waive_required_full_owner(self):
        event, sha = self.merge({'tools/branch-cleanup/cleanup.py': b'changed cleanup\n',
            'tools/test-evidence/sandbox.py': b'changed sandbox\n', 'tests/run-project-tests.py': b'changed runner\n',
            'browser-client/src/world.ts': b'changed frontend\n'})
        self.assertEqual(self.boundary(sha), self.reviewed)
        selected = NATIVE.candidate_plan(self.root, event, sha)
        self.assertEqual(selected['mode'], 'skip')
        handoff = selected['browser_handoff']
        plan = BROWSER.route(event, 'pull_request', self.root, sha, policy_root=self.trusted)
        self.assertEqual(plan['mode'], 'full')
        self.assertEqual(handoff['owner_contract'], APP.owner_identity(self.trusted))
        self.assertEqual(handoff['browser_plan'], plan['plan'])
        self.assertEqual(NATIVE.plan(['browser-client/src/world.ts'])['mode'], 'full')
        job = {'result': 'success', 'outputs': {'candidate': sha, 'plan': plan['plan'], 'verified': 'true'}}
        BROWSER.verify_outer(job, BROWSER.outer_outputs(plan), plan)
        for status in ('failure', 'skipped', 'cancelled', None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                BROWSER.verify_outer({**job, 'result': status}, BROWSER.outer_outputs(plan), plan)
        for mode in ('skip', 'cpu', None):
            with patch.object(BROWSER, 'route', return_value={'mode': mode}):
                self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')

    def test_source_guard_default_off_and_json_cannot_enable_or_bless_missing_anchor(self):
        event, sha = self.merge({'tools/branch-cleanup/cleanup.py': b'changed cleanup\n',
                                 'browser-client/src/world.ts': b'changed frontend\n'})
        with patch.object(APP, 'ACTIVATION_READY', False):
            self.assertFalse(APP.enabled(BROWSER.trusted_bytes, self.trusted))
            self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
        self.ledger['reader_boundary'] = None; self.save_ledger()
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
        with self.assertRaises(ValueError):
            BROWSER.route(event, 'pull_request', self.root, sha, policy_root=self.trusted)

    def test_unknown_paths_import_shadows_build_inputs_and_packaged_markdown_are_visible(self):
        for name in ('tools/test-evidence/new.py', 'tools/branch-cleanup/new.py', 'tools/json.py', 'json.py',
                     'tools/__init__.py', 'package.json', 'tools/package.json', 'tools/ambient.pth',
                     'tools/test-evidence/package.json', 'tools/test-evidence/ambient.pth',
                     'tools/test-evidence/json.so', 'tools/test-evidence/SANDBOX.py',
                     'tools/test-evidence/CMakeLists.txt', 'tools/test-evidence/new.cmake',
                     'tools/test-evidence/new.cpp', 'tools/test-evidence/new.qrc',
                     'tests/device/contracts/new.py', 'tools/native-tests/run.py',
                     'interface/resources/README.md', 'tools/jsdoc/plugins/hifi.js'):
            with self.subTest(path=name):
                event, sha = self.merge({name: b'new unreviewed input\n', 'browser-client/src/world.ts': b'frontend\n'})
                self.assertNotEqual(self.boundary(sha), self.reviewed)
                self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')

    def test_changed_reader_then_later_ci_and_frontend_edits_stay_full(self):
        for name, source in {
            'CMakeLists.txt': b'file(GLOB_RECURSE INPUTS tools/test-evidence/*.py)\n',
            'conanfile.py': b'import sys; sys.path.insert(0, "tools/test-evidence"); import sandbox\n',
            'tools/shadergen.py': b'import sys; sys.path.insert(0, "tools/branch-cleanup"); import cleanup\n',
            'interface/resources/resources.qrc': b'<RCC><qresource><file>../../tools/test-evidence/sandbox.py</file></qresource></RCC>\n',
        }.items():
            with self.subTest(reader=name):
                self.git('checkout', '-q', '--detach', self.base)
                self.write(name, source)
                integrated = self.commit('A reader begins consuming a classified CI input')
                event, sha = self.merge({'tools/test-evidence/sandbox.py': b'changed\n',
                                         'browser-client/src/world.ts': b'frontend\n'}, base=integrated)
                self.assertNotEqual(self.boundary(integrated), self.reviewed)
                self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')

    def test_modes_alias_gitlink_rename_and_deletion_cannot_hide_unknown_inputs(self):
        path = 'tools/branch-cleanup/cleanup.py'
        for mode in ('executable', 'symlink', 'gitlink'):
            with self.subTest(mode=mode):
                self.git('checkout', '-q', '--detach', self.base)
                target = self.root / path
                if mode == 'executable': target.chmod(0o755)
                else:
                    target.unlink()
                    if mode == 'symlink': target.symlink_to('../../browser-client/src/world.ts')
                    else:
                        subprocess.run(['git', 'clone', '-q', '--shared', '--no-checkout',
                                        str(self.root), str(target)], check=True, stderr=subprocess.PIPE)
                        self.git('update-index', '--add', '--cacheinfo', '160000,' + self.base + ',' + path)
                if mode == 'gitlink':
                    self.git('commit', '-qm', 'Replace reviewed CI file with a Git dependency')
                    changed = self.git('rev-parse', 'HEAD')
                else: changed = self.commit('Change classified CI entry mode')
                event, sha = self.merge({'browser-client/src/world.ts': b'frontend\n'}, base=changed)
                self.assertNotEqual(self.boundary(sha), self.reviewed)
                self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
                if mode == 'gitlink':
                    shutil.rmtree(target)
        self.git('checkout', '-q', '--detach', self.base)
        (self.root / 'tests/run-project-tests.py').chmod(0o644)
        changed = self.commit('Remove the exact reviewed runner executable mode')
        event, sha = self.merge({'browser-client/src/world.ts': b'frontend\n'}, base=changed)
        self.assertNotEqual(self.boundary(sha), self.reviewed)
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
        event, sha = self.merge({path: None, 'tools/branch-cleanup/renamed.py': b'renamed\n',
                                 'browser-client/src/world.ts': b'frontend\n'})
        self.assertNotEqual(self.boundary(sha), self.reviewed)
        event, sha = self.merge({path: None, 'browser-client/src/world.ts': b'frontend\n'})
        self.assertEqual(self.boundary(sha), self.reviewed, 'CI-only deletion is app-neutral')
        event, sha = self.merge({BROWSER.OUTER_WORKFLOW: None, 'browser-client/src/world.ts': b'frontend\n'})
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')

    def test_sparse_candidate_and_materialized_tampering_cannot_change_immutable_plan(self):
        event, sha = self.merge({'browser-client/src/world.ts': b'frontend\n'})
        full = self.boundary(sha)
        self.git('sparse-checkout', 'set', '--cone', '.github')
        self.assertFalse((self.root / 'tools').exists())
        self.assertEqual(self.boundary(sha), full)
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'skip')
        self.git('sparse-checkout', 'disable')
        self.write('CMakeLists.txt', b'not immutable Git source\n')
        self.assertEqual(self.boundary(sha), full)

    def test_required_owner_helper_deletion_mode_and_predecessor_omission_are_rejected(self):
        for name in ('tools/repository-checks/browser_cpu.py', 'tools/repository-checks/package_checks.py',
                     'tools/test-evidence/inputs.py', APP.POLICY):
            with self.subTest(path=name):
                event, sha = self.merge({name: None, 'browser-client/src/world.ts': b'frontend\n'})
                self.assertEqual(self.boundary(sha), self.reviewed, 'App independence is not owner presence proof')
                self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
                with self.assertRaisesRegex(ValueError, 'required Browser owner input'):
                    BROWSER.route(event, 'pull_request', self.root, sha, policy_root=self.trusted)
        name = 'tools/repository-checks/browser_cpu.py'
        self.git('checkout', '-q', '--detach', self.base)
        (self.root / name).chmod(0o755)
        base = self.commit('Unreviewed required helper executable mode')
        event, sha = self.merge({'browser-client/src/world.ts': b'frontend\n'}, base=base)
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')
        self.git('checkout', '-q', '--detach', self.base)
        original = (self.root / name).read_bytes()
        (self.root / name).unlink()
        base = self.commit('Predecessor lacks a required owner helper')
        event, sha = self.merge({name: original, 'browser-client/src/world.ts': b'frontend\n'}, base=base)
        self.assertEqual(NATIVE.candidate_plan(self.root, event, sha)['mode'], 'full')

    def test_configured_collision_guard_checks_ci_sources_without_extension_filter(self):
        paths = APP.ci_paths(BROWSER, self.trusted)
        for name in ('tools/branch-cleanup/cleanup.py', 'tools/test-evidence/sandbox.py',
                     'tools/test-evidence/../test-evidence/sandbox.py', 'tests/run-project-tests.py'):
            for generated in (False, True):
                target = {'type': 'EXECUTABLE', 'sources': [{'path': name, 'isGenerated': generated}],
                          'compileGroups': [{'language': 'CXX'}]}
                with self.subTest(path=name, generated=generated), self.assertRaisesRegex(ValueError, 'classified CI input'):
                    SELECT.validate_input_routes([target], self.root, NATIVE.plan, OWNER.owned_paths(), paths)
        SELECT.validate_input_routes([{'type': 'UTILITY', 'sources': [{'path': name}]}],
                                     self.root, NATIVE.plan, OWNER.owned_paths(), paths)

    def test_owner_code_and_complete_generation_changes_invalidate_old_plan_not_app_closure(self):
        event, sha = self.merge({'browser-client/src/world.ts': b'frontend\n'})
        original = BROWSER.route(event, 'pull_request', self.root, sha, policy_root=self.trusted)
        identity = APP.owner_identity(self.trusted)
        sources = APP.owner_sources(self.trusted)
        self.assertIn('.github/package-workflow-generations.json', sources)
        self.assertIn('tools/sbom/requirements-validation.txt', sources)
        self.assertIn('tools/repository-checks/package_checks.py', sources)
        self.assertIn('tools/sync-test-reuse/gate.py', sources)
        for name in ('.github/package-workflow-generations.json', '.github/browser-native-ownership.json',
                     'tools/repository-checks/workflows/browser-client.yml',
                     'tools/ios-build-qualification/host.py', '.github/ios-host-orchestration.json',
                     'tools/ios-build-qualification/host-workflow.yml'):
            path = self.trusted / name; before = path.read_bytes()
            path.write_bytes(before + b'\n')
            try:
                self.assertNotEqual(APP.owner_identity(self.trusted), identity, name)
            finally: path.write_bytes(before)
        # Actual executing code identity cannot be replaced by a policy mirror.
        mirror = self.directory / 'policy-mirror'
        shutil.copytree(self.trusted, mirror, ignore=shutil.ignore_patterns('__pycache__'))
        path = mirror / 'tools/repository-checks/package_checks.py'
        path.write_bytes(path.read_bytes() + b'\n# policy mirror is not executing code\n')
        self.assertEqual(APP.owner_identity(mirror), identity)
        with tempfile.TemporaryDirectory(prefix='overte-owner-code-') as temporary:
            code = Path(temporary)
            for relative in APP.CODE_INPUTS:
                target = code / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            for relative in ('tests/run-project-tests.py', 'tools/sync-test-reuse/qualification.py'):
                target = code / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            shutil.copytree(ROOT / 'tools/test-evidence', code / 'tools/test-evidence',
                            ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
            with patch.object(APP, 'ROOT', code):
                before = APP.owner_identity(self.trusted)
                (code / 'tools/repository-checks/package_checks.py').write_text(
                    (code / 'tools/repository-checks/package_checks.py').read_text() + '\n# changed trusted validator\n')
                self.assertNotEqual(APP.owner_identity(self.trusted), before)
                current = BROWSER.route(event, 'pull_request', self.root, sha, policy_root=self.trusted)
                self.assertNotEqual(current['plan'], original['plan'])
                with self.assertRaises(ValueError):
                    BROWSER.verify_outer({'result': 'success', 'outputs': {
                        'candidate': sha, 'plan': original['plan'], 'verified': 'true'}},
                        BROWSER.outer_outputs(current), current)
                needs = {'route': {'result': 'success', 'outputs': original},
                         'cpu': {'result': 'skipped'}, 'browser': {'result': 'success'},
                         'native-journey': {'result': 'success'}}
                with self.assertRaises(ValueError):
                    BROWSER.verify(event, 'pull_request', self.root, sha, needs, policy_root=self.trusted)
        self.assertEqual(self.boundary(sha), self.reviewed)

    def test_trusted_ledger_rejects_duplicates_build_paths_and_bad_modes(self):
        for name, mode in (('CMakeLists.txt', '100644'), ('tools/new.cpp', '100644'),
                           ('tools/conanfile.py', '100644'), ('tools/package.json', '100644'),
                           ('interface/resources/README.md', '100644'), ('tools/json.py', '100644'),
                           ('tests/device/new.py', '100644'), ('tools/test-evidence/*.py', '100644'),
                           ('../outside.py', '100644'), ('tools/ok.py', '120000')):
            value = deepcopy(self.ledger); value['ci_paths'][name] = mode
            self.ledger_path.write_text(json.dumps(value))
            with self.subTest(path=name), self.assertRaises(ValueError):
                APP.policy(BROWSER.trusted_bytes, self.trusted)
        self.ledger_path.write_text('{"schema":1,' + json.dumps(self.ledger)[1:])
        with self.assertRaises(ValueError): APP.policy(BROWSER.trusted_bytes, self.trusted)


if __name__ == '__main__':
    unittest.main(verbosity=2)
