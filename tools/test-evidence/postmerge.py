#!/usr/bin/env python3
"""Source-staged finite protected-target consumer of ORIGINAL PR evidence.

No candidate checkout, runtime probe, installation or test command is needed to
look up proof. Unsupported proof leaves the existing actual execution selected.
This entrypoint never executes candidate code or emits a qualification receipt.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import attested
import ci_profile
import execution
import inputs
import producer as P
import producer_api as A
import producer_workflow as producer
import runtime_ci
import sandbox
import source_admission

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = 'tools/repository-checks/workflows/producers/parent-qualification.yml'
SOURCE_READY = True
GENERATIONS = {'postmerge-original-e-v1', 'protected-producer-postmerge-original-e-v1',
               'protected-producer-ci37-v1', 'protected-producer-metadata-ci-v1',
               'protected-producer-seven-target-ci-v1'}
DOCUMENTATION_SUITES = frozenset({'documentation-contracts','documentation','policy-consistency'})


def _source_qualified():
    return (SOURCE_READY is True and producer.PRODUCTION_READY is True
            and sandbox.ACTIVATION_READY is True and attested.ISOLATED_ADMISSION_READY is True)


def _native(event, environment):
    target=environment.get('GITHUB_REF','').removeprefix('refs/heads/')
    A.require(target in source_admission.TARGET_PROFILES, 'unknown protected consumer target')
    workflow='parent-qualification' if target in {'main','android-main','android-vr','apple-main'} else 'project-tests'
    job='qualify-parent' if workflow=='parent-qualification' else 'route'
    if environment.get('GITHUB_WORKFLOW_REF')==A.REPOSITORY+'/'+A.DOCUMENTATION_PUSH_WORKFLOW+'@refs/heads/'+target:
        A.require(target in A.DOCUMENTATION_PUSH_BRANCHES, 'unreviewed documentation push target')
        workflow='documentation-push-owner';job='documentation-source'
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': A.REPOSITORY,
        'GITHUB_REPOSITORY_ID': '1319052603', 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF': 'refs/heads/'+target, 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_JOB': job, 'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24'}
    A.require(all(environment.get(key) == value for key, value in expected.items()),
              'consumer requires the original current protected push job')
    source = A.sha(environment.get('GITHUB_SHA'))
    A.require(environment.get('GITHUB_WORKFLOW_SHA') == source
        and environment.get('GITHUB_WORKFLOW_REF') == A.REPOSITORY + '/.github/workflows/'+workflow+'.yml@refs/heads/'+target
        and re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')),
        'consumer native workflow source unavailable')
    A.require(type(event) is dict and event.get('ref') == 'refs/heads/'+target and event.get('after') == source
        and event.get('deleted') is False and event.get('forced') is False
        and event.get('repository', {}).get('full_name') == A.REPOSITORY
        and event.get('repository', {}).get('id') == 1319052603,
        'consumer event differs from the current native protected push')
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


def default_authority(adapter, references):
    authority=adapter._object('branches/main')
    A.require(authority.get('name')=='main' and authority.get('protected') is True
        and authority.get('commit',{}).get('sha')==references['default'],
        'current default controller authority protection changed')
    return {'name':'main','protected':True,'commit':references['default']}


def integrated_controller(policy, previous, current, local, target, root):
    """Reconstruct actual D bytes from original B's complete finite enrollment.

    The native pre-import recipe commits D to B. This does not assert a
    historical D commit; the original controller hash and E remain actual D.
    Metadata retention keeps its separate original_controller path unchanged.
    """
    A.require(set(producer.controller_sources(policy))==set(source_admission.CONTROLLERS),
              'integrated controller graph is not independently reviewed')
    read=lambda name:source_admission.actual_bytes(root,name)
    before=source_admission.compatibility(previous,local,target,read_actual=read,actual_imports=source_admission.actual_import_inventory(root))
    after=source_admission.compatibility(current,local,target,read_actual=read,actual_imports=source_admission.actual_import_inventory(root))
    A.require(before==after, 'integrated controller or target declarations changed')
    return before['controller_digest']


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
    metadata_workflows, metadata_sources = producer.metadata_generations(policy, root=root)
    result = A.AdapterPolicy(original, A.positive(caller.get('id')), '.github/workflows/repository-checks.yml',
        generations, producer.DESCRIPTOR_JOB, {'shared-host': producer.SHARED_JOB}, producer.PUBLISH_PREFIX,
        metadata_workflows, metadata_sources)
    plan = {'owners': {'shared-host': {'kind': 'shared', 'suites': selected['suites'],
                                     'include_platform': selected['include_platform'], 'platform': {}}}}
    A._policy(result, plan, binding['pull_request'])
    return plan, result


def _affected_receipt_selection(profile, registry, target):
    """Scope receipts only AFTER protected selection_profile rederives the plan.

    This structural check supplies no selection authority. That entrypoint has
    already checked actual registry bytes, the immutable protected dependency
    graph, complete B/M/D lookup and the independent legacy preparation gate.
    """
    selected=profile['selection']
    if selected.get('reason')!='protected-affected-dependencies':
        return False
    A.require(target=='main' and profile['profile']==producer.FULL_PROFILE
        and selected['full_host'] is True and selected['include_platform'] is False
        and selected['suites']==selected['affected']['required']
        and bool(selected['suites']) and set(selected['suites'])<set(registry['suites']),
        'affected receipt does not have an independently selected main full-runtime subset')
    return True


def _require_full_reuse_partition(reuse, registry, selected, affected):
    if affected:
        A.require(reuse['reused']==selected['suites']
            and set(reuse['required'])==set(registry['suites'])-set(selected['suites']),
            'selected affected owner requires actual verification')
    else:
        A.require(not reuse['required'] and set(reuse['reused'])==set(registry['suites']),
            'complete current shared input closure requires actual verification')


def verify_main(event, environment, adapter, *, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Verify one independently selected original owner, never rebound PASS."""
    A.require(_source_qualified(),
              'postmerge protected reuse is not qualified')
    source, run_id = _native(event, environment)
    binding, references = adapter._integrated_current(run_id, 15368, clock())
    source_authority=default_authority(adapter,references)
    target=binding['base_ref']
    default_tree_sha, _=adapter._commit(references['default'])
    A.require(references['target'] == source and references['default_ref'] == 'main'
        and target in source_admission.TARGET_PROFILES and event.get('before') == binding['base_sha']
        and execution.checkout_identity(root) == (references['default'], default_tree_sha),
        'current target or trusted default source differs from authenticated push')
    current_tree_sha, current = full_tree(adapter, source)
    local = inputs.full_tree(root, references['default'])
    _, immutable_default=full_tree(adapter,references['default'])
    A.require(immutable_default == local and current_tree_sha == references['integration']['tree'],
              'complete default inventory differs from trusted immutable checkout')
    policy = producer._host_policy()
    package = policy.package_policy()
    A.require(package.validate_tree_wiring(current) in GENERATIONS,
              'current target does not contain the exact complete consumer generation')
    workflow=references['integration']['workflow_path']
    documentation=workflow==A.DOCUMENTATION_PUSH_WORKFLOW
    template=workflow if documentation else TEMPLATE if workflow=='.github/workflows/parent-qualification.yml' else producer.TEMPLATE
    A.require(workflow in {'.github/workflows/parent-qualification.yml','.github/workflows/project-tests.yml',A.DOCUMENTATION_PUSH_WORKFLOW}
        and environment.get('GITHUB_WORKFLOW_REF')==A.REPOSITORY+'/'+workflow+'@refs/heads/'+target
        and current.get(workflow)==local.get(template) and local.get(template,{}).get('mode')=='100644',
        'actual protected push workflow differs from trusted canonical source')
    _, previous = full_tree(adapter, binding['base_sha'])
    controller = integrated_controller(policy,previous,current,local,target,root)
    registry = inputs.load_registry(root / '.github/test-suites.json')
    A.require(all(suite['scope'] == 'content' for suite in registry['suites'].values()),
              'candidate-scoped suites require actual execution for the integrated commit')
    # Enrolled product declarations are independently bound on BOTH snapshots.
    # Additional candidate commands cannot disappear behind a trusted registry.
    for snapshot in (previous, current):
        for relative in ('.github/test-suites.json',):
            A.require(snapshot.get(relative) == local.get(relative), 'candidate command or product declarations changed')
    A.require(local.get('tests/platform-profile.json')==source_admission.ordinary(source_admission.SHARED_PROFILE),
        'shared default controller profile changed')
    # Receipt fields never choose the profile or selected owner. Derive the
    # current plan before discovering its original native producer source.
    # On main, original D is independently known to be original B; preserve
    # that full transition context even after current default advances to S.
    # Child admission is limited to complete shared execution under the current
    # identical controller policy; no historical whole-default tree is invented.
    selection_context=previous if target=='main' else local
    read_blob = lambda oid:adapter.api.immutable_blob(oid)
    current_profile = producer.selection_profile(policy, registry, current, previous, selection_context, root=root,target=target,read_blob=read_blob)
    selected = current_profile['selection']
    affected=_affected_receipt_selection(current_profile,registry,target)
    if documentation:
        A.require(DOCUMENTATION_SUITES <= set(selected['suites']),
            'original shared owner does not contain every documentation command')
    if target!='main':
        A.require(current_profile['profile']==producer.FULL_PROFILE and selected['full_host'] is True
            and set(selected['suites'])==set(registry['suites']),
            'child protected reuse requires complete shared execution')
    A.require(source_admission.shared_platform_supported(selected,target,current.get(source_admission.PROFILE)),
        'required platform owners need existing actual execution')
    plan, api_policy = _policy(policy, registry, binding, controller, adapter, root, selected)
    snapshot = adapter.capture_integrated(run_id, plan, api_policy, now=clock())
    A.require(snapshot.references == references, 'integration changed before original proof selection')
    original_tree_sha, original_tree = full_tree(adapter, snapshot.binding['merge_sha'])
    A.require(original_tree_sha == snapshot.binding['merge_tree'] == current_tree_sha and original_tree == current,
              'integrated file tree differs from the complete actually tested source')
    original_profile = producer.selection_profile(policy, registry, original_tree, previous, selection_context, root=root,target=target,read_blob=read_blob)
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
        require_all=original_profile['profile'] != ci_profile.PROFILE and not affected, expected_git_context=original_git)
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
        _require_full_reuse_partition(reuse,registry,selected,affected)
        reused_suites, runtime_admission = reuse['reused'], admission['policy']
    if documentation:
        A.require(DOCUMENTATION_SUITES <= set(reused_suites), 'documentation owner requires actual verification')
    context = P.SharedContext(registry, original_tree, original_environment,
                             snapshot.binding['merge_sha'], original_tree_sha, original_git)
    # The original data above supplies no authority. Only these fresh complete
    # snapshots authenticate the owner, attempt, hash publisher, E and expiry.
    verified = adapter.verify_integrated(run_id, plan, api_policy, {'shared-host': context}, clock=clock)
    A.require(verified['integration'] == references['integration']
        and verified['source_chain']['producer_commit'] == snapshot.binding['merge_sha']
        and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
        and verified['aggregate_digest'] == aggregate.get('aggregate_digest')
        and clock() < P._time(verified['expires_at'])
        and execution.checkout_identity(root)==(references['default'],default_tree_sha)
        and integrated_controller(policy,previous,current,local,target,root)==controller
        and default_authority(adapter,references)==source_authority,
        'original proof changed before consumer completion')
    # Independent package owners are never inferred from shared proof. Their
    # exact immutable delta controls whether checkout/Node/package routing is
    # still needed. A changed package-reader/controller already denied above.
    roots = (*package.tools().PROJECTS, package.S3, package.BROWSER)
    package_work = any(any(path == prefix or path.startswith(prefix + '/') for prefix in roots)
                       for path in previous.keys() | current.keys() if previous.get(path) != current.get(path))
    return {'schema': 1, 'kind': 'original-pr-main-reuse' if target=='main' else 'original-pr-target-reuse', 'target':target, 'reusable': False,
        'current_commit': source, 'current_tree': current_tree_sha, 'current_push_run_id': run_id,
        'original_commit': snapshot.binding['merge_sha'], 'original_git_context': original_git,
        'original_proof': verified, 'original_environment_digest': admission['environment_digest'],
        'runtime_admission': runtime_admission, 'reused_suites': reused_suites, 'executed_suites': [],
        'package_work': package_work}


def _metadata_module(root=ROOT):
    spec = importlib.util.spec_from_file_location('trusted_native_metadata_context',
        Path(root) / 'tools/repository-checks/metadata_context.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def metadata_selection(event, binding, previous, current, local, registry, policy, *, root=ROOT, read_blob=None):
    """A finite positive owner class, derived from complete immutable maps.

    Native, Android, package/tool and browser execution are deliberately outside
    this initial owner. Their absence is proved from current inputs; no receipt
    or previous aggregate output chooses or narrows this scope.
    """
    package = policy.package_policy()
    checks = package.load('metadata_current_repository_policy', 'tools/repository-checks/check.py')
    config, branches = checks.configuration()
    paths = sorted(path for path in previous.keys() | current.keys() if previous.get(path) != current.get(path))
    A.require(paths and all(entry is None or entry.get('mode') == '100644' and entry.get('type') == 'blob'
        for path in paths for entry in (previous.get(path), current.get(path))), 'metadata delta is not ordinary')
    A.require(all(policy.ci_owned(path) for path in paths), 'metadata initial class requires CI-owned inputs')
    route = checks.plan(event, paths, config, branches, True)
    selected_packages = package.select(paths, True, legacy_mode=route['mode'],
        legacy_projects=route.get('tool_projects', '').split(',') if route.get('tool_projects') else (),
        include_browser=True)
    A.require(selected_packages == {'host_mode': 'full', 'tool_projects': [], 'package_set': []},
              'metadata initial class cannot retain package/tool execution')
    A.require(not checks.direct_browser_required(config, event)
        and binding['base_ref'] not in config.get('browser_client_required_branches', []),
        'metadata initial class cannot retain browser execution')
    native = package.load('metadata_current_native_policy', 'tools/native-tests/check.py').plan(paths, True)
    A.require(native['mode'] == 'skip', 'metadata initial class cannot retain native execution')
    roots = (*package.tools().PROJECTS, package.S3, package.BROWSER, 'browser-direct-client')
    A.require(not any(any(path == prefix or path.startswith(prefix + '/') for prefix in roots) for path in paths),
              'metadata package input closure changed')
    for tree in (previous, current):
        A.require(not any(path == 'android' or path.startswith('android/') or path in {
            '.github/workflows/android-tests.yml', '.github/workflows/android-vr-tests.yml'} for path in tree),
            'metadata initial class cannot retain Android execution')
        for relative in ('.github/test-suites.json', 'tests/platform-profile.json'):
            A.require(tree.get(relative) == local.get(relative), 'metadata command or platform inventory changed')
    A.require(json.loads(package._trusted_bytes('tests/platform-profile.json')) ==
        {'schema': 1, 'platform': 'shared', 'suites': []}, 'metadata platform declarations are not empty')
    A.require(all(suite['scope'] == 'content' for suite in registry['suites'].values()),
              'metadata requires the reviewed content-scoped registry')
    selected = producer.selection_profile(policy, registry, current, previous, local,
        root=root, target='main', read_blob=read_blob)
    return {'selection': selected, 'route': route, 'native': native, 'paths': paths,
            'package_work': False, 'android_required': False, 'browser_required': False}


_METADATA_OUTER_RECIPES = {
    '.github/workflows/documentation-checks.yml': (
        'documentation / documentation', (
            'Verify documentation checker behavior', 'Check every workspace document and incoming link',
            'Verify policy-derived branch and suite displays')),
    '.github/workflows/workflow-security.yml': (
        'workflow-security / Actionlint, Zizmor, and Gitleaks', (
            'Verify immutable action references', 'Install checksum-verified static analyzers',
            'Lint workflow syntax and runner labels', 'Audit workflow security',
            'Scan workflow files for secrets with redacted output', 'Verify fail-closed workflow contracts')),
}


def metadata_outer_jobs(adapter, run_id, binding, current, local, security, *, shared_receipt=None, root=ROOT):
    """Authenticate actual same-M checker jobs, independently of old PASS text."""
    run = adapter._object(f'actions/runs/{run_id}/attempts/1')
    jobs = adapter._pages(f'actions/runs/{run_id}/attempts/1/jobs', 'jobs')
    A.require(run.get('id') == run_id and run.get('run_attempt') == 1
        and run.get('head_sha') == binding['head_sha'] and run.get('status') == 'completed'
        and run.get('conclusion') == 'success', 'metadata original outer execution is unavailable')
    references = run.get('referenced_workflows')
    A.require(type(references) is list, 'metadata original reusable source inventory unavailable')
    for label in ('native', 'android', 'project / tool-dependencies', 'project / package-checks'):
        matches = [job for job in jobs if job.get('name') == label]
        A.require(len(matches) == 1, 'metadata absent owner native record is missing or ambiguous')
        fact = adapter._job(matches[0], run, 15368, final_name=label)
        A.require(fact.status == 'completed' and fact.conclusion == 'skipped',
                  'metadata initial class cannot retain an executed external owner')
    A.require(not any(isinstance(job.get('name'), str) and
        job['name'].startswith(('direct-browser', 'browser-client')) and job.get('conclusion') != 'skipped'
        for job in jobs), 'metadata initial class cannot retain a browser owner')
    delegated = set()
    publication = None
    generation = producer._host_policy().package_policy().validate_tree_wiring(current)
    if generation == 'protected-producer-seven-target-ci-v1' and shared_receipt is not None:
        # This is an observation used on both sides of verify_metadata's full
        # adapter.verify call below. It never supplies standalone proof. Bind
        # the conditional owner facts to the ACTUAL completed native whole hash;
        # the unchanged original aggregate protocol authenticates its complete
        # source, schema3 runtime, descriptor, jobs, results and artifacts.
        A.require(type(shared_receipt) is dict and shared_receipt.get('schema') == 3
            and shared_receipt.get('candidate_commit') == binding['merge_sha']
            and shared_receipt.get('candidate_tree') == binding['merge_tree']
            and shared_receipt.get('reusable') is True
            and type(shared_receipt.get('requested_suites')) is list
            and type(shared_receipt.get('results')) is dict
            and set(shared_receipt['results']) == set(shared_receipt['requested_suites'])
            and all(type(value) is dict and value.get('status') == 'passed'
                    for value in shared_receipt['results'].values()),
            'metadata delegated commands have no original successful schema3 receipt')
        commitment = hashlib.sha256(P.canonical(shared_receipt)).hexdigest()
        publishers = [job for job in jobs if isinstance(job.get('name'), str)
                      and job['name'].startswith(producer.PUBLISH_PREFIX)]
        A.require(len(publishers) == 1 and publishers[0]['name'] == producer.PUBLISH_PREFIX + commitment,
                  'metadata delegated commands differ from the native whole receipt')
        publication = adapter._job(publishers[0], run, 15368, final_name=publishers[0]['name'])
        A.require(publication.status == 'completed' and publication.conclusion == 'success'
            and publication.started_at is not None and publication.completed_at is not None,
            'metadata delegated owner was not natively published')
        delegated = set(shared_receipt['results'])
    fallback = None
    if generation == 'protected-producer-seven-target-ci-v1':
        # Static analyzers remain parallel. The separate same-M unit job is
        # required only when the original native shared owner lacks contracts.
        matches = [job for job in jobs if job.get('name') == 'workflow-contracts']
        A.require(len(matches) == 1, 'metadata original contract fallback job is missing or ambiguous')
        job = matches[0]
        fact = adapter._job(job, run, 15368, final_name='workflow-contracts')
        expected = 'success' if security == 'true' and 'workflow-contracts' not in delegated else 'skipped'
        A.require(fact.status == 'completed' and fact.conclusion == expected,
                  'metadata original contract fallback did not follow its actual owner')
        if expected == 'success':
            labels = [step for step in job.get('steps', []) if type(step) is dict
                      and step.get('name') == 'Verify remaining workflow contracts']
            A.require(publication is not None
                and P._time(publication.completed_at) <= P._time(fact.started_at)
                and len(labels) == 1 and labels[0].get('status') == 'completed'
                and labels[0].get('conclusion') == 'success'
                and P._time(fact.started_at) <= P._time(labels[0].get('started_at'))
                <= P._time(labels[0].get('completed_at')) <= P._time(fact.completed_at),
                'metadata original fallback contract command did not succeed')
        fallback = {'job': job, 'native': vars(fact)}
    retained = {}
    for path, (name, steps) in _METADATA_OUTER_RECIPES.items():
        required = path.endswith('/documentation-checks.yml') or security == 'true'
        if not required:
            # A previously executed security owner is never silently narrowed.
            A.require(not any(job.get('name') == name and job.get('conclusion') != 'skipped' for job in jobs),
                      'metadata original security owner differs from current route')
            continue
        A.require(current.get(path) == local.get(path) and current.get(path, {}).get('mode') == '100644',
                  'metadata checker workflow differs from current reviewed recipe')
        if path.endswith('/documentation-checks.yml') and DOCUMENTATION_SUITES <= delegated:
            # A skipped reusable caller has its caller name, not the nested
            # callee's job name. Require exactly that native skipped record.
            candidates = [job for job in jobs if job.get('name') in {'documentation', name}]
            A.require(len(candidates) == 1 and candidates[0].get('name') == 'documentation',
                      'metadata delegated documentation native job is ambiguous')
            job = candidates[0]
            fact = adapter._job(job, run, 15368, final_name='documentation')
            A.require(fact.status == 'completed' and fact.conclusion == 'skipped',
                      'metadata delegated documentation must be precisely skipped')
            retained[path] = {'job': job, 'native': vars(fact),
                'shared_suites': sorted(DOCUMENTATION_SUITES), 'publication': vars(publication)}
            continue
        matching = [item for item in references if type(item) is dict and item.get('path') ==
            A.REPOSITORY + '/' + path + '@' + binding['merge_sha']]
        A.require(len(matching) == 1 and matching[0].get('sha') == binding['merge_sha']
            and matching[0].get('ref') == f"refs/pull/{binding['pull_request']}/merge",
            'metadata checker has no original same-M reusable source')
        source_reference = matching[0]
        candidates = [job for job in jobs if job.get('name') == name]
        A.require(len(candidates) == 1, 'metadata checker job missing or ambiguous')
        job = candidates[0]
        fact = adapter._job(job, run, 15368, final_name=name)
        A.require(fact.status == 'completed' and fact.conclusion == 'success', 'metadata checker did not pass')
        A.require(type(job.get('steps')) is list and all(type(step) is dict for step in job['steps']),
                  'metadata checker native steps unavailable')
        for label in steps:
            matching = [step for step in job['steps'] if step.get('name') == label]
            delegated_contract = (generation == 'protected-producer-seven-target-ci-v1'
                and path.endswith('/workflow-security.yml')
                and label == 'Verify fail-closed workflow contracts')
            expected = 'skipped' if delegated_contract else 'success'
            A.require(len(matching) == 1 and matching[0].get('status') == 'completed'
                and matching[0].get('conclusion') == expected
                and (delegated_contract or P._time(fact.started_at) <= P._time(matching[0].get('started_at'))
                     <= P._time(matching[0].get('completed_at')) <= P._time(fact.completed_at)),
                'metadata checker command did not succeed in its authenticated job')
        retained[path] = {'job': job, 'native': vars(fact), 'reference': source_reference}
    result = {'run': run, 'jobs': jobs, 'retained': retained}
    if fallback is not None:
        result['contract_fallback'] = fallback
    return result


def verify_metadata(event, environment, adapter, *, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Retain same-PR protected proof; never capture a consumer E or emit PASS."""
    A.require(_source_qualified(), 'protected metadata retention is not qualified')
    helper = _metadata_module(root)
    A.require(helper.SOURCE_READY is True, 'metadata source capability is disabled')
    native = helper.native(event, environment, root=root, caller='.github/workflows/repository-checks.yml')
    A.require(environment.get('GITHUB_JOB') == 'route', 'metadata retention requires the reviewed routing job')
    binding, refs = adapter.current(native['number'])
    producer._event_binding(event, binding)
    A.require(binding['merge_sha'] == native['merge'] and binding['base_ref'] == refs['default_ref'] == 'main'
        and refs['default'] == binding['base_sha'] == native['base'], 'metadata current default/candidate differs')
    previous_sha, previous = full_tree(adapter, binding['base_sha'])
    tree_sha, current = full_tree(adapter, binding['merge_sha'])
    local = inputs.full_tree(root, 'HEAD')
    A.require(previous == local and execution.checkout_identity(root) == (binding['base_sha'], previous_sha)
        and tree_sha == binding['merge_tree'], 'metadata actual trusted source differs from protected main')
    policy = producer._host_policy()
    package = policy.package_policy()
    A.require(package.validate_tree_wiring(current) in {
        'protected-producer-metadata-ci-v1', 'protected-producer-seven-target-ci-v1'},
              'metadata requires the exact complete six-file source generation')
    controller = original_controller(policy, previous, local, root)
    registry = inputs.load_registry(Path(root) / '.github/test-suites.json')
    owners = metadata_selection(event, binding, previous, current, local, registry, policy,
        root=root, read_blob=adapter.api.immutable_blob)
    selected_profile = owners['selection']
    selected = selected_profile['selection']
    affected=_affected_receipt_selection(selected_profile,registry,binding['base_ref'])
    plan, api_policy = _policy(policy, registry, binding, controller, adapter, root, selected)
    snapshot = adapter.capture(native['number'], plan, api_policy, now=clock())
    A.require(snapshot.binding == binding and snapshot.references == refs
        and native['run_id'] in snapshot.metadata_nonproducers,
        'current invocation is not an authenticated one-way metadata non-producer')
    authority = P.select_authority(snapshot.observations, binding, plan, api_policy.producer,
        inventory_complete=snapshot.inventory_complete, now=clock())
    A.require(authority['state'] == 'proof-required', 'newest original producer is not qualified')
    observation = next(value for value in snapshot.observations if value.run.run_id == authority['run_id'])
    raw, facts = adapter._artifact(observation.run, 'aggregate', snapshot.artifact_inventories[authority['run_id']],
                                   clock(), binding['head_sha'])
    A.require(raw is not None and facts is not None, 'original protected aggregate unavailable')
    aggregate = P.read_artifact(raw, 'aggregate', facts, observation.run, now=clock())
    receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
    A.require(type(receipt) is dict and receipt.get('schema') == 3, 'original protected receipt unavailable')
    original_git = producer.expected_git_context(adapter, binding)
    execution.validate_receipt(receipt, registry, current,
        require_all=selected_profile['profile'] != ci_profile.PROFILE and not affected, expected_git_context=original_git)
    A.require(receipt['requested_suites'] == selected['suites']
        and receipt['include_platform'] == selected['include_platform'], 'metadata owner inventory differs')
    environment_original = receipt['environment']
    if selected_profile['profile'] == ci_profile.PROFILE:
        admitted = runtime_ci.plan_original_reuse(environment_original, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), selected, selected, current, current, local,
            registry, receipt['results'], root=root, read_blob=adapter.api.immutable_blob)['admission']
    else:
        admitted = attested.validate_environment(environment_original, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), root=root, isolated=True)
        reused = inputs.plan_reuse(registry, current, current, receipt['results'], environment_original, environment_original)
        _require_full_reuse_partition(reused,registry,selected,affected)
    outer_before = metadata_outer_jobs(adapter, observation.run.run_id, binding, current, local,
                                       owners['route']['security'], shared_receipt=receipt, root=root)
    context = P.SharedContext(registry, current, environment_original, binding['merge_sha'], tree_sha, original_git)
    verified = adapter.verify(native['number'], plan, api_policy, {'shared-host': context}, clock=clock)
    A.require(verified['run_id'] == observation.run.run_id
        and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
        and verified['aggregate_digest'] == aggregate['aggregate_digest']
        and metadata_outer_jobs(adapter, observation.run.run_id, binding, current, local,
                                owners['route']['security'], shared_receipt=receipt, root=root) == outer_before
        and adapter.current(native['number']) == (binding, refs) and clock() < P._time(verified['expires_at']),
        'metadata original execution or current source changed')
    A.require(_source_qualified() and helper.SOURCE_READY is True
        and helper.native(event, environment, root=root, caller='.github/workflows/repository-checks.yml') == native
        and execution.checkout_identity(root) == (binding['base_sha'], previous_sha)
        and inputs.full_tree(root, 'HEAD') == local
        and original_controller(policy, previous, local, root) == controller
        and clock() < P._time(verified['expires_at']),
        'metadata actual trusted controller changed before retention')
    return {'kind': 'same-pr-metadata-retention', 'qualification': False, 'metadata_only': 'true',
        'binding': binding, 'original_proof': verified, 'original_environment_digest': admitted['environment_digest'],
        'retained_suites': selected['suites'], 'executed_suites': [], 'retained_checker_jobs': outer_before['retained']}


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
