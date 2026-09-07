"""Execute the real Pico adapter with explicit synthetic SH009/package inputs.

ELF headers are fixtures, not runnable tools or native artifact evidence.
No Conan, Gradle, compiler, network, SDK or device operation is performed.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

PICO = Path(__file__).resolve().parents[1]
ROOT = PICO.parents[2]
SPEC = importlib.util.spec_from_file_location('pico_inputs', PICO / 'release/pico-source-inputs.py')
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)
SOURCE = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def write(self, relative, value):
        file = self.root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value if isinstance(value, bytes) else value.encode())
        return file

    def __init__(self, root, host_qt_version=None):
        self.root = root
        self.packages = {}
        self.graphs = {}
        closure_nodes = {}
        for phase, names in [('target', ['qt', 'openssl', 'draco', 'openxr']),
                             ('host-tools', ['qt', 'scribe', 'glslang', 'spirv-cross', 'spirv-tools'])]:
            nodes = {'0': {'id': '0', 'dependencies': {}}}
            for i, name in enumerate(names, 1):
                reference = name + '/' + ('3.5.8' if name == 'openssl' else '5.15.18-2026.01.04' if name == 'qt' else '1.0') + '@overte/stable'
                if name == 'qt' and phase == 'host-tools' and host_qt_version:
                    reference = 'qt/' + host_qt_version + '@overte/stable'
                folder = root / 'packages' / phase / name
                folder.mkdir(parents=True)
                self.packages[phase, name] = folder
                settings = {'os': 'Android', 'arch': 'armv8', 'build_type': 'Debug', 'os.api_level': '26'} if phase == 'target' else {'os': 'Linux', 'arch': 'x86_64'}
                nodes[str(i)] = dict(id=str(i), ref=reference + '#' + 'd'*32, rrev='d'*32,
                    package_id='e'*40, prev='f'*32, context='host', binary='Build', remote=None,
                    binary_remote=None, settings=settings, options={'shared': True}, license='MIT',
                    dependencies={}, package_folder=str(folder))
                nodes['0']['dependencies'][str(i)] = {'ref': reference}
                if reference not in closure_nodes:
                    recipe_path = 'recipes/' + name + '/conanfile.py'
                    closure_nodes[reference] = dict(reference=reference, recipe_revision='d'*32,
                        classification='source-bearing', contexts=[],
                        recipe={'path': recipe_path, 'sha256': '1'*64, 'exported_files': {recipe_path: '1'*64}},
                        sources=[{'id': name, 'sha256': '2'*64, 'canonical_url': 'https://fixture.invalid/source.tar.gz',
                                  'license': {'path': 'LICENSE', 'sha256': '3'*64, 'spdx': 'MIT'}}])
                closure_nodes[reference]['contexts'].append({'graph': phase})
            self.graphs[phase] = {'graph': {'nodes': nodes}}
        self.write('index.json', '{}')
        self.write('closure.json', json.dumps({'schema_version': 1, 'node_count': len(closure_nodes),
            'recipe_export_index': {'sha256': sha(root / 'index.json')}, 'nodes': list(closure_nodes.values())}))
        self.spec = dict(contract='overte-pico-source-inputs-v1', sourceRevision=SOURCE,
            sourceClosure='closure.json', recipeIndex='index.json', generators='generators',
            qtSourceDirectory='qt-source', qtRuntimePatchSha256=sha(ROOT / 'android/common/conan/patches/qt-pico-android-runtime.patch'), phases={})
        for phase in self.graphs: self.graph(phase)
        qt = self.packages['target', 'qt']
        self.write('generators/conandeps_legacy.cmake', '# synthetic CMakeDeps\n')
        self.write('generators/Qt5-debug-armv8-data.cmake', 'set(qt_PACKAGE_FOLDER_DEBUG "' + str(qt) + '")\n')
        for module in ADAPTER.QML_MODULES: self.write(str((qt / 'qml' / module / 'qmldir').relative_to(root)), 'module fixture\n')
        self.write(str((qt / 'jar/QtAndroid.jar').relative_to(root)), b'fixture jar')
        self.elf(qt / 'lib/libQt5Core_arm64-v8a.so', 183)
        resources = PICO / 'apps/picoInterface/src/main/res/values/qt_dependencies.xml'
        for item in ADAPTER.ET.parse(resources).findall("./string-array[@name='bundled_in_lib']/item"):
            name, destination = item.text.split(':')
            # Explicit fixture layout follows the production extraction map.
            folder = 'lib' if name.startswith('libQt5') else str(Path(destination).parent)
            self.elf(qt / folder / name, 183)
        ssl = self.packages['target', 'openssl']
        for name in ('crypto', 'ssl'):
            self.elf(ssl / ('lib/lib' + name + '_3.so'), 183)
            (ssl / ('lib/lib' + name + '.so')).symlink_to('lib' + name + '_3.so')
        draco = self.packages['target', 'draco']
        self.write(str((draco / 'lib/libdraco.a').relative_to(root)), b'!<arch>\n')
        self.write(str((draco / 'include/draco/compression/decode.h').relative_to(root)), '// fixture\n')
        for name in ('moc', 'rcc', 'uic', 'qmake'): self.elf(self.packages['host-tools', 'qt'] / 'bin' / name, 62, True)
        for name, relative in ADAPTER.SHADER_TOOLS.items(): self.elf(self.packages['host-tools', name] / relative, 62, True)
        # Reconstruct only the postimage contexts needed by git apply --reverse
        # --check. These files intentionally are NOT a Qt source distribution.
        file = None
        lines = []
        cursor = None
        for line in (ROOT / 'android/common/conan/patches/qt-pico-android-runtime.patch').read_text().splitlines():
            if line.startswith('diff --git'):
                if file: self.write('qt-source/' + file, '\n'.join(lines) + '\n')
                file, lines, cursor = None, [], None
            elif line.startswith('+++ b/'):
                file = line[6:]
            elif line.startswith('@@'):
                cursor = int(re.search(r'\+(\d+)', line)[1]) - 1
                while len(lines) < cursor: lines.append('// synthetic padding')
            elif cursor is not None and not line.startswith('-'):
                lines.append(line[1:] if line.startswith((' ', '+')) else line)
                cursor += 1
        if file: self.write('qt-source/' + file, '\n'.join(lines) + '\n')
        self.seal()

    def elf(self, path, machine, executable=False):
        header = bytearray(20)
        header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, machine)
        self.write(str(path.relative_to(self.root)), bytes(header))
        if executable: path.chmod(0o755)

    def graph(self, phase, update_expected=True):
        self.write(phase + '.json', json.dumps(self.graphs[phase]))
        if update_expected:
            expected = copy.deepcopy(self.graphs[phase])
            for node in list(expected['graph']['nodes'].values())[1:]: node['prev'] = None
            self.write(phase + '-expected.json', json.dumps(expected))
        checkpoint = dict(attempt_root=str(self.root), name=phase, source_commit=SOURCE,
            manifest_sha256=sha(self.root / 'closure.json'), recipe_index_sha256=sha(self.root / 'index.json'),
            result_sha256=sha(self.root / (phase + '.json')), jobs='1')
        self.write(phase + '.COMPLETE', ''.join(k + '=' + v + '\n' for k, v in checkpoint.items()))
        self.spec['phases'][phase] = dict(actualGraph=phase + '.json', expectedGraph=phase + '-expected.json', checkpoint=phase + '.COMPLETE')

    def seal(self):
        self.spec['files'] = {p.relative_to(self.root).as_posix(): sha(p) for p in self.root.rglob('*')
                              if p.is_file() and p.name != 'inputs.json'}
        self.binding = self.write('inputs.json', json.dumps(self.spec))
        self.digest = sha(self.binding)

    def resolve(self):
        return ADAPTER.resolve(str(self.root), self.binding, self.digest, SOURCE)

    def env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('PICO_')}
        env.update(PICO_SOURCE_GRAPH_ROOT=str(self.root), PICO_SOURCE_INPUTS=str(self.binding),
                   PICO_SOURCE_INPUTS_SHA256=self.digest, PICO_EXPECTED_SOURCE_SHA=SOURCE)
        return env


class SourceInputs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.f = Fixture(Path(self.temporary.name))

    def test_canonical_providers_and_host_selection_preserve_prevs(self):
        result = self.f.resolve()
        self.assertTrue({'libssl_3.so', 'libcrypto_3.so', 'libQt5Core_arm64-v8a.so'} <= set(result['runtime']))
        self.assertIn('/host-tools/qt/bin/rcc', result['tools']['rcc'])
        self.assertNotIn('libQt5Core_arm64-v8a.so', result['stagedRuntime'])
        self.assertIn('libplugins_platforms_qtforandroid_arm64-v8a.so', result['stagedRuntime'])
        self.assertEqual(result['provenance']['target']['packages'][0]['prev'], 'f'*32)
        self.assertIn('No graph equivalence', result['acceptance'])

    def test_named_conan_consumer_is_not_a_runtime_package(self):
        self.f.graphs['target']['graph']['nodes']['0'].update(
            ref='OverteAndroidSourceTarget/None', context='host',
            settings={'os':'Android','arch':'armv8'}, package_folder=None)
        self.f.graph('target'); self.f.seal()
        self.assertIn('libssl_3.so', self.f.resolve()['runtime'])

    def test_actual_shell_entrypoints_consume_without_legacy_staging(self):
        for command in ([str(PICO / 'build.sh'), 'deps', '--source-graph'],
                        [str(PICO / 'build.sh'), 'prepare'], [str(PICO / 'prepare-deps.sh')]):
            process = subprocess.run(command, env=self.f.env(), capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)['bindingSha256'], self.f.digest)

    def test_missing_inputs_and_foreign_adapter_fail_before_external_work(self):
        env = self.f.env(); del env['PICO_SOURCE_INPUTS']
        for args in (['deps', '--source-graph'], ['prepare'], ['build']):
            process = subprocess.run([str(PICO / 'build.sh')] + args, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertIn('PICO_SOURCE_INPUTS_REJECTED', process.stderr)
        env = self.f.env(); env['PICO_SHARED_GRAPH_ADAPTER'] = '/bin/true'
        process = subprocess.run([str(PICO / 'build.sh'), 'deps', '--source-graph'], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 2)

    def test_stale_manifest_and_mutated_payload_are_rejected(self):
        self.f.binding.write_text(self.f.binding.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'PICO_BINDING_HASH'): self.f.resolve()
        self.f.seal()
        (self.f.packages['target', 'openssl'] / 'lib/libssl_3.so').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'PICO_PAYLOAD_HASH'): self.f.resolve()

    def test_graph_revision_mismatch_and_cached_binary_are_rejected(self):
        node = self.f.graphs['target']['graph']['nodes']['2']
        node['package_id'] = 'b'*40
        self.f.graph('target', update_expected=False); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'CONAN_PINNED_PACKAGE_MISMATCH'): self.f.resolve()
        node['binary'] = 'Cache'
        self.f.graph('target'); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'CONAN_BINARY_OR_REMOTE'): self.f.resolve()

    def test_legacy_provider_wrong_arch_and_missing_patch_are_rejected(self):
        ssl = self.f.packages['target', 'openssl']
        bad = ssl / 'lib/libssl_1_1.so'
        self.f.elf(bad, 183); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'PICO_LEGACY_PROVIDER'): self.f.resolve()
        bad.unlink(); self.f.elf(ssl / 'lib/libssl_3.so', 62); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'PICO_ELF_ARCH'): self.f.resolve()
        self.f.elf(ssl / 'lib/libssl_3.so', 183)
        source = next((self.f.root / 'qt-source').rglob('qtimezoneprivate_android.cpp'))
        source.write_text('// missing runtime fix\n'); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'PICO_QT_RUNTIME_PATCH_MISSING'): self.f.resolve()

    def test_external_symlink_and_unbound_generator_are_rejected(self):
        qt = self.f.packages['target', 'qt']
        (qt / 'escape').symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError, 'PICO_PATH_ESCAPE'): self.f.resolve()
        (qt / 'escape').unlink()
        self.f.write('generators/foreign.cmake', '# not pinned\n')
        with self.assertRaisesRegex(ValueError, 'PICO_PAYLOAD_HASH'): self.f.resolve()

    def test_missing_declared_qt_plugin_is_rejected_even_with_fresh_hashes(self):
        plugin = next(self.f.packages['target', 'qt'].rglob('libplugins_platforms_qtforandroid_arm64-v8a.so'))
        plugin.unlink(); self.f.seal()
        with self.assertRaisesRegex(ValueError, 'PICO_QT_RUNTIME_BINDING'): self.f.resolve()

    def test_independently_valid_host_graph_cannot_supply_other_qt_version(self):
        other = self.f.root / 'other-attempt'; other.mkdir()
        fixture = Fixture(other, host_qt_version='6.8.0')
        with self.assertRaisesRegex(ValueError, 'PICO_QT_HOST_RECIPE_MISMATCH'): fixture.resolve()

    def test_actual_groovy_consumer_positive_and_negative(self):
        # Explicit host-tool input; never discover or run a Gradle installation.
        classpath = os.environ.get('PICO_TEST_GROOVY_CLASSPATH')
        if not classpath: self.skipTest('PICO_TEST_GROOVY_CLASSPATH not supplied')
        script = self.f.root / 'consumer.groovy'
        script.write_text('''def root = new File(args[0])
def loader = new GroovyClassLoader()
loader.parseClass('class GradleException extends RuntimeException { GradleException(String text) { super(text) } }')
// Parse the unchanged production Gradle DSL without running Gradle/AGP.
loader.parseClass(new File(root, 'apps/picoInterface/build.gradle'))
def load = new GroovyShell().evaluate(new File(root, 'release/source-inputs.groovy'))
println groovy.json.JsonOutput.toJson(load(root))
''')
        command = ['java', '-cp', classpath, 'groovy.ui.GroovyMain', str(script), str(PICO)]
        result = subprocess.run(command, env=self.f.env(), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['bindingSha256'], self.f.digest)
        env = self.f.env(); env['PICO_SOURCE_INPUTS_SHA256'] = '0'*64
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PICO_SOURCE_INPUTS_REJECTED', result.stderr)

    def test_cmake_host_tools_all_configurations_and_missing_input(self):
        # LANGUAGES NONE: executes owned CMake bindings without native compiler,
        # Android configuration, dependency discovery or a build invocation.
        source = self.f.root / 'cmake-test'
        source.mkdir()
        tool = self.f.packages['host-tools', 'qt'] / 'bin/moc'
        (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.20)
project(PicoHostBinding LANGUAGES NONE)
add_custom_target(consumer)
foreach(tool moc rcc uic qmake)
  add_executable(Qt5::${tool} IMPORTED GLOBAL)
  string(TOUPPER "${tool}" upper)
  set(PICO_QT_${upper} "${BOUND_TOOL}")
endforeach()
include("''' + str(PICO / 'cmake/pico-qt-host-tools.cmake') + '''")
pico_bind_qt_host_tools(consumer)
foreach(tool moc rcc uic qmake)
  foreach(config IMPORTED_LOCATION IMPORTED_LOCATION_DEBUG IMPORTED_LOCATION_RELEASE IMPORTED_LOCATION_RELWITHDEBINFO)
    get_target_property(actual Qt5::${tool} ${config})
    if(NOT actual STREQUAL BOUND_TOOL)
      message(FATAL_ERROR "host tool configuration mismatch")
    endif()
  endforeach()
endforeach()
get_target_property(actual consumer AUTOMOC_EXECUTABLE)
if(NOT actual STREQUAL BOUND_TOOL)
  message(FATAL_ERROR "consumer uses target moc")
endif()
''')
        command = ['cmake', '-S', str(source), '-B', str(source / 'out'), '-DBOUND_TOOL=' + str(tool)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        tool.unlink()
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('Missing bound Pico Qt5 host tool', process.stderr)

    def test_shared_bootstrap_receives_distinct_host_shader_directories(self):
        script = self.f.root / 'bootstrap.cmake'
        text = 'set(CMAKE_BINARY_DIR "' + str(self.f.root / 'cmake-output') + '")\n'
        text += 'set(HIFI_ANDROID_HOST_TOOLS "' + str(self.f.packages['host-tools', 'qt'] / 'bin') + '")\n'
        mapping = {'SCRIBE': 'scribe', 'GLSLANG': 'glslang', 'SPIRV_CROSS': 'spirv-cross', 'SPIRV_TOOLS': 'spirv-tools'}
        for key, name in mapping.items():
            path = self.f.packages['host-tools', name] / ADAPTER.SHADER_TOOLS[name]
            text += 'set(PICO_' + key + ' "' + str(path) + '")\n'
        text += 'include("' + str(PICO / 'cmake/pico-source-bootstrap.cmake') + '")\n'
        text += 'include("${CMAKE_BINARY_DIR}/cmake/ConanToolsDirs.cmake")\n'
        for key, name in mapping.items():
            folder = (self.f.packages['host-tools', name] / ADAPTER.SHADER_TOOLS[name]).parent
            text += 'if(NOT ${' + key + '_DIR} STREQUAL "' + str(folder) + '")\nmessage(FATAL_ERROR "shader path mismatch")\nendif()\n'
        script.write_text(text)
        env = self.f.env(); env.pop('OVERTE_FDROID_CONAN_DIR', None)
        process = subprocess.run(['cmake', '-P', str(script)], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        env['OVERTE_FDROID_CONAN_DIR'] = '/foreign'
        process = subprocess.run(['cmake', '-P', str(script)], env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('explicit host/target inputs', process.stderr)

    def test_actual_java_initializer_loads_canonical_pair_before_openxr(self):
        activity = (PICO / 'apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivity.java').read_text()
        initializer = activity.split('    static {', 1)[1].split('\n    }', 1)[0]
        source = self.f.root / 'LoadOrder.java'
        source.write_text('''public class LoadOrder {
  static String loaded = "";
  static String missing = "";
  static class System {
    static void loadLibrary(String name) {
      if (name.equals(missing)) throw new UnsatisfiedLinkError();
      loaded += name + ",";
    }
  }
  static void initialize() {''' + initializer + '''
  }
  public static void main(String[] args) {
    initialize();
    if (!loaded.equals("crypto_3,ssl_3,picoOpenXR,")) throw new AssertionError(loaded);
    loaded = ""; missing = "ssl_3";
    try { initialize(); throw new AssertionError("missing provider accepted"); }
    catch (UnsatisfiedLinkError expected) {
      if (!loaded.equals("crypto_3,")) throw new AssertionError(loaded);
    }
  }
}
''')
        subprocess.run(['javac', '-d', str(self.f.root), str(source)], check=True, timeout=15)
        subprocess.run(['java', '-cp', str(self.f.root), 'LoadOrder'], check=True, timeout=5)


if __name__ == '__main__': unittest.main()
