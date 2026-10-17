#!/usr/bin/env python3
"""Finite source guard tests with fake native/API facts, never host qualification."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import source_admission as S

ROOT=Path(__file__).resolve().parents[2]

class SourceFixture:
    def setUp(self):
        self.bodies={name:b'raise AssertionError("repository code must not execute during source admission")\n'
                     for name in {*S.CONTROLLERS,*S.IMPORT_MEMBERS}}
        for name in ('tests/requirements-host.txt','tests/requirements-repository.txt','tools/sbom/requirements-validation.txt'):
            self.bodies[name]=b'pytest==8.4.2\n'
        # These fake API facts model D/main and an Apple target. The profile
        # must not depend on the real branch executing this shared test suite.
        self.bodies[S.PROFILE]=(json.dumps({'schema':1,'platform':'shared','suites':[]},indent=2)+'\n').encode()
        self.assertEqual(S.blob_id(self.bodies[S.PROFILE]),S.SHARED_PROFILE)
        self.bodies[S.SELF]=Path(S.__file__).read_bytes()
        self.default={name:S.ordinary(S.blob_id(raw),'100755' if name=='tests/run-project-tests.py' else '100644')
                      for name,raw in self.bodies.items()}
        self.base=deepcopy(self.default)
        self.target='apple-ios'
        self.base_id='a'*40;self.default_id='d'*40;self.head_id='c'*40;self.merge_id='e'*40
        self.event={'number':23,'repository':{'full_name':S.REPOSITORY,'id':S.REPOSITORY_ID},'pull_request':{
            'number':23,'base':{'ref':self.target,'sha':self.base_id,'repo':{'full_name':S.REPOSITORY,'id':S.REPOSITORY_ID}},
            'head':{'ref':'fix/ios/source-guard','sha':self.head_id,'repo':{'full_name':S.REPOSITORY,'id':S.REPOSITORY_ID}}}}
        self.env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':S.REPOSITORY,'GITHUB_REPOSITORY_ID':str(S.REPOSITORY_ID),
            'GITHUB_RUN_ATTEMPT':'1','RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24','GITHUB_EVENT_NAME':'pull_request',
            'GITHUB_SHA':self.merge_id,'GITHUB_WORKFLOW_SHA':self.merge_id,'GITHUB_BASE_REF':self.target,
            'GITHUB_HEAD_REF':self.event['pull_request']['head']['ref'],'GITHUB_REF':'refs/pull/23/merge',
            'GITHUB_WORKFLOW_REF':S.REPOSITORY+'/.github/workflows/repository-checks.yml@refs/pull/23/merge'}
    def imports(self, tree=None):
        tree=self.default if tree is None else tree
        files={path:entry for path,entry in tree.items() if any(path==root or path.startswith(root+'/') for root in S.IMPORT_ROOTS)}
        directories={str(p) for path in files for p in Path(path).parents
            if any(str(p)==root or str(p).startswith(root+'/') for root in S.IMPORT_ROOTS)}
        return {'files':files,'directories':sorted(directories)}
    def read(self,name):
        return self.bodies[name],self.default[name]
    def admit(self, **kwargs):
        return S.compatibility(kwargs.get('base',self.base),kwargs.get('default',self.default),kwargs.get('target',self.target),
            read_actual=kwargs.get('read_actual',self.read),actual_imports=kwargs.get('actual_imports',self.imports()))
    def put(self,name,raw,mode='100644'):
        self.bodies[name]=raw
        self.default[name]=S.ordinary(S.blob_id(raw),mode)
        self.base[name]=deepcopy(self.default[name])
    def api(self):
        case=self
        class Api:
            def __init__(self): self.calls=[]
            def get(self,endpoint):
                self.calls.append(endpoint)
                if endpoint=='': value={'full_name':S.REPOSITORY,'id':S.REPOSITORY_ID,'default_branch':'main'}
                elif endpoint=='pulls/23': value={**case.event['pull_request'],'state':'open'}
                elif endpoint=='commits/refs/pull/23/merge': value={'sha':case.merge_id,'parents':[{'sha':case.base_id},{'sha':case.head_id}]}
                elif endpoint=='git/ref/heads/'+S.quote(case.event['pull_request']['head']['ref'],safe=''): value={'ref':'refs/heads/'+case.event['pull_request']['head']['ref'],'object':{'type':'commit','sha':case.head_id}}
                elif endpoint=='git/ref/heads/main': value={'ref':'refs/heads/main','object':{'type':'commit','sha':case.default_id}}
                elif endpoint.startswith('branches/'):
                    name=endpoint.removeprefix('branches/')
                    value={'name':name,'protected':True,'commit':{'sha':case.default_id if name=='main' else case.base_id}}
                elif endpoint.startswith('git/commits/'):
                    value={'sha':endpoint.rsplit('/',1)[1],'tree':{'sha':'1'*40 if endpoint.endswith(case.base_id) else '2'*40}}
                elif endpoint.startswith('git/trees/'):
                    tree=case.base if '1'*40 in endpoint else case.default
                    value={'sha':'1'*40 if tree is case.base else '2'*40,'truncated':False,
                           'tree':[{'path':path,**entry} for path,entry in tree.items()]}
                else: raise AssertionError('unexpected source API endpoint: '+endpoint)
                return deepcopy(value)
        return Api()

class SourceAdmissionTests(SourceFixture,unittest.TestCase):
    def test_repository_root_transport_has_no_slash_and_relative_requests_stay_exact(self):
        calls=[]
        class Response:
            status=200
            def __init__(self,url): self.url=url
            def geturl(self): return self.url
            def read(self,maximum):
                self_case.assertEqual(maximum,16_000_001)
                return b'{"ok":true}'
            def __enter__(self): return self
            def __exit__(self,*args): return False
        self_case=self
        def opened(request,timeout):
            calls.append(request.full_url)
            self.assertEqual(request.get_method(),'GET')
            self.assertEqual({key.lower():value for key,value in request.header_items()},
                {'authorization':'Bearer fake-source-token','accept':'application/vnd.github+json',
                 'x-github-api-version':'2022-11-28'})
            self.assertEqual(timeout,10)
            return Response(request.full_url)
        with patch.dict(os.environ,{'GH_TOKEN':'fake-source-token'},clear=True), \
             patch.object(S.time,'monotonic',return_value=100), \
             patch.object(S.urllib.request,'urlopen',side_effect=AssertionError('live source I/O forbidden')), \
             patch.object(S.urllib.request,'build_opener',return_value=SimpleNamespace(open=opened)) as builder:
            api=S.GitHubSource()
            self.assertEqual(api.get(''),{'ok':True})
            self.assertEqual(api.get('pulls/23'),{'ok':True})
            self.assertEqual(api.get('git/ref/heads/main'),{'ok':True})
            self.assertEqual(api.calls,3)
            self.assertTrue(all(type(call.args[0]) is S._NoRedirect for call in builder.call_args_list))
        self.assertEqual(calls,['https://api.github.com/repos/noah-l-frank/overte',
            'https://api.github.com/repos/noah-l-frank/overte/pulls/23',
            'https://api.github.com/repos/noah-l-frank/overte/git/ref/heads/main'])

    def test_root_url_fix_keeps_endpoint_redirect_and_status_rejections(self):
        root_url='https://api.github.com/repos/noah-l-frank/overte'
        class Response:
            def __init__(self,status,url): self.status=status;self.url=url
            def geturl(self): return self.url
            def read(self,maximum): return b'{}'
            def __enter__(self): return self
            def __exit__(self,*args): return False
        with patch.dict(os.environ,{'GH_TOKEN':'fake-source-token'},clear=True), \
             patch.object(S.urllib.request,'urlopen',side_effect=AssertionError('live source I/O forbidden')):
            for endpoint in ('/','../pulls/23','pulls/0','https://api.github.com/repos/noah-l-frank/overte'):
                with self.subTest(endpoint=endpoint), \
                     patch.object(S.urllib.request,'build_opener') as builder:
                    with self.assertRaises(S.SourceUnavailable): S.GitHubSource().get(endpoint)
                    builder.assert_not_called()
            for status,url in ((200,root_url+'/'),(200,'https://example.invalid/'),(301,root_url),(404,root_url)):
                with self.subTest(status=status,url=url), \
                     patch.object(S.urllib.request,'build_opener',return_value=SimpleNamespace(
                         open=lambda request,timeout:Response(status,url))):
                    with self.assertRaises(S.SourceUnavailable): S.GitHubSource().get('')
            with self.assertRaises(S.SourceUnavailable):
                S._NoRedirect().redirect_request(None,None,301,'Moved',{},root_url+'/')

    def test_reuse_precheck_preserves_all_original_data_without_relaxing_capture(self):
        for name in S.REUSE_LOOKUP_DATA:
            self.base[name]=S.ordinary('a'*40)
        before=deepcopy(self.base);default=deepcopy(self.default)
        with self.assertRaises(S.SourceUnavailable):self.admit()
        value=S.reuse_compatibility(self.base,self.default,self.target,
            read_actual=self.read,actual_imports=self.imports())
        self.assertEqual(value['kind'],'protected-default-reuse-controller-precheck-v1')
        self.assertEqual(self.base,before);self.assertEqual(self.default,default)
        self.assertEqual(set(S.REUSE_LOOKUP_DATA),set(S.IMPORT_MEMBERS)-set(S.CONTROLLERS))
        for field in ('verified','results','environment','receipt','qualification','expires_at'):
            self.assertNotIn(field,value)

    def test_reuse_precheck_rejects_changed_executables_and_lookup_shapes(self):
        original=deepcopy(self.base)
        for name in S.CONTROLLERS:
            self.base=deepcopy(original);self.base[name]['sha']='a'*40
            with self.subTest(controller=name),self.assertRaises(S.SourceUnavailable):
                S.reuse_compatibility(self.base,self.default,self.target,
                    read_actual=self.read,actual_imports=self.imports())
        self.base=deepcopy(original)
        for side in ('base','default'):
            for change in ('mode','alias','gitlink','missing','new-member','local-drift'):
                base,default=deepcopy(self.base),deepcopy(self.default)
                tree=base if side=='base' else default;name=S.REUSE_LOOKUP_DATA[0]
                observed=deepcopy(self.imports())
                if change=='mode':tree[name]['mode']='100755'
                elif change=='alias':tree[name]['mode']='120000'
                elif change=='gitlink':tree[name].update(mode='160000',type='commit')
                elif change=='missing':tree.pop(name)
                elif change=='new-member':tree['tools/test-evidence/shadow.py']=S.ordinary('a'*40)
                else:observed['files'][name]['sha']='b'*40
                with self.subTest(side=side,change=change),self.assertRaises(S.SourceUnavailable):
                    S.reuse_compatibility(base,default,self.target,
                        read_actual=self.read,actual_imports=observed)

    def test_only_native_push_consumer_roles_select_reuse_precheck(self):
        context={'default':self.default_id,'base':self.base_id,'source':self.merge_id,'target':self.target}
        process=SimpleNamespace(stdout=(self.default_id+'\n').encode())
        for event in ('pull_request','push'):
            for job in (*sorted(S._REUSE_PUSH_ROLES),'project-tests','producer-publication','platform-tests','unknown'):
                env={**self.env,'GITHUB_EVENT_NAME':event,'GITHUB_JOB':job}
                with self.subTest(event=event,job=job),patch.object(S,'native',return_value=context), \
                     patch.object(S,'api_tree',side_effect=[self.default,self.base]), \
                     patch.object(S,'compatibility',return_value={'kind':'strict'}) as strict, \
                     patch.object(S,'reuse_compatibility',return_value={'kind':'precheck'}) as reuse, \
                     patch.object(S.subprocess,'run',return_value=process):
                    value=S.authenticate(self.event,env,self.api(),ROOT)
                    selected=event=='push' and job in S._REUSE_PUSH_ROLES
                    self.assertEqual(value['kind'],'precheck' if selected else 'strict')
                    self.assertEqual(reuse.call_count,int(selected));self.assertEqual(strict.call_count,int(not selected))

    def test_fixed_graph_matches_actual_complete_producer_controller(self):
        import producer_workflow as P
        self.assertEqual(set(S.CONTROLLERS),set(P.controller_sources(P._host_policy())))
        self.assertEqual(len(S.TARGET_PROFILES),7)
        self.assertEqual(len(set(S.TARGET_PROFILES.values())),3)

    def test_actual_native_push_preimport_admits_only_current_controllers_before_source4_lookup(self):
        for name in S.REUSE_LOOKUP_DATA:self.base[name]=S.ordinary('a'*40)
        env={**self.env,'GITHUB_EVENT_NAME':'push','GITHUB_JOB':'route',
            'GITHUB_REF':'refs/heads/'+self.target,
            'GITHUB_WORKFLOW_REF':S.REPOSITORY+'/.github/workflows/project-tests.yml@refs/heads/'+self.target}
        event={'repository':self.event['repository'],'ref':env['GITHUB_REF'],'before':self.base_id,
            'after':self.merge_id,'forced':False,'deleted':False}
        api=self.api();get=api.get
        def native_get(endpoint):
            if endpoint=='git/commits/'+self.merge_id:
                return {'sha':self.merge_id,'tree':{'sha':'3'*40},
                    'parents':[{'sha':self.base_id},{'sha':self.head_id}]}
            value=get(endpoint)
            if endpoint=='branches/'+self.target:value['commit']['sha']=self.merge_id
            return value
        api.get=native_get
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw in self.bodies.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                path.chmod(0o755 if self.default[name]['mode']=='100755' else 0o644)
            process=SimpleNamespace(stdout=(self.default_id+'\n').encode())
            with patch.object(S.subprocess,'run',return_value=process):
                value=S.authenticate(event,env,api,root)
                self.assertEqual(value['kind'],'protected-default-reuse-controller-precheck-v1')
                self.assertEqual(value['source'],self.merge_id)
                for role in ('project-tests','producer-publication','platform-tests'):
                    with self.subTest(role=role),self.assertRaises(S.SourceUnavailable):
                        S.authenticate(event,{**env,'GITHUB_JOB':role},api,root)
                path=root/'tools/test-evidence/runtime.py';path.write_bytes(b'changed current controller\n')
                with self.assertRaises(S.SourceUnavailable):S.authenticate(event,env,api,root)
    def test_controller_identity_excludes_only_fixed_import_projection_members(self):
        import producer_workflow as P
        import postmerge
        reviewed = set(S.CONTROLLERS)
        projected = set(P.shared.sources())
        import_only = set(S.IMPORT_MEMBERS) - reviewed
        policy = P._host_policy()
        self.assertEqual(len(reviewed), 71)
        self.assertEqual(len(projected), 88)
        self.assertEqual(len(import_only), 17)
        self.assertEqual(projected - reviewed, import_only)
        self.assertEqual(set(P.controller_sources(policy)), reviewed)
        for extra in ('tools/test-evidence/unreviewed-controller.py',
                      'tools/repository-checks/unreviewed-controller.py'):
            with self.subTest(extra=extra), patch.object(P.shared, 'sources',
                    return_value=sorted(projected | {extra})):
                self.assertEqual(set(P.controller_sources(policy)), reviewed | {extra})
                with self.assertRaisesRegex(postmerge.A.ApiError,
                        'integrated controller graph is not independently reviewed'):
                    postmerge.integrated_controller(policy, self.base, self.base,
                        self.default, self.target, ROOT)

    def test_all_seven_exact_enrollments_hash_actual_D_not_android_B(self):
        import producer as P
        expected=P.digest({name:{'mode':entry['mode'],'sha256':hashlib.sha256(self.bodies[name]).hexdigest()}
                           for name,entry in self.default.items() if name in S.CONTROLLERS})
        for target,oid in S.TARGET_PROFILES.items():
            with self.subTest(target=target):
                base=deepcopy(self.base);base[S.PROFILE]=S.ordinary(oid)
                result=self.admit(base=base,target=target)
                self.assertEqual(result['controller_digest'],expected)
                self.assertEqual(result['target_profile'],base[S.PROFILE])
        self.assertNotIn('original_default_commit',result)
    def test_every_controller_member_is_mandatory_ordinary_and_unchanged(self):
        for name in S.CONTROLLERS:
            for kind in ('changed','removed','executable','alias'):
                if name=='tests/run-project-tests.py' and kind=='executable': continue
                with self.subTest(name=name,kind=kind):
                    base=deepcopy(self.base)
                    if kind=='changed': base[name]['sha']='f'*40
                    elif kind=='removed': del base[name]
                    elif kind=='executable': base[name]['mode']='100755'
                    else: base[name]={'mode':'120000','type':'blob','sha':'f'*40}
                    with self.assertRaises(S.SourceUnavailable): self.admit(base=base)
    def test_unknown_profiles_modes_and_neighbors_cannot_be_enrolled(self):
        for target,entry in [('other',self.base[S.PROFILE]),(self.target,S.ordinary('f'*40)),
                             (self.target,S.ordinary(S.SHARED_PROFILE,'100755'))]:
            with self.subTest(target=target,entry=entry):
                base=deepcopy(self.base);base[S.PROFILE]=entry
                with self.assertRaises(S.SourceUnavailable): self.admit(base=base,target=target)
        default=deepcopy(self.default);default[S.PROFILE]=S.ordinary(S.TARGET_PROFILES['android-main'])
        with self.assertRaises(S.SourceUnavailable): self.admit(default=default)
    def test_import_membership_bytes_aliases_untracked_and_empty_directories_are_bound(self):
        path='tools/test-evidence/shadow.so'
        for side in ('base','default'):
            changed=deepcopy(self.base);changed[path]=S.ordinary('f'*40)
            with self.assertRaises(S.SourceUnavailable): self.admit(**{side:changed})
        actual=deepcopy(self.imports());actual['files'][path]=S.ordinary('f'*40)
        with self.assertRaises(S.SourceUnavailable): self.admit(actual_imports=actual)
        actual=deepcopy(self.imports());actual['directories'].append('tools/test-evidence/namespace')
        with self.assertRaises(S.SourceUnavailable): self.admit(actual_imports=actual)
        self.put(path,b'not executed')
        with self.assertRaises(S.SourceUnavailable): self.admit()
        self.base[path]['mode']=self.default[path]['mode']='120000'
        with self.assertRaises(S.SourceUnavailable): self.admit()
    def test_changed_actual_byte_or_mode_cannot_hide_behind_same_API_map(self):
        for body,mode in ((b'changed','100644'),(self.bodies[S.SELF],'100755')):
            def read(name):
                return (body,S.ordinary(S.blob_id(body),mode)) if name==S.SELF else self.read(name)
            with self.assertRaises(S.SourceUnavailable): self.admit(read_actual=read)
    def test_recursive_requirement_escape_new_reader_and_unpinned_install_are_rejected(self):
        requirements=('tests/requirements-host.txt','tests/requirements-repository.txt','tools/sbom/requirements-validation.txt')
        for name in requirements:
            self.put(name,(ROOT/name).read_bytes())
        observed=[]
        def read(name):
            observed.append(name)
            return self.read(name)
        self.assertEqual(self.admit(read_actual=read)['target'],self.target)
        self.assertTrue(set(requirements).issubset(observed))
        for raw in (b'-r ../outside.txt\n',b'-r new-extra.txt\n',b'-r /tools/sbom/requirements-validation.txt\n',
                    b'-r ../../tools/sbom/requirements-validation.txt\n',b'pytest>=8\n',
                    b'--extra-index-url https://example.invalid\n',b'-r requirements-host.txt\n'):
            with self.subTest(raw=raw):
                self.put('tests/requirements-host.txt',raw)
                with self.assertRaises(S.SourceUnavailable): self.admit()
        for name in requirements:
            self.put(name,(ROOT/name).read_bytes())
        self.put('tests/requirements-repository.txt',b'-r requirements-host.txt\n')
        with self.assertRaises(S.SourceUnavailable): self.admit()
        self.put('tests/requirements-repository.txt',(ROOT/'tests/requirements-repository.txt').read_bytes())
        for mode in ('100755','120000'):
            with self.subTest(included_mode=mode):
                self.base['tools/sbom/requirements-validation.txt']['mode']=mode
                with self.assertRaises(S.SourceUnavailable): self.admit()
    def test_integrated_controller_reconstructs_actual_D_bytes_and_rejects_any_S_drift(self):
        import postmerge
        policy=postmerge.producer._host_policy()
        target='android-phone'
        base=deepcopy(self.base);base[S.PROFILE]=S.ordinary(S.TARGET_PROFILES[target])
        current=deepcopy(base)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,raw in self.bodies.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                path.chmod(0o755 if self.default[name]['mode']=='100755' else 0o644)
            expected=self.admit(base=base,target=target)['controller_digest']
            self.assertEqual(postmerge.integrated_controller(policy,base,current,self.default,target,root),expected)
            for name in (S.SELF,'tools/test-evidence/runtime.py',S.PROFILE):
                with self.subTest(name=name):
                    changed=deepcopy(current);changed[name]['sha']='f'*40
                    with self.assertRaises(S.SourceUnavailable):
                        postmerge.integrated_controller(policy,base,changed,self.default,target,root)
    def test_isolated_launcher_excludes_cwd_and_script_parent_import_shadowing(self):
        launcher='import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name="__main__")'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);closed=root/'closed';script_parent=root/'scripts';cwd=root/'candidate'
            for path in (closed,script_parent,cwd): path.mkdir()
            (closed/'bound.py').write_text('VALUE="bound"\n')
            script=script_parent/'controller.py'
            script.write_text('import bound;print(bound.VALUE)\n')
            command=[sys.executable,'-I','-S','-B','-c',launcher,str(closed),str(script)]
            result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=5)
            self.assertEqual((result.returncode,result.stdout),(0,'bound\n'))
            (cwd/'shadow.py').write_text('raise AssertionError("candidate import executed")\n')
            (script_parent/'shadow.py').write_text('raise AssertionError("unbound script-parent import executed")\n')
            script.write_text('import shadow\n')
            result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('ModuleNotFoundError',result.stderr)
            self.assertNotIn('AssertionError',result.stderr)
    def test_native_all_seven_PR_targets_keep_M_and_D_separate(self):
        for target in S.TARGET_PROFILES:
            with self.subTest(target=target):
                self.target=target;self.event['pull_request']['base']['ref']=target;self.env['GITHUB_BASE_REF']=target
                # Current main base and default are necessarily the same ref.
                if target=='main': self.base_id=self.default_id;self.event['pull_request']['base']['sha']=self.base_id
                else: self.base_id='a'*40;self.event['pull_request']['base']['sha']=self.base_id
                context=S.native(self.event,self.env,self.api())
                self.assertEqual(context['source'],self.merge_id)
                self.assertEqual(context['default'],self.default_id)
                self.assertEqual(context['base'],self.base_id)
    def test_source_failure_after_execution_cannot_be_reclassified_as_preexecution_fallback(self):
        import producer_workflow as P
        binding={'fixture':'binding'};refs={'fixture':'refs'}
        context={'number':23,'binding':binding,'refs':refs,'source_context':{'fixture':'source'}}
        adapter=SimpleNamespace(current=lambda number:(binding,refs))
        with patch.object(P,'_host_policy',return_value=object()),patch.object(P,'protected_source_context',side_effect=P.PreExecutionUnavailable('changed')):
            with self.assertRaises(P.host.Unavailable) as raised: P._bookend(context,adapter)
            self.assertNotIsInstance(raised.exception,P.PreExecutionUnavailable)
            with self.assertRaises(P.PreExecutionUnavailable): P._bookend(context,adapter,preexecution=True)
    def test_actual_producer_and_push_contexts_are_finite_seven_not_arbitrary_refs(self):
        import producer_workflow as P
        import postmerge
        for target in S.TARGET_PROFILES:
            with self.subTest(target=target):
                env={**self.env,'GITHUB_BASE_REF':target,'GITHUB_RUN_ID':'77'}
                self.assertEqual(P._native(env),(23,77))
                parent=target in {'main','android-main','android-vr','apple-main'}
                workflow='parent-qualification' if parent else 'project-tests'
                push={**env,'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+target,
                    'GITHUB_WORKFLOW_REF':S.REPOSITORY+'/.github/workflows/'+workflow+'.yml@refs/heads/'+target,
                    'GITHUB_JOB':'qualify-parent' if parent else 'route'}
                event={'repository':self.event['repository'],'ref':push['GITHUB_REF'],'after':self.merge_id,'forced':False,'deleted':False}
                self.assertEqual(postmerge._native(event,push),(self.merge_id,77))
                with self.assertRaises(Exception): postmerge._native(event,{**push,'GITHUB_JOB':'unknown'})
        with self.assertRaises(Exception): P._native({**self.env,'GITHUB_BASE_REF':'topic','GITHUB_RUN_ID':'77'})
    def test_platform_true_android_thirteen_or_nineteen_always_keep_legacy_execution(self):
        for target,oid in S.TARGET_PROFILES.items():
            with self.subTest(target=target):
                entry=S.ordinary(oid)
                self.assertTrue(S.shared_platform_supported({'include_platform':False},target,entry))
                self.assertEqual(S.shared_platform_supported({'include_platform':True},target,entry),oid==S.SHARED_PROFILE)
                for bad in (None,0,1,'false'):
                    self.assertFalse(S.shared_platform_supported({'include_platform':bad},target,entry))
                self.assertFalse(S.shared_platform_supported({'include_platform':False},target,S.ordinary('f'*40)))
    def test_native_foreign_unknown_unprotected_or_moved_sources_reject(self):
        for change in ('foreign','unknown','wrong-M','wrong-parents','unprotected','default-unprotected'):
            with self.subTest(change=change):
                event=deepcopy(self.event);env=dict(self.env);api=self.api();get=api.get
                if change=='foreign': event['pull_request']['head']['repo']['id']=99
                if change=='unknown': event['pull_request']['base']['ref']='topic';env['GITHUB_BASE_REF']='topic'
                if change=='wrong-M': env['GITHUB_SHA']='f'*40;env['GITHUB_WORKFLOW_SHA']='f'*40
                if change=='wrong-parents':
                    def mutate(endpoint):
                        value=get(endpoint)
                        if endpoint.startswith('commits/refs/'): value['parents'].reverse()
                        return value
                    api.get=mutate
                if 'unprotected' in change:
                    def mutate(endpoint):
                        value=get(endpoint)
                        if endpoint=='branches/'+('main' if change=='default-unprotected' else self.target): value['protected']=False
                        return value
                    api.get=mutate
                with self.assertRaises(S.SourceUnavailable): S.native(event,env,api)
    def test_complete_api_inventory_rejects_rebound_truncated_duplicate_and_nonordinary_data(self):
        for kind in ('rebound','truncated','duplicate','bad-mode'):
            api=self.api();get=api.get
            def mutate(endpoint):
                value=get(endpoint)
                if endpoint.startswith('git/trees/'):
                    if kind=='rebound': value['sha']='f'*40
                    if kind=='truncated': value['truncated']=True
                    if kind=='duplicate': value['tree'].append(value['tree'][0])
                    if kind=='bad-mode': value['tree'][0]['mode']='777777'
                return value
            api.get=mutate
            with self.subTest(kind=kind),self.assertRaises(S.SourceUnavailable): S.api_tree(api,self.base_id)
    def test_actual_materialized_lookup_rejects_alias_and_unknown_bytecode(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);parent=root/S.IMPORT_ROOTS[0];parent.mkdir(parents=True)
            path=parent/'module.py';path.write_bytes(b'x=1\n')
            self.assertEqual(set(S.actual_import_inventory(root)['files']),{'tools/test-evidence/module.py'})
            (parent/'module.pyc').write_bytes(b'extra')
            self.assertIn('tools/test-evidence/module.pyc',S.actual_import_inventory(root)['files'])
            (parent/'alias.py').symlink_to(path)
            with self.assertRaises(S.SourceUnavailable): S.actual_import_inventory(root)

class BootstrapTests(SourceFixture,unittest.TestCase):
    def scripts(self):
        import yaml
        scripts=[]
        for name in ('protected-project-tests','parent-qualification'):
            value=yaml.safe_load((ROOT/'tools/repository-checks/workflows/producers'/ (name+'.yml')).read_text())
            for job in value['jobs'].values():
                for step in job.get('steps',[]):
                    if step.get('id')=='protected-source':
                        lines=step['run'].splitlines();self.assertIn('-I -S -B',lines[0])
                        scripts.append('\n'.join(lines[1:-1])+'\n')
        value=yaml.safe_load((ROOT/S.DOCUMENTATION_WORKFLOW).read_text())
        step=next(item for item in value['jobs']['documentation-source']['steps'] if item.get('id')=='protected-source')
        lines=step['run'].splitlines();self.assertIn('-I -S -B',lines[0])
        scripts.append('\n'.join(lines[1:-1])+'\n')
        self.assertEqual(len(scripts),5)
        self.assertEqual(len(set(scripts)),1)
        return scripts[0]
    def execute_bootstrap(self, *, changed_helper=False, changed_controller=False, drift=False):
        script=self.scripts();api=self.api()
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp);root=parent/'trusted'
            for name,raw in self.bodies.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                path.chmod(0o755 if self.default[name]['mode']=='100755' else 0o644)
            if changed_helper: (root/S.SELF).write_text('raise AssertionError("unbound helper executed")\n')
            if changed_controller: (root/'tools/test-evidence/runtime.py').write_text('raise AssertionError("changed module executed")\n')
            event=parent/'event.json';event.write_text(json.dumps(self.event));output=parent/'output'
            environment={**self.env,'GITHUB_EVENT_PATH':str(event),'GITHUB_OUTPUT':str(output),'GH_TOKEN':'fake-source-token'}
            class Response:
                status=200
                def __init__(self,url,raw): self.url=url;self.raw=raw
                def geturl(self): return self.url
                def read(self,maximum): return self.raw[:maximum]
                def __enter__(self): return self
                def __exit__(self,*args): return False
            def urlopen(request,timeout):
                prefix='https://api.github.com/repos/'+S.REPOSITORY+'/'
                if request.full_url==prefix[:-1]:
                    endpoint=''
                else:
                    self.assertTrue(request.full_url.startswith(prefix))
                    endpoint=request.full_url.removeprefix(prefix)
                self.assertEqual(request.method,'GET')
                value=api.get(endpoint)
                if drift and endpoint=='git/ref/heads/main' and api.calls.count(endpoint)>1:
                    value['object']['sha']='f'*40
                return Response(request.full_url,json.dumps(value).encode())
            before=Path.cwd()
            try:
                os.chdir(parent)
                with patch.dict(os.environ,environment,clear=True),patch('urllib.request.urlopen',side_effect=AssertionError('live source I/O forbidden')),\
                     patch('urllib.request.build_opener',return_value=SimpleNamespace(open=urlopen)),\
                     patch('subprocess.run',return_value=SimpleNamespace(stdout=(self.default_id+'\n').encode())),patch('sys.stdout',new=io.StringIO()):
                    exec(compile(script,'fixed-native-recipe','exec'),{'__name__':'__main__'})
            finally: os.chdir(before)
            return output.read_text()
    def test_bootstrap_validates_all_source_without_importing_any_controller(self):
        self.assertEqual(self.execute_bootstrap(),'admitted=true\n')
    def test_bootstrap_default_source_drift_cannot_admit_after_the_initial_snapshot(self):
        self.assertEqual(self.execute_bootstrap(drift=True),'admitted=false\n')
    def test_bootstrap_rejects_changed_helper_before_exec_and_changed_controller_before_import(self):
        self.assertEqual(self.execute_bootstrap(changed_helper=True),'admitted=false\n')
        self.assertEqual(self.execute_bootstrap(changed_controller=True),'admitted=false\n')

class EffectiveBaseBootstrapTests(BootstrapTests):
    def scripts(self):
        import yaml
        path=ROOT/'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml'
        value=yaml.safe_load(path.read_text());scripts=[]
        for job in value['jobs'].values():
            for step in job.get('steps',[]):
                if step.get('id')=='protected-source':
                    lines=step['run'].splitlines();self.assertIn('-I -S -B',lines[0])
                    scripts.append('\n'.join(lines[1:-1])+'\n')
        self.assertEqual(len(scripts),5);self.assertEqual(len(set(scripts)),1)
        return scripts[0]

    def api(self):
        api=super().api();original=api.get
        def get(endpoint):
            if endpoint.startswith('compare/'):
                api.calls.append(endpoint)
                snapshot=endpoint.split('/',1)[1].split('...',1)[0]
                return {'status':'ahead','ahead_by':40,'behind_by':0,'total_commits':40,
                    'base_commit':{'sha':snapshot},'merge_base_commit':{'sha':snapshot},
                    'commits':[{'sha':'3'*40}],'files':[]}
            return original(endpoint)
        api.get=get
        return api

    def test_future_native_bootstrap_resolves_actual_base_before_loading_guard(self):
        self.event['pull_request']['base']['sha']='1'*40
        self.assertEqual(self.execute_bootstrap(),'admitted=true\n')
        self.assertEqual(self.execute_bootstrap(changed_helper=True),'admitted=false\n')
        self.assertEqual(self.execute_bootstrap(changed_controller=True),'admitted=false\n')
        self.assertEqual(self.execute_bootstrap(drift=True),'admitted=false\n')

class DocumentationSourceTests(SourceFixture,unittest.TestCase):
    def test_fixed_documentation_native_role_rejects_unknown_target_job_or_source(self):
        import postmerge
        self.assertEqual(set(S.DOCUMENTATION_TARGETS),set(postmerge.A.DOCUMENTATION_PUSH_BRANCHES))
        self.assertEqual(S.DOCUMENTATION_WORKFLOW,postmerge.A.DOCUMENTATION_PUSH_WORKFLOW)
        for target in S.DOCUMENTATION_TARGETS:
            event={'repository':self.event['repository'],'ref':'refs/heads/'+target,
                'before':self.base_id,'after':self.merge_id,'forced':False,'deleted':False}
            env={**self.env,'GITHUB_EVENT_NAME':'push','GITHUB_JOB':'documentation-source','GITHUB_RUN_ID':'500',
                'GITHUB_REF':event['ref'],'GITHUB_WORKFLOW_REF':S.REPOSITORY+'/'+S.DOCUMENTATION_WORKFLOW+'@'+event['ref']}
            api=self.api();get=api.get
            def read(endpoint):
                value=get(endpoint)
                if endpoint=='branches/'+target: value['commit']['sha']=self.merge_id
                if target=='main' and endpoint=='git/ref/heads/main': value['object']['sha']=self.merge_id
                if endpoint=='git/commits/'+self.merge_id:
                    value['parents']=[{'sha':self.base_id},{'sha':self.head_id}]
                return value
            api.get=read
            with self.subTest(target=target):
                self.assertEqual(S.native(event,env,api)['source'],self.merge_id)
                self.assertEqual(postmerge._native(event,env),(self.merge_id,500))
                for changed in ({'GITHUB_JOB':'documentation'}, {'GITHUB_WORKFLOW_SHA':'f'*40},
                                {'GITHUB_WORKFLOW_REF':env['GITHUB_WORKFLOW_REF'].replace('owner.yml','other.yml')}):
                    with self.subTest(changed=changed),self.assertRaises(Exception):
                        postmerge._native(event,{**env,**changed})
        env={**env,'GITHUB_REF':'refs/heads/android-main','GITHUB_WORKFLOW_REF':
            S.REPOSITORY+'/'+S.DOCUMENTATION_WORKFLOW+'@refs/heads/android-main'}
        with self.assertRaises(Exception): postmerge._native({**event,'ref':'refs/heads/android-main'},env)

    def test_documentation_wrapper_is_mandatory_source_before_any_import(self):
        self.assertEqual(self.admit()['target'],self.target)
        for kind in ('missing','changed','executable','alias'):
            tree=deepcopy(self.base)
            if kind=='missing': del tree[S.DOCUMENTATION_WORKFLOW]
            elif kind=='changed': tree[S.DOCUMENTATION_WORKFLOW]['sha']='f'*40
            else: tree[S.DOCUMENTATION_WORKFLOW]['mode']='100755' if kind=='executable' else '120000'
            with self.subTest(kind=kind),self.assertRaises(S.SourceUnavailable): self.admit(base=tree)

    def test_push_wrapper_keeps_reusable_contents_only_and_requires_explicit_fallback(self):
        import yaml
        old=yaml.safe_load((ROOT/'.github/workflows/documentation-checks.yml').read_text())
        wrapper=yaml.safe_load((ROOT/S.DOCUMENTATION_WORKFLOW).read_text())
        events=lambda value:value.get('on',value.get(True))
        self.assertNotIn('push',events(old));self.assertIn('workflow_call',events(old))
        self.assertEqual(old['permissions'],{'contents':'read'})
        self.assertEqual([step['run'] for step in old['jobs']['documentation']['steps'] if 'run' in step],
            ['python3 tests/documentation-test.py','python3 tests/check-documentation.py --all',
             'python3 tools/repository-policy/check.py'])
        self.assertEqual(set(events(wrapper)),{'push'})
        self.assertEqual(set(events(wrapper)['push']['branches']),S.DOCUMENTATION_TARGETS)
        jobs=wrapper['jobs'];source=jobs['documentation-source'];fallback=jobs['documentation']
        self.assertEqual(source['permissions'],dict.fromkeys(('contents','actions','pull-requests','checks'),'read'))
        self.assertEqual(fallback['permissions'],{'contents':'read'})
        self.assertEqual(fallback['uses'],'./.github/workflows/documentation-checks.yml')
        self.assertEqual(fallback['if'],"needs.documentation-source.outputs.documentation_reused != 'true' && needs.documentation-source.outputs.documentation_unchanged != 'true'")
        self.assertEqual(source['outputs']['documentation_unchanged'],
            '${{ steps.empty.outputs.no_execution }}')
        empty=next(step for step in source['steps'] if step.get('id')=='empty')
        self.assertEqual(empty['if'],"steps.reuse.outputs.no_execution == 'true'")
        self.assertIn('--verify-empty --candidate',empty['run'])
        self.assertNotIn('--junit',empty['run'])
        checkout=source['steps'][0]
        self.assertEqual(checkout['with']['ref'],'${{ github.event.repository.default_branch }}')
        self.assertFalse(checkout['with']['persist-credentials'])
        candidate=[item for item in source['steps'] if item.get('with',{}).get('path')=='candidate']
        self.assertEqual(len(candidate),1)
        self.assertEqual(candidate[0]['if'],"steps.reuse.outputs.no_execution == 'true'")
        self.assertEqual(candidate[0]['with']['ref'],'${{ github.sha }}')
        self.assertEqual(candidate[0]['with']['fetch-depth'],2)
        self.assertFalse(candidate[0]['with']['persist-credentials'])
        self.assertEqual(candidate[0]['with']['sparse-checkout'].splitlines(),['.github','tests/platform-profile.json'])
        self.assertLess(next(i for i,item in enumerate(source['steps']) if item.get('id')=='protected-source'),
                        next(i for i,item in enumerate(source['steps']) if item.get('id')=='reuse'))
        route=source['steps'][-1]['run']
        for value in ('true','false','','1','TRUE'):
            run=subprocess.run(['/usr/bin/bash','-e','-o','pipefail','-c',route],
                env={'SHARED_REUSED':value},capture_output=True,timeout=5)
            self.assertEqual(run.returncode==0,value in {'true','false'})



class EffectiveBaseResolutionTests(SourceFixture,unittest.TestCase):
    def observations(self, *, event_snapshot='1'*40, api_snapshot='2'*40):
        event=deepcopy(self.event['pull_request']);current=deepcopy(event)
        event['base']['sha']=event_snapshot;current['base']['sha']=api_snapshot;current['state']='open'
        merge={'sha':self.merge_id,'parents':[{'sha':self.base_id},{'sha':self.head_id}]}
        values={
            'branches/'+self.target:{'name':self.target,'protected':True,'commit':{'sha':self.base_id}},
            'git/ref/heads/'+S.quote(event['head']['ref'],safe=''):{'ref':'refs/heads/'+event['head']['ref'],
                'object':{'type':'commit','sha':self.head_id}},
        }
        for snapshot in (event_snapshot,api_snapshot):
            if snapshot!=self.base_id:
                values['compare/'+snapshot+'...'+self.base_id+'?per_page=1']={
                    'status':'ahead','ahead_by':40,'behind_by':0,'total_commits':40,
                    'base_commit':{'sha':snapshot},'merge_base_commit':{'sha':snapshot},
                    'commits':[{'sha':'3'*40}],'files':[]}
        calls=[]
        def get(endpoint):
            calls.append(endpoint)
            return deepcopy(values[endpoint])
        return event,current,merge,values,calls,SimpleNamespace(get=get)

    def test_distinct_event_and_api_ancestors_retain_exact_current_authority(self):
        for snapshots in (('1'*40,'1'*40),('1'*40,'2'*40),(self.base_id,self.base_id)):
            with self.subTest(snapshots=snapshots):
                event,current,merge,values,calls,api=self.observations(event_snapshot=snapshots[0],api_snapshot=snapshots[1])
                original=deepcopy((event,current,merge))
                self.assertEqual(S.resolve_pr_base(api,current,merge,event),{'base':self.base_id,'head':self.head_id,
                    'target':self.target,'head_ref':event['head']['ref'],'source':self.merge_id})
                self.assertEqual((event,current,merge),original)
                self.assertEqual(sum(name.startswith('compare/') for name in calls),sum(value!=self.base_id for value in snapshots))

    def test_each_snapshot_and_current_ref_are_independent_mandatory_evidence(self):
        for failure in ('event-diverged','api-diverged','missing-event','boolean-count','truncated-commits',
                        'future-snapshot','base-ref','head-ref','head-sha','retarget','repo','one-parent','parent-order'):
            event,current,merge,values,calls,api=self.observations()
            comparisons=[name for name in values if name.startswith('compare/')]
            if failure in {'event-diverged','api-diverged'}:
                key='compare/'+('1' if failure=='event-diverged' else '2')*40+'...'+self.base_id+'?per_page=1'
                values[key]['merge_base_commit']['sha']='4'*40
            elif failure=='missing-event': event['base'].pop('sha')
            elif failure=='boolean-count':values[comparisons[0]]['ahead_by']=True
            elif failure=='truncated-commits':values[comparisons[0]]['commits']=[]
            elif failure=='future-snapshot':values[comparisons[0]].update(status='behind',ahead_by=0,behind_by=1,total_commits=0)
            elif failure=='base-ref':values['branches/'+self.target]['commit']['sha']='4'*40
            elif failure=='head-ref':values['git/ref/heads/'+S.quote(event['head']['ref'],safe='')]['object']['sha']='4'*40
            elif failure=='head-sha':current['head']['sha']='4'*40
            elif failure=='retarget':event['base']['ref']='main'
            elif failure=='repo':current['head']['repo']['id']=1
            elif failure=='one-parent':merge['parents'].pop()
            else:merge['parents'].reverse()
            with self.subTest(failure=failure),self.assertRaises(S.SourceUnavailable):
                S.resolve_pr_base(api,current,merge,event)

    def test_actual_source_transport_stale_dual_snapshot_bookends_fit_unchanged_budget(self):
        self.event['pull_request']['base']['sha']='1'*40
        fake=self.api();original=fake.get
        def facts(endpoint):
            if endpoint.startswith('compare/'):
                snapshot=endpoint.split('/',1)[1].split('...',1)[0]
                return {'status':'ahead','ahead_by':40,'behind_by':0,'total_commits':40,
                    'base_commit':{'sha':snapshot},'merge_base_commit':{'sha':snapshot},
                    'commits':[{'sha':'3'*40}],'files':[]}
            value=original(endpoint)
            if endpoint=='pulls/23':value['base']['sha']='2'*40
            return value
        class Response:
            status=200
            def __init__(self,url,body):self.url=url;self.body=body
            def geturl(self):return self.url
            def read(self,maximum):return self.body[:maximum]
            def __enter__(self):return self
            def __exit__(self,*args):return False
        seen=[]
        def opened(request,timeout):
            prefix='https://api.github.com/repos/'+S.REPOSITORY
            self.assertTrue(request.full_url==prefix or request.full_url.startswith(prefix+'/'))
            endpoint=request.full_url[len(prefix):].removeprefix('/')
            seen.append(endpoint)
            return Response(request.full_url,json.dumps(facts(endpoint)).encode())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,body in self.bodies.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
                path.chmod(0o755 if self.default[name]['mode']=='100755' else 0o644)
            with patch.dict(os.environ,{'GH_TOKEN':'fake-source-token'},clear=True), \
                 patch.object(S.urllib.request,'build_opener',return_value=SimpleNamespace(open=opened)), \
                 patch.object(S.time,'monotonic',return_value=100), \
                 patch.object(S.subprocess,'run',return_value=SimpleNamespace(stdout=(self.default_id+'\n').encode())):
                api=S.GitHubSource()
                value=S.authenticate(self.event,self.env,api,root)
                self.assertEqual(value['base'],self.base_id);self.assertEqual(api.calls,24)
                self.assertEqual(api.deadline,145);self.assertEqual(len(seen),24)
                self.assertEqual(sum(endpoint.startswith('compare/') for endpoint in seen),4)
                with self.assertRaisesRegex(S.SourceUnavailable,'budget exceeded'):api.get('')

    def test_native_source_keeps_actual_base_and_separate_snapshot_bookends(self):
        event,current,merge,values,calls,api=self.observations()
        payload={**self.event,'pull_request':event}
        values.update({'':{'id':S.REPOSITORY_ID,'full_name':S.REPOSITORY,'default_branch':'main'},
            'pulls/23':current,'commits/refs/pull/23/merge':merge,
            'git/ref/heads/main':{'ref':'refs/heads/main','object':{'type':'commit','sha':self.default_id}},
            'branches/main':{'name':'main','protected':True,'commit':{'sha':self.default_id}}})
        before=deepcopy(payload)
        self.assertEqual(S.native(payload,self.env,api)['base'],self.base_id)
        self.assertEqual(payload,before)
        for key,value in (('GITHUB_SHA','4'*40),('GITHUB_WORKFLOW_SHA','4'*40),
                          ('GITHUB_EVENT_NAME','pull_request_target'),('GITHUB_HEAD_REF','foreign')):
            with self.subTest(key=key),self.assertRaises(S.SourceUnavailable):
                S.native(payload,{**self.env,key:value},api)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SourceAdmissionTests)
    suite.addTests(BootstrapTests(name) for name in (
        'test_bootstrap_validates_all_source_without_importing_any_controller',
        'test_bootstrap_rejects_changed_helper_before_exec_and_changed_controller_before_import',
        'test_bootstrap_default_source_drift_cannot_admit_after_the_initial_snapshot'))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(DocumentationSourceTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(EffectiveBaseResolutionTests))
    suite.addTests(EffectiveBaseBootstrapTests(name) for name in (
        "test_future_native_bootstrap_resolves_actual_base_before_loading_guard",))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
