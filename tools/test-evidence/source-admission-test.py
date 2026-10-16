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
        self.bodies[S.PROFILE]=(ROOT/S.PROFILE).read_bytes()
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
    def test_fixed_graph_matches_actual_complete_producer_controller(self):
        import producer_workflow as P
        self.assertEqual(set(S.CONTROLLERS),set(P.controller_sources(P._host_policy())))
        self.assertEqual(len(S.TARGET_PROFILES),7)
        self.assertEqual(len(set(S.TARGET_PROFILES.values())),3)
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
        self.assertEqual(len(scripts),4)
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
                self.assertTrue(request.full_url.startswith(prefix));self.assertEqual(request.method,'GET')
                endpoint=request.full_url.removeprefix(prefix)
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

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SourceAdmissionTests)
    suite.addTests(BootstrapTests(name) for name in (
        'test_bootstrap_validates_all_source_without_importing_any_controller',
        'test_bootstrap_rejects_changed_helper_before_exec_and_changed_controller_before_import',
        'test_bootstrap_default_source_drift_cannot_admit_after_the_initial_snapshot'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
