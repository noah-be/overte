# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise owned probe preparation without starting services or checking ports."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import probe

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent


class ProbeCredentials(unittest.TestCase):
    def test_environment_schema_observation_reports_only_existing_bounds(self):
        environment={f'PRIVATE_NAME_{index}':'private-token-value'for index in range(probe.MAX_ENV_ENTRIES+1)}
        environment['PRIVATE_NAME_0']='private-token-value'*500
        environment['PRIVATE_NAME_1']='private\0token'
        row=probe.environment_shape(environment)
        self.assertEqual(row['entries'],probe.MAX_ENV_ENTRIES+1)
        self.assertTrue(row['entryBoundExceeded'])
        self.assertTrue(row['valueBoundExceeded'])
        self.assertTrue(row['nulObserved'])
        self.assertNotIn('PRIVATE_NAME',json.dumps(row))
        self.assertNotIn('private-token',json.dumps(row))
        with self.assertRaises(ValueError):probe.environment_shape(['private-token'])

    def test_fixed_failure_observation_refuses_unknown_exception_prose(self):
        self.assertEqual(probe.failure_observation(ValueError('input-size-or-executable-invalid'))['refusal'],
                         'input-size-or-executable-invalid')
        for error in (ValueError('/private/token-secret'), ValueError(['private-secret']),
                      RuntimeError('probe-reviewed-source-changed'),
                      ValueError('probe-reviewed-source-changed', '/private/token-secret')):
            row=probe.failure_observation(error)
            self.assertEqual(row['refusal'],'unclassified')
            self.assertNotIn('private',json.dumps(row))
            self.assertNotIn('token-secret',json.dumps(row))

    def test_failed_cli_keeps_original_failure_and_prints_only_fixed_observation(self):
        import contextlib
        import io
        stderr=io.StringIO()
        with patch.object(sys,'argv',['probe','--repo-root','/unused-repo','--lab-root','/unused-lab','--private-output','/unused-output']), \
             patch.object(probe,'run',side_effect=ValueError('probe-reviewed-source-changed')), \
             contextlib.redirect_stderr(stderr):
            self.assertEqual(probe.main(),1)
        lines=stderr.getvalue().splitlines()
        self.assertEqual(lines[-1],'standalone-owned-probe-refused')
        row=json.loads(lines[0].split(':',1)[1])
        self.assertEqual(row,{'scope':'owned-probe-failure-observation-not-causality',
                              'refusal':'probe-reviewed-source-changed'})

    def test_preparation_persists_only_verifier_and_keeps_authentication_in_memory(self):
        original_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        with tempfile.TemporaryDirectory(prefix='overte-probe-credential-test-') as temporary:
            root = Path(temporary).resolve()
            repo, lab, output, fixtures = [root / name for name in ('repo', 'lab', 'output', 'fixtures')]
            for directory in (repo / 'browser-client/lab', lab, output, fixtures):
                directory.mkdir(parents=True, mode=0o700)
            pins = json.loads((HERE / 'source-pins.json').read_text())
            for name in pins:
                shutil.copyfile(SOURCE / name, repo / 'browser-client/lab' / name)
            (fixtures / 'source-pins.json').write_text(json.dumps(pins))
            native = lab / 'server/opt/overte'
            (native / 'resources').mkdir(parents=True)
            (native / 'domain-server').write_bytes(b'owned non-executable native-data fixture')
            (native / 'domain-server').chmod(0o700)
            (native / 'resources/describe-settings.json').write_text('{}')
            (fixtures / 'native-pins.json').write_text(json.dumps({
                'domain-server': hashlib.sha256((native / 'domain-server').read_bytes()).hexdigest(),
                'describe-settings.json': hashlib.sha256(b'{}').hexdigest(),
            }))
            (fixtures / 'dependency.json').write_text(json.dumps({'binarySHA256': 'a' * 64}))
            with patch.dict(os.environ), patch.object(probe, 'HERE', fixtures), \
                 patch.object(probe, 'free_ports') as ports, \
                 patch.object(probe, 'validated_launch', return_value=[]) as admission:
                result = probe.prepare(repo, lab, output)
            ports.assert_called_once_with()
            admission.assert_called_once()
            authorization = result[3]
            self.assertTrue(authorization.startswith('Basic '))
            user, token = base64.b64decode(authorization[6:]).decode().split(':', 1)
            self.assertEqual(user, 'browser-lab-admin')
            self.assertEqual(len(token), 64)
            self.assertFalse((lab / 'runtime/admin.json').exists())
            config = json.loads((lab / 'config/domain.json').read_text())
            self.assertEqual(config['security']['http_password'], hashlib.sha256(token.encode()).hexdigest())
            for directory in (lab / 'config', lab / 'runtime', output):
                for file in directory.iterdir():
                    self.assertFalse(token.encode() in file.read_bytes(),
                                     'Preparation must not persist the startup-only administration token')

    def test_reviewed_source_pins_match_all_current_probe_dependencies(self):
        pins = json.loads((HERE / 'source-pins.json').read_text())
        self.assertEqual(set(pins), {'manage.py', 'native_admin.py', 'guest_permissions.py',
                                    'provisioning_diagnostics.py', 'host_tools.py', 'chrome_browser.py'})
        for name, expected in pins.items():
            with self.subTest(source=name):
                self.assertEqual(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
