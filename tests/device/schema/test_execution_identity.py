# SPDX-License-Identifier: Apache-2.0
"""Actual runner control flow; the native target and module boundary are test-only."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('identity_device_runner', ROOT / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from execution_identity import ExecutionIdentity
from result_binding import validate
from terminal_evidence import EvidenceError


class ExecutionIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.artifact = self.root / 'synthetic-candidate'
        self.artifact.write_bytes(b'test-only candidate bytes')
        self.sha = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.claim = dict(schemaVersion=1, sourceRevision='a'*40, artifactSha256=self.sha,
                          installedCandidateVerified=True)
        self.args = argparse.Namespace(adapter_manifest=ROOT/'adapters/mock/adapter.json',
            catalog=ROOT/'catalog.json', suite='smoke', list=False, tablet_policy=None,
            target=None, allow_virtual=True, output_dir=self.root/'output', keep_running=False,
            require_complete=True, candidate_artifact=self.artifact,
            expected_source_sha='a'*40, expected_artifact_sha256=self.sha)
        self.modules = runner.load_modules(self.args.catalog, 'smoke')
        self.capabilities = sorted({cap for mod in self.modules for cap in mod['requires']})
        self.events = []

    def execute(self, first=None, last=None, mutate=False, module_status='passed'):
        calls = 0
        def adapter(command, action, selector):
            nonlocal calls
            self.events.append(action)
            if action == 'cleanup': return {}
            calls += 1
            claim = first if calls == 1 else last
            return copy.deepcopy({'executionIdentity': self.claim} if claim is None else claim)
        def module(mod, *args):
            self.events.append('module')
            if mutate: self.artifact.write_bytes(b'test-only changed candidate')
            return dict(id=mod['id'], description=mod['description'], status=module_status,
                        returncode=0 if module_status == 'passed' else 1,
                        durationSeconds=0.0, output='CANARY_SECRET_NOT_EXPORTED')
        target = dict(selector='test-only-private-selector', platform='android', physical=False,
                      capabilities=self.capabilities)
        with patch.object(runner, 'parse_args', return_value=self.args), \
             patch.object(runner, 'discover', return_value=target), \
             patch.object(runner, 'adapter_call', side_effect=adapter), \
             patch.object(runner, 'run_module', side_effect=module), \
             patch.dict(runner.os.environ, {'OVERTE_DEVICE_LOCK_ROOT': str(self.root/'locks')}):
            return runner.main()

    def verify(self):
        return validate(self.args.output_dir, 'a'*40, self.sha, 'mock-e2e', 'android',
                        [m['id'] for m in self.modules], False)

    def test_actual_runner_emits_consumer_compatible_identity_with_reserved_rechecks(self):
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.verify()['status'], 'RESULT_BOUND_NOT_NODE_ACCEPTED')
        self.assertEqual(self.events, ['describe'] + ['module']*len(self.modules) + ['describe','cleanup'])
        raw = (self.args.output_dir/'result-identity.json').read_text()
        self.assertNotIn('selector', raw)
        self.assertNotIn('CANARY', raw)

    def test_missing_initial_native_binding_runs_no_module_and_emits_no_identity(self):
        self.assertEqual(self.execute(first={}), 1)
        self.assertNotIn('module', self.events)
        self.assertFalse((self.args.output_dir/'result-identity.json').exists())

    def test_changed_final_installation_cannot_emit_identity(self):
        wrong = copy.deepcopy(self.claim); wrong['artifactSha256'] = 'c'*64
        self.assertEqual(self.execute(last={'executionIdentity': wrong}), 1)
        self.assertFalse((self.args.output_dir/'result-identity.json').exists())

    def test_candidate_mutation_cannot_emit_identity(self):
        self.assertEqual(self.execute(mutate=True), 1)
        self.assertFalse((self.args.output_dir/'result-identity.json').exists())

    def test_test_failure_is_bound_but_never_accepted(self):
        self.assertEqual(self.execute(module_status='failed'), 1)
        self.assertTrue((self.args.output_dir/'result-identity.json').exists())
        with self.assertRaises(EvidenceError): self.verify()

    def test_arguments_and_artifact_reject_before_discovery(self):
        self.args.expected_source_sha = None
        with self.assertRaisesRegex(ValueError, 'ALL_ARGUMENTS'): self.execute()
        self.assertEqual(self.events, [])
        for source, artifact in [('bad',self.sha), ('a'*40, 'b'*64)]:
            with self.assertRaises(ValueError): ExecutionIdentity(self.artifact, source, artifact)
        link = self.root/'link'; link.symlink_to(self.artifact)
        with self.assertRaises(ValueError): ExecutionIdentity(link, 'a'*40, self.sha)

    def test_strict_native_claim_does_not_accept_boolean_version_or_unverified_install(self):
        identity = ExecutionIdentity(self.artifact, 'a'*40, self.sha)
        for key, value in [('schemaVersion',True), ('installedCandidateVerified',False),
                           ('sourceRevision','c'*40), ('extra','unknown')]:
            claim = self.claim | {key:value}
            with self.assertRaises(ValueError): identity.verify_description({'executionIdentity':claim})

    def test_legacy_diagnostic_mode_has_no_identity(self):
        self.args.candidate_artifact = self.args.expected_source_sha = self.args.expected_artifact_sha256 = None
        self.assertEqual(self.execute(first={}), 0)
        self.assertFalse((self.args.output_dir/'result-identity.json').exists())


if __name__ == '__main__': unittest.main()
