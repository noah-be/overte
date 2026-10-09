#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Expose locked native archives to F-Droid's source scanner before compilation.

The archive cache remains outside the checkout. All native archives are expanded
inside the checkout and cleaned using the explicit, content-bound policy before
inventorying. Conan applies the same exclusions to actual compiler sources.
Compilation accepts only the declared, content-bound scandelete removals from
the inventoried view; raw archives must never restore the rejected files.
"""
import hashlib
import json
from pathlib import Path
import os
import stat
import tarfile
import zipfile


def load_policy(path, manifest=None):
    policy = json.loads(Path(path).read_text())
    if policy.get('schema_version') != 2:
        raise ValueError('unsupported source scan policy')
    if manifest is not None and digest(manifest) != policy['source_manifest_sha256']:
        raise ValueError('source cleanup policy does not match locked manifest')
    seen = set()
    for rule in policy['remove'] + policy['scandelete']:
        for key in ('archive_path', 'compiler_suffix'):
            relative = Path(rule[key])
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise ValueError('unsafe source cleanup path')
        identity = (rule['archive_sha256'], rule['archive_path'])
        if identity in seen:
            raise ValueError('duplicate source cleanup rule')
        seen.add(identity)
    return policy


def clean_view(root, policy):
    """Only exact, content-bound removals; preserve source and license files."""
    for rule in policy['remove'] + policy['scandelete']:
        path = root / rule['archive_sha256'] / rule['archive_path']
        if path.is_symlink() or not path.is_file() or digest(path) != rule['sha256']:
            raise ValueError('source cleanup rule is stale: ' + rule['archive_path'])
    # Validate every rule before changing any file.
    for rule in policy['remove']:
        (root / rule['archive_sha256'] / rule['archive_path']).unlink()


def clean_compiler_sources(root, reference, policy):
    """Apply the same exclusions after Conan source() and before any build().

    Recipes may put their extracted archive below an additional source directory;
    a full relative suffix plus SHA-256 binds each exclusion. Qt's composed module
    prefix is explicitly recorded in the policy. Missing inputs may already have
    been excluded by a recipe, but changed matching inputs fail closed.
    """
    rules = [rule for rule in policy['remove'] + policy.get('scandelete', [])
             if rule['reference'] == reference]
    by_name = {}
    for rule in rules:
        by_name.setdefault(Path(rule['compiler_suffix']).name, []).append(rule)
    remove = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in files:
            if name not in by_name:
                continue
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            for rule in by_name[name]:
                suffix = rule['compiler_suffix']
                if relative != suffix and not relative.endswith('/' + suffix):
                    continue
                if path.is_symlink() or digest(path) != rule['sha256']:
                    raise ValueError('compiler source cleanup input changed: ' + relative)
                remove.append(path)
                break
    for path in remove:
        path.unlink()
    return len(remove)


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


def expand(document, store, destination, checkout, policy=None):
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
    if policy is not None:
        clean_view(destination, policy)
    # Leave these files present for F-Droid's scanner to delete. Record exact
    # paths inside the hash-bound inventory, not glob permissions: metadata
    # globs must never authorize deleting an unexpected compiler input.
    deletions = [rule['archive_sha256'] + '/' + rule['archive_path']
                 for rule in (policy or {}).get('scandelete', [])]
    record = {'archives': archives, 'files': inventory(destination),
              'scandelete': deletions}
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
    deletions = set(record['scandelete'])
    expected = {path: entry for path, entry in record['files'].items()
                if path not in deletions}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        remaining = sorted(deletions & set(actual))
        raise ValueError('expanded source changed after prebuild; refusing to restore '
                         'scanner-deleted inputs from archives. Missing examples: ' + str(missing[:5])
                         + '; declared scandelete files still present: ' + str(remaining[:5]))
