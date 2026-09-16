"""SH-009 channel-neutral byte/input binding, not package/signature acceptance."""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import re

class IdentityError(ValueError):
    pass

def require(ok, code):
    if not ok:
        raise IdentityError(code)

def hex_digest(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None

def fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'IDENTITY_FIELDS')

def digest_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'MISSING_REGULAR_INPUT')
    size = path.stat().st_size
    require(0 < size <= 4 * 1024**3, 'INPUT_SIZE')
    value = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            value.update(chunk)
            count += len(chunk)
            require(count <= size, 'INPUT_CHANGED')
    require(count == size and path.stat().st_size == size, 'INPUT_CHANGED')
    return value.hexdigest()

INPUT_KEYS = ('sourceTree', 'sourceClosure', 'recipes', 'bootstrapLock', 'hostLock',
              'targetLock', 'toolchain', 'buildParameters')
EVIDENCE_KEYS = ('bootstrapPackages', 'hostPackages', 'targetPackages', 'generatedOutputs',
                 'spdx', 'cyclonedx')

def normalized_inputs(value):
    fields(value, INPUT_KEYS)
    require(all(hex_digest(item) for item in value.values()), 'INPUT_DIGEST')
    # Exact labels+digests only. No paths, times or private build environment.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def validate(record, artifact, evidence_files, expected_source, expected_inputs, minimum_version=0):
    fields(record, ('contract', 'sourceRevision', 'product', 'versionCode', 'channel', 'artifactSha256',
                    'inputs', 'normalizedInputsSha256', 'evidence', 'signature', 'upgrade'))
    require(record['contract'] == 'overte-sh009-identity-v1', 'IDENTITY_CONTRACT')
    require(hex_digest(expected_source,40) and record['sourceRevision'] == expected_source, 'STALE_SOURCE')
    require(record['product'] in ('android-phone','pico4','ios'), 'PRODUCT')
    require(type(minimum_version) is int and minimum_version >= 0, 'MINIMUM_VERSION')
    require(type(record['versionCode']) is int and record['versionCode'] > minimum_version, 'ROLLBACK_OR_VERSION')
    require(record['channel'] in ('source-proof','internal-candidate','fdroid-candidate'), 'CHANNEL')
    require(hex_digest(record['artifactSha256']) and digest_file(artifact) == record['artifactSha256'], 'ARTIFACT_BYTES')
    expected_normalized = normalized_inputs(expected_inputs)
    require(record['inputs'] == expected_inputs and normalized_inputs(record['inputs']) == expected_normalized
            and record['normalizedInputsSha256'] == expected_normalized, 'BUILD_INPUT_MISMATCH')
    fields(record['evidence'], EVIDENCE_KEYS)
    fields(evidence_files, EVIDENCE_KEYS)
    for key in EVIDENCE_KEYS:
        require(hex_digest(record['evidence'][key]) and digest_file(evidence_files[key]) == record['evidence'][key], 'EVIDENCE_BYTES')
    fields(record['signature'], ('state','receiptSha256'))
    fields(record['upgrade'], ('state','receiptSha256'))
    # No trust is invented from a producer's boolean. Platform signature and
    # upgrade acceptance remain external authenticated verifiers in this slice.
    for value in (record['signature'], record['upgrade']):
        require(value['state'] in ('pending','not-applicable-source-proof'), 'UNVERIFIED_ACCEPTANCE_CLAIM')
        require(value['receiptSha256'] is None, 'UNVERIFIED_RECEIPT')
        if value['state'] == 'not-applicable-source-proof':
            require(record['channel'] == 'source-proof', 'WRONG_CHANNEL_EXEMPTION')
    return {'contract':'overte-sh009-identity-v1','status':'ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING',
            'sourceRevision':expected_source,'artifactSha256':record['artifactSha256'],
            'normalizedInputsSha256':expected_normalized}

def read_record(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'MISSING_RECORD')
    with path.open('rb') as stream:
        data = stream.read(262145)
    require(0 < len(data) <= 262144, 'RECORD_SIZE')
    def pairs(items):
        result = {}
        for key,value in items:
            require(key not in result, 'DUPLICATE_KEY')
            result[key]=value
        return result
    try:
        result=json.loads(data,object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(IdentityError('NONFINITE_JSON')))
    except (ValueError,UnicodeError,RecursionError) as error:
        raise IdentityError('INVALID_JSON') from error
    require(type(result) is dict,'RECORD_OBJECT')
    return result
