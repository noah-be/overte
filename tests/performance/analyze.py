#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate a frozen SH-008 trace; no device execution or acceptance promotion."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'schema'))
from metrics import MetricsError, validate

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--expected-fixture-sha256', required=True)
    parser.add_argument('--budget', type=Path)
    parser.add_argument('--expected-budget-sha256')
    args = parser.parse_args()
    try:
        result = validate(args.trace, args.expected_source_sha, args.expected_artifact_sha256,
                          args.platform, args.expected_fixture_sha256, args.budget, args.expected_budget_sha256)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(str(error) if isinstance(error, MetricsError) else 'METRICS_IO_OR_FORMAT', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == '__main__': raise SystemExit(main())
