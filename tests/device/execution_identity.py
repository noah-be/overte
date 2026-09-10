"""Execution-time SH-004 binding; native installation claims remain adapter-owned."""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def need(condition, code):
    if not condition:
        raise ValueError(code)


def file_digest(path):
    """No symlink/device/empty/oversized input, bounded memory, detect mutation."""
    need(hasattr(os, 'O_NOFOLLOW'), 'OVT_IDENTITY_HOST_UNSUPPORTED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 8 * 1024**3,
             'OVT_IDENTITY_ARTIFACT_FILE')
        result = hashlib.sha256()
        count = 0
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            need(count <= before.st_size, 'OVT_IDENTITY_ARTIFACT_CHANGED')
            result.update(block)
        after = os.fstat(stream.fileno())
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
             and count == before.st_size, 'OVT_IDENTITY_ARTIFACT_CHANGED')
        return result.hexdigest()


class ExecutionIdentity:
    def __init__(self, artifact, source, expected_artifact):
        need(type(source) is str and re.fullmatch('[0-9a-f]{40}', source) is not None,
             'OVT_IDENTITY_EXPECTED_SOURCE')
        need(type(expected_artifact) is str and re.fullmatch('[0-9a-f]{64}', expected_artifact) is not None,
             'OVT_IDENTITY_EXPECTED_ARTIFACT')
        self.artifact = Path(artifact)
        self.source = source
        self.expected_artifact = expected_artifact
        self.verify_artifact()

    def verify_artifact(self):
        try:
            need(file_digest(self.artifact) == self.expected_artifact, 'OVT_IDENTITY_ARTIFACT_MISMATCH')
        except OSError as error:
            raise ValueError('OVT_IDENTITY_ARTIFACT_UNAVAILABLE') from error

    def verify_description(self, description):
        claim = description.get('executionIdentity') if type(description) is dict else None
        need(type(claim) is dict and set(claim) == {
            'schemaVersion', 'sourceRevision', 'artifactSha256', 'installedCandidateVerified'},
            'OVT_IDENTITY_ADAPTER_CLAIM_REQUIRED')
        need(type(claim['schemaVersion']) is int and claim['schemaVersion'] == 1 and
             claim['sourceRevision'] == self.source and
             claim['artifactSha256'] == self.expected_artifact and
             claim['installedCandidateVerified'] is True,
             'OVT_IDENTITY_INSTALLED_CANDIDATE_MISMATCH')

    def emit(self, output):
        # Only the runner calls this after both reserved-target describe checks.
        # No standalone after-the-fact CLI is provided.
        self.verify_artifact()
        value = dict(contract='overte-sh004-result-v1', sourceRevision=self.source,
                     artifactSha256=self.expected_artifact)
        for key, filename in [('runSha256', 'run-manifest.json'),
                              ('summarySha256', 'summary.json'), ('junitSha256', 'junit.xml')]:
            value[key] = file_digest(output / filename)
        destination = output / 'result-identity.json'
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2) + '\n')
