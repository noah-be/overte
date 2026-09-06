"""Pico-native binding of the original SH-009 identity validator."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'provenance'))
from artifact_identity import EVIDENCE_KEYS, read_record, require, validate

def validate_candidate_identity(args, metadata):
    record = read_record(args.identity_record)
    require(record.get('product') == 'pico4' and record.get('channel') == 'internal-candidate', 'PICO_CANDIDATE_PRODUCT')
    require(record.get('versionCode') == int(metadata['version_code']), 'PICO_PACKAGE_VERSION')
    evidence = {key: getattr(args, key) for key in EVIDENCE_KEYS}
    # A single document cannot stand in for all distinct required inventories.
    require(len({Path(path).resolve() for path in evidence.values()}) == len(EVIDENCE_KEYS), 'PICO_DISTINCT_EVIDENCE')
    return validate(record, args.apk, evidence, args.source_revision,
                    read_record(args.expected_inputs), args.minimum_version)
