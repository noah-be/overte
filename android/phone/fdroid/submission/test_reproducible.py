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

    def test_changed_node_generator_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'tools').mkdir()
            (root / 'tools/js2c.cc').write_text('unexpected implementation')
            with self.assertRaisesRegex(ValueError, 'Unexpected Node'):
                hook.normalize_node_config(root, [])

    def test_legacy_executor_does_not_enable_hook(self):
        with patch.dict(os.environ, OVERTE_FDROID_STANDARD_TOOLCHAIN='0'):
            hook.pre_generate(None)


if __name__ == '__main__':
    unittest.main()
