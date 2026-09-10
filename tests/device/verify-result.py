#!/usr/bin/env python3
"""Offline SH-004 acceptance consumer for existing runner outputs; no device use."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'schema'))
from result_binding import validate
from terminal_evidence import EvidenceError

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', required=True, type=Path)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    parser.add_argument('--expected-adapter', required=True)
    parser.add_argument('--expected-platform', required=True, choices=('android', 'ios', 'pico4'))
    parser.add_argument('--required-module', required=True, action='append')
    parser.add_argument('--device-class', required=True, choices=('physical', 'virtual'))
    args = parser.parse_args()
    try:
        result = validate(args.result_dir, args.expected_source_sha, args.expected_artifact_sha256,
                          args.expected_adapter, args.expected_platform, args.required_module, args.device_class == 'physical')
    except (EvidenceError, OSError, TypeError, KeyError, ValueError):
        print('RESULT_REJECTED', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
