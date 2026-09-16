#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
"""Apply the pinned Qt patch and bind its source build to installed QtCore bytes.

This receipt supplements the existing producer/branch checkpoint verification.
It is build provenance, not evidence of native runtime acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / 'ios/patches/qtbase-qmutex-freelist-serialization.patch'
SOURCE = Path('qtbase/src/corelib/thread/qmutex.cpp')
ORIGINAL = 'f617eea7f2ebc22540dafdf7734215a8fbca1dce1c3a105b5856bc4b7caff7c9'
PATCHED = 'c55b9d397e588a4ac6a5b24dca275200d804e60da05935cd8cdc3dce91016d67'
RECEIPT = '.overte-qt-mutex-patch.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(root):
    source = root / SOURCE
    current = digest(source)
    if current == PATCHED:
        return
    if current != ORIGINAL:
        raise ValueError('Qt mutex source does not match pinned Qt 6.11.1 input')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(PATCH)],
                   cwd=root, check=True, timeout=15)
    if digest(source) != PATCHED:
        raise ValueError('Qt mutex patch did not produce the pinned source')


def core_binaries(prefix):
    # Qt static builds can install either a library or a framework archive.
    # Headers/QtCore is an umbrella header, not the framework executable.
    def is_archive_path(path):
        return path.name == 'libQt6Core.a' or (
            path.name == 'QtCore' and (
                path.parent.name == 'QtCore.framework' or
                (path.parent.parent.name == 'Versions' and
                 path.parent.parent.parent.name == 'QtCore.framework')))

    candidates = sorted({p.resolve() for p in (prefix / 'lib').rglob('*')
                         if p.is_file() and is_archive_path(p)})
    if not candidates:
        raise ValueError('Installed QtCore archive is missing')
    result = {}
    for path in candidates:
        relative = path.relative_to(prefix.resolve())
        if path.read_bytes()[:8] != b'!<arch>\n':
            raise ValueError(f'Expected a static QtCore archive: {relative}')
        result[str(relative)] = digest(path)
    return result


def expected(prefix):
    plan = (prefix / '.overte-qt-ios-plan-id').read_text().strip()
    if not plan.endswith('-mutex-' + digest(PATCH)):
        raise ValueError('Qt target build plan lacks the exact mutex patch')
    return {'schema': 1, 'qtVersion': '6.11.1', 'patchSha256': digest(PATCH),
            'sourceSha256': PATCHED, 'plan': plan, 'qtCore': core_binaries(prefix)}


def seal(root, prefix):
    if digest(root / SOURCE) != PATCHED:
        raise ValueError('Cannot seal an unpatched source build')
    receipt = expected(prefix)
    (prefix / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def verify(prefix):
    receipt = json.loads((prefix / RECEIPT).read_text())
    if receipt != expected(prefix):
        raise ValueError('Qt patch receipt does not match source plan/installed QtCore')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['apply', 'seal', 'verify'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--prefix', type=Path)
    args = parser.parse_args()
    if args.mode in ('apply', 'seal') and args.source is None:
        parser.error('--source is required')
    if args.mode in ('seal', 'verify') and args.prefix is None:
        parser.error('--prefix is required')
    if args.mode == 'apply':
        apply(args.source)
    else:
        print(json.dumps(seal(args.source, args.prefix) if args.mode == 'seal'
                         else verify(args.prefix), indent=2))


if __name__ == '__main__':
    main()
