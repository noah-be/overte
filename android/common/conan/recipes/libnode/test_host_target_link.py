"""Original recipe methods; Configure/GYP itself has a separate offline probe."""
import importlib.util
from pathlib import Path
import shlex
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('libnode_recipe', Path(__file__).with_name('conanfile.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
RECIPE = MODULE.LibnodeAndroidConan


class HostTargetLink(unittest.TestCase):
    def test_source_routes_only_android_cross_dependencies_in_late_toolset_phase(self):
        recipe = SimpleNamespace(version='22.22.3', conan_data={'sources': {'22.22.3': {}}})
        with patch.object(MODULE, 'get') as get, patch.object(MODULE, 'replace_in_file') as replace:
            RECIPE.source(recipe)
        get.assert_called_once_with(recipe, strip_root=True)
        changes = [call.args for call in replace.call_args_list if call.args[1] == 'configure.py']
        self.assertEqual(len(changes), 1)
        _, _, old, new = changes[0]
        self.assertEqual(old, '  if getattr(options, shared_lib):\n')
        self.assertIn("options.cross_compiling and flavor == 'android'", new)
        self.assertIn("lib in ('openssl', 'zlib')", new)
        self.assertIn("output.setdefault('target_conditions', [])", new)
        self.assertNotIn("output.setdefault('conditions', [])", new)
        self.assertIn("['_toolset==\"target\"', target_output]", new)
        # Real Python execution of the inserted routing: unrelated/native
        # calls retain their original output; both affected cross libs move.
        for cross, flavor, lib in ((True, 'android', 'openssl'), (True, 'android', 'zlib'),
                                  (False, 'android', 'openssl'), (True, 'linux', 'openssl'),
                                  (True, 'android', 'libuv')):
            original = {'include_dirs': [], 'libraries': []}
            namespace = dict(options=SimpleNamespace(cross_compiling=cross, shared=True), flavor=flavor,
                             lib=lib, shared_lib='shared', output=original)
            exec('if True:\n' + new + "    output['libraries'].append('target-library')\n", namespace)
            routed = cross and flavor == 'android' and lib in ('openssl', 'zlib')
            self.assertEqual(bool(original.get('target_conditions')), routed)
            self.assertEqual(original['libraries'], [] if routed else ['target-library'])
            if routed:
                self.assertEqual(original['target_conditions'][0][1]['libraries'], ['target-library'])

    def test_actual_build_keeps_external_crypto_for_both_architectures(self):
        for arch, cpu in (('armv8', 'arm64'), ('x86_64', 'x64')):
            dependencies = {name: SimpleNamespace(cpp_info=SimpleNamespace(
                libs=libs, system_libs=[], components={}, includedirs=['/target/' + name + '/include'],
                libdirs=['/target/' + name + '/lib'])) for name, libs in
                (('openssl', ['ssl', 'crypto']), ('zlib', ['z']))}
            recipe = SimpleNamespace(settings=SimpleNamespace(arch=arch, build_type='Debug'),
                                     dependencies=dependencies, package_folder='/package', run=Mock())
            recipe._shared_args = MethodType(RECIPE._shared_args, recipe)
            with patch.object(MODULE, 'build_jobs', return_value=3):
                RECIPE.build(recipe)
            configure, make = recipe.run.call_args_list
            args = shlex.split(configure.args[0])
            for required in ('--cross-compiling', '--shared-openssl', '--shared-zlib',
                             '--shared-openssl-libname=ssl,crypto', '--dest-cpu=' + cpu):
                self.assertIn(required, args)
            self.assertNotIn('--openssl-no-asm', args)
            self.assertEqual(configure.kwargs['env'], ['conanbuild', 'node_android_cross'])
            self.assertEqual(make.args[0], 'make -j3 libnode -C out BUILDTYPE=Debug')


if __name__ == '__main__':
    unittest.main()
