# SPDX-License-Identifier: Apache-2.0
"""Bind reusable build outputs to one source commit and release configuration."""
import json
from pathlib import Path, PurePosixPath

from core import digest, write_json

FIXED_FILES = {
    'bootstrap': 'bootstrap-result.json',
    'host-tools': 'host-tools-result.json',
    'target': 'target-result.json',
    'gradle': 'gradle-runtime.json',
    'source': 'source.tar',
    'apk': 'source/android/phone/apps/phoneInterface/build/outputs/apk/release/phoneInterface-release-unsigned.apk',
}
MODULE = 'source/android/phone/apps/phoneInterface/'


def regular_file(attempt, relative):
    part = PurePosixPath(relative)
    if part.is_absolute() or '..' in part.parts or '\\' in relative:
        raise ValueError('Build evidence path escapes its attempt')
    candidate = attempt / relative
    cursor = candidate
    while cursor != attempt:
        if cursor.is_symlink():
            raise ValueError('Symlinked build evidence is not accepted')
        cursor = cursor.parent
    if not candidate.is_file() or attempt not in candidate.resolve().parents:
        raise ValueError('Build evidence is not a regular file inside the attempt')
    return candidate


def write_receipt(g):
    files = {role: [relative] for role, relative in FIXED_FILES.items()}
    module = g.attempt / MODULE
    files['aab'] = [p.relative_to(g.attempt).as_posix() for p in module.glob('build/outputs/bundle/release/*.aab')]
    files['merger'] = [p.relative_to(g.attempt).as_posix() for p in module.glob('build/**/manifest-merger-release-report.txt')]
    files['compile'] = [p.relative_to(g.attempt).as_posix() for p in module.glob('.cxx/**/compile_commands.json')
                        if any(part in {'Release', 'RelWithDebInfo'} for part in p.parts)]
    if any(not paths for paths in files.values()):
        raise ValueError('Build lacks required APK/AAB, merger, compiler or dependency evidence')
    records = {role: [dict(path=rel, sha256=digest(regular_file(g.attempt, rel))) for rel in sorted(paths)]
               for role, paths in files.items()}
    g.receipt = dict(schema=2, source_commit=g.commit, artifact_sha256=digest(g.artifact),
                     attempt=str(g.attempt), builder_image=g.config['builder_image'], network='none',
                     version_code=g.config['version_code'], version_name=g.config['version_name'], files=records)
    write_json(g.out / 'build-receipt.json', g.receipt)


def validate_receipt(g):
    if g.receipt is None:
        path = g.config.get('build_receipt')
        if not path or not Path(path).is_absolute():
            raise ValueError('An absolute build_receipt path is required')
        g.receipt = json.loads(Path(path).read_text())
    r = g.receipt
    if (r.get('schema') != 2 or r.get('source_commit') != g.commit or r.get('network') != 'none'
            or not r.get('builder_image') or r.get('builder_image') != g.config.get('builder_image')
            or type(r.get('version_code')) is not int or r['version_code'] <= 0
            or r.get('version_code') != g.config.get('version_code')
            or r.get('version_name') != g.config.get('version_name')):
        raise ValueError('Build receipt schema, source or release coordinates differ')
    attempt = Path(r['attempt'])
    if not attempt.is_absolute() or attempt.is_symlink() or not attempt.is_dir():
        raise ValueError('Build receipt attempt is unavailable')
    attempt = attempt.resolve()
    records = r.get('files', {})
    if set(records) != (set(FIXED_FILES) | {'aab', 'merger', 'compile'}):
        raise ValueError('Build receipt has missing or unexpected evidence roles')
    seen = set()
    for role, entries in records.items():
        if not isinstance(entries, list) or not entries:
            raise ValueError('Build receipt contains an empty evidence role')
        if role in FIXED_FILES and [entry['path'] for entry in entries] != [FIXED_FILES[role]]:
            raise ValueError('Build evidence role has an unexpected path')
        for entry in entries:
            relative = entry['path']
            if relative in seen:
                raise ValueError('Build receipt duplicates an evidence file')
            seen.add(relative)
            if role == 'aab' and not (relative.startswith(MODULE + 'build/outputs/bundle/release/') and relative.endswith('.aab')):
                raise ValueError('AAB evidence is outside the release output')
            if role == 'merger' and not (relative.startswith(MODULE + 'build/') and relative.endswith('/manifest-merger-release-report.txt')):
                raise ValueError('Permission origin evidence is not the release merger report')
            if role == 'compile' and not (relative.startswith(MODULE + '.cxx/') and relative.endswith('/compile_commands.json')
                                          and any(p in {'Release', 'RelWithDebInfo'} for p in PurePosixPath(relative).parts)):
                raise ValueError('Native compiler evidence is not from a release configuration')
            if digest(regular_file(attempt, relative)) != entry['sha256']:
                raise ValueError('Build evidence was changed after receipt creation')
    apk = regular_file(attempt, FIXED_FILES['apk'])
    if digest(apk) != r.get('artifact_sha256'):
        raise ValueError('APK differs from build receipt')
    if g.config.get('artifact') and digest(Path(g.config['artifact'])) != r['artifact_sha256']:
        raise ValueError('Explicit artifact differs from build receipt')
    g.attempt, g.artifact = attempt, apk
    return apk


def role_paths(g, role):
    return [g.attempt / entry['path'] for entry in g.receipt['files'][role]]
