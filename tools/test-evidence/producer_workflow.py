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
PLATFORM_TEMPLATE = 'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml'
PLATFORM_PARENT_TEMPLATE = 'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml'
PLATFORM_GENERATION = 'protected-producer-original-default-v1'
PLATFORM_JOB = 'project / Android platform tests'
_PLATFORM_TARGETS = frozenset({'android-main', 'android-phone', 'android-vr', 'android-vr-pico'})
_PLATFORM_SOURCES = (
    '.github/android-checks.json', '.github/android-owner-transfer.json',
    'tools/repository-checks/android.py', 'tools/repository-checks/android_gate.py',
    'tools/repository-checks/android_handoff.py', PLATFORM_TEMPLATE, PLATFORM_PARENT_TEMPLATE,
)
PRODUCTION_READY = True
DESCRIPTOR_JOB = 'project / Publish producer descriptor'
SHARED_JOB = 'project / Shared tests'
PUBLISH_PREFIX = 'project / Publish final producer '
FULL_PROFILE = 'ubuntu24-host-qt5-qt6-v1'
CURRENT_OWNER_GENERATION = 'protected-producer-seven-target-ci-v1'
DOCUMENTATION_SUITES = frozenset({'documentation-contracts', 'documentation', 'policy-consistency'})
WORKFLOW_CONTRACT_SUITES = frozenset({'workflow-contracts'})
_CURRENT_OWNER_DEMANDS = (DOCUMENTATION_SUITES, WORKFLOW_CONTRACT_SUITES,
                         DOCUMENTATION_SUITES | WORKFLOW_CONTRACT_SUITES)
_CURRENT_OWNER_TARGETS = frozenset({'main', 'apple-main', 'apple-ios', 'android-main',
                                   'android-phone', 'android-vr', 'android-vr-pico'})


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


def execution_schema(policy, tree, target):
    """A new complete reviewed generation alone enrolls retained source proof."""
    generation=policy.package_policy().validate_tree_wiring(tree)
    if generation==ci_profile.RETAINED_SOURCE_GENERATION:
        return 4
    if target!='main':
        raise PreExecutionUnavailable('child protected proof requires retained original default source generation')
    return 3


def retained_receipt_source(receipt, binding, adapter, registry, selected, run_id, *, root=ROOT):
    """Authenticate original D selected by a native-hash-bound source envelope.

    This must run before SharedContext is constructed, then again at the final
    native/context bookend. It never selects D from consumer currentdefault.
    """
    if receipt.get('schema')!=4:
        host.require(binding['base_ref']=='main' and receipt.get('schema')==3,
                     'child original protected default source is missing')
        return None
    value=ci_profile.retained_source_shape(receipt.get('protected_source'))
    identity, _=adapter._commit(value['default_commit'])
    host.require(identity==value['default_tree'],'original immutable D tree differs')
    from types import SimpleNamespace
    api=SimpleNamespace(get=adapter._object)
    base=source_admission.api_tree(api,binding['base_sha'],tree_reader=adapter.api.immutable_tree)
    default=source_admission.api_tree(api,value['default_commit'],tree_reader=adapter.api.immutable_tree)
    expected=ci_profile.validate_retained_source(value,base,default,native_binding=binding,
        run_id=run_id,registry=registry,selection=selected,environment=receipt['environment'],root=root,
        read_source_blob=getattr(adapter.api,'immutable_source_blob',None))
    host.require(expected['binding']['git_context']==expected_git_context(adapter,binding),
                 'retained original projection Git context differs from independent native source')
    return expected


def verify_original_source(adapter, invocation, plan, api_policy, context, receipt, binding, *, integrated, root=ROOT, clock):
    """Actual native verification is the sole mint for original runtime authority.

    There is no serialized token, optional proof callback or supplied verification
    result. Legacy schema3 callers retain their existing verification path.
    """
    verified,token=ci_profile.authenticate_original_source(adapter,invocation,plan,api_policy,context,
        receipt,binding,integrated=integrated,root=root,clock=clock)
    host.require(clock()<protocol._time(verified['expires_at']), 'original proof expired during source reconstruction')
    return verified,token


def reuse_source_profile(snapshot, adapter, api_policy, policy, registry, candidate, base,
                         *, root=ROOT, target, read_blob, now):
    """Two-phase source lookup, never evidence/runtime admission or a PASS.

    The native newest run is located without choosing its plan from current D.
    Claimed descriptor data permits only reading source4, after which the owner
    is independently rederived from complete immutable ORIGINAL B/D inputs.
    Actual Adapter.verify and original runtime admission remain mandatory later.
    """
    host.require(snapshot.inventory_complete is True and bool(snapshot.observations),
        'original source lookup inventory is incomplete')
    seen=set();ordered=[]
    for item in snapshot.observations:
        protocol._run(item.run,api_policy.producer,require_latest=False)
        key=(item.run.run_id,item.run.attempt)
        host.require(key not in seen and item.run.attempt==item.run.latest_attempt==1,
            'original source lookup has mixed or duplicate attempts')
        seen.add(key);ordered.append((protocol._time(item.run.attempt_started_at),item))
    newest=max(stamp for stamp,_ in ordered)
    matches=[item for stamp,item in ordered if stamp==newest]
    host.require(len(matches)==1,'original source lookup has tied newest runs')
    item=matches[0]
    descriptor=protocol.read_artifact(item.descriptor_archive,'descriptor',item.descriptor_artifact,item.run,now=now)
    claim=descriptor.get('plan')
    authority=protocol.select_authority(snapshot.observations,snapshot.binding,claim,api_policy.producer,
        inventory_complete=snapshot.inventory_complete,now=now)
    host.require(authority['state']=='proof-required' and authority['run_id']==item.run.run_id,
        'newest original source is failed, pending or unclassified')
    raw,facts=adapter._artifact(item.run,'aggregate',snapshot.artifact_inventories[item.run.run_id],now,snapshot.binding['head_sha'])
    aggregate=protocol.read_artifact(raw,'aggregate',facts,item.run,now=now)
    receipt=aggregate.get('results',{}).get('shared-host',{}).get('receipt')
    host.require(type(receipt) is dict and receipt.get('schema')==4,
        'complete original source4 data is unavailable')
    source=ci_profile.retained_source_shape(receipt.get('protected_source'))
    # This bounded full reconstruction still supplies no native whole-hash
    # authority; it only closes original-data dependency/selection derivation.
    retained_receipt_source(receipt,snapshot.binding,adapter,registry,source['binding']['selection'],item.run.run_id,root=root)
    from types import SimpleNamespace
    default=source_admission.api_tree(SimpleNamespace(get=adapter._object),source['default_commit'],
        tree_reader=adapter.api.immutable_tree)
    profile=selection_profile_for_reuse(policy,registry,candidate,base,default,root=root,target=target,read_blob=read_blob)
    host.require(profile['selection']==source['binding']['selection'],
        'original immutable source does not derive the claimed selected owners')
    return profile,default


def _event_binding(event, binding, *, api=None):
    repository = {'full_name': 'noah-l-frank/overte', 'id': 1319052603}
    host.require(isinstance(event, dict) and all(event.get('repository', {}).get(key) == value
                 for key, value in repository.items()), 'event repository differs from native producer')
    pr = event.get('pull_request')
    host.require(isinstance(pr, dict) and event.get('number') == pr.get('number') == binding['pull_request'],
                 'event PR number differs from current candidate')
    for side in ('base', 'head'):
        branch = pr.get(side, {})
        host.require(isinstance(branch, dict) and branch.get('ref') == binding[side + '_ref']
                     and all(branch.get('repo', {}).get(key) == value for key, value in repository.items()),
                     'event branch differs from independently read current candidate')
        if side == 'head':
            host.require(branch.get('sha') == binding['head_sha'],
                         'event head differs from independently read current candidate')
        elif branch.get('sha') != binding['base_sha']:
            host.require(api is not None, 'event base snapshot requires independent ancestry proof')
            try:
                source_admission.validate_base_snapshot(api, branch.get('sha'), binding['base_sha'])
            except source_admission.SourceUnavailable as error:
                raise host.Unavailable(str(error)) from error


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
    # Policy projection also carries fixed import-only members for its actual-D
    # manifest. Those bytes belong to CI37 generation, not the producer's fixed
    # controller identity. Unknown new source dependencies must remain visible.
    import_only = set(source_admission.IMPORT_MEMBERS) - set(source_admission.CONTROLLERS)
    projected = set(shared.sources()) - import_only
    return sorted({source_admission.SELF, inputs.AFFECTED_POLICY, *projected, *policy.package_policy()._policy_inputs(), *attested._CONSUMER_FILES, TEMPLATE, *_PLATFORM_SOURCES,
        'tools/repository-checks/metadata_context.py',
        'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
        '.github/workflows/documentation-checks.yml', '.github/workflows/workflow-security.yml',
        source_admission.DOCUMENTATION_WORKFLOW,
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
    old_template = {'mode': '100644', 'type': 'blob', 'sha': 'd04a6dc70213d8b549bac30c11cc15eaf0182dea'}
    old_helper = {'mode': '100644', 'type': 'blob', 'sha': '9c531c34ba559d17255768d8cae3129496fac55d'}
    generations = {row['name']: row['workflows'] for row in package.workflow_generations()
        if set(row['workflows']) == producer_api.METADATA_WORKFLOWS
        and row['workflows'].get(producer_api.METADATA_WORKFLOW) in (template, old_template)}
    if not generations:
        return None, None
    return generations, {name: {producer_api.METADATA_SOURCE: old_helper
        if workflows[producer_api.METADATA_WORKFLOW] == old_template else helper}
        for name, workflows in generations.items()}


def source_blob(repository, oid):
    """Read only a bounded immutable blob using the existing config-free reader."""
    host.require(isinstance(oid,str) and re.fullmatch(r'[0-9a-f]{40}',oid) and set(oid) != {'0'},
                 'CI37 data requires an immutable blob identity')
    return sandbox._git(repository,'cat-file','blob',oid,limit=64_000)


def _affected_full_selection(policy, registry, selected, candidate_tree, base_tree, trusted_tree, paths,
                             regular, *, root, target, _reuse_only=False):
    """Admit a finite source-proved subset without changing the full runtime.

    The selector's label or supplied names are insufficient. Reconstruct the
    protected dependency plan and its legacy preparation boundary independently;
    neither the candidate graph nor a future receipt can select its own work.
    """
    try:
        host.require(target in source_admission.TARGET_PROFILES and regular is True,
                     'affected producer requires ordinary finite-target inputs')
        raw_registry = sandbox._source(root, '.github/test-suites.json')
        actual_registry = inputs._validate_registry(json.loads(raw_registry, object_pairs_hook=inputs._unique_object))
        registry_entry = {'mode': '100644', 'type': 'blob', 'sha': hashlib.sha1(
            b'blob ' + str(len(raw_registry)).encode('ascii') + b'\0' + raw_registry).hexdigest()}
        host.require(actual_registry == registry and all(
            tree.get('.github/test-suites.json') == registry_entry for tree in (base_tree, candidate_tree, trusted_tree)),
            'affected command definitions differ from protected registry bytes')
        raw = inputs.load_dependencies(root / inputs.AFFECTED_POLICY, registry)
        dependencies = json.loads(raw)
        if target != 'main':
            host.require(dependencies['schema'] == 2 and execution_schema(policy,candidate_tree,target) == 4,
                'child affected proof requires the retained-source seven-target generation')
            if _reuse_only:
                ci_profile.reuse_controller_precheck(base_tree,trusted_tree,target,root=root)
            else:
                source_admission.compatibility(base_tree,trusted_tree,target,
                    read_actual=lambda name:source_admission.actual_bytes(root,name),
                    actual_imports=source_admission.actual_import_inventory(root))
        native = dependencies['suites'].get('device-control-plane-full', {})
        host.require(all(policy.ci_owned(path) for path in native.get('native_independent_paths', ())),
                     'affected native lookup has an unreviewed independence exception')
        plan = inputs.plan_affected(registry, raw, base_tree, candidate_tree, trusted_tree,target=target)
        legacy = policy._select_legacy(candidate_tree, paths, regular, base_tree=base_tree,
            trusted_tree=trusted_tree, candidate_root=root, trusted_root=root, target=target)
        platform = bool(dependencies['schema'] == 2
            and dependencies['targets'][target]['profile'] != inputs._AFFECTED_SHARED_PROFILE
            and legacy['include_platform'] is not False)
        expected = {'suites': plan['required'], 'reason': 'protected-affected-dependencies',
                    'full_host': True, 'include_platform': platform, 'affected': plan}
        host.require(selected == expected and selected['full_host'] is True
                     and plan['paths'] == paths,
                     'affected owner differs from independently derived protected dependencies')
        names = execution.select_common(registry, plan['required'])
        host.require(names == plan['required'] and bool(names), 'affected owner is empty or noncanonical')
        host.require(legacy['full_host'] is True and legacy['reason'] not in {
            'unknown-or-nonregular-inventory', 'unowned-inputs', 'reviewed-protected-producer-transition'}
            and set(names) < set(execution.select_common(registry, legacy['suites'])),
            'affected owner cannot widen preparation or replace a full installation gate')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise PreExecutionUnavailable('affected subset has no independent protected full admission') from error


def _selection_profile(policy, registry, candidate_tree, base_tree, trusted_tree, *, root=ROOT, target='main', read_blob=None,
                       _reuse_only=False):
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
        _affected_full_selection(policy, registry, selected, candidate_tree, base_tree, trusted_tree,
                                 paths, regular, root=root, target=target,_reuse_only=_reuse_only)
    names = execution.select_common(registry, selected['suites'])
    profile = FULL_PROFILE
    binding = None
    if selected['full_host'] is not True:
        try:
            host.require(all(snapshot.get('.github/test-suites.json') == trusted_tree.get('.github/test-suites.json')
                for snapshot in (candidate_tree,base_tree)), 'CI37 command registry differs from original trusted policy')
            runtime_policy = ci_profile.load_policy(root)
            if runtime_policy.get('generation_kind') == ci_profile.SEVEN_CONTROLLER_KIND:
                host.require(execution_schema(policy,candidate_tree,target) == 4,
                    'seven-target CI execution requires retained original default source')
                legacy = policy._select_legacy(candidate_tree,paths,regular,base_tree=base_tree,
                    trusted_tree=trusted_tree,candidate_root=root,trusted_root=root,target=target,
                    package_paths=selected.get('package_owned_paths',()))
                host.require(legacy['suites'] == list(ci_profile.SUITES) and legacy['full_host'] is False
                    and legacy['include_platform'] is False and legacy['reason'] in {
                        'reviewed-ci-only-inputs','reviewed-ci-and-package-owners'},
                    'CI subset has no independently established Qt-free upper bound')
                if selected['reason'] != 'protected-ci-dependencies':
                    host.require(selected == legacy,'exact CI37 selection differs from its independent legacy plan')
            validator=ci_profile.preliminary_reuse_selection if _reuse_only else ci_profile.validate_selection
            binding = validator(selected,candidate_tree,trusted_tree,registry,target=target,
                regular=regular,unknown=False,policy=runtime_policy,root=root,read_blob=read_blob,base_tree=base_tree)
        except (ci_profile.CIProfileError, OSError, ValueError) as error:
            raise PreExecutionUnavailable('selected CI37 profile has no qualified source admission') from error
        profile = ci_profile.PROFILE
    host.require(bool(names), 'protected shared owner has no selected suites')
    return {'selection':selected,'profile':profile,'suites':names,'binding':binding}


def selection_profile(policy, registry, candidate_tree, base_tree, trusted_tree, *, root=ROOT, target='main', read_blob=None):
    return _selection_profile(policy,registry,candidate_tree,base_tree,trusted_tree,
        root=root,target=target,read_blob=read_blob)


def selection_profile_for_reuse(policy, registry, candidate_tree, base_tree, trusted_tree, **kwargs):
    """Non-authoritative plan for source4 lookup; never a capture/execute input."""
    target=kwargs.get('target','main')
    if execution_schema(policy,candidate_tree,target)!=4:
        return selection_profile(policy,registry,candidate_tree,base_tree,trusted_tree,**kwargs)
    return _selection_profile(policy,registry,candidate_tree,base_tree,trusted_tree,**kwargs,_reuse_only=True)


def _ci_runtime_context(context, candidate):
    """Read original B only for the versioned seven-target namespace."""
    binding = context.get('profile_binding')
    if type(binding) is not dict or binding.get('generation_kind') != ci_profile.SEVEN_CONTROLLER_KIND:
        return {}
    return {'target':context['binding']['base_ref'],
            'base_tree':inputs.full_tree(candidate,context['binding']['base_sha'])}


def project_template(policy, candidate_tree):
    """The complete trusted catalog, never a flag, selects a native recipe."""
    if PLATFORM_TEMPLATE not in candidate_tree:
        return TEMPLATE
    generation = policy.package_policy().validate_tree_wiring(candidate_tree)
    return PLATFORM_TEMPLATE if generation == PLATFORM_GENERATION else TEMPLATE


def platform_partition(policy, profile, registry, candidate_tree, base_tree, trusted_tree,
                       *, target, root=ROOT, read_blob=None):
    """Separate existing Android declarations from an unchanged full common owner.

    This capability is unavailable until the exact future recipe is enrolled in
    the protected catalog. The original selection remains intact. A common
    receipt never claims these external platform commands or their runtime.
    """
    if target not in _PLATFORM_TARGETS or PLATFORM_TEMPLATE not in trusted_tree:
        return None
    if policy.package_policy().validate_tree_wiring(candidate_tree) != PLATFORM_GENERATION:
        return None
    # selection_profile independently admits this versioned Qt-free owner.
    # It never selected Android declarations, so there is nothing to split.
    # A full-host profile cannot waive platform work with a false boolean.
    selected = profile.get('selection', {})
    binding = profile.get('binding')
    if (profile.get('profile') == ci_profile.PROFILE and type(binding) is dict
            and binding.get('generation_kind') == ci_profile.SEVEN_CONTROLLER_KIND
            and binding.get('profile') == ci_profile.PROFILE
            and binding.get('suites') == list(ci_profile.SUITES)
            and selected.get('full_host') is False and selected.get('include_platform') is False
            and profile.get('suites') == selected.get('suites')
            and bool(profile['suites']) and profile['suites'] == [
                name for name in ci_profile.SUITES if name in profile['suites']]
            and all(tree.get(source_admission.PROFILE) == source_admission.ordinary(
                source_admission.TARGET_PROFILES[target]) for tree in (base_tree,candidate_tree))):
        return None
    try:
        for tree in (base_tree, candidate_tree, trusted_tree):
            inputs._validate_tree(tree)
        selected = profile['selection']
        full_names = execution.select_common(registry)
        names = execution.select_common(registry,profile['suites'])
        affected = (selected.get('reason') == 'protected-affected-dependencies'
            and selected.get('affected',{}).get('dependency_schema') == 2
            and selected['affected'].get('target') == target and bool(names) and set(names) < set(full_names))
        host.require(len(full_names) == 60 and (names == full_names or affected) and profile['profile'] == FULL_PROFILE
            and profile['binding'] is None and profile['suites'] == names
            and selected['suites'] == names and selected['full_host'] is True
            and selected['include_platform'] is True,
            'Android partition needs the original complete full-host selection')
        raw_registry = sandbox._source(root, '.github/test-suites.json')
        registry_entry = source_admission.ordinary(source_admission.blob_id(raw_registry))
        host.require(inputs._validate_registry(json.loads(raw_registry, object_pairs_hook=inputs._unique_object)) == registry
            and all(tree.get('.github/test-suites.json') == registry_entry
                for tree in (base_tree, candidate_tree, trusted_tree)),
            'Android partition command definitions differ from protected source')
        _, template_entry = source_admission.actual_bytes(root, PLATFORM_TEMPLATE)
        host.require(template_entry['mode'] == '100644'
            and trusted_tree.get(PLATFORM_TEMPLATE) == template_entry
            and candidate_tree.get('.github/workflows/project-tests.yml') == template_entry,
            'Android partition native recipe differs from actual protected source')
        expected = source_admission.ordinary(source_admission.TARGET_PROFILES[target])
        host.require(callable(read_blob) and base_tree.get(source_admission.PROFILE) == expected
            and candidate_tree.get(source_admission.PROFILE) == expected,
            'Android partition requires the unchanged exact declared platform')
        declarations = []
        for tree in (base_tree, candidate_tree):
            raw = read_blob(tree[source_admission.PROFILE]['sha'])
            host.require(type(raw) is bytes and len(raw) <= 64_000
                and source_admission.blob_id(raw) == expected['sha'],
                'Android platform declaration bytes are unauthenticated')
            document = json.loads(raw, object_pairs_hook=inputs._unique_object)
            host.require(type(document) is dict and set(document) == {'schema', 'platform', 'suites'}
                and type(document['schema']) is int and document['schema'] == 1
                and document['platform'] == 'android' and type(document['suites']) is list
                and len(document['suites']) == (19 if target == 'android-phone' else 13),
                'Android partition platform inventory is incomplete')
            declarations.append(document['suites'])
        host.require(declarations[0] == declarations[1], 'Android declarations changed')
        commands, entries, seen = [], {}, set(names)
        for item in declarations[0]:
            host.require(type(item) is dict and set(item) == {'name', 'entrypoint', 'interpreter'}
                and type(item['name']) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]*', item['name'])
                and item['name'] not in seen and item['interpreter'] in {'python', 'bash'},
                'Android partition has an unknown or duplicate owner')
            path = inputs._path(item['entrypoint'], 'Android platform entrypoint')
            host.require(path.startswith('android/') or path.startswith('tests/device/'),
                'Android platform entrypoint is outside its fixed declaration')
            mode = '100755' if item['interpreter'] == 'bash' else '100644'
            for tree in (base_tree, candidate_tree):
                entry = tree.get(path)
                host.require(type(entry) is dict and entry['type'] == 'blob' and entry['mode'] == mode,
                    'Android platform implementation is missing or nonordinary')
            seen.add(item['name'])
            entries[path] = dict(candidate_tree[path])
            commands.append({'name': item['name'], 'command': [item['interpreter'], path]})
        value = {'schema': 1, 'kind': 'android-common-platform-partition-v1',
            'generation': PLATFORM_GENERATION, 'target': target, 'profile': expected,
            'commands': commands, 'entrypoints': entries,
            'common_owner': {'kind': 'shared', 'suites': names, 'include_platform': False, 'platform': {}}}
        value['digest'] = protocol.digest(value)
        return value
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise PreExecutionUnavailable('Android common/platform partition is not admitted') from error


def common_owner(profile, partition=None):
    """Return a truthful owner after its independently derived partition."""
    return (partition['common_owner'] if partition is not None else
        {'kind': 'shared', 'suites': profile['suites'],
         'include_platform': profile['selection']['include_platform'], 'platform': {}})


def current_platform_context(candidate, event, environment, adapter, *, root=ROOT, clock=None):
    """Authenticate a push as a push; never manufacture an open PR context."""
    if environment.get('GITHUB_EVENT_NAME') == 'pull_request':
        return prepare(candidate, event, environment, adapter)
    import postmerge
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    source, run_id = _platform_push_native(event, environment)
    binding, refs = adapter._integrated_current(run_id, 15368, now)
    target = binding['base_ref']
    host.require(target in _PLATFORM_TARGETS and refs['target'] == source
        and event.get('before') == binding['base_sha'] and refs['default_ref'] == 'main'
        and execution.checkout_identity(root)[0] == refs['default'], 'platform push native source differs')
    _, current = postmerge.full_tree(adapter, source)
    _, previous = postmerge.full_tree(adapter, binding['base_sha'])
    _, local = postmerge.full_tree(adapter, refs['default'])
    host.require(inputs.full_tree(root, refs['default']) == local
        and execution.checkout_identity(candidate) == (source, binding['merge_tree'])
        and inputs.full_tree(candidate, source) == current,
        'platform push checkout differs from complete immutable API source')
    policy = _host_policy()
    package = policy.package_policy()
    host.require(package.validate_tree_wiring(current) == PLATFORM_GENERATION,
        'platform push needs the complete enrolled future generation')
    workflow = refs['integration']['workflow_path']
    template = PLATFORM_PARENT_TEMPLATE if workflow == '.github/workflows/parent-qualification.yml' else PLATFORM_TEMPLATE
    host.require(workflow in {'.github/workflows/parent-qualification.yml', '.github/workflows/project-tests.yml'}
        and current.get(workflow) == local.get(template), 'platform push workflow is not its fixed recipe')
    # Loading current controllers and deriving ownership grants no execution
    # authority. Original B lookup data may differ only in the fixed seventeen.
    controller = postmerge.integrated_controller_for_reuse(policy, previous, current, local, target, root)
    registry = inputs.load_registry(root / '.github/test-suites.json')
    paths = sorted(path for path in previous.keys() | current.keys() if previous.get(path) != current.get(path))
    regular = bool(paths) and all(entry is None or entry['mode'] == '100644' and entry['type'] == 'blob'
        for path in paths for entry in (previous.get(path), current.get(path)))
    package_plan = package.candidate_plan(candidate,event,source)
    host.require(package_plan['candidate']==source and package_plan['tree']==binding['merge_tree']
        and package_plan['base']==binding['base_sha'] and package_plan['head']==source
        and package_plan['unknown'] is False and package_plan['paths']==paths
        and package_plan['regular'] is regular,
        'platform push package plan differs from complete immutable source')
    host.require(source_admission.shared_platform_supported({'include_platform': False}, target,
        current.get(source_admission.PROFILE)), 'platform push declaration is unknown')
    selected = None
    partition = None
    if package_plan['host_mode']=='unchanged':
        # Equal complete native maps are necessary, but not sufficient: repeat
        # the raw Git/event proof rather than trusting a scheduling field.
        host.require(not paths and previous == current,
            'unchanged platform route has changed inputs')
        package.verify_empty_plan(package_plan, candidate, event)
    elif package_plan['host_mode']!='full':
        # The existing exact package/documentation router owns these deltas.
        # A generic host selector must not invent a platform owner for them.
        host.require(regular and package_plan['host_mode'] in {
            'documentation','tool-dependencies','package-dependencies'},
            'unknown nonhost parent route')
    else:
        selected = policy.select(current, paths, regular, base_tree=previous, trusted_tree=local,
            candidate_root=root, trusted_root=root, target=target)
    if selected is not None and selected['include_platform'] is True:
        # A real platform owner must independently re-enter the unchanged strict
        # source and selection admission before setup or command execution.
        controller = postmerge.integrated_controller(policy, previous, current, local, target, root)
        profile = selection_profile(policy, registry, current, previous, local, root=root, target=target,
            read_blob=adapter.api.immutable_blob)
        host.require(profile['selection'] == selected, 'platform push selections differ')
        partition = platform_partition(policy, profile, registry, current, previous, local,
            target=target, root=root, read_blob=adapter.api.immutable_blob)
        host.require(partition is not None, 'required Android platform push is unsupported')
    elif selected is not None and selected['full_host'] is True:
        # Planning a common owner executes nothing. Keep original-source lookup
        # available when its inert test members differ from current default.
        profile = selection_profile_for_reuse(policy, registry, current, previous, local,
            root=root,target=target,read_blob=adapter.api.immutable_blob)
        host.require(profile['selection']==selected and selected['include_platform'] is False
            and profile['profile']==FULL_PROFILE and profile['binding'] is None,
            'full-host platform omission has no independent common owner')
    elif selected is not None:
        profile = selection_profile_for_reuse(policy, registry, current, previous, local,
            root=root,target=target,read_blob=adapter.api.immutable_blob)
        host.require(profile['selection']==selected and profile['profile']==ci_profile.PROFILE
            and type(profile['binding']) is dict
            and profile['binding'].get('generation_kind')==ci_profile.SEVEN_CONTROLLER_KIND
            and selected['full_host'] is False,
            'platform omission has no independently admitted seven-target CI owner')
    return {'number': binding['pull_request'], 'run_id': run_id, 'binding': binding, 'refs': refs,
        'candidate': candidate, 'registry': registry, 'selected': selected, 'platform_partition': partition,
        'integration': refs['integration'], 'controller': controller,'package_plan':package_plan}


def _platform_push_native(event, environment):
    """A closed future push role; the ordinary consumer entrypoint is unchanged."""
    target = environment.get('GITHUB_REF', '').removeprefix('refs/heads/')
    host.require(target in _PLATFORM_TARGETS, 'unknown platform push target')
    parent = target in {'android-main', 'android-vr'}
    workflow = 'parent-qualification' if parent else 'project-tests'
    jobs = {'route', 'common-parent', 'platform-tests', 'qualify-parent'} if parent else {
        'project-tests', 'platform-tests', 'project-results', 'route'}
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': producer_api.REPOSITORY,
        'GITHUB_REPOSITORY_ID': '1319052603', 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24'}
    source = producer_api.sha(environment.get('GITHUB_SHA'))
    host.require(all(environment.get(key) == value for key, value in expected.items())
        and environment.get('GITHUB_JOB') in jobs
        and environment.get('GITHUB_REF') == 'refs/heads/' + target
        and environment.get('GITHUB_WORKFLOW_SHA') == source
        and environment.get('GITHUB_WORKFLOW_REF') == producer_api.REPOSITORY
            + '/.github/workflows/' + workflow + '.yml@refs/heads/' + target
        and re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')),
        'platform requires its original current native push job')
    host.require(type(event) is dict and event.get('ref') == 'refs/heads/' + target
        and event.get('after') == source and event.get('deleted') is False
        and event.get('forced') is False
        and event.get('repository', {}).get('full_name') == producer_api.REPOSITORY
        and event.get('repository', {}).get('id') == 1319052603,
        'platform push event differs from current native source')
    return source, int(environment['GITHUB_RUN_ID'])


def current_platform_job(context, adapter):
    if 'integration' not in context:
        return current_run(context, adapter, 'platform')
    return _push_platform_job(context, adapter, 'Android platform tests')


def _push_platform_job(context, adapter, name):
    host.require(name in {'Android platform tests', 'Common parent tests', 'Shared tests'}, 'unknown native push role')
    binding, refs = adapter._integrated_current(context['run_id'], 15368, datetime.now(timezone.utc))
    host.require(binding == context['binding'] and refs == context['refs'], 'platform push source changed')
    attempt = adapter._object(f"actions/runs/{context['run_id']}/attempts/1")
    host.require(attempt.get('id') == context['run_id'] and attempt.get('run_attempt') == 1
        and attempt.get('head_sha') == context['binding']['merge_sha']
        and attempt.get('path') == context['integration']['workflow_path']
        and attempt.get('workflow_id') == context['integration']['workflow_id']
        and (attempt.get('status'), attempt.get('conclusion')) == ('in_progress', None),
        'platform push is not its original active attempt')
    jobs = adapter._pages(f"actions/runs/{context['run_id']}/attempts/1/jobs", 'jobs')
    matches = [row for row in jobs if row.get('name') == name]
    host.require(len(matches) == 1, 'native platform push role is missing or ambiguous')
    job = adapter._job(matches[0], attempt, 15368, final_name=name)
    host.require((job.status, job.conclusion) == ('in_progress', None), 'native platform push role is not running')
    return job


def _platform_bookend(context, event, environment, adapter):
    try:
        after = current_platform_context(context['candidate'], event, environment, adapter)
    except (PreExecutionUnavailable, ValueError, OSError) as error:
        raise host.Unavailable('platform source admission changed after execution') from error
    host.require(after['binding'] == context['binding'] and after['refs'] == context['refs']
        and after['platform_partition'] == context['platform_partition']
        and all(after.get(name)==context.get(name) for name in ('selected','controller','package_plan')),
        'Android platform selection changed after execution')


def completed_platform_job(context, adapter, *, now=None):
    """Authenticate the current separate job, never its self-reported JSON."""
    now = now or datetime.now(timezone.utc)
    if 'integration' in context:
        binding, refs = adapter._integrated_current(context['run_id'], 15368, now)
        host.require(binding == context['binding'] and refs == context['refs'],
            'current platform integration changed')
        name = 'Android platform tests'
    else:
        binding, refs = adapter.current(context['number'])
        host.require(binding == context['binding'] and refs == context['refs'],
            'current platform PR changed')
        name = PLATFORM_JOB
    latest = adapter._object('actions/runs/' + str(context['run_id']))
    attempt = adapter._object(f"actions/runs/{context['run_id']}/attempts/1")
    keys = ('id', 'workflow_id', 'check_suite_id', 'path', 'event', 'head_sha',
        'head_branch', 'run_attempt', 'status', 'conclusion')
    host.require(all(latest.get(key) == attempt.get(key) for key in keys)
        and attempt.get('id') == context['run_id'] and attempt.get('run_attempt') == 1
        and (attempt.get('status'), attempt.get('conclusion')) == ('in_progress', None),
        'current platform aggregate is not the original active attempt')
    if 'integration' not in context:
        chain = adapter._chain(attempt, context['policy'], context['binding'])
        host.require(chain['producer_commit'] == binding['merge_sha'], 'platform source chain changed')
    else:
        host.require(attempt.get('head_sha') == binding['merge_sha']
            and attempt.get('path') == refs['integration']['workflow_path']
            and attempt.get('workflow_id') == refs['integration']['workflow_id'],
            'completed platform job differs from current integration source')
    jobs = adapter._pages(f"actions/runs/{context['run_id']}/attempts/1/jobs", 'jobs')
    return _completed_platform_job(adapter, attempt, jobs, name, now)


def _completed_platform_job(adapter, attempt, jobs, name, now):
    """Fixed native step and app checks shared with completed-original lookup."""
    host.require(name in {PLATFORM_JOB, 'Android platform tests'}, 'unknown platform native job')
    matches = [row for row in jobs if row.get('name') == name]
    host.require(len(matches) == 1, 'required native platform job is missing or ambiguous')
    raw = matches[0]
    job = adapter._job(raw, attempt, 15368, final_name=name)
    host.require((job.status, job.conclusion) == ('completed', 'success'),
        'required native Android platform job did not succeed')
    steps = [step for step in raw.get('steps', []) if step.get('name') ==
        'Execute and verify the complete Android platform inventory']
    host.require(len(steps) == 1 and (steps[0].get('status'), steps[0].get('conclusion')) == ('completed', 'success')
        and protocol._time(job.started_at) <= protocol._time(steps[0].get('started_at'))
        <= protocol._time(steps[0].get('completed_at')) <= protocol._time(job.completed_at) <= now,
        'required native platform execution step is unavailable')
    return {'job_id': job.job_id, 'job': raw}


def _protected_source_context(adapter, binding, references, policy, *, _reuse_only=False):
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
        admitted=(ci_profile.reuse_controller_precheck(base,default,target,root=ROOT) if _reuse_only else
            source_admission.compatibility(base,default,target,
                read_actual=lambda name:source_admission.actual_bytes(ROOT,name),
                actual_imports=source_admission.actual_import_inventory(ROOT)))
        source_admission.require(admitted['controller_digest']==_controller_identity(policy),
            'source admission differs from actual default controller identity')
        return {**admitted,**({'kind':'reuse-current-controller-precheck-v1'} if _reuse_only else {}),
            'base':binding['base_sha'],'default':references['default']}
    except (source_admission.SourceUnavailable,host.Unavailable,OSError,ValueError,KeyError,TypeError) as error:
        raise PreExecutionUnavailable('protected base/default source is not enrolled') from error


def protected_source_context(adapter, binding, references, policy):
    return _protected_source_context(adapter,binding,references,policy)


def reuse_source_context(adapter, binding, references, policy):
    """Metadata lookup bookend only, never original producer/source authority."""
    return _protected_source_context(adapter,binding,references,policy,_reuse_only=True)


def prepare(candidate, event, environment, adapter):
    """Independently select a supported protected owner and source generation."""
    number, identifier = _native(environment)
    binding, refs = adapter.current(number)
    host.require(binding['merge_sha'] == environment['GITHUB_SHA'] and binding['base_ref'] == environment.get('GITHUB_BASE_REF') in source_admission.TARGET_PROFILES
                 and binding['head_ref'] == environment.get('GITHUB_HEAD_REF'), 'current PR differs from native invocation')
    from types import SimpleNamespace
    _event_binding(event, binding, api=SimpleNamespace(get=lambda endpoint: adapter._object(endpoint)))
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
    base_tree=inputs.full_tree(candidate,binding['base_sha'])
    trusted_tree=inputs.full_tree(ROOT,refs['default'])
    prepared_selection = selection_profile(policy,registry,candidate_tree,
        base_tree,trusted_tree,root=ROOT,target=binding['base_ref'],
        read_blob=lambda oid:source_blob(candidate,oid))
    if prepared_selection['selection'] != selected:
        raise PreExecutionUnavailable('independent package/host owner needs existing actual execution')
    names = prepared_selection['suites']
    partition = platform_partition(policy,prepared_selection,registry,candidate_tree,base_tree,trusted_tree,
        target=binding['base_ref'],root=ROOT,read_blob=lambda oid:source_blob(candidate,oid))
    if partition is None:
        if not source_admission.shared_platform_supported(selected,binding['base_ref'],candidate_tree.get(source_admission.PROFILE)):
            raise PreExecutionUnavailable('candidate platform declaration needs existing actual execution')
        if selected['include_platform'] is True and execution.platform_suites(candidate, registry['suites']):
            raise PreExecutionUnavailable('selected profile needs existing nonreusable execution')
    if binding['base_ref']!='main':
        future = execution_schema(policy,candidate_tree,binding['base_ref']) == 4
        supported = (prepared_selection['profile']==FULL_PROFILE and selected['full_host'] is True
            and (set(names)==set(registry['suites']) or selected.get('reason')=='protected-affected-dependencies')
            or prepared_selection['profile']==ci_profile.PROFILE
                and prepared_selection['binding'].get('generation_kind')==ci_profile.SEVEN_CONTROLLER_KIND)
        if not future or not supported:
            raise PreExecutionUnavailable('child protected owner needs independently admitted retained-source selection')
    plan = {'owners': {'shared-host': common_owner(prepared_selection,partition)}}
    template=project_template(policy,candidate_tree)
    blob = sandbox._git(ROOT, 'ls-tree', '-z', refs['default'], '--', template).split(b'\t')[0].split()[-1].decode()
    controller = source_context['controller_digest']
    schema = execution_schema(policy,candidate_tree,binding['base_ref'])
    producer = protocol.Policy('noah-l-frank/overte', 1319052603, 15368, '.github/workflows/project-tests.yml',
        blob, environment['GITHUB_REF'], ('pull_request',), controller, sandbox.contract(ROOT)['digest'],
        required_execution_schema=schema)
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
              'platform_partition':partition,
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
    if context.get('platform_partition') is not None:
        expected['platform'] = PLATFORM_JOB
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


def _platform_handoff():
    spec = importlib.util.spec_from_file_location('protected_platform_android_handoff',
        ROOT / 'tools/repository-checks/android_handoff.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pending_platform_owner(context, event, environment):
    """Only the existing Android owner may defer Pico; this is not a PASS."""
    try:
        value = _platform_handoff().platform_owner(context['candidate'], event,
            context['binding']['merge_sha'], environment['GITHUB_EVENT_NAME'], policy_root=ROOT)
    except ValueError:
        # An unavailable transfer executes Pico here. No platform command has
        # started and no existing owner has been claimed successful.
        return {}
    if value:
        execution._validate_platform_owner(value, context['binding']['merge_sha'])
        host.require(set(value) == {'pico4-device-free'}, 'unknown Android platform transfer')
    return value


def platform_prerequisites(partition, candidate, environment):
    """Prevent the existing phone fixture's missing-NDK exit0 from passing."""
    if not any(row['name'] == 'phone-package-binding' for row in partition['commands']):
        return {}
    sdk = environment.get('ANDROID_SDK_ROOT') or environment.get('ANDROID_HOME')
    host.require(type(sdk) is str and bool(sdk), 'required phone NDK is unavailable')
    sdk = Path(sdk).resolve(strict=True)
    host.require(not sdk.is_relative_to(candidate) and (sdk / 'ndk').is_dir(),
        'required phone NDK is outside its prepared system layout')
    compilers = []
    versions = list((sdk / 'ndk').iterdir())
    host.require(0 < len(versions) <= 32, 'phone NDK inventory is unbounded')
    for version in versions:
        host.require(not version.is_symlink() and version.is_dir()
            and re.fullmatch(r'[0-9]+(?:\.[0-9]+){2}', version.name), 'unknown phone NDK layout')
        compiler = version / 'toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
        if compiler.is_file() and os.access(compiler, os.X_OK):
            compilers.append((tuple(int(part) for part in version.name.split('.')), compiler))
    host.require(bool(compilers), 'required phone NDK clang is unavailable')
    # The existing fixture chooses the highest installed numeric version using
    # sort -V. Preserve that variant, but require and bind the actual compiler.
    compiler = max(compilers, key=lambda row: row[0])[1].resolve(strict=True)
    host.require(not compiler.is_relative_to(candidate), 'phone NDK compiler is candidate controlled')
    return {'ndk_clang': {'path': str(compiler), 'sha256': hashlib.sha256(compiler.read_bytes()).hexdigest()}}


def _run_platform_suites(candidate, commands, report):
    """Legacy process boundary in its OWN job; never capture a reusable E."""
    controller = execution._runner()
    suites = [controller.Suite(row['name'], 'quick', tuple(
        sys.executable if index == 0 and item == 'python' else item
        for index, item in enumerate(row['command']))) for row in commands]
    observations, cancelled, handlers = [], [], {}
    def interrupt(signum, _frame):
        if not cancelled:
            cancelled.append(signum)
    old_root, old_command = controller.ROOT, controller.run_command
    def run(command, timeout, cancellations):
        with execution.candidate_process_environment():
            return old_command(command, timeout, cancellations)
    controller.ROOT, controller.run_command = candidate, run
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, interrupt)
        from types import SimpleNamespace
        arguments = SimpleNamespace(timeout=240, host_timeout=900, native_build_dir=None,
            junit=report, fail_fast=False)
        status = controller.run_suites(arguments, suites, cancelled, result_callback=observations.append)
    finally:
        controller.ROOT, controller.run_command = old_root, old_command
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    return status or bool(cancelled), observations


def platform_execution(context, event, environment, adapter, *, report, runner=None):
    """Current mandatory platform execution, isolated from shared artifacts."""
    partition = context.get('platform_partition')
    host.require(partition is not None and partition['generation'] == PLATFORM_GENERATION,
        'platform execution requires its independently derived future partition')
    candidate = context['candidate']
    host.require(not Path(report).resolve().is_relative_to(candidate), 'platform report is candidate writable')
    identity = execution.checkout_identity(candidate)
    host.require(identity == (context['binding']['merge_sha'], context['binding']['merge_tree']),
        'platform checkout differs from exact current source')
    current_platform_job(context, adapter)
    delegated = pending_platform_owner(context, event, environment)
    commands = [row for row in partition['commands'] if row['name'] not in delegated]
    prerequisites = platform_prerequisites(partition, candidate, environment)
    status, observations = (runner or _run_platform_suites)(candidate, commands, report)
    # Once execution starts every error is hard. There is no retry or fallback.
    host.require(status == 0 and [row.get('name') for row in observations] == [row['name'] for row in commands]
        and all(row.get('status') == 'passed' for row in observations), 'required Android platform execution failed')
    host.require(execution.checkout_identity(candidate) == identity
        and platform_prerequisites(partition, candidate, environment) == prerequisites,
        'Android platform source or NDK changed during execution')
    _platform_bookend(context, event, environment, adapter)
    host.require(pending_platform_owner(context, event, environment) == delegated,
        'Android platform transfer changed after execution')
    current_platform_job(context, adapter)
    return {'schema': 1, 'kind': 'current-android-platform-job-v1', 'reusable': False,
        'qualification': False, 'candidate': context['binding']['merge_sha'], 'partition': partition['digest'],
        'executed': [row['name'] for row in commands], 'delegated': delegated, 'prerequisites': prerequisites}


def legacy_common_fallback(context, event, environment, adapter, *, report):
    """Pre-suite native unavailability may run common once; platform has its job."""
    host.require(context.get('platform_partition') is not None,
        'common-only fallback requires the independent platform owner')
    native = (lambda: _push_platform_job(context, adapter, 'Common parent tests'
        if context['binding']['base_ref'] in {'android-main', 'android-vr'} else 'Shared tests')) \
        if 'integration' in context else (lambda: current_run(context, adapter, 'shared'))
    native()
    status, receipt = execution.execute(context['candidate'], context['platform_partition']['common_owner']['suites'], include_platform=False,
        junit=report, _impact_selection=True)
    host.require(status == 0 and receipt['reusable'] is False and receipt['environment'] is None,
        'required common fallback failed')
    _platform_bookend(context, event, environment, adapter)
    native()
    return receipt


def verify_platform_project(candidate, event, environment, adapter, needs):
    """A separate mandatory job cannot disappear behind the common receipt."""
    policy = _host_policy()
    package = policy.package_policy()
    host.require(package.validate_wiring(candidate) == PLATFORM_GENERATION,
        'platform project aggregate requires the complete future generation')
    plan = package.candidate_plan(candidate, event, environment['GITHUB_SHA'])
    host.require(type(needs) is dict and set(needs) == {
        'route', 'project-tests', 'platform-tests', 'tool-dependencies', 'package-checks'},
        'platform project aggregate has an incomplete owner inventory')
    host.require(all(type(job) is dict for job in needs.values()), 'platform project job record is invalid')
    route = needs['route']
    published = route.get('outputs')
    host.require(type(published) is dict and set(published) == set(package.outputs(plan)) | {
        'protected_full', 'platform_required'}
        and published['protected_full'] in {'true', 'false'}
        and published['platform_required'] in {'true', 'false'}
        and (published['protected_full'] == 'false' or plan['host_mode'] == 'full'),
        'platform dispatch differs from its exact native route')
    context = (current_platform_context(candidate, event, environment, adapter)
        if published['protected_full'] == 'true' or environment.get('GITHUB_EVENT_NAME') == 'push'
            and environment.get('GITHUB_REF', '').removeprefix('refs/heads/') in _PLATFORM_TARGETS else None)
    if context is not None:
        context['candidate'] = candidate
    partition = context.get('platform_partition') if context else None
    host.require(published['platform_required'] == str(partition is not None).lower(),
        'platform dispatch differs from independently derived required ownership')
    job = needs['platform-tests']
    if partition is not None:
        host.require(job.get('result') == 'success' and job.get('outputs') == {
            'required': 'true', 'verified': 'true', 'partition': partition['digest'].removeprefix('sha256:')},
            'required independent Android platform job did not succeed')
        completed_platform_job(context, adapter)
        _platform_bookend(context, event, environment, adapter)
    else:
        host.require(job.get('result') == 'skipped' and job.get('outputs') in (
            {}, {'verified': '', 'partition': ''}, {'required': '', 'verified': '', 'partition': ''}),
            'unselected platform job has an unexpected claim')
    ordinary = {key: value for key, value in published.items()
        if key not in {'protected_full', 'platform_required'}}
    normalized = {key: value for key, value in needs.items() if key != 'platform-tests'}
    normalized['route'] = {**route, 'outputs': ordinary}
    return package.verify(normalized, plan, candidate=candidate, event=event)


def parent_route_outputs(context):
    """Dispatch hints bound to current native source; never reusable evidence."""
    host.require(context['binding']['base_ref'] in {'android-main','android-vr'}
        and context['refs']['target']==context['binding']['merge_sha'], 'unreviewed parent route target')
    partition=context['platform_partition']
    identity={'schema':1,'kind':'current-parent-platform-route-v1','binding':context['binding'],
        'default':context['refs']['default'],'controller':context['controller'],
        'selection':context['selected'],'package_plan':context.get('package_plan'),
        'partition':partition['digest'] if partition else None}
    return {'parent_candidate':context['binding']['merge_sha'],
        'parent_plan':protocol.digest(identity).removeprefix('sha256:'),
        'platform_required':str(partition is not None).lower()}


def _empty_parent_source(candidate,event,environment,adapter):
    """Independently prove why an existing main/Apple parent has no route VM."""
    import postmerge
    source,run_id=postmerge._native(event,environment)
    binding,refs=adapter._integrated_current(run_id,15368,datetime.now(timezone.utc))
    target=binding['base_ref']
    host.require(target in {'main','apple-main'} and refs['target']==source
        and event.get('before')==binding['base_sha'] and refs['default_ref']=='main',
        'skipped parent routing has no known empty-platform source')
    tree,current=postmerge.full_tree(adapter,source)
    _,previous=postmerge.full_tree(adapter,binding['base_sha'])
    default_tree,local=postmerge.full_tree(adapter,refs['default'])
    host.require(execution.checkout_identity(ROOT)==(refs['default'],default_tree)
        and inputs.full_tree(ROOT,refs['default'])==local
        and execution.checkout_identity(candidate)==(source,tree)
        and inputs.full_tree(candidate,source)==current
        and refs['integration']['workflow_path']=='.github/workflows/parent-qualification.yml'
        and current.get('.github/workflows/parent-qualification.yml')==local.get(PLATFORM_PARENT_TEMPLATE)
        and all(snapshot.get(source_admission.PROFILE)==source_admission.ordinary(source_admission.SHARED_PROFILE)
            for snapshot in (previous,current,local)), 'empty parent profile or native source changed')
    controller=postmerge.integrated_controller_for_reuse(_host_policy(),previous,current,local,target,ROOT)
    authority=postmerge.default_authority(adapter,refs)
    return binding,refs,controller,authority


def verify_platform_parent(candidate, event, environment, adapter, needs):
    """The old required parent check stays downstream of BOTH actual owners."""
    package = _host_policy().package_policy()
    host.require(package.validate_wiring(candidate) == PLATFORM_GENERATION
        and type(needs) is dict and set(needs) == {'route','common-parent', 'platform-tests'}
        and all(type(row) is dict for row in needs.values())
        and needs['common-parent'].get('result') == 'success',
        'future parent aggregate requires its complete successful common job')
    target = environment.get('GITHUB_REF', '').removeprefix('refs/heads/')
    platform = needs['platform-tests']
    plan = package.candidate_plan(candidate, event, environment['GITHUB_SHA'])
    if plan['host_mode'] == 'unchanged':
        import postmerge
        before = postmerge.no_execution_context(event, environment, adapter, candidate=candidate)
        if target in {'main','apple-main'}:
            host.require(needs['route'].get('result') == 'skipped'
                and needs['route'].get('outputs') == {}, 'unchanged shared parent has a routing claim')
        else:
            context = current_platform_context(candidate, event, environment, adapter)
            host.require(context['selected'] is None and context['platform_partition'] is None
                and needs['route'].get('result') == 'success'
                and needs['route'].get('outputs') == parent_route_outputs(context),
                'unchanged Android route differs from current native source')
        host.require(platform.get('result') == 'skipped' and platform.get('outputs') == {},
            'unchanged parent cannot claim platform execution')
        _completed_empty_parent(adapter, before, environment)
        host.require(postmerge.no_execution_context(event, environment, adapter, candidate=candidate) == before,
            'unchanged parent inputs changed during aggregate verification')
        return
    if target in {'main','apple-main'}:
        before=_empty_parent_source(candidate,event,environment,adapter)
        host.require(needs['route'].get('result')=='skipped' and needs['route'].get('outputs')=={}
            and platform.get('result')=='skipped' and platform.get('outputs')=={},
            'empty-profile parent requires exact unselected routing/platform jobs')
        host.require(_empty_parent_source(candidate,event,environment,adapter)==before,
            'empty parent source changed during aggregate verification')
        return
    host.require(target in {'android-main','android-vr'}, 'unreviewed parent platform target')
    context = current_platform_context(candidate, event, environment, adapter)
    host.require(needs['route'].get('result')=='success'
        and needs['route'].get('outputs')==parent_route_outputs(context),
        'parent dispatch differs from independently rederived current native source')
    partition = context['platform_partition']
    if partition is not None:
        expected={'required':'true','verified':'true','partition':partition['digest'].removeprefix('sha256:')}
        host.require(platform.get('result')=='success' and platform.get('outputs')==expected,
            'current parent platform owner is missing or failed')
        completed_platform_job(context, adapter)
    else:
        host.require(platform.get('result')=='skipped' and platform.get('outputs')=={},
            'unselected parent platform job made a claim')
    _platform_bookend(context, event, environment, adapter)


def _completed_empty_parent(adapter, context, environment):
    """A successful fixed native validation step, never a test receipt."""
    run_id = int(environment['GITHUB_RUN_ID'])
    binding, refs = adapter._integrated_current(run_id, 15368, datetime.now(timezone.utc))
    host.require(binding == context['binding'] and refs == context['refs'],
        'unchanged parent native source changed')
    latest = adapter._object(f'actions/runs/{run_id}')
    attempt = adapter._object(f'actions/runs/{run_id}/attempts/1')
    keys = ('id','workflow_id','check_suite_id','path','event','head_sha',
        'head_branch','run_attempt','status','conclusion')
    host.require(all(latest.get(key) == attempt.get(key) for key in keys)
        and attempt.get('id') == run_id and attempt.get('run_attempt') == 1
        and attempt.get('head_sha') == binding['merge_sha']
        and attempt.get('path') == refs['integration']['workflow_path']
        and attempt.get('workflow_id') == refs['integration']['workflow_id']
        and (attempt.get('status'), attempt.get('conclusion')) == ('in_progress',None),
        'unchanged parent aggregate has no original active native attempt')
    jobs = adapter._pages(f'actions/runs/{run_id}/attempts/1/jobs','jobs')
    matches = [row for row in jobs if row.get('name') == 'Common parent tests']
    host.require(len(matches) == 1, 'unchanged parent native job is missing or ambiguous')
    raw = matches[0]
    job = adapter._job(raw, attempt, 15368, final_name='Common parent tests')
    host.require((job.status,job.conclusion) == ('completed','success'),
        'unchanged parent native validation failed')
    steps = [step for step in raw.get('steps',[]) if step.get('name') ==
        'Independently verify unchanged parent inputs']
    host.require(len(steps) == 1
        and (steps[0].get('status'),steps[0].get('conclusion')) == ('completed','success')
        and protocol._time(job.started_at) <= protocol._time(steps[0].get('started_at'))
        <= protocol._time(steps[0].get('completed_at')) <= protocol._time(job.completed_at)
        <= datetime.now(timezone.utc), 'unchanged parent native validation step is unavailable')


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
                    read_blob=lambda oid:source_blob(batch.candidate,oid),**_ci_runtime_context(context,batch.candidate))
            else:
                attested.validate_environment(environment, utc_seconds(now), utc_seconds(now + timedelta(hours=24)),
                                             now, root=ROOT, isolated=True)
        except (attested.AttestedReuseUnavailable, runtime_ci.CIEnvironmentError) as error:
            raise PreExecutionUnavailable('original selected environment has no qualified admission') from error
    source=None
    if context['policy'].producer.required_execution_schema==4:
        try:
            manifest=ci_profile.load_controller_projection(batch.policy)
            host.require(manifest['source_commit']==context['refs']['default'],
                         'actual retained source differs from native admitted D')
            source=ci_profile.capture_retained_source(manifest,batch.projection,batch.binding,
                context['source_context'],root=ROOT)
        except (ci_profile.CIProfileError,OSError,ValueError) as error:
            raise PreExecutionUnavailable('original source projection cannot be retained') from error
    if source is not None:
        original = git_context(batch.snapshot)
        host.require(original == context['git_context'], 'actual materialized Git context differs from immutable API source')
        execution.validate_git_context(source['binding']['git_context'],
            context['binding']['merge_sha'], context['binding']['merge_tree'])
        if source['binding']['source'] != context['binding']['merge_sha'] \
                or source['binding']['git_context'] != original:
            raise execution.ExecutionError('retained source does not bind original materialized candidate before execution')
    options = {'preexecution_unavailable':PreExecutionUnavailable} if context.get('profile') == ci_profile.PROFILE else {}
    statuses, before, after = shared.check_batch(batch, context['registry'], cancelled, installed,
        names=context['plan']['owners']['shared-host']['suites'], admit=admit, **options)
    host.require(not cancelled and before == after, 'protected execution did not finish successfully')
    if source is not None:
        host.require(ci_profile.capture_retained_source(ci_profile.load_controller_projection(batch.policy),
            batch.projection,batch.binding,context['source_context'],root=ROOT)==source,
            'original protected source projection changed after candidate execution')
    original = git_context(batch.snapshot)
    host.require(original == context['git_context'], 'actual materialized Git context differs from immutable API source')
    names = [entry['name'] for entry in statuses]
    receipt = {'schema': context['policy'].producer.required_execution_schema, 'producer': execution.PRODUCER, 'candidate_commit': context['binding']['merge_sha'],
        'candidate_tree': context['binding']['merge_tree'], 'git_context': original, 'environment': before, 'reusable': True,
        'requested_suites': names, 'include_platform': context['plan']['owners']['shared-host']['include_platform'],
        'results': {name: {'status': 'passed', 'fingerprint': inputs.suite_fingerprint(context['registry'], name, tree, before)} for name in names},
        'platform_results': {}, 'conclusion': 'success', 'started_at': started, 'completed_at': utc_seconds()}
    if source is not None:receipt['protected_source']=source
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
    schema=context['policy'].producer.required_execution_schema
    host.require(receipt.get('schema') == schema and schema in {3,4}, 'isolated publisher has the wrong versioned receipt')
    if schema==4:
        retained=receipt.get('protected_source')
        host.require(ci_profile.retained_source_shape(retained)['admission']==context['source_context'],
                     'original default source changed before native final publication')
        manifest=ci_profile.capture_controller_manifest(ROOT,context['refs']['default'])
        ci_profile.validate_retained_source(retained,inputs.full_tree(context['candidate'],context['binding']['base_sha']),
            manifest['entries'],native_binding=context['binding'],run_id=run.run_id,registry=context['registry'],
            selection=context['selected'],environment=receipt['environment'],root=ROOT)
        host.require(ci_profile._digest(manifest)==retained['manifest_digest']
            and ci_profile._digest(ci_profile._retained_projection(manifest,retained['binding'],ROOT))==retained['projection_digest'],
            'native publisher cannot reconstruct original full projection')
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
            read_blob=lambda oid:source_blob(context['candidate'],oid),**_ci_runtime_context(context,context['candidate']))
    else:
        attested.validate_environment(receipt['environment'], qualified, expires, now, root=ROOT, isolated=True)
    value = {'schema': 1, 'producer': 'overte-producer-aggregate-v1', 'descriptor_digest': descriptor['descriptor_digest'],
        'results': {'shared-host': {'status': 'passed', 'job_id': owner.job_id, 'attempt': 1, 'receipt': receipt}},
        'qualified_at': qualified, 'expires_at': expires}
    value['aggregate_digest'] = protocol.digest(value)
    return value


def _owner_target_supported(context):
    """Use only the actual source admission returned by protected prepare.

    This context is reconstructed internally, never read from candidate JSON.
    Versioned child owners retain their independently derived exact selection
    and separate platform boundary. This helper never admits a supplied plan.
    """
    target = context['binding']['base_ref']
    source = context.get('source_context')
    if target not in _CURRENT_OWNER_TARGETS or type(source) is not dict or type(source.get('schema')) is not int or source['schema'] != 1 \
            or source.get('kind') != 'protected-default-controller-source-v1' or source.get('target') != target \
            or source.get('base') != context['binding']['base_sha'] or source.get('default') != context['refs']['default'] \
            or source.get('controller_digest') != context['policy'].producer.controller_digest \
            or not isinstance(source.get('lookup_digest'), str) \
            or re.fullmatch(r'sha256:[0-9a-f]{64}', source['lookup_digest']) is None:
        return False
    if target == 'main':
        return True
    if context['policy'].producer.required_execution_schema != 4:
        return False
    owner = context['plan']['owners']['shared-host']
    selected = context['selected']
    full = (context['profile'] == FULL_PROFILE and selected['full_host'] is True
        and (owner['suites'] == list(context['registry']['suites'])
            or selected.get('reason') == 'protected-affected-dependencies'
                and selected.get('affected',{}).get('dependency_schema') == 2
                and selected['affected'].get('target') == target))
    ci = (context['profile'] == ci_profile.PROFILE and selected['full_host'] is False
        and selected['include_platform'] is False and type(context.get('profile_binding')) is dict
        and context['profile_binding'].get('generation_kind') == ci_profile.SEVEN_CONTROLLER_KIND)
    return (bool(owner['suites']) and owner['suites'] == selected['suites'] and (full or ci)
        and (owner['include_platform'] is False or source.get('target_profile') == inputs._AFFECTED_SHARED_PROFILE))


def _completed_owner_outputs(context, receipt):
    """Dispatch hints only, emitted after actual selected publication validates."""
    supported = (_host_policy().package_policy().validate_wiring(context['candidate']) in {
                    CURRENT_OWNER_GENERATION,ci_profile.RETAINED_SOURCE_GENERATION}
                 and _owner_target_supported(context))
    passed = {name for name, result in receipt['results'].items() if result['status'] == 'passed'} if supported else set()
    return {'documentation_verified': str(DOCUMENTATION_SUITES <= passed).lower(),
            'workflow_contracts_verified': str(WORKFLOW_CONTRACT_SUITES <= passed).lower()}


def verify_current_owners(candidate, event, environment, adapter, *, demanded,
                          clock=lambda: datetime.now(timezone.utc)):
    """Authenticate completed owners of this still-running original PR only.

    This fixed outer job may consume its own completed native producer jobs;
    it cannot make the overall pending run a completed reusable authority.
    The caller still checks every other required lane independently.
    """
    host.require(type(demanded) in {set, frozenset} and demanded in _CURRENT_OWNER_DEMANDS
                 and environment.get('GITHUB_JOB') == 'repository-checks',
                 'current owner lookup requires a fixed native outer owner group')
    protected_admission()
    candidate = Path(candidate).resolve(strict=True)
    host.require(candidate == Path(environment['GITHUB_WORKSPACE']).resolve(strict=True) / 'candidate',
                 'current owner candidate is outside the exact native checkout')
    context = prepare(candidate, event, environment, adapter)
    package = _host_policy().package_policy()
    owner_generation=package.validate_wiring(candidate)
    host.require(owner_generation in {CURRENT_OWNER_GENERATION,ci_profile.RETAINED_SOURCE_GENERATION}
                 and _owner_target_supported(context)
                 and demanded <= set(context['plan']['owners']['shared-host']['suites']),
                 'current owner requires the exact enrolled generation and every actual command')

    def observe():
        snapshot = adapter.capture(context['number'], context['plan'], context['policy'], now=clock())
        host.require(snapshot.binding == context['binding'] and snapshot.references == context['refs'],
                     'current owner source differs from independently selected native context')
        authority = protocol.select_authority(snapshot.observations, snapshot.binding, context['plan'],
            context['policy'].producer, inventory_complete=snapshot.inventory_complete, now=clock())
        host.require(authority['state'] == 'pending' and authority['run_id'] == context['run_id']
                     and authority['attempt'] == 1,
                     'current owner is not the unique original current native run')
        selected = next(item for item in snapshot.observations if item.run.run_id == context['run_id'])
        run = selected.run
        host.require(run.status == 'in_progress' and run.conclusion is None and run.attempt == run.latest_attempt == 1
                     and run.workflow_commit == context['binding']['merge_sha']
                     and snapshot.source_chains[run.run_id]['producer_commit'] == context['binding']['merge_sha']
                     and run.final_publisher is not None,
                     'current owner does not belong to the actual original native merge execution')
        latest = adapter._object('actions/runs/' + str(run.run_id))
        host.require(latest.get('id') == run.run_id and latest.get('run_attempt') == 1
                     and latest.get('status') == run.status and latest.get('conclusion') is None,
                     'current outer run changed during owner authentication')
        jobs = adapter._pages(f'actions/runs/{run.run_id}/attempts/1/jobs', 'jobs')
        matches = [job for job in jobs if job.get('name') == 'repository-checks']
        host.require(len(matches) == 1, 'current outer aggregate job is missing or ambiguous')
        outer = adapter._job(matches[0], latest, 15368, final_name='repository-checks')
        host.require(outer.status == 'in_progress' and outer.conclusion is None
                     and outer.started_at is not None and outer.completed_at is None
                     and run.final_publisher.job.completed_at is not None
                     and protocol._time(run.final_publisher.job.completed_at) <= protocol._time(outer.started_at) <= clock()
                     and outer.job_id not in {run.publisher.job_id, run.final_publisher.job.job_id,
                                              *(job.job_id for job in run.owners.values())},
                     'current outer aggregate did not start after its completed original publisher')
        return snapshot, selected, outer

    initial, observation, outer = observe()
    run = observation.run
    items = initial.artifact_inventories[run.run_id]
    raw, facts = adapter._artifact(run, 'aggregate', items, clock(), context['binding']['head_sha'])
    host.require(raw is not None and facts is not None, 'current original aggregate is unavailable')
    aggregate = protocol.read_artifact(raw, 'aggregate', facts, run, now=clock())
    receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
    host.require(type(receipt) is dict and receipt.get('schema') == context['policy'].producer.required_execution_schema,
                 'current owner requires the actual versioned isolated original receipt')
    tree = inputs.full_tree(candidate, context['binding']['merge_sha'])
    host.require(tree.get('tests/platform-profile.json') == context['source_context']['target_profile'],
                 'current owner platform declaration differs from its actual protected source admission')
    retained=retained_receipt_source(receipt,context['binding'],adapter,context['registry'],
        context['selected'],run.run_id)
    shared_context = protocol.SharedContext(context['registry'], tree, receipt['environment'],
        context['binding']['merge_sha'], context['binding']['merge_tree'], context['git_context'],retained)
    verified = protocol._verify_original_payload(raw, facts, context['binding'], context['plan'],
        context['policy'].producer, observation, contexts={'shared-host': shared_context}, now=clock())
    host.require(receipt['requested_suites'] == context['plan']['owners']['shared-host']['suites']
                 and demanded <= set(receipt['results']), 'current owner omitted an actual demanded result')
    if context['profile'] == ci_profile.PROFILE:
        runtime_ci.validate_environment(receipt['environment'], aggregate['qualified_at'], aggregate['expires_at'], clock(),
            context['selected'], tree, inputs.full_tree(ROOT, context['refs']['default']), context['registry'], root=ROOT,
            read_blob=lambda oid:source_blob(candidate, oid),**_ci_runtime_context(context,candidate))
    else:
        attested.validate_environment(receipt['environment'], aggregate['qualified_at'], aggregate['expires_at'],
                                      clock(), root=ROOT, isolated=True)
    final, final_observation, final_outer = observe()
    host.require(final == initial and final_observation == observation and final_outer == outer
                 and prepare(candidate, event, environment, adapter) == context
                 and package.validate_wiring(candidate) == owner_generation
                 and clock() < protocol._time(verified['expires_at']),
                 'current original proof, native jobs, artifacts or protected source changed')
    return {**verified, 'kind': 'current-original-pr-owners', 'qualification': False, 'reusable': False,
            'suites': sorted(demanded),
            'source_chain': final.source_chains[run.run_id], 'outer_job_id': outer.job_id}


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
        host.require(all(re.fullmatch(r'[a-z_]+', key) and (re.fullmatch(r'(?:true|false|[0-9a-f]{64})', value)
            or key=='parent_candidate' and re.fullmatch(r'[0-9a-f]{40}',value)
            or key=='platform_plan' and value=='' and values.get('platform_required')=='false')
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
            projection = shared.project_policy(policy_path, shared.sources(), trusted_source=context['refs']['default'])
            binding = {'source': context['binding']['merge_sha'], 'run_id': context['run_id'], 'run_attempt': 1,
                'profile': shared.PROFILE, 'snapshot': snapshot['digest'], 'git_context': git_context(snapshot),
                'runtime_profile':context['profile'],'selection':context['selected'],
                'profile_binding':context['profile_binding'],
                'registry': execution.digest(context['registry']), 'prepared': installed, 'projection': execution.digest(projection),
                'outside_namespaces': {name: os.stat('/proc/self/ns/' + name).st_ino for name in ('user', 'mnt', 'pid', 'net', 'ipc', 'uts')}}
            if context['profile_binding'] is not None and context['profile_binding'].get('generation_kind') == ci_profile.SEVEN_CONTROLLER_KIND:
                binding.update(selection_target=context['binding']['base_ref'],selection_base=context['binding']['base_sha'])
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
    parser.add_argument('role', choices=('descriptor', 'shared', 'publish', 'platform', 'platform-plan','parent-route',
        'fallback-common', 'project-verify', 'parent-verify'))
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.role in {'project-verify', 'parent-verify'}:
        event_path = Path(os.environ['GITHUB_EVENT_PATH'])
        host.require(event_path.is_file() and not event_path.is_symlink() and event_path.stat().st_size <= 1_000_000,
            'native project event is unavailable')
        event = json.loads(event_path.read_bytes(), object_pairs_hook=inputs._unique_object)
        needs = json.loads(os.environ['CHECK_RESULTS'], object_pairs_hook=inputs._unique_object)
        if args.role == 'parent-verify':
            verify_platform_parent(args.candidate, event, os.environ, producer_api.Adapter(), needs)
            return 0
        value = verify_platform_project(args.candidate, event, os.environ, producer_api.Adapter(), needs)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
            output.write(''.join(f'{key}={item}\n' for key, item in value.items()))
        return 0
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
        context = (current_platform_context(candidate, event, os.environ, adapter)
            if args.role in {'platform', 'platform-plan', 'parent-route', 'fallback-common'} else
            prepare(candidate, event, os.environ, adapter))
    except PreExecutionUnavailable:
        if args.role == 'descriptor':
            _output({'protected_full': 'false'})
            return 0
        raise
    context['candidate'] = candidate
    if args.role=='parent-route':
        _platform_bookend(context,event,os.environ,adapter)
        _output(parent_route_outputs(context))
        return 0
    if args.role == 'platform-plan':
        partition = context.get('platform_partition')
        _output({'platform_required': str(partition is not None).lower(),
            'platform_plan': partition['digest'].removeprefix('sha256:') if partition else ''})
        return 0
    if args.role == 'platform':
        report = _directory('ci-platform-report') / 'platform.xml'
        result = platform_execution(context, event, os.environ, adapter, report=report)
        _output({'platform_verified': 'true', 'platform_plan': result['partition'].removeprefix('sha256:')})
        return 0
    if args.role == 'fallback-common':
        legacy_common_fallback(context, event, os.environ, adapter,
            report=_directory('ci-common-fallback-report') / 'common.xml')
        return 0
    run = current_run(context, adapter, args.role)
    if args.role == 'descriptor':
        value = protocol.descriptor(context['binding'], context['plan'], context['policy'].producer, run)
        _bookend(context, adapter)
        execution._write_receipt(_directory('ci-producer-descriptor') / 'descriptor.json', value)
        _output({'protected_full': 'true', 'platform_required': str(context.get('platform_partition') is not None).lower()})
        return 0
    descriptor, facts = _descriptor(context, adapter, run)
    receipt = _receipt_artifact(context, run, adapter)
    value = publication(context, descriptor, receipt, run, datetime.now(timezone.utc), facts.expires_at)
    _bookend(context, adapter)
    host.require(current_run(context, adapter, 'publish') == run, 'native publication job changed before output')
    execution._write_receipt(_directory('ci-producer-aggregate') / 'aggregate.json', value)
    _output(_completed_owner_outputs(context, receipt))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (host.Unavailable, producer_api.ApiError, protocol.ProtocolError, execution.ExecutionError,
            inputs.InputError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        # Candidate output and server/private metadata are never log commands.
        detail = (sandbox.safe_diagnostic(str(error).encode()[:8192]) if isinstance(error, host.Unavailable)
                  else json.dumps(host.failure_summary(error), sort_keys=True))
        print('Protected shared producer failed closed: ' + detail, file=sys.stderr)
        raise SystemExit(1)
