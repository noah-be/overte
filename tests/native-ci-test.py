#!/usr/bin/env python3
"""Behavioral regressions for native routing, CMake dependency selection, and gates."""
import copy
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POLICY = load('native_policy', 'tools/native-tests/check.py')
SELECT = load('native_select', 'tools/native-tests/select.py')
GATE = load('native_gate', 'tools/repository-checks/check.py')
SHADERS = load('native_shaders', 'tools/native-tests/shader-cache.py')


class RoutingTests(unittest.TestCase):
    def test_host_changes_do_not_start_native_builds(self):
        for path in ('README.md', 'docs/developer.md', 'tools/native-tests/README.md', 'scripts/system/main.js',
                     'tests/device/run_control_plane_tests.py', 'tests/project-health-test.py',
                     'tools/sync-test-reuse/test.py', 'server-console/src/main.js',
                     '.github/ISSUE_TEMPLATE/bug.yml', 'interface/resources/qml/Main.qml',
                     'interface/resources/images/example.png'):
            with self.subTest(path=path):
                self.assertEqual(POLICY.plan([path])['mode'], 'skip')

    def test_core_test_edit_uses_bounded_core_lane(self):
        for path in ('tests/shared/src/AABoxTests.cpp', 'tools/native-tests/check.py', 'tools/native-tests/run.py'):
            self.assertEqual(POLICY.plan([path])['mode'], 'core')

    def test_production_dependency_and_unknown_changes_are_conservative(self):
        for path in ('libraries/shared/src/AABox.cpp', 'libraries/shared/src/AABox.h',
                     'libraries/new/src/new.cpp', 'interface/src/Application.cpp', 'unknown.data',
                     'conanfile.py', 'cmake/macros/TargetGlm.cmake', 'tests/shared/CMakeLists.txt',
                     'docs/CMakeLists.txt', 'scripts/resources.qrc', 'interface/resources/resources.qrc',
                     'interface/resources/new.cpp', '.github/native-tests.json',
                     'tools/native-tests/configure.sh', '.github/workflows/native-tests.yml'):
            with self.subTest(path=path):
                self.assertEqual(POLICY.plan([path])['mode'], 'full')

    def test_empty_nonregular_and_mixed_changes_never_skip(self):
        for paths, regular in (([], True), (['README.md'], False),
                               (['README.md', 'libraries/shared/src/AABox.cpp'], True)):
            self.assertEqual(POLICY.plan(paths, regular)['mode'], 'full')
        nonregular = POLICY.plan(['libraries/base/value.cpp'], regular=False)
        self.assertTrue(nonregular['force_broad'])
        mixed = POLICY.plan(['README.md', 'libraries/base/value.cpp'])
        self.assertEqual(mixed['paths'], ['libraries/base/value.cpp'])
        self.assertFalse(mixed['force_broad'])

    def test_only_verified_empty_delta_skips_native_work(self):
        self.assertEqual(POLICY.plan([], False, verified_empty=True)['mode'], 'skip')
        self.assertEqual(POLICY.plan([], False)['mode'], 'full')
        with self.assertRaises(ValueError):
            POLICY.plan(['source.cpp'], verified_empty=True)

    def test_malformed_paths_fail(self):
        for path in ('', '../secret', '/absolute', 'a\x00b', 'a\\b'):
            with self.assertRaises(ValueError):
                POLICY.plan([path])

    def test_required_repository_gate_rejects_native_failures_and_skips(self):
        for mode in ('full', 'documentation', 'delegated-sync'):
            for native in ('skip', 'core', 'full'):
                needs = {'route': {'result': 'success', 'outputs': {'mode': mode, 'security': 'false', 'native': native}},
                         'project': {'result': 'success' if mode == 'full' else 'skipped'},
                         'documentation': {'result': 'success'}, 'workflow-security': {'result': 'skipped'},
                         'native': {'result': 'skipped' if native == 'skip' else 'success'}}
                self.assertEqual(GATE.verify(needs)['status'], 'PASS')
                for bad in ('failure', 'cancelled', 'timed_out', 'missing',
                            'success' if native == 'skip' else 'skipped'):
                    changed = copy.deepcopy(needs)
                    changed['native']['result'] = bad
                    with self.assertRaises(ValueError):
                        GATE.verify(changed)
                del needs['route']['outputs']['native']
                with self.assertRaises(ValueError):
                    GATE.verify(needs)

    def test_bootstrap_compatibility_cannot_bypass_activated_gate(self):
        legacy = {'route': {'result': 'success', 'outputs': {'mode': 'full', 'security': 'true'}},
                  'project': {'result': 'success'}, 'documentation': {'result': 'success'},
                  'workflow-security': {'result': 'success'}}
        self.assertEqual(GATE.verify(legacy, require_native=False)['status'], 'PASS')
        with self.assertRaises(ValueError):
            GATE.verify(legacy, require_native=True)

    def test_manifest_has_real_test_sources_and_explicit_exclusions(self):
        config = json.loads((ROOT / '.github/native-tests.json').read_text())
        self.assertEqual(config['schema'], 1)
        for name, methods in config['tests'].items():
            group, cls = name.rsplit('-', 1)
            source = ROOT / 'tests' / group / 'src' / (cls + '.cpp')
            self.assertTrue(source.is_file(), name)
            self.assertIsInstance(methods, list)
            for method in methods:
                self.assertIn('::' + method + '(', source.read_text())
            if methods:
                implemented = set(re.findall(r'void ' + re.escape(cls) + r'::(\w+)\(', source.read_text()))
                implemented -= {'initTestCase', 'cleanupTestCase'}
                self.assertEqual(set(methods) | set(config['method_exclusions'][name]), implemented,
                                 'New methods must not disappear behind an old explicit Qt method list')
        candidates = set()
        for cmake in (ROOT / 'tests').glob('*/CMakeLists.txt'):
            if not any('setup_hifi_testcase(' in line.lower() and not line.lstrip().startswith('#')
                       for line in cmake.read_text().splitlines()):
                continue
            for source in (cmake.parent / 'src').glob('*.cpp'):
                if source.stem.endswith(('Test', 'Tests')):
                    candidates.add(cmake.parent.name + '-' + source.stem)
        covered = set(config['tests'])
        covered.update(name for name in candidates if any(name == excluded or name.startswith(excluded + '-') for excluded in config['excluded']))
        self.assertEqual(candidates, covered, 'Every native executable needs an explicit CI disposition')


class WorkflowCostTests(unittest.TestCase):
    def test_native_jobs_are_selected_once_and_cache_hits_do_not_skip_tests(self):
        workflow = (ROOT / '.github/workflows/native-tests.yml').read_text()
        caller = (ROOT / '.github/workflows/repository-checks.yml').read_text()
        self.assertIn('  workflow_call:', workflow)
        self.assertNotRegex(workflow, r'(?m)^  (push|pull_request|pull_request_target):')
        if json.loads((ROOT / '.github/repository-checks.json').read_text()).get('native_required', False):
            self.assertIn("if: needs.route.outputs.native != 'skip'", caller)
            self.assertIn('workflow-security, native]', caller)
        self.assertIn('timeout-minutes: 45', workflow)
        self.assertIn('timeout-minutes: 10', workflow)
        self.assertNotIn('--build=missing', workflow)
        self.assertIn('--build=never', workflow)
        run_step = workflow.split('      - name: Build and run selected native tests', 1)[1].split('      - name:', 1)[0]
        self.assertNotIn('if:', run_step)
        self.assertIn('trusted/tools/native-tests/run.py', run_step)
        self.assertIn('cancel-in-progress: true', caller)
        triggers = caller.split('  pull_request:', 1)[1].split('  workflow_dispatch:', 1)[0]
        self.assertNotIn('ready_for_review', triggers)
        self.assertIn('synchronize', triggers)
        self.assertIn('edited', triggers)  # Retargeting must validate the new merge candidate.

    def test_baseline_preparation_is_explicit_and_caches_match_prs(self):
        source = (ROOT / '.github/workflows/native-dependencies.yml').read_text()
        ordinary = (ROOT / '.github/workflows/native-tests.yml').read_text()
        self.assertIn('  workflow_dispatch:', source)
        self.assertIn('repository: noah-be/overte', source)
        self.assertIn('ref: ${{ inputs.candidate_sha || github.sha }}', source)
        self.assertIn('--sha "$BASELINE_SHA"', source)
        self.assertNotRegex(source, r'(?m)^  (push|pull_request|schedule):')
        self.assertIn("if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", source)
        self.assertIn('--build=missing', source)
        self.assertIn("conan cache clean '*' --source --build --download --temp", source)
        cache_key = "native-deps-babe51f7c369-v1-${{ hashFiles('conanfile.py', 'tools/conan-profiles/linux', 'tools/native-tests/conan-linux.lock') }}"
        self.assertIn(cache_key, source)
        self.assertIn(cache_key, ordinary)
        for workflow in (source, ordinary):
            self.assertEqual(workflow.count('conan install .'),
                             workflow.count('--lockfile=tools/native-tests/conan-linux.lock'))
        self.assertIn('native-ccache-babe51f7c369-v1-full-', source)
        self.assertIn('native-ccache-babe51f7c369-v1-${{ inputs.mode }}-', ordinary)
        self.assertIn('tools/native-tests/run.py', source)
        image = re.search(r'image: (.+@sha256:([0-9a-f]{64}))', ordinary)
        self.assertIsNotNone(image)
        self.assertIn(image.group(1), source)
        for workflow in (source, ordinary):
            self.assertIn('native-deps-' + image.group(2)[:12] + '-v1-', workflow)
            self.assertIn('native-ccache-' + image.group(2)[:12] + '-v1-', workflow)

    def test_package_publishing_requires_successful_manual_qualification(self):
        workflow = (ROOT / '.github/workflows/native-dependencies.yml').read_text()
        prepare, publish = workflow.split('  publish:', 1)
        self.assertNotIn('packages: write', prepare)
        self.assertIn('needs: prepare', publish)
        self.assertNotIn('always()', publish.split('    steps:', 1)[0])
        self.assertIn("github.repository == 'noah-be/overte'", publish)
        self.assertIn("github.event.repository.default_branch", publish)
        self.assertIn('ref: ${{ github.sha }}', publish)
        self.assertIn('ghcr.io/noah-be/overte/native-dependencies:', publish)
        self.assertIn("metadata['source_sha'] == os.environ['BASELINE_SHA']", publish)
        self.assertIn("metadata['run_id'] == os.environ['GITHUB_RUN_ID']", publish)
        self.assertIn("== metadata['archive_sha256']", publish)
        self.assertIn("conan cache save '*#*:*#*' --no-source", prepare)
        dockerfile = (ROOT / 'tools/native-tests/package-image.Dockerfile').read_text()
        self.assertIn('org.opencontainers.image.source="https://github.com/noah-be/overte"', dockerfile)
        self.assertIn('conan cache restore /native-packages/conan-packages.tgz', dockerfile)
        self.assertNotIn('COPY . ', dockerfile)

    def test_cache_actions_use_the_existing_repository_allowlist(self):
        for name in ('native-tests.yml', 'native-dependencies.yml'):
            source = (ROOT / '.github/workflows' / name).read_text()
            self.assertNotIn('uses: actions/cache@', source)
            for action, sha in re.findall(r'uses: (actions/cache(?:/[^@\s]+)?)@([0-9a-f]+)', source):
                self.assertIn(action, ('actions/cache/restore', 'actions/cache/save'))
                self.assertEqual(sha, 'caa296126883cff596d87d8935842f9db880ef25')
            for title in ('Save successful compiler cache', 'Save successful shader outputs'):
                step = source.split('      - name: ' + title, 1)[1].split('      - name:', 1)[0]
                self.assertIn('if: success()', step)
                self.assertIn('cache-primary-key', step)

    def test_linux_dependency_lock_freezes_recipe_revisions(self):
        lock = json.loads((ROOT / 'tools/native-tests/conan-linux.lock').read_text())
        self.assertEqual(lock['version'], '0.5')
        self.assertTrue(lock['requires'])
        self.assertTrue(lock['build_requires'])
        for section in ('requires', 'build_requires', 'python_requires'):
            for reference in lock[section]:
                self.assertRegex(reference, r'^[^\s]+#[0-9a-f]{32}%[0-9.]+$')



class GitInventoryTests(unittest.TestCase):
    def test_actual_merge_inventory_covers_deletion_rename_and_more_than_300_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()
            git('init', '-q', '-b', 'base')
            git('config', 'user.email', 'native-test@example.invalid')
            git('config', 'user.name', 'Native fixture')
            (root / 'libraries/shared/src').mkdir(parents=True)
            (root / 'libraries/shared/src/old.cpp').write_text('old')
            (root / 'libraries/shared/src/deleted.cpp').write_text('deleted')
            git('add', '.')
            git('commit', '-qm', 'Base fixture')
            base = git('rev-parse', 'HEAD')
            git('switch', '-qc', 'candidate')
            (root / 'libraries/shared/src/old.cpp').rename(root / 'renamed.md')
            (root / 'libraries/shared/src/deleted.cpp').unlink()
            for index in range(305):
                (root / f'doc-{index}.md').write_text('doc')
            (root / 'newline\nname.md').write_text('line')
            (root / 'scripts').mkdir()
            script = root / 'scripts/host.sh'
            script.write_text('#!/bin/sh\nexit 0\n')
            script.chmod(0o755)
            git('add', '-A')
            git('commit', '-qm', 'Candidate fixture')
            head = git('rev-parse', 'HEAD')
            git('switch', '-q', 'base')
            git('merge', '--no-ff', '-m', 'Merge fixture', head)
            merge = git('rev-parse', 'HEAD')
            event = {'pull_request': {'base': {'sha': base}, 'head': {'sha': head}}}
            paths, regular = POLICY.candidate_changes(root, event, merge)
            self.assertGreater(len(paths), 300)
            self.assertTrue(regular, 'Regular executable host scripts must not force native builds')
            self.assertFalse(GATE.changed_paths(root, event, merge)[1],
                             'The stricter documentation-only policy must stay unchanged')
            self.assertIn('libraries/shared/src/old.cpp', paths)
            self.assertIn('libraries/shared/src/deleted.cpp', paths)
            self.assertIn('renamed.md', paths)
            self.assertIn('newline\nname.md', paths)
            self.assertEqual(POLICY.plan(paths, regular)['mode'], 'full')
            git('sparse-checkout', 'set', '--cone', '.github')
            self.assertFalse(script.exists())
            self.assertEqual(POLICY.candidate_changes(root, event, merge), (paths, regular),
                             'Sparse routing checkout must preserve the complete Git tree diff')
            with self.assertRaises(ValueError):
                POLICY.candidate_changes(root, event, head)
            event['pull_request']['base']['sha'] = head
            with self.assertRaises(ValueError):
                POLICY.candidate_changes(root, event, merge)
            # An ancestry-only merge has an exact, verified empty tree delta.
            base = merge
            git('switch', '-qc', 'empty-candidate')
            git('commit', '--allow-empty', '-qm', 'Empty candidate fixture')
            head = git('rev-parse', 'HEAD')
            git('switch', '-q', 'base')
            git('merge', '--no-ff', '-m', 'Empty merge fixture', head)
            merge = git('rev-parse', 'HEAD')
            event = {'pull_request': {'base': {'sha': base}, 'head': {'sha': head}}}
            paths, regular = POLICY.candidate_changes(root, event, merge)
            self.assertEqual(paths, [])
            self.assertEqual(POLICY.plan(paths, regular, verified_empty=True)['mode'], 'skip')


class CMakeGraphTests(unittest.TestCase):
    def test_new_compiled_sources_cannot_hide_in_host_only_paths(self):
        source = Path('/fixture')
        targets = [{'type': 'STATIC_LIBRARY', 'sources': [{'path': 'scripts/embedded.cpp'}]}]
        with self.assertRaises(ValueError):
            SELECT.validate_input_routes(targets, source, POLICY.plan)
        targets[0]['sources'][0]['path'] = 'libraries/shared/src/value.cpp'
        SELECT.validate_input_routes(targets, source, POLICY.plan)

    def test_real_graph_limits_builds_and_tracks_include_only_consumers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, build = root / 'src', root / 'build'
            source.mkdir()
            query = build / '.cmake/api/v1/query'
            query.mkdir(parents=True)
            (query / 'codemodel-v2').touch()
            for name in ('base', 'middle', 'unrelated'):
                directory = source / 'libraries' / name
                directory.mkdir(parents=True)
                (directory / 'value.cpp').write_text(f'int {name}() {{ return 0; }}\n')
                (directory / 'CMakeLists.txt').write_text(f'add_library({name} STATIC value.cpp)\n')
            (source / 'main.cpp').write_text('int main() { return 0; }\n')
            (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.24)
project(NativeGraph LANGUAGES CXX)
add_subdirectory(libraries/base)
add_subdirectory(libraries/middle)
add_subdirectory(libraries/unrelated)
target_link_libraries(middle PRIVATE base)
add_executable(dependent main.cpp)
target_link_libraries(dependent PRIVATE middle)
add_executable(header_only main.cpp)
target_include_directories(header_only PRIVATE "${CMAKE_SOURCE_DIR}/libraries/base")
add_executable(unrelated_test main.cpp)
target_link_libraries(unrelated_test PRIVATE unrelated)
''')
            subprocess.run(['cmake', '-S', str(source), '-B', str(build)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            reply = build / '.cmake/api/v1/reply'
            index = json.loads(next(reply.glob('index-*.json')).read_text())
            model = json.loads((reply / index['reply']['codemodel-v2']['jsonFile']).read_text())
            targets = [json.loads((reply / entry['jsonFile']).read_text()) for entry in model['configurations'][0]['targets']]
            tests = {'dependent', 'header_only', 'unrelated_test'}
            result = SELECT.select(targets, tests, ['libraries/base/value.cpp'], source)
            self.assertEqual(set(result['tests']), {'dependent-test', 'header_only-test'})
            self.assertEqual(set(result['targets']), {'base', 'middle', 'dependent', 'header_only'})
            for changed in ('cmake/build.cmake', 'libraries/removed/file.cpp'):
                result = SELECT.select(targets, tests, [changed], source)
                self.assertEqual(set(result['tests']), {name + '-test' for name in tests})
                self.assertTrue(result['broad'])
            mixed = SELECT.select(targets, tests,
                                  ['libraries/base/value.cpp', 'libraries/removed/file.cpp'], source)
            self.assertTrue(mixed['broad'])
            self.assertEqual(set(mixed['tests']), {name + '-test' for name in tests})
            forced = SELECT.select(targets, tests, ['libraries/base/value.cpp'], source,
                                   broad=POLICY.plan(['libraries/base/value.cpp'], regular=False)['force_broad'])
            self.assertEqual(set(forced['tests']), {name + '-test' for name in tests})
            with self.assertRaises(ValueError):
                SELECT.select(targets, {'missing'}, [], source)


class NativeRunnerTests(unittest.TestCase):
    def test_real_build_test_and_timeout_failures_never_leave_success_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, build = root / 'source', root / 'build'
            source.mkdir()
            cmake = source / 'CMakeLists.txt'
            cmake.write_text('cmake_minimum_required(VERSION 3.24)\nproject(Fixture LANGUAGES CXX)\n'
                             'enable_testing()\nadd_executable(shared-Fixture main.cpp)\n'
                             'add_test(NAME shared-Fixture-test COMMAND shared-Fixture)\n')
            main = source / 'main.cpp'
            main.write_text('int main() { return 0; }\n')
            def configure():
                subprocess.run(['cmake', '-S', str(source), '-B', str(build)], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            configure()
            selection = root / 'selection.json'
            selection.write_text(json.dumps({'targets': ['shared-Fixture'], 'tests': ['shared-Fixture-test'],
                                             'sha': '1' * 40}))
            def run():
                return subprocess.run([sys.executable, str(ROOT / 'tools/native-tests/run.py'), '--build', str(build),
                                       '--selection', str(selection)], capture_output=True, text=True, timeout=30)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((build / 'native-result.json').read_text())['status'], 'PASS')
            main.write_text('intentional compile failure\n')
            self.assertNotEqual(run().returncode, 0)
            self.assertFalse((build / 'native-result.json').exists())
            self.assertFalse((build / 'native-ctest.xml').exists())
            main.write_text('int main() { return 1; }\n')
            self.assertNotEqual(run().returncode, 0)
            self.assertFalse((build / 'native-result.json').exists())
            main.write_text('int main() { return 0; }\n')
            text = cmake.read_text().replace('COMMAND shared-Fixture)',
                'COMMAND "' + sys.executable + '" "-c" "import time; time.sleep(10)")')
            cmake.write_text(text + 'set_tests_properties(shared-Fixture-test PROPERTIES TIMEOUT 0.1)\n')
            configure()
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Timeout', result.stdout)
            self.assertFalse((build / 'native-result.json').exists())
            cmake.write_text('cmake_minimum_required(VERSION 3.24)\nproject(Empty NONE)\nenable_testing()\n')
            configure()
            self.assertNotEqual(run().returncode, 0)
            self.assertFalse((build / 'native-result.json').exists())


class QtResultTests(unittest.TestCase):
    def test_wrapper_rejects_empty_skipped_and_failed_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / 'test.py'
            fake.write_text('''import os, pathlib, sys
report = pathlib.Path(sys.argv[sys.argv.index('-o') + 1].split(',')[0])
assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'
assert os.environ['XDG_CONFIG_HOME'] != os.environ.get('HOME')
report.write_text(os.environ['FIXTURE_XML'])
sys.exit(int(os.environ.get('FIXTURE_EXIT', '0')))
''')
            cases = [('<TestCase><TestFunction name="check"><Incident type="pass"/></TestFunction></TestCase>', 0, True),
                     ('<TestCase><TestFunction name="initTestCase"><Incident type="pass"/></TestFunction></TestCase>', 0, False),
                     ('<TestCase><TestFunction name="check"><Incident type="skip"/></TestFunction></TestCase>', 0, False),
                     ('<TestCase><TestFunction name="check"><Incident type="fail"/></TestFunction></TestCase>', 0, False),
                     ('<TestCase/>', 0, False), ('bad xml', 0, False),
                     ('<TestCase><TestFunction name="check"><Incident type="pass"/></TestFunction></TestCase>', 1, False)]
            for xml, exit_code, success in cases:
                result = subprocess.run([sys.executable, str(ROOT / 'tools/native-tests/qt-test.py'), '--report',
                                         str(root / 'result.xml'), '--', sys.executable, str(fake)],
                                        env=dict(os.environ, FIXTURE_XML=xml, FIXTURE_EXIT=str(exit_code)),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode == 0, success, result.stderr)


class ShaderCacheTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'cmake').mkdir()
        (root / 'libraries/shaders').mkdir(parents=True)
        (root / 'libraries/shaders/shadergen.txt').write_text('450;mono;source;output\n')
        (root / 'shadergen.py').write_text('generator')
        (root / 'input.slh').write_text('shader input')
        (root / 'unrelated.cpp').write_text('unrelated')
        definitions = []
        for variable, binary in (('GLSLANG_DIR', 'glslangValidator'), ('SCRIBE_DIR', 'scribe'),
                                 ('SPIRV_CROSS_DIR', 'spirv-cross'), ('SPIRV_TOOLS_DIR', 'spirv-opt')):
            directory = root / variable
            directory.mkdir()
            (directory / binary).write_text('tool binary')
            definitions.append(f'set({variable} "{directory}")')
        (root / 'cmake/ConanToolsDirs.cmake').write_text('\n'.join(definitions))
        (root / 'build.ninja').write_text('''rule generate
  command = shader-compiler --dialect 450
build shadergen: generate input.slh shadergen.py
build product: phony shadergen
build unrelated: phony unrelated.cpp
''')

    def test_actual_ninja_inputs_commands_tools_and_selection_bind_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            key = SHADERS.cache_key(root, ['product'])
            self.assertRegex(key, r'^[0-9a-f]{64}$')
            self.assertEqual(SHADERS.cache_key(root, ['unrelated']), '')
            (root / 'input.slh').touch()
            self.assertEqual(key, SHADERS.cache_key(root), 'Checkout timestamps are not source identity')
            for relative in ('input.slh', 'shadergen.py', 'build.ninja', 'SCRIBE_DIR/scribe',
                             'libraries/shaders/shadergen.txt'):
                path = root / relative
                original = path.read_bytes()
                path.write_bytes(original.replace(b'450', b'410') if relative == 'build.ninja' else original + b'changed')
                self.assertNotEqual(key, SHADERS.cache_key(root), relative)
                path.write_bytes(original)
            (root / 'input.slh').unlink()
            with self.assertRaises(ValueError):
                SHADERS.cache_key(root)

    def test_refresh_changes_only_generated_output_times_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = root / 'libraries/shaders/shaders'
            outputs.mkdir(parents=True)
            generated, source = outputs / 'generated.spv', root / 'source.slh'
            generated.write_bytes(b'compiled artifact')
            source.write_text('source')
            for path in (generated, source):
                os.utime(path, (100, 100))
            SHADERS.refresh(root)
            self.assertGreater(generated.stat().st_mtime, 100)
            self.assertEqual(generated.read_bytes(), b'compiled artifact')
            self.assertEqual(source.stat().st_mtime, 100)
            os.utime(generated, (100, 100))
            (outputs / 'escape').symlink_to(source)
            with self.assertRaises(ValueError):
                SHADERS.refresh(root)
            self.assertEqual(generated.stat().st_mtime, 100)
            self.assertEqual(source.stat().st_mtime, 100)

    def test_workflows_share_exact_shader_keys_without_skipping_test_execution(self):
        for filename in ('native-tests.yml', 'native-dependencies.yml'):
            source = (ROOT / '.github/workflows' / filename).read_text()
            self.assertIn('native-shaders-babe51f7c369-v1-${{ steps.shader-key.outputs.key }}', source)
            block = source.split('key: native-shaders-', 1)[1].split('      - name:', 1)[0]
            self.assertNotIn('restore-keys:', block)
            self.assertIn("steps.shaders.outputs.cache-hit == 'true'", source)
            self.assertIn('--selection build/native-selection.json --output', source)
            self.assertIn('shader-cache.py refresh --build build/native', source)
            self.assertIn("QT_RCC_SOURCE_DATE_OVERRIDE: '1'", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
