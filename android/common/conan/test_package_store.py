#!/usr/bin/env python3
"""Real offline Conan build/transport/restore/install and altered-input rejection."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('package_store', Path(__file__).with_name('package-store.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='overte-conan-transport-')
        cls.root = Path(cls.temporary.name)
        cls.attempt = cls.root / 'original'
        cls.home = cls.attempt / 'conan'
        cls.source = cls.root / 'recipe'
        cls.source.mkdir()
        cls.env = os.environ | {'CONAN_HOME': str(cls.home)}
        cls.profile = cls.root / 'profile'
        compiler = subprocess.check_output(['c++', '-dumpversion'], text=True).strip().split('.')[0]
        cls.profile.write_text('[settings]\nos=Linux\narch=x86_64\ncompiler=gcc\ncompiler.version=' + compiler
                               + '\ncompiler.libcxx=libstdc++11\ncompiler.cppstd=gnu17\nbuild_type=Release\n')
        (cls.source / 'value.cpp').write_text('extern "C" int storefixture_value() { return 42; }\n')
        (cls.source / 'conanfile.py').write_text('''from conan import ConanFile
from conan.tools.files import copy
import os
import shlex
class Fixture(ConanFile):
    name = 'storefixture'
    version = '1.0'
    license = 'MIT'
    package_type = 'static-library'
    settings = 'os', 'arch', 'compiler', 'build_type'
    exports_sources = 'value.cpp'
    def build(self):
        self.run('c++ -std=gnu++17 -c ' + shlex.quote(os.path.join(self.source_folder, 'value.cpp')) + ' -o value.o')
        self.run('ar rcs libstorefixture.a value.o')
    def package(self):
        copy(self, 'libstorefixture.a', self.build_folder, os.path.join(self.package_folder, 'lib'))
    def package_info(self):
        self.cpp_info.libs = ['storefixture']
''')
        cls.run_cli('remote', 'remove', '*')
        # Conan 2.25.2 predates the local GCC16 preset. Record the actual test
        # compiler in this private fixture cache instead of calling it GCC15.
        cls.settings_extension = 'compiler:\n  gcc:\n    version: ["' + compiler + '"]\n'
        (cls.home / 'settings_user.yml').write_text(cls.settings_extension)
        graph = json.loads(cls.run_cli('create', str(cls.source), '-pr:a', str(cls.profile),
                                      '--no-remote', '--build=*', '--format=json'))
        cls.graph = graph
        cls.node = next(n for n in graph['graph']['nodes'].values() if (n.get('ref') or '').startswith('storefixture/'))
        cls.key = list(module.identity(cls.node))
        export = Path(cls.run_cli('cache', 'path', cls.node['ref']).strip())
        cls.recipes = cls.root / 'recipes'
        destination = cls.recipes / 'storefixture/1.0'
        shutil.copytree(export, destination / 'export')
        shutil.copytree(export.parent / 'es', destination / 'export_sources')
        files = {p.relative_to(destination).as_posix(): module.digest(p)
                 for p in destination.rglob('*') if p.is_file()}
        cls.index = {'schema_version': 1, 'recipes': {'storefixture/1.0': {
            'rrev': cls.node['rrev'], 'cache_folder': export.parent.name, 'files': files}}}
        cls.evidence = cls.root / 'evidence'
        cls.evidence.mkdir()
        for name in ('host.json', 'target.json'):
            (cls.evidence / name).write_text(json.dumps(graph))
        (cls.evidence / 'index.json').write_text(json.dumps(cls.index))
        cls.binding = {'contract': 'overte-pico-qualified-inputs-v2', 'attemptRoot': str(cls.attempt),
                       'recipeIndex': 'index.json', 'phases': {'host-tools': {'actualGraph': 'host.json'},
                       'target': {'actualGraph': 'target.json'}},
                       'files': {p.name: module.digest(p) for p in cls.evidence.iterdir()}}
        payload = Path(cls.node['package_folder'])
        cls.payload_relative = payload.relative_to(cls.attempt)
        for path in payload.rglob('*'):
            if path.is_file():
                cls.binding['files'][path.relative_to(cls.attempt).as_posix()] = module.digest(path)

    @classmethod
    def run_cli(cls, *args, env=None):
        result = subprocess.run([sys.executable, '-m', 'conans.conan', *args],
                                env=env or cls.env, text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return result.stdout

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.payload = self.case / 'payload'
        self.package = self.payload / self.payload_relative
        shutil.copytree(Path(self.node['package_folder']), self.package)
        self.evidence = self.case / 'evidence'
        shutil.copytree(type(self).evidence, self.evidence)
        self.recipes = self.case / 'recipes'
        shutil.copytree(type(self).recipes, self.recipes)
        self.binding = copy.deepcopy(type(self).binding)
        self.binding_file = self.case / 'binding.json'
        self.selection_file = self.case / 'selection.json'
        self.selection = {'contract': 'overte-conan-package-import-selection-v1', 'packages': [self.key]}

    def store(self):
        self.binding_file.write_text(json.dumps(self.binding))
        binding_sha = module.digest(self.binding_file)
        self.selection['bindingSha256'] = binding_sha
        self.selection_file.write_text(json.dumps(self.selection))
        return module.PackageStore(self.binding_file, binding_sha, self.evidence, [self.payload], self.recipes)

    def validate(self):
        store = self.store()
        store.validate(self.selection_file, module.digest(self.selection_file))
        return store

    def test_actual_conan_restore_install_and_link(self):
        store = self.validate()
        cache = self.case / 'restored'
        receipt = self.case / 'receipt.json'
        result = store.restore(cache, self.case / 'transport.tgz', receipt)
        self.assertEqual(result['status'], 'TRANSPORT_RESTORE_COMPLETE')
        self.assertEqual(result['packages'], [self.key])
        self.assertEqual(result['missingPackages'], [])
        self.assertIn('NOT_DEPENDENCY_PRODUCTION', result['qualification'])
        env = os.environ | {'CONAN_HOME': str(cache)}
        (cache / 'settings_user.yml').write_text(self.settings_extension)
        graph = json.loads(self.run_cli('install', '--requires=' + self.key[0], '-pr:a', str(self.profile),
                         '--no-remote', '--build=never', '--format=json', '-of', str(self.case / 'consumer'), env=env))
        node = next(n for n in graph['graph']['nodes'].values() if (n.get('ref') or '').startswith('storefixture/'))
        self.assertEqual(list(module.identity(node)), self.key)
        self.assertEqual(node['binary'], 'Cache')
        program = self.case / 'consumer.cpp'
        program.write_text('extern "C" int storefixture_value(); int main() { return storefixture_value() == 42 ? 0 : 1; }\n')
        executable = self.case / 'consumer-bin'
        subprocess.run(['c++', str(program), str(Path(node['package_folder']) / 'lib/libstorefixture.a'),
                        '-o', str(executable)], check=True, timeout=30)
        subprocess.run([str(executable)], check=True, timeout=10)
        self.assertEqual(module.digest(Path(self.node['package_folder']) / 'lib/libstorefixture.a'),
                         module.digest(self.package / 'lib/libstorefixture.a'))
        self.assertTrue(all(p['exitCode'] == 0 for p in result['operations']))

    def test_current_python_conan_used_when_path_cli_is_unusable(self):
        # An explicit virtualenv Python does not put its console scripts on
        # PATH. A different global CLI must not replace its pinned Conan.
        canary = self.case / 'unusable-cli'
        canary.mkdir()
        command = canary / 'conan'
        command.write_text('#!/bin/sh\nexit 97\n')
        command.chmod(0o755)
        path = str(canary) + os.pathsep + os.environ.get('PATH', '')
        with mock.patch.dict(os.environ, {'PATH': path}):
            self.assertEqual(subprocess.run(['conan', '--version']).returncode, 97)
            self.test_actual_conan_restore_install_and_link()

    def test_manifest_content_and_missing_file_rejected(self):
        library = self.package / 'lib/libstorefixture.a'
        original = library.read_bytes()
        library.write_bytes(original + b'altered')
        with self.assertRaisesRegex(module.StoreError, 'manifest content'):
            self.validate()
        library.unlink()
        with self.assertRaisesRegex(module.StoreError, 'manifest file set'):
            self.validate()

    def test_foreign_unmanifested_file_rejected(self):
        (self.package / 'lib/foreign-library.a').write_bytes(b'foreign package payload')
        with self.assertRaisesRegex(module.StoreError, 'manifest file set'):
            self.validate()

    def test_prev_and_package_id_rejected(self):
        path = self.package / 'conanmanifest.txt'
        original = path.read_text()
        path.write_text(original.replace('conaninfo.txt: ', 'conaninfo.txt: 0', 1))
        with self.assertRaises(module.StoreError):
            self.validate()
        path.write_text(original)
        (self.package / 'conaninfo.txt').write_text('different identity\n')
        with self.assertRaisesRegex(module.StoreError, 'package-ID'):
            self.validate()

    def test_valid_manifest_hash_changes_original_prev(self):
        from conan.internal.model.manifest import FileTreeManifest
        library = self.package / 'lib/libstorefixture.a'
        library.write_bytes(library.read_bytes() + b'changed')
        FileTreeManifest.create(str(self.package)).save(str(self.package))
        with self.assertRaisesRegex(module.StoreError, 'PREV mismatch'):
            self.validate()

    def test_valid_but_foreign_prev_and_package_id_rejected(self):
        self.selection['packages'] = [[self.key[0], self.key[1], 'a' * 32]]
        with self.assertRaisesRegex(module.StoreError, 'foreign'):
            self.validate()
        self.selection['packages'] = [[self.key[0], 'b' * 40, self.key[2]]]
        with self.assertRaisesRegex(module.StoreError, 'foreign'):
            self.validate()

    def test_manifest_traversal_rejected(self):
        path = self.package / 'conanmanifest.txt'
        path.write_text(path.read_text() + '../escape: ' + 'a' * 32 + '\n')
        with self.assertRaisesRegex(module.StoreError, 'path escape'):
            self.validate()

    def test_symlink_escape_rejected(self):
        library = self.package / 'lib/libstorefixture.a'
        outside = self.case / 'outside'
        outside.write_bytes(library.read_bytes())
        library.unlink(); library.symlink_to(outside)
        with self.assertRaisesRegex(module.StoreError, 'symlink escape'):
            self.validate()

    def test_duplicate_selection_and_changed_binding_rejected(self):
        self.selection['packages'] = [self.key, self.key]
        with self.assertRaisesRegex(module.StoreError, 'duplicate selection'):
            self.validate()
        self.selection['packages'] = [self.key]
        (self.evidence / 'target.json').write_text('{}')
        with self.assertRaisesRegex(module.StoreError, 'evidence SHA256'):
            self.store()

    def test_recipe_and_original_sha_ledger_rejected(self):
        recipe = self.recipes / 'storefixture/1.0/export/conanfile.py'
        original = recipe.read_text()
        recipe.write_text(original + '\n# altered\n')
        with self.assertRaisesRegex(module.StoreError, 'payload SHA256'):
            self.validate()
        recipe.write_text(original)
        name = (self.payload_relative / 'lib/libstorefixture.a').as_posix()
        self.binding['files'][name] = '0' * 64
        with self.assertRaisesRegex(module.StoreError, 'payload SHA256'):
            self.validate()

    def test_late_payload_replacement_and_existing_cache_rejected(self):
        store = self.validate()
        (self.package / 'lib/libstorefixture.a').write_bytes(b'late change')
        with self.assertRaisesRegex(module.StoreError, 'changed during transport'):
            store.restore(self.case / 'late-cache', self.case / 'late.tgz', self.case / 'late.json')
        cache = self.case / 'existing'; cache.mkdir()
        with self.assertRaisesRegex(module.StoreError, 'new private'):
            store.restore(cache, self.case / 'other.tgz', self.case / 'other.json')

    def test_duplicate_manifest_and_output_path_rejected(self):
        path = self.package / 'conanmanifest.txt'
        original = path.read_text()
        path.write_text(original + original.splitlines()[1] + '\n')
        with self.assertRaisesRegex(module.StoreError, 'duplicate manifest'):
            self.validate()
        path.write_text(original)
        store = self.validate()
        with self.assertRaisesRegex(module.StoreError, 'absolute canonical'):
            store.restore(Path('relative-cache'), self.case / 'archive.tgz', self.case / 'receipt.json')

    def test_transport_budget_and_new_special_file_rejected(self):
        maximum = module.MAX_BYTES
        try:
            module.MAX_BYTES = 1
            with self.assertRaisesRegex(module.StoreError, 'byte limit'):
                self.validate()
        finally:
            module.MAX_BYTES = maximum
        os.mkfifo(self.package / 'unexpected-fifo')
        with self.assertRaisesRegex(module.StoreError, 'special payload file'):
            self.validate()

    def test_finalized_output_and_graph_path_escape_rejected(self):
        for ph in ('host.json', 'target.json'):
            graph = json.loads((self.evidence / ph).read_text())
            node = next(n for n in graph['graph']['nodes'].values() if (n.get('ref') or '').startswith('storefixture/'))
            node['package_folder'] = str(Path(node['package_folder']).with_name('f'))
            (self.evidence / ph).write_text(json.dumps(graph))
            self.binding['files'][ph] = module.digest(self.evidence / ph)
        store = self.store()
        self.assertEqual(store.available()['missingPackages'], [self.key])
        with self.assertRaisesRegex(module.StoreError, 'immutable package missing'):
            store.validate(self.selection_file, module.digest(self.selection_file))
        for ph in ('host.json', 'target.json'):
            graph = json.loads((self.evidence / ph).read_text())
            node = next(n for n in graph['graph']['nodes'].values() if (n.get('ref') or '').startswith('storefixture/'))
            node['package_folder'] = str(self.attempt) + '/conan/p/../../escape'
            (self.evidence / ph).write_text(json.dumps(graph))
            self.binding['files'][ph] = module.digest(self.evidence / ph)
        with self.assertRaisesRegex(module.StoreError, 'path escape'):
            self.store()


if __name__ == '__main__':
    unittest.main()
