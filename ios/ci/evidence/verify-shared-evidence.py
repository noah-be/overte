#!/usr/bin/env python3
"""Executable Shared adapter for the existing iOS candidate verifier seam."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import importlib.util
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('overte_terminal_evidence',
                                             root / 'tests/device/schema/terminal_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-metadata', type=Path, required=True)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    parser.add_argument('--expected-normalized-inputs-sha256')
    parser.add_argument('--expected-toolchain-sha256')
    args = parser.parse_args()
    try:
        result = module.validate(args.candidate_metadata, args.expected_source_sha,
                                 args.expected_artifact_sha256,
                                 expected_normalized_inputs_sha256=args.expected_normalized_inputs_sha256,
                                 expected_toolchain_sha256=args.expected_toolchain_sha256)
    except (module.EvidenceError, OSError, ValueError, TypeError) as error:
        code = str(error) if isinstance(error, module.EvidenceError) else 'EVIDENCE_IO_OR_FORMAT'
        print('shared-evidence: ' + code, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
