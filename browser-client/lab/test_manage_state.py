# SPDX-License-Identifier: Apache-2.0
"""No-process preparation cleanup and strict recorded-identity contracts."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location('lab_state_test_manager', SOURCE / 'manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManagedState(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='overte-owned-state-test-')
        self.root = Path(self.directory.name)
        self.state = self.root / 'runtime' / 'processes.json'
        self.state_override = patch.object(m, 'STATE', self.state)
        self.state_override.start()

    def tearDown(self):
        self.state_override.stop()
        self.directory.cleanup()

    def write(self, value):
        self.state.parent.mkdir(exist_ok=True)
        self.state.write_text(value)

    def test_missing_registry_stop_is_a_non_mutating_noop(self):
        with patch.object(m.os, 'killpg') as kill, patch.object(m, 'alive') as alive:
            self.assertEqual(m.load_state(), {})
            m.stop()
        kill.assert_not_called()
        alive.assert_not_called()
        self.assertFalse(self.state.parent.exists())

    def test_existing_empty_registry_bytes_are_preserved(self):
        self.write(' { } \n')
        with patch.object(m.os, 'killpg') as kill:
            m.stop()
        kill.assert_not_called()
        self.assertEqual(self.state.read_text(), ' { } \n')

    def test_malformed_registry_is_not_converted_to_missing(self):
        self.write('{')
        with patch.object(m.os, 'killpg') as kill, self.assertRaises(json.JSONDecodeError):
            m.stop()
        kill.assert_not_called()
        self.assertEqual(self.state.read_text(), '{')

    def test_invalid_identities_fail_before_any_process_is_inspected(self):
        entries = [[], None, {'one': None}, {'one': {}},
                   {'one': {'pid': True, 'startTicks': '12'}},
                   {'one': {'pid': -1, 'startTicks': '12'}},
                   {'one': {'pid': '123', 'startTicks': '12'}},
                   {'one': {'pid': 123, 'startTicks': 12}},
                   {'one': {'pid': 123, 'startTicks': ''}},
                   {'one': {'pid': 123, 'startTicks': '12junk'}}]
        for value in entries:
            with self.subTest(value=value):
                self.write(json.dumps(value))
                with patch.object(m, 'alive') as alive, patch.object(m.os, 'killpg') as kill, \
                     self.assertRaisesRegex(RuntimeError, 'valid recorded process identities'):
                    m.stop()
                alive.assert_not_called()
                kill.assert_not_called()

    def test_permission_error_remains_an_error(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError('test-only-denial')), \
             self.assertRaises(PermissionError):
            m.load_state()

    def test_dangling_registry_symlink_is_rejected(self):
        self.state.parent.mkdir()
        self.state.symlink_to(self.root / 'absent-other-registry')
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            m.stop()
        self.assertTrue(self.state.is_symlink())

    def test_existing_registry_symlink_is_rejected(self):
        self.state.parent.mkdir()
        target = self.root / 'other-registry'
        target.write_text('{}')
        self.state.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            m.stop()
        self.assertEqual(target.read_text(), '{}')

    def test_valid_dead_process_can_be_removed_without_signalling(self):
        self.write(json.dumps({'owned': {'pid': 1234567, 'startTicks': '123'}}))
        with patch.object(m, 'alive', return_value=False), patch.object(m.os, 'killpg') as kill:
            m.stop()
        kill.assert_not_called()
        self.assertEqual(json.loads(self.state.read_text()), {})

    def test_reused_pid_is_refused_without_killing_or_changing_state(self):
        document = json.dumps({'owned': {'pid': 1234567, 'startTicks': '123'}})
        self.write(document)
        with patch.object(m, 'alive', return_value=True), \
             patch.object(Path, 'read_bytes', return_value=str(m.REPO).encode()), \
             patch.object(Path, 'resolve', return_value=m.REPO), \
             patch.object(m, 'start_ticks', return_value='456'), \
             patch.object(m.os, 'killpg') as kill, \
             self.assertRaisesRegex(RuntimeError, 'was reused'):
            m.stop()
        kill.assert_not_called()
        self.assertEqual(self.state.read_text(), document)

    def test_changed_process_group_is_refused(self):
        document = json.dumps({'owned': {'pid': 1234567, 'startTicks': '123'}})
        self.write(document)
        with patch.object(m, 'alive', return_value=True), \
             patch.object(Path, 'read_bytes', return_value=str(m.REPO).encode()), \
             patch.object(Path, 'resolve', return_value=m.REPO), \
             patch.object(m, 'start_ticks', return_value='123'), \
             patch.object(m.os, 'getpgid', return_value=7654321), \
             patch.object(m.os, 'killpg') as kill, \
             self.assertRaisesRegex(RuntimeError, 'Process group'):
            m.stop()
        kill.assert_not_called()
        self.assertEqual(self.state.read_text(), document)

    def test_real_cli_stop_before_prepare_is_successful_and_creates_nothing(self):
        environment = {'PATH': '/usr/bin:/bin', 'OVERTE_LAB_ROOT': str(self.root),
                       'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, str(SOURCE / 'manage.py'), 'stop'],
                                env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
