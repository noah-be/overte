#!/usr/bin/env python3
"""Real canonical entry/native verifier; synthetic APK/tools and in-memory ADB only."""
import contextlib
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tests/device'))
from adapters.android import adapter

spec = importlib.util.spec_from_file_location('pico_candidate_test_fixture',
    Path(__file__).with_name('test_candidate_identity.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class FakeAdb:
    """Test boundary: no subprocess, SDK, socket, discovery or real receipt."""
    target = 'synthetic-private-target'
    path = '/data/app/~~synthetic/org.overte.pico-fixture/base.apk'

    def __init__(self, digest):
        self.digest = digest
        self.mapping = 'package:' + self.path + '\n'
        self.paths = []
        self.events = []
        self.after_install = None
        self.error = False

    def require_connected(self, target, **kwargs):
        assert target == self.target

    def authorized_targets(self):
        return [self.target]

    def prop(self, target, name):
        assert target == self.target
        return {'ro.product.manufacturer': 'Pico', 'ro.product.brand': 'Pico',
            'ro.product.model': 'Pico 4', 'ro.product.device': 'Pico',
            'ro.product.cpu.abilist': 'arm64-v8a', 'ro.build.version.sdk': '26',
            'ro.opengles.version': '196610', 'ro.kernel.qemu': '0',
            'ro.build.version.release': 'test-only'}.get(name, '')

    def process_state(self, target, package):
        assert target == self.target and package == 'org.overte.pico'
        return {'running': False, 'identity': None}

    def shell(self, target, *args, check=True):
        assert target == self.target
        self.events.append(args)
        if self.error:
            raise RuntimeError('PRIVATE_OS_EXCEPTION_CANARY')
        if args == ('pm', 'path', 'org.overte.pico'):
            return self.paths.pop(0) if self.paths else self.mapping
        if args[:2] == ('toybox', 'sha256sum'):
            assert args[2] == self.path
            return self.digest + '  ' + args[2] + '\n'
        if args == ('am', 'force-stop', 'org.overte.pico'):
            return ''
        if args == ('pidof', '-s', 'org.overte.pico'):
            return ''
        raise AssertionError('unexpected fake native operation')

    def execute(self, args, *, target, timeout):
        assert target == self.target and args[:4] == ['install', '-r', '-d', '-g']
        self.events.append(('install',))
        if self.after_install:
            self.after_install()
        return ''


class NativeExecutionBindingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.CandidateIdentityTest('test_actual_candidate_entry_and_pending_semantics')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.record_file.write_text(json.dumps(self.fixture.record))
        self.fake = FakeAdb(self.fixture.record['artifactSha256'])
        self.prefix = ['--kind', 'pico', '--native-binding', '--apk', str(self.fixture.apk),
                       *self.fixture.command[3:], '--expected-version-code', '7']
        native = patch.object(adapter, 'AdbTransport', return_value=self.fake)
        native.start(); self.addCleanup(native.stop)
        environment = patch.dict(os.environ, {'OVERTE_PICO_OPENXR_INPUT': '0',
            'OVERTE_ANDROID_E2E_DEBUG': '0', 'OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT': ''})
        environment.start(); self.addCleanup(environment.stop)

    def invoke(self, action, extra=(), prefix=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = adapter.main([*(self.prefix if prefix is None else prefix), action,
                                   '--target', self.fake.target, *extra])
        self.assertEqual(result, 0)
        self.assertNotIn(self.fake.target, output.getvalue())
        self.assertNotIn(str(self.fixture.root), output.getvalue())
        return json.loads(output.getvalue())

    def instance(self):
        args, binding = adapter.cli([*self.prefix, 'describe', '--target', self.fake.target])
        return binding.create_adapter(args, adapter.AndroidAdapter)

    def test_real_dispatch_and_original_candidate_verifier(self):
        result = self.invoke('describe')
        self.assertEqual(result['adapter'], 'android-pico-adb')
        self.assertEqual(result['executionIdentity'], dict(schemaVersion=1, sourceRevision='a'*40,
            artifactSha256=self.fake.digest, installedCandidateVerified=True))
        self.assertGreaterEqual(self.fake.events.count(('pm', 'path', 'org.overte.pico')), 6)
        self.assertEqual(self.invoke('invoke', ['--operation', 'app.process']),
                         {'running': False, 'identity': None})
        self.assertNotIn('app.upgrade', self.instance().capabilities())
        # The signature-tool output and OS bytes above are synthetic. Pending
        # SH009 receipt semantics remain unchanged even on this positive path.
        self.assertEqual(self.fixture.record['signature']['state'], 'pending')

    def test_missing_split_unsafe_changed_and_foreign_installations(self):
        for mapping in ['', self.fake.mapping * 2,
                        'package:/data/app/x/../base.apk\n',
                        'package:/data/app/x/$(private)/base.apk\n',
                        'package:/data/app/x/base.apk\nWARNING\n']:
            with self.subTest(mapping=mapping):
                self.fake.mapping = mapping
                with self.assertRaisesRegex(ValueError, '^OVT_PICO_BINDING_REJECTED$'):
                    self.invoke('describe')
        self.fake.mapping = 'package:' + self.fake.path + '\n'
        self.fake.paths = [self.fake.mapping, 'package:/data/app/other/base.apk\n']
        with self.assertRaises(ValueError): self.invoke('describe')
        self.fake.paths = []
        self.fake.digest = 'f' * 64
        with self.assertRaises(ValueError): self.invoke('describe')

    def test_build_receipt_bytes_frozen_and_missing_evidence_precedes_device(self):
        bound = self.instance()
        # Harmless JSON whitespace still changes frozen bytes, even though the
        # receipt could be rehashed consistently in a modified envelope.
        entry = self.fixture.build['evidence']['receipts'][0]
        path = self.fixture.build_file.parent / entry['path']
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, '^OVT_PICO_BINDING_REJECTED$'):
            bound.describe(self.fake.target)
        self.assertEqual(self.fake.events, [])
        self.fixture.build_file.unlink()
        with self.assertRaises(ValueError):
            self.instance()
        self.assertEqual(self.fake.events, [])
        self.invoke('cleanup')

    def test_candidate_and_evidence_rechecked_not_cached_receipts(self):
        bound = self.instance()
        self.fixture.files['spdx'].write_text('PRIVATE_MUTATED_EVIDENCE')
        with self.assertRaisesRegex(ValueError, '^OVT_PICO_BINDING_REJECTED$'):
            bound.describe(self.fake.target)
        # Cleanup remains usable even on the very same now-invalid instance.
        self.assertEqual(bound.cleanup(self.fake.target), {'cleaned': True})
        self.fixture.apk.unlink()
        self.assertEqual(self.invoke('cleanup', prefix=['--kind', 'pico', '--native-binding']),
                         {'cleaned': True})

    def test_reinstall_same_candidate_late_mismatch_and_upgrade_rejected(self):
        values = json.dumps({'path': str(self.fixture.apk)})
        extra = ['--operation', 'app.install', '--arguments', values]
        self.assertEqual(self.invoke('invoke', extra), {'installed': True})
        self.fake.after_install = lambda: setattr(self.fake, 'digest', 'f' * 64)
        with self.assertRaises(ValueError): self.invoke('invoke', extra)
        self.fake.events.clear()
        with self.assertRaises(ValueError):
            self.invoke('invoke', ['--operation', 'app.upgrade'])
        self.assertNotIn(('install',), self.fake.events)

    def test_incomplete_inputs_and_private_native_failure_closed(self):
        with patch.object(adapter, 'AdbTransport') as transport:
            with self.assertRaises(ValueError):
                adapter.main(['--kind', 'pico', '--native-binding', 'describe'])
            transport.assert_not_called()
        self.fake.error = True
        with self.assertRaisesRegex(ValueError, '^OVT_PICO_BINDING_REJECTED$'):
            self.invoke('describe')
        result = subprocess.run([sys.executable, str(ROOT / 'tests/device/adapters/android/adapter.py'),
            '--kind', 'pico', '--native-binding', '--apk', 'PRIVATE_PATH_CANARY', 'describe'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), 'OVT_ANDROID_ADAPTER_REJECTED')
        self.assertEqual(result.stdout, '')
        # The same original Pico entry as a REAL child through the canonical
        # runner. Missing candidate inputs reject before constructing ADB, as
        # asserted above; this never discovers or accesses a device.
        runner_spec = importlib.util.spec_from_file_location('pico_adapter_error_runner',
            ROOT / 'tests/device/run.py')
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        with self.assertRaisesRegex(RuntimeError, '^OVT_TEST_INFRASTRUCTURE_ERROR$'):
            runner.adapter_call([sys.executable,
                str(ROOT / 'tests/device/adapters/android/adapter.py'),
                '--kind', 'pico', '--native-binding', '--apk', 'PRIVATE_PATH_CANARY'],
                'describe', self.fake.target, timeout=5)

    def test_real_runner_producer_native_claim_and_pico_consumer(self):
        from adapters.pico4.verify_result import verify
        runner_spec = importlib.util.spec_from_file_location('pico_bound_original_runner',
            ROOT / 'tests/device/run.py')
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        native_path = ROOT / 'tests/device/adapters/android/adapter.py'
        manifest = self.fixture.root / 'private-bound-manifest.json'
        manifest.write_text(json.dumps(dict(schemaVersion=1, id='android-pico-adb',
            command=[str(native_path), *self.prefix])))
        args = argparse.Namespace(adapter_manifest=manifest, catalog=ROOT / 'tests/device/catalog.json',
            suite='smoke', list=False, tablet_policy=None, target=None, allow_virtual=False,
            output_dir=self.fixture.root / 'producer', keep_running=False, require_complete=True,
            candidate_artifact=self.fixture.apk, expected_source_sha='a'*40,
            expected_artifact_sha256=self.fixture.record['artifactSha256'])
        original_run = subprocess.run
        def in_process_native(command, **kwargs):
            if len(command) > 1 and command[1] == str(native_path):
                self.assertIs(kwargs['stderr'], subprocess.DEVNULL)
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        code = adapter.main(command[2:])
                    except ValueError:
                        code = 2
                        print('OVT_ANDROID_ADAPTER_REJECTED', file=sys.stderr)
                return subprocess.CompletedProcess(command, code, stdout.getvalue(), None)
            # Only the synthetic aapt/apksigner fixtures reach this boundary.
            return original_run(command, **kwargs)
        changed = False
        def module_result(module, *unused):
            if changed:
                self.fake.digest = 'f'*64
            return dict(id=module['id'], description=module['description'], status='passed',
                        returncode=0, durationSeconds=0.0, output='TEST_MODULE_NOT_DEVICE_EVIDENCE')
        with patch.object(runner, 'parse_args', return_value=args), \
             patch.object(runner.subprocess, 'run', side_effect=in_process_native), \
             patch.object(runner, 'run_module', side_effect=module_result), \
             patch.dict(os.environ, {'OVERTE_DEVICE_LOCK_ROOT': str(self.fixture.root / 'locks')}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 0)
            self.assertEqual(verify(args.output_dir, args.expected_source_sha,
                args.expected_artifact_sha256, ['launch-smoke'])['status'], 'RESULT_BOUND_NOT_NODE_ACCEPTED')
            changed = True
            args.output_dir = self.fixture.root / 'late-installation-mismatch'
            self.assertEqual(runner.main(), 1)
            self.assertFalse((args.output_dir / 'result-identity.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
