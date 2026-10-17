#!/usr/bin/env python3
"""Authenticate inert PR-event scheduling; never assert qualification.

The deliberately small marker implementation imports only the standard library.
Its exact ordinary blob and complete B/D reader closure are independently bound.
A successful marker means this invocation has an actual same-M ordinary owner,
including a pending/failed owner. It may only abstain from duplicate scheduling
or fail; it never executes a producer or supplies successful results.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'tools/repository-checks/metadata_context.py'
SOURCE_READY = True
REPOSITORY = 'noah-l-frank/overte'
REPOSITORY_ID = 1319052603
MARKER_STEP = 'Authenticated one-way metadata non-producer'
SOURCE_WORKFLOW = '.github/workflows/pr-metadata-context.yml'
SOURCE_TEMPLATE = 'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml'
MARKER_JOB = 'Authenticate PR text edit / Recognize immutable text edit context'
ORDINARY_SOURCE_STEP = 'Authenticated ordinary producer scheduling source'
LEGACY_SOURCE_WORKFLOW = 'd04a6dc70213d8b549bac30c11cc15eaf0182dea'
LEGACY_HELPER_BLOB = '9c531c34ba559d17255768d8cae3129496fac55d'
# Authenticate the only executable bootstrap BEFORE it can read API facts.
# A guard upgrade requires a reviewed helper upgrade; local Git equality alone
# cannot let an arbitrary historical/candidate guard authenticate itself.
SOURCE_GUARD_BLOB = '20580c3ea413e63a6779898fdd3d2c5e051625f4'
TARGETS = frozenset({'main', 'apple-main', 'apple-ios', 'android-main',
                     'android-phone', 'android-vr', 'android-vr-pico'})
_READERS = ('inputs', 'runtime', 'execution', 'producer', 'producer_api', 'source_admission')
CALLERS = frozenset({'.github/workflows/repository-checks.yml', '.github/workflows/codeql.yml'})
_SHA = re.compile(r'[0-9a-f]{40}')


class MetadataUnavailable(ValueError):
    """The inert-event lane cannot establish current native scheduling context."""


def require(condition, message):
    if not condition:
        raise MetadataUnavailable(message)


def event_only(event, event_name):
    """Closed inert PR events; the Android diagnostic label remains meaningful."""
    if event_name not in {'pull_request', 'pull_request_target'} or not isinstance(event, dict) \
            or event.get('action') not in {'edited', 'labeled', 'unlabeled'}:
        return False
    repository, pr, changes = event.get('repository'), event.get('pull_request'), event.get('changes')
    if not isinstance(repository, dict) or repository.get('full_name') != REPOSITORY \
            or type(repository.get('id')) is not int or repository['id'] != REPOSITORY_ID \
            or not isinstance(pr, dict) or type(event.get('number')) is not int or event['number'] < 1 \
            or type(pr.get('number')) is not int or pr['number'] != event['number'] \
            or pr.get('state') != 'open':
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
    if pr['base']['ref'] not in TARGETS:
        return False
    if event['action'] in {'labeled', 'unlabeled'}:
        label, labels = event.get('label'), pr.get('labels')
        if changes not in (None, {}) or type(label) is not dict or type(labels) is not list \
                or type(label.get('id')) is not int or label['id'] <= 0 \
                or type(label.get('name')) is not str or not 0 < len(label['name']) <= 100 \
                or label['name'] == 'android-long-diagnostics':
            return False
        if any(type(item) is not dict or type(item.get('id')) is not int or item['id'] <= 0
               or type(item.get('name')) is not str or not 0 < len(item['name']) <= 100 for item in labels):
            return False
        if len({item['id'] for item in labels}) != len(labels) or len({item['name'] for item in labels}) != len(labels):
            return False
        matches = [item for item in labels if item['id'] == label['id'] or item['name'] == label['name']]
        return (event['action'] == 'labeled' and len(matches) == 1 and matches[0]['id'] == label['id']
                and matches[0]['name'] == label['name']) or (event['action'] == 'unlabeled' and not matches)
    if not isinstance(changes, dict) or not changes or not set(changes) <= {'title', 'body'}:
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
    require(len(result.stdout) <= 1_000_000, 'trusted source identity exceeds bound')
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
        'GITHUB_REF': f'refs/pull/{number}/merge', 'GITHUB_BASE_REF': pr['base']['ref'],
        'GITHUB_HEAD_REF': pr['head']['ref'], 'GITHUB_RUN_ATTEMPT': '1',
        'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24'}
    require(all(environment.get(key) == value for key, value in expected.items()),
            'metadata requires the original native Actions invocation')
    require(pr['base']['ref'] in TARGETS and pr['head'].get('repo', {}).get('full_name') == REPOSITORY
        and pr['head'].get('repo', {}).get('id') == REPOSITORY_ID, 'metadata source is not same-fork')
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
    checkout = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    require(_SHA.fullmatch(checkout), 'marker checkout is not immutable')
    row = _git(root, 'ls-tree', '-z', checkout, '--', ':(literal)' + SOURCE).split(b'\0')
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
    return {'number': number, 'base_snapshot': pr['base']['sha'], 'head': pr['head']['sha'],
        'merge': source, 'run_id': int(environment['GITHUB_RUN_ID']), 'helper_blob': oid,
        'checkout': checkout}


def _protected_readers(event, environment, native_value, root):
    """Authenticate the stdlib guard, complete B/D and lookup BEFORE imports."""
    import importlib.util
    root = Path(root).resolve(strict=True)
    relative = 'tools/test-evidence/source_admission.py'
    path = root / relative
    raw = _git(root, 'show', 'HEAD:' + relative)
    require(not path.is_symlink() and not path.parent.is_symlink() and path.read_bytes() == raw,
            'stdlib source guard differs from immutable protected checkout')
    require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == SOURCE_GUARD_BLOB
        and not path.stat().st_mode & 0o111, 'stdlib source guard has no reviewed bootstrap identity')
    # No neighboring import lookup is exposed until the guard has checked its
    # complete reviewed inventory. The bootstrap itself imports only stdlib.
    search = list(sys.path)
    standard = Path(os.__file__).resolve().parent
    sys.path[:] = [str(standard), str(standard / 'lib-dynload')]
    try:
        spec = importlib.util.spec_from_file_location('trusted_metadata_source_bootstrap', path)
        source = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
    finally:
        sys.path[:] = search
    api = source.GitHubSource()
    repository = api.get('')
    require(repository.get('id') == REPOSITORY_ID and repository.get('full_name') == REPOSITORY
        and repository.get('default_branch') == 'main', 'scheduling repository/default identity changed')
    current_pr = api.get('pulls/' + str(native_value['number']))
    require(current_pr.get('number') == native_value['number'] and current_pr.get('state') == 'open',
            'scheduling current open PR unavailable')
    current_merge = api.get('commits/refs/pull/' + str(native_value['number']) + '/merge')
    resolved = source.resolve_pr_base(api, current_pr, current_merge, event_pr=event['pull_request'])
    target, effective_base = resolved['target'], resolved['base']
    require(resolved['head'] == native_value['head'] and resolved['source'] == native_value['merge']
        and resolved['head_ref'] == event['pull_request']['head']['ref']
        and target == event['pull_request']['base']['ref'], 'scheduling native M/head/target differs')
    reference = api.get('git/ref/heads/main')
    require(reference.get('ref') == 'refs/heads/main' and reference.get('object', {}).get('type') == 'commit',
            'scheduling protected default ref changed')
    default_commit = source.object_id(reference['object'].get('sha'))
    authority = api.get('branches/main')
    require(authority.get('name') == 'main' and authority.get('protected') is True
        and authority.get('commit', {}).get('sha') == default_commit, 'scheduling default protection changed')
    require(native_value['checkout'] in {effective_base, default_commit},
            'scheduling checkout is neither protected B nor D')
    base = source.api_tree(api, effective_base)
    default = source.api_tree(api, default_commit)
    def actual(relative):
        raw = _git(root, 'show', 'HEAD:' + relative)
        entry = default.get(relative)
        require(type(entry) is dict and (relative == source.PROFILE or relative in source.REUSE_LOOKUP_DATA
            or entry == base.get(relative))
            and source.blob_id(raw) == entry['sha'], 'scheduling actual protected controller changed')
        return raw, entry
    require(event_only(event, environment.get('GITHUB_EVENT_NAME'))
        and environment.get('GITHUB_JOB') in {'recognize','route','select'},
        'source precheck requires the one-way metadata scheduling role')
    context = {**source.reuse_compatibility(base, default, target,
        read_actual=actual, actual_imports=source.actual_import_inventory(root)), 'base': effective_base}
    import importlib
    directory = root / 'tools/test-evidence'
    for name in _READERS:
        loaded = sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__).resolve() == directory / (name + '.py'),
                'foreign scheduling reader is already loaded')
    search = list(sys.path)
    sys.path.insert(0, str(directory))
    try:
        A = importlib.import_module('producer_api')
    finally:
        sys.path[:] = search
    return A, source, base, default, default_commit, context


def _source_policy(root, adapter, binding, references, native_value, protected, *, caller):
    """Bind complete current B/D controller and import closure, including labels.

    The marker checkout can be B (tiny source job) or D (independent selector).
    Only immutable Git bytes supply nonmaterialized policy data; no candidate
    Python, YAML snippet, tool, environment capture or suite is executed.
    """
    A, source, base, default, default_commit, context = protected
    require(references['default'] == default_commit and binding['base_sha'] == context['base'],
            'scheduling API and stdlib protected source disagree')
    extras = ('tools/repository-checks/codeql.py', 'tools/repository-checks/codeql_results.py',
              'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
              '.github/codeql/codeql-config.yml')
    for relative in extras:
        require(base.get(relative) == default.get(relative) and base.get(relative, {}).get('mode') == '100644'
            and base[relative]['type'] == 'blob', 'metadata semantic reader differs from current default')
    # M is independently authenticated by the native source adapter. Candidate
    # inputs may change: no candidate parser is imported to classify this event.
    require(base.get(SOURCE) == {'mode': '100644', 'type': 'blob', 'sha': native_value['helper_blob']},
            'scheduling helper differs from original B')
    templates = {
        '.github/workflows/repository-checks.yml': 'tools/repository-checks/workflows/producers/repository-checks.yml',
        '.github/workflows/project-tests.yml': 'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
        '.github/workflows/parent-qualification.yml': 'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
        '.github/workflows/sync-validation.yml': 'tools/repository-checks/workflows/sync-ci-selection.yml',
        '.github/workflows/browser-client.yml': 'tools/repository-checks/workflows/npm-consumers/browser-client.yml',
        SOURCE_WORKFLOW: SOURCE_TEMPLATE,
        '.github/workflows/codeql.yml': 'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
    }
    workflows = {path: default.get(templates[path]) for path in A.METADATA_CALLERS[caller]}
    for entry in workflows.values():
        require(type(entry) is dict and entry.get('mode') == '100644' and entry.get('type') == 'blob',
                'reviewed scheduling workflow template unavailable')
    registered = adapter._object('actions/workflows/' + caller.rsplit('/', 1)[1])
    generations = {'metadata-scheduling-v2': workflows}
    sources = {'metadata-scheduling-v2': {SOURCE: base[SOURCE]}}
    old_source = {'mode': '100644', 'type': 'blob', 'sha': LEGACY_SOURCE_WORKFLOW}
    old_helper = {SOURCE: {'mode': '100644', 'type': 'blob', 'sha': LEGACY_HELPER_BLOB}}
    if caller.endswith('/repository-checks.yml'):
        catalog = json.loads(_git(root, 'show', 'HEAD:.github/package-workflow-generations.json'),
                             object_pairs_hook=source.unique)
        require(type(catalog) is dict and catalog.get('schema') == 1
            and type(catalog.get('generations')) is list and len(catalog['generations']) <= 23,
            'scheduling trusted generation catalog unavailable')
        for row in catalog['generations']:
            entries = row.get('workflows', {})
            if set(entries) == A.METADATA_WORKFLOWS and entries.get(SOURCE_WORKFLOW) == old_source:
                generations[row['name']] = entries
                sources[row['name']] = old_helper
    else:
        generations['codeql-metadata-v1'] = {caller: {'mode': '100644', 'type': 'blob',
            'sha': '3a273057a38255ca368d3028594fb94227ba7c3b'}, SOURCE_WORKFLOW: old_source}
        sources['codeql-metadata-v1'] = old_helper
    policy = A.MetadataPolicy(A.positive(registered.get('id')), caller,
                              generations, sources)
    return policy, context


def schedule(event, environment, *, root=ROOT, adapter=None, clock=lambda: datetime.now(timezone.utc)):
    """Scheduling-only same-M observation. Pending and failed remain unchanged."""
    native_value = native(event, environment, root=root)
    require(environment.get('GITHUB_JOB') in {'recognize', 'route', 'select'}, 'unreviewed scheduling role')
    protected = _protected_readers(event, environment, native_value, root)
    A = protected[0]
    adapter = A.Adapter() if adapter is None else adapter
    binding, references = adapter.current(native_value['number'])
    require(binding['base_ref'] == event['pull_request']['base']['ref']
        and all(binding[key + '_sha'] == native_value[key] for key in ('head', 'merge'))
        and references['default_ref'] == 'main', 'scheduling live native candidate differs')
    caller = next(path for path in CALLERS if environment['GITHUB_WORKFLOW_REF'] ==
        REPOSITORY + '/' + path + '@' + environment['GITHUB_REF'])
    policy, context = _source_policy(root, adapter, binding, references, native_value, protected, caller=caller)
    labels = event['pull_request'].get('labels')
    require(type(labels) is list and all(type(row) is dict and type(row.get('name')) is str for row in labels),
            'scheduling native event label inventory unavailable')
    diagnostics = caller.endswith('/repository-checks.yml') and any(
        row['name'] == 'android-long-diagnostics' for row in labels)
    value = adapter.metadata_schedule(native_value['number'], native_value['run_id'], policy,
        diagnostics=diagnostics, now=clock())
    require(value['binding'] == binding and value['references'] == references
        and adapter.current(native_value['number']) == (binding, references)
        and _source_policy(root, adapter, binding, references, native_value,
            _protected_readers(event, environment, native_value, root), caller=caller) == (policy, context)
        and native(event, environment, root=root) == native_value, 'scheduling source changed before output')
    return value


def recognize(event, environment, *, root=ROOT):
    metadata = event_only(event, environment.get('GITHUB_EVENT_NAME'))
    result = {'kind': 'native-metadata-intent', 'metadata_edit': metadata,
              'metadata_intent': 'false', 'metadata_scheduling': 'false', 'qualification': False}
    intent = environment.get('NATIVE_NONPRODUCER_INTENT', '')
    require(intent in {'', 'false', 'true'}, 'invalid one-way native scheduling input')
    if intent == 'true':
        require(metadata and SOURCE_READY is True, 'native nonproducer intent cannot fall through to ordinary work')
    elif metadata and SOURCE_READY is True:
        require(False, 'inert native event has no reviewed nonproducer intent')
    if SOURCE_READY is not True or not metadata:
        return result
    require(environment.get('GITHUB_JOB') == 'recognize', 'marker requires its reviewed reusable job')
    native(event, environment, root=root)
    # A short bounded API wait allows the ordinary tiny source step to finish.
    # Unavailable proof never triggers a duplicate producer or analyzer run.
    for attempt in range(3):
        try:
            value = schedule(event, environment, root=root)
            return {**result, **value, 'metadata_intent': 'true', 'metadata_scheduling': 'true'}
        except ValueError as error:
            reader = sys.modules.get('producer_api')
            if reader is None or not isinstance(error, reader.SchedulingPending) or attempt == 2:
                raise
            time.sleep(2)


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
            output.write('metadata_scheduling=' + result['metadata_scheduling'] + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MetadataUnavailable, ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        print('Native metadata context unavailable; no retained qualification asserted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
