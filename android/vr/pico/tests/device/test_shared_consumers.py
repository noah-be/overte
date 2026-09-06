#!/usr/bin/env python3
"""Pico-focused Shared profile/result consumers with synthetic metadata only."""
import hashlib
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[5]
DEVICE = ROOT / 'tests/device'
PICO = ROOT / 'android/vr/pico'

class SharedConsumersTest(unittest.TestCase):
    def test_original_execution_producer_to_real_pico_consumer(self):
        sys.path.insert(0, str(DEVICE))
        spec = importlib.util.spec_from_file_location('pico_original_device_runner', DEVICE / 'run.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        modules = runner.load_modules(DEVICE / 'catalog.json', 'smoke')
        capabilities = sorted({cap for module in modules for cap in module['requires']})
        with tempfile.TemporaryDirectory(prefix='pico-producer-consumer-synthetic-') as scratch:
            root = Path(scratch)
            artifact = root / 'test-only-candidate'
            artifact.write_bytes(b'synthetic bytes, never an installed APK')
            artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
            args = argparse.Namespace(adapter_manifest=DEVICE / 'adapters/android/pico.json',
                catalog=DEVICE / 'catalog.json', suite='smoke', list=False, tablet_policy=None,
                target=None, allow_virtual=False, output_dir=root / 'bound', keep_running=False,
                require_complete=True, candidate_artifact=artifact, expected_source_sha='a' * 40,
                expected_artifact_sha256=artifact_sha)
            # This metadata is a TEST SUBSTITUTE, not a physical observation.
            target = dict(selector='host-only-synthetic-private-selector', platform='android',
                          physical=True, capabilities=capabilities)
            claim = dict(schemaVersion=1, sourceRevision='a' * 40, artifactSha256=artifact_sha,
                         installedCandidateVerified=True)
            def module_result(module, *unused):
                return dict(id=module['id'], description=module['description'], status='passed',
                            returncode=0, durationSeconds=0.0, output='PRIVATE_TEST_CANARY')
            def produce(bound):
                def adapter(command, action, selector):
                    return {'executionIdentity': claim} if bound and action == 'describe' else {}
                with patch.object(runner, 'parse_args', return_value=args), \
                     patch.object(runner, 'discover', return_value=target), \
                     patch.object(runner, 'adapter_call', side_effect=adapter), \
                     patch.object(runner, 'run_module', side_effect=module_result), \
                     patch.dict(runner.os.environ, {'OVERTE_DEVICE_LOCK_ROOT': str(root / 'locks')}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    return runner.main()
            def consume():
                command = [sys.executable, str(PICO / 'device-tests/verify-result.py'),
                    '--result-dir', str(args.output_dir), '--expected-source-sha', 'a' * 40,
                    '--expected-artifact-sha256', artifact_sha]
                for module in modules: command += ['--required-module', module['id']]
                return subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(produce(True), 0)
            result = consume()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'RESULT_BOUND_NOT_NODE_ACCEPTED')
            self.assertNotIn('PRIVATE_TEST_CANARY', (args.output_dir / 'junit.xml').read_text())
            args.output_dir = root / 'missing-installation-proof'
            self.assertEqual(produce(False), 1)
            self.assertFalse((args.output_dir / 'result-identity.json').exists())
            self.assertEqual(consume().returncode, 1)

    def test_published_profile_and_real_selector_caller(self):
        source = (ROOT / 'libraries/shared/src/shared/FileUtils.cpp').read_text()
        self.assertIn('profileSelectors(product, gles)', source)
        self.assertIn('const Product product = configuredProduct();', source)
        configured = (ROOT / 'libraries/ui/src/ConfiguredCapabilityProfile.h').read_text()
        self.assertIn('resolveProduct(true, false, HIFI_ANDROID_APP)', configured)
        self.assertIn("'-DHIFI_ANDROID_APP=picoInterface'",
            (PICO / 'apps/picoInterface/build.gradle').read_text())
        preferences = (ROOT / 'libraries/shared/src/Preferences.h').read_text()
        self.assertIn('overte::ui::configuredProduct()', preferences)
        with tempfile.TemporaryDirectory(prefix='pico-sh003-') as scratch:
            executable = Path(scratch) / 'profiles'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
                str(DEVICE / 'contracts/profile-test.cpp'), '-o', str(executable)], check=True, timeout=30)
            subprocess.run([str(executable)], check=True, timeout=30)

    def test_offline_production_result_entry_and_negative_boundaries(self):
        module = json.loads((DEVICE / 'catalog.json').read_text())['modules'][0]
        with tempfile.TemporaryDirectory(prefix='pico-sh004-fixture-') as scratch:
            root = Path(scratch)
            # Physical=true is SYNTHETIC test metadata, never a producer/device receipt.
            run = dict(schemaVersion=1, adapter='android-pico-adb', suite='smoke', platform='android',
                physical=True, requireComplete=True, capabilities=module['requires'], modules=[module['id']],
                startedEpochMs=1000, finishedEpochMs=2000, durationSeconds=1, status='passed')
            summary = dict(schemaVersion=1, adapter='android-pico-adb', suite='smoke', status='passed',
                results=[dict(id=module['id'], description=module['description'], status='passed', returncode=0, durationSeconds=1)])
            xml = ('<testsuite name="device-smoke" tests="1" failures="0" errors="0" skipped="0" time="1">'
                '<testcase classname="overte.device" name="launch-smoke" time="1">'
                '<system-out>OVT_REDACTED</system-out></testcase></testsuite>')
            def write():
                identity = dict(contract='overte-sh004-result-v1', sourceRevision='a'*40, artifactSha256='b'*64)
                for name, key, raw in [('run-manifest.json','runSha256',json.dumps(run).encode()),
                        ('summary.json','summarySha256',json.dumps(summary).encode()), ('junit.xml','junitSha256',xml.encode())]:
                    (root / name).write_bytes(raw)
                    identity[key] = hashlib.sha256(raw).hexdigest()
                (root / 'result-identity.json').write_text(json.dumps(identity))
            command = [sys.executable, str(PICO / 'device-tests/verify-result.py'), '--result-dir', scratch,
                '--expected-source-sha', 'a'*40, '--expected-artifact-sha256', 'b'*64, '--required-module', module['id']]
            def invoke(extra=()):
                return subprocess.run(command + list(extra), capture_output=True, text=True, timeout=5)
            write()
            result = invoke()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'RESULT_BOUND_NOT_NODE_ACCEPTED')
            for key, bad in [('physical',False), ('platform','pico4'), ('adapter','android-phone-adb'),
                             ('capabilities',[]), ('requireComplete',False)]:
                with self.subTest(key=key):
                    old = run[key]; run[key] = bad; write()
                    result = invoke(); self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr.strip(), 'PICO_RESULT_REJECTED')
                    run[key] = old
            write()
            for extra in [('--required-module','unknown'), ('--private-canary','not-a-real-selector')]:
                result = invoke(extra)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.strip(), 'PICO_RESULT_REJECTED')
            (root / 'summary.json').write_text('{"private-canary": true}')
            self.assertEqual(invoke().returncode, 1)

if __name__ == '__main__': unittest.main(verbosity=2)
