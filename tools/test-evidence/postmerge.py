#!/usr/bin/env python3
"""Source-staged main consumer of ORIGINAL protected PR evidence.

No candidate checkout, runtime probe, installation or test command is needed to
look up proof. Unsupported proof leaves the existing actual execution selected.
This entrypoint never executes candidate code or emits a qualification receipt.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import attested
import ci_profile
import execution
import inputs
import producer as P
import producer_api as A
import producer_workflow as producer
import runtime_ci
import sandbox

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = 'tools/repository-checks/workflows/producers/parent-qualification.yml'
SOURCE_READY = False
GENERATIONS = {'postmerge-original-e-v1', 'protected-producer-postmerge-original-e-v1',
               'protected-producer-ci37-v1'}


def _source_qualified():
    return (SOURCE_READY is True and producer.PRODUCTION_READY is True
            and sandbox.ACTIVATION_READY is True and attested.ISOLATED_ADMISSION_READY is True)


def _native(event, environment):
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': A.REPOSITORY,
        'GITHUB_REPOSITORY_ID': '1319052603', 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF': 'refs/heads/main', 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_JOB': 'qualify-parent', 'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24'}
    A.require(all(environment.get(key) == value for key, value in expected.items()),
              'consumer requires the original current main push job')
    source = A.sha(environment.get('GITHUB_SHA'))
    A.require(environment.get('GITHUB_WORKFLOW_SHA') == source
        and environment.get('GITHUB_WORKFLOW_REF') == A.REPOSITORY + '/.github/workflows/parent-qualification.yml@refs/heads/main'
        and re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')),
        'consumer native workflow source unavailable')
    A.require(type(event) is dict and event.get('ref') == 'refs/heads/main' and event.get('after') == source
        and event.get('deleted') is False and event.get('forced') is False
        and event.get('repository', {}).get('full_name') == A.REPOSITORY
        and event.get('repository', {}).get('id') == 1319052603,
        'consumer event differs from the current native main push')
    return source, int(environment['GITHUB_RUN_ID'])


def full_tree(adapter, revision):
    """Immutable complete source map, including aliases and negative membership."""
    tree_sha, _ = adapter._commit(revision)
    value = adapter.api.immutable_tree(tree_sha)
    A.require(type(value) is dict and value.get('sha') == tree_sha and value.get('truncated') is False
        and type(value.get('tree')) is list and len(value['tree']) <= 200_000,
        'consumer full source inventory is incomplete')
    result, seen = {}, set()
    for item in value['tree']:
        A.require(type(item) is dict, 'invalid immutable source entry')
        path = inputs._path(item.get('path'), 'immutable consumer path')
        A.require(path not in seen, 'duplicate immutable source path')
        seen.add(path)
        mode, kind, oid = item.get('mode'), item.get('type'), A.sha(item.get('sha'))
        A.require({'040000': 'tree', '100644': 'blob', '100755': 'blob', '120000': 'blob',
                   '160000': 'commit'}.get(mode) == kind, 'unsupported immutable source mode')
        if kind != 'tree':
            result[path] = {'mode': mode, 'type': kind, 'sha': oid}
    inputs._validate_tree(result)
    A.require(bool(result), 'empty immutable source inventory')
    return tree_sha, result


def original_controller(policy, previous, current, root=ROOT):
    """Reconstruct original B from reviewed bytes, never descriptor root claims.

    The finite producer graph is shared with its actual protected entrypoint.
    Every member on B must equal this reviewed source generation. No historic
    imports, candidate authority or current process module inventory is used.
    """
    package = policy.package_policy()
    identity = {}
    for relative in producer.controller_sources(policy):
        entry = current.get(relative)
        A.require(type(entry) is dict and entry.get('type') == 'blob'
            and entry.get('mode') in {'100644', '100755'} and previous.get(relative) == entry,
            'original protected controller source generation changed')
        raw = package._trusted_bytes(relative, git_fallback=True)
        immutable = sandbox._git(root, 'cat-file', 'blob', entry['sha'], limit=1_000_000)
        A.require(raw == immutable, 'loaded consumer policy differs from immutable trusted bytes')
        identity[relative] = {'mode': entry['mode'], 'sha256': hashlib.sha256(raw).hexdigest()}
    return P.digest(identity)


def _policy(policy, registry, binding, controller, adapter, root, selected):
    tree = inputs.full_tree(root, 'HEAD')
    entry = tree.get(producer.TEMPLATE)
    A.require(type(entry) is dict and entry['mode'] == '100644' and entry['type'] == 'blob',
              'trusted protected producer template unavailable')
    original = P.Policy(A.REPOSITORY, 1319052603, 15368, '.github/workflows/project-tests.yml',
        entry['sha'], f"refs/pull/{binding['pull_request']}/merge", ('pull_request',), controller,
        sandbox.contract(root)['digest'], required_execution_schema=3)
    generations = {}
    for generation in policy.package_policy().workflow_generations():
        workflows = generation['workflows']
        if set(A.WORKFLOWS) <= workflows.keys() and workflows[original.workflow_path]['sha'] == original.workflow_blob:
            projection = {path: workflows[path] for path in A.WORKFLOWS}
            generations['generation-' + P.digest(projection).removeprefix('sha256:')] = projection
    caller = adapter._object('actions/workflows/repository-checks.yml')
    A.require(caller.get('path') == '.github/workflows/repository-checks.yml', 'original producer caller unavailable')
    result = A.AdapterPolicy(original, A.positive(caller.get('id')), '.github/workflows/repository-checks.yml',
        generations, producer.DESCRIPTOR_JOB, {'shared-host': producer.SHARED_JOB}, producer.PUBLISH_PREFIX)
    plan = {'owners': {'shared-host': {'kind': 'shared', 'suites': selected['suites'],
                                     'include_platform': selected['include_platform'], 'platform': {}}}}
    A._policy(result, plan, binding['pull_request'])
    return plan, result


def verify_main(event, environment, adapter, *, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Verify one independently selected original owner, never rebound PASS."""
    A.require(_source_qualified(),
              'postmerge protected reuse is not qualified')
    source, run_id = _native(event, environment)
    binding, references = adapter._integrated_current(run_id, 15368, clock())
    A.require(references['target'] == references['default'] == source and references['default_ref'] == 'main'
        and binding['base_ref'] == 'main' and event.get('before') == binding['base_sha']
        and execution.checkout_identity(root) == (source, references['integration']['tree']),
        'current main or trusted source differs from authenticated push')
    current_tree_sha, current = full_tree(adapter, source)
    local = inputs.full_tree(root, source)
    A.require(current == local and current_tree_sha == references['integration']['tree'],
              'complete current main inventory differs from trusted immutable checkout')
    policy = producer._host_policy()
    package = policy.package_policy()
    A.require(package.validate_tree_wiring(current) in GENERATIONS,
              'current main does not contain the exact complete consumer generation')
    A.require(current.get('.github/workflows/parent-qualification.yml') == local.get(TEMPLATE)
        and current.get(TEMPLATE, {}).get('mode') == '100644', 'actual parent workflow differs from trusted canonical source')
    _, previous = full_tree(adapter, binding['base_sha'])
    controller = original_controller(policy, previous, local, root)
    registry = inputs.load_registry(root / '.github/test-suites.json')
    A.require(all(suite['scope'] == 'content' for suite in registry['suites'].values()),
              'candidate-scoped suites require actual execution for the integrated commit')
    # Empty product declarations are independently bound on BOTH full snapshots.
    # Additional candidate commands cannot disappear behind a trusted registry.
    for snapshot in (previous, current):
        for relative in ('.github/test-suites.json', 'tests/platform-profile.json'):
            A.require(snapshot.get(relative) == local.get(relative), 'candidate command or product declarations changed')
    A.require(json.loads(package._trusted_bytes('tests/platform-profile.json')) ==
        {'schema': 1, 'platform': 'shared', 'suites': []}, 'product execution is outside this main consumer')
    # Receipt fields never choose the profile or selected owner. Derive the
    # current plan before discovering its original native producer source.
    # The controller's original B context is independently reconstructed above;
    # using it for both plans also retains the finite full transition owner.
    read_blob = lambda oid:adapter.api.immutable_blob(oid)
    current_profile = producer.selection_profile(policy, registry, current, previous, previous, root=root,read_blob=read_blob)
    selected = current_profile['selection']
    plan, api_policy = _policy(policy, registry, binding, controller, adapter, root, selected)
    snapshot = adapter.capture_integrated(run_id, plan, api_policy, now=clock())
    A.require(snapshot.references == references, 'integration changed before original proof selection')
    original_tree_sha, original_tree = full_tree(adapter, snapshot.binding['merge_sha'])
    A.require(original_tree_sha == snapshot.binding['merge_tree'] == current_tree_sha and original_tree == current,
              'integrated file tree differs from the complete actually tested source')
    original_profile = producer.selection_profile(policy, registry, original_tree, previous, previous, root=root,read_blob=read_blob)
    A.require(original_profile == current_profile, 'original and current independently selected owners differ')
    authority = P.select_authority(snapshot.observations, snapshot.binding, plan, api_policy.producer,
                                   inventory_complete=snapshot.inventory_complete, now=clock())
    A.require(authority['state'] == 'proof-required', 'newest original producer cannot establish complete proof')
    observation = next(value for value in snapshot.observations if value.run.run_id == authority['run_id'])
    raw, facts = adapter._artifact(observation.run, 'aggregate', snapshot.artifact_inventories[authority['run_id']],
                                   clock(), snapshot.binding['head_sha'])
    A.require(raw is not None and facts is not None, 'original aggregate unavailable')
    aggregate = P.read_artifact(raw, 'aggregate', facts, observation.run, now=clock())
    receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
    A.require(type(receipt) is dict and receipt.get('schema') == 3, 'original isolated execution receipt unavailable')
    original_git = producer.expected_git_context(adapter, snapshot.binding)
    execution.validate_receipt(receipt, registry, original_tree,
        require_all=original_profile['profile'] != ci_profile.PROFILE, expected_git_context=original_git)
    A.require(receipt['requested_suites'] == selected['suites']
        and receipt['include_platform'] == selected['include_platform'],
        'original receipt differs from independently selected shared owners')
    original_environment = receipt['environment']
    if original_profile['profile'] == ci_profile.PROFILE:
        reuse = runtime_ci.plan_original_reuse(original_environment, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), selected, current_profile['selection'],
            original_tree, current, local, registry, receipt['results'], root=root,read_blob=read_blob)
        admission = reuse['admission']
        reused_suites = reuse['reused_suites']
        runtime_admission = {'profile': admission['profile'], 'policy_digest': admission['policy_digest']}
    else:
        admission = attested.validate_environment(original_environment, aggregate.get('qualified_at'), aggregate.get('expires_at'),
                                                   clock(), root=root, isolated=True)
        reuse = inputs.plan_reuse(registry, original_tree, current, receipt['results'], original_environment, original_environment)
        A.require(not reuse['required'] and set(reuse['reused']) == set(registry['suites']),
                  'complete current shared input closure requires actual verification')
        reused_suites, runtime_admission = reuse['reused'], admission['policy']
    context = P.SharedContext(registry, original_tree, original_environment,
                             snapshot.binding['merge_sha'], original_tree_sha, original_git)
    # The original data above supplies no authority. Only these fresh complete
    # snapshots authenticate the owner, attempt, hash publisher, E and expiry.
    verified = adapter.verify_integrated(run_id, plan, api_policy, {'shared-host': context}, clock=clock)
    A.require(verified['integration'] == references['integration']
        and verified['source_chain']['producer_commit'] == snapshot.binding['merge_sha']
        and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
        and verified['aggregate_digest'] == aggregate.get('aggregate_digest')
        and clock() < P._time(verified['expires_at']), 'original proof changed before consumer completion')
    # Independent package owners are never inferred from shared proof. Their
    # exact immutable delta controls whether checkout/Node/package routing is
    # still needed. A changed package-reader/controller already denied above.
    roots = (*package.tools().PROJECTS, package.S3, package.BROWSER)
    package_work = any(any(path == prefix or path.startswith(prefix + '/') for prefix in roots)
                       for path in previous.keys() | current.keys() if previous.get(path) != current.get(path))
    return {'schema': 1, 'kind': 'original-pr-main-reuse', 'reusable': False,
        'current_commit': source, 'current_tree': current_tree_sha, 'current_push_run_id': run_id,
        'original_commit': snapshot.binding['merge_sha'], 'original_git_context': original_git,
        'original_proof': verified, 'original_environment_digest': admission['environment_digest'],
        'runtime_admission': runtime_admission, 'reused_suites': reused_suites, 'executed_suites': [],
        'package_work': package_work}


def lookup(event, environment, adapter=None, *, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Pre-execution only: no failure is hidden by retrying an alternate executor."""
    try:
        if not _source_qualified():
            return {'reused': False, 'reason': 'protected-consumer-not-qualified'}
        proof = verify_main(event, environment, adapter or A.Adapter(), root=root, clock=clock)
        return {'reused': True, 'proof': proof}
    except (P.ProtocolError, attested.AttestedReuseUnavailable, inputs.InputError, execution.ExecutionError,
            sandbox.SandboxUnavailable, ci_profile.CIProfileError, runtime_ci.CIEnvironmentError,
            producer.PreExecutionUnavailable, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError,
            AttributeError, StopIteration):
        # API bodies, candidate strings, signed URLs and credentials never enter
        # output. This means no reuse, not success of any unexecuted test.
        return {'reused': False, 'reason': 'original-proof-unavailable'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    event = {}
    try:
        if _source_qualified():
            path = Path(os.environ['GITHUB_EVENT_PATH'])
            A.require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 2_000_000,
                      'native event file unavailable')
            event = json.loads(path.read_bytes(), object_pairs_hook=inputs._unique_object)
    except (P.ProtocolError, OSError, KeyError, TypeError, ValueError):
        event = {}  # The bounded lookup selects actual fallback without API proof.
    result = lookup(event, os.environ)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(P.canonical(result))
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write('shared_reused=' + str(result['reused']).lower() + '\n')
        output.write('package_work=' + str(not result['reused'] or result['proof']['package_work']).lower() + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
