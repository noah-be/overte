# SPDX-License-Identifier: Apache-2.0
"""Exercise source-scan visibility and refusal to restore rejected inputs."""
import importlib.util
import glob
import io
import json
from pathlib import Path
import socket
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('submission_build', HERE / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
scan = builder.scan_sources


class ScannerInputTests(unittest.TestCase):
    def test_compiler_cleanup_removes_only_exact_content_bound_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / 'extra-source-prefix/tests/platform.exe'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'fixture binary')
            source = binary.with_suffix('.cpp')
            source.write_text('int library() { return 1; }')
            rule = {'reference': 'library/1', 'compiler_suffix': 'tests/platform.exe',
                    'sha256': scan.digest(binary)}
            policy = {'remove': [rule]}
            self.assertEqual(0, scan.clean_compiler_sources(root, 'different/1', policy))
            self.assertTrue(binary.exists())
            self.assertEqual(1, scan.clean_compiler_sources(root, 'library/1', policy))
            self.assertFalse(binary.exists())
            self.assertTrue(source.exists())
            self.assertEqual(0, scan.clean_compiler_sources(root, 'library/1', policy))

    def test_cleanup_refuses_changed_files_before_removing_anything(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            binary = root / 'fixture.bin'
            binary.write_bytes(b'original')
            policy = {'remove': [{'reference': 'library/1',
                                  'compiler_suffix': 'fixture.bin', 'sha256': scan.digest(binary)}]}
            binary.write_bytes(b'different')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                scan.clean_compiler_sources(root, 'library/1', policy)
            self.assertEqual(b'different', binary.read_bytes())

    def test_cleanup_rejects_symlink_targets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'outside').write_bytes(b'original')
            (root / 'fixture.bin').symlink_to(root / 'outside')
            policy = {'remove': [{'reference': 'library/1',
                                  'compiler_suffix': 'fixture.bin', 'sha256': scan.digest(root / 'outside')}]}
            with self.assertRaisesRegex(ValueError, 'input changed'):
                scan.clean_compiler_sources(root, 'library/1', policy)
            self.assertTrue((root / 'outside').exists())

    def test_scandelete_globs_cover_the_content_bound_policy(self):
        policy = scan.load_policy(HERE / 'source-scan-policy.json',
                                  HERE.parent / 'manifests/source-closure.lock.json')
        template = (HERE / 'metadata/io.github.noah_be.overte.phone.yml.in').read_text()
        self.assertNotIn('    scanignore:', template)
        patterns = [line.strip()[2:] for line in template.splitlines()
                    if line.strip().startswith('- fdroid-source-closure/')]
        self.assertLess(len(patterns), len(policy['scandelete']))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            expected = set()
            for rule in policy['scandelete']:
                self.assertIn(Path(rule['archive_path']).name,
                              ['package.json', 'Cargo.toml', 'QtLoader.java'])
                path = root / 'fdroid-source-closure' / rule['archive_sha256'] / rule['archive_path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                expected.add(str(path))
            # F-Droid's getpaths_map uses non-recursive glob.glob, not a
            # recursive ** matcher. Exercise those semantics for nested npm.
            matches = set()
            for pattern in patterns:
                found = glob.glob(str(root / pattern))
                self.assertTrue(found, pattern)
                self.assertTrue(all(Path(p).is_file() for p in found))
                matches.update(found)
            self.assertEqual(expected, matches)

    def fixture(self, root):
        archive = root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as out:
            info = tarfile.TarInfo('library/source.c')
            content = b'int main(void) { return 0; }\n'
            info.size = len(content)
            out.addfile(info, io.BytesIO(content))
            info = tarfile.TarInfo('library/examples/package.json')
            content = b'{"name":"unused-example"}\n'
            info.size = len(content)
            out.addfile(info, io.BytesIO(content))
        sha = scan.digest(archive)
        object_dir = root / 'store' / sha
        object_dir.mkdir(parents=True)
        archive.rename(object_dir / 'source')
        doc = {'nodes': [{'sources': [{'sha256': sha, 'store_path': sha}]}]}
        checkout = root / 'checkout'
        checkout.mkdir()
        view = checkout / 'fdroid-source-closure'
        return doc, root / 'store', checkout, view, sha

    def deletion_fixture(self, root):
        document, store, checkout, view, sha = self.fixture(root)
        rule = {'reference': 'library/1', 'archive_sha256': sha,
                'archive_path': 'library/examples/package.json',
                'compiler_suffix': 'examples/package.json',
                'sha256': scan.hashlib.sha256(b'{"name":"unused-example"}\n').hexdigest()}
        policy = {'remove': [], 'scandelete': [rule]}
        inventory_sha = scan.expand(document, store, view, checkout, policy)
        return store, view, sha, inventory_sha, policy

    def test_declared_scanner_deletion_is_required_and_then_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            store, view, sha, inventory_sha, policy = self.deletion_fixture(Path(td))
            with self.assertRaisesRegex(ValueError, 'scandelete files still present'):
                scan.verify(store, view, inventory_sha)
            (view / sha / 'library/examples/package.json').unlink()
            scan.verify(store, view, inventory_sha)
            self.assertTrue((view / sha / 'library/source.c').exists())

    def test_approved_deletion_does_not_allow_other_source_changes(self):
        for change in ('delete', 'modify', 'add', 'symlink', 'restore'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as td:
                store, view, sha, inventory_sha, policy = self.deletion_fixture(Path(td))
                manifest = view / sha / 'library/examples/package.json'
                manifest.unlink()
                source = view / sha / 'library/source.c'
                if change == 'delete':
                    source.unlink()
                elif change == 'modify':
                    source.write_text('changed')
                elif change == 'add':
                    source.with_name('injected.c').write_text('unexpected')
                elif change == 'symlink':
                    source.unlink()
                    source.symlink_to('examples')
                else:
                    manifest.write_text('restored')
                with self.assertRaisesRegex(ValueError, 'expanded source changed'):
                    scan.verify(store, view, inventory_sha)

    def test_compiler_cannot_restore_the_declared_scandelete_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, view, sha, inventory_sha, policy = self.deletion_fixture(root)
            (view / sha / 'library/examples/package.json').unlink()
            scan.verify(store, view, inventory_sha)
            compiler = root / 'compiler'
            scan.unpack(store / sha / 'source', compiler)
            self.assertEqual(1, scan.clean_compiler_sources(compiler, 'library/1', policy))
            self.assertFalse((compiler / 'library/examples/package.json').exists())
            self.assertEqual(scan.inventory(view / sha), scan.inventory(compiler))

    def test_changed_manifest_is_rejected_before_any_compiler_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, view, sha, inventory_sha, policy = self.deletion_fixture(root)
            compiler = root / 'compiler'
            scan.unpack(store / sha / 'source', compiler)
            manifest = compiler / 'library/examples/package.json'
            manifest.write_text('changed dependency declaration')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                scan.clean_compiler_sources(compiler, 'library/1', policy)
            self.assertTrue(manifest.exists())

    def test_scandelete_authorization_cannot_be_added_to_inventory_after_scan(self):
        with tempfile.TemporaryDirectory() as td:
            store, view, sha, inventory_sha, policy = self.deletion_fixture(Path(td))
            record_path = view / 'inventory.json'
            record = json.loads(record_path.read_text())
            record['scandelete'].append(sha + '/library/source.c')
            record_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'inventory missing or changed'):
                scan.verify(store, view, inventory_sha)

    def test_complete_view_matches_locked_archive_and_rejects_scanner_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            document, store, root, view, sha = self.fixture(Path(td))
            manifest = scan.expand(document, store, view, root)
            scan.verify(store, view, manifest)
            (view / sha / 'library/source.c').unlink()
            with self.assertRaisesRegex(ValueError, 'scanner-deleted'):
                scan.verify(store, view, manifest)

    def test_archive_cannot_be_swapped_after_scan(self):
        with tempfile.TemporaryDirectory() as td:
            document, store, root, view, sha = self.fixture(Path(td))
            manifest = scan.expand(document, store, view, root)
            (store / sha / 'source').write_bytes(b'replacement')
            with self.assertRaisesRegex(ValueError, 'archive changed'):
                scan.verify(store, view, manifest)

    def test_inventory_cannot_be_rewritten_to_approve_different_sources(self):
        with tempfile.TemporaryDirectory() as td:
            document, store, root, view, sha = self.fixture(Path(td))
            manifest = scan.expand(document, store, view, root)
            (view / 'inventory.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'inventory missing or changed'):
                scan.verify(store, view, manifest)

    def test_expansion_outside_scanned_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            document, store, root, view, sha = self.fixture(Path(td))
            with self.assertRaisesRegex(ValueError, 'inside the scanned checkout'):
                scan.expand(document, store, root.parent / 'outside', root)

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with zipfile.ZipFile(root / 'bad.zip', 'w') as out:
                out.writestr('../escape.c', 'bad')
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                scan.unpack(root / 'bad.zip', root / 'expanded')
            self.assertFalse((root / 'escape.c').exists())

    def test_tar_link_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with tarfile.open(root / 'bad.tar', 'w') as out:
                info = tarfile.TarInfo('link')
                info.type = tarfile.SYMTYPE
                info.linkname = '../../outside'
                out.addfile(info)
            with self.assertRaises(tarfile.FilterError):
                scan.unpack(root / 'bad.tar', root / 'expanded')

    def test_build_only_never_acquires_when_prebuild_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            args = ['build.py', '--build-only', '--commit', 'a' * 40,
                    '--version-code', '4', '--version-name', '0.1.3',
                    '--sdk', '/sdk', '--work-dir', str(Path(td) / 'missing')]
            with patch('sys.argv', args), patch.object(builder, 'preflight'), \
                    patch.object(builder, 'acquire') as acquire, \
                    patch.object(builder.urllib.request, 'urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'will not download'):
                    builder.main()
                acquire.assert_not_called()
                network.assert_not_called()

    def test_acquisition_does_not_enter_compilation(self):
        with tempfile.TemporaryDirectory() as td:
            args = ['build.py', '--acquire-only', '--commit', 'a' * 40,
                    '--version-code', '4', '--version-name', '0.1.3',
                    '--sdk', '/sdk', '--work-dir', str(Path(td) / 'new')]
            with patch('sys.argv', args), patch.object(builder, 'preflight'), \
                    patch.object(builder, 'acquire') as acquire, \
                    patch.object(builder, 'release_command') as compile_command:
                builder.main()
                acquire.assert_called_once()
                compile_command.assert_not_called()

    def test_existing_isolated_runner_does_not_require_nested_user_namespace(self):
        with patch.object(socket, 'if_nameindex', return_value=[(1, 'lo')]):
            self.assertEqual([], builder.isolation_prefix())
        with patch.object(socket, 'if_nameindex', return_value=[(1, 'lo'), (2, 'eth0')]):
            self.assertEqual('unshare', builder.isolation_prefix()[0])


if __name__ == '__main__':
    unittest.main()
