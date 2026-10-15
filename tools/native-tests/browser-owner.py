#!/usr/bin/env python3
"""Conditionally delegate reviewed frontend inputs to required Browser checks.

This controller and its finite inventory come from trusted policy. Candidate
data never enables the owner, changes the allowlist or refreshes reader anchors.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PROFILE = '.github/browser-native-ownership.json'
REPOSITORY = {'full_name': 'noah-l-frank/overte', 'id': 1319052603}
SUFFIXES = frozenset({'.ts', '.mts', '.js', '.mjs', '.css', '.html'})
BOOTSTRAP_INPUTS = frozenset({
    'tools/native-tests/check.py', 'tools/native-tests/select.py',
    'tools/native-tests/browser-owner.py', 'tests/native-ci-test.py',
    'tools/native-tests/README.md',
})
SHA = re.compile(r'[0-9a-f]{40}\Z')


def require(value, message):
    if not value:
        raise ValueError(message)


def ordinary(entry):
    return (isinstance(entry, dict) and set(entry) == {'mode', 'type', 'sha'}
            and entry['mode'] in {'100644', '100755'} and entry['type'] == 'blob'
            and isinstance(entry['sha'], str) and SHA.fullmatch(entry['sha']))


def load_profile():
    path = ROOT
    for component in PurePosixPath(PROFILE).parts:
        path /= component
        require(not path.is_symlink(), 'trusted Browser ownership profile is aliased')
    require(path.is_file() and path.stat().st_size <= 200_000, 'trusted Browser ownership profile unavailable')
    raw = path.read_bytes()
    require(len(raw) <= 200_000, 'oversized Browser ownership profile')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate Browser ownership policy field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict) and set(value) == {
        'schema', 'repository', 'reviewed_revision', 'reader_boundary', 'paths', 'bootstrap_inputs'},
        'invalid Browser ownership policy fields')
    require(type(value['schema']) is int and value['schema'] == 1 and value['repository'] == REPOSITORY,
            'foreign Browser ownership policy')
    require(isinstance(value['reviewed_revision'], str) and SHA.fullmatch(value['reviewed_revision'])
            and isinstance(value['reader_boundary'], str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', value['reader_boundary']), 'unreviewed ordinary reader identity')
    paths = value['paths']
    require(isinstance(paths, list) and 1 <= len(paths) <= 1000 and all(isinstance(path, str) for path in paths)
            and paths == sorted(set(paths)), 'invalid frozen Browser path inventory')
    for name in paths:
        path = PurePosixPath(name)
        require(name.startswith('browser-client/') and path.as_posix() == name and '..' not in path.parts
                and '\\' not in name and '\0' not in name and path.suffix in SUFFIXES,
                'unsupported Browser ownership path')
    controls = value['bootstrap_inputs']
    require(isinstance(controls, dict) and set(controls) == BOOTSTRAP_INPUTS, 'unknown ownership reader normalization')
    for row in controls.values():
        require(isinstance(row, dict) and set(row) == {'before', 'after'}
                and (row['before'] is None or ordinary(row['before'])) and ordinary(row['after']),
                'ownership readers require exact ordinary source identities')
    return value, 'sha256:' + hashlib.sha256(raw).hexdigest()


def owned_paths():
    """Static collision inventory for CMake's independent configured-input guard."""
    return frozenset(load_profile()[0]['paths'])


def reader_boundary(snapshot, profile, browser):
    excluded = set(profile['paths']) | set(browser.CPU_PATHS) | set(browser.PACKAGE_PATHS) | {
        browser.WORKFLOW, browser.OUTER_WORKFLOW, browser.CONFIGURATION, PROFILE}
    rows = []
    for path, original in sorted(snapshot['entries'].items()):
        # Mode and alias changes never disappear behind a path exception.
        if path in excluded and original['mode'] == '100644' and original['type'] == 'blob':
            continue
        entry = original
        normalization = profile['bootstrap_inputs'].get(path)
        if normalization and entry == normalization['after']:
            entry = normalization['before']
            if entry is None:
                continue
        rows.append({'path': path, **entry})
    return browser.digest({'domain': 'overte-required-browser-ordinary-reader-boundary-v1', 'entries': rows})


def select(candidate, event, sha, paths, regular, checks):
    """Return evidence for a possible omission; callers retain native fallback.

    The Browser final aggregate independently enforces this same candidate and
    plan. Omission is eligible only after trusted target activation, with both
    full Browser jobs required and both immutable reader trees reviewed.
    """
    fallback = {'paths': [], 'reason': 'required Browser ownership unavailable'}
    if not regular or not isinstance(event.get('pull_request'), dict):
        return fallback
    try:
        profile, identity = load_profile()
        proposed = sorted(set(paths) & set(profile['paths']))
        if not proposed:
            return {'paths': [], 'reason': 'no newly delegated Browser inputs'}
        browser = checks.browser_policy()
        if not browser.activated(event, 'pull_request'):
            return {'paths': [], 'reason': 'Browser owner is advisory or inactive for target'}
        plan = browser.route(event, 'pull_request', candidate, sha)
        require(plan['mode'] == 'full', 'Browser full owner is not selected')
        previous = browser.snapshot(candidate, event['pull_request']['base']['sha'])
        current = browser.snapshot(candidate, sha)
        packages = checks.package_policy()
        for tree in (previous, current):
            browser.validate_wiring(tree)
            packages.validate_tree_wiring(tree['entries'])
            require(all(ordinary(entry) for entry in tree['entries'].values()), 'nonregular ordinary reader inventory')
            require(reader_boundary(tree, profile, browser) == profile['reader_boundary'],
                    'ordinary reader boundary is stale or not reviewed')
        changed = {path for path in previous['entries'].keys() | current['entries'].keys()
                   if previous['entries'].get(path) != current['entries'].get(path)}
        require(changed == set(paths), 'Browser/native exact change inventories differ')
        for path in proposed:
            require(all(entry is None or (entry['mode'] == '100644' and entry['type'] == 'blob')
                        for entry in (previous['entries'].get(path), current['entries'].get(path))),
                    'Browser source mode requires ordinary native fallback')
        return {'paths': proposed, 'reason': 'exact inputs delegated to required full Browser owner',
                'owner': 'browser-client', 'candidate': sha, 'tree': plan['tree'], 'target': plan['target'],
                'browser_plan': plan['plan'], 'policy': identity}
    except (ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.SubprocessError):
        # Missing policy/capability, incomplete wiring and uncertain dependency
        # closure retain ordinary full validation. They never authorize a skip.
        return fallback
