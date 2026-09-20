# SPDX-License-Identifier: Apache-2.0
"""Offline test-input inventory helpers; no network operations on import."""
from pathlib import Path
import re
import shutil

from core import digest

RUNTIMES = ('8.0.0_r4-robolectric-r1-i7', '15-robolectric-13954326-i7')


def verify_inventory(store):
    inventory = store / 'ARTIFACT_SHA256SUMS'
    complete = store / 'COMPLETE'
    if complete.read_text().strip() != digest(inventory) + '  ARTIFACT_SHA256SUMS':
        raise ValueError('Gradle completion marker does not bind the inventory')
    expected = {}
    for line in inventory.read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        if not match:
            raise ValueError('Malformed Gradle artifact inventory')
        sha, relative = match.groups()
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or '\\' in relative or relative in expected:
            raise ValueError('Unsafe or duplicate Gradle inventory path')
        expected[relative] = sha
    actual = {}
    for directory in ('caches/modules-2/files-2.1', 'wrapper/dists'):
        for p in (store / directory).rglob('*'):
            if p.is_symlink():
                raise ValueError('Linked Gradle artifacts are not accepted')
            if p.is_file() and p.suffix not in {'.lck', '.ok'}:
                actual[p.relative_to(store).as_posix()] = digest(p)
    if not actual or actual != expected:
        raise ValueError('Gradle artifacts are missing, changed or outside the inventory')


def write_inventory(store):
    lines = []
    for directory in ('caches/modules-2/files-2.1', 'wrapper/dists'):
        for p in (store / directory).rglob('*'):
            if p.is_symlink():
                raise ValueError('Linked Gradle artifacts are not accepted')
            if p.is_file() and p.suffix not in {'.lck', '.ok'}:
                lines.append(f'{digest(p)}  {p.relative_to(store).as_posix()}\n')
    if not lines:
        raise ValueError('Empty Gradle artifact store')
    inventory = store / 'ARTIFACT_SHA256SUMS'
    inventory.write_text(''.join(sorted(lines, key=lambda line: line[66:])))
    (store / 'COMPLETE').write_text(digest(inventory) + '  ARTIFACT_SHA256SUMS\n')


def stage_runtimes(store, destination):
    sources = []
    for version in RUNTIMES:
        name = f'android-all-instrumented-{version}.jar'
        candidates = list((store / 'caches/modules-2/files-2.1/org.robolectric/android-all-instrumented' / version).glob('*/' + name))
        if len(candidates) != 1 or candidates[0].is_symlink():
            raise ValueError('Acquire both pinned Robolectric SDKs before the clean build')
        sources.append(candidates[0])
    destination.mkdir()
    for source in sources:
        shutil.copyfile(source, destination / source.name)
