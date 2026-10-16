#!/usr/bin/env python3
"""Recognize a one-way native PR text-edit lane; never assert qualification.

The deliberately small marker implementation imports only the standard library.
Its exact ordinary blob at the original protected base is independently pinned
by the API consumer. A successful marker means that this invocation may only
retain authenticated prior proof or fail; it must never execute a producer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'tools/repository-checks/metadata_context.py'
SOURCE_READY = True
REPOSITORY = 'noah-l-frank/overte'
REPOSITORY_ID = 1319052603
MARKER_STEP = 'Authenticated one-way metadata non-producer'
SOURCE_WORKFLOW = '.github/workflows/pr-metadata-context.yml'
SOURCE_TEMPLATE = 'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml'
MARKER_JOB = 'Authenticate PR text edit / Recognize immutable text edit context'
CALLERS = frozenset({'.github/workflows/repository-checks.yml', '.github/workflows/codeql.yml'})
_SHA = re.compile(r'[0-9a-f]{40}')


class MetadataUnavailable(ValueError):
    """The recognized lane cannot establish current retained qualification."""


def require(condition, message):
    if not condition:
        raise MetadataUnavailable(message)


def event_only(event, event_name):
    """Recognize only complete known text edits, including title plus body."""
    if event_name not in {'pull_request', 'pull_request_target'} or not isinstance(event, dict) \
            or event.get('action') != 'edited':
        return False
    repository, pr, changes = event.get('repository'), event.get('pull_request'), event.get('changes')
    if not isinstance(repository, dict) or repository.get('full_name') != REPOSITORY \
            or type(repository.get('id')) is not int or repository['id'] != REPOSITORY_ID \
            or not isinstance(pr, dict) or type(event.get('number')) is not int or event['number'] < 1 \
            or type(pr.get('number')) is not int or pr['number'] != event['number'] \
            or pr.get('state') != 'open' or not isinstance(changes, dict) or not changes \
            or not set(changes) <= {'title', 'body'}:
        return False
    for side in ('base', 'head'):
        identity = pr.get(side)
        if not isinstance(identity, dict) or not isinstance(identity.get('ref'), str) or not identity['ref'] \
                or not isinstance(identity.get('sha'), str) or not _SHA.fullmatch(identity['sha']) \
                or identity['sha'] == '0' * 40:
            return False
    base_repository = pr['base'].get('repo')
    if not isinstance(base_repository, dict) or base_repository.get('full_name') != REPOSITORY \
            or type(base_repository.get('id')) is not int or base_repository['id'] != REPOSITORY_ID:
        return False
    for key, change in changes.items():
        if not isinstance(change, dict) or set(change) != {'from'}:
            return False
        allowed = (str, type(None)) if key == 'body' else (str,)
        if not isinstance(change['from'], allowed) or key not in pr or not isinstance(pr[key], allowed):
            return False
    return True


def document(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate server event field')
            value[key] = item
        return value
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 1_000_000,
            'bounded server event unavailable')
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(MetadataUnavailable('nonfinite server event')))


def _git(root, *arguments):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', '--no-replace-objects', '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', *arguments], cwd=root, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
    require(len(result.stdout) <= 100_000, 'trusted source identity exceeds bound')
    return result.stdout


def native(event, environment, *, root=ROOT, caller=None):
    """Bind the native invocation and its actual immutable protected checkout.

    This is not an API proof of original caller M. The separate native reusable
    source reference supplies M to the consumer; event fields never replace it.
    """
    require(event_only(event, environment.get('GITHUB_EVENT_NAME')), 'not a complete known text edit')
    number, pr = event['number'], event['pull_request']
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': REPOSITORY,
        'GITHUB_REPOSITORY_ID': str(REPOSITORY_ID), 'GITHUB_EVENT_NAME': 'pull_request',
        'GITHUB_REF': f'refs/pull/{number}/merge', 'GITHUB_BASE_REF': 'main',
        'GITHUB_HEAD_REF': pr['head']['ref'], 'GITHUB_RUN_ATTEMPT': '1',
        'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24'}
    require(all(environment.get(key) == value for key, value in expected.items()),
            'metadata requires the original main native Actions invocation')
    require(pr['base']['ref'] == 'main' and pr['head'].get('repo', {}).get('full_name') == REPOSITORY
        and pr['head'].get('repo', {}).get('id') == REPOSITORY_ID, 'metadata source is not same-fork main')
    source = environment.get('GITHUB_SHA')
    require(type(source) is str and _SHA.fullmatch(source) and source != '0' * 40
        and environment.get('GITHUB_WORKFLOW_SHA') == source
        and re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')),
        'metadata server source unavailable')
    candidates = CALLERS if caller is None else {caller}
    require(candidates <= CALLERS and any(environment.get('GITHUB_WORKFLOW_REF') ==
        REPOSITORY + '/' + path + '@' + expected['GITHUB_REF'] for path in candidates),
        'metadata caller source unavailable')
    root = Path(root)
    require(_git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip() == pr['base']['sha'],
            'marker checkout differs from the immutable main base')
    row = _git(root, 'ls-tree', '-z', pr['base']['sha'], '--', ':(literal)' + SOURCE).split(b'\0')
    require(len(row) == 2 and not row[1], 'marker source absent or ambiguous')
    fields, path = row[0].split(b'\t')
    mode, kind, oid = fields.decode().split()
    require(path.decode() == SOURCE and mode == '100644' and kind == 'blob',
            'marker source is not an ordinary immutable blob')
    source_path = root
    for part in Path(SOURCE).parts:
        source_path = source_path / part
        require(not source_path.is_symlink(), 'marker source contains an alias')
    raw = source_path.read_bytes()
    require(len(raw) <= 64_000 and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == oid,
            'loaded marker differs from immutable protected source')
    return {'number': number, 'base': pr['base']['sha'], 'head': pr['head']['sha'],
        'merge': source, 'run_id': int(environment['GITHUB_RUN_ID']), 'helper_blob': oid}


def recognize(event, environment, *, root=ROOT):
    metadata = event_only(event, environment.get('GITHUB_EVENT_NAME'))
    result = {'kind': 'native-metadata-intent', 'metadata_edit': metadata,
              'metadata_intent': 'false', 'qualification': False}
    if SOURCE_READY is not True or not metadata or event['pull_request']['base']['ref'] != 'main':
        return result
    require(environment.get('GITHUB_JOB') == 'recognize', 'marker requires its reviewed reusable job')
    return {**result, **native(event, environment, root=root), 'metadata_intent': 'true'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--event-name', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        require(str(args.event) == os.environ.get('GITHUB_EVENT_PATH')
            and args.event_name == os.environ.get('GITHUB_EVENT_NAME')
            and str(args.output) == os.environ.get('GITHUB_OUTPUT'), 'marker requires native server files')
        result = recognize(document(args.event), os.environ)
        with args.output.open('a') as output:
            output.write('metadata_intent=' + result['metadata_intent'] + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MetadataUnavailable, ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        print('Native metadata context unavailable; no retained qualification asserted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
