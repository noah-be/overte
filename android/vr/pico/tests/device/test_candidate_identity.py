#!/usr/bin/env python3
"""Actual Pico candidate consumer; synthetic APK and mock signature tools only."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parents[5]
PICO = ROOT / 'android/vr/pico'
sys.path.insert(0, str(ROOT / 'provenance'))
from artifact_identity import EVIDENCE_KEYS, INPUT_KEYS, digest_file, normalized_inputs
spec = importlib.util.spec_from_file_location('pico_apk_fixture', PICO / 'tests/pico-apk-verifier-test.py')
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
spec = importlib.util.spec_from_file_location('shared_android_receipt_fixture',
    ROOT / 'tests/device/schema/test_android_build_evidence.py')
build_fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(build_fixture)

class CandidateIdentityTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.PicoApkVerifierTests('test_accepts_expected_pico_apk_and_emits_manifest')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.directory
        self.apk = self.fixture._apk()
        self.inputs = {key:'c'*64 for key in INPUT_KEYS}
        self.input_file = self.root / 'expected-inputs.json'
        self.input_file.write_text(json.dumps(self.inputs))
        self.files = {key:self.root/(key+'.json') for key in EVIDENCE_KEYS}
        for key, path in self.files.items(): path.write_text(json.dumps({'testOnly': key}))
        self.record_file = self.root / 'identity.json'
        self.record = dict(contract='overte-sh009-identity-v1', sourceRevision='a'*40, product='pico4',
            versionCode=7, channel='internal-candidate', artifactSha256=digest_file(self.apk), inputs=self.inputs,
            normalizedInputsSha256=normalized_inputs(self.inputs), evidence={k:digest_file(p) for k,p in self.files.items()},
            signature=dict(state='pending',receiptSha256=None), upgrade=dict(state='pending',receiptSha256=None))
        self.command = [sys.executable, str(PICO / 'release/verify-candidate.py'), str(self.apk),
            '--aapt',str(self.fixture.aapt),'--apksigner',str(self.fixture.apksigner),
            '--identity-record',str(self.record_file),'--source-revision','a'*40,
            '--expected-inputs',str(self.input_file),'--minimum-version','6',
            '--expected-version-name','0.4.0','--expected-signer-sha256','0'*64]
        for key,path in self.files.items(): self.command += ['--'+key,str(path)]
        # Original Shared TEST fixture only. These PASS JSON values prove no build.
        self.build = build_fixture.AndroidEvidence().fixture(self.root / 'build', 'pico4')
        self.record_file.write_text(json.dumps(self.record))
        self.build_file = self.build['args'][0]
        envelope = self.build['evidence']
        envelope.update(identityRecordSha256=digest_file(self.record_file),
            artifactSha256=digest_file(self.apk), normalizedInputsSha256=normalized_inputs(self.inputs),
            toolchainSha256=self.inputs['toolchain'])
        for receipt in self.build['receipts'].values():
            receipt.update(artifactSha256=digest_file(self.apk),
                normalizedInputsSha256=normalized_inputs(self.inputs))
            if receipt['provenance']:
                receipt['provenance'].update(toolchainSha256=self.inputs['toolchain'],
                    normalizedInputsSha256=normalized_inputs(self.inputs))
        build_fixture.AndroidEvidence().update(self.build)
        self.command += ['--build-evidence', str(self.build_file),
                         '--expected-artifact-sha256', digest_file(self.apk)]
    def invoke(self, extra=()):
        self.record_file.write_text(json.dumps(self.record))
        return subprocess.run(self.command + list(extra), capture_output=True, text=True, timeout=5)
    def test_actual_candidate_entry_and_pending_semantics(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest['identity_status'], 'ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING')
        self.assertEqual(manifest['identity']['artifactSha256'], manifest['sha256'])
        self.assertEqual(manifest['build_evidence']['status'],
            'MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING')
        # Neither fake signer output nor bytes turn pending Shared claims into verified receipts.
        self.assertEqual(self.record['signature']['state'], 'pending')
        result = subprocess.run([sys.executable, str(PICO / 'release/verify-candidate.py'), str(self.apk)],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires SH-009 identity', result.stderr)
    def test_named_apk_form_shares_verification_and_rejects_duplicates(self):
        self.command = [*self.command[:2], '--apk', self.command[2], *self.command[3:]]
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['identity_status'],
                         'ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING')
        result = self.invoke((str(self.apk),))
        self.assertEqual(result.returncode, 2)
        self.assertIn('candidate APK was supplied twice', result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
    def test_missing_build_inputs_and_each_mandatory_tier_fail_closed(self):
        original_command = list(self.command)
        for option in ('--build-evidence', '--expected-artifact-sha256'):
            offset = self.command.index(option)
            self.command = self.command[:offset] + self.command[offset + 2:]
            self.assertEqual(self.invoke().returncode, 2)
            self.command = list(original_command)
        original = copy.deepcopy(self.build['evidence'])
        for tier in build_fixture.MODULE.mandatory_checks('pico4'):
            self.build['evidence'] = copy.deepcopy(original)
            self.build['evidence']['receipts'] = [entry for entry in original['receipts'] if entry['tier'] != tier]
            build_fixture.AndroidEvidence().update(self.build)
            result = self.invoke()
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.build['evidence'] = original
        build_fixture.AndroidEvidence().update(self.build)
        self.assertEqual(self.invoke().returncode, 0)

    def test_foreign_receipt_and_independent_artifact_expectation_rejected(self):
        receipt = self.build['receipts']['source-graph-compatibility']
        for key, value in [('product', 'android-phone'), ('sourceRevision', 'f'*40),
                           ('artifactSha256', 'f'*64), ('normalizedInputsSha256', 'f'*64)]:
            original = receipt[key]
            receipt[key] = value
            build_fixture.AndroidEvidence().update(self.build)
            self.assertEqual(self.invoke().returncode, 2)
            receipt[key] = original
        build_fixture.AndroidEvidence().update(self.build)
        index = self.command.index('--expected-artifact-sha256') + 1
        self.command[index] = 'f'*64
        self.assertEqual(self.invoke().returncode, 2)

    def test_named_check_cannot_be_replaced_with_generic_pass_count(self):
        for tier, names in build_fixture.MODULE.mandatory_checks('pico4').items():
            checks = self.build['receipts'][tier]['checks']
            for name in names:
                value = checks.pop(name)
                build_fixture.AndroidEvidence().update(self.build)
                self.assertEqual(self.invoke().returncode, 2)
                checks[name] = value
        build_fixture.AndroidEvidence().update(self.build)
        self.assertEqual(self.invoke().returncode, 0)

    def test_wrong_product_version_claim_inputs_and_foreign_evidence(self):
        original = copy.deepcopy(self.record)
        for key,value in [('product','android-phone'),('channel','source-proof'),('versionCode',8),
                          ('sourceRevision','f'*40),('signature',dict(state='verified',receiptSha256='d'*64))]:
            with self.subTest(key=key):
                self.record = copy.deepcopy(original); self.record[key] = value
                result = self.invoke(); self.assertEqual(result.returncode, 2)
                self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.record = original
        self.assertEqual(self.invoke(('--minimum-version','7')).returncode, 2)
        self.assertEqual(self.invoke(('--cyclonedx', str(self.files['spdx']))).returncode, 2)
        self.files['spdx'].write_text('private-fixture')
        result = self.invoke(); self.assertEqual(result.returncode, 2)
        self.assertNotIn('private-fixture', result.stdout + result.stderr)
        self.input_file.write_text(json.dumps(dict(self.inputs, toolchain='d'*64)))
        self.assertEqual(self.invoke().returncode, 2)
if __name__ == '__main__': unittest.main(verbosity=2)
