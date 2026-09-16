"""Focused producer/consumer and corruption fixtures for SH-002 v1."""
# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import terminal_evidence as evidence

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / 'ios/ci/evidence/verify-shared-evidence.py'
SOURCE, ARTIFACT = 'a' * 40, 'b' * 64


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate.json'
        candidate = {'contract': 'overte-ios-io001-candidate-v1',
                     'source': {'revision': SOURCE}, 'artifact': {'sha256': ARTIFACT}}
        self.candidate.write_text(json.dumps(candidate))
        self.manifest = {'contract': 'overte-sh002-ios-evidence-v1',
                         'candidateSha256': evidence.digest(self.candidate.read_bytes()),
                         'sourceRevision': SOURCE, 'artifactSha256': ARTIFACT,
                         'toolchainSha256': 'c' * 64, 'normalizedInputsSha256': 'd' * 64,
                         'receipts': []}
        self.receipts = {}
        for tier in evidence.TIERS:
            provenance = {}
            if tier in ('cold-full-client-build', 'warm-full-client-build'):
                provenance = {'network': 'none', 'initialCache': 'empty' if tier.startswith('cold') else 'same-source',
                              'foreignBinaryInputs': False, 'toolchainSha256': 'c' * 64,
                              'normalizedInputsSha256': 'd' * 64}
            self.receipts[tier] = {'contract': 'overte-sh002-receipt-v1', 'tier': tier,
                                   'sourceRevision': SOURCE, 'artifactSha256': ARTIFACT,
                                   'status': 'PASS', 'checks': 1, 'failures': 0, 'errors': 0,
                                   'skipped': 0, 'provenance': provenance}
        self.publish()

    def publish(self):
        self.manifest['receipts'] = []
        for tier, receipt in self.receipts.items():
            raw = json.dumps(receipt).encode()
            name = tier + '.json'
            (self.root / name).write_bytes(raw)
            self.manifest['receipts'].append({'tier': tier, 'path': name, 'sha256': evidence.digest(raw)})
        self.sidecar = self.candidate.with_name(self.candidate.name + '.shared-evidence.json')
        self.sidecar.write_text(json.dumps(self.manifest))

    def verify(self):
        return evidence.validate(self.candidate, SOURCE, ARTIFACT)

    def test_positive_cli(self):
        result = subprocess.run([str(ADAPTER), '--candidate-metadata', str(self.candidate),
                                 '--expected-source-sha', SOURCE, '--expected-artifact-sha256', ARTIFACT],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'BOUND')

    def test_missing_sidecar_fails(self):
        self.sidecar.unlink()
        with self.assertRaisesRegex(evidence.EvidenceError, 'MISSING_REGULAR'):
            self.verify()

    def test_independently_frozen_inputs_cli(self):
        base = [str(ADAPTER), '--candidate-metadata', str(self.candidate),
                '--expected-source-sha', SOURCE, '--expected-artifact-sha256', ARTIFACT]
        for inputs, toolchain, code in [('d' * 64, 'c' * 64, 0),
                                        ('e' * 64, 'c' * 64, 1),
                                        ('d' * 64, 'e' * 64, 1),
                                        ('invalid', 'c' * 64, 1)]:
            with self.subTest(inputs=inputs, toolchain=toolchain):
                result = subprocess.run(base + ['--expected-normalized-inputs-sha256', inputs,
                                               '--expected-toolchain-sha256', toolchain],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stderr)
                if code == 0:
                    value = json.loads(result.stdout)
                    self.assertEqual(value['normalizedInputsSha256'], inputs)
                    self.assertEqual(value['toolchainSha256'], toolchain)

    def test_coherent_foreign_cohort_is_not_independent_evidence(self):
        self.manifest['normalizedInputsSha256'] = 'e' * 64
        for receipt in self.receipts.values():
            if receipt['provenance']:
                receipt['provenance']['normalizedInputsSha256'] = 'e' * 64
        self.publish()
        self.assertEqual(self.verify()['normalizedInputsSha256'], 'e' * 64)
        with self.assertRaisesRegex(evidence.EvidenceError, 'EXPECTED_BUILD_INPUT_MISMATCH'):
            evidence.validate(self.candidate, SOURCE, ARTIFACT,
                              expected_normalized_inputs_sha256='d' * 64,
                              expected_toolchain_sha256='c' * 64)

    def test_semantic_negative_matrix(self):
        original = copy.deepcopy(self.receipts)
        changes = [('sourceRevision', 'e' * 40), ('artifactSha256', 'e' * 64),
                   ('status', 'SKIP'), ('failures', 1), ('errors', 1), ('skipped', 1),
                   ('checks', 0), ('checks', True)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.receipts = copy.deepcopy(original)
                self.receipts['host-contracts'][key] = value
                self.publish()
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_build_contamination_matrix(self):
        original = copy.deepcopy(self.receipts)
        for key, value in [('network', 'enabled'), ('initialCache', 'global'),
                           ('foreignBinaryInputs', True), ('toolchainSha256', 'e' * 64),
                           ('normalizedInputsSha256', 'e' * 64)]:
            with self.subTest(key=key):
                self.receipts = copy.deepcopy(original)
                self.receipts['cold-full-client-build']['provenance'][key] = value
                self.publish()
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_missing_tier(self):
        del self.receipts['package-verification']
        self.publish()
        with self.assertRaisesRegex(evidence.EvidenceError, 'MISSING_MANDATORY_TIER'):
            self.verify()

    def test_byte_tampering(self):
        (self.root / 'host-contracts.json').write_text('{}')
        with self.assertRaisesRegex(evidence.EvidenceError, 'RECEIPT_BYTES_MISMATCH'):
            self.verify()

    def test_candidate_tampering(self):
        self.candidate.write_text(self.candidate.read_text() + '\n')
        with self.assertRaisesRegex(evidence.EvidenceError, 'CANDIDATE_BYTES_MISMATCH'):
            self.verify()

    def test_traversal(self):
        self.manifest['receipts'][0]['path'] = '../private'
        self.sidecar.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(evidence.EvidenceError, 'UNSAFE_EVIDENCE_PATH'):
            self.verify()

    def test_duplicate_json(self):
        self.sidecar.write_text('{"contract":1,"contract":2}')
        with self.assertRaisesRegex(evidence.EvidenceError, 'DUPLICATE_KEY'):
            self.verify()

    def test_symlink(self):
        path = self.root / 'host-contracts.json'
        path.rename(self.root / 'other.json')
        path.symlink_to('other.json')
        with self.assertRaisesRegex(evidence.EvidenceError, 'MISSING_REGULAR'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
