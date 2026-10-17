#!/usr/bin/env python3
"""Finite protected-base commitment for the actual default-branch controller.

This module uses only the standard library. The native recipe verifies its own
ordinary immutable B blob before executing it. It imports no repository code,
installs nothing and confers no runtime or suite qualification.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

REPOSITORY = 'noah-l-frank/overte'
REPOSITORY_ID = 1319052603
SELF = 'tools/test-evidence/source_admission.py'
PROFILE = 'tests/platform-profile.json'
DOCUMENTATION_WORKFLOW = '.github/workflows/documentation-push-owner.yml'
DOCUMENTATION_TARGETS = frozenset({'main','android-phone','android-vr-pico','apple-ios'})
SHARED_PROFILE = 'd63537504c20204de9d35d9be61da72a56df59c3'
TARGET_PROFILES = {
    'main': SHARED_PROFILE,
    'android-main': '1314006455751831be60b143e46ce9c6f5398e26',
    'android-phone': 'f91169af7bdfedffb0b6ab9ab0ac1da28fd1f7fe',
    'android-vr': '1314006455751831be60b143e46ce9c6f5398e26',
    'android-vr-pico': '1314006455751831be60b143e46ce9c6f5398e26',
    'apple-main': SHARED_PROFILE,
    'apple-ios': SHARED_PROFILE,
}
# No caller may supply a shorter graph. Changes require independent source review.
CONTROLLERS = (
    '.github/android-checks.json',
    '.github/android-orchestration.json',
    '.github/android-owner-transfer.json',
    '.github/attested-runtime.json',
    '.github/branch-policy.json',
    '.github/ci37-runtime.json',
    '.github/package-workflow-generations.json',
    '.github/repository-checks.json',
    '.github/shared-sandbox.json',
    '.github/sync-test-reuse.json',
    '.github/test-suite-dependencies.json',
    '.github/test-suites.json',
    '.github/workflows/documentation-checks.yml',
    '.github/workflows/documentation-push-owner.yml',
    '.github/workflows/shared-sandbox-host-diagnostic.yml',
    '.github/workflows/workflow-security.yml',
    'tests/platform-profile.json',
    'tests/requirements-host.txt',
    'tests/requirements-repository.txt',
    'tests/run-project-tests.py',
    'tools/branch-policy/check.py',
    'tools/native-tests/check.py',
    'tools/repository-checks/android.py',
    'tools/repository-checks/android_gate.py',
    'tools/repository-checks/android_handoff.py',
    'tools/repository-checks/check.py',
    'tools/repository-checks/host_selection.py',
    'tools/repository-checks/metadata_context.py',
    'tools/repository-checks/npm-proxy-addr-tests.cjs',
    'tools/repository-checks/npm-source-map-tests.cjs',
    'tools/repository-checks/npm_consumers.py',
    'tools/repository-checks/package_checks.py',
    'tools/repository-checks/tool_dependencies.py',
    'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
    'tools/repository-checks/workflows/metadata-edits/repository-checks.yml',
    'tools/repository-checks/workflows/metadata-edits/sync-test-reuse.yml',
    'tools/repository-checks/workflows/npm-consumers/browser-client.yml',
    'tools/repository-checks/workflows/npm-consumers/repository-checks.yml',
    'tools/repository-checks/workflows/packages/parent-qualification.yml',
    'tools/repository-checks/workflows/packages/project-tests.yml',
    'tools/repository-checks/workflows/packages/repository-checks-direct.yml',
    'tools/repository-checks/workflows/packages/repository-checks.yml',
    'tools/repository-checks/workflows/packages/sync-validation.yml',
    'tools/repository-checks/workflows/producers/parent-qualification.yml',
    'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
    'tools/repository-checks/workflows/producers/project-tests.yml',
    'tools/repository-checks/workflows/producers/protected-project-tests.yml',
    'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
    'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml',
    'tools/sbom/requirements-validation.txt',
    'tools/sync-test-reuse/differential.py',
    'tools/sync-test-reuse/gate.py',
    'tools/sync-test-reuse/qualification.py',
    'tools/test-evidence/attested.py',
    'tools/test-evidence/ci_profile.py',
    'tools/test-evidence/execution.py',
    'tools/test-evidence/inputs.py',
    'tools/test-evidence/postmerge.py',
    'tools/test-evidence/producer.py',
    'tools/test-evidence/producer_api.py',
    'tools/test-evidence/producer_workflow.py',
    'tools/test-evidence/run.py',
    'tools/test-evidence/runtime.py',
    'tools/test-evidence/runtime_ci.py',
    'tools/test-evidence/sandbox.py',
    'tools/test-evidence/sandbox_host.py',
    'tools/test-evidence/sandbox_host_fixture.py',
    'tools/test-evidence/sandbox_probe.py',
    'tools/test-evidence/sandbox_shared.py',
    'tools/test-evidence/source_admission.py',
    'tools/test-evidence/validate-sync.py',
)
IMPORT_ROOTS = ('tools/test-evidence',)
IMPORT_MEMBERS = (
    'tools/test-evidence/AFFECTED_SELECTION.md',
    'tools/test-evidence/affected-test.py',
    'tools/test-evidence/attested-test.py',
    'tools/test-evidence/attested.py',
    'tools/test-evidence/ci-integration-test.py',
    'tools/test-evidence/ci-profile-test.py',
    'tools/test-evidence/ci_profile.py',
    'tools/test-evidence/execution-test.py',
    'tools/test-evidence/execution.py',
    'tools/test-evidence/inputs.py',
    'tools/test-evidence/postmerge.py',
    'tools/test-evidence/producer-api-test.py',
    'tools/test-evidence/producer-test.py',
    'tools/test-evidence/producer.py',
    'tools/test-evidence/producer_api.py',
    'tools/test-evidence/producer_workflow.py',
    'tools/test-evidence/qualification-producer-test.py',
    'tools/test-evidence/registry-test.py',
    'tools/test-evidence/run.py',
    'tools/test-evidence/runtime-ci-test.py',
    'tools/test-evidence/runtime-test.py',
    'tools/test-evidence/runtime.py',
    'tools/test-evidence/runtime_ci.py',
    'tools/test-evidence/sandbox-host-test.py',
    'tools/test-evidence/sandbox-test.py',
    'tools/test-evidence/sandbox.py',
    'tools/test-evidence/sandbox_host.py',
    'tools/test-evidence/sandbox_host_fixture.py',
    'tools/test-evidence/sandbox_probe.py',
    'tools/test-evidence/sandbox_shared.py',
    'tools/test-evidence/source-admission-test.py',
    'tools/test-evidence/source_admission.py',
    'tools/test-evidence/test.py',
    'tools/test-evidence/validate-sync-test.py',
    'tools/test-evidence/validate-sync.py',
)
_SHA = re.compile(r'[0-9a-f]{40}\Z')

class SourceUnavailable(ValueError):
    """Protected execution unavailable before candidate suites start."""

def require(value, message):
    if not value:
        raise SourceUnavailable(message)

def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate protected source JSON field')
        result[key] = value
    return result

def digest(value):
    return 'sha256:' + hashlib.sha256((json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()).hexdigest()

def object_id(value):
    require(type(value) is str and _SHA.fullmatch(value) and value != '0'*40, 'invalid immutable source object')
    return value

def ordinary(oid, mode='100644'):
    return {'mode':mode,'type':'blob','sha':object_id(oid)}

def blob_id(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def actual_bytes(root, relative, maximum=1_000_000):
    root = Path(root)
    require(root.is_absolute() and '..' not in root.parts, 'source root must be canonical')
    current = Path(root.anchor)
    for part in (*root.parts[1:], *Path(relative).parts):
        current /= part
        require(not current.is_symlink(), 'protected source contains an alias')
    info = current.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, 'protected source is not a bounded ordinary file')
    raw = current.read_bytes()
    require(len(raw) <= maximum, 'protected source grew beyond its bound')
    mode = '100755' if info.st_mode & 0o111 else '100644'
    return raw, ordinary(blob_id(raw), mode)

def validate_tree(tree):
    require(type(tree) is dict and 0 < len(tree) <= 200_000, 'complete source map required')
    for path, entry in tree.items():
        require(type(path) is str and path and not path.startswith('/') and all(part not in {'','.','..'} for part in path.split('/'))
            and not any(ord(c)<32 or ord(c)==127 for c in path), 'invalid protected source path')
        require(type(entry) is dict and set(entry)=={'mode','type','sha'}
            and {'100644':'blob','100755':'blob','120000':'blob','160000':'commit'}.get(entry['mode'])==entry['type'], 'invalid source entry')
        object_id(entry['sha'])
    return tree

def shared_platform_supported(selection, target, candidate_profile):
    """Only independently selected platform omission or the exact empty profile.

    This predicate grants no owner authority: callers must first derive selection
    from complete immutable sources and separately authenticate the target.
    """
    return (target in TARGET_PROFILES and type(selection) is dict
        and type(selection.get('include_platform')) is bool
        and candidate_profile==ordinary(TARGET_PROFILES[target])
        and (selection['include_platform'] is False or TARGET_PROFILES[target]==SHARED_PROFILE))


def actual_import_inventory(root):
    """Exact materialized import lookup, including untracked native/bytecode names."""
    root=Path(root); files={}; directories=set(); total=0
    for prefix in IMPORT_ROOTS:
        parent=root/prefix
        require(parent.is_dir() and not parent.is_symlink(), 'protected import root is unavailable')
        directories.add(prefix)
        for path in parent.rglob('*'):
            relative=path.relative_to(root).as_posix()
            require(not path.is_symlink(), 'protected import lookup contains an alias')
            if path.is_dir():
                directories.add(relative)
            else:
                raw,entry=actual_bytes(root,relative)
                total+=len(raw)
                require(len(files)<4096 and total<=16_000_000, 'protected import lookup exceeds bound')
                files[relative]=entry
    return {'files':files,'directories':sorted(directories)}


def compatibility(base, default, target, *, read_actual, actual_imports):
    """Pure finite B/D enrollment plus every actual default controller byte."""
    validate_tree(base); validate_tree(default)
    require(target in TARGET_PROFILES, 'target is not a reviewed permanent branch')
    require(base.get(PROFILE)==ordinary(TARGET_PROFILES[target]) and default.get(PROFILE)==ordinary(SHARED_PROFILE),
            'target or default platform declaration is not enrolled')
    # Every recursive requirement include is a reviewed ordinary member; a new
    # include cannot make setup read a file outside the pre-import commitment.
    seen=set(); active=set()
    def requirement(name):
        require(name in CONTROLLERS, 'requirement include is outside the reviewed graph')
        require(name not in active, 'requirement include cycle is forbidden')
        if name in seen: return
        seen.add(name); active.add(name)
        require(len(seen)<=20, 'requirement graph exceeds bound')
        raw, observed=read_actual(name)
        require(observed==base.get(name)==default.get(name), 'requirement source differs')
        for line in raw.decode('utf-8').splitlines():
            line=line.split('#',1)[0].strip()
            if not line: continue
            if line.startswith('-r '):
                relative=line[3:].strip()
                require(relative and not relative.startswith('/') and '\\' not in relative
                        and not any(ord(c)<32 or ord(c)==127 for c in relative), 'invalid requirement include')
                # Includes are relative to their declaring file. Normalize only
                # lexically; no filesystem aliases or new readers are admitted.
                parts=name.split('/')[:-1]
                for part in relative.split('/'):
                    if part in {'','.'}: continue
                    if part=='..':
                        require(parts, 'requirement include escapes root')
                        parts.pop()
                    else: parts.append(part)
                requirement('/'.join(parts))
            else:
                require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9_.+!-]*',line), 'requirement is not an exact reviewed pin')
        active.remove(name)
    requirement('tests/requirements-host.txt')
    identity = {}
    for name in CONTROLLERS:
        expected = default.get(name)
        mode='100755' if name=='tests/run-project-tests.py' else '100644'
        require(type(expected) is dict and expected['type']=='blob' and expected['mode']==mode,
                'complete default controller graph is unavailable')
        require(name==PROFILE or base.get(name)==expected, 'original base controller differs from current default')
        raw, observed = read_actual(name)
        require(observed==expected, 'actual default controller bytes differ from immutable source')
        identity[name] = {'mode':expected['mode'],'sha256':hashlib.sha256(raw).hexdigest()}
    # The isolated launcher uses only this module directory and standard-library
    # paths. Bind the entire lookup inventory, including absent/new native modules.
    def imports(tree):
        return {path:entry for path,entry in tree.items()
            if any(path==root or path.startswith(root+'/') for root in IMPORT_ROOTS)}
    before, current = imports(base), imports(default)
    require(set(before)==set(current)==set(IMPORT_MEMBERS),'protected import membership is not reviewed')
    require(before==current and all(entry['mode'] in {'100644','100755'} and entry['type']=='blob' for entry in current.values()),
            'protected Python import or negative lookup inventory changed')
    directories={str(parent) for path in current for parent in Path(path).parents
        if any(str(parent)==root or str(parent).startswith(root+'/') for root in IMPORT_ROOTS)}
    require(actual_imports=={'files':current,'directories':sorted(directories)},
            'actual import lookup differs from the immutable reviewed inventory')
    return {'schema':1,'kind':'protected-default-controller-source-v1','target':target,
            'target_profile':base[PROFILE],'controller_digest':digest(identity),
            'lookup_digest':digest(current)}

# These exact lookup files are never imported by production controllers. Their
# original bytes remain mandatory in source4; this precheck grants no result.
REUSE_LOOKUP_DATA = tuple('tools/test-evidence/'+name for name in (
    'AFFECTED_SELECTION.md', 'affected-test.py', 'attested-test.py', 'ci-integration-test.py',
    'ci-profile-test.py', 'execution-test.py', 'producer-api-test.py', 'producer-test.py',
    'qualification-producer-test.py', 'registry-test.py', 'runtime-ci-test.py', 'runtime-test.py',
    'sandbox-host-test.py', 'sandbox-test.py', 'source-admission-test.py', 'test.py', 'validate-sync-test.py'))
_REUSE_PUSH_ROLES = frozenset({'common-parent','qualify-parent','route','project-results','documentation-source'})


def reuse_compatibility(base, default, target, *, read_actual, actual_imports):
    """Authenticate current executable imports only; no original-source/PASS claim.

    Exact original seventeen bytes must subsequently be reconstructed from the
    native source4 receipt. Strict capture compatibility remains unchanged.
    """
    validate_tree(base);validate_tree(default)
    require(set(IMPORT_MEMBERS)-set(CONTROLLERS)==set(REUSE_LOOKUP_DATA),
            'nonproduction reuse lookup set is not reviewed')
    for name in REUSE_LOOKUP_DATA:
        require(all(tree.get(name,{}).get('mode')=='100644'
                    and tree[name]['type']=='blob' for tree in (base,default)),
                'reuse lookup membership, mode or type changed')
    provisional={**base,**{name:default[name] for name in REUSE_LOOKUP_DATA}}
    current=compatibility(provisional,default,target,read_actual=read_actual,actual_imports=actual_imports)
    return {**current,'kind':'protected-default-reuse-controller-precheck-v1'}


def _branch_ref(value):
    require(type(value) is str and 0 < len(value) <= 255
        and not value.startswith(('/', '-', 'refs/')) and not value.endswith(('/', '.'))
        and not any(token in value for token in ('//','..','@{'))
        and not re.search(r'[\x00-\x20\x7f~^:?*\[\\]', value)
        and all(not part.startswith('.') and not part.endswith('.lock') for part in value.split('/')),
        'invalid protected source branch ref')
    return value


def validate_base_snapshot(api, snapshot, effective_base):
    """Validate a non-authoritative event/API observation against current B.

    GitHub may retain different older base snapshots in the event and PR API.
    Neither observation replaces the independently authenticated M.parent0/ref.
    """
    object_id(snapshot); object_id(effective_base)
    if snapshot == effective_base:
        return
    value = api.get('compare/'+snapshot+'...'+effective_base+'?per_page=1')
    require(type(value) is dict and value.get('status') == 'ahead'
        and value.get('base_commit',{}).get('sha') == snapshot
        and value.get('merge_base_commit',{}).get('sha') == snapshot,
        'PR base snapshot is not an ancestor of current protected B')
    ahead, behind, total = (value.get(name) for name in ('ahead_by','behind_by','total_commits'))
    require(type(ahead) is int and ahead > 0 and type(behind) is int and behind == 0
        and type(total) is int and total == ahead, 'invalid base ancestry comparison counts')
    commits, files = value.get('commits'), value.get('files')
    require(type(commits) is list and len(commits) == 1 and type(commits[0]) is dict
        and type(files) is list and len(files) <= 300
        and all(type(item) is dict for item in files), 'incomplete bounded base ancestry comparison')
    object_id(commits[0].get('sha'))


def resolve_pr_base(api, current_pr, current_merge, event_pr=None):
    """Resolve current API/ref authority, retaining raw snapshot objects unchanged.

    Native caller/source/App/attempt authentication belongs to the invoking
    boundary. Every observation here is repeated by that boundary's bookends.
    """
    require(type(current_pr) is dict and type(current_merge) is dict
        and type(current_pr.get('base')) is dict and type(current_pr.get('head')) is dict,
            'current PR and native merge objects required')
    number = current_pr.get('number')
    require(type(number) is int and number > 0 and current_pr.get('state') == 'open',
            'current open PR unavailable')
    parents = current_merge.get('parents')
    require(type(parents) is list and len(parents) == 2 and all(type(p) is dict for p in parents),
            'native M must have exactly two ordered parents')
    base, head = (object_id(p.get('sha')) for p in parents)
    source = object_id(current_merge.get('sha'))
    target = current_pr.get('base',{}).get('ref')
    head_ref = _branch_ref(current_pr.get('head',{}).get('ref'))
    require(target in TARGET_PROFILES, 'unknown protected PR target')
    for observation in (current_pr,) if event_pr is None else (current_pr,event_pr):
        require(type(observation) is dict and type(observation.get('number')) is int and observation['number'] == number,
                'native PR number changed')
        for side, ref in (('base',target),('head',head_ref)):
            row = observation.get(side,{})
            require(type(row) is dict and row.get('ref') == ref
                and row.get('repo',{}).get('full_name') == REPOSITORY
                and type(row.get('repo',{}).get('id')) is int
                and row['repo']['id'] == REPOSITORY_ID, 'PR source repository/ref changed')
        require(observation['head'].get('sha') == head, 'current PR head changed')
        validate_base_snapshot(api, observation['base'].get('sha'), base)
    branch = api.get('branches/'+target)
    require(branch.get('name') == target and branch.get('protected') is True
        and branch.get('commit',{}).get('sha') == base, 'current protected PR base changed')
    reference = api.get('git/ref/heads/'+quote(head_ref,safe=''))
    require(reference.get('ref') == 'refs/heads/'+head_ref
        and reference.get('object',{}).get('type') == 'commit'
        and reference['object'].get('sha') == head, 'current PR branch head changed')
    return {'base':base,'head':head,'target':target,'head_ref':head_ref,'source':source}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        raise SourceUnavailable('protected source API redirects are forbidden')

class GitHubSource:
    """Fixed GET-only source metadata; no endpoint, host or credential argument."""
    def __init__(self, *, deadline=None):
        self.calls = 0
        current=time.monotonic()
        self.deadline=current+45 if deadline is None else min(current+45,deadline)
    def get(self, endpoint):
        require(type(endpoint) is str and re.fullmatch(r'(?:|pulls/[1-9][0-9]*|branches/(?:'+ '|'.join(TARGET_PROFILES)+r')|git/ref/heads/(?:[A-Za-z0-9._~-]|%[0-9A-F]{2})+|compare/[0-9a-f]{40}\.\.\.[0-9a-f]{40}\?per_page=1|git/commits/[0-9a-f]{40}|git/trees/[0-9a-f]{40}\?recursive=1|commits/refs/pull/[1-9][0-9]*/merge)',endpoint), 'unsupported protected source endpoint')
        self.calls += 1
        require(self.calls <= 24, 'protected source API budget exceeded')
        request = urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+('/'+endpoint if endpoint else ''),
            headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},method='GET')
        remaining=self.deadline-time.monotonic()
        require(remaining>0,'protected source admission deadline exceeded')
        with urllib.request.build_opener(_NoRedirect()).open(request,timeout=min(10,remaining)) as response:
            require(response.status==200 and response.geturl()==request.full_url, 'protected source API redirect/status changed')
            raw=response.read(16_000_001)
        require(len(raw)<=16_000_000 and time.monotonic()<=self.deadline,'protected source metadata exceeds byte/time bound')
        value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(SourceUnavailable('nonfinite JSON')))
        require(type(value) is dict,'protected source API object required')
        return value

def api_tree(api, revision, *, tree_reader=None):
    commit=api.get('git/commits/'+object_id(revision))
    require(commit.get('sha')==revision,'immutable source commit rebound')
    tree_id=object_id(commit.get('tree',{}).get('sha'))
    value=api.get('git/trees/'+tree_id+'?recursive=1') if tree_reader is None else tree_reader(tree_id)
    require(type(value) is dict and type(value.get('tree')) is list and len(value['tree'])<=200_000,'source inventory bound exceeded')
    require(value.get('sha')==tree_id and value.get('truncated') is False and type(value.get('tree')) is list,'incomplete immutable source tree')
    result={};seen=set()
    for row in value['tree']:
        require(type(row) is dict and type(row.get('path')) is str and row['path'] not in seen,'duplicate/malformed immutable source path')
        seen.add(row['path'])
        if row.get('type')=='tree':
            require(row.get('mode')=='040000','invalid source directory')
            continue
        result[row['path']]={key:row.get(key) for key in ('mode','type','sha')}
    return validate_tree(result)

def native(event, environment, api):
    expected={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':REPOSITORY,'GITHUB_REPOSITORY_ID':str(REPOSITORY_ID),
              'GITHUB_RUN_ATTEMPT':'1','RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24'}
    require(all(environment.get(k)==v for k,v in expected.items()),'unsupported native source invocation')
    require(type(event) is dict and event.get('repository',{}).get('full_name')==REPOSITORY
        and event.get('repository',{}).get('id')==REPOSITORY_ID, 'native event repository changed')
    repo=api.get('')
    require(repo.get('id')==REPOSITORY_ID and repo.get('full_name')==REPOSITORY and repo.get('default_branch')=='main','protected repository/default changed')
    source=object_id(environment.get('GITHUB_SHA'))
    require(environment.get('GITHUB_WORKFLOW_SHA')==source,'native caller source changed')
    if environment.get('GITHUB_EVENT_NAME')=='pull_request':
        pr=event.get('pull_request',{});number=event.get('number')
        require(type(number) is int and number>0 and pr.get('number')==number,'native PR number unavailable')
        current=api.get('pulls/'+str(number))
        require(current.get('number')==number and current.get('state')=='open','current open PR unavailable')
        target=pr.get('base',{}).get('ref')
        require(environment.get('GITHUB_BASE_REF')==target and environment.get('GITHUB_HEAD_REF')==pr.get('head',{}).get('ref')
            and environment.get('GITHUB_REF')=='refs/pull/'+str(number)+'/merge'
            and environment.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/.github/workflows/repository-checks.yml@refs/pull/'+str(number)+'/merge','native PR caller changed')
        merge=api.get('commits/refs/pull/'+str(number)+'/merge')
        require(merge.get('sha')==source, 'native M source changed')
        resolved=resolve_pr_base(api,current,merge,pr)
        base,head=resolved['base'],resolved['head']
    else:
        require(environment.get('GITHUB_EVENT_NAME')=='push' and event.get('forced') is False and event.get('deleted') is False,'unsupported protected source event')
        ref=environment.get('GITHUB_REF','');target=ref.removeprefix('refs/heads/')
        require(ref=='refs/heads/'+target and event.get('ref')==ref and event.get('after')==source,'native push source changed')
        base=object_id(event.get('before'))
        commit=api.get('git/commits/'+source)
        require(commit.get('sha')==source and type(commit.get('parents')) is list
            and len(commit['parents'])==2 and commit['parents'][0].get('sha')==base,
            'protected push is not the exact normal integration of original B')
        workflow='parent-qualification' if target in {'main','android-main','android-vr','apple-main'} else 'project-tests'
        if environment.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+DOCUMENTATION_WORKFLOW+'@'+ref:
            require(target in DOCUMENTATION_TARGETS and environment.get('GITHUB_JOB')=='documentation-source',
                    'unreviewed documentation source role')
            workflow='documentation-push-owner'
        require(environment.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/.github/workflows/'+workflow+'.yml@'+ref,'native push workflow changed')
    require(target in TARGET_PROFILES,'unknown protected target')
    branch=api.get('branches/'+target)
    require(branch.get('name')==target and branch.get('protected') is True
        and branch.get('commit',{}).get('sha')==(base if environment['GITHUB_EVENT_NAME']=='pull_request' else source),'current protected base/target changed')
    reference=api.get('git/ref/heads/main')
    require(reference.get('ref')=='refs/heads/main' and reference.get('object',{}).get('type')=='commit', 'default ref is not a commit')
    default=object_id(reference.get('object',{}).get('sha'))
    authority=api.get('branches/main')
    require(authority.get('name')=='main' and authority.get('protected') is True
        and authority.get('commit',{}).get('sha')==default,'default authority protection/source changed')
    return {'target':target,'base':base,'source':source,'default':default}

def authenticate(event, environment, api, root):
    """No repository import is permitted until this complete result succeeds."""
    context=native(event,environment,api)
    default=api_tree(api,context['default']);base=api_tree(api,context['base'])
    # Fixed native bootstrap has already committed this very stdlib-only file to B.
    # Native push consumers may import CURRENT protected controllers before
    # authenticating original source4 data. PR execution/publication and other
    # push roles retain strict original B/D admission. This grants no PASS.
    validator=(reuse_compatibility if environment.get('GITHUB_EVENT_NAME')=='push'
        and environment.get('GITHUB_JOB') in _REUSE_PUSH_ROLES else compatibility)
    result=validator(base,default,context['target'],read_actual=lambda name:actual_bytes(root,name),actual_imports=actual_import_inventory(root))
    clean_env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
    actual=subprocess.run(['/usr/bin/git','--no-replace-objects','-c','safe.directory='+str(root),'-c','core.hooksPath=/dev/null','rev-parse','--verify','HEAD'],cwd=root,env=clean_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=10).stdout.decode().strip()
    require(actual==context['default'],'actual controller checkout is not current defaultD')
    require(native(event,environment,api)==context,'native base/default source changed during pre-import admission')
    return {**result,**context}
