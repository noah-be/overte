# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from preflight_diagnostics import retain_failed_preflight
from read_private_preflight import project_retained


class RetainedPrefix(unittest.TestCase):
    def make(self, root, stderr):
        root.chmod(0o700)
        result = retain_failed_preflight(str(root), b'', stderr)
        self.assertEqual(result['status'], 'retained-private')
        capture = next(root.iterdir())
        return capture, capture / 'stderr-prefix.private.log'

    def test_actual_original_retention_read_fixed_setpriv_category_without_raw_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture, _ = self.make(root, b'setpriv: apply bounding set: Operation not permitted\n')
            value = project_retained(str(root), capture.name)
        self.assertEqual(value['status'], 'read-verified-private')
        self.assertEqual(value['stderrBytes'], 53)
        self.assertEqual(value['stderrFailure'], 'capability-action-refused')
        self.assertNotIn('Operation not permitted', json.dumps(value))

    def test_same_53_byte_length_never_guesses_supported_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture, _ = self.make(root, b'x' * 53)
            value = project_retained(str(root), capture.name)
        self.assertEqual(value['stderrFailure'], 'unobserved-or-unclassified')

    def test_password_paths_and_unknown_literals_never_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = b'setpriv: failed to execute /private/credential: No such file or directory\n'
            capture, _ = self.make(root, secret)
            value = project_retained(str(root), capture.name)
        self.assertEqual(value['stderrFailure'], 'command-exec-not-found')
        for token in ('credential', '/private', str(root), capture.name):
            self.assertNotIn(token, json.dumps(value))

    def test_public_parent_or_child_mode_refuses(self):
        for scope in ('parent', 'child'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                capture, _ = self.make(root, b'known')
                (root if scope == 'parent' else capture).chmod(0o755)
                self.assertEqual(project_retained(str(root), capture.name)['status'], 'read-refused')

    def test_prefix_symlink_public_mode_and_oversize_refuse(self):
        for kind in ('symlink', 'mode', 'oversize', 'fifo'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                capture, file = self.make(root, b'known')
                if kind == 'symlink':
                    file.unlink(); file.symlink_to(capture / 'stdout-prefix.private.log')
                elif kind == 'mode':
                    file.chmod(0o644)
                elif kind == 'oversize':
                    file.write_bytes(b'x' * 8193)
                else:
                    file.unlink(); os.mkfifo(file, 0o600)
                self.assertEqual(project_retained(str(root), capture.name)['status'], 'read-refused')

    def test_path_traversal_or_unbound_capture_name_refuses_before_open(self):
        for value in ('../preflight-failure-' + 'a' * 16, 'other-' + 'a' * 16, '/private/credential'):
            with patch('read_private_preflight.os.open') as opened:
                self.assertEqual(project_retained('/private/parent', value)['status'], 'read-refused')
                opened.assert_not_called()

    def test_changed_same_length_prefix_refuses_and_closes_owned_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture, file = self.make(root, b'123')
            original = os.read
            called = False
            def changed(fd, length):
                nonlocal called
                value = original(fd, length)
                if not called:
                    called = True
                    file.write_bytes(b'456')
                return value
            with patch('read_private_preflight.os.read', changed), patch('read_private_preflight.os.close', wraps=os.close) as closed:
                result = project_retained(str(root), capture.name)
                self.assertEqual(closed.call_count, 3)
            self.assertEqual(result['status'], 'read-refused')


if __name__ == '__main__':
    unittest.main()
