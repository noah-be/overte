#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'provenance'))
from artifact_identity import IdentityError
from sbom_validation import read_sbom, validate_pair


def main():
    parser = argparse.ArgumentParser(description='Offline SPDX2.3/CycloneDX1.6 pair, not binary/source completeness proof')
    parser.add_argument('--spdx', required=True)
    parser.add_argument('--cyclonedx', required=True)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    args = parser.parse_args()
    try:
        result = validate_pair(read_sbom(args.spdx), read_sbom(args.cyclonedx),
                               args.expected_source_sha, args.expected_artifact_sha256)
    except IdentityError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('SBOM_INPUT_INVALID', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
