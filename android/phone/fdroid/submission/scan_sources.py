#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Expose locked native archives to F-Droid's source scanner before compilation.

The archive cache remains outside the checkout. Its complete expanded view is
inside the checkout, with a content inventory bound to the archive digests.
Compilation refuses a missing or changed view, including scanner deletions:
it must never restore rejected files silently from an unscanned archive.
"""
import hashlib
import json
from pathlib import Path
import os
import stat
import tarfile
import zipfile


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                resolved = path.resolve()
                if not resolved.is_relative_to(root.resolve()):
                    raise ValueError('source symlink escapes scanner view: ' + relative)
                result[relative] = {'link': os.readlink(path)}
            elif path.is_file():
                result[relative] = {'sha256': digest(path)}
            elif not path.is_dir():
                raise ValueError('unsupported source entry: ' + relative)
    return result


def unpack(archive, destination):
    destination.mkdir()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                path = Path(entry.filename)
                mode = entry.external_attr >> 16
                if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                        or stat.S_ISLNK(mode)):
                    raise ValueError('unsafe source ZIP member')
            source.extractall(destination)
    else:
        with tarfile.open(archive, 'r:*') as source:
            # Python's data filter rejects devices and links/path traversal
            # outside this archive root and preserves safe executable bits.
            source.extractall(destination, filter='data')


def expand(document, store, destination, checkout):
    destination = destination.resolve()
    if not destination.is_relative_to(checkout.resolve()) or destination == checkout.resolve():
        raise ValueError('expanded sources must be inside the scanned checkout')
    if destination.exists():
        raise ValueError('scanner view must be new')
    destination.mkdir(parents=True)
    sources = {s['sha256']: s for n in document['nodes'] for s in n.get('sources', [])}
    archives = {}
    for sha, source in sorted(sources.items()):
        archive = store / source['store_path'] / 'source'
        if digest(archive) != sha:
            raise ValueError('source archive changed before expansion')
        unpack(archive, destination / sha)
        archives[sha] = source['store_path']
    record = {'archives': archives, 'files': inventory(destination)}
    (destination / 'inventory.json').write_text(json.dumps(record, sort_keys=True) + '\n')
    return digest(destination / 'inventory.json')


def verify(store, destination, expected_inventory):
    record_path = destination / 'inventory.json'
    if not record_path.is_file() or digest(record_path) != expected_inventory:
        raise ValueError('scanner inventory missing or changed; repeat prebuild and scan')
    record = json.loads(record_path.read_text())
    for sha, relative in record['archives'].items():
        if digest(store / relative / 'source') != sha:
            raise ValueError('source archive changed after prebuild')
    actual = inventory(destination)
    actual.pop('inventory.json', None)
    if actual != record['files']:
        missing = sorted(set(record['files']) - set(actual))
        raise ValueError('expanded source changed after prebuild; refusing to restore '
                         'scanner-deleted inputs from archives. Missing examples: ' + str(missing[:5]))
