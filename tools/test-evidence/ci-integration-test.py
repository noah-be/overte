#!/usr/bin/env python3
"""Fake selected-profile routing; no host queries, namespaces or workloads."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import ci_profile as C
import inputs
import producer_workflow as P
import sandbox
import sandbox_host as H
import sandbox_shared as S


class SelectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.registry = inputs.load_registry(C.ROOT/'.github/test-suites.json')
        paths = {C.POLICY,'.github/test-suites.json','README.md','.github/workflows/project-tests.yml'}
        self.tree = {path:{'mode':'100644','type':'blob','sha':'a'*40} for path in paths}
        self.tree[C.PINNED_SOURCE]=C._pinned_source_entry(C.ROOT)
        data=(C.ROOT/C.DATA_PATH).read_bytes()
        oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        self.tree[C.DATA_PATH]={'mode':'100644','type':'blob','sha':oid}
        self.blobs={oid:data}
        self.base = deepcopy(self.tree); self.base['README.md']['sha']='b'*40
        self.selected = {'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs',
                         'full_host':False,'include_platform':False}
        self.policy = {'schema':1,'enabled':True,'profile':C.PROFILE,'epoch':'ci37-integration-fixture',
            'not_before':'2026-10-16T00:00:00Z','max_age_seconds':259200,'suites':list(C.SUITES),
            'definition_digest':C.definition_digest(self.registry),'generation_digest':C.generation(self.tree,self.registry)}
        self.router = SimpleNamespace(select=Mock(side_effect=lambda *_a,**_k:deepcopy(self.selected)))
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(C,'load_policy',return_value=self.policy))
        self.stack.enter_context(patch.object(C,'SOURCE_READY',True))

    def prepare(self, tree=None, base=None, registry=None):
        return P.selection_profile(self.router,self.registry if registry is None else registry,
            self.tree if tree is None else tree,self.base if base is None else base,self.base,read_blob=self.blobs.__getitem__)

    def test_actual_finite_guard_follows_independently_reconstructed_complete_delta(self):
        result=self.prepare()
        self.assertEqual(result['profile'],C.PROFILE)
        self.assertEqual(result['suites'],list(C.SUITES))
        self.assertEqual(result['binding']['generation_digest'],self.policy['generation_digest'])
        args,options=self.router.select.call_args
        self.assertEqual(args,(self.tree,['README.md'],True))
        self.assertEqual(options['base_tree'],self.base)
        self.assertEqual(options['trusted_tree'],self.base)
        self.assertEqual(options['target'],'main')

    def test_disabled_generation_workflow_lookup_and_registry_drift_fall_back_before_execution(self):
        for change in ('disabled','source','generation','workflow','new-lookup','registry','policy'):
            tree=deepcopy(self.tree); registry=deepcopy(self.registry); policy=deepcopy(self.policy)
            if change=='disabled':policy['enabled']=False
            elif change=='generation':policy['generation_digest']='sha256:'+'0'*64
            elif change=='workflow':tree['.github/workflows/project-tests.yml']['sha']='c'*40
            elif change=='new-lookup':tree['tools/test-evidence/shadow.py']=deepcopy(tree['README.md'])
            elif change=='registry':del registry['suites']['snapshot-native']
            elif change=='policy':tree[C.POLICY]['sha']='c'*40
            with self.subTest(change=change),patch.object(C,'load_policy',return_value=policy), \
                 patch.object(C,'SOURCE_READY',change!='source'),self.assertRaises(P.PreExecutionUnavailable):
                self.prepare(tree=tree,registry=registry)

    def test_full_owner_and_control_plane_subset_keep_original_environment_path(self):
        for names in (list(self.registry['suites']),[*C.SUITES,'device-control-plane-full']):
            self.selected={'suites':names,'reason':'full-fixture','full_host':True,'include_platform':True}
            with patch.object(C,'validate_selection',side_effect=AssertionError('full owner uses original E')):
                result=self.prepare()
            self.assertEqual(result['profile'],P.FULL_PROFILE)
            self.assertIsNone(result['binding'])
            self.assertEqual(set(result['suites']),set(names))

    def test_platform_extra_or_nonregular_owner_cannot_be_relabelled_ci37(self):
        for kind in ('platform','extra','symlink','empty'):
            self.selected={'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs',
                           'full_host':False,'include_platform':kind=='platform'}
            tree=deepcopy(self.tree); base=self.base
            if kind=='extra':self.selected['suites'].append('snapshot-native')
            elif kind=='symlink':tree['README.md']['mode']='120000'
            elif kind=='empty':base=tree
            with self.subTest(kind=kind),self.assertRaises(P.PreExecutionUnavailable):self.prepare(tree,base)

    def test_existing_markdown_route_declines_an_unused_protected_descriptor(self):
        package=P._host_policy().package_policy()
        checks=package.load('ci37_documentation_route','tools/repository-checks/check.py')
        config,branches=checks.configuration()
        repo={'full_name':'noah-l-frank/overte','id':1319052603}
        event={'repository':repo,'pull_request':{'base':{'ref':'main','repo':repo},
            'head':{'ref':'fix/main/documentation','repo':repo}}}
        paths=sorted(C._VARIABLE_DATA)
        route=checks.plan(event,paths,config,branches)
        planned=package.select(paths,legacy_mode=route['mode'])
        self.assertEqual(planned['host_mode'],'documentation')
        policy=SimpleNamespace(additional_suites=Mock(return_value=[]),candidate_registry=Mock(return_value=self.registry),
            package_policy=Mock(return_value=SimpleNamespace(candidate_plan=Mock(return_value=planned))),
            candidate_selection=Mock(side_effect=AssertionError('documentation has no shared host job')))
        binding={'merge_sha':'a'*40,'base_ref':'main','head_ref':'fix/main/documentation'}
        adapter=SimpleNamespace(current=Mock(return_value=(binding,{'default':'b'*40,'default_ref':'main'})))
        with (patch.object(P,'_native',return_value=(17,19)),patch.object(P,'_event_binding'),
              patch.object(P.execution,'checkout_identity',return_value=('b'*40,'c'*40)),
              patch.object(P,'_host_policy',return_value=policy),patch.object(P.inputs,'load_registry',return_value=self.registry),
              self.assertRaises(P.PreExecutionUnavailable)):
            P.prepare(Path('/unexecuted'),event,{'GITHUB_SHA':'a'*40,'GITHUB_HEAD_REF':'fix/main/documentation'},adapter)
        policy.candidate_selection.assert_not_called()


class ExecutionIntegrationTests(unittest.TestCase):
    def batch(self,probe):
        return SimpleNamespace(candidate=Path('/fixture'),snapshot={},policy=Path('/policy'),projection={},
            protected=Path('/protected'),prepared=((),None,None,None),probe=probe,empty=Mock())

    def check_patches(self):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(sandbox,'verify_snapshot'))
        stack.enter_context(patch.object(sandbox,'_files',return_value={}))
        stack.enter_context(patch.object(S,'prepared_identity',return_value={}))
        return stack

    def test_only_initial_ci37_probe_failure_can_select_existing_fallback(self):
        self.check_patches()
        for phase in ('before','suite','after','cancelled'):
            probe=Mock(side_effect=H.Unavailable('capture unavailable') if phase in ('before','cancelled')
                       else [{'E':1},H.Unavailable('after capture unavailable')])
            batch=self.batch(probe)
            with patch.object(S,'run_suites',side_effect=H.Unavailable('suite failure') if phase=='suite' else [[]]) as run:
                with self.subTest(phase=phase),self.assertRaises(H.Unavailable) as caught:
                    S.check_batch(batch,{},[15] if phase=='cancelled' else [],{},
                                  preexecution_unavailable=P.PreExecutionUnavailable)
                self.assertEqual(type(caught.exception),P.PreExecutionUnavailable if phase=='before' else H.Unavailable)
                self.assertEqual(run.call_count,0 if phase in ('before','cancelled') else 1)
                self.assertEqual(probe.call_count,2 if phase=='after' else 1)
                if phase=='before':batch.empty.assert_called_once()

    def test_admission_precedes_37_commands_and_post_measurement_follows_empty_scope(self):
        self.check_patches(); events=[]
        batch=self.batch(lambda _:events.append('probe') or {'actual':1})
        batch.empty=lambda:events.append('empty')
        names=list(C.SUITES)
        with patch.object(S,'run_suites',side_effect=lambda *a,**k:events.append(('suites',k['names'])) or []) as run:
            statuses,before,after=S.check_batch(batch,{},[],{},names=names,
                admit=lambda e:events.append(('admit',e)),preexecution_unavailable=P.PreExecutionUnavailable)
        self.assertEqual(events,['probe',('admit',{'actual':1}),('suites',names),'empty','probe'])
        self.assertEqual(before,after);self.assertEqual(statuses,[]);run.assert_called_once()

    def test_ci37_plan_omits_qt_java_and_rejects_inherited_lookup_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots=[Path(temporary)/name for name in ('candidate','scratch','policy','venv','protected')]
            for root in roots:root.mkdir()
            (roots[0]/'.git').mkdir()
            layout=sandbox.Layout(*roots)
            prepared=((),Path('/opt/hostedtoolcache/Python/3.12.15/x64'),
                         Path('/opt/hostedtoolcache/node/22.23.3/x64'),None)
            plan=S.shared_plan(layout,['python','tests/fake.py'],prepared,{})
            argv=plan['argv'];values={argv[i+1]:argv[i+2] for i,v in enumerate(argv) if v=='--setenv'}
            self.assertFalse({'JAVA_HOME','QT_QPA_PLATFORM','QT_QUICK_BACKEND','OVERTE_QML_TEST_RUNNER'} & values.keys())
            self.assertEqual(values['PATH'],'/opt/overte-ci/venv/bin:/opt/hostedtoolcache/node/22.23.3/x64/bin:/usr/bin:/bin')
            self.assertEqual(S.identity_roots(prepared),())
            for key in ('JAVA_HOME','QT_QPA_PLATFORM','CXX','PATH'):
                with self.subTest(key=key),self.assertRaises(sandbox.SandboxUnavailable):
                    S.shared_plan(layout,['python','fake.py'],prepared,{key:'unreviewed'})

    def test_root_receipt_selects_ci37_admission_before_any_candidate_command(self):
        events=[];registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        tree={path:{'mode':'100644','type':'blob','sha':'a'*40}
              for definition in registry['suites'].values() for path in definition['closure']['required']}
        context={'profile':C.PROFILE,'selected':{'suites':list(C.SUITES)},'registry':registry,
            'refs':{'default':'b'*40},'binding':{'merge_sha':'a'*40,'merge_tree':'c'*40},'git_context':{},
            'plan':{'owners':{'shared-host':{'suites':list(C.SUITES),'include_platform':False}}}}
        batch=SimpleNamespace(candidate=Path('/candidate'),snapshot={})
        def check(*a,**k):
            self.assertIs(k['preexecution_unavailable'],P.PreExecutionUnavailable)
            events.append('capture');k['admit']({'real':'original E'});events.append('candidate suites')
            return ([{'name':name,'status':'passed'} for name in C.SUITES],{'real':'original E'},{'real':'original E'})
        with (patch.object(P.inputs,'full_tree',return_value=tree),patch.object(P,'git_context',return_value={}),
              patch.object(P.execution,'validate_receipt'),patch.object(P.shared,'check_batch',side_effect=check),
              patch.object(P.runtime_ci,'validate_environment',side_effect=lambda *a,**k:events.append('admit')) as admit,
              patch.object(P.attested,'validate_environment',side_effect=AssertionError('no full E'))):
            receipt=P.protected_receipt(batch,context,[],{})
        self.assertEqual(events,['capture','admit','candidate suites'])
        self.assertEqual(receipt['schema'],3);self.assertEqual(receipt['requested_suites'],list(C.SUITES))
        self.assertEqual(admit.call_args.args[4],context['selected'])


class ProbeAndManualIntegrationTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('ci37_probe_fixture',Path(__file__).with_name('sandbox_probe.py'))
        self.probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.probe)

    def test_full_capture_remains_exact_default_and_unknown_profiles_never_probe(self):
        with patch.object(self.probe.runtime,'capture_host_environment',return_value={'full':'original'}) as capture:
            self.assertEqual(self.probe.shared_environment({}),{'full':'original'})
            for binding in ({'runtime_profile':'unknown'},{'diagnostic_only':1},{'diagnostic_only':True}):
                with self.subTest(binding=binding),self.assertRaises(ValueError):self.probe.shared_environment(binding)
            capture.assert_called_once()

    def test_protected_probe_cannot_choose_manual_diagnostic_capture_implicitly(self):
        import runtime_ci
        raw=b'fixed protected policy'
        entry={'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
        tree={C.POLICY:entry};binding={'runtime_profile':C.PROFILE,'source':'a'*40,'selection':{'suites':list(C.SUITES)},
                                     'profile_binding':{'fixed':'binding'}}
        def capture(*args,**options):
            options['read_blob'](entry['sha'])
            return {'selection':binding['profile_binding']}
        def git(repository,*args,**options):
            # Exercise the real reader's Path arithmetic contract: a string
            # here would fail before its bounded subprocess guard is entered.
            self.assertEqual(repository/'.git/objects',Path('/work/.git/objects'))
            self.assertEqual(args,('cat-file','blob',entry['sha']))
            self.assertEqual(options,{'limit':64_000})
            return b'fixed immutable data'
        with (patch.object(inputs,'full_tree',return_value=tree),patch.object(inputs,'load_registry',return_value={}),
              patch.object(Path,'read_bytes',return_value=raw),
              patch.object(sandbox,'_git',side_effect=git),
              patch.object(runtime_ci,'capture_ci_environment',side_effect=capture) as production,
              patch.object(runtime_ci,'capture_ci_environment_diagnostic',side_effect=capture) as diagnostic):
            self.probe.shared_environment(binding)
            production.assert_called_once();diagnostic.assert_not_called()
            self.probe.shared_environment({**binding,'diagnostic_only':True})
            diagnostic.assert_called_once()
            for mutation in ({'diagnostic_only':'true'},{'source':'HEAD'},{'profile_binding':{'forged':True}}):
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                    self.probe.shared_environment({**binding,**mutation})
            tree[C.POLICY]['sha']='0'*40
            with self.assertRaises(ValueError):self.probe.shared_environment(binding)

    def test_fixed_manual_cli_retains_full_diagnostic_and_never_calls_producer(self):
        result={'schema':1,'authority':'none','production_qualified':False,'reusable':False}
        with (patch.object(S,'run_host_ci37',return_value=result) as quick,
              patch.object(S,'run_host',return_value=result) as full,
              patch.object(P,'shared_execution',side_effect=AssertionError('no producer')),
              patch.object(H.sys,'stdout',new_callable=io.StringIO)):
            self.assertEqual(H.main(['--profile','ci37']),0);quick.assert_called_once();full.assert_not_called()
            self.assertEqual(H.main(['--profile','shared-host']),0);full.assert_called_once()
        with patch.object(H,'host_context') as context,self.assertRaises(H.Unavailable):S.run_host(profile='unknown')
        context.assert_not_called()

    def test_manual_ci37_retains_complete_source_guard_and_exact_fixed_inventory(self):
        registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        tree={path:{'mode':'100644','type':'blob','sha':'a'*40} for path in (C.POLICY,'.github/test-suites.json')}
        tree[C.PINNED_SOURCE]=C._pinned_source_entry(C.ROOT)
        data=(C.ROOT/C.DATA_PATH).read_bytes()
        data_oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        tree[C.DATA_PATH]={'mode':'100644','type':'blob','sha':data_oid}
        policy={'schema':1,'enabled':False,'profile':C.PROFILE,'epoch':'manual-ci37-fixture',
            'not_before':'2026-10-16T00:00:00Z','max_age_seconds':259200,'suites':list(C.SUITES),
            'definition_digest':C.definition_digest(registry),'generation_digest':C.generation(tree,registry)}
        real_stat,real_read=Path.stat,Path.read_text
        fixed={'/usr/bin/bwrap','/usr/bin/unshare','/usr/bin/python3','/usr/bin/sudo'}
        def fake_stat(path,*a,**k):
            return SimpleNamespace(st_mode=stat.S_IFREG|0o755,st_uid=0) if str(path) in fixed else real_stat(path,*a,**k)
        def fake_read(path,*a,**k):
            return 'ID=ubuntu\nVERSION_ID="24.04"\n' if str(path)=='/etc/os-release' else real_read(path,*a,**k)
        made=[]
        def batch(*a):
            value=SimpleNamespace(binding=a[5],proofs=['fixed before/after'],protected=a[0]);made.append(value);return value
        def check(*a,**k):
            self.assertEqual(k['names'],list(C.SUITES))
            return ([{'name':name,'status':'passed'} for name in k['names']],{'actual':'E'},{'actual':'E'})
        with (patch.dict(os.environ,{'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'17','GITHUB_RUN_ATTEMPT':'1',
                                    'ImageOS':'ubuntu24','ImageVersion':'20261012.1','RUNNER_ENVIRONMENT':'github-hosted'}),
              patch.object(H,'host_context',return_value=1001) as context,
              patch.object(H,'verify_account',return_value=(2001,2001)),patch.object(H,'prepare_delegation'),
              patch.object(Path,'stat',fake_stat),patch.object(Path,'read_text',fake_read),
              patch.object(S,'verify_source',return_value=['protected sources']),
              patch.object(S,'prepared_tools',return_value=((),None,None,None)) as prepared,
              patch.object(S,'prepared_identity',return_value={}),patch.object(inputs,'load_registry',return_value=registry),
              patch.object(sandbox,'_git',side_effect=lambda *a,**k:data if a[-1]==data_oid else b''),
              patch.object(inputs,'full_tree',return_value=tree),patch.object(C,'load_policy',return_value=policy),
              patch.object(C,'SOURCE_READY',False),patch.object(S,'materialize_source',return_value={'digest':'fixed','git_context':{}}),
              patch.object(S,'project_policy',return_value={}),patch.object(S,'Batch',side_effect=batch),
              patch.object(S,'check_batch',side_effect=check) as checked,patch.object(S.execution,'_write_receipt')):
            result=S.run_host_ci37()
            context.assert_called_once();checked.assert_called_once()
            self.assertEqual(prepared.call_args.kwargs,{'profile':C.PROFILE})
            self.assertEqual(made[0].binding['selection']['suites'],list(C.SUITES))
            self.assertIs(made[0].binding['diagnostic_only'],True)
            self.assertEqual(result['authority'],'none');self.assertIs(result['production_qualified'],False)
            self.assertIs(result['reusable'],False);self.assertEqual(len(result['suites']),37)
            checked.reset_mock();tree['new-lookup.py']=deepcopy(tree[C.POLICY])
            with self.assertRaises(C.CIProfileError):S.run_host_ci37()
            checked.assert_not_called()

    def test_canonical_manual_ci37_omits_java_qt_setup_and_preserves_full_preparation(self):
        import yaml
        canonical=yaml.safe_load((C.ROOT/'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml').read_bytes())
        # Both copies retain the independently reviewed full preparation.
        active=yaml.safe_load((C.ROOT/'.github/workflows/shared-sandbox-host-diagnostic.yml').read_bytes())
        self.assertEqual(active,canonical)
        steps={step['name']:step for step in canonical['jobs']['boundary-diagnostic']['steps']}
        original={step['name']:step for step in active['jobs']['boundary-diagnostic']['steps']}
        for name in ('Set up prepared shared-host Java','Install existing mandatory portable host contract prerequisites'):
            self.assertEqual(steps[name],original[name])
            self.assertEqual(steps[name]['if'],"inputs.profile == 'shared-host'")
        quick=steps['Prepare the fixed Qt-free CI37 diagnostic tools']
        self.assertEqual(quick['if'],"inputs.profile == 'ci37'")
        self.assertNotIn('JAVA',quick['run']);self.assertNotIn('qml-module',quick['run']);self.assertNotIn('libglm',quick['run'])
        self.assertIn('root:root',quick['run']);self.assertIn('go-w',quick['run'])
        # Execute only the actual prerequisite selection prefix. All commands
        # are temporary fixtures; sudo records arguments and installs nothing.
        prefix=quick['run'].split('test ! -e /opt/overte-ci',1)[0]
        tools={'cmake','ctest','ninja','make','gmake','g++','gcc'}
        cases=[(set(),[]),({'ninja'},['ninja-build']),({'ctest'},['cmake']),
               ({'gmake','gcc'},['make','g++']),({'g++','gcc'},['g++'])]
        for missing,packages in cases:
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);binpath=root/'bin';binpath.mkdir();log=root/'apt.log'
                for name in tools-missing:
                    path=binpath/name;path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
                sudo=binpath/'sudo'
                sudo.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SETUP_LOG"\n')
                sudo.chmod(0o755)
                subprocess.run(['/usr/bin/bash','-euc',prefix],check=True,capture_output=True,text=True,
                    env={'PATH':str(binpath),'SETUP_LOG':str(log)})
                if packages:
                    self.assertEqual(log.read_text().splitlines(),[
                        '-n /usr/bin/apt-get update',
                        '-n /usr/bin/apt-get install --no-install-recommends -y '+' '.join(packages)])
                else:
                    self.assertFalse(log.exists())


class CleanupDataGitRouteTests(unittest.TestCase):
    """Real small Git/route fixtures; never production source or runtime proof."""
    def setUp(self):
        import subprocess
        self.process=subprocess
        self.folder=tempfile.TemporaryDirectory(prefix='overte-ci37-data-route-')
        self.addCleanup(self.folder.cleanup)
        self.repo=Path(self.folder.name)/'candidate';self.repo.mkdir()
        self.trusted=Path(self.folder.name)/'trusted'
        self.environment={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
            'GIT_AUTHOR_NAME':'Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid',
            'GIT_COMMITTER_NAME':'Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid',
            'GIT_TERMINAL_PROMPT':'0'}
        for name in ('GIT_DIR','GIT_WORK_TREE','GIT_COMMON_DIR','GIT_INDEX_FILE',
                'GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_CONFIG_COUNT',
                'GIT_CONFIG_PARAMETERS'):
            self.environment.pop(name,None)
        self.router=P._host_policy();self.package=self.router.package_policy()
        self.registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        self.git('init','-q','--initial-branch=main')
        # Only these ordinary fixture leaves exist. The independently loaded
        # helpers and complete60 command definitions remain the reviewed code;
        # no fixture implementation is ever imported or executed.
        for relative in ('.github/test-suites.json',C.POLICY,C.PINNED_SOURCE,C.DATA_PATH,
                         'tests/platform-profile.json'):
            self.write(relative,(C.ROOT/relative).read_bytes())
        for relative in ('tools/test-evidence/runtime.py','tools/branch-cleanup/cleanup.py',
                         self.router.CONTROL_PLANE):
            self.write(relative,b'# Frozen fixture implementation; never executed.\n')
        generation=next(item for item in self.package.workflow_generations() if item['name']=='packages-v1')
        for relative,entry in generation['workflows'].items():
            raw=subprocess.check_output(['git','--no-replace-objects','cat-file','blob',entry['sha']],
                cwd=C.ROOT,stderr=subprocess.PIPE,timeout=10)
            self.write(relative,raw)
        self.git('add','.');self.git('commit','-qm','Create finite cleanup data fixture')
        self.base=self.git('rev-parse','HEAD')
        self.base_tree=inputs.full_tree(self.repo,self.base)
        self.git('worktree','add','-q','--detach',str(self.trusted),self.base)
        self.cleanup=json.loads((self.repo/C.DATA_PATH).read_bytes())
        self.updated=deepcopy(self.cleanup)
        self.updated['holds']['fix/main/kept-fixture']='Retain unfinished fixture work'
        self.policy={'schema':1,'enabled':True,'profile':C.PROFILE,'epoch':'ci37-git-data-fixture',
            'not_before':'2026-10-16T00:00:00Z','max_age_seconds':259200,'suites':list(C.SUITES),
            'definition_digest':C.definition_digest(self.registry),
            'generation_digest':C.generation(self.base_tree,self.registry)}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.router,'ROOT',self.trusted))
        self.stack.enter_context(patch.object(self.router,'package_policy',return_value=self.package))
        self.stack.enter_context(patch.object(self.router,'REVIEWED_PROGRAMS',
            self.router.program_digest(self.base_tree,self.repo)))
        self.stack.enter_context(patch.object(C,'load_policy',return_value=self.policy))
        self.stack.enter_context(patch.object(C,'SOURCE_READY',True))

    def git(self,*arguments):
        return self.process.check_output(['git','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',
            *arguments],cwd=self.repo,env=self.environment,stderr=self.process.PIPE,text=True,timeout=10).strip()

    def write(self,relative,content):
        path=self.repo/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)

    def candidate(self,changes=None):
        self.git('checkout','-q','--detach',self.base)
        self.git('checkout','-q','-B','fix/main/cleanup-data-fixture',self.base)
        self.write(C.DATA_PATH,json.dumps(self.updated).encode())
        for relative,content in (changes or {}).items():self.write(relative,content)
        self.git('add','-A');self.git('commit','-qm','Change cleanup fixture data')
        head=self.git('rev-parse','HEAD')
        self.git('checkout','-q','-B','main',self.base)
        self.git('merge','-q','--no-ff','--no-commit',head)
        self.git('commit','-qm','Merge exact cleanup fixture candidate')
        self.merge=self.git('rev-parse','HEAD')
        repository={'full_name':'noah-l-frank/overte','id':1319052603}
        self.event={'repository':repository,'pull_request':{
            'base':{'ref':'main','sha':self.base,'repo':repository},
            'head':{'ref':'fix/main/cleanup-data-fixture','sha':head,'repo':repository}}}
        self.tree=inputs.full_tree(self.repo,self.merge)
        self.package.validate_wiring(self.repo)
        return self.package.candidate_plan(self.repo,self.event,self.merge)

    def profile(self,read_blob=None):
        return P.selection_profile(self.router,self.registry,self.tree,self.base_tree,self.base_tree,
            root=self.repo,read_blob=read_blob or (lambda oid:P.source_blob(self.repo,oid)))

    def test_holds_only_real_merge_selects_actual_full_host_route_and_exact37_profile(self):
        plan=self.candidate()
        self.assertEqual(plan['paths'],[C.DATA_PATH])
        self.assertEqual(plan['host_mode'],'full')
        self.assertTrue(plan['regular']);self.assertFalse(plan['unknown'])
        self.assertEqual(self.git('show','-s','--format=%P',self.merge).split(),
            [self.base,self.event['pull_request']['head']['sha']])
        selected=self.router.candidate_selection(self.repo,self.event,self.merge,plan['plan'])
        self.assertEqual(selected,{'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs',
                                   'full_host':False,'include_platform':False})
        reads=[]
        def blob(oid):
            reads.append(oid);return P.source_blob(self.repo,oid)
        result=self.profile(blob)
        self.assertEqual(result['selection'],selected)
        self.assertEqual(result['profile'],C.PROFILE)
        self.assertEqual(result['suites'],list(C.SUITES))
        self.assertEqual(reads,[self.base_tree[C.DATA_PATH]['sha'],self.tree[C.DATA_PATH]['sha']])
        self.assertEqual(result['binding']['generation_digest'],self.policy['generation_digest'])
        self.assertEqual(len(self.registry['suites']),60)

    def test_malformed_or_rebound_cleanup_blobs_never_receive_the_ci37_profile(self):
        for content in (b'{"holds":{}}',json.dumps({**self.updated,'artifact_retention_days':31}).encode(),
                        b'{"schema":1,"schema":1}'):
            with self.subTest(content=content):
                plan=self.candidate({C.DATA_PATH:content})
                self.assertEqual(plan['host_mode'],'full')
                self.assertFalse(self.router.candidate_selection(self.repo,self.event,self.merge,plan['plan'])['full_host'])
                with self.assertRaises(P.PreExecutionUnavailable):self.profile()
        self.candidate()
        original=P.source_blob(self.repo,self.base_tree[C.DATA_PATH]['sha'])
        with self.assertRaises(P.PreExecutionUnavailable):self.profile(lambda _oid:original)

    def test_controller_neighbor_platform_and_extra_command_changes_cannot_inherit_ci37(self):
        platform={'schema':1,'platform':'android','suites':[{'name':'new-platform-fixture',
            'interpreter':'python','entrypoint':'tools/branch-cleanup/cleanup.py'}]}
        registry=deepcopy(self.registry)
        registry['suites']['producer-proof']['command'].append('--unreviewed-fixture-command')
        variants={
            'controller':{'tools/test-evidence/runtime.py':b'# Changed protected controller\n'},
            'control-plane':{self.router.CONTROL_PLANE:b'# Changed control-plane reader\n'},
            'neighbor':{'.github/branch-cleanup-extra.json':b'{}\n'},
            'platform':{'tests/platform-profile.json':json.dumps(platform).encode()},
            'extra-command':{'.github/test-suites.json':json.dumps(registry).encode()},
        }
        for name,changes in variants.items():
            with self.subTest(name=name):
                plan=self.candidate(changes)
                self.assertEqual(plan['host_mode'],'full')
                if name=='extra-command':
                    with self.assertRaises(ValueError):
                        self.router.candidate_selection(self.repo,self.event,self.merge,plan['plan'])
                    with self.assertRaises(P.PreExecutionUnavailable):self.profile()
                else:
                    selected=self.router.candidate_selection(self.repo,self.event,self.merge,plan['plan'])
                    self.assertTrue(selected['full_host'])
                    self.assertEqual(self.profile()['profile'],P.FULL_PROFILE)
                    if name=='platform':self.assertTrue(P.execution.platform_suites(self.repo,self.registry['suites']))

    def test_changed_ci_program_keeps_legacy37_but_denies_new_protected_profile(self):
        plan=self.candidate({'tools/branch-cleanup/cleanup.py':b'# Changed CI implementation\n'})
        selected=self.router.candidate_selection(self.repo,self.event,self.merge,plan['plan'])
        self.assertEqual(selected['suites'],list(C.SUITES));self.assertFalse(selected['full_host'])
        with self.assertRaises(P.PreExecutionUnavailable):self.profile()

    def test_immutable_cleanup_reader_ignores_checkout_bytes_and_candidate_git_config(self):
        self.candidate()
        oid=self.tree[C.DATA_PATH]['sha']
        expected=P.source_blob(self.repo,oid)
        self.write(C.DATA_PATH,b'uncommitted misleading bytes')
        (self.repo/'.git/config').write_bytes(b'not valid Git configuration\n')
        self.assertEqual(P.source_blob(self.repo,oid),expected)


if __name__=='__main__':
    unittest.main()
