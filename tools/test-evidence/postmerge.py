#!/usr/bin/env python3
"""Source-staged finite protected-target consumer of ORIGINAL PR evidence.

No candidate checkout, runtime probe, installation or test command is needed to
look up proof. Unsupported proof leaves the existing actual execution selected.
This entrypoint never executes candidate code or emits a qualification receipt.
"""
from __future__ import annotations
from types import SimpleNamespace

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
               'protected-producer-seven-target-ci-v1', producer.PLATFORM_GENERATION,
               ci_profile.RETAINED_SOURCE_GENERATION}
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
    # A future exact catalog recipe keeps the required final check separate
    # from its common job. verify_main still authenticates the complete recipe.
    if workflow == 'parent-qualification' and environment.get('GITHUB_JOB') == 'common-parent':
        expected['GITHUB_JOB'] = 'common-parent'
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


def integrated_controller_for_reuse(policy, previous, current, local, target, root):
    """Source4 lookup precheck only; complete original projection is checked later."""
    A.require(set(producer.controller_sources(policy))==set(source_admission.CONTROLLERS),
        'reuse controller graph is not independently reviewed')
    before=ci_profile.reuse_controller_precheck(previous,local,target,root=root)
    after=ci_profile.reuse_controller_precheck(current,local,target,root=root)
    A.require(before==after, 'current executable or target declarations changed')
    return before['controller_digest']


def _policy(policy, registry, binding, controller, adapter, root, selected, *, common_owner=None, template=None):
    tree = inputs.full_tree(root, 'HEAD')
    entry = tree.get(producer.TEMPLATE if template is None else template)
    A.require(type(entry) is dict and entry['mode'] == '100644' and entry['type'] == 'blob',
              'trusted protected producer template unavailable')
    original = P.Policy(A.REPOSITORY, 1319052603, 15368, '.github/workflows/project-tests.yml',
        entry['sha'], f"refs/pull/{binding['pull_request']}/merge", ('pull_request',), controller,
        sandbox.contract(root)['digest'], required_execution_schema=producer.execution_schema(policy,
            full_tree(adapter,binding['merge_sha'])[1],binding['base_ref']))
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
    plan = {'owners': {'shared-host': common_owner if common_owner is not None else
        {'kind': 'shared', 'suites': selected['suites'],
         'include_platform': selected['include_platform'], 'platform': {}}}}
    A._policy(result, plan, binding['pull_request'])
    return plan, result


def original_platform_owner(adapter, run, partition, *, now):
    """Native job observation only; no platform artifact becomes reusable E."""
    latest = adapter._object('actions/runs/' + str(run.run_id))
    attempt = adapter._object(f'actions/runs/{run.run_id}/attempts/1')
    fields = ('id', 'run_attempt', 'workflow_id', 'check_suite_id', 'head_sha',
              'head_branch', 'event', 'path', 'status', 'conclusion')
    A.require(all(latest.get(key) == attempt.get(key) for key in fields)
        and latest.get('id') == run.run_id and latest.get('run_attempt') == 1
        and (latest.get('status'), latest.get('conclusion')) == ('completed', 'success'),
        'original Android platform native run changed')
    jobs = adapter._pages(f'actions/runs/{run.run_id}/attempts/1/jobs', 'jobs')
    observed = producer._completed_platform_job(adapter, attempt, jobs, producer.PLATFORM_JOB, now)
    return {'kind': 'original-android-platform-native-job-v1', 'job_id': observed['job_id'],
        'run_id': run.run_id, 'attempt': 1, 'partition': partition['digest'],
        'job': observed['job'], 'reusable': False, 'qualification': False}


def _affected_receipt_selection(profile, registry, target):
    """Scope receipts only AFTER protected selection_profile rederives the plan.

    This structural check supplies no selection authority. That entrypoint has
    already checked actual registry bytes, the immutable protected dependency
    graph, complete B/M/D lookup and the independent legacy preparation gate.
    """
    selected=profile['selection']
    if selected.get('reason')!='protected-affected-dependencies':
        return False
    versioned = selected.get('affected',{}).get('dependency_schema') == 2
    A.require(target in source_admission.TARGET_PROFILES and (target=='main' or versioned)
        and (not versioned or selected['affected'].get('target') == target)
        and profile['profile']==producer.FULL_PROFILE and selected['full_host'] is True
        and type(selected['include_platform']) is bool
        and (selected['include_platform'] is False or target in producer._PLATFORM_TARGETS and versioned)
        and selected['suites']==selected['affected']['required']
        and bool(selected['suites']) and set(selected['suites'])<set(registry['suites']),
            'affected receipt does not have an independently selected finite-target full-runtime subset')
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
    generation = package.validate_tree_wiring(current)
    A.require(generation in GENERATIONS,
              'current target does not contain the exact complete consumer generation')
    workflow=references['integration']['workflow_path']
    documentation=workflow==A.DOCUMENTATION_PUSH_WORKFLOW
    future = generation == producer.PLATFORM_GENERATION
    template = (workflow if documentation else
        producer.PLATFORM_PARENT_TEMPLATE if future and workflow=='.github/workflows/parent-qualification.yml' else
        producer.PLATFORM_TEMPLATE if future else
        TEMPLATE if workflow=='.github/workflows/parent-qualification.yml' else producer.TEMPLATE)
    A.require(workflow in {'.github/workflows/parent-qualification.yml','.github/workflows/project-tests.yml',A.DOCUMENTATION_PUSH_WORKFLOW}
        and environment.get('GITHUB_WORKFLOW_REF')==A.REPOSITORY+'/'+workflow+'@refs/heads/'+target
        and current.get(workflow)==local.get(template) and local.get(template,{}).get('mode')=='100644',
        'actual protected push workflow differs from trusted canonical source')
    A.require(environment.get('GITHUB_JOB') != 'common-parent' or future,
        'separate common push job is not an enrolled complete recipe')
    _, previous = full_tree(adapter, binding['base_sha'])
    controller_check=integrated_controller_for_reuse if future else integrated_controller
    controller = controller_check(policy,previous,current,local,target,root)
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
    select_profile=producer.selection_profile_for_reuse if future else producer.selection_profile
    current_profile = select_profile(policy, registry, current, previous, selection_context, root=root,target=target,read_blob=read_blob)
    selected = current_profile['selection']
    affected=_affected_receipt_selection(current_profile,registry,target)
    if documentation:
        A.require(DOCUMENTATION_SUITES <= set(selected['suites']),
            'original shared owner does not contain every documentation command')
    if target!='main':
        supported = (current_profile['profile']==producer.FULL_PROFILE and selected['full_host'] is True
            and (set(selected['suites'])==set(registry['suites']) or affected)
            or current_profile['profile']==ci_profile.PROFILE
                and current_profile['binding'].get('generation_kind')==ci_profile.SEVEN_CONTROLLER_KIND)
        A.require(future and supported, 'child protected reuse requires its independently admitted versioned owner')
    partition = producer.platform_partition(policy, current_profile, registry, current, previous, local,
        target=target, root=root, read_blob=read_blob)
    if partition is None:
        A.require(source_admission.shared_platform_supported(selected,target,current.get(source_admission.PROFILE)),
            'required platform owners need existing actual execution')
    owner = producer.common_owner(current_profile, partition)
    plan, api_policy = _policy(policy, registry, binding, controller, adapter, root, selected,
        common_owner=owner, template=producer.PLATFORM_TEMPLATE if future else None)
    snapshot = adapter.capture_integrated(run_id, plan, api_policy, now=clock())
    A.require(snapshot.references == references, 'integration changed before original proof selection')
    if future:
        current_profile,selection_context=producer.reuse_source_profile(snapshot,adapter,api_policy,policy,registry,
            current,previous,root=root,target=target,read_blob=read_blob,now=clock())
        selected=current_profile['selection'];affected=_affected_receipt_selection(current_profile,registry,target)
        partition=producer.platform_partition(policy,current_profile,registry,current,previous,local,
            target=target,root=root,read_blob=read_blob)
        owner=producer.common_owner(current_profile,partition)
        plan,api_policy=_policy(policy,registry,binding,controller,adapter,root,selected,
            common_owner=owner,template=producer.PLATFORM_TEMPLATE)
    original_tree_sha, original_tree = full_tree(adapter, snapshot.binding['merge_sha'])
    A.require(original_tree_sha == snapshot.binding['merge_tree'] == current_tree_sha and original_tree == current,
              'integrated file tree differs from the complete actually tested source')
    original_profile = select_profile(policy, registry, original_tree, previous, selection_context, root=root,target=target,read_blob=read_blob)
    A.require(original_profile == current_profile, 'original and current independently selected owners differ')
    A.require(producer.platform_partition(policy, original_profile, registry, original_tree, previous, local,
        target=target, root=root, read_blob=read_blob) == partition,
        'original and current Android partitions differ')
    authority = P.select_authority(snapshot.observations, snapshot.binding, plan, api_policy.producer,
                                   inventory_complete=snapshot.inventory_complete, now=clock())
    A.require(authority['state'] == 'proof-required', 'newest original producer cannot establish complete proof')
    observation = next(value for value in snapshot.observations if value.run.run_id == authority['run_id'])
    platform_observation = (original_platform_owner(adapter, observation.run, partition, now=clock())
        if partition is not None else None)
    raw, facts = adapter._artifact(observation.run, 'aggregate', snapshot.artifact_inventories[authority['run_id']],
                                   clock(), snapshot.binding['head_sha'])
    A.require(raw is not None and facts is not None, 'original aggregate unavailable')
    aggregate = P.read_artifact(raw, 'aggregate', facts, observation.run, now=clock())
    receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
    A.require(type(receipt) is dict and receipt.get('schema') == api_policy.producer.required_execution_schema,
              'original versioned isolated execution receipt unavailable')
    original_git = producer.expected_git_context(adapter, snapshot.binding)
    execution.validate_receipt(receipt, registry, original_tree,
        require_all=original_profile['profile'] != ci_profile.PROFILE and not affected, expected_git_context=original_git)
    A.require(receipt['requested_suites'] == selected['suites']
        and receipt['include_platform'] == owner['include_platform']
        and (partition is None or receipt['platform_results'] == {}),
        'original receipt differs from independently selected shared owners')
    original_environment = receipt['environment']
    retained=producer.retained_receipt_source(receipt,snapshot.binding,adapter,registry,selected,
        authority['run_id'],root=root)
    context = P.SharedContext(registry, original_tree, original_environment,
                             snapshot.binding['merge_sha'], original_tree_sha, original_git,retained)
    original_source=None
    if receipt['schema']==4:
        verified,original_source=producer.verify_original_source(adapter,run_id,plan,api_policy,context,
            receipt,snapshot.binding,integrated=True,root=root,clock=clock)
    if original_profile['profile'] == ci_profile.PROFILE:
        reuse = runtime_ci.plan_original_reuse(original_environment, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), selected, current_profile['selection'],
            original_tree, current, local, registry, receipt['results'], root=root,read_blob=read_blob,
            target=target,base_tree=previous,**({'original_source':original_source} if original_source is not None else {}))
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
    if original_source is None:
        verified=adapter.verify_integrated(run_id,plan,api_policy,{'shared-host':context},clock=clock)
    else:
        A.require(A.Adapter.verify_integrated(adapter,run_id,plan,api_policy,{'shared-host':context},clock=clock)==verified,
            'original native proof changed during runtime/source admission')
    # The original data above supplies no authority. Only these fresh complete
    # snapshots authenticate the owner, attempt, hash publisher, E and expiry.
    if partition is not None:
        A.require(original_platform_owner(adapter, observation.run, partition, now=clock()) == platform_observation,
            'original required Android platform job changed during common proof verification')
    A.require(verified['integration'] == references['integration']
        and verified['source_chain']['producer_commit'] == snapshot.binding['merge_sha']
        and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
        and verified['aggregate_digest'] == aggregate.get('aggregate_digest')
        and clock() < P._time(verified['expires_at'])
        and execution.checkout_identity(root)==(references['default'],default_tree_sha)
        and controller_check(policy,previous,current,local,target,root)==controller
        and default_authority(adapter,references)==source_authority
        and producer.retained_receipt_source(receipt,snapshot.binding,adapter,registry,selected,authority['run_id'],root=root)==retained,
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
        'original_proof': verified, 'original_protected_source':retained, 'original_environment_digest': admission['environment_digest'],
        'runtime_admission': runtime_admission, 'reused_suites': reused_suites, 'executed_suites': [],
        'package_work': package_work,
        **({'external_platform_required': True, 'platform_partition': partition['digest'],
            'original_platform_job': platform_observation} if partition is not None else {})}


def _metadata_module(root=ROOT):
    spec = importlib.util.spec_from_file_location('trusted_native_metadata_context',
        Path(root) / 'tools/repository-checks/metadata_context.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def metadata_selection(event, binding, previous, current, local, registry, policy, *, root=ROOT, read_blob=None, _reuse_only=False):
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
    selector=producer.selection_profile_for_reuse if _reuse_only else producer.selection_profile
    selected = selector(policy, registry, current, previous, local,
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
    current_owners = generation in {'protected-producer-seven-target-ci-v1', ci_profile.RETAINED_SOURCE_GENERATION}
    if current_owners and shared_receipt is not None:
        # This is an observation used on both sides of verify_metadata's full
        # adapter.verify call below. It never supplies standalone proof. Bind
        # the conditional owner facts to the ACTUAL completed native whole hash;
        # the unchanged original aggregate protocol authenticates its complete
        # source, versioned runtime, descriptor, jobs, results and artifacts.
        A.require(type(shared_receipt) is dict and shared_receipt.get('schema') ==
            (4 if generation == ci_profile.RETAINED_SOURCE_GENERATION else 3)
            and shared_receipt.get('candidate_commit') == binding['merge_sha']
            and shared_receipt.get('candidate_tree') == binding['merge_tree']
            and shared_receipt.get('reusable') is True
            and type(shared_receipt.get('requested_suites')) is list
            and type(shared_receipt.get('results')) is dict
            and set(shared_receipt['results']) == set(shared_receipt['requested_suites'])
            and all(type(value) is dict and value.get('status') == 'passed'
                    for value in shared_receipt['results'].values()),
            'metadata delegated commands have no original successful versioned receipt')
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
    if generation == ci_profile.RETAINED_SOURCE_GENERATION:
        matches = [job for job in jobs if job.get('name') == producer.PLATFORM_JOB]
        A.require(len(matches) == 1, 'metadata platform owner native record is missing or ambiguous')
        fact = adapter._job(matches[0], run, 15368, final_name=producer.PLATFORM_JOB)
        A.require(fact.status == 'completed' and fact.conclusion == 'skipped',
                  'metadata initial class cannot retain an executed platform owner')
    if current_owners:
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
            delegated_contract = (current_owners
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
    producer._event_binding(event, binding, api=SimpleNamespace(get=lambda endpoint: adapter._object(endpoint)))
    A.require(binding['merge_sha'] == native['merge'] and binding['head_sha'] == native['head']
        and refs['default_ref'] == 'main', 'metadata current default/candidate differs')
    previous_sha, previous = full_tree(adapter, binding['base_sha'])
    tree_sha, current = full_tree(adapter, binding['merge_sha'])
    local = inputs.full_tree(root, 'HEAD')
    policy = producer._host_policy()
    package = policy.package_policy()
    generation = package.validate_tree_wiring(current)
    future = generation == ci_profile.RETAINED_SOURCE_GENERATION
    A.require(generation in {'protected-producer-metadata-ci-v1',
        'protected-producer-seven-target-ci-v1', ci_profile.RETAINED_SOURCE_GENERATION},
              'metadata requires the exact complete six-file source generation')
    source_context = None
    if future:
        A.require(binding['base_ref'] in source_admission.TARGET_PROFILES,
                  'metadata protected target is not enrolled')
        source_context = producer.reuse_source_context(adapter, binding, refs, policy)
        default_tree, default = full_tree(adapter, refs['default'])
        A.require(local == default and execution.checkout_identity(root) == (refs['default'], default_tree),
                  'metadata actual ROOT differs from current protected default')
        controller = integrated_controller_for_reuse(policy, previous, current, local, binding['base_ref'], root)
    else:
        A.require(binding['base_ref'] == 'main' and refs['default'] == binding['base_sha']
            and previous == local and execution.checkout_identity(root) == (binding['base_sha'], previous_sha),
            'metadata legacy actual trusted source differs from protected main')
        controller = original_controller(policy, previous, local, root)
    A.require(tree_sha == binding['merge_tree'], 'metadata candidate tree differs')
    registry = inputs.load_registry(Path(root) / '.github/test-suites.json')
    owners = metadata_selection(event, binding, previous, current, local, registry, policy,
        root=root, read_blob=adapter.api.immutable_blob,**({'_reuse_only':True} if future else {}))
    selected_profile = owners['selection']
    selected = selected_profile['selection']
    affected=_affected_receipt_selection(selected_profile,registry,binding['base_ref'])
    plan, api_policy = _policy(policy, registry, binding, controller, adapter, root, selected,
        template=producer.project_template(policy,current) if future else None)
    snapshot = adapter.capture(native['number'], plan, api_policy, now=clock())
    A.require(snapshot.binding == binding and snapshot.references == refs
        and native['run_id'] in snapshot.metadata_nonproducers,
        'current invocation is not an authenticated one-way metadata non-producer')
    if future:
        selected_profile,_=producer.reuse_source_profile(snapshot,adapter,api_policy,policy,registry,current,previous,
            root=root,target=binding['base_ref'],read_blob=adapter.api.immutable_blob,now=clock())
        selected=selected_profile['selection'];affected=_affected_receipt_selection(selected_profile,registry,binding['base_ref'])
        plan,api_policy=_policy(policy,registry,binding,controller,adapter,root,selected,
            template=producer.project_template(policy,current))
    authority = P.select_authority(snapshot.observations, binding, plan, api_policy.producer,
        inventory_complete=snapshot.inventory_complete, now=clock())
    A.require(authority['state'] == 'proof-required', 'newest original producer is not qualified')
    observation = next(value for value in snapshot.observations if value.run.run_id == authority['run_id'])
    raw, facts = adapter._artifact(observation.run, 'aggregate', snapshot.artifact_inventories[authority['run_id']],
                                   clock(), binding['head_sha'])
    A.require(raw is not None and facts is not None, 'original protected aggregate unavailable')
    aggregate = P.read_artifact(raw, 'aggregate', facts, observation.run, now=clock())
    receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
    A.require(type(receipt) is dict and receipt.get('schema') == api_policy.producer.required_execution_schema,
              'original versioned protected receipt unavailable')
    original_git = producer.expected_git_context(adapter, binding)
    execution.validate_receipt(receipt, registry, current,
        require_all=selected_profile['profile'] != ci_profile.PROFILE and not affected, expected_git_context=original_git)
    A.require(receipt['requested_suites'] == selected['suites']
        and receipt['include_platform'] == selected['include_platform'], 'metadata owner inventory differs')
    environment_original = receipt['environment']
    outer_before = metadata_outer_jobs(adapter, observation.run.run_id, binding, current, local,
                                       owners['route']['security'], shared_receipt=receipt, root=root)
    retained = producer.retained_receipt_source(receipt,binding,adapter,registry,selected,
        authority['run_id'],root=root)
    context = P.SharedContext(registry, current, environment_original, binding['merge_sha'], tree_sha, original_git,retained)
    original_source=None
    if receipt['schema']==4:
        verified,original_source=producer.verify_original_source(adapter,native['number'],plan,api_policy,
            context,receipt,binding,integrated=False,root=root,clock=clock)
    if selected_profile['profile'] == ci_profile.PROFILE:
        admitted = runtime_ci.plan_original_reuse(environment_original, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), selected, selected, current, current, local,
            registry, receipt['results'], root=root, read_blob=adapter.api.immutable_blob,
            **({'target':binding['base_ref'],'base_tree':previous,'original_source':original_source} if future else {}))['admission']
    else:
        admitted = attested.validate_environment(environment_original, aggregate.get('qualified_at'),
            aggregate.get('expires_at'), clock(), root=root, isolated=True)
        reused = inputs.plan_reuse(registry, current, current, receipt['results'], environment_original, environment_original)
        _require_full_reuse_partition(reused,registry,selected,affected)
    if original_source is None:
        verified=adapter.verify(native['number'],plan,api_policy,{'shared-host':context},clock=clock)
    else:
        A.require(A.Adapter.verify(adapter,native['number'],plan,api_policy,{'shared-host':context},clock=clock)==verified,
            'metadata original native proof changed during runtime/source admission')
    A.require(verified['run_id'] == observation.run.run_id
        and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
        and verified['aggregate_digest'] == aggregate['aggregate_digest']
        and producer.retained_receipt_source(receipt,binding,adapter,registry,selected,
            authority['run_id'],root=root) == retained
        and metadata_outer_jobs(adapter, observation.run.run_id, binding, current, local,
                                owners['route']['security'], shared_receipt=receipt, root=root) == outer_before
        and adapter.current(native['number']) == (binding, refs) and clock() < P._time(verified['expires_at']),
        'metadata original execution or current source changed')
    A.require(_source_qualified() and helper.SOURCE_READY is True
        and helper.native(event, environment, root=root, caller='.github/workflows/repository-checks.yml') == native
        and inputs.full_tree(root, 'HEAD') == local
        and (producer.reuse_source_context(adapter,binding,refs,policy) == source_context
            and execution.checkout_identity(root) == (refs['default'], default_tree)
            and integrated_controller_for_reuse(policy,previous,current,local,binding['base_ref'],root) == controller
            if future else execution.checkout_identity(root) == (binding['base_sha'], previous_sha)
            and original_controller(policy, previous, local, root) == controller)
        and clock() < P._time(verified['expires_at']),
        'metadata actual trusted controller changed before retention')
    return {'kind': 'same-pr-metadata-retention', 'qualification': False, 'metadata_only': 'true',
        'binding': binding, 'original_proof': verified, 'original_environment_digest': admitted['environment_digest'],
        'retained_suites': selected['suites'], 'executed_suites': [], 'retained_checker_jobs': outer_before['retained'],
        'original_protected_source':retained}


def no_execution_context(event, environment, adapter, *, candidate=None, root=ROOT,
                         clock=lambda: datetime.now(timezone.utc)):
    """Authenticate unchanged push inputs, without an executor or original E.

    Omitting candidate is allowed only for the early scheduling observation.
    The fixed recipe and final aggregate repeat this with actual Git objects.
    No successful/reused suite or reusable execution receipt is produced.
    """
    A.require(_source_qualified(), 'unchanged consumer source is unavailable')
    source, run_id = _native(event, environment)
    # Fast refusal only: ordinary pushes must not pay for a second complete
    # source/native lookup. These two immutable IDs confer no skip authority.
    source_tree, _ = adapter._commit(source)
    previous_tree, _ = adapter._commit(A.sha(event.get('before')))
    A.require(source_tree == previous_tree, 'current push has changed inputs')
    binding, refs = adapter._integrated_current(run_id, 15368, clock())
    target = binding['base_ref']
    documentation = refs['integration']['workflow_path'] == A.DOCUMENTATION_PUSH_WORKFLOW
    targets = A.DOCUMENTATION_PUSH_BRANCHES if documentation else {'main','apple-main','android-main','android-vr'}
    workflow = A.DOCUMENTATION_PUSH_WORKFLOW if documentation else '.github/workflows/parent-qualification.yml'
    A.require(target in targets
        and refs['target'] == source == binding['merge_sha'] and refs['default_ref'] == 'main'
        and event.get('before') == binding['base_sha']
        and refs['integration']['workflow_path'] == workflow,
        'unchanged consumer has no current native source')
    authority = default_authority(adapter, refs)
    tree, current = full_tree(adapter, source)
    before_tree, previous = full_tree(adapter, binding['base_sha'])
    default_tree, local = full_tree(adapter, refs['default'])
    A.require(tree == before_tree == binding['merge_tree'] == refs['integration']['tree']
        and current == previous and execution.checkout_identity(root) == (refs['default'], default_tree)
        and inputs.full_tree(root, refs['default']) == local,
        'complete unchanged inputs or trusted source differ')
    policy = producer._host_policy()
    package = policy.package_policy()
    template = workflow if documentation else producer.PLATFORM_PARENT_TEMPLATE
    A.require(package.validate_tree_wiring(current) == producer.PLATFORM_GENERATION
        and current.get(workflow) == local.get(template)
        and local.get(template, {}).get('mode') == '100644',
        'unchanged consumer requires the complete fixed future recipe')
    controller = integrated_controller_for_reuse(policy, previous, current, local, target, root)
    if candidate is not None:
        A.require(execution.checkout_identity(candidate) == (source, tree)
            and inputs.full_tree(candidate, source) == current,
            'unchanged parent candidate differs from complete native inventory')
        plan = package.candidate_plan(candidate, event, source)
        A.require(plan['host_mode'] == 'unchanged', 'unchanged parent plan is not independently empty')
        package.verify_empty_plan(plan, candidate, event)
        A.require(plan['verified_empty_delta']['tree'] == tree,
            'raw unchanged proof differs from native tree')
    return {'schema': 1, 'kind': 'protected-parent-no-execution-v1', 'authority': 'none',
        'reusable': False, 'qualification': False, 'execution': None,
        'executed_suites': [], 'reused_suites': [], 'binding': binding, 'refs': refs,
        'controller': controller, 'default_authority': authority, 'tree': tree}


def _running_documentation_no_execution(adapter, context, environment, now):
    """Actual current validation job, never completion or test/E authority."""
    run_id = int(environment['GITHUB_RUN_ID'])
    A.require(environment.get('GITHUB_JOB') == 'documentation-source'
        and context['refs']['integration']['workflow_path'] == A.DOCUMENTATION_PUSH_WORKFLOW,
        'unchanged documentation has no fixed native role')
    latest = adapter._object(f'actions/runs/{run_id}')
    attempt = adapter._object(f'actions/runs/{run_id}/attempts/1')
    fields = ('id','workflow_id','check_suite_id','path','event','head_sha','head_branch',
        'run_attempt','status','conclusion')
    A.require(all(latest.get(key) == attempt.get(key) for key in fields)
        and attempt.get('id') == run_id and attempt.get('run_attempt') == 1
        and attempt.get('head_sha') == context['binding']['merge_sha']
        and attempt.get('head_branch') == context['binding']['base_ref']
        and attempt.get('event') == 'push' and attempt.get('path') == A.DOCUMENTATION_PUSH_WORKFLOW
        and attempt.get('workflow_id') == context['refs']['integration']['workflow_id']
        and (attempt.get('status'),attempt.get('conclusion')) == ('in_progress',None),
        'unchanged documentation is not the current original native attempt')
    name = 'Authenticate original documentation owner'
    jobs = adapter._pages(f'actions/runs/{run_id}/attempts/1/jobs','jobs')
    matches = [job for job in jobs if job.get('name') == name]
    A.require(len(matches) == 1, 'unchanged documentation native job is missing or ambiguous')
    observed = adapter._job(matches[0],attempt,15368,final_name=name)
    A.require((observed.status,observed.conclusion) == ('in_progress',None)
        and P._time(observed.started_at) <= now and observed.completed_at is None,
        'unchanged documentation validation is not running')
    return {'run':attempt,'job':matches[0],'native_check':vars(observed)}


def verify_no_execution(event, environment, adapter, *, candidate, root=ROOT,
                        clock=lambda: datetime.now(timezone.utc)):
    before = no_execution_context(event, environment, adapter, candidate=candidate, root=root, clock=clock)
    context = {'run_id': int(environment['GITHUB_RUN_ID']), 'binding': before['binding'],
        'refs': before['refs'], 'integration': before['refs']['integration']}
    documentation = before['refs']['integration']['workflow_path'] == A.DOCUMENTATION_PUSH_WORKFLOW
    native = (_running_documentation_no_execution(adapter,before,environment,clock()) if documentation else
        producer._push_platform_job(context, adapter, 'Common parent tests'))
    A.require(no_execution_context(event, environment, adapter, candidate=candidate, root=root, clock=clock) == before,
        'unchanged consumer source changed during verification')
    if documentation:
        A.require(_running_documentation_no_execution(adapter,before,environment,clock()) == native,
            'unchanged documentation native validation changed')
    return before


def lookup(event, environment, adapter=None, *, root=ROOT, clock=lambda: datetime.now(timezone.utc)):
    """Pre-execution only: no failure is hidden by retrying an alternate executor."""
    try:
        if not _source_qualified():
            return {'reused': False, 'reason': 'protected-consumer-not-qualified'}
        adapter = adapter or A.Adapter()
        # This is scheduling only. Missing proof still takes the existing
        # execution route; the final no-setup recipe must rederive raw equality.
        try:
            empty = no_execution_context(event, environment, adapter, root=root, clock=clock)
        except (P.ProtocolError, inputs.InputError, execution.ExecutionError,
                producer.PreExecutionUnavailable, OSError, subprocess.SubprocessError,
                KeyError, TypeError, ValueError, AttributeError):
            empty = None
        if empty is not None:
            return {'reused': False, 'no_execution': True, 'proof': empty}
        proof = verify_main(event, environment, adapter, root=root, clock=clock)
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
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--verify-empty', action='store_true')
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
    if args.verify_empty:
        A.require(args.candidate is not None, 'unchanged verification requires actual candidate objects')
        result = {'reused': False, 'no_execution': True, 'proof': verify_no_execution(
            event, os.environ, A.Adapter(), candidate=args.candidate)}
    else:
        result = lookup(event, os.environ)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(P.canonical(result))
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write('shared_reused=' + str(result['reused']).lower() + '\n')
        output.write('package_work=' + str(not result.get('no_execution', False)
            and (not result['reused'] or result['proof']['package_work'])).lower() + '\n')
        output.write('no_execution=' + str(result.get('no_execution', False)).lower() + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
