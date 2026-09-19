#!/usr/bin/env python3
"""Offline Pico consumer of pinned SH-004; never discovers or contacts a device."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
from pathlib import Path
import sys

DEVICE_ROOT = Path(__file__).resolve().parents[2]

class ClosedParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid arguments')

def verify(result_dir, source_sha, artifact_sha, required_modules):
    sys.path.insert(0, str(DEVICE_ROOT / 'schema'))
    from result_binding import validate
    from terminal_evidence import read_document, require
    manifest, _ = read_document(DEVICE_ROOT / 'adapters/android/pico-bound.json')
    require(manifest == {'schemaVersion': 1, 'id': 'android-pico-adb',
                         'command': ['adapter.py', '--kind', 'pico', '--native-binding']}, 'PICO_ADAPTER_BINDING')
    # The existing canonical ADB adapter reports platform=android, not pico4.
    # Its actual selected ID disambiguates the product. Never relabel a Phone run.
    return validate(result_dir, source_sha, artifact_sha, manifest['id'], 'android',
                    required_modules, True)

def main(argv=None):
    try:
        parser = ClosedParser(description=__doc__)
        parser.add_argument('--result-dir', type=Path, required=True)
        parser.add_argument('--expected-source-sha', required=True)
        parser.add_argument('--expected-artifact-sha256', required=True)
        parser.add_argument('--required-module', action='append', required=True)
        args = parser.parse_args(argv)
        result = verify(args.result_dir, args.expected_source_sha,
                        args.expected_artifact_sha256, args.required_module)
    except (ImportError, OSError, TypeError, KeyError, ValueError, RecursionError):
        print('PICO_RESULT_REJECTED', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == '__main__': raise SystemExit(main())
