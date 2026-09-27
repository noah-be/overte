#!/usr/bin/env python3
"""Verify the prepared image matches this candidate's locked dependency inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

INPUTS = ('conanfile.py', 'tools/conan-profiles/linux', 'tools/native-tests/conan-linux.lock')


def verify(source: Path, metadata: dict) -> dict:
    if (metadata.get('schema') != 1 or metadata.get('repository') != 'noah-be/overte'
            or not re.fullmatch(r'[0-9a-f]{40}', str(metadata.get('source_sha', '')))
            or not re.fullmatch(r'[1-9][0-9]*', str(metadata.get('run_id', '')))
            or not re.fullmatch(r'[0-9a-f]{64}', str(metadata.get('archive_sha256', '')))
            or not isinstance(metadata.get('inputs'), dict) or set(metadata['inputs']) != set(INPUTS)):
        raise ValueError('invalid prepared package identity')
    for name in INPUTS:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'dependency input must be a regular file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata['inputs'][name]:
            raise ValueError(f'prepared image does not match {name}; prepare and review a new baseline image')
    return {'status': 'PASS', 'baseline_sha': metadata['source_sha'], 'baseline_run': metadata['run_id']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path.cwd())
    parser.add_argument('--metadata', type=Path, default=Path('/opt/overte-native-package.json'))
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.source, json.loads(args.metadata.read_text())), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f'Native package prerequisite failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
