import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location('android_build_evidence', HERE / 'android_build_evidence.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AndroidEvidence(unittest.TestCase):
    def fixture(self, root, product='android-phone'):
        root.mkdir(exist_ok=True)
        artifact = root / 'fixture.apk'
        artifact.write_bytes(b'NOT AN APK - test-only artifact bytes')
        artifact_sha = MODULE.identity.digest_file(artifact)
        source = 'a' * 40
        inputs = {key: hashlib.sha256(key.encode()).hexdigest() for key in MODULE.identity.INPUT_KEYS}
        inputs_path = root / 'inputs.json'
        write(inputs_path, inputs)
        normalized = MODULE.identity.normalized_inputs(inputs)
        files = {}
        for key in MODULE.identity.EVIDENCE_KEYS:
            files[key] = root / (key + '.json')
            write(files[key], {'test-only': key})
        record = {'contract': 'overte-sh009-identity-v1', 'sourceRevision': source,
                  'product': product, 'versionCode': 2, 'channel': 'internal-candidate',
                  'artifactSha256': artifact_sha, 'inputs': inputs, 'normalizedInputsSha256': normalized,
                  'evidence': {key: MODULE.identity.digest_file(path) for key, path in files.items()},
                  'signature': {'state': 'pending', 'receiptSha256': None},
                  'upgrade': {'state': 'pending', 'receiptSha256': None}}
        record_path = root / 'identity.json'
        record_sha = write(record_path, record)
        evidence = {'contract': 'overte-sh002-android-build-evidence-v1', 'product': product,
                    'identityRecordSha256': record_sha, 'sourceRevision': source,
                    'artifactSha256': artifact_sha, 'normalizedInputsSha256': normalized,
                    'toolchainSha256': inputs['toolchain'], 'receipts': []}
        receipts = {}
        for tier, names in MODULE.mandatory_checks(product).items():
            receipt = {'contract': 'overte-sh002-android-tier-v1', 'tier': tier, 'product': product,
                       'sourceRevision': source, 'artifactSha256': artifact_sha,
                       'normalizedInputsSha256': normalized, 'status': 'PASS',
                       'checks': {name: {'status': 'PASS', 'executed': 1, 'failures': 0,
                                         'errors': 0, 'skipped': 0} for name in names}, 'provenance': {}}
            if tier in ('cold-full-client-build', 'warm-full-client-build'):
                receipt['provenance'] = {'network': 'none', 'initialCache': 'empty' if tier.startswith('cold') else 'same-source',
                                         'foreignBinaryInputs': False, 'toolchainSha256': inputs['toolchain'],
                                         'normalizedInputsSha256': normalized}
            path = root / (tier + '.json')
            receipts[tier] = receipt
            evidence['receipts'].append({'tier': tier, 'path': path.name, 'sha256': write(path, receipt)})
        evidence_path = root / 'build-evidence.json'
        write(evidence_path, evidence)
        return {'args': (evidence_path, record_path, artifact, inputs_path, source, artifact_sha, product),
                'evidence': evidence, 'receipts': receipts, 'record': record, 'inputs': inputs, 'files': files}

    def update(self, fixture):
        root = fixture['args'][0].parent
        for entry in fixture['evidence']['receipts']:
            entry['sha256'] = write(root / entry['path'], fixture['receipts'][entry['tier']])
        write(fixture['args'][0], fixture['evidence'])

    def test_both_products_join_original_identity_without_acceptance_upgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            for product in MODULE.PRODUCT_CHECKS:
                fixture = self.fixture(Path(temporary) / product, product)
                old = MODULE.identity.validate(fixture['record'], fixture['args'][2], fixture['files'],
                                               fixture['args'][4], fixture['inputs'], 1)
                self.assertEqual(old['status'], 'ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING')
                result = MODULE.validate(*fixture['args'])
                self.assertEqual(result['status'], 'MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING')

    def test_every_missing_tier_and_check_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for product in MODULE.PRODUCT_CHECKS:
                for tier, checks in MODULE.mandatory_checks(product).items():
                    fixture = self.fixture(Path(temporary) / (product + tier), product)
                    fixture['evidence']['receipts'] = [item for item in fixture['evidence']['receipts'] if item['tier'] != tier]
                    self.update(fixture)
                    with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])
                    for check in checks:
                        fixture = self.fixture(Path(temporary) / (product + tier + check), product)
                        del fixture['receipts'][tier]['checks'][check]
                        self.update(fixture)
                        with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_skip_failure_boolean_and_empty_count_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for key, value in [('status', 'SKIP'), ('executed', 0), ('executed', True),
                               ('failures', 1), ('errors', 1), ('skipped', 1), ('skipped', False)]:
                fixture = self.fixture(Path(temporary) / (key + str(value)))
                fixture['receipts']['host-contracts']['checks']['source-locks'][key] = value
                self.update(fixture)
                with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_contamination_wrong_input_source_artifact_and_product_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            mutations = [('provenance', 'network', 'online'), ('provenance', 'initialCache', 'foreign'),
                         ('provenance', 'foreignBinaryInputs', True), ('provenance', 'toolchainSha256', '0' * 64),
                         ('receipt', 'sourceRevision', 'b' * 40), ('receipt', 'artifactSha256', 'b' * 64),
                         ('receipt', 'product', 'pico4'), ('receipt', 'normalizedInputsSha256', 'b' * 64)]
            for number, (scope, key, value) in enumerate(mutations):
                fixture = self.fixture(Path(temporary) / str(number))
                receipt = fixture['receipts']['cold-full-client-build']
                (receipt['provenance'] if scope == 'provenance' else receipt)[key] = value
                self.update(fixture)
                with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_symlink_hardlink_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for kind in ('symlink', 'hardlink', 'traversal'):
                fixture = self.fixture(root / kind)
                entry = fixture['evidence']['receipts'][0]
                path = fixture['args'][0].parent / entry['path']
                if kind == 'traversal':
                    entry['path'] = '../foreign.json'
                else:
                    path.unlink()
                    if kind == 'symlink': path.symlink_to(fixture['args'][1])
                    else: os.link(fixture['args'][1], path)
                    entry['sha256'] = MODULE.identity.digest_file(fixture['args'][1])
                write(fixture['args'][0], fixture['evidence'])
                with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_changed_record_or_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for kind in ('record', 'artifact'):
                fixture = self.fixture(Path(temporary) / kind)
                if kind == 'record':
                    fixture['record']['versionCode'] = 3
                    write(fixture['args'][1], fixture['record'])
                else:
                    fixture['args'][2].write_bytes(b'changed')
                with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_duplicate_tier_nonpass_scanner_and_forged_input_digest_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for kind in ('duplicate-tier', 'scanner-error', 'forged-inputs'):
                fixture = self.fixture(Path(temporary) / kind)
                if kind == 'duplicate-tier':
                    fixture['evidence']['receipts'][-1] = dict(fixture['evidence']['receipts'][0])
                elif kind == 'scanner-error':
                    fixture['receipts']['fdroid-source-scanner']['status'] = 'ERROR'
                else:
                    fixture['evidence']['normalizedInputsSha256'] = 'b' * 64
                self.update(fixture)
                with self.assertRaises(MODULE.EvidenceError): MODULE.validate(*fixture['args'])

    def test_actual_shared_shell_entrypoint_and_closed_argument_errors(self):
        entry = ROOT / 'android/phone/fdroid/scripts/verify-source-only.sh'
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(Path(temporary))
            values = fixture['args']
            flags = ('--build-evidence', '--identity-record', '--artifact', '--expected-inputs',
                     '--expected-source-sha', '--expected-artifact-sha256', '--product')
            command = ['bash', str(entry)] + [value for pair in zip(flags, map(str, values)) for value in pair]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PRODUCER_VERIFICATION_PENDING', result.stdout)
            result = subprocess.run(command + ['--unknown', 'fixture-secret'], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, 'OVT_ANDROID_BUILD_EVIDENCE_ARGUMENTS_REJECTED\n')
            self.assertNotIn('fixture-secret', result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
