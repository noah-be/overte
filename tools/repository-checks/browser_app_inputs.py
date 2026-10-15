#!/usr/bin/env python3
"""Dormant separation of ordinary app readers and required Browser policy.

The finite ledger comes only from trusted policy. Hashing a proposal is not
approval: both the source guard and a separately reviewed identity are required.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parents[2]
POLICY = '.github/browser-native-app-inputs.json'
REPOSITORY = {'full_name': 'noah-l-frank/overte', 'id': 1319052603}
DOMAIN = 'overte-required-browser-ordinary-app-readers-v2'
# A candidate/trusted JSON marker cannot approve this new dependency boundary.
ACTIVATION_READY = False
CODE_INPUTS = (
    'tools/native-tests/browser-owner.py', 'tools/native-tests/check.py',
    'tools/native-tests/select.py', 'tools/repository-checks/browser_app_inputs.py',
    'tools/repository-checks/browser_cpu.py', 'tools/repository-checks/check.py',
    'tools/repository-checks/package_checks.py', 'tools/repository-checks/tool_dependencies.py',
    'tools/repository-checks/android.py', 'tools/repository-checks/android_gate.py',
    'tools/repository-checks/android_handoff.py',
    'tools/ios-build-qualification/check.py', 'tools/ios-build-qualification/inputs.py',
    'tools/test-evidence/validate-sync.py', 'tools/sync-test-reuse/gate.py',
    'tools/sync-test-reuse/differential.py', 'tools/branch-policy/check.py',
    'tools/repository-checks/android-host-prepare.sh',
)
POLICY_INPUTS = (
    POLICY, '.github/browser-native-ownership.json', '.github/android-checks.json',
    '.github/android-orchestration.json', '.github/android-owner-transfer.json',
    '.github/ios-build-qualification.json',
    '.github/sync-test-reuse.json',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate trusted app-reader policy field')
        result[key] = value
    return result


def policy(read, policy_root):
    value = json.loads(read(POLICY, policy_root), object_pairs_hook=unique)
    require(isinstance(value, dict) and set(value) == {
        'schema', 'repository', 'enabled', 'reviewed_ci_revision', 'reader_boundary', 'ci_paths'},
        'invalid trusted app-reader policy fields')
    require(type(value['schema']) is int and value['schema'] == 1 and value['repository'] == REPOSITORY
            and type(value['repository'].get('id')) is int and type(value['enabled']) is bool,
            'invalid trusted app-reader policy identity')
    require(isinstance(value['reviewed_ci_revision'], str)
            and re.fullmatch(r'[0-9a-f]{40}', value['reviewed_ci_revision']), 'invalid CI classification review')
    require(value['reader_boundary'] is None or isinstance(value['reader_boundary'], str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', value['reader_boundary']), 'invalid app-reader approval')
    paths = value['ci_paths']
    require(isinstance(paths, dict) and 1 <= len(paths) <= 256, 'invalid finite CI classification inventory')
    for name, mode in paths.items():
        require(isinstance(name, str) and name and '\\' not in name and '\0' not in name
                and str(PurePosixPath(name)) == name and not PurePosixPath(name).is_absolute()
                and '..' not in PurePosixPath(name).parts and not any(char in name for char in '*?[]')
                and isinstance(mode, str) and mode in {'100644', '100755'},
                'invalid exact CI path or mode')
        require(name.startswith(('tools/branch-cleanup/', 'tools/test-evidence/', 'tools/repository-checks/'))
                or name.startswith(('tests/', 'docs/')) and len(PurePosixPath(name).parts) == 2
                or name in {POLICY, '.github/attested-runtime.json', '.github/package-workflow-generations.json',
                            '.github/shared-sandbox.json', '.github/test-suites.json',
                            '.github/workflows/branch-cleanup.yml'},
                'CI classification cannot enter an application or ambient import root')
        require(PurePosixPath(name).name not in {'CMakeLists.txt', 'conanfile.py', 'conan.lock',
                                               'package.json', '.gitmodules', '.gitattributes'}
                and PurePosixPath(name).suffix.lower() not in {
                    '.cmake', '.qrc', '.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx'},
                'build or native input cannot be classified as CI-only')
    return value


def enabled(read, policy_root):
    if not ACTIVATION_READY:
        return False
    value = policy(read, policy_root)
    if not value['enabled']:
        return False
    require(value['reader_boundary'] is not None, 'enabled app boundary has no protected reader approval')
    return True


def ci_paths(browser, policy_root):
    """Static collision inventory, including while the new selection is off."""
    return frozenset(policy(browser.trusted_bytes, policy_root)['ci_paths'])


def boundary(snapshot, profile, browser, policy_root):
    """Return a domain-separated proposal, without granting an omission."""
    browser.inventory()._validate_tree(snapshot['entries'])
    ledger = policy(browser.trusted_bytes, policy_root)['ci_paths']
    excluded = set(profile['paths']) | set(browser.CPU_PATHS) | set(browser.PACKAGE_PATHS) | {
        browser.WORKFLOW, browser.OUTER_WORKFLOW, browser.CONFIGURATION, '.github/browser-native-ownership.json'}
    rows = []
    for name, original in sorted(snapshot['entries'].items()):
        if original['type'] == 'blob' and (
                name in excluded and original['mode'] == '100644'
                or original['mode'] == ledger.get(name)):
            continue
        entry = original
        normalization = profile['bootstrap_inputs'].get(name)
        if normalization and entry == normalization['after']:
            entry = normalization['before']
            if entry is None:
                continue
        rows.append({'path': name, **entry})
    return digest({'domain': DOMAIN, 'entries': rows})


def owner_sources(policy_root):
    """Bind current trusted validators separately from app dependency contents.

    The existing package map includes its actual helper/recursive requirements
    graph. Additional sources cover native delegation, Browser inner/outer and
    the other validators reachable from the approved combined outer callers.
    """
    package_path = ROOT / 'tools/repository-checks/package_checks.py'
    spec = importlib.util.spec_from_file_location('browser_owner_package_identity', package_path)
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    package.ROOT = Path(policy_root)
    sources = package._policy_inputs()
    # Code executes from ROOT, even when a separate trusted fixture supplies
    # policy/templates. Do not fingerprint a policy mirror in place of code.
    code_reader = importlib.util.spec_from_file_location('browser_owner_actual_code', package_path)
    actual = importlib.util.module_from_spec(code_reader)
    code_reader.loader.exec_module(actual)
    for name in CODE_INPUTS:
        sources[name] = hashlib.sha256(actual._trusted_bytes(name, git_fallback=True)).hexdigest()
    for name in list(sources):
        if name.startswith('tools/test-evidence/') or name in {
                'tests/run-project-tests.py', 'tools/sync-test-reuse/qualification.py'}:
            sources[name] = hashlib.sha256(actual._trusted_bytes(name, git_fallback=True)).hexdigest()
    for name in POLICY_INPUTS:
        sources[name] = hashlib.sha256(package._trusted_bytes(name, git_fallback=True)).hexdigest()
    templates = {
        'tools/repository-checks/workflows/browser-client.yml',
        'tools/repository-checks/workflows/browser/repository-checks.yml',
        'tools/repository-checks/workflows/browser-direct-client.yml',
        'tools/repository-checks/workflows/repository-checks.yml',
    }
    android = json.loads(package._trusted_bytes('.github/android-orchestration.json'))
    for generation in android['workflow_generations']:
        templates.update(value for key, value in generation.items() if key != 'name')
    transfer = json.loads(package._trusted_bytes('.github/android-owner-transfer.json'))
    for group in ('legacy_workflows', 'source_contracts'):
        templates.update(row['source'] for row in transfer[group].values())
    for name in templates:
        require(isinstance(name, str) and str(PurePosixPath(name)) == name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                'canonical owner input must stay within trusted policy')
        sources[name] = hashlib.sha256(package._trusted_bytes(name, git_fallback=True)).hexdigest()
    return sources


def owner_identity(policy_root):
    return digest({'domain': 'overte-required-browser-current-owner-v1', 'sources': owner_sources(policy_root)})


def validate_owner_inventory(snapshot, validate_tree, policy_root):
    """A content exemption cannot remove or alias a required owner input."""
    validate_tree(snapshot['entries'])
    for name in owner_sources(policy_root):
        entry = snapshot['entries'].get(name)
        mode = '100755' if name == 'tests/run-project-tests.py' else '100644'
        require(isinstance(entry, dict) and entry['mode'] == mode and entry['type'] == 'blob',
                'required Browser owner input is missing or has an unreviewed mode: ' + name)
