"""Finite source-history contracts; only ordinary Python source-test workers."""
import ast
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location('managed_ancestry_cpu_history', HERE / 'managed_ancestry_history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
REPLAY_SHA256 = '10b719060a9b66d3b7328dea403aa11803e46d21788b1bb0b36875f3ef7264d6'


class ManagedAncestryHistory(unittest.TestCase):
    def altered(self, text):
        raw = gzip.compress(text.encode(), mtime=0)
        with patch.object(history, 'ARCHIVE_SHA256', hashlib.sha256(raw).hexdigest()):
            return history.checked_archive(raw)

    def test_all_original84_host_method_bodies_remain_byte_exact(self):
        raw = (HERE / 'fixtures/managed-ancestry-original84-bodies.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'cf9a324b544cd6ef005cbcb52a8829641ecaca7b3ba07e5b881e1eba1ffa77b7')
        record = json.loads(raw, object_pairs_hook=history.unique)
        self.assertEqual(set(record), {'schemaVersion', 'methods'})
        self.assertEqual(record['schemaVersion'], 1)
        self.assertEqual(len(record['methods']), 84)
        for key, pin in record['methods'].items():
            path, name = key.split('::')
            class_name, method_name = name.split('.')
            text = (REPO / path).read_text()
            cls = next(node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name == class_name)
            node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method_name)
            body = ast.get_source_segment(text, node).encode()
            self.assertEqual(len(body), pin['bytes'], key)
            self.assertEqual(hashlib.sha256(body).hexdigest(), pin['sha256'], key)

    def test_all_five_complete_before_sources_recover_only_exact_current(self):
        sources = history.read_archive()
        self.assertEqual(len(sources), 5)
        for path, pin in history.PINS.items():
            current = (REPO / path).read_bytes()
            recovered = history.recover(path, current)
            self.assertEqual(hashlib.sha256(recovered).hexdigest(), pin['before'])
            self.assertEqual(recovered, sources[path]['beforeText'].encode())

    def test_unknown_old_changed_missing_source_bytes_refuse(self):
        for path in history.PINS:
            old = history.read_archive()[path]['beforeText'].encode()
            current = (REPO / path).read_bytes()
            for invalid in (old, current + b'\n# drift\n', b'', None):
                with self.assertRaises(ValueError):
                    history.recover(path, invalid)
        with self.assertRaises(ValueError):
            history.recover('browser-client/lab/unlisted.py', b'anything')

    def test_duplicate_or_missing_archive_member_refuses(self):
        sources = history.read_archive()
        text = json.dumps(dict(schemaVersion=1, sources=sources))
        with self.assertRaises(ValueError):
            self.altered(text.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1', 1))
        sources.pop(next(iter(sources)))
        with self.assertRaises(ValueError):
            self.altered(json.dumps(dict(schemaVersion=1, sources=sources)))

    def test_unknown_archive_field_and_changed_before_source_refuse(self):
        sources = history.read_archive()
        with self.assertRaises(ValueError):
            self.altered(json.dumps(dict(schemaVersion=1, sources=sources, unknown=True)))
        sources[next(iter(sources))]['beforeText'] += '\n# drift\n'
        with self.assertRaises(ValueError):
            self.altered(json.dumps(dict(schemaVersion=1, sources=sources)))

    def test_archive_limits_and_missing_symlink_hardlink_refuse(self):
        for invalid in (b'', b'x' * 131073):
            with self.assertRaises(ValueError):
                history.checked_archive(invalid)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'archive.gz'
            original.write_bytes(history.ARCHIVE.read_bytes())
            alias = root / 'alias.gz'
            alias.symlink_to(original)
            for path in (root / 'missing.gz', alias):
                with patch.object(history, 'ARCHIVE', path), self.assertRaises((OSError, ValueError)):
                    history.read_archive()
            alias.unlink()
            os.link(original, alias)
            with patch.object(history, 'ARCHIVE', original), self.assertRaises(ValueError):
                history.read_archive()

    def test_current_manager_inverts_whole_original84_and_156bc_history(self):
        key = 'browser-client/lab/manage.py'
        current = (REPO / key).read_bytes()
        self.assertEqual(hashlib.sha256(current).hexdigest(), '53cd7fcce5887c993bc724ce3e391c4c7d0975f338ed1c96a1adfdbe7c9bdb95')
        original = history.recover(key, current)
        self.assertEqual(hashlib.sha256(original).hexdigest(), '84b4426187e078515b77984a3581a63130d2dbc0c5edf4230a66a17ecdbf8e66')
        recovery = json.loads((HERE / 'fixtures/managed-seven-manage-recovery.json').read_text())
        old_recovery = json.loads(history.recover('browser-client/lab/atomic-provisioning/fixtures/managed-seven-manage-recovery.json', (HERE / 'fixtures/managed-seven-manage-recovery.json').read_bytes()))
        self.assertEqual(recovery['anchors'][:-1], old_recovery['anchors'])
        self.assertEqual(recovery['beforeSHA256'], old_recovery['beforeSHA256'])
        text = current.decode()
        for row in reversed(recovery['anchors']):
            self.assertEqual(text.count(row['after']), 1)
            text = text.replace(row['after'], row['before'], 1)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), '156bcbd944bf29a94647bcaee75e1ecdc06bcdf94dca388f9a60d7bebdf81ab2')

    def test_old_whole_seven_manager_pin_refuses_current_before_import_or_ports(self):
        import probe
        probe.verify_reviewed_sources(HERE.parent)
        old = history.recover('browser-client/lab/atomic-provisioning/source-pins.json', (HERE / 'source-pins.json').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'repo/browser-client/lab'
            lab = root / 'lab'
            out = root / 'out'
            metadata = root / 'metadata'
            for path in (source, lab, out, metadata):
                path.mkdir(parents=True, mode=0o700)
            for name in probe.SOURCE_DEPENDENCIES:
                (source / name).write_bytes((HERE.parent / name).read_bytes())
            (metadata / 'source-pins.json').write_bytes(old)
            with patch.object(probe, 'HERE', metadata), patch.object(probe, 'free_ports') as ports, patch.object(probe.importlib.util, 'spec_from_file_location') as importing, patch.object(probe.subprocess, 'Popen') as child:
                with self.assertRaisesRegex(ValueError, '^probe-reviewed-source-changed$'):
                    probe.prepare(root / 'repo', lab, out)
                ports.assert_not_called()
                importing.assert_not_called()
                child.assert_not_called()
            self.assertEqual((metadata / 'source-pins.json').read_bytes(), old)

    def test_native_helper_probe_and_runtime_history_exclusion_unchanged(self):
        for path, pin in [('browser-client/lab/native_launch.py', '5358a62e101c2fc8fc94063b6ec617a9a221b93b6778f59fc80cac2171ccc581'), ('browser-client/lab/atomic-provisioning/probe.py', '67d90f5598f05ef50af1098d33854cb64165b315874aa449003119adc03364e1')]:
            data = (REPO / path).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin)
            self.assertNotIn(b'managed_ancestry_history', data)
        self.assertNotIn(b'managed_ancestry_history', (REPO / 'browser-client/lab/manage.py').read_bytes())

    def test_original_seven_whole_metadata_count_bodies_replay_on_original_inputs(self):
        raw = (HERE / 'fixtures/managed-ancestry-replay-inputs.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), REPLAY_SHA256)
        document = json.loads(raw, object_pairs_hook=history.unique)
        self.assertEqual(set(document), {'schemaVersion', 'inputs'})
        self.assertEqual(document['schemaVersion'], 1)
        self.assertEqual(len(document['inputs']), 87)
        self.assertNotIn('browser-client/lab/curate-core-journey.py', document['inputs'])
        with tempfile.TemporaryDirectory(prefix='managed-whole-before-cpu-') as directory:
            root = Path(directory)
            root.chmod(0o700)
            total = 0
            for path, pin in document['inputs'].items():
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn('..', Path(path).parts)
                source = REPO / path
                self.assertEqual(source.resolve(strict=True), source)
                info = source.stat()
                self.assertTrue(stat.S_ISREG(info.st_mode))
                self.assertEqual(info.st_uid, os.getuid())
                self.assertEqual(info.st_nlink, 1)
                self.assertEqual(info.st_mode & 0o022, 0)
                self.assertLessEqual(info.st_size, 262144)
                data = source.read_bytes()
                self.assertEqual(len(data), pin['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), pin['sha256'])
                total += len(data)
                self.assertLessEqual(total, 2097152)
                if path in history.PINS:
                    data = history.recover(path, data)
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    self.assertEqual(os.write(fd, data), len(data))
                finally:
                    os.close(fd)
            self.assertFalse((root / 'browser-client/lab/curate-core-journey.py').exists())
            command = [sys.executable, '-B', str(root / 'browser-client/lab/atomic-provisioning/test_managed_composition.py')]
            result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                                    env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertLessEqual(len(result.stdout) + len(result.stderr), 16384)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b'Ran 7 tests', result.stderr)
            self.assertIn(b'\nOK\n', result.stderr)


    def test_missing_required_replay_manager_is_not_ignored(self):
        original = Path.read_bytes
        required = REPO / 'browser-client/lab/manage.py'
        def read(path):
            if path == required:
                raise FileNotFoundError('required-replay-manager-missing')
            return original(path)
        with patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(FileNotFoundError, '^required-replay-manager-missing$'):
                self.test_original_seven_whole_metadata_count_bodies_replay_on_original_inputs()


if __name__ == '__main__':
    unittest.main(verbosity=2)
