#!/usr/bin/env python3
"""Select reviewed host dependencies using trusted policy and immutable Git trees.

This is impact selection, not a claim that an omitted suite passed or that an
old artifact was built from this candidate. Unowned inputs retain the full gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import signal
import importlib.util
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/test-evidence'))
import execution
import inputs

# These tools are not imported, executed, discovered, or read by the reviewed
# production host contracts. Their own regression tests remain selected below.
CI_ROOTS = (
    'tools/branch-cleanup/', 'tools/branch-policy/', 'tools/repository-checks/',
    'tools/repository-policy/', 'tools/repository-maintenance/', 'tools/repository-health/',
    'tools/sync-test-reuse/', 'tools/workflow-security/', 'tools/issue-intake/',
    'tools/dependency-releases/', 'tools/ios-build-qualification/',
)
CI_TESTS = frozenset({
    'tests/branch-cleanup-test.py', 'tests/branch-policy-test.py', 'tests/branch-name-guard-test.py',
    'tests/repository-checks-test.py', 'tests/repository-policy-test.py',
    'tests/repository-maintenance-test.py', 'tests/repository-health-test.py',
    'tests/workflow-contract-test.py', 'tests/workflow-action-pin-test.py',
    'tests/issue-intake-test.py', 'tests/android-ci-test.py', 'tests/android-orchestration-test.py',
    'tests/android-build-inputs-test.py', 'tests/ios-build-qualification-test.py',
    'tests/ios-input-selection-test.py', 'tests/codeql-selection-test.py',
    'tests/browser-cpu-selection-test.py', 'tests/host-selection-test.py',
})
CI_POLICY = frozenset({
    '.github/branch-policy.json', '.github/branch-cleanup.json', '.github/issue-policy.json',
    '.github/repository-checks.json', '.github/package-workflow-generations.json',
    '.github/ios-host-orchestration.json', '.github/ios-build-qualification.json',
    '.github/workflows/branch-cleanup.yml', '.github/workflows/branch-policy.yml',
    '.github/workflows/browser-client.yml', '.github/workflows/browser-direct-client.yml',
    '.github/workflows/browser-client-atomic-settings.yml',
})
# Bind the actual reviewed readers, imports, discovery roots, and subprocess
# launchers. A new reader or historical child variant cannot silently inherit
# this exclusion; it requires a fresh review or executes the complete suite.
PROGRAM_INPUTS = (
    'tests/device', 'tests/device/**', 'tests/safe-landing', 'tests/safe-landing/**',
    'tests/run-unittest-suite.py', 'tests/run-project-tests.py', 'tests/platform-profile.json',
    'tests/requirements*.txt', 'interface', 'interface/**', 'libraries', 'libraries/**',
    'scripts', 'scripts/**', 'domain-server', 'domain-server/**', 'provenance', 'provenance/**', 'tools/sbom', 'tools/sbom/**',
)
REVIEWED_PROGRAMS = 'd89fecb2c53a13e43556cc5ccf6e481e5fbfb933a20ba14dbb01f9a7f7e4953c'


def program_digest(tree):
    entries = inputs.selected_entries(tree, list(PROGRAM_INPUTS))
    if any(entry['mode'] not in {'100644', '100755'} or entry['type'] != 'blob' for entry in entries):
        raise ValueError('host program closure contains an unreviewed nonregular input')
    return hashlib.sha256((json.dumps(entries, sort_keys=True, separators=(',', ':')) + '\n').encode()).hexdigest()


def ci_owned(path):
    # Exact hyphenated test filenames are safe: admitting arbitrary tests/*.py
    # could introduce json.py/sitecustomize.py into a child interpreter path.
    return (path in CI_TESTS or path in CI_POLICY or path.startswith(CI_ROOTS)
            or path.endswith('.md') or path.endswith('.mdx'))


def select(tree, paths, regular, *, unknown=False, trusted_tree=None):
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    names = list(registry['suites'])
    reason = 'unowned-inputs'
    if unknown or not regular or not paths:
        reason = 'unknown-or-nonregular-inventory'
    elif not all(isinstance(path, str) and ci_owned(path) for path in paths):
        reason = 'unowned-inputs'
    else:
        try:
            reviewed = program_digest(tree) == REVIEWED_PROGRAMS
            if trusted_tree is not None:
                reviewed &= program_digest(trusted_tree) == REVIEWED_PROGRAMS
        except (ValueError, inputs.InputError):
            reviewed = False
        if reviewed:
            return {'suites': [name for name in names if registry['suites'][name]['layer'] == 'quick'],
                    'reason': 'reviewed-ci-only-inputs', 'full_host': False}
        reason = 'host-reader-generation-not-reviewed'
    return {'suites': names, 'reason': reason, 'full_host': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--expected-plan', required=True)
    parser.add_argument('--junit', type=Path)
    parser.add_argument('--select-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        package = execution._runner()  # Trusted process cleanup/timeouts, never candidate runner code.
        spec = importlib.util.spec_from_file_location('host_packages', ROOT / 'tools/repository-checks/package_checks.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        candidate = args.candidate.resolve(strict=True)
        before = execution.checkout_identity(candidate)
        policy.validate_wiring(candidate)
        plan = policy.candidate_plan(candidate, json.loads(args.event.read_text()), args.sha)
        if plan['candidate'] != before[0] or plan['plan'] != args.expected_plan or plan['host_mode'] != 'full':
            raise ValueError('host execution differs from the independently recomputed required plan')
        selected = select(inputs.full_tree(candidate, before[0]), plan['paths'], plan['regular'],
                          unknown=plan['unknown'], trusted_tree=inputs.full_tree(ROOT, 'HEAD'))
        print(json.dumps(selected, sort_keys=True), flush=True)
        if args.select_only:
            if args.output is None:
                raise ValueError('selection requires its step output path')
            with args.output.open('a') as output:
                output.write('full_host=' + str(selected['full_host']).lower() + '\n')
            return 0
        if args.junit is None:
            raise ValueError('host execution requires a test report path')
        registry = inputs.load_registry(ROOT / '.github/test-suites.json')
        suites = [package.Suite(name, registry['suites'][name]['layer'], tuple(
            sys.executable if index == 0 and value == 'python' else value
            for index, value in enumerate(registry['suites'][name]['command']))) for name in selected['suites']]
        suites += [package.Suite(name, 'quick', tuple(
            sys.executable if index == 0 and value == 'python' else value for index, value in enumerate(command)))
            for name, command in execution.platform_suites(candidate, registry['suites'])]
        package.ROOT = candidate
        cancelled = []
        def interrupted(signum, _frame):
            if not cancelled:
                cancelled.append(signum)
        previous = {signum: signal.signal(signum, interrupted) for signum in (signal.SIGINT, signal.SIGTERM)}
        try:
            with execution.candidate_process_environment():
                status = package.run_suites(SimpleNamespace(timeout=240, host_timeout=900, native_build_dir=None,
                                           junit=args.junit, fail_fast=False), suites, cancelled)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        if execution.checkout_identity(candidate) != before:
            raise ValueError('host execution changed the candidate')
        return status
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Host selection failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
