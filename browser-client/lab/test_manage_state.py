# SPDX-License-Identifier: Apache-2.0
"""No-process preparation cleanup and strict recorded-identity contracts."""
import importlib.util
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# Execute the strict readback suite in the existing owned-lab state gate.
# These cases validate real helper output, without another gate or mirror tests.
from test_guest_permissions import GuestReadback
from test_provisioning_diagnostics import ProvisioningDiagnostics
from test_native_launch import ManagedLaunchRecords, OwnedSupervisor
from test_managed_stop import StopContracts, SessionBoundary
from test_managed_parent_guard import ParentGuards, NativePrivilege, AdmitRetirement
from test_managed_registered_wrapper import Registered
from test_managed_python_boundary import PythonBoundary
from test_managed_owned_cpu import OwnedCPU
from test_managed_parent_owned_cpu import RealParent
from test_managed_ancestry import ManagedAncestry
from test_managed_ancestry_owned_cpu import ManagedAncestryOwnedCPU

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
        def synthetic_identity(pid):
            if pid != 1234567:raise AssertionError('unexpected synthetic identity')
            return None
        def synthetic_group_absent(group):
            if group != 1234567:raise AssertionError('unexpected synthetic group')
            return True
        self.identity_override = patch.object(m._OwnedStop, 'identity', side_effect=synthetic_identity)
        self.group_override = patch.object(m._OwnedStop, 'group_absent', side_effect=synthetic_group_absent)
        self.identity_override.start();self.group_override.start()

    def tearDown(self):
        self.group_override.stop();self.identity_override.stop()
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

    def test_start_keeps_administration_token_out_of_persistent_files(self):
        (self.root / 'appimage/squashfs-root').mkdir(parents=True)
        (self.root / 'appimage/squashfs-root/AppRun').touch()
        (self.root / 'config').mkdir()
        (self.root / 'runtime').mkdir()
        credential = {'token': 'a' * 64,
                      'nativeVerifier': m.hashlib.sha256(('a' * 64).encode()).hexdigest()}
        with patch.object(m, 'ROOT', self.root), patch.object(m, 'load_tools', return_value={}), \
             patch.object(m, 'native_admin_credential', return_value=credential), \
             patch.object(m.native_launch, 'managed_command', return_value=nullcontext((['owned-domain-fixture'], {}, 3, {}))), \
             patch.object(m.socket, 'socket'), \
             patch.object(m, 'launch', side_effect=RuntimeError('owned-test-before-native-launch')) as launch, \
             self.assertRaisesRegex(RuntimeError, 'owned-test-before-native-launch'):
            m.start()
        self.assertFalse((self.root / 'runtime/admin.json').exists(),
                         'A startup-only administration token must not be stored on disk')
        config = json.loads((self.root / 'config/domain.json').read_text())
        self.assertEqual(config['security']['http_password'], credential['nativeVerifier'])
        self.assertNotIn(credential['token'], (self.root / 'config/domain.json').read_text())
        self.assertEqual(launch.call_args.args[0], 'domain')
        self.assertNotIn(credential['token'], json.dumps(launch.call_args.args[2]))


if __name__ == '__main__':
    unittest.main()
