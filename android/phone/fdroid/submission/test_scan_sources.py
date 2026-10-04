# SPDX-License-Identifier: Apache-2.0
"""Exercise source-scan visibility and refusal to restore rejected inputs."""
import importlib.util
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
    def fixture(self, root):
        archive = root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as out:
            info = tarfile.TarInfo('library/source.c')
            content = b'int main(void) { return 0; }\n'
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
