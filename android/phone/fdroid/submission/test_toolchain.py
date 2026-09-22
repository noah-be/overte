# SPDX-License-Identifier: Apache-2.0
"""Prevent snapshot pins and incorrect Conan compiler contexts from returning."""
import importlib.util
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('standard_toolchain', HERE / 'toolchain.py')
toolchain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toolchain)


class StandardToolchainTests(unittest.TestCase):
    def setUp(self):
        self.versions = dict(gcc='14.2.0', cmake='3.31.6', ninja='1.12.1',
                             java='21.0.12.1', conan='2.25.2', **{'g++': '14.2.0'})

    def test_standard_packages_and_distro_patch_updates_are_accepted(self):
        toolchain.validate(self.versions)
        self.versions.update(gcc='14.3.0', java='21.0.13', ninja='1.12.2',
                             **{'g++': '14.3.0'})
        toolchain.validate(self.versions)

    def test_wrong_compiler_context_and_incompatible_tools_fail(self):
        for name, value in [('gcc', '15.3.0'), ('g++', '14.1.0'),
                            ('java', '17.0.20'), ('cmake', '3.25.0'),
                            ('cmake', '4.0.0'), ('ninja', '1.11.1'),
                            ('conan', '2.24.0')]:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                toolchain.validate(dict(self.versions, **{name: value}))

    def test_actual_executor_overrides_linux_only_and_preserves_legacy(self):
        source = (HERE.parent / 'scripts/build-dependencies.sh').read_text()
        function = 'conan_install() {' + source.split('conan_install() {', 1)[1].split('\npreflight()', 1)[0]
        for standard, context in [('1', 'linux'), ('1', 'android'), ('0', 'linux')]:
            script = ('conan() { printf "%s\\n" "$@"; }\n' + function +
                      '\nOVERTE_FDROID_STANDARD_TOOLCHAIN=$1\n'
                      'conan_install "$2" recipe.py --no-remote "--build=*"\n')
            args = subprocess.check_output(['sh', '-eu', '-c', script, 'test', standard, context], text=True).splitlines()
            expected = ['install', 'recipe.py', '--no-remote', '--build=*']
            if standard == '1':
                if context == 'linux':
                    expected += ['-s:h', 'compiler.version=14']
                expected += ['-s:b', 'compiler.version=14']
            self.assertEqual(expected, args)


if __name__ == '__main__':
    unittest.main()
