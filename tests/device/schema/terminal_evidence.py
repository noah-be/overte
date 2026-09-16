"""SH-002 v1: validate content-bound terminal evidence for IO-001.

Receipts are producer observations, not attestations of producer trust. Acceptance
must also authenticate the producer and its source/build execution separately.
"""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import re
from pathlib import Path

TIERS = ('host-contracts', 'cold-full-client-build', 'warm-full-client-build',
         'package-verification')
MAX_BYTES = 262144


class EvidenceError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'DUPLICATE_KEY')
        result[key] = value
    return result


def read_document(path):
    require(not path.is_symlink() and path.is_file(), 'MISSING_REGULAR_EVIDENCE')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, 'EVIDENCE_SIZE')
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError('NONFINITE_JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise EvidenceError('INVALID_JSON') from error
    require(type(value) is dict, 'OBJECT_REQUIRED')
    return value, raw


def fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'FIELD_SET')


def hex_value(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def relative_file(root, value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value)
            is not None and value not in ('.', '..'), 'UNSAFE_EVIDENCE_PATH')
    return root / value


def validate(candidate_path, source_sha, artifact_sha256, *,
             expected_normalized_inputs_sha256=None, expected_toolchain_sha256=None):
    require(hex_value(source_sha, 40) and hex_value(artifact_sha256, 64), 'INVALID_EXPECTED_IDENTITY')
    expected_inputs = {'normalizedInputsSha256': expected_normalized_inputs_sha256,
                       'toolchainSha256': expected_toolchain_sha256}
    for value in expected_inputs.values():
        require(value is None or hex_value(value, 64), 'INVALID_EXPECTED_INPUT_IDENTITY')
    candidate_path = Path(candidate_path)
    candidate, candidate_raw = read_document(candidate_path)
    require(candidate.get('contract') == 'overte-ios-io001-candidate-v1', 'CANDIDATE_CONTRACT')
    require(candidate.get('source') == {'revision': source_sha}, 'STALE_SOURCE')
    require(type(candidate.get('artifact')) is dict
            and candidate['artifact'].get('sha256') == artifact_sha256, 'WRONG_ARTIFACT')
    evidence_path = candidate_path.with_name(candidate_path.name + '.shared-evidence.json')
    evidence, _ = read_document(evidence_path)
    fields(evidence, ('contract', 'candidateSha256', 'sourceRevision', 'artifactSha256',
                      'toolchainSha256', 'normalizedInputsSha256', 'receipts'))
    require(evidence['contract'] == 'overte-sh002-ios-evidence-v1', 'EVIDENCE_CONTRACT')
    require(evidence['sourceRevision'] == source_sha, 'STALE_SOURCE')
    require(evidence['artifactSha256'] == artifact_sha256, 'WRONG_ARTIFACT')
    require(evidence['candidateSha256'] == digest(candidate_raw), 'CANDIDATE_BYTES_MISMATCH')
    for key in ('toolchainSha256', 'normalizedInputsSha256'):
        require(hex_value(evidence[key], 64), 'INVALID_INPUT_IDENTITY')
        require(expected_inputs[key] is None or evidence[key] == expected_inputs[key],
                'EXPECTED_BUILD_INPUT_MISMATCH')
    receipts = evidence['receipts']
    require(type(receipts) is list and len(receipts) == len(TIERS), 'MISSING_MANDATORY_TIER')
    seen, paths = set(), set()
    for entry in receipts:
        fields(entry, ('tier', 'path', 'sha256'))
        tier = entry['tier']
        require(type(tier) is str and tier in TIERS and tier not in seen, 'TIER_SET')
        seen.add(tier)
        path = relative_file(candidate_path.parent, entry['path'])
        require(path.name not in paths and path not in (candidate_path, evidence_path), 'REUSED_RECEIPT')
        paths.add(path.name)
        receipt, raw = read_document(path)
        require(hex_value(entry['sha256'], 64) and digest(raw) == entry['sha256'], 'RECEIPT_BYTES_MISMATCH')
        fields(receipt, ('contract', 'tier', 'sourceRevision', 'artifactSha256', 'status',
                        'checks', 'failures', 'errors', 'skipped', 'provenance'))
        require(receipt['contract'] == 'overte-sh002-receipt-v1' and receipt['tier'] == tier, 'RECEIPT_CONTRACT')
        require(receipt['sourceRevision'] == source_sha, 'STALE_SOURCE')
        require(receipt['artifactSha256'] == artifact_sha256, 'WRONG_ARTIFACT')
        require(receipt['status'] == 'PASS', 'NONPASS_TIER')
        require(type(receipt['checks']) is int and receipt['checks'] > 0, 'NO_CHECKS')
        for key in ('failures', 'errors', 'skipped'):
            require(type(receipt[key]) is int and receipt[key] == 0, 'FAILED_OR_SKIPPED_CHECK')
        provenance = receipt['provenance']
        if tier in ('cold-full-client-build', 'warm-full-client-build'):
            fields(provenance, ('network', 'initialCache', 'foreignBinaryInputs',
                                'toolchainSha256', 'normalizedInputsSha256'))
            require(provenance['network'] == 'none', 'NETWORK_CONTAMINATION')
            require(provenance['initialCache'] == ('empty' if tier.startswith('cold') else 'same-source'),
                    'CACHE_CONTAMINATION')
            require(provenance['foreignBinaryInputs'] is False, 'FOREIGN_BINARY_INPUT')
            for key in ('toolchainSha256', 'normalizedInputsSha256'):
                require(provenance[key] == evidence[key], 'BUILD_INPUT_MISMATCH')
        else:
            require(provenance == {}, 'UNEXPECTED_PROVENANCE')
    require(seen == set(TIERS), 'MISSING_MANDATORY_TIER')
    return {'contract': evidence['contract'], 'status': 'BOUND',
            'sourceRevision': source_sha, 'artifactSha256': artifact_sha256,
            'normalizedInputsSha256': evidence['normalizedInputsSha256'],
            'toolchainSha256': evidence['toolchainSha256']}
