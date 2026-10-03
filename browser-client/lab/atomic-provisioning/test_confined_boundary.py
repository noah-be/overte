# SPDX-License-Identifier: Apache-2.0
"""Actual immutable policy descriptors and CPU-only launch-boundary controls."""
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import confined_launch as launch
import curate


class BoundaryTests(unittest.TestCase):
    def test_policy_descriptor_cannot_be_written_grown_or_unsealed(self):
        fd = launch.sealed_filter()
        try:
            self.assertEqual(os.read(fd, 4096), launch.tmpfile_filter())
            with self.assertRaises(OSError):os.write(fd, b'private-policy-substitution')
            with self.assertRaises(OSError):os.ftruncate(fd, 4096)
            with self.assertRaises(OSError):fcntl.fcntl(fd, fcntl.F_ADD_SEALS, 0)
        finally:
            os.close(fd)

    def test_unknown_architecture_refuses_before_creating_a_usable_policy(self):
        with patch.object(launch.platform, 'machine', return_value='unreviewed-ABI'):
            with self.assertRaisesRegex(ValueError, '^confined-filter-ABI-unreviewed$'):
                launch.sealed_filter()

    def test_private_root_alias_or_public_mode_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):launch.private_directory(directory + '/.')
            root.chmod(0o755)
            with self.assertRaises(ValueError):launch.private_directory(directory)

    def test_final_native_guard_keeps_exact_original_argv_and_full_environment(self):
        good = {'zeroCapabilities': True, 'noNewPrivileges': True, 'userIsolated': True,
                'ipcIsolated': True, 'profile': 'signed-bwrap-child-enforce', 'identityStable': True,
                'seccompFiltered': True, 'allThreadsConfined': True}
        command = ['/usr/bin/unshare', '--user', '--map-current-user', '--ipc', '--',
                   '/owned/domain-server', '--user-config', '/owned/settings.json',
                   '--logOptions', 'nocolor,nojournald']
        environment = {'HOME': '/unchanged', 'LD_LIBRARY_PATH': '/native-only', 'LANG': 'C'}
        with patch.object(launch, 'confinement', return_value=good), patch.object(launch.os, 'execvpe') as execute:
            launch.exec_final({'environment': environment}, command, 'private-user-identity', 'private-ipc-identity')
            execute.assert_called_once_with(command[5], command[5:], environment)
        for key in good:
            row = {**good, key: 'unqualified' if key == 'profile' else False}
            with patch.object(launch, 'confinement', return_value=row), patch.object(launch.os, 'execvpe') as execute:
                with self.assertRaisesRegex(ValueError, '^confined-native-guard-refused$'):
                    launch.exec_final({'environment': environment}, command, 'private', 'private')
                execute.assert_not_called()

    def test_bootstrap_never_receives_native_loader_environment_or_caller_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab, output = root / 'lab', root / 'output'
            lab.mkdir(mode=0o700);output.mkdir(mode=0o700)
            document = {'environment': {'OVERTE_LAB_ROOT': str(lab), 'LD_LIBRARY_PATH': '/private-native-only'},
                        'native': str(lab / 'server/opt/overte/domain-server'),
                        'settings': str(lab / 'config/domain.json'), 'output': str(output), 'cwd': str(root)}
            calls = []
            def execute(executable, argv, env):
                fd = int(argv[argv.index('--seccomp') + 1])
                calls.append((executable, argv, env, os.pread(fd, 4096, 0)))
            with patch.object(launch.os, 'execvpe', side_effect=execute):
                launch.exec_confined(document, str(output / 'launch.private.json'))
            self.assertEqual(len(calls), 1)
            executable, argv, env, policy = calls[0]
            self.assertEqual(executable, '/usr/bin/bwrap')
            self.assertEqual(policy, launch.tmpfile_filter())
            self.assertIn('--disable-userns', argv)
            self.assertEqual(argv[argv.index('--cap-drop') + 1], 'ALL')
            self.assertNotIn('LD_LIBRARY_PATH', env)
            self.assertNotIn('/private-native-only', argv)
            self.assertNotIn('--cap-add', argv)
            document['settings'] = str(root / 'foreign.json')
            with patch.object(launch.os, 'execvpe') as execute:
                with self.assertRaises(ValueError):launch.exec_confined(document, str(output / 'launch.private.json'))
                execute.assert_not_called()

    def test_curator_refuses_native_confinement_without_variant_or_with_private_fields(self):
        row = {'schemaVersion': 1, 'scope': 'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle',
               'completed': False, 'phase': 'preparation', 'endpointOwnership': 'not-observed', 'provisioning': 'not-requested',
               'diagnosticLaunch': 'signed-bwrap-fixed-tmpfile-denial',
               'nativeConfinement': {'zeroCapabilities': True, 'noNewPrivileges': True,
                                     'userIsolated': True, 'ipcIsolated': True,
                                     'identityStable': True, 'profile': 'signed-bwrap-child-enforce',
                                     'seccompFiltered': True, 'allThreadsConfined': True}}
        self.assertEqual(curate.project(row)['nativeConfinement'], row['nativeConfinement'])
        for changed in ({key: value for key, value in row.items() if key != 'diagnosticLaunch'},
                        {**row, 'nativeConfinement': {**row['nativeConfinement'], 'privatePath': '/private'}},
                        {**row, 'nativeConfinement': {**row['nativeConfinement'], 'zeroCapabilities': 1}},
                        {**row, 'nativeConfinement': {**row['nativeConfinement'], 'profile': '/private'}}):
            with self.assertRaises(ValueError):curate.project(changed)
        self.assertNotIn('/private', json.dumps(curate.project(row)))


if __name__ == '__main__':unittest.main()
