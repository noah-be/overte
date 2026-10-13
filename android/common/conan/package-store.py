#!/usr/bin/env python3
"""Restore explicitly selected original packages; never attest dependency production."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

MAX_FILES = 100000
MAX_BYTES = 32 * 1024 ** 3


class StoreError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise StoreError(message)


def unique_json(path):
    require(path.stat().st_size <= 32 * 1024 ** 2, 'metadata byte limit')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def digest(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def hex_value(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value and '\x00' not in value,
            'invalid relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == value
            and value != '.', 'path escape or noncanonical path')
    return path


def regular(path):
    require(path.is_file() and not path.is_symlink(), 'missing or symlinked metadata')
    return path


def manifest(folder):
    # PREV/RREV are Conan's legacy MD5 manifest identities. Independently pinned
    # SHA256 input ledgers and the new transport ledger remain separate.
    from conan.internal.model.manifest import FileTreeManifest
    parsed = FileTreeManifest.load(str(folder))
    text = (folder / 'conanmanifest.txt').read_text()
    require(len([line for line in text.splitlines()[1:] if line]) == len(parsed.file_sums),
            'duplicate manifest entry')
    for name, value in parsed.file_sums.items():
        relative(name)
        require(hex_value(value, 32), 'invalid manifest hash')
    return parsed


def tree(folder):
    require(folder.is_dir() and not folder.is_symlink() and folder.resolve() == folder,
            'noncanonical payload directory')
    files, directory_links = {}, {}
    for path in folder.rglob('*'):
        name = path.relative_to(folder).as_posix()
        relative(name)
        if path.is_symlink():
            link = os.readlink(path)
            require(not Path(link).is_absolute() and path.resolve(strict=True).is_relative_to(folder),
                    'symlink escape')
            if path.is_dir():
                directory_links[name] = (path, link)
                continue
        require(path.is_dir() or path.is_file(), 'special payload file')
        if path.is_file():
            files[name] = path
        require(len(files) + len(directory_links) <= MAX_FILES, 'file limit')
    return files, directory_links


def identity(node):
    return node['ref'], node['package_id'], node['prev']


class PackageStore:
    def __init__(self, binding, binding_sha256, evidence_root, payload_roots, recipe_root):
        import conan
        require(conan.__version__ == '2.25.2', 'Conan 2.25.2 required')
        self.binding_path = regular(binding.absolute())
        require(self.binding_path == self.binding_path.resolve(), 'noncanonical binding')
        require(hex_value(binding_sha256, 64) and digest(self.binding_path) == binding_sha256,
                'binding SHA256 mismatch')
        self.binding_sha256 = binding_sha256
        self.spec = unique_json(self.binding_path)
        require(self.spec.get('contract') == 'overte-pico-qualified-inputs-v2', 'original V2 binding required')
        self.evidence_root = evidence_root.resolve(strict=True)
        self.payload_roots = [p.resolve(strict=True) for p in payload_roots]
        self.recipe_root = recipe_root.resolve(strict=True)
        require(self.payload_roots and all(p.is_dir() for p in self.payload_roots), 'payload roots required')
        require(isinstance(self.spec.get('files'), dict) and 0 < len(self.spec['files']) <= MAX_FILES,
                'invalid original inventory')
        self.nodes = {}
        self.graph_hashes = {}
        original_root = PurePosixPath(self.spec['attemptRoot'])
        require(original_root.is_absolute(), 'original attempt root required')
        for phase in ('host-tools', 'target'):
            name = self.spec['phases'][phase]['actualGraph']
            path = self.bound(name)
            self.graph_hashes[phase] = digest(path)
            nodes = unique_json(path)['graph']['nodes']
            require(isinstance(nodes, dict) and 1 < len(nodes) <= 1024, 'graph node limit')
            for node_id, node in nodes.items():
                if node_id == '0':
                    continue
                require(hex_value(node.get('rrev'), 32) and hex_value(node.get('package_id'), 40)
                        and hex_value(node.get('prev'), 32) and node['ref'].endswith('#' + node['rrev']),
                        'invalid original package identity')
                require(node.get('binary') in ('Build', 'Cache') and node.get('remote') is None
                        and node.get('binary_remote') is None, 'unqualified original package state')
                recorded = PurePosixPath(node['package_folder'])
                require(recorded.is_absolute() and recorded.is_relative_to(original_root), 'package path escape')
                rel = relative(recorded.relative_to(original_root).as_posix())
                # f/ is Conan finalize output, not the immutable package whose
                # manifest defines PREV. Missing immutable bytes need production.
                require(rel.parts[:2] == ('conan', 'p'), 'unexpected package namespace')
                item = self.nodes.setdefault(identity(node), {'node': node, 'paths': set()})
                item['paths'].add(rel.as_posix())
        self.index = unique_json(self.bound(self.spec['recipeIndex']))
        self.recipes = self.index['recipes']
        require(self.index.get('schema_version') == 1 and isinstance(self.recipes, dict)
                and 0 < len(self.recipes) <= 64, 'recipe index limit')
        self.entries = []
        self.total_bytes = 0

    def bound(self, name):
        rel = relative(name)
        path = self.evidence_root / rel
        regular(path)
        require(path.resolve(strict=True).is_relative_to(self.evidence_root), 'evidence path escape')
        expected = self.spec['files'].get(name)
        require(hex_value(expected, 64) and digest(path) == expected, 'original evidence SHA256 mismatch')
        return path

    def available(self):
        available, missing = [], []
        for key, item in sorted(self.nodes.items()):
            candidates = [root / rel for root in self.payload_roots for rel in sorted(item['paths'])
                          if PurePosixPath(rel).name == 'p' and (root / rel / 'conanmanifest.txt').is_file()
                          and (root / rel / 'conaninfo.txt').is_file()]
            (available if candidates else missing).append(list(key))
        return {'contract': 'overte-conan-package-import-selection-v1',
                'bindingSha256': self.binding_sha256, 'packages': available, 'missingPackages': missing,
                'status': 'METADATA_AVAILABILITY_ONLY_CONTENT_VERIFICATION_PENDING'}

    def add_tree(self, folder, archive_folder, expected_manifest, expected_ledger=None):
        files, links = tree(folder)
        ordinary = set(files) - {'conanmanifest.txt'}
        require(ordinary == set(expected_manifest.file_sums), 'manifest file set mismatch')
        for name, path in files.items():
            if name != 'conanmanifest.txt':
                actual = hashlib.md5(os.readlink(path).encode(), usedforsecurity=False).hexdigest() \
                    if path.is_symlink() else digest(path, 'md5')
                require(actual == expected_manifest.file_sums[name], 'manifest content mismatch')
            self.add(path, archive_folder + '/' + name, expected_ledger.get(name) if expected_ledger else None)
        for name, (path, _) in links.items():
            self.add(path, archive_folder + '/' + name)

    def add(self, path, archive_name, expected_sha256=None):
        relative(archive_name)
        require(len(self.entries) < MAX_FILES, 'transport file limit')
        value = digest(path) if path.is_file() else hashlib.sha256(os.readlink(path).encode()).hexdigest()
        require(expected_sha256 is None or value == expected_sha256, 'original payload SHA256 mismatch')
        size = path.stat().st_size if path.is_file() and not path.is_symlink() else 0
        self.total_bytes += size
        require(self.total_bytes <= MAX_BYTES, 'transport byte limit')
        self.entries.append((path, archive_name, value, os.readlink(path) if path.is_symlink() else None))

    def validate(self, selection, selection_sha256):
        regular(selection)
        require(hex_value(selection_sha256, 64) and digest(selection) == selection_sha256,
                'selection SHA256 mismatch')
        chosen = unique_json(selection)
        require(chosen.get('contract') == 'overte-conan-package-import-selection-v1'
                and chosen.get('bindingSha256') == self.binding_sha256, 'selection binding mismatch')
        selected = chosen.get('packages')
        require(isinstance(selected, list) and 0 < len(selected) <= 128
                and all(isinstance(k, list) and len(k) == 3 and all(isinstance(v, str) for v in k)
                        for k in selected), 'invalid selection')
        keys = [tuple(k) for k in selected]
        require(len(set(keys)) == len(keys) and all(k in self.nodes for k in keys), 'foreign or duplicate selection')
        pkglist = {}
        folders = set()
        from conan.internal.model.manifest import FileTreeManifest
        for reference, item in sorted(self.recipes.items()):
            relative(reference)
            folder = item['cache_folder']
            require(re.fullmatch('[A-Za-z0-9_-]{1,64}', folder) and folder not in folders,
                    'invalid recipe cache folder')
            folders.add(folder)
            require(hex_value(item['rrev'], 32) and isinstance(item.get('files'), dict), 'recipe identity')
            root = self.recipe_root / reference
            export = root / 'export'
            files, links = tree(root)
            require(not links and set(files) == set(item['files']), 'recipe ledger file set mismatch')
            for name, path in files.items():
                require(name.startswith(('export/', 'export_sources/')) and not path.is_symlink(),
                        'unexpected recipe path')
                self.add(path, folder + ('/e/' + name[7:] if name.startswith('export/')
                                        else '/es/' + name[15:]), item['files'][name])
            m = manifest(export)
            created = FileTreeManifest.create(str(export), str(root / 'export_sources'))
            require(created.file_sums == m.file_sums and m.summary_hash == item['rrev'], 'recipe manifest/RREV mismatch')
            pkglist[reference] = {'revisions': {item['rrev']: {'recipe_folder': folder, 'packages': {}}}}
        for key in keys:
            item = self.nodes[key]
            ref, package_id, prev = key
            reference, rrev = ref.rsplit('#', 1)
            require(reference in self.recipes and self.recipes[reference]['rrev'] == rrev, 'graph recipe mismatch')
            candidates = [(root, root / rel, rel) for root in self.payload_roots for rel in sorted(item['paths'])
                          if PurePosixPath(rel).name == 'p' and (root / rel / 'conanmanifest.txt').is_file()]
            require(candidates, 'immutable package missing; finalized f/ is not importable')
            payload_root, path, rel = candidates[0]
            require(path.resolve(strict=True).is_relative_to(payload_root), 'payload root escape')
            regular(path / 'conaninfo.txt'); regular(path / 'conanmanifest.txt')
            m = manifest(path)
            require(m.summary_hash == prev, 'package PREV mismatch')
            require(digest(path / 'conaninfo.txt', 'sha1') == package_id, 'package-ID mismatch')
            ledger = {name[len(rel) + 1:]: value for name, value in self.spec['files'].items()
                      if name.startswith(rel + '/')}
            archive_folder = 'imports/' + hashlib.sha256('\0'.join(key).encode()).hexdigest() + '/p'
            try:
                self.add_tree(path, archive_folder, m, ledger)
            except StoreError as error:
                raise StoreError(ref + ':' + package_id + '#' + prev + ': ' + str(error)) from error
            packages = pkglist[reference]['revisions'][rrev]['packages']
            packages.setdefault(package_id, {'revisions': {}})['revisions'][prev] = {'package_folder': archive_folder}
        self.pkglist = pkglist
        self.selected = keys
        self.selection_sha256 = selection_sha256

    def transport(self, destination):
        require(not destination.exists(), 'transport already exists')
        require(len({name for _, name, _, _ in self.entries}) == len(self.entries), 'duplicate archive path')
        with destination.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as zipped, \
                tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as archive:
            # Conan export_sources() may require an empty es/ directory.
            for item in self.recipes.values():
                for name in (item['cache_folder'] + '/es', item['cache_folder'] + '/d/metadata'):
                    entry = tarfile.TarInfo(name); entry.type = tarfile.DIRTYPE; entry.mode = 0o755
                    archive.addfile(entry)
            for path, name, expected, link in self.entries:
                # Archive actual bytes for hardlinked regular files as well;
                # inode sharing is not a package identity or an import grant.
                archive.inodes.clear()
                entry = archive.gettarinfo(str(path), arcname=name)
                require(not (entry.mode & 0o6000), 'privileged archive mode')
                entry.uid = entry.gid = entry.mtime = 0
                entry.uname = entry.gname = ''
                if entry.issym():
                    require(link == entry.linkname and not Path(link).is_absolute(),
                            'symlink changed during transport')
                    actual = digest(path) if path.is_file() else hashlib.sha256(os.readlink(path).encode()).hexdigest()
                    require(actual == expected, 'payload changed during transport')
                    archive.addfile(entry)
                else:
                    require(entry.isfile() and link is None, 'special or changed archive member')
                    with path.open('rb') as stream:
                        class Reader:
                            def __init__(self): self.hash = hashlib.sha256()
                            def read(self, size):
                                data = stream.read(size); self.hash.update(data); return data
                        reader = Reader()
                        archive.addfile(entry, reader)
                        require(reader.hash.hexdigest() == expected and not stream.read(1),
                                'payload changed during transport')
            content = json.dumps(self.pkglist, sort_keys=True).encode()
            entry = tarfile.TarInfo('pkglist.json'); entry.size = len(content); entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(content))

    def restore(self, cache, transport, receipt):
        require(all(p.is_absolute() and p == p.resolve() for p in (cache, transport, receipt)),
                'absolute canonical output paths required')
        require(len({cache, transport, receipt}) == 3, 'distinct output paths required')
        require(cache != Path.home() / '.conan2' and not cache.exists(),
                'new private canonical cache required')
        require(not receipt.exists() and receipt.parent.is_dir() and transport.parent.is_dir(),
                'new transport/receipt destinations required')
        for source in self.payload_roots + [self.evidence_root, self.recipe_root]:
            require(not cache.is_relative_to(source) and not transport.is_relative_to(source)
                    and not receipt.is_relative_to(source), 'output inside immutable input')
        self.transport(transport)
        env = os.environ | {'CONAN_HOME': str(cache)}
        logs = []
        def run(*args, json_result=False):
            result = subprocess.run(['conan', *args], env=env, text=True, capture_output=True, timeout=240)
            logs.append({'command': ['conan', *args], 'exitCode': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
            require(result.returncode == 0, 'actual Conan operation failed: ' + ' '.join(args))
            return json.loads(result.stdout) if json_result else result.stdout
        require(run('--version').strip() == 'Conan version 2.25.2', 'CLI Conan version mismatch')
        remotes = run('remote', 'list', '--format=json', json_result=True)
        for remote in remotes:
            run('remote', 'remove', remote['name'])
        require(run('remote', 'list', '--format=json', json_result=True) == [], 'remote configured')
        require(not run('list', '*#*:*#*', '--format=json', json_result=True).get('Local Cache'), 'cache not empty')
        run('cache', 'restore', str(transport))
        listing = run('list', '*#*:*#*', '--format=json', json_result=True)['Local Cache']
        actual = {(ref + '#' + rrev, pid, prev) for ref, row in listing.items()
                  for rrev, rev in row['revisions'].items() for pid, package in rev.get('packages', {}).items()
                  for prev in package['revisions']}
        require(actual == set(self.selected), 'restored package identity mismatch')
        run('cache', 'check-integrity', '*#*:*#*')
        result = {'contract': 'overte-conan-package-transport-v1', 'status': 'TRANSPORT_RESTORE_COMPLETE',
                  'qualification': 'NOT_DEPENDENCY_PRODUCTION_OR_APPLICATION_QUALIFICATION',
                  'importerSha256': digest(Path(__file__).resolve()), 'conanVersion': '2.25.2',
                  'bindingSha256': self.binding_sha256, 'selectionSha256': self.selection_sha256,
                  'originalDependencySourceRevision': self.spec.get('dependencySourceRevision'),
                  'originalApplicationSourceRevision': self.spec.get('sourceRevision'),
                  'actualGraphSha256': self.graph_hashes, 'transportSha256': digest(transport),
                  'cacheRoot': str(cache), 'packages': [list(k) for k in self.selected],
                  'missingPackages': [list(k) for k in sorted(set(self.nodes) - set(self.selected))],
                  'transportFileSha256': {name: sha for _, name, sha, _ in self.entries}, 'operations': logs}
        with receipt.open('x') as stream:
            json.dump(result, stream, indent=2); stream.write('\n')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'restore'))
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--expected-binding-sha256', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--payload-root', type=Path, action='append', required=True)
    parser.add_argument('--recipe-root', type=Path, required=True)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--expected-selection-sha256')
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--transport', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    store = PackageStore(args.binding, args.expected_binding_sha256, args.evidence_root,
                         args.payload_root, args.recipe_root)
    if args.command == 'inspect':
        print(json.dumps(store.available(), indent=2))
    else:
        require(all((args.selection, args.expected_selection_sha256, args.cache, args.transport, args.receipt)),
                'restore requires explicit selected identities, independent SHA256 and new destinations')
        store.validate(args.selection, args.expected_selection_sha256)
        result = store.restore(args.cache, args.transport, args.receipt)
        print(result['status'] + ': ' + str(len(result['packages'])) + ' original packages restored')


if __name__ == '__main__':
    try:
        main()
    except (StoreError, OSError, KeyError, json.JSONDecodeError, tarfile.TarError, subprocess.TimeoutExpired) as error:
        raise SystemExit('package-store: FAIL: ' + str(error))
