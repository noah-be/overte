#!/usr/bin/env python3
"""Protected reusable-PR producer; source capability is not qualification.

Only native server context and the fixed read-only API establish invocation
facts. No CLI argument supplies an endpoint, command, policy flag or proof.
Candidate output never establishes source identity, environment or cleanup.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import zipfile

import attested
import execution
import inputs
import producer as protocol
import producer_api
import sandbox
import sandbox_host as host
import sandbox_shared as shared
import ci_profile
import runtime_ci
import source_admission

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = 'tools/repository-checks/workflows/producers/protected-project-tests.yml'
PRODUCTION_READY = True
DESCRIPTOR_JOB = 'project / Publish producer descriptor'
SHARED_JOB = 'project / Shared tests'
PUBLISH_PREFIX = 'project / Publish final producer '
FULL_PROFILE = 'ubuntu24-host-qt5-qt6-v1'


class PreExecutionUnavailable(host.Unavailable):
    """No candidate suite has started; existing mandatory execution is needed."""


def protected_admission(*, root=None):
    """Check trusted capabilities/policy before setup, never host qualification.

    Native context, complete source ownership, actual before/after E and kernel
    cleanup remain mandatory in the selected supervisor and final publisher.
    """
    if PRODUCTION_READY is not True:
        raise PreExecutionUnavailable('protected producer source is not qualified')
    root = ROOT if root is None else root
    try:
        sandbox.require_protected_execution(root)
        attested.load_policy(root, isolated=True)
    except (sandbox.SandboxUnavailable, attested.AttestedReuseUnavailable) as error:
        raise PreExecutionUnavailable('protected producer policy is not qualified') from error


def utc_seconds(now=None):
    value = datetime.now(timezone.utc) if now is None else now
    protocol._now(value)
    return value.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def git_context(snapshot):
    value = {'profile': snapshot['profile'], **snapshot['git_context']}
    execution.validate_git_context(value, snapshot['identity']['commit'], snapshot['identity']['tree'])
    return value


def expected_git_context(adapter, binding):
    """Reconstruct original depth-2 context from immutable API commit facts."""
    commits = {}
    for revision in dict.fromkeys([binding['merge_sha'], *binding['merge_parents']]):
        tree, parents = adapter._commit(revision)
        commits[revision] = {'commit': revision, 'tree': tree, 'parents': parents}
    value = {'profile': 'streamed-candidate-source-v1', 'commits': commits,
             'shallow': sorted(oid for oid, identity in commits.items() if set(identity['parents']) - commits.keys())}
    execution.validate_git_context(value, binding['merge_sha'], binding['merge_tree'])
    host.require(commits[binding['merge_sha']]['parents'] == binding['merge_parents'], 'original ordered parents changed')
    return value


def _host_policy():
    spec = importlib.util.spec_from_file_location('protected_producer_host_selection', ROOT / 'tools/repository-checks/host_selection.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event_binding(event, binding):
    repository = {'full_name': 'noah-l-frank/overte', 'id': 1319052603}
    host.require(isinstance(event, dict) and all(event.get('repository', {}).get(key) == value
                 for key, value in repository.items()), 'event repository differs from native producer')
    pr = event.get('pull_request')
    host.require(isinstance(pr, dict) and event.get('number') == pr.get('number') == binding['pull_request'],
                 'event PR number differs from current candidate')
    for side in ('base', 'head'):
        branch = pr.get(side, {})
        host.require(isinstance(branch, dict) and branch.get('sha') == binding[side + '_sha']
                     and branch.get('ref') == binding[side + '_ref']
                     and all(branch.get('repo', {}).get(key) == value for key, value in repository.items()),
                     'event branch differs from independently read current candidate')


def _native(environment):
    expected = {'GITHUB_REPOSITORY': 'noah-l-frank/overte', 'GITHUB_REPOSITORY_ID': '1319052603',
                'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'pull_request',
                'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24', 'GITHUB_RUN_ATTEMPT': '1'}
    host.require(all(environment.get(key) == value for key, value in expected.items()), 'unsupported protected producer context')
    host.require(environment.get('GITHUB_BASE_REF') in source_admission.TARGET_PROFILES,
                 'unsupported protected producer target')
    ref = environment.get('GITHUB_REF', '')
    match = re.fullmatch(r'refs/pull/([1-9][0-9]*)/merge', ref)
    host.require(match is not None and re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', ''))
                 and re.fullmatch(r'[0-9a-f]{40}', environment.get('GITHUB_SHA', ''))
                 and environment.get('GITHUB_WORKFLOW_SHA') == environment['GITHUB_SHA']
                 and environment.get('GITHUB_WORKFLOW_REF') == 'noah-l-frank/overte/.github/workflows/repository-checks.yml@' + ref,
                 'native producer invocation source is unavailable')
    return int(match[1]), int(environment['GITHUB_RUN_ID'])


def controller_sources(policy):
    """Finite reviewed producer graph, independent of consumer process imports.

    An original protected base must retain these exact reviewed bytes before a
    consumer may reconstruct its controller identity. Historical Python is data,
    never code loaded by that consumer.
    """
    return sorted({source_admission.SELF, inputs.AFFECTED_POLICY, *shared.sources(), *policy.package_policy()._policy_inputs(), *attested._CONSUMER_FILES, TEMPLATE,
        'tools/repository-checks/metadata_context.py',
        'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
        '.github/workflows/documentation-checks.yml', '.github/workflows/workflow-security.yml',
        'tools/native-tests/check.py',
        ci_profile.POLICY, 'tools/test-evidence/ci_profile.py', 'tools/test-evidence/runtime_ci.py',
        *('tools/test-evidence/' + name + '.py' for name in (
            'attested', 'execution', 'inputs', 'runtime', 'sandbox', 'sandbox_host',
            'sandbox_shared', 'producer', 'producer_api', 'producer_workflow')),
        *('tools/repository-checks/' + name + '.py' for name in (
            'host_selection', 'package_checks', 'check', 'tool_dependencies', 'npm_consumers'))})


def _controller_identity(policy):
    # Bind the actually reached protected modules, not all application files.
    # Imports from the immutable candidate are never performed in this process.
    names = set(controller_sources(policy))
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(ROOT):
            relative = Path(path).resolve().relative_to(ROOT).as_posix()
            host.require(relative.endswith('.py') and relative in names,
                         'protected controller imported an unreviewed repository module')
    identity = {}
    revision, _ = execution.checkout_identity(ROOT)
    for name in sorted(names):
        raw = sandbox._source(ROOT, name)
        rows = sandbox._git(ROOT, 'ls-tree', '-z', revision, '--', name).split(b'\0')
        host.require(len(rows) == 2 and not rows[1], 'protected controller source is absent or ambiguous')
        fields, path = rows[0].split(b'\t')
        mode, kind, oid = fields.split()
        host.require(path.decode() == name and mode in {b'100644', b'100755'} and kind == b'blob'
                     and sandbox._git(ROOT, 'cat-file', 'blob', oid.decode(), limit=1_000_000) == raw,
                     'loaded controller differs from immutable trusted source')
        identity[name] = {'mode': mode.decode(), 'sha256': hashlib.sha256(raw).hexdigest()}
    return protocol.digest(identity)


def metadata_generations(policy, *, root=ROOT):
    """Finite future workflow/helper pairs from the actual trusted source.

    A disabled marker has no old positive evidence. Future changes to an enabled
    marker must explicitly retain its old reviewed pair before deployment.
    """
    package = policy.package_policy()
    tree = inputs.full_tree(root, 'HEAD')
    helper = tree.get(producer_api.METADATA_SOURCE)
    if not (type(helper) is dict and helper.get('mode') == '100644' and helper.get('type') == 'blob'):
        return None, None
    template = tree.get('tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml')
    generations = {row['name']: row['workflows'] for row in package.workflow_generations()
        if set(row['workflows']) == producer_api.METADATA_WORKFLOWS
        and row['workflows'].get(producer_api.METADATA_WORKFLOW) == template}
    if not generations:
        return None, None
    return generations, {name: {producer_api.METADATA_SOURCE: helper} for name in generations}


def source_blob(repository, oid):
    """Read only a bounded immutable blob using the existing config-free reader."""
    host.require(isinstance(oid,str) and re.fullmatch(r'[0-9a-f]{40}',oid) and set(oid) != {'0'},
                 'CI37 data requires an immutable blob identity')
    return sandbox._git(repository,'cat-file','blob',oid,limit=64_000)


def selection_profile(policy, registry, candidate_tree, base_tree, trusted_tree, *, root=ROOT, target='main', read_blob=None):
    """Derive the owner from complete immutable inputs, never receipt claims."""
    inputs._validate_registry(registry)
    host.require(type(base_tree) is dict and type(trusted_tree) is dict, 'protected selection needs complete base and trusted inputs')
    inputs._validate_tree(candidate_tree); inputs._validate_tree(base_tree); inputs._validate_tree(trusted_tree)
    paths = sorted(path for path in base_tree.keys() | candidate_tree.keys()
                   if base_tree.get(path) != candidate_tree.get(path))
    regular = bool(paths) and all(entry is None or entry.get('mode') == '100644' and entry.get('type') == 'blob'
        for path in paths for entry in (base_tree.get(path),candidate_tree.get(path)))
    selected = policy.select(candidate_tree, paths, regular, base_tree=base_tree, trusted_tree=trusted_tree,
                             candidate_root=root, trusted_root=root, target=target)
    if selected.get('reason') == 'protected-affected-dependencies':
        raise PreExecutionUnavailable('affected subset requires existing nonreusable execution')
    names = execution.select_common(registry, selected['suites'])
    profile = FULL_PROFILE
    binding = None
    if selected['full_host'] is not True:
        try:
            host.require(all(snapshot.get('.github/test-suites.json') == trusted_tree.get('.github/test-suites.json')
                for snapshot in (candidate_tree,base_tree)), 'CI37 command registry differs from original trusted policy')
            binding = ci_profile.validate_selection(selected,candidate_tree,trusted_tree,registry,target=target,
                regular=regular,unknown=False,policy=ci_profile.load_policy(root),root=root,read_blob=read_blob)
        except (ci_profile.CIProfileError, OSError, ValueError) as error:
            raise PreExecutionUnavailable('selected CI37 profile has no qualified source admission') from error
        profile = ci_profile.PROFILE
    host.require(bool(names), 'protected shared owner has no selected suites')
    return {'selection':selected,'profile':profile,'suites':names,'binding':binding}


def protected_source_context(adapter, binding, references, policy):
    """Exact B commitment to current defaultD; no historical D commit assertion."""
    target=binding['base_ref']
    try:
        source_admission.require(target in source_admission.TARGET_PROFILES, 'unknown protected source target')
        if set(controller_sources(policy)) != set(source_admission.CONTROLLERS):
            raise source_admission.SourceUnavailable('producer source graph is not reviewed')
        branch=adapter._object('branches/'+target)
        source_admission.require(branch.get('name')==target and branch.get('protected') is True
            and branch.get('commit',{}).get('sha')==binding['base_sha'], 'protected PR base changed')
        authority=branch if target=='main' else adapter._object('branches/main')
        source_admission.require(authority.get('name')=='main' and authority.get('protected') is True
            and authority.get('commit',{}).get('sha')==references['default'], 'default source protection changed')
        # These complete API inventories are independent of checkout Git config.
        from types import SimpleNamespace
        api=SimpleNamespace(get=adapter._object)
        base=source_admission.api_tree(api,binding['base_sha'],tree_reader=adapter.api.immutable_tree)
        default=source_admission.api_tree(api,references['default'],tree_reader=adapter.api.immutable_tree)
        admitted=source_admission.compatibility(base,default,target,
            read_actual=lambda name:source_admission.actual_bytes(ROOT,name),
            actual_imports=source_admission.actual_import_inventory(ROOT))
        source_admission.require(admitted['controller_digest']==_controller_identity(policy),
            'source admission differs from actual default controller identity')
        return {**admitted,'base':binding['base_sha'],'default':references['default']}
    except (source_admission.SourceUnavailable,host.Unavailable,OSError,ValueError,KeyError,TypeError) as error:
        raise PreExecutionUnavailable('protected base/default source is not enrolled') from error


def prepare(candidate, event, environment, adapter):
    """Independently select a supported protected owner and source generation."""
    number, identifier = _native(environment)
    binding, refs = adapter.current(number)
    host.require(binding['merge_sha'] == environment['GITHUB_SHA'] and binding['base_ref'] == environment.get('GITHUB_BASE_REF') in source_admission.TARGET_PROFILES
                 and binding['head_ref'] == environment.get('GITHUB_HEAD_REF'), 'current PR differs from native invocation')
    _event_binding(event, binding)
    host.require(execution.checkout_identity(ROOT)[0] == refs['default'] and refs['default_ref'] == 'main',
                 'trusted checkout differs from current protected default source')
    policy = _host_policy()
    source_context = protected_source_context(adapter,binding,refs,policy)
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    if policy.additional_suites(policy.candidate_registry(candidate), registry):
        raise PreExecutionUnavailable('new candidate commands need existing monotonic full execution')
    package_plan = policy.package_policy().candidate_plan(candidate,event,binding['merge_sha'])
    if package_plan['host_mode'] != 'full':
        raise PreExecutionUnavailable('the actual required route has no shared host owner')
    selected = policy.candidate_selection(candidate, event, binding['merge_sha'],package_plan['plan'])
    candidate_tree=inputs.full_tree(candidate,binding['merge_sha'])
    if not source_admission.shared_platform_supported(selected,binding['base_ref'],candidate_tree.get(source_admission.PROFILE)):
        raise PreExecutionUnavailable('candidate platform declaration needs existing actual execution')
    if selected['include_platform'] is True and execution.platform_suites(candidate, registry['suites']):
        raise PreExecutionUnavailable('selected profile needs existing nonreusable execution')
    prepared_selection = selection_profile(policy,registry,inputs.full_tree(candidate,binding['merge_sha']),
        inputs.full_tree(candidate,binding['base_sha']),inputs.full_tree(ROOT,refs['default']),root=ROOT,target=binding['base_ref'],
        read_blob=lambda oid:source_blob(candidate,oid))
    if prepared_selection['selection'] != selected:
        raise PreExecutionUnavailable('independent package/host owner needs existing actual execution')
    names = prepared_selection['suites']
    if binding['base_ref']!='main' and (prepared_selection['profile']!=FULL_PROFILE
            or selected['full_host'] is not True or set(names)!=set(registry['suites'])):
        raise PreExecutionUnavailable('child protected owner needs existing nonreusable execution')
    plan = {'owners': {'shared-host': {'kind': 'shared', 'suites': names,
              'include_platform': selected['include_platform'], 'platform': {}}}}
    blob = sandbox._git(ROOT, 'ls-tree', '-z', refs['default'], '--', TEMPLATE).split(b'\t')[0].split()[-1].decode()
    controller = source_context['controller_digest']
    producer = protocol.Policy('noah-l-frank/overte', 1319052603, 15368, '.github/workflows/project-tests.yml',
        blob, environment['GITHUB_REF'], ('pull_request',), controller, sandbox.contract(ROOT)['digest'],
        required_execution_schema=3)
    # The execution controller separately validates the COMPLETE package tuple.
    # The API adapter authenticates its fixed reusable source-chain projection;
    # only trusted complete generations can contribute that projection.
    generations = {}
    for generation in policy.package_policy().workflow_generations():
        workflows = generation['workflows']
        if set(producer_api.WORKFLOWS) <= workflows.keys() and workflows[producer.workflow_path]['sha'] == blob:
            projection = {path: workflows[path] for path in producer_api.WORKFLOWS}
            generations['generation-' + protocol.digest(projection).removeprefix('sha256:')] = projection
    caller = adapter._object('actions/workflows/repository-checks.yml')
    host.require(caller.get('path') == '.github/workflows/repository-checks.yml', 'caller workflow ID unavailable')
    metadata_workflows, metadata_sources = metadata_generations(policy)
    api_policy = producer_api.AdapterPolicy(producer, producer_api.positive(caller.get('id')),
        '.github/workflows/repository-checks.yml', generations, DESCRIPTOR_JOB,
        {'shared-host': SHARED_JOB}, PUBLISH_PREFIX, metadata_workflows, metadata_sources)
    producer_api._policy(api_policy, plan, number)
    result = {'number': number, 'run_id': identifier, 'binding': binding, 'refs': refs, 'selected': selected,
              'profile':prepared_selection['profile'],
              'profile_binding':prepared_selection['binding'],
              'registry': registry, 'plan': plan, 'policy': api_policy, 'source_context':source_context,
              'git_context': expected_git_context(adapter, binding)}
    _bookend(result, adapter, preexecution=True)
    return result


def current_run(context, adapter, role):
    """Authenticate the CURRENT attempt without requiring future jobs/artifacts."""
    value = adapter._object('actions/runs/' + str(context['run_id']))
    host.require(value.get('id') == context['run_id'] and value.get('run_attempt') == 1
                 and value.get('status') == 'in_progress' and value.get('conclusion') is None,
                 'producer is not the original active run')
    attempt = adapter._object(f"actions/runs/{context['run_id']}/attempts/1")
    keys = ('id', 'workflow_id', 'check_suite_id', 'path', 'event', 'head_sha', 'head_branch', 'run_attempt', 'status', 'conclusion')
    host.require(all(value.get(key) == attempt.get(key) for key in keys), 'active producer attempt changed')
    chain = adapter._chain(attempt, context['policy'], context['binding'])
    host.require(chain['producer_commit'] == context['binding']['merge_sha'], 'producer is another source context')
    suite = adapter._object('check-suites/' + str(producer_api.positive(attempt.get('check_suite_id'))))
    host.require(suite.get('id') == attempt['check_suite_id'] and suite.get('head_sha') == context['binding']['head_sha']
                 and suite.get('repository', {}).get('id') == 1319052603 and suite.get('app', {}).get('id') == 15368,
                 'native producer check suite identity differs')
    jobs = adapter._pages(f"actions/runs/{context['run_id']}/attempts/1/jobs", 'jobs')
    expected = {'descriptor': DESCRIPTOR_JOB, 'shared': SHARED_JOB}
    selected = {}
    final = None
    for name in expected.values():
        matches = [job for job in jobs if job.get('name') == name]
        host.require(len(matches) <= 1, 'native producer job is ambiguous')
        selected[name] = adapter._job(matches[0], attempt, 15368, final_name=name) if matches else None
    if role == 'publish':
        matches = [job for job in jobs if str(job.get('name', '')).startswith(PUBLISH_PREFIX)]
        host.require(len(matches) == 1, 'native final publisher is missing or ambiguous')
        suffix = matches[0]['name'][len(PUBLISH_PREFIX):]
        host.require(re.fullmatch(r'[0-9a-f]{64}', suffix), 'native final receipt commitment is malformed')
        final = protocol.AuthenticatedPublication(adapter._job(matches[0], attempt, 15368, final_name=matches[0]['name']), suffix)
    run = protocol.AuthenticatedRun('noah-l-frank/overte', 1319052603, 15368, context['run_id'], 1, 1,
        attempt.get('run_started_at'), '.github/workflows/project-tests.yml', chain['producer_blob'], chain['producer_commit'],
        chain['producer_ref'], 'pull_request', 'in_progress', None, selected[DESCRIPTOR_JOB],
        {'shared-host': selected[SHARED_JOB]} if selected[SHARED_JOB] else {}, final)
    protocol._run(run, context['policy'].producer)
    job = final.job if role == 'publish' else selected[expected[role]]
    host.require(job is not None and job.status == 'in_progress' and job.conclusion is None and job.started_at is not None,
                 'current native producer role is not executing')
    return run


def _bookend(context, adapter, *, preexecution=False):
    binding, refs = adapter.current(context['number'])
    host.require(binding == context['binding'] and refs == context['refs'], 'PR/default source changed during producer operation')
    if 'source_context' in context:
        try:
            host.require(protected_source_context(adapter,binding,refs,_host_policy())==context['source_context'],
                         'protected base/default controller source changed')
        except PreExecutionUnavailable as error:
            if preexecution:
                raise
            # This bookend also runs AFTER run_suites. Never turn a finished
            # or failed execution into a new legacy execution/fallback attempt.
            raise host.Unavailable('protected source changed after admission') from error


def _descriptor(context, adapter, run):
    artifacts = adapter._artifacts(run)
    raw, facts = adapter._artifact(run, 'descriptor', artifacts, datetime.now(timezone.utc), context['binding']['head_sha'])
    host.require(raw is not None, 'early descriptor is missing')
    value = protocol.read_artifact(raw, 'descriptor', facts, run, now=datetime.now(timezone.utc))
    protocol.validate_descriptor(value, context['binding'], context['plan'], context['policy'].producer, run)
    host.require(run.publisher.conclusion == 'success' and run.publisher.completed_at is not None
                 and protocol._time(run.publisher.started_at) <= protocol._time(facts.created_at) <= protocol._time(run.publisher.completed_at),
                 'early descriptor was not published within its successful native job')
    return value, facts


def protected_receipt(batch, context, cancelled, installed):
    """Root-owned observation only; no failure after execution can become fallback."""
    started = utc_seconds()
    tree = inputs.full_tree(batch.candidate,context['binding']['merge_sha'])
    trusted_tree = inputs.full_tree(ROOT,context['refs']['default'])
    def admit(environment):
        now = datetime.now(timezone.utc)
        try:
            if context.get('profile',FULL_PROFILE) == ci_profile.PROFILE:
                runtime_ci.validate_environment(environment,utc_seconds(now),utc_seconds(now+timedelta(hours=24)),
                    now,context['selected'],tree,trusted_tree,context['registry'],root=ROOT,
                    read_blob=lambda oid:source_blob(batch.candidate,oid))
            else:
                attested.validate_environment(environment, utc_seconds(now), utc_seconds(now + timedelta(hours=24)),
                                             now, root=ROOT, isolated=True)
        except (attested.AttestedReuseUnavailable, runtime_ci.CIEnvironmentError) as error:
            raise PreExecutionUnavailable('original selected environment has no qualified admission') from error
    options = {'preexecution_unavailable':PreExecutionUnavailable} if context.get('profile') == ci_profile.PROFILE else {}
    statuses, before, after = shared.check_batch(batch, context['registry'], cancelled, installed,
        names=context['plan']['owners']['shared-host']['suites'], admit=admit, **options)
    host.require(not cancelled and before == after, 'protected execution did not finish successfully')
    original = git_context(batch.snapshot)
    host.require(original == context['git_context'], 'actual materialized Git context differs from immutable API source')
    names = [entry['name'] for entry in statuses]
    receipt = {'schema': 3, 'producer': execution.PRODUCER, 'candidate_commit': context['binding']['merge_sha'],
        'candidate_tree': context['binding']['merge_tree'], 'git_context': original, 'environment': before, 'reusable': True,
        'requested_suites': names, 'include_platform': context['plan']['owners']['shared-host']['include_platform'],
        'results': {name: {'status': 'passed', 'fingerprint': inputs.suite_fingerprint(context['registry'], name, tree, before)} for name in names},
        'platform_results': {}, 'conclusion': 'success', 'started_at': started, 'completed_at': utc_seconds()}
    receipt['receipt_digest'] = execution.digest(receipt)
    execution.validate_receipt(receipt, context['registry'], tree, expected_git_context=context['git_context'])
    return receipt


def publication(context, descriptor, receipt, run, now, descriptor_expires_at):
    """Prepare canonical bytes; consumers still authenticate the COMPLETED job."""
    protocol.validate_descriptor(descriptor, context['binding'], context['plan'], context['policy'].producer, run)
    owner = run.owners.get('shared-host')
    final = run.final_publisher
    host.require(owner is not None and owner.status == 'completed' and owner.conclusion == 'success'
                 and owner.completed_at is not None and final is not None and final.job.status == 'in_progress'
                 and protocol._time(owner.completed_at) <= protocol._time(final.job.started_at)
                 and protocol._time(run.publisher.completed_at) <= protocol._time(owner.started_at),
                 'shared execution lacks successful ordered native jobs')
    host.require(receipt.get('schema') == 3, 'isolated publisher cannot publish a legacy receipt')
    tree = inputs.full_tree(context['candidate'], context['binding']['merge_sha'])
    execution.validate_receipt(receipt, context['registry'], tree, expected_git_context=context['git_context'])
    host.require(receipt['candidate_commit'] == context['binding']['merge_sha'] and receipt['candidate_tree'] == context['binding']['merge_tree']
                 and receipt['requested_suites'] == context['plan']['owners']['shared-host']['suites']
                 and receipt['include_platform'] == context['plan']['owners']['shared-host']['include_platform']
                 and receipt['platform_results'] == {} and receipt['reusable'] is True
                 and protocol._time(owner.started_at) <= protocol._time(receipt['started_at'])
                 <= protocol._time(receipt['completed_at']) <= protocol._time(owner.completed_at)
                 and hashlib.sha256(protocol.canonical(receipt)).hexdigest() == final.receipt_sha256,
                 'protected receipt differs from selected source/native whole-receipt commitment')
    qualified = utc_seconds(now)
    expires = utc_seconds(min(now + timedelta(seconds=context['policy'].producer.max_age_seconds),
                              protocol._time(descriptor_expires_at)))
    if context.get('profile',FULL_PROFILE) == ci_profile.PROFILE:
        runtime_ci.validate_environment(receipt['environment'],qualified,expires,now,context['selected'],
            tree,inputs.full_tree(ROOT,context['refs']['default']),context['registry'],root=ROOT,
            read_blob=lambda oid:source_blob(context['candidate'],oid))
    else:
        attested.validate_environment(receipt['environment'], qualified, expires, now, root=ROOT, isolated=True)
    value = {'schema': 1, 'producer': 'overte-producer-aggregate-v1', 'descriptor_digest': descriptor['descriptor_digest'],
        'results': {'shared-host': {'status': 'passed', 'job_id': owner.job_id, 'attempt': 1, 'receipt': receipt}},
        'qualified_at': qualified, 'expires_at': expires}
    value['aggregate_digest'] = protocol.digest(value)
    return value


def _receipt_artifact(context, run, adapter):
    name = f"ci-protected-receipt-{run.run_id}-1"
    items = [item for item in adapter._artifacts(run) if item.get('name') == name]
    host.require(len(items) == 1, 'protected shared receipt artifact is missing or ambiguous')
    item = items[0]
    detail = adapter._object('actions/artifacts/' + str(producer_api.positive(item.get('id'))))
    fields = ('id', 'name', 'digest', 'size_in_bytes', 'expired', 'created_at', 'expires_at', 'workflow_run')
    host.require(all(item.get(key) == detail.get(key) for key in fields), 'protected receipt artifact changed')
    owner = detail.get('workflow_run', {})
    job = run.owners['shared-host']
    host.require(owner.get('id') == run.run_id and owner.get('repository_id') == owner.get('head_repository_id') == 1319052603
                 and owner.get('head_sha') == context['binding']['head_sha'] and detail.get('expired') is False
                 and type(detail.get('size_in_bytes')) is int and 0 < detail['size_in_bytes'] <= protocol._MAX_ARCHIVE
                 and protocol._time(job.started_at) <= protocol._time(detail.get('created_at')) <= protocol._time(job.completed_at)
                 and protocol._time(detail.get('created_at')) <= datetime.now(timezone.utc) < protocol._time(detail.get('expires_at')),
                 'protected receipt artifact has wrong source or publishing window')
    raw = adapter.api.bytes(producer_api.PREFIX + f"/actions/artifacts/{detail['id']}/zip")
    host.require(isinstance(raw, bytes) and len(raw) == detail['size_in_bytes']
                 and 'sha256:' + hashlib.sha256(raw).hexdigest() == detail.get('digest'), 'protected receipt archive differs from API digest')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        host.require(len(entries) == 1 and entries[0].filename == 'receipt.json'
                     and 0 < entries[0].file_size <= protocol._MAX_JSON
                     and entries[0].compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                     and not stat.S_ISLNK(entries[0].external_attr >> 16), 'protected receipt archive has unsupported members')
        content = archive.read(entries[0])
    value = json.loads(content, object_pairs_hook=inputs._unique_object)
    host.require(content == protocol.canonical(value), 'protected receipt is not canonical JSON')
    # Recheck identity after downloading; this artifact never authenticates its
    # own contents. The independent native final-job hash is checked separately.
    host.require(adapter._object('actions/artifacts/' + str(detail['id'])) == detail
                 and [row for row in adapter._artifacts(run) if row.get('name') == name] == items,
                 'protected receipt artifact inventory changed during read')
    return value


def _output(values, *, protected=False):
    descriptor = os.open(os.environ['GITHUB_OUTPUT'], os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        allowed = {0, int(os.environ.get('SUDO_UID', os.getuid()))} if protected else {os.getuid()}
        host.require(stat.S_ISREG(info.st_mode) and info.st_uid in allowed and not info.st_mode & 0o022,
                     'native command file is not protected from candidate writes')
        body = ''.join(key + '=' + value + '\n' for key, value in values.items())
        host.require(all(re.fullmatch(r'[a-z_]+', key) and re.fullmatch(r'(?:true|false|[0-9a-f]{64})', value)
                         for key, value in values.items()), 'unsupported native producer output')
        with os.fdopen(descriptor, 'w', encoding='ascii', closefd=False) as output:
            output.write(body)
    finally:
        os.close(descriptor)


def _directory(name, *, root_only=False):
    base = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    host.require(base.is_dir() and not base.is_symlink(), 'native producer temporary directory is unavailable')
    path = base / name
    path.mkdir(mode=0o700, exist_ok=False)
    host.require(not path.is_symlink() and path.stat().st_uid == (0 if root_only else os.getuid()),
                 'native producer output directory has wrong ownership')
    return path


def shared_execution(candidate, event, environment, adapter):
    """Actual selected supervisor; called only after fixed production admission."""
    protected_admission()
    host.require(os.geteuid() == 0 and re.fullmatch(r'[1-9][0-9]*', environment.get('SUDO_UID', '')),
                 'protected shared execution requires the trusted root supervisor')
    number, _ = _native(environment)
    current, _ = adapter.current(number)
    host.require(current['merge_sha'] == environment['GITHUB_SHA'], 'native source moved before protected materialization')
    uid, gid = host.verify_account(int(environment['SUDO_UID']))
    delegated = host.prepare_delegation()
    cancelled, handlers = [], {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, lambda number, _frame: cancelled.append(number))
        with tempfile.TemporaryDirectory(prefix='overte-protected-shared-') as temporary:
            base = Path(temporary)
            base.chmod(0o755)
            snapshot_path, policy_path = base / 'candidate', base / 'policy'
            snapshot_path.mkdir(mode=0o755)
            policy_path.mkdir(mode=0o755)
            # This config-free immutable reader is the ONLY root Git operation
            # on the raw Actions candidate. Ordinary selection helpers then see
            # our root-owned pristine index/config, never checkout Git config.
            snapshot = shared.materialize_source(current['merge_sha'], snapshot_path, repository=candidate)
            context = prepare(snapshot_path, event, environment, adapter)
            try:
                prepared = shared.prepared_tools(environment,profile=context['profile'])
                installed = shared.prepared_identity(shared.identity_roots(prepared),
                    external_inputs=shared.prepared_external_inputs(prepared))
            except (host.Unavailable,OSError) as error:
                if context['profile'] != ci_profile.PROFILE:
                    raise
                raise PreExecutionUnavailable('selected CI37 prepared tools are unavailable') from error
            run = current_run(context, adapter, 'shared')
            _descriptor(context, adapter, run)
            projection = shared.project_policy(policy_path, shared.sources())
            binding = {'source': context['binding']['merge_sha'], 'run_id': context['run_id'], 'run_attempt': 1,
                'profile': shared.PROFILE, 'snapshot': snapshot['digest'], 'git_context': snapshot['git_context'],
                'runtime_profile':context['profile'],'selection':context['selected'],
                'profile_binding':context['profile_binding'],
                'registry': execution.digest(context['registry']), 'prepared': installed, 'projection': execution.digest(projection),
                'outside_namespaces': {name: os.stat('/proc/self/ns/' + name).st_ino for name in ('user', 'mnt', 'pid', 'net', 'ipc', 'uts')}}
            sandbox._write_source(policy_path, 'context.json', sandbox._canonical({'shared_host': binding}))
            projection = sandbox._files(policy_path)
            image = {name: environment[name] for name in ('ImageOS', 'ImageVersion', 'RUNNER_ENVIRONMENT')}
            batch = shared.Batch(base, snapshot_path, policy_path, snapshot, projection, binding, prepared, delegated, uid, gid, image)
            receipt = protected_receipt(batch, context, cancelled, installed)
            _bookend(context, adapter)
            current_run(context, adapter, 'shared')
            return receipt
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('descriptor', 'shared', 'publish'))
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args(argv)
    # A controlled first native attempt may establish the first qualified E and
    # completed publisher. Source capability alone supplies neither proof.
    try:
        protected_admission()
    except PreExecutionUnavailable:
        if args.role == 'descriptor':
            print('Protected shared producer disabled; required nonreusable execution remains selected.')
            _output({'protected_full': 'false'})
            return 0
        raise
    event_path = Path(os.environ['GITHUB_EVENT_PATH'])
    host.require(event_path.is_file() and not event_path.is_symlink() and event_path.stat().st_size <= 1_000_000,
                 'native event inventory is unavailable')
    event = json.loads(event_path.read_bytes(), object_pairs_hook=inputs._unique_object)
    if args.role == 'descriptor' and (os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_BASE_REF') not in source_admission.TARGET_PROFILES
            or event.get('pull_request', {}).get('head', {}).get('repo', {}).get('id') != 1319052603):
        _output({'protected_full': 'false'})
        return 0
    # No caller can select a candidate outside the exact clean checkout. No
    # candidate path is imported as protected implementation or policy.
    candidate = args.candidate.resolve(strict=True)
    host.require(candidate == Path(os.environ['GITHUB_WORKSPACE']).resolve() / 'candidate', 'unexpected candidate location')
    adapter = producer_api.Adapter()
    if args.role == 'shared':
        try:
            receipt = shared_execution(candidate, event, os.environ, adapter)
        except PreExecutionUnavailable:
            # Admission is the sole recoverable exception. Once run_suites has
            # started, failure/cancellation/timeout remains a required failure.
            _output({'protected_executed': 'false'}, protected=True)
            return 0
        destination = _directory('ci-protected-receipt', root_only=True)
        execution._write_receipt(destination / 'receipt.json', receipt)
        # Make only the finished canonical receipt upload-readable after all
        # candidate scopes are empty. It was never candidate-writable.
        destination.chmod(0o755)
        (destination / 'receipt.json').chmod(0o444)
        _output({'protected_executed': 'true', 'receipt_sha256': hashlib.sha256(protocol.canonical(receipt)).hexdigest()}, protected=True)
        return 0
    try:
        context = prepare(candidate, event, os.environ, adapter)
    except PreExecutionUnavailable:
        if args.role == 'descriptor':
            _output({'protected_full': 'false'})
            return 0
        raise
    context['candidate'] = candidate
    run = current_run(context, adapter, args.role)
    if args.role == 'descriptor':
        value = protocol.descriptor(context['binding'], context['plan'], context['policy'].producer, run)
        _bookend(context, adapter)
        execution._write_receipt(_directory('ci-producer-descriptor') / 'descriptor.json', value)
        _output({'protected_full': 'true'})
        return 0
    descriptor, facts = _descriptor(context, adapter, run)
    receipt = _receipt_artifact(context, run, adapter)
    value = publication(context, descriptor, receipt, run, datetime.now(timezone.utc), facts.expires_at)
    _bookend(context, adapter)
    host.require(current_run(context, adapter, 'publish') == run, 'native publication job changed before output')
    execution._write_receipt(_directory('ci-producer-aggregate') / 'aggregate.json', value)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (host.Unavailable, producer_api.ApiError, protocol.ProtocolError, execution.ExecutionError,
            inputs.InputError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        # Candidate output and server/private metadata are never log commands.
        detail = sandbox.safe_diagnostic(str(error).encode()[:8192]) if isinstance(error, host.Unavailable) else 'required protected operation failed'
        print('Protected shared producer failed closed: ' + detail, file=sys.stderr)
        raise SystemExit(1)
