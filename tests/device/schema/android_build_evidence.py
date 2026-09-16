"""SH-002 Android mandatory-tier byte binding, not authenticated build proof."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminal_evidence import (EvidenceError, digest, fields, hex_value,
                               read_document, relative_file, require)

spec = importlib.util.spec_from_file_location('sh002_artifact_identity', ROOT / 'provenance/artifact_identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)

# Closed, versioned mandatory tiers. Native owners map actual producer outcomes
# to these IDs; an arbitrary positive test count cannot stand in for this set.
COMMON = {
    'host-contracts': ('source-locks', 'protected-storage', 'redaction', 'native-adapter'),
    'cold-full-client-build': ('empty-binary-cache', 'network-isolation', 'full-client-output'),
    'warm-full-client-build': ('same-effective-inputs', 'same-source-cache', 'full-client-output'),
    'source-license-closure': ('source-archive-digests', 'recipe-revisions', 'license-closure'),
    'package-verification': ('apk-structure', 'arm64-abi', 'sdk-policy', 'permissions', 'no-legacy-openssl'),
}
PRODUCT_CHECKS = {
    'android-phone': {
        'fdroid-source-scanner': ('official-source-scan', 'no-binary-inputs', 'no-undeclared-exceptions'),
        'elf-loader-verification': ('elf-16k-alignment', 'soname-closure', 'api26-symbols'),
    },
    'pico4': {
        'source-graph-compatibility': ('qt-runtime-patches', 'openssl3-loader-mapping', 'host-target-isolation'),
        'pico-package-verification': ('signature-verification', 'openxr-manifest', 'debug-layer-policy'),
    },
}


def mandatory_checks(product):
    require(product in PRODUCT_CHECKS, 'ANDROID_PRODUCT')
    return dict(COMMON, **PRODUCT_CHECKS[product])


def validate(evidence_path, identity_record_path, artifact, expected_inputs_path,
             source_sha, artifact_sha256, product):
    """Join independently expected identity to mandatory, digest-bound receipts.

    Native callers STILL run their original SH-009 and package/signature verifier.
    This validates the join and tier structure, never elevates producer trust.
    """
    checks = mandatory_checks(product)
    require(hex_value(source_sha, 40) and hex_value(artifact_sha256, 64), 'INVALID_EXPECTED_IDENTITY')
    paths = [Path(evidence_path), Path(identity_record_path), Path(artifact), Path(expected_inputs_path)]
    seen_files = set()
    def distinct(path):
        require(path.is_file() and not path.is_symlink(), 'MISSING_REGULAR_EVIDENCE')
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino)
        require(key not in seen_files, 'REUSED_EVIDENCE_FILE')
        seen_files.add(key)
    for path in paths:
        distinct(path)
    evidence_path, record_path, artifact_path, inputs_path = paths
    record, record_raw = read_document(record_path)
    inputs, inputs_raw = read_document(inputs_path)
    normalized = identity.normalized_inputs(inputs)
    require(record.get('contract') == 'overte-sh009-identity-v1', 'IDENTITY_CONTRACT')
    require(record.get('sourceRevision') == source_sha, 'STALE_SOURCE')
    require(record.get('product') == product, 'ANDROID_PRODUCT')
    require(record.get('artifactSha256') == artifact_sha256 and
            identity.digest_file(artifact_path) == artifact_sha256, 'WRONG_ARTIFACT')
    require(record.get('inputs') == inputs and record.get('normalizedInputsSha256') == normalized,
            'EXPECTED_BUILD_INPUT_MISMATCH')
    evidence, evidence_raw = read_document(evidence_path)
    fields(evidence, ('contract', 'product', 'identityRecordSha256', 'sourceRevision',
                      'artifactSha256', 'normalizedInputsSha256', 'toolchainSha256', 'receipts'))
    require(evidence['contract'] == 'overte-sh002-android-build-evidence-v1', 'EVIDENCE_CONTRACT')
    require(evidence['product'] == product, 'ANDROID_PRODUCT')
    require(evidence['identityRecordSha256'] == digest(record_raw), 'CANDIDATE_BYTES_MISMATCH')
    require(evidence['sourceRevision'] == source_sha, 'STALE_SOURCE')
    require(evidence['artifactSha256'] == artifact_sha256, 'WRONG_ARTIFACT')
    require(evidence['normalizedInputsSha256'] == normalized and
            evidence['toolchainSha256'] == inputs['toolchain'], 'EXPECTED_BUILD_INPUT_MISMATCH')
    entries = evidence['receipts']
    require(type(entries) is list and len(entries) == len(checks), 'MISSING_MANDATORY_TIER')
    seen_tiers, snapshots = set(), []
    for entry in entries:
        fields(entry, ('tier', 'path', 'sha256'))
        tier = entry['tier']
        require(type(tier) is str and tier in checks and tier not in seen_tiers, 'TIER_SET')
        seen_tiers.add(tier)
        path = relative_file(evidence_path.parent, entry['path'])
        distinct(path)
        receipt, raw = read_document(path)
        require(hex_value(entry['sha256'], 64) and digest(raw) == entry['sha256'], 'RECEIPT_BYTES_MISMATCH')
        snapshots.append((path, raw))
        fields(receipt, ('contract', 'tier', 'product', 'sourceRevision', 'artifactSha256',
                         'normalizedInputsSha256', 'status', 'checks', 'provenance'))
        require(receipt['contract'] == 'overte-sh002-android-tier-v1' and receipt['tier'] == tier,
                'RECEIPT_CONTRACT')
        require(receipt['product'] == product, 'ANDROID_PRODUCT')
        require(receipt['sourceRevision'] == source_sha, 'STALE_SOURCE')
        require(receipt['artifactSha256'] == artifact_sha256, 'WRONG_ARTIFACT')
        require(receipt['normalizedInputsSha256'] == normalized, 'BUILD_INPUT_MISMATCH')
        require(receipt['status'] == 'PASS', 'NONPASS_TIER')
        outcomes = receipt['checks']
        fields(outcomes, checks[tier])
        for outcome in outcomes.values():
            fields(outcome, ('status', 'executed', 'failures', 'errors', 'skipped'))
            require(outcome['status'] == 'PASS' and type(outcome['executed']) is int and
                    outcome['executed'] > 0, 'NO_EXECUTED_CHECK')
            for key in ('failures', 'errors', 'skipped'):
                require(type(outcome[key]) is int and outcome[key] == 0, 'FAILED_OR_SKIPPED_CHECK')
        provenance = receipt['provenance']
        if tier in ('cold-full-client-build', 'warm-full-client-build'):
            fields(provenance, ('network', 'initialCache', 'foreignBinaryInputs',
                                'toolchainSha256', 'normalizedInputsSha256'))
            require(provenance['network'] == 'none', 'NETWORK_CONTAMINATION')
            require(provenance['initialCache'] == ('empty' if tier.startswith('cold') else 'same-source'),
                    'CACHE_CONTAMINATION')
            require(provenance['foreignBinaryInputs'] is False, 'FOREIGN_BINARY_INPUT')
            require(provenance['toolchainSha256'] == inputs['toolchain'] and
                    provenance['normalizedInputsSha256'] == normalized, 'BUILD_INPUT_MISMATCH')
        else:
            require(provenance == {}, 'UNEXPECTED_PROVENANCE')
    require(seen_tiers == set(checks), 'MISSING_MANDATORY_TIER')
    # Recheck bytes at the completion boundary. This is bounded file consistency,
    # not an adversarial filesystem snapshot or authenticated producer receipt.
    for path, raw in [(record_path, record_raw), (inputs_path, inputs_raw),
                      (evidence_path, evidence_raw), *snapshots]:
        require(read_document(path)[1] == raw, 'EVIDENCE_CHANGED')
    require(identity.digest_file(artifact_path) == artifact_sha256, 'ARTIFACT_CHANGED')
    return {'contract': evidence['contract'], 'product': product,
            'status': 'MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING',
            'sourceRevision': source_sha, 'artifactSha256': artifact_sha256,
            'normalizedInputsSha256': normalized}


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'OVT_ANDROID_BUILD_EVIDENCE_ARGUMENTS_REJECTED\n')


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    for option in ('build-evidence', 'identity-record', 'artifact', 'expected-inputs'):
        parser.add_argument('--' + option, required=True, type=Path)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    parser.add_argument('--product', required=True, choices=tuple(PRODUCT_CHECKS))
    values = list(sys.argv[1:] if argv is None else argv)
    options = [value.split('=', 1)[0] for value in values if value.startswith('--')]
    if len(options) != len(set(options)):
        parser.error('duplicate option')
    args = parser.parse_args(values)
    try:
        result = validate(args.build_evidence, args.identity_record, args.artifact,
                          args.expected_inputs, args.expected_source_sha,
                          args.expected_artifact_sha256, args.product)
    except (EvidenceError, identity.IdentityError, OSError, ValueError, TypeError, KeyError, RecursionError):
        print('OVT_ANDROID_BUILD_EVIDENCE_REJECTED', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
