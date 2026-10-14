# SPDX-License-Identifier: Apache-2.0
"""Private, hash-bound APK and SDK inputs shared by every artifact reader."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from core import write_json

SDK_ROOTS = ('build-tools/36.0.0', 'cmdline-tools/latest')
SDK_REQUIRED = ('build-tools/36.0.0/aapt2', 'build-tools/36.0.0/zipalign',
                'build-tools/36.0.0/apksigner', 'build-tools/36.0.0/lib/apksigner.jar',
                'cmdline-tools/latest/bin/apkanalyzer',
                'cmdline-tools/latest/lib/apkanalyzer-classpath.jar')


def source_text(g, relative):
    """Consume the already scanned bytes, never reopen the mutable checkout."""
    expected = g.source_hashes.get(relative)
    path = g.out / 'source-scope' / relative
    part = PurePosixPath(relative)
    if (part.is_absolute() or '..' in part.parts or '\\' in relative
            or not re.fullmatch(r'[0-9a-f]{64}', expected or '')):
        raise ValueError('Artifact source input lacks an exact captured hash')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Captured source input is not a regular file')
        data = stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Captured source input exceeds its bound')
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Captured artifact source input changed')
    return data.decode('utf-8')


def copy_bound(source, target, expected, limit, executable=False):
    if not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
        raise ValueError('Artifact input lacks an exact expected SHA256')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as incoming:
        before = os.fstat(incoming.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError('Artifact input must be a bounded regular file')
        target.parent.mkdir(parents=True, exist_ok=True)
        total, sha = 0, hashlib.sha256()
        with target.open('xb') as outgoing:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b''):
                total += len(chunk)
                if total > limit:
                    raise ValueError('Artifact input grew beyond its size bound')
                outgoing.write(chunk)
                sha.update(chunk)
        after = os.fstat(incoming.fileno())
    if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
            (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or total != before.st_size or sha.hexdigest() != expected):
        raise ValueError('Artifact input changed or differs from its expected SHA256')
    target.chmod(0o555 if executable else 0o444)
    return dict(sha256=sha.hexdigest(), bytes=total, executable=executable)


def sdk_files(sdk):
    files = {}
    for relative in SDK_ROOTS:
        root = sdk / relative
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Required artifact SDK subtree is unavailable or linked')
        for path in root.rglob('*'):
            if path.is_symlink():
                raise ValueError('Linked artifact SDK input is forbidden')
            if path.is_file():
                files[path.relative_to(sdk).as_posix()] = path
            elif not path.is_dir():
                raise ValueError('Special artifact SDK input is forbidden')
    if not set(SDK_REQUIRED).issubset(files) or len(files) > 2048:
        raise ValueError('Artifact SDK closure is empty or exceeds its bound')
    return files


@contextmanager
def artifact_inputs(g, apk, expected, sdk):
    """Remove private copies on success, decoder failure and interruption."""
    if getattr(g, 'artifact_input_paths', None) is not None:
        raise ValueError('Artifact readers must share one active snapshot')
    with tempfile.TemporaryDirectory(prefix='artifact-inputs-', dir=g.out / 'tmp') as directory:
        private = Path(directory)
        private_apk = private / 'artifact.apk'
        apk_record = copy_bound(apk, private_apk, expected, g.policy['max_archive_bytes'])
        bindings = g.config.get('artifact_sdk_bindings')
        files = sdk_files(sdk)
        if not isinstance(bindings, dict) or set(bindings) != set(files):
            raise ValueError('Artifact SDK requires independently pinned complete subtree bindings')
        copied_sdk, records, total = private / 'sdk', {}, 0
        for relative, path in sorted(files.items()):
            binding = bindings[relative]
            part = PurePosixPath(relative)
            if (part.is_absolute() or '..' in part.parts or '\\' in relative
                    or not isinstance(binding, dict) or set(binding) != {'sha256', 'executable'}
                    or type(binding['executable']) is not bool
                    or bool(path.stat().st_mode & 0o111) != binding['executable']):
                raise ValueError('Invalid artifact SDK binding or executable mode')
            records[relative] = copy_bound(path, copied_sdk / relative, binding['sha256'],
                                           512 * 1024 * 1024, binding['executable'])
            total += records[relative]['bytes']
            if total > 2 * 1024 * 1024 * 1024:
                raise ValueError('Artifact SDK closure exceeds its total size bound')
        if set(sdk_files(sdk)) != set(files):
            raise ValueError('Artifact SDK closure changed during capture')
        previous_attempt = getattr(g, 'attempt', None)
        previous_artifact = getattr(g, 'artifact', None)
        evidence, evidence_records = private / 'evidence', {}
        receipt = getattr(g, 'receipt', None) or {}
        evidence_bytes = 0
        for role, entries in receipt.get('files', {}).items():
            if role == 'apk':
                continue  # Every APK reader uses private_apk, including manual review.
            for entry in entries:
                relative = entry['path']
                part = PurePosixPath(relative)
                if (not previous_attempt or part.is_absolute() or '..' in part.parts
                        or '\\' in relative or relative in evidence_records):
                    raise ValueError('Invalid or duplicate artifact evidence input')
                if len(evidence_records) >= 8192:
                    raise ValueError('Artifact receipt evidence exceeds its file bound')
                evidence_records[relative] = copy_bound(previous_attempt / relative,
                    evidence / relative, entry['sha256'], g.policy['max_archive_bytes'])
                evidence_bytes += evidence_records[relative]['bytes']
                if evidence_bytes > 2 * g.policy['max_archive_bytes']:
                    raise ValueError('Artifact receipt evidence exceeds its total size bound')
        write_json(g.out / 'artifact-inputs.json', dict(
            artifact=apk_record, sdk=records, receipt_evidence=evidence_records,
            sdk_scope='Complete Build-Tools 36.0.0 and cmdline-tools/latest subtrees',
            host_runtime='Host Java, shell, Python, scanners and system libraries remain separate prerequisites',
            app_source_closure='Not established by these artifact input bindings'))
        g.artifact_input_paths = private_apk, copied_sdk
        if evidence_records:
            g.attempt = evidence
        g.artifact = private_apk
        try:
            yield private_apk, copied_sdk
        finally:
            g.artifact_input_paths = None
            g.attempt = previous_attempt
            g.artifact = previous_artifact
