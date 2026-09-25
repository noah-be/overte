# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for actual path and resource-time differences."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('repro_hook', HERE / 'hook_reproducible.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class ReproducibleTests(unittest.TestCase):
    def test_flags_preserve_existing_options_and_record_all_variants(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = []
            conf = SimpleNamespace(append=lambda name, value: records.append((name, value)))
            for variant in ('random-first', 'random-second'):
                recipe = SimpleNamespace(name='qt', ref='qt/5.15.18@overte/stable',
                    source_folder=str(root / variant / 'source'), build_folder=str(root / variant / 'build'),
                    package_folder=str(root / variant / 'package'), conf=conf, dependencies={})
                with patch.dict(os.environ, OVERTE_ATTEMPT_ROOT=td, OVERTE_FDROID_STANDARD_TOOLCHAIN='1'):
                    hook.pre_generate(recipe)
            self.assertEqual(2, len(list((root / 'reproducible-paths').glob('*.json'))))
            self.assertTrue(any(name == 'tools.build:cflags' for name, _ in records))
            self.assertTrue(any(name == 'tools.build:cxxflags' for name, _ in records))
            self.assertTrue(all(flag.startswith('-ffile-prefix-map=') for _, flag in records))

    def test_openssl_does_not_embed_new_random_flags(self):
        with tempfile.TemporaryDirectory() as td:
            recipe = SimpleNamespace(name='openssl', ref='openssl/3.5.8@overte/stable',
                source_folder=td+'/s', build_folder=td+'/b', package_folder=td+'/p', dependencies={})
            # No conf object: this branch must only record mappings, not add flags.
            with patch.dict(os.environ, OVERTE_ATTEMPT_ROOT=td, OVERTE_FDROID_STANDARD_TOOLCHAIN='1'):
                hook.pre_generate(recipe)

    def test_normalization_compiles_and_only_changes_embedded_config_paths(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'tools').mkdir()
            p = root / 'tools/js2c.cc'
            p.write_text('''#include <string>
#include <vector>
#include <iostream>
std::vector<char> JSONify(std::vector<char> code) { return code; }
int main() {
  std::string original="/random/cache/pkg/include unchanged";
  std::vector<char> code(original.begin(), original.end());
  std::vector<char> transformed = JSONify(code);
  std::cout << original << "\\n" << std::string(transformed.begin(), transformed.end());
}
''')
            hook.normalize_node_config(root, [('/random/cache/pkg', '/usr/src/dependency')])
            binary = root / 'probe'
            subprocess.run([compiler, '-std=c++17', str(p), '-o', str(binary)], check=True)
            self.assertEqual('/random/cache/pkg/include unchanged\n/usr/src/dependency/include unchanged',
                             subprocess.check_output([str(binary)], text=True))

    def test_post_generate_keeps_flags_after_ndk_and_qmake_initialization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            feature = root / 'qt5/qtbase/mkspecs/features/default_post.prf'
            feature.parent.mkdir(parents=True)
            feature.write_text('# original feature\n')
            toolchain = root / 'conan_toolchain.cmake'
            toolchain.write_text('# original toolchain\n')
            recipe = SimpleNamespace(name='qt', ref='qt/5.15.18@overte/stable',
                source_folder=td, build_folder=td, package_folder=td+'/package',
                generators_folder=td, dependencies={})
            with patch.dict(os.environ, OVERTE_FDROID_STANDARD_TOOLCHAIN='1'):
                hook.post_generate(recipe)
            self.assertTrue(toolchain.read_text().startswith('# original toolchain'))
            self.assertIn('add_compile_options("-ffile-prefix-map=', toolchain.read_text())
            self.assertTrue(feature.read_text().startswith('# original feature'))
            for variable in ('QMAKE_CFLAGS', 'QMAKE_CXXFLAGS'):
                self.assertIn(variable + ' += -ffile-prefix-map=', feature.read_text())

    def test_changed_node_generator_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'tools').mkdir()
            (root / 'tools/js2c.cc').write_text('unexpected implementation')
            with self.assertRaisesRegex(ValueError, 'Unexpected Node'):
                hook.normalize_node_config(root, [])

    def test_scribe_date_is_compiled_from_epoch_and_preserves_shader_text(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'src').mkdir()
            source = root / 'src/main.cpp'
            original = '''#include <chrono>
#include <ctime>
#include <iostream>
using namespace std;
int main() {
    time_t endTime = chrono::system_clock::to_time_t(chrono::system_clock::now());
    std::cout << "// Generated on " << ctime(&endTime);
    std::cout << "// Copyright preserved\\nvoid main() {}\\n";
}
'''
            outputs = []
            for name in ('first', 'second'):
                source.write_text(original)
                with patch.dict(os.environ, SOURCE_DATE_EPOCH='1790000000'):
                    hook.normalize_scribe_date(root)
                binary = root / name
                subprocess.run([compiler, str(source), '-o', str(binary)], check=True)
                outputs.append(subprocess.check_output([str(binary)], env=dict(os.environ, TZ='UTC')))
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn(b'2026', outputs[0])
            self.assertTrue(outputs[0].endswith(b'// Copyright preserved\nvoid main() {}\n'))
            with patch.dict(os.environ, SOURCE_DATE_EPOCH='invalid'):
                with self.assertRaisesRegex(ValueError, 'Invalid SOURCE_DATE_EPOCH'):
                    hook.normalize_scribe_date(root)
            with patch.dict(os.environ, SOURCE_DATE_EPOCH='1790000000'):
                with self.assertRaisesRegex(ValueError, 'Unexpected Scribe'):
                    hook.normalize_scribe_date(root)

    def test_legacy_executor_does_not_enable_hook(self):
        with patch.dict(os.environ, OVERTE_FDROID_STANDARD_TOOLCHAIN='0'):
            hook.pre_generate(None)


if __name__ == '__main__':
    unittest.main()
