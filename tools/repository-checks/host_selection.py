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
import subprocess
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
    '.github/test-suites.json',
    '.github/ios-host-orchestration.json', '.github/ios-build-qualification.json',
    '.github/workflows/branch-cleanup.yml', '.github/workflows/branch-policy.yml',
    # Complete tuple validation runs before selection; arbitrary edits fail.
    '.github/workflows/project-tests.yml', '.github/workflows/codeql.yml',
    '.github/workflows/parent-qualification.yml',
    '.github/codeql/codeql-config.yml',
    '.github/workflows/browser-client.yml', '.github/workflows/browser-direct-client.yml',
    '.github/workflows/browser-client-atomic-settings.yml',
})
# Individually reviewed CI propagation inputs. The production harnesses do not
# import/read these controls or unit tests. Do not extend this to tools/** or
# tests/**: those roots also contain real product readers and import candidates.
CI_ROLLOUT_PATHS = frozenset({
    '.github/android-checks.json', '.github/android-orchestration.json',
    '.github/attested-runtime.json', '.github/sync-test-reuse.json',
    '.github/workflows/dependency-releases.yml', '.github/workflows/repository-checks.yml',
    '.github/workflows/repository-health.yml', '.github/workflows/sync-test-reuse.yml',
    '.github/workflows/sync-validation.yml',
    'tests/device/run_control_plane_tests.py', 'tests/host-producer-preparation-test.py',
    'tests/native-ci-test.py', 'tests/project-suite-self-test.py', 'tests/run-project-tests.py',
    'tools/native-tests/check.py',
    'tools/test-evidence/attested-test.py', 'tools/test-evidence/attested.py',
    'tools/test-evidence/execution-test.py', 'tools/test-evidence/execution.py',
    'tools/test-evidence/inputs.py', 'tools/test-evidence/producer-api-test.py',
    'tools/test-evidence/producer-test.py', 'tools/test-evidence/producer.py',
    'tools/test-evidence/producer_api.py', 'tools/test-evidence/qualification-producer-test.py',
    'tools/test-evidence/registry-test.py', 'tools/test-evidence/run.py',
    'tools/test-evidence/runtime-test.py', 'tools/test-evidence/runtime.py',
    'tools/test-evidence/test.py', 'tools/test-evidence/validate-sync-test.py',
    'tools/test-evidence/validate-sync.py',
})
# These product contracts do not consume the admitted CI inputs. Their source,
# helpers, fixtures, import/include membership AND definitions are bound below.
PRODUCT_QUICK_SUITES = frozenset({
    'codeql-remediation', 'javascript-behavior', 'server-console-behavior',
    'device-result-schema', 'device-jenkins', 'desktop-input-protocol', 'performance-contracts',
})
# Bind the actual reviewed readers, imports, discovery roots, and subprocess
# launchers. A new reader or historical child variant cannot silently inherit
# this exclusion; it requires a fresh review or executes the complete suite.
PROGRAM_INPUTS = (
    'tests/device', 'tests/device/**', 'tests/safe-landing', 'tests/safe-landing/**',
    'tests/run-unittest-suite.py', 'tests/run-project-tests.py', 'tests/platform-profile.json',
    'tests/requirements*.txt', 'interface', 'interface/**', 'libraries', 'libraries/**',
    'scripts', 'scripts/**', 'domain-server', 'domain-server/**', 'provenance', 'provenance/**', 'tools/sbom', 'tools/sbom/**',
    # These are execution controllers, not independent unit-test implementation.
    # Admission as a changed CI path does not remove them from the reader graph.
    'tools/test-evidence/attested.py', 'tools/test-evidence/execution.py',
    'tools/test-evidence/inputs.py', 'tools/test-evidence/producer.py',
    'tools/test-evidence/producer_api.py', 'tools/test-evidence/run.py',
    'tools/test-evidence/runtime.py', 'tools/test-evidence/validate-sync.py',
    # Actual assertions consume these documents; the generic Markdown rule does
    # not exempt them. Their membership, modes and bytes remain immutable inputs.
    'android/vr/common/openxr/README.md',
    'android/phone/device-tests/parity/fixtures/README.md',
)
# Main358937 and six main649 CI-only topic previews, preserving both child npm
# locks, product sources and profiles. These are reader identities, not passing
# test receipts. The changed control-plane launcher still selects its real owner.
REVIEWED_PROGRAMS = 'e5c142d70a46be66a725bcdf652c78dab1cf17346cf2c5020c0ba272cd8ba0b4'
REVIEWED_CHILD_PROGRAMS = {
    'apple-main': '8be34fee156fbac2fd1f82db5d1f526194afa457e028314eddbebf6a4227c078',
    'apple-ios': 'e8a35177e412e00bed9d0674842584e15bfee1f107e602618b7bdb28612cbb75',
    'android-main': 'a43c20a42b2990d9abb473c4419ffc6f6cd22e1b86eef3ee1d891c65f52d482e',
    'android-phone': '64823eb0cbc70a3fc65790b6f228b4df33136094e773862d717ab9b0639eddc8',
    'android-vr': '118fe7cb0d84e930a487e74a9ba7ad6cec8ba41a60d3f9e6a2b95e9cdf2d2baa',
    'android-vr-pico': '939f06ce47bb28c6efae3f97fdd26482a904b92286b5bb923cbbca082fcef79d',
}
CONTROL_PLANE = 'tests/device/run_control_plane_tests.py'
PACKAGE_LOCKS = {
    'browser-client/package-lock.json': ('browser-client', 'source-map-postcss-v1'),
    'script-archive/marketplace/S3Server/package-lock.json':
        ('script-archive/marketplace/S3Server', 'proxy-addr-express-v1'),
}


def package_owned_paths(plan):
    """Read only a trusted, independently recomputed package candidate plan.

    This is a dependency omission, never a package execution receipt. The
    required repository aggregate still requires the separate package owner.
    """
    if not isinstance(plan, dict) or plan.get('consumer_generation') is not True:
        return ()
    consumers = plan.get('dependency_profiles')
    if not isinstance(consumers, dict) or consumers.get('unknown') is not False \
            or consumers.get('base', {}).get('revision') != plan.get('base') \
            or consumers.get('candidate', {}).get('revision') != plan.get('candidate') \
            or consumers.get('candidate', {}).get('tree') != plan.get('tree'):
        return ()
    result = []
    for path, (project, profile) in PACKAGE_LOCKS.items():
        selected = consumers.get('projects', {}).get(project, {})
        if path not in plan.get('paths', ()) or selected.get('changed_paths') != [path]:
            continue
        focused = (selected.get('profile') == profile and selected.get('required') is True
                   and project in plan.get('package_set', ()))
        formatting = (selected.get('profile') == 'none' and selected.get('required') is False
                      and selected.get('reason') == 'reviewed-lockfile-format-only')
        if focused or formatting:
            result.append(path)
    return tuple(result)


def program_digest(tree, root=ROOT):
    # Persist the absence of unowned modules/headers too: checking just the
    # current delta would miss historical child search-path differences.
    if any(entry['mode'] not in {'100644', '100755'} or entry['type'] != 'blob' for entry in tree.values()):
        raise ValueError('host inventory contains an unreviewed nonregular input')
    owned = {entry['path'] for entry in inputs.selected_entries(tree, list(PROGRAM_INPUTS))}
    entries = [{'path': path, **entry} for path, entry in sorted(tree.items())
               if path in owned or not ci_owned(path)]
    if any(entry['mode'] not in {'100644', '100755'} or entry['type'] != 'blob' for entry in entries):
        raise ValueError('host program closure contains an unreviewed nonregular input')
    registry_entry = tree.get('.github/test-suites.json', {})
    if registry_entry.get('mode') != '100644' or registry_entry.get('type') != 'blob':
        raise ValueError('host suite registry is not an ordinary immutable blob')
    sha = registry_entry['sha']
    size = subprocess.check_output(['git', '--no-replace-objects', 'cat-file', '-s', sha], cwd=root, timeout=30)
    if int(size) > 1_000_000:
        raise ValueError('host registry is oversized')
    raw = subprocess.check_output(['git', '--no-replace-objects', 'cat-file', 'blob', sha], cwd=root, timeout=30)
    registry = inputs._validate_registry(json.loads(raw, object_pairs_hook=inputs._unique_object))
    definitions = {name: suite for name, suite in registry['suites'].items() if suite['layer'] == 'host' or name in PRODUCT_QUICK_SUITES}
    payload = {'programs': entries, 'host_definitions': definitions, 'controls': registry['control_inputs']}
    return hashlib.sha256((json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()).hexdigest()


def ci_owned(path):
    # Exact hyphenated test filenames are safe: admitting arbitrary tests/*.py
    # could introduce json.py/sitecustomize.py into a child interpreter path.
    return (path in CI_TESTS or path in CI_POLICY or path in CI_ROLLOUT_PATHS or path.startswith(CI_ROOTS)
            or path.endswith('.md') or path.endswith('.mdx'))


def select(tree, paths, regular, *, unknown=False, trusted_tree=None, candidate_root=ROOT,
           trusted_root=ROOT, target='main', base_tree=None, package_paths=()):
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    names = list(registry['suites'])
    reason = 'unowned-inputs'
    if not isinstance(package_paths, (tuple, list)) or any(path not in PACKAGE_LOCKS for path in package_paths):
        raise ValueError('host package normalization requires finite separately owned lock paths')
    if unknown or not regular or not paths:
        reason = 'unknown-or-nonregular-inventory'
    elif not all(isinstance(path, str) and (ci_owned(path) or path in package_paths) for path in paths):
        reason = 'unowned-inputs'
    else:
        try:
            # Keep the reviewed historical program identity. Only the separate
            # required npm owner covers these exact lock deltas; all other
            # candidate files and the trusted production reader graph stay bound.
            reviewed_tree = tree
            if package_paths:
                if base_tree is None or any(
                        not isinstance(snapshot.get(path), dict)
                        or snapshot[path].get('mode') != '100644'
                        or snapshot[path].get('type') != 'blob'
                        for snapshot in (tree, base_tree) for path in package_paths):
                    raise ValueError('package lock normalization requires ordinary inputs on both sides')
                reviewed_tree = dict(tree)
                for path in package_paths:
                    reviewed_tree[path] = dict(base_tree[path])
            expected = REVIEWED_PROGRAMS if target == 'main' else REVIEWED_CHILD_PROGRAMS.get(target)
            reviewed = expected is not None and program_digest(reviewed_tree, candidate_root) == expected
            if trusted_tree is not None:
                reviewed &= program_digest(trusted_tree, trusted_root) == REVIEWED_PROGRAMS
        except (ValueError, OSError, subprocess.SubprocessError):
            reviewed = False
        if reviewed:
            affected = CONTROL_PLANE in paths or (base_tree is not None and base_tree.get(CONTROL_PLANE) != tree.get(CONTROL_PLANE))
            result = {'suites': [name for name in names if (
                        registry['suites'][name]['layer'] == 'quick' and name not in PRODUCT_QUICK_SUITES
                        or affected and name == 'device-control-plane-full')],
                    'reason': 'reviewed-ci-with-control-plane-update' if affected else 'reviewed-ci-only-inputs',
                    'full_host': affected, 'include_platform': False}
            if package_paths:
                result['package_owned_paths'] = sorted(package_paths)
                result['reason'] = ('reviewed-ci-control-plane-and-package-owners' if affected
                                    else 'reviewed-ci-and-package-owners')
            return result
        reason = 'host-reader-generation-not-reviewed'
    return {'suites': names, 'reason': reason, 'full_host': True, 'include_platform': True}


def target_branch(event):
    """Read the target from the same server event validated by candidate_plan."""
    pr = event.get('pull_request')
    if isinstance(pr, dict):
        return (pr.get('base') or {}).get('ref')
    ref = event.get('ref')
    return ref[len('refs/heads/'):] if isinstance(ref, str) and ref.startswith('refs/heads/') else None


def additional_suites(candidate_registry, registry):
    """Monotonically add new candidate commands; never replace a trusted check."""
    environments = {suite['environment'] for suite in registry['suites'].values()}
    seen = {(tuple(suite['command']), suite['environment']) for suite in registry['suites'].values()}
    additions = []
    for name, suite in candidate_registry['suites'].items():
        key = (tuple(suite['command']), suite['environment'])
        if key in seen:
            continue  # One actual command/context serves duplicate definitions.
        if suite['environment'] not in environments or suite['command'][0] not in {'python', 'node', 'bash'}:
            raise ValueError('new test context requires a reviewed host owner')
        seen.add(key)
        suffix = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
        additions.append((name + '-candidate-' + suffix, suite['layer'], suite['command']))
    return additions


def candidate_registry(candidate):
    path = candidate / '.github/test-suites.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError('candidate test registry must be a bounded ordinary file')
    return inputs.load_registry(path)


def package_policy():
    spec = importlib.util.spec_from_file_location('host_packages', ROOT / 'tools/repository-checks/package_checks.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--expected-plan', required=True)
    parser.add_argument('--junit', type=Path)
    parser.add_argument('--select-only', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--selection-report', type=Path)
    args = parser.parse_args()
    try:
        package = execution._runner()  # Trusted process cleanup/timeouts, never candidate runner code.
        policy = package_policy()
        candidate = args.candidate.resolve(strict=True)
        before = execution.checkout_identity(candidate)
        policy.validate_wiring(candidate)
        event = json.loads(args.event.read_text())
        plan = policy.candidate_plan(candidate, event, args.sha)
        if plan['candidate'] != before[0] or plan['plan'] != args.expected_plan or plan['host_mode'] != 'full':
            raise ValueError('host execution differs from the independently recomputed required plan')
        base_tree = inputs.full_tree(candidate, plan['base']) if plan.get('base') and not plan['unknown'] else None
        selected = select(inputs.full_tree(candidate, before[0]), plan['paths'], plan['regular'],
                          unknown=plan['unknown'], trusted_tree=inputs.full_tree(ROOT, 'HEAD'),
                          candidate_root=candidate, target=target_branch(event), base_tree=base_tree,
                          package_paths=package_owned_paths(plan))
        registry = inputs.load_registry(ROOT / '.github/test-suites.json')
        additions = additional_suites(candidate_registry(candidate), registry)
        if additions:
            selected = {'suites': list(registry['suites']), 'full_host': True,
                        'reason': 'new-or-changed-test-command-requires-full-verification', 'include_platform': True}
        selected['additional_suites'] = [name for name, _, _ in additions]
        platform = execution.platform_suites(candidate, registry['suites'])
        selected['platform_suites'] = [name for name, _ in platform] if selected['include_platform'] else []
        selected['omitted_platform_suites'] = [name for name, _ in platform] if not selected['include_platform'] else []
        complete_receipt = (set(selected['suites']) == set(registry['suites']) and not additions
                            and selected['include_platform'])
        print(json.dumps(selected, sort_keys=True), flush=True)
        if args.selection_report is not None:
            report = {'schema': 1, 'kind': 'host-impact-selection', 'reusable': False,
                      'candidate': before[0], 'tree': before[1], 'package_plan': plan['plan'],
                      'selection': selected,
                      'omitted_suites': [name for name in registry['suites'] if name not in selected['suites']],
                      'complete_receipt_required': complete_receipt}
            args.selection_report.parent.mkdir(parents=True, exist_ok=True)
            args.selection_report.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
        if args.select_only:
            if args.output is None:
                raise ValueError('selection requires its step output path')
            with args.output.open('a') as output:
                output.write('full_host=' + str(selected['full_host']).lower() + '\n')
                output.write('complete_receipt=' + str(complete_receipt).lower() + '\n')
            return 0
        if args.junit is None:
            raise ValueError('host execution requires a test report path')
        registry = inputs.load_registry(ROOT / '.github/test-suites.json')
        suites = [package.Suite(name, registry['suites'][name]['layer'], tuple(
            sys.executable if index == 0 and value == 'python' else value
            for index, value in enumerate(registry['suites'][name]['command']))) for name in selected['suites']]
        suites += [package.Suite(name, layer, tuple(
            sys.executable if index == 0 and value == 'python' else value for index, value in enumerate(command)))
            for name, layer, command in additions]
        suites += [package.Suite(name, 'quick', tuple(
            sys.executable if index == 0 and value == 'python' else value for index, value in enumerate(command)))
            for name, command in platform if selected['include_platform']]
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
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'Host selection failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
