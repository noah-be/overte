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
    'tests/browser-cpu-selection-test.py', 'tests/host-selection-test.py', 'tests/android-owner-transfer-test.py',
    'tests/unittest-runner-test.py',
})
CI_POLICY = frozenset({
    '.github/test-suite-dependencies.json',
    '.github/branch-policy.json', '.github/branch-cleanup.json', '.github/issue-policy.json',
    '.github/repository-checks.json', '.github/package-workflow-generations.json',
    '.github/test-suites.json',
    '.github/ios-host-orchestration.json', '.github/ios-build-qualification.json',
    '.github/workflows/branch-cleanup.yml', '.github/workflows/branch-policy.yml',
    # Complete tuple validation runs before selection; arbitrary edits fail.
    '.github/workflows/project-tests.yml', '.github/workflows/codeql.yml',
    '.github/workflows/android-required.yml',
    '.github/workflows/parent-qualification.yml',
    '.github/codeql/codeql-config.yml',
    '.github/workflows/browser-client.yml', '.github/workflows/browser-direct-client.yml',
    '.github/workflows/browser-client-atomic-settings.yml',
})
# Individually reviewed CI propagation inputs. The production harnesses do not
# import/read these controls or unit tests. Do not extend this to tools/** or
# tests/**: those roots also contain real product readers and import candidates.
CI_ROLLOUT_PATHS = frozenset({
    '.github/workflows/documentation-checks.yml',
    '.github/workflows/workflow-security.yml',

    '.github/workflows/documentation-push-owner.yml',
    'tools/test-evidence/source_admission.py',
    'tools/test-evidence/source-admission-test.py',
    'tools/test-evidence/affected-test.py',
    ".github/workflows/pr-metadata-context.yml",
    '.github/android-checks.json', '.github/android-orchestration.json', '.github/android-owner-transfer.json',
    '.github/attested-runtime.json', '.github/sync-test-reuse.json', '.github/ci37-runtime.json',
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
    # Fixed CI boundary diagnostics and their owning controls; these paths are
    # not product sources. Actual controller bytes stay bound below.
    '.github/shared-sandbox.json', '.github/workflows/shared-sandbox-host-diagnostic.yml',
    'tools/test-evidence/sandbox-test.py', 'tools/test-evidence/sandbox-host-test.py',
    'tools/test-evidence/sandbox.py', 'tools/test-evidence/sandbox_host.py',
    'tools/test-evidence/sandbox_host_fixture.py', 'tools/test-evidence/sandbox_probe.py',
    'tools/test-evidence/sandbox_shared.py',
    'tools/test-evidence/producer_workflow.py', 'tools/test-evidence/postmerge.py',
    'tools/test-evidence/ci_profile.py', 'tools/test-evidence/ci-profile-test.py',
    'tools/test-evidence/runtime_ci.py', 'tools/test-evidence/runtime-ci-test.py',
    'tools/test-evidence/ci-integration-test.py',
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
    '.github/shared-sandbox.json', 'tools/test-evidence/sandbox.py',
    'tools/test-evidence/sandbox_host.py', 'tools/test-evidence/sandbox_host_fixture.py',
    'tools/test-evidence/sandbox_probe.py',
    'tools/test-evidence/sandbox_shared.py',
    'tools/test-evidence/producer_workflow.py',
    'tools/test-evidence/postmerge.py',
    'tools/test-evidence/source_admission.py',
    # The CI37 policy is independently CI-owned data: protected admission binds
    # its exact ordinary entry and bytes. Including its generation here would
    # cycle through this file's REVIEWED_PROGRAMS and the complete CI37 tree.
    'tools/test-evidence/ci_profile.py',
    'tools/test-evidence/runtime_ci.py',
    'tools/repository-checks/workflows/producers/protected-project-tests.yml',
    'tools/repository-checks/workflows/producers/repository-checks.yml',
    'tools/repository-checks/workflows/producers/parent-qualification.yml',
    'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
    'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
    # Actual assertions consume these documents; the generic Markdown rule does
    # not exempt them. Their membership, modes and bytes remain immutable inputs.
    'android/vr/common/openxr/README.md',
    'android/phone/device-tests/parity/fixtures/README.md',
)
# Reviewed complete parent merges at protected main 19636184 and the
# prospective sole-owner generation. Shared execution controllers and passive
# runner instrumentation remain bound; Android additionally binds all six exact
# legacy-retirement/contract handoff files. Only the two separately owned foreign
# locks are outside this complement; changed locks need mandatory package coverage.
# These identities are not execution receipts or application-build evidence.
REVIEWED_PROGRAMS = 'b547c26d4c952ec34fd47688afc134bcf2c933566c3c3647ed5049e7c4226ff3'
REVIEWED_CHILD_PROGRAMS = {
    'apple-main': 'dc2869615e57eb0f3fc24cfc78684d67238867299d75e70f42414714bb1bbc71',
    'apple-ios': 'c4c9f5fbbf38e227e3cceac49ffea37e53fdab14a1835c2d31bf75437f65b45e',
    'android-main': 'a1465b1a06466d785f42c105370254a257509d565879190f537b076fcd6dcb9d',
    'android-phone': '9c6dc165db7d265f212665d857bb8c961cc24db524198723226a4a136ebeb297',
    'android-vr': 'a1465b1a06466d785f42c105370254a257509d565879190f537b076fcd6dcb9d',
    'android-vr-pico': '1cf99bff17e489284b312d9aaf0533f250b0d3b1607df64487473ad5c8e8a6bc',
}
REVIEWED_PREDECESSORS = {
    'main': '0644bec55de2d979b7a406f54e96960e44d50961b1fc43e2f73fac739658b799',
    'apple-main': '4f317ee1df2e619b1465605751f472fa555fad68a13fd7a739139057c63c3fd0',
    'apple-ios': 'c284b211104288ddb08ed34d63b22bf0b9e515feb301bec0573c2a150d744022',
    'android-main': '6e2fa5e9ed95ead952fd9ae6e50b6d9ba524641b832ca847779ae4b0306b245f',
    'android-phone': '085ad53b6f0c99c4ac6a0323d9f0b545b4f31c8244730376d9b1aa89ce1cf518',
    'android-vr': '6e2fa5e9ed95ead952fd9ae6e50b6d9ba524641b832ca847779ae4b0306b245f',
    'android-vr-pico': 'd664c6fcb84a98e584781be64eb7d3b7ebfe75e4ca5e44504fa25cca9afbfd97',
}
CONTROL_PLANE = 'tests/device/run_control_plane_tests.py'
PACKAGE_LOCKS = {
    'browser-client/package-lock.json': ('browser-client', 'source-map-postcss-v1'),
    'script-archive/marketplace/S3Server/package-lock.json':
        ('script-archive/marketplace/S3Server', 'proxy-addr-express-v1'),
}
CI_EXECUTABLE_PATHS = frozenset({
    'tests/project-suite-self-test.py', 'tests/repository-health-test.py',
    'tests/run-project-tests.py',
})


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
        # Native reader independence does not depend on the particular npm
        # security update. An unsupported focused delta retains the package's
        # complete required JavaScript owner, without widening native work.
        focused = (selected.get('profile') in {profile, 'full'} and selected.get('required') is True
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
    if any(entry['mode'] != '100644' or entry['type'] != 'blob'
           for path, entry in tree.items() if path in PACKAGE_LOCKS):
        raise ValueError('separate package locks must remain ordinary non-executable blobs')
    owned = {entry['path'] for entry in inputs.selected_entries(tree, list(PROGRAM_INPUTS))}
    entries = [{'path': path, **entry} for path, entry in sorted(tree.items())
               if path not in PACKAGE_LOCKS and (path in owned or not ci_owned(path))]
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


def _regular_ci_delta(tree, base_tree, paths, package_paths):
    """Distinguish reviewed CI executables from documentation-safe inputs.

    The ordinary package/router flag intentionally rejects every executable.
    This separate proof admits only the finite unchanged executable modes,
    binds the complete actual delta, and keeps package ownership independent.
    """
    if not isinstance(base_tree, dict) or not isinstance(tree, dict) or not paths:
        return False
    changed = {path for path in base_tree.keys() | tree.keys()
               if base_tree.get(path) != tree.get(path)}
    if changed != set(paths) or not changed & CI_EXECUTABLE_PATHS:
        return False
    if any(not (ci_owned(path) or path in package_paths) for path in changed):
        return False
    for path in changed:
        old, new = base_tree.get(path), tree.get(path)
        expected = '100755' if path in CI_EXECUTABLE_PATHS else '100644'
        if path in CI_EXECUTABLE_PATHS and (old is None or new is None):
            return False
        for entry in (old, new):
            if entry is not None and (entry.get('mode') != expected or entry.get('type') != 'blob'):
                return False
    return True


def regular_ci_inventory(plan, base_tree, candidate_tree):
    """Use only an independently recomputed complete trusted package plan."""
    if not isinstance(plan, dict) or plan.get('unknown') is not False:
        return False
    return plan.get('regular') is True or _regular_ci_delta(
        candidate_tree, base_tree, plan.get('paths', ()), package_owned_paths(plan))


def _protected_producer_transition(tree, paths, base_tree, trusted_tree, target):
    """Widen only the complete reviewed legacy-to-producer installation once.

    This is selection, never activation or execution evidence. The ordinary
    complete-tuple wiring check still runs independently before selection.
    """
    producer_endpoints = {'.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'}
    metadata_endpoints = {*producer_endpoints, '.github/workflows/parent-qualification.yml',
                          '.github/workflows/pr-metadata-context.yml'}
    codeql_path = '.github/workflows/codeql.yml'
    joint_endpoints = {*metadata_endpoints, codeql_path}
    retained_endpoints = {*joint_endpoints, '.github/workflows/sync-validation.yml'}
    if target != 'main' or not isinstance(paths, (tuple, list)) \
            or len(paths) != len(set(paths)) \
            or set(paths) not in (producer_endpoints, metadata_endpoints, joint_endpoints, retained_endpoints) \
            or not isinstance(base_tree, dict) \
            or not isinstance(trusted_tree, dict) or trusted_tree != base_tree:
        return False
    # No path hint may conceal a source/controller/profile/registry change.
    changed = {path for path in base_tree.keys() | tree.keys() if base_tree.get(path) != tree.get(path)}
    if changed != set(paths):
        return False
    policy = package_policy()
    generations = {generation['name']: generation['workflows'] for generation in policy.workflow_generations()}
    consumers = set(policy.CONSUMER_WORKFLOW_PATHS)
    if set(paths) == retained_endpoints:
        producer = generations.get('protected-producer-original-default-v1', {})
        ordinary = lambda oid: {'mode': '100644', 'type': 'blob', 'sha': oid}
        # The pre-sole-owner source recipe keeps the original Android owners
        # during source propagation. This exact installation still requires a
        # new full producer run; neither recipe grants execution evidence.
        for name in ('npm-consumers-sync-ci-v1', 'android-owned-npm5-sync-ci-v1'):
            previous = generations.get(name, {})
            if set(previous) != consumers or set(producer) != set(policy.METADATA_WORKFLOW_PATHS) \
                    or {path for path in consumers | set(producer)
                        if previous.get(path) != producer.get(path)} != retained_endpoints - {codeql_path} \
                    or any(base_tree.get(path) is not None for path in set(producer) - consumers):
                continue
            if base_tree.get(codeql_path) != ordinary('6d55d0fe4e9edc86204c66e1fa3967681793a2cd') \
                    or tree.get(codeql_path) != ordinary('e9aaaed9693efc5ffb4701697ac2a4d51f5f5ba1'):
                continue
            if all(snapshot.get(path) == entry
                   for snapshot, workflows in ((trusted_tree, previous), (base_tree, previous), (tree, producer))
                   for path, entry in workflows.items()):
                return True
        return False
    for old_name, new_name, endpoints, candidate_paths, joint_codeql in (
            ('android-owned-npm5-sync-ci-v1', 'protected-shared-producer-v1', producer_endpoints, consumers, False),
            ('postmerge-original-e-v1', 'protected-producer-postmerge-original-e-v1', producer_endpoints, consumers, False),
            ('postmerge-original-e-v1', 'protected-producer-ci37-v1', producer_endpoints, consumers, False),
            ('postmerge-original-e-v1', 'protected-producer-metadata-ci-v1', metadata_endpoints,
             set(policy.METADATA_WORKFLOW_PATHS), False),
            ('android-owned-npm5-sync-ci-v1', 'protected-producer-metadata-ci-v1', joint_endpoints,
             set(policy.METADATA_WORKFLOW_PATHS), True),
            ('android-owned-npm5-sync-ci-v1', 'protected-producer-seven-target-ci-v1', joint_endpoints,
             set(policy.METADATA_WORKFLOW_PATHS), True)):
        previous, producer = generations.get(old_name, {}), generations.get(new_name, {})
        if set(paths) != endpoints or set(previous) != consumers or set(producer) != candidate_paths \
                or {path for path in consumers | candidate_paths if previous.get(path) != producer.get(path)} \
                    != endpoints - ({codeql_path} if joint_codeql else set()) \
                or any(base_tree.get(path) is not None for path in candidate_paths - consumers):
            continue
        if joint_codeql:
            # One exact deployment gives the original full producer and CodeQL
            # the SAME native M. Both recipes retain reviewed extractor 2.27.2;
            # this widens selection, never admission or passing evidence.
            ordinary = lambda oid: {'mode': '100644', 'type': 'blob', 'sha': oid}
            if base_tree.get(codeql_path) != ordinary('6d55d0fe4e9edc86204c66e1fa3967681793a2cd') \
                    or tree.get(codeql_path) != ordinary('3a273057a38255ca368d3028594fb94227ba7c3b'):
                continue
        # Reviewed complete pairs only, never an arbitrary cross-product.
        if all(snapshot.get(path) == entry
               for snapshot, workflows in ((trusted_tree, previous), (base_tree, previous), (tree, producer))
               for path, entry in workflows.items()):
            return True
    return False


def select(tree, paths, regular, *, unknown=False, trusted_tree=None, candidate_root=ROOT,
           trusted_root=ROOT, target='main', base_tree=None, package_paths=()):
    """Improve an existing trusted decision only with a strictly smaller owner set."""
    legacy = _select_legacy(tree, paths, regular, unknown=unknown, trusted_tree=trusted_tree,
        candidate_root=candidate_root, trusted_root=trusted_root, target=target,
        base_tree=base_tree, package_paths=package_paths)
    if legacy['reason'] in {'unknown-or-nonregular-inventory', 'unowned-inputs',
                            'reviewed-protected-producer-transition'}:
        return legacy
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    affected = affected_selection(registry, tree, base_tree, trusted_tree, paths,
                                  allow_full_host=legacy['full_host'], legacy_selection=legacy, target=target)
    if affected is None:
        return legacy
    if affected['reason'] == 'protected-dependencies-unavailable':
        # An unavailable additional proof cannot invalidate the independently
        # reviewed legacy decision or require broader work than that decision.
        return legacy
    # Do not replace a stronger existing CI37/package proof with broad unproved
    # repository owners, or relabel that proof as an unsupported environment.
    narrower = set(affected['suites']) < set(legacy['suites'])
    # Fewer owners cannot justify broader preparation. In particular, keep the
    # existing Qt-free route until a subset has equivalent setup authority.
    no_broader_setup = not affected['full_host'] or legacy['full_host']
    return affected if narrower and no_broader_setup else legacy


def _select_legacy(tree, paths, regular, *, unknown=False, trusted_tree=None, candidate_root=ROOT,
                   trusted_root=ROOT, target='main', base_tree=None, package_paths=()):
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    names = list(registry['suites'])
    reason = 'unowned-inputs'
    if not isinstance(package_paths, (tuple, list)) or any(path not in PACKAGE_LOCKS for path in package_paths):
        raise ValueError('host package ownership requires finite separately owned lock paths')
    if unknown or not paths or (not regular and not _regular_ci_delta(tree, base_tree, paths, package_paths)):
        reason = 'unknown-or-nonregular-inventory'
    elif not all(isinstance(path, str) and (ci_owned(path) or path in package_paths) for path in paths):
        reason = 'unowned-inputs'
    else:
        try:
            # These exact foreign lock bytes are not product reader inputs.
            # Changed locks still require their separate mandatory owner and
            # ordinary entries on both sides; unchanged locks need no new run.
            reviewed_tree = tree
            if package_paths:
                if base_tree is None or any(
                        not isinstance(snapshot.get(path), dict)
                        or snapshot[path].get('mode') != '100644'
                        or snapshot[path].get('type') != 'blob'
                        for snapshot in (tree, base_tree) for path in package_paths):
                    raise ValueError('package lock ownership requires ordinary inputs on both sides')
            expected = REVIEWED_PROGRAMS if target == 'main' else REVIEWED_CHILD_PROGRAMS.get(target)
            reviewed = expected is not None and program_digest(reviewed_tree, candidate_root) in {
                expected, REVIEWED_PREDECESSORS.get(target)}
            if trusted_tree is not None:
                reviewed &= program_digest(trusted_tree, trusted_root) in {
                    REVIEWED_PROGRAMS, REVIEWED_PREDECESSORS['main']}
        except (ValueError, OSError, subprocess.SubprocessError):
            reviewed = False
        if reviewed:
            if _protected_producer_transition(tree, paths, base_tree, trusted_tree, target):
                return {'suites': names, 'reason': 'reviewed-protected-producer-transition',
                        'full_host': True, 'include_platform': True}
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


def _qt_free_dependency_namespace():
    """Only the new protected namespace may narrow the existing CI37 route."""
    try:
        import ci_profile
        return ci_profile.load_policy(ROOT).get('generation_kind') == ci_profile.SEVEN_CONTROLLER_KIND
    except (OSError, ValueError, AttributeError):
        return False


def affected_selection(registry, tree, base_tree, trusted_tree, paths, *, allow_full_host=True,
                       legacy_selection=None, target='main'):
    """Use only an already protected graph; missing legacy graphs retain legacy routing.

    A graph/source rollout cannot certify itself. Every unavailable or changed
    protected authority keeps the complete existing gate, before any execution.
    """
    # Preserve the old namespace's setup dominance and cheap early return.
    # Only the new finite source/profile policy may narrow an independently
    # established CI37 route without adding Qt or Java preparation.
    qt_free = allow_full_host is False
    if qt_free and not _qt_free_dependency_namespace():
        return None
    snapshots = (tree, base_tree, trusted_tree)
    if all(isinstance(snapshot, dict) and inputs.AFFECTED_POLICY not in snapshot for snapshot in snapshots):
        return None
    try:
        raw = inputs.load_dependencies(ROOT / inputs.AFFECTED_POLICY, registry)
        document = json.loads(raw)
        if qt_free and document['schema'] != 2:
            return None
        device = document['suites'].get('device-control-plane-full', {})
        if any(not ci_owned(path) for path in device.get('native_independent_paths', ())):
            raise ValueError('device native lookup may exempt only reviewed CI-owned leaves')
        plan = inputs.plan_affected(registry, raw, base_tree, tree, trusted_tree, target=target)
        if plan['paths'] != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError('affected suite paths differ from complete immutable delta')
    except (inputs.InputError, ValueError, OSError, KeyError, TypeError):
        return {'suites': list(registry['suites']), 'reason': 'protected-dependencies-unavailable',
                'full_host': True, 'include_platform': True}
    if qt_free:
        import ci_profile
        if type(legacy_selection) is not dict or legacy_selection.get('suites') != list(ci_profile.SUITES) \
                or legacy_selection.get('full_host') is not False or legacy_selection.get('include_platform') is not False \
                or legacy_selection.get('reason') not in {'reviewed-ci-only-inputs', 'reviewed-ci-and-package-owners'}:
            return None
        names = [name for name in ci_profile.SUITES if name in plan['required']]
        if not names or names == list(ci_profile.SUITES):
            return None
        value = {'suites': names, 'reason': 'protected-ci-dependencies',
            'full_host': False, 'include_platform': False, 'affected': plan}
        if legacy_selection.get('package_owned_paths'):
            value['package_owned_paths'] = legacy_selection['package_owned_paths']
        return value
    include_platform = bool(document['schema'] == 2
        and document['targets'][target]['profile'] != inputs._AFFECTED_SHARED_PROFILE
        and (legacy_selection is None or legacy_selection.get('include_platform') is not False))
    return {'suites': plan['required'], 'reason': 'protected-affected-dependencies',
            # This legacy flag also controls prerequisite preparation. Until
            # setup ownership is qualified, retain complete host provisioning.
            'full_host': True, 'include_platform': include_platform, 'affected': plan}


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


def candidate_selection(candidate, event, sha, expected_plan=None):
    """Independently recompute selection; never infer execution from a receipt."""
    candidate = Path(candidate).resolve(strict=True)
    before = execution.checkout_identity(candidate)
    policy = package_policy()
    policy.validate_wiring(candidate)
    plan = policy.candidate_plan(candidate, event, sha)
    if plan['candidate'] != before[0] or plan['host_mode'] != 'full' \
            or expected_plan is not None and plan['plan'] != expected_plan:
        raise ValueError('owned host execution differs from the exact required package plan')
    base_tree = inputs.full_tree(candidate, plan['base']) if plan.get('base') and not plan['unknown'] else None
    selected = select(inputs.full_tree(candidate, before[0]), plan['paths'], regular_ci_inventory(plan, base_tree, inputs.full_tree(candidate, before[0])),
        unknown=plan['unknown'], trusted_tree=inputs.full_tree(ROOT, 'HEAD'), candidate_root=candidate,
        target=target_branch(event), base_tree=base_tree, package_paths=package_owned_paths(plan))
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    if additional_suites(candidate_registry(candidate), registry):
        raise ValueError('new candidate command requires a reviewed Android host generation')
    if execution.checkout_identity(candidate) != before:
        raise ValueError('candidate changed during owned host selection')
    return selected

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
