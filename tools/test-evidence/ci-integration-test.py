#!/usr/bin/env python3
"""Fake selected-profile routing; no host queries, namespaces or workloads."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
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


def fixed_system_setup(script, missing=(), *, install=True):
    """Execute the actual shell against real fixture files, without root/apt.

    Only the fixed /usr/bin prefix is relocated into a temporary filesystem.
    A separate host-PATH directory always has every tool, reproducing why
    command-v checks were insufficient for the isolated system-only PATH.
    """
    tools={'bash','cmake','ctest','ninja','make','gmake','g++','gcc','c++','cc','git','jq',
           'pkg-config','unshare','as','ld','ar','ranlib','sha256sum','env','ldd','dpkg-query'}
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);system=root/'system';shadow=root/'host-path'
        system.mkdir();shadow.mkdir();log=root/'apt.log'
        for directory,names in ((system,tools-set(missing)),(shadow,tools)):
            for name in names:
                path=directory/name;path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
        sudo=shadow/'sudo'
        sudo.write_text('''#!/usr/bin/python3
import os, pathlib, sys
args=sys.argv[1:]
with open(os.environ['SETUP_LOG'],'a') as output:output.write(' '.join(args)+'\\n')
if 'install' in args and os.environ['FIXTURE_INSTALL']=='true':
    packages={'cmake':('cmake','ctest'),'ninja-build':('ninja',),
              'make':('make','gmake'),'g++':('gcc','g++','cc','c++')}
    for package in args:
        for name in packages.get(package,()):
            path=pathlib.Path(os.environ['FIXED_SYSTEM_BIN'])/name
            path.write_text('#!/bin/sh\\nexit 0\\n');path.chmod(0o755)
''');sudo.chmod(0o755)
        prefix=script.split('test ! -e /opt/overte-ci',1)[0]
        relocated=prefix.replace('/usr/bin/',str(system)+'/')
        # Check the resulting executable lookup, not a mocked which response.
        relocated+='\nPATH="$FIXED_SYSTEM_BIN:$PATH"\ncommand -v cmake\ncommand -v ctest\ncommand -v ninja\n'
        result=subprocess.run(['/usr/bin/bash','-euc',relocated],capture_output=True,text=True,
            env={'PATH':str(shadow),'SETUP_LOG':str(log),'FIXED_SYSTEM_BIN':str(system),
                 'FIXTURE_INSTALL':str(install).lower()})
        recorded=[line.replace(str(system),'/usr/bin') for line in log.read_text().splitlines()] if log.exists() else []
        resolved=result.stdout.splitlines()
        expected=[str(system/name) for name in ('cmake','ctest','ninja')]
        return result,recorded,resolved,expected


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
              patch.object(P,'protected_source_context',return_value={'fixture':'already authenticated native source'}) as source,
              patch.object(P.execution,'checkout_identity',return_value=('b'*40,'c'*40)),
              patch.object(P,'_host_policy',return_value=policy),patch.object(P.inputs,'load_registry',return_value=self.registry),
              self.assertRaises(P.PreExecutionUnavailable)):
            P.prepare(Path('/unexecuted'),event,{'GITHUB_SHA':'a'*40,'GITHUB_HEAD_REF':'fix/main/documentation',
                'GITHUB_BASE_REF':'main'},adapter)
        source.assert_called_once()
        policy.candidate_selection.assert_not_called()


class AffectedProtectedAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Seal a small protected fixture, retaining the real complete registry,
        # every authority/required subject/import root and finite CI exception.
        # This exercises the real pure planner, never a mocked subset result.
        cls.registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        cls.registry_raw=(C.ROOT/'.github/test-suites.json').read_bytes()
        source=inputs.full_tree(C.ROOT,'HEAD')
        graph=json.loads(inputs.load_dependencies(C.ROOT/inputs.AFFECTED_POLICY,cls.registry))
        # This historical source3/main-only contract deliberately retains its
        # schema1 graph. SevenTargetProfileTests independently covers schema2
        # and all seven source4 targets with their complete target identities.
        graph['schema']=1
        graph.pop('targets',None)
        required=set(inputs.AFFECTED_AUTHORITY)
        required.update(graph['suites']['device-control-plane-full']['native_independent_paths'])
        for suite in cls.registry['suites'].values():
            required.update(suite['closure']['required'])
            imports=suite.get('python_imports')
            if imports and inputs.python_import_digest(source,imports['roots'])==imports['reviewed']:
                required.update(row['path'] for row in inputs.selected_entries(
                    source,inputs._import_patterns(imports['roots'])))
        cls.base={path:dict(entry) for path,entry in source.items() if path in required}
        # This complete synthetic schema1 repository models protected main,
        # independently of the child checkout running this test. Android's
        # actual 13/19-owner declarations remain covered by the target fixtures.
        cls.base['tests/platform-profile.json']=deepcopy(inputs._AFFECTED_SHARED_PROFILE)
        graph['lookup_digest']=inputs.affected_lookup_digest(cls.base)
        native=graph['suites']['device-control-plane-full']
        native['reviewed_reader_digest']=inputs.device_reader_digest(cls.base,native['native_independent_paths'])
        cls.graph_raw=(json.dumps(graph,indent=2)+'\n').encode()
        cls.base[inputs.AFFECTED_POLICY]=cls.blob(cls.graph_raw)
        cls.router=P._host_policy()
        cls.temporary=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temporary.cleanup)
        cls.root=Path(cls.temporary.name)
        (cls.root/'.github').mkdir()
        (cls.root/'.github/test-suites.json').write_bytes(cls.registry_raw)
        subprocess.run(['git','init','--quiet',str(cls.root)],check=True,capture_output=True)
        subprocess.run(['git','hash-object','-w','.github/test-suites.json'],cwd=cls.root,
                       check=True,capture_output=True)

    @staticmethod
    def blob(raw):
        return {'mode':'100644','type':'blob',
                'sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}

    def setUp(self):
        self.old=deepcopy(self.base);self.candidate=deepcopy(self.base)
        self.candidate['tools/test-evidence/sandbox_host.py']=self.blob(b'changed candidate controller')
        (self.root/inputs.AFFECTED_POLICY).write_bytes(self.graph_raw)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.router,'ROOT',self.root))

    def profile(self, *, target='main', registry=None):
        return P.selection_profile(self.router,self.registry if registry is None else registry,
            self.candidate,self.old,self.base,root=self.root,target=target)

    def selected(self):
        paths=sorted(p for p in self.old.keys()|self.candidate.keys() if self.old.get(p)!=self.candidate.get(p))
        return self.router.select(self.candidate,paths,True,base_tree=self.old,trusted_tree=self.base,
                                  candidate_root=self.root,trusted_root=self.root)

    def test_real_protected_plan_uses_original_full_environment_for_exact_subset(self):
        with patch.object(C,'validate_selection',side_effect=AssertionError('no CI37 identity')):
            prepared=self.profile()
        selected=prepared['selection'];names=prepared['suites']
        self.assertEqual(len(self.registry['suites']),60)
        self.assertEqual(selected['reason'],'protected-affected-dependencies')
        self.assertEqual(names,selected['affected']['required'])
        self.assertTrue(set(names)<set(self.registry['suites']))
        self.assertNotIn('device-control-plane-full',names)
        self.assertIn('test-evidence',names)
        self.assertEqual(prepared['profile'],P.FULL_PROFILE);self.assertIsNone(prepared['binding'])
        self.assertIs(selected['full_host'],True);self.assertIs(selected['include_platform'],False)
        # A pure selection has no passing evidence. Actual schema-3 execution
        # and the final native whole-receipt publisher remain separate gates.
        self.assertIs(selected['affected']['reusable'],False)

    def test_claimed_label_cannot_choose_names_or_forge_the_dependency_plan(self):
        actual=self.selected()
        for change in ('missing','extra','duplicate','order','plan','paths','field','platform','quick'):
            claimed=deepcopy(actual)
            if change=='missing':claimed['suites']=claimed['suites'][1:]
            elif change=='extra':claimed['suites'].append(actual['affected']['omitted'][0])
            elif change=='duplicate':claimed['suites'].append(claimed['suites'][0])
            elif change=='order':claimed['suites'].reverse()
            elif change=='plan':claimed['affected']['required']=[]
            elif change=='paths':claimed['affected']['paths']=[]
            elif change=='field':claimed['supplied_subset']=True
            elif change=='platform':claimed['include_platform']=True
            else:claimed['full_host']=False
            with self.subTest(change=change),patch.object(self.router,'select',return_value=claimed), \
                 self.assertRaises(P.PreExecutionUnavailable):self.profile()

    def test_legacy_setup_unknown_and_installation_gates_cannot_be_replaced(self):
        actual=self.selected()
        full={'suites':list(self.registry['suites']),'reason':'host-reader-generation-not-reviewed',
              'full_host':True,'include_platform':True}
        for change in ('qt-free','unknown','unowned','installation','not-narrower'):
            legacy=deepcopy(full)
            if change=='qt-free':legacy['full_host']=False
            elif change=='unknown':legacy['reason']='unknown-or-nonregular-inventory'
            elif change=='unowned':legacy['reason']='unowned-inputs'
            elif change=='installation':legacy['reason']='reviewed-protected-producer-transition'
            else:legacy['suites']=list(actual['suites'])
            with self.subTest(change=change),patch.object(self.router,'select',return_value=actual), \
                 patch.object(self.router,'_select_legacy',return_value=legacy), \
                 self.assertRaises(P.PreExecutionUnavailable):self.profile()
        for target in ('apple-main','apple-ios','android-main','android-phone','android-vr','android-vr-pico'):
            with self.subTest(target=target),patch.object(self.router,'select',return_value=actual), \
                 self.assertRaises(P.PreExecutionUnavailable):self.profile(target=target)

    def test_untrusted_graph_source_platform_modes_and_definitions_decline_before_execution(self):
        actual=self.selected()
        for change in ('graph','authority','platform','mode','alias','lookup','neighbor','registry','new-definition'):
            self.old=deepcopy(self.base);self.candidate=deepcopy(self.base)
            self.candidate['tools/test-evidence/sandbox_host.py']=self.blob(b'changed candidate controller')
            registry=deepcopy(self.registry)
            if change=='graph':self.candidate[inputs.AFFECTED_POLICY]=self.blob(b'candidate graph')
            elif change=='authority':self.candidate['tools/test-evidence/execution.py']=self.blob(b'changed runner')
            elif change=='platform':self.candidate['tests/platform-profile.json']=self.blob(b'nonempty delegated owners')
            elif change in ('mode','alias'):
                self.candidate['tools/test-evidence/sandbox_host.py']['mode']='100755' if change=='mode' else '120000'
            elif change=='lookup':self.candidate['tools/test-evidence/new_import.py']=self.blob(b'new import')
            elif change=='neighbor':self.candidate['unknown-ci-controller.py']=self.blob(b'unknown input')
            elif change=='registry':self.candidate['.github/test-suites.json']=self.blob(b'new commands')
            else:registry['suites']['snapshot-native']['command'].append('--changed-definition')
            with self.subTest(change=change),patch.object(self.router,'select',return_value=actual), \
                 self.assertRaises(P.PreExecutionUnavailable):self.profile(registry=registry)

    def test_current_plan_is_rederived_even_when_candidate_and_claim_are_changed_together(self):
        # Adding a native input makes device tests genuinely necessary. A
        # matching freshly computed claim still must respect the legacy
        # unowned-input gate, rather than certify arbitrary new source paths.
        self.candidate['cassert']=self.blob(b'changed native include lookup')
        actual=self.selected()
        plan=inputs.plan_affected(self.registry,self.graph_raw,self.old,self.candidate,self.base)
        self.assertIn('device-control-plane-full',plan['required'])
        self.assertEqual(actual['reason'],'unowned-inputs')
        claimed={'suites':plan['required'],'reason':'protected-affected-dependencies',
                 'full_host':True,'include_platform':False,'affected':plan}
        with patch.object(self.router,'select',return_value=claimed),self.assertRaises(P.PreExecutionUnavailable):
            self.profile()

    def test_selected_failure_is_hard_after_full_admission_without_fallback(self):
        prepared=self.profile();events=[]
        batch=SimpleNamespace(candidate=Path('/fixture'),snapshot={},policy=Path('/policy'),projection={},
            protected=Path('/protected'),prepared=((),None,None,None),
            probe=lambda _:events.append('probe') or {'actual':'full E'},empty=lambda:events.append('empty'))
        with (patch.object(sandbox,'verify_snapshot'),patch.object(sandbox,'_files',return_value={}),
              patch.object(S,'prepared_identity',return_value={}),
              patch.object(S,'run_suites',side_effect=H.Unavailable('selected failure')) as run,
              self.assertRaises(H.Unavailable) as caught):
            S.check_batch(batch,self.registry,[],{},names=prepared['suites'],
                          admit=lambda _:events.append('full admission'))
        self.assertIs(type(caught.exception),H.Unavailable)
        self.assertEqual(events,['probe','full admission'])
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.kwargs['names'],prepared['suites'])

    def test_actual_receipt_path_admits_full_e_and_keeps_only_selected_results(self):
        prepared=self.profile();names=prepared['suites'];events=[]
        context={'profile':prepared['profile'],'selected':prepared['selection'],'registry':self.registry,
            'policy':SimpleNamespace(producer=SimpleNamespace(required_execution_schema=3)),
            'refs':{'default':'b'*40},'binding':{'merge_sha':'a'*40,'merge_tree':'c'*40},'git_context':{},
            'plan':{'owners':{'shared-host':{'suites':names,'include_platform':False}}}}
        batch=SimpleNamespace(candidate=Path('/candidate'),snapshot={})
        def check(*args,**options):
            self.assertNotIn('preexecution_unavailable',options)
            self.assertEqual(options['names'],names)
            events.append('before');options['admit']({'actual':'original full E'});events.append('selected suites')
            return ([{'name':name,'status':'passed'} for name in names],
                    {'actual':'original full E'},{'actual':'original full E'})
        with (patch.object(P.inputs,'full_tree',return_value=self.candidate),
              patch.object(P,'git_context',return_value={}),patch.object(P.execution,'validate_receipt') as validate,
              patch.object(P.shared,'check_batch',side_effect=check),
              patch.object(P.attested,'validate_environment',side_effect=lambda *a,**k:events.append('full admission')) as admit,
              patch.object(P.runtime_ci,'validate_environment',side_effect=AssertionError('no CI37 E'))):
            receipt=P.protected_receipt(batch,context,[],{})
        self.assertEqual(events,['before','full admission','selected suites'])
        self.assertEqual(admit.call_args.kwargs,{'root':P.ROOT,'isolated':True})
        self.assertEqual(receipt['schema'],3);self.assertEqual(receipt['requested_suites'],names)
        self.assertEqual(list(receipt['results']),names)
        self.assertTrue(set(receipt['results']).isdisjoint(prepared['selection']['affected']['omitted']))
        self.assertIs(receipt['include_platform'],False);self.assertEqual(receipt['platform_results'],{})
        validate.assert_called_once_with(receipt,self.registry,self.candidate,expected_git_context={})


class CurrentOriginalOwnerTests(unittest.TestCase):
    """Actual fake-API protocol with explicit source/admission primitives.

    The selected definitions are the shipping three docs commands and workflow
    contracts plus one other owner. These fixtures cannot qualify native E or
    enroll generation21; the separate source/recipe checks own that boundary.
    """
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('current_owner_api_fixtures',
            Path(__file__).with_name('producer-api-test.py'))
        cls.fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.fixtures)

    def setUp(self):
        f=self.fixtures.AdapterTests('runTest');f.setUp();self.case=f
        self.now=self.fixtures.NOW
        original=f.capture().observations[0].run
        shipping=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        suites={name:deepcopy(shipping['suites'][name]) for name in
                ('documentation-contracts','documentation','policy-consistency','workflow-contracts')}
        suites['first']=deepcopy(f.context.registry['suites']['first'])
        self.registry={'schema':1,'control_inputs':shipping['control_inputs'],'suites':suites}
        self.tree=deepcopy(f.context.tree)
        self.tree['tests/platform-profile.json']=deepcopy(inputs._AFFECTED_SHARED_PROFILE)
        for suite in suites.values():
            for path in suite['closure']['required']:
                self.tree.setdefault(path,{'mode':'100644','type':'blob','sha':'5'*40})
        f.plan['owners']['shared-host']['suites']=list(suites)
        f.pp=replace(f.pp,required_execution_schema=3)
        f.policy=replace(f.policy,producer=f.pp)
        f.originals[f.binding['base_sha']]=('6'*40,['7'*40])
        self.git=P.expected_git_context(f.adapter,f.binding)
        self.receipt=deepcopy(f.aggregate['results']['shared-host']['receipt'])
        self.receipt.update(schema=3,git_context=self.git,requested_suites=list(suites),
            environment=self.fixtures.FIXTURES.isolated_codec_environment())
        self.receipt['results']={name:{'status':'passed','fingerprint':inputs.suite_fingerprint(
            self.registry,name,self.tree,self.receipt['environment'])} for name in suites}
        self.receipt=self.fixtures.FIXTURES.signed(self.receipt,'receipt_digest')
        self.run=replace(original,status='in_progress',conclusion=None,
            final_publisher=replace(original.final_publisher,
                receipt_sha256=hashlib.sha256(P.protocol.canonical(self.receipt)).hexdigest()))
        self.refresh()
        binding,refs=f.adapter.current(17)
        self.context={'number':17,'run_id':100,'binding':binding,'refs':refs,'registry':self.registry,
            'selected':{'suites':list(suites),'reason':'fixture-full-owner','full_host':True,'include_platform':False},
            'profile':P.FULL_PROFILE,'profile_binding':None,'plan':f.plan,'policy':f.policy,'git_context':self.git}
        self.context['source_context']={'schema':1,'kind':'protected-default-controller-source-v1',
            'target':'main','base':binding['base_sha'],'default':refs['default'],
            'controller_digest':f.pp.controller_digest,'lookup_digest':'sha256:'+'a'*64,
            'target_profile':deepcopy(inputs._AFFECTED_SHARED_PROFILE)}
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name);self.candidate=self.workspace/'candidate';self.candidate.mkdir()
        self.context['candidate']=self.candidate
        self.environment={'GITHUB_JOB':'repository-checks','GITHUB_WORKSPACE':str(self.workspace)}
        self.package=SimpleNamespace(validate_wiring=Mock(return_value=P.CURRENT_OWNER_GENERATION))
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(P,'protected_admission'))
        self.prepared=self.stack.enter_context(patch.object(P,'prepare',return_value=self.context))
        self.stack.enter_context(patch.object(P,'_host_policy',return_value=SimpleNamespace(package_policy=lambda:self.package)))
        self.stack.enter_context(patch.object(inputs,'full_tree',return_value=self.tree))
        self.admitted=self.stack.enter_context(patch.object(P.attested,'validate_environment',return_value={}))
        self.stack.enter_context(patch.object(P.execution,'execute',side_effect=AssertionError('no candidate command')))
        self.stack.enter_context(patch.object(P.execution,'capture_execution_environment',side_effect=AssertionError('no consumer E')))

    def refresh(self):
        f=self.case
        f.aggregate['results']['shared-host']['receipt']=self.receipt
        f.add_run(self.run)
        f.jobs[100].append({'id':140,'run_id':100,'run_attempt':1,'head_sha':f.binding['head_sha'],
            'name':'repository-checks','status':'in_progress','conclusion':None,
            'started_at':'2026-10-15T10:04:50Z','completed_at':None,
            'check_run_url':f'https://api.github.com/{P.producer_api.PREFIX}/check-runs/140'})

    def verify(self,demanded=None):
        return P.verify_current_owners(self.candidate,{},self.environment,self.case.adapter,
            demanded=P.DOCUMENTATION_SUITES if demanded is None else demanded,clock=lambda:self.now)

    def test_original_pending_outer_has_completed_native_owners_without_completed_run_relabel(self):
        value=self.verify(P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES)
        self.assertIs(value['verified'],True);self.assertIs(value['qualification'],False);self.assertIs(value['reusable'],False)
        self.assertEqual(value['suites'],sorted(P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES))
        self.assertEqual((value['run_id'],value['attempt'],value['outer_job_id']),(100,1,140))
        self.assertEqual(value['receipt_sha256'],hashlib.sha256(P.protocol.canonical(self.receipt)).hexdigest())
        self.assertEqual(value['source_chain']['producer_commit'],self.case.binding['merge_sha'])
        self.assertEqual(self.case.runs[100]['status'],'in_progress');self.assertIsNone(self.case.runs[100]['conclusion'])
        # The same honest API facts remain unavailable to the ordinary completed
        # proof selector. The fixed current-self verifier grants only these jobs.
        snapshot=self.case.capture()
        self.assertEqual(P.protocol.select_authority(snapshot.observations,snapshot.binding,self.case.plan,self.case.pp,
            inventory_complete=True,now=self.now)['state'],'pending')
        context=P.protocol.SharedContext(self.registry,self.tree,self.receipt['environment'],
            self.case.binding['merge_sha'],self.case.binding['merge_tree'],self.git)
        with self.assertRaises(P.protocol.ProtocolError):
            self.case.adapter.verify(17,self.case.plan,self.case.policy,{'shared-host':context},clock=lambda:self.now)
        self.admitted.assert_called_once();self.assertEqual(self.prepared.call_count,2)

    def test_only_fixed_owner_groups_exact_generation_current_job_and_selected_commands_are_allowed(self):
        for demanded in (set(),{'first'},{'documentation'},{'workflow-contracts','first'},['workflow-contracts']):
            with self.subTest(demanded=demanded),self.assertRaises(H.Unavailable):self.verify(demanded)
        for generation in ('protected-producer-metadata-ci-v1','foreign',None):
            self.package.validate_wiring.return_value=generation
            with self.subTest(generation=generation),self.assertRaises(H.Unavailable):self.verify()
        self.package.validate_wiring.return_value=P.CURRENT_OWNER_GENERATION
        self.environment['GITHUB_JOB']='documentation'
        with self.assertRaises(H.Unavailable):self.verify()
        self.environment['GITHUB_JOB']='repository-checks'
        complete=list(self.case.plan['owners']['shared-host']['suites'])
        for name in P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES:
            self.case.plan['owners']['shared-host']['suites']=[item for item in complete if item!=name]
            demand=P.WORKFLOW_CONTRACT_SUITES if name=='workflow-contracts' else P.DOCUMENTATION_SUITES
            with self.subTest(name=name),self.assertRaises(H.Unavailable):self.verify(demand)

    def test_native_app_source_first_attempt_job_status_and_outer_identity_cannot_be_claimed(self):
        for kind in ('app','source','attempt','descriptor','shared','final','outer','outer-id'):
            def mutate(endpoint,value):
                if kind=='app' and '/check-runs/' in endpoint:value['app']['id']=42
                elif kind=='source' and '/attempts/' in endpoint and 'referenced_workflows' in value:
                    value['referenced_workflows'][0]['sha']='f'*40
                elif kind=='attempt' and '/actions/runs/100' in endpoint and 'run_attempt' in value:value['run_attempt']=2
                elif endpoint.endswith('/jobs?per_page=100&page=1'):
                    for job in value['jobs']:
                        match=(kind=='descriptor' and job['name']==self.case.policy.publisher_job
                            or kind=='shared' and job['name']==P.SHARED_JOB
                            or kind=='final' and job['name'].startswith(P.PUBLISH_PREFIX)
                            or kind in {'outer','outer-id'} and job['name']=='repository-checks')
                        if match:
                            if kind=='outer-id':job['check_run_url']='https://api.github.com/repos/overte-org/overte/check-runs/140'
                            else:job.update(status='completed',conclusion='failure')
                return value
            self.case.api.mutate=mutate
            with self.subTest(kind=kind),self.assertRaises((H.Unavailable,P.protocol.ProtocolError)):
                self.verify()

    def test_artifact_native_hash_and_every_actual_required_result_must_match(self):
        runs,jobs,artifacts,archives=deepcopy((self.case.runs,self.case.jobs,self.case.artifacts,self.case.archives))
        for kind in ('hash','api-digest','duplicate','missing-result','failed-result'):
            self.case.runs,self.case.jobs,self.case.artifacts,self.case.archives=deepcopy((runs,jobs,artifacts,archives))
            if kind=='hash':self.case.jobs[100][2]['name']=P.PUBLISH_PREFIX+'f'*64
            elif kind=='api-digest':self.case.artifacts[100][-1]['digest']='sha256:'+'f'*64
            elif kind=='duplicate':self.case.artifacts[100].append(deepcopy(self.case.artifacts[100][-1]))
            else:
                value=deepcopy(self.receipt)
                if kind=='missing-result':del value['results']['documentation']
                else:value['results']['documentation']['status']='failed'
                value=self.fixtures.FIXTURES.signed(value,'receipt_digest')
                self.case.aggregate['results']['shared-host']['receipt']=value
                changed=replace(self.run,final_publisher=replace(self.run.final_publisher,
                    receipt_sha256=hashlib.sha256(P.protocol.canonical(value)).hexdigest()))
                self.case.add_run(changed)
                self.case.jobs[100].append(deepcopy(jobs[100][-1]))
            with self.subTest(kind=kind),self.assertRaises((H.Unavailable,P.protocol.ProtocolError)):self.verify()

    def test_newer_failed_or_pending_and_equal_timestamp_runs_do_not_borrow_current_jobs(self):
        for kind in ('failed','pending','tie'):
            stamp='2026-10-15T09:59:00Z' if kind=='tie' else '2026-10-15T10:04:00Z'
            run=replace(self.run,run_id=101,attempt_started_at=stamp,
                status='completed' if kind!='pending' else 'in_progress',
                conclusion='failure' if kind!='pending' else None,
                publisher=replace(self.run.publisher,job_id=211,
                    started_at='2026-10-15T10:04:00Z',completed_at='2026-10-15T10:04:30Z'),
                owners={},final_publisher=None)
            self.case.add_run(run)
            with self.subTest(kind=kind),self.assertRaises(H.Unavailable):self.verify()
            for values in (self.case.runs,self.case.jobs,self.case.artifacts):values.pop(101)

    def test_original_environment_admission_and_final_bookends_are_required(self):
        self.admitted.side_effect=P.attested.AttestedReuseUnavailable('fixture E declined')
        with self.assertRaises(P.attested.AttestedReuseUnavailable):self.verify()
        self.admitted.side_effect=None
        capture=self.case.adapter.capture;reads=0
        def late(*args,**options):
            nonlocal reads
            reads+=1
            if reads==2:self.case.artifacts[100].append(deepcopy(self.case.artifacts[100][-1]))
            return capture(*args,**options)
        with patch.object(self.case.adapter,'capture',side_effect=late),self.assertRaises((H.Unavailable,P.protocol.ProtocolError)):
            self.verify()

    def test_dispatch_outputs_are_literal_and_do_not_invent_missing_owner_results(self):
        self.assertEqual(P._completed_owner_outputs(self.context,self.receipt),
            {'documentation_verified':'true','workflow_contracts_verified':'true'})
        for name in P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES:
            receipt=deepcopy(self.receipt);del receipt['results'][name]
            value=P._completed_owner_outputs(self.context,receipt)
            self.assertEqual(value['documentation_verified'],'true' if name=='workflow-contracts' else 'false')
            self.assertEqual(value['workflow_contracts_verified'],'false' if name=='workflow-contracts' else 'true')
        self.package.validate_wiring.return_value='protected-producer-metadata-ci-v1'
        self.assertEqual(P._completed_owner_outputs(self.context,self.receipt),
            {'documentation_verified':'false','workflow_contracts_verified':'false'})

    def test_finite_targets_keep_native_source_but_children_cannot_use_legacy_source3(self):
        profiles={'main':inputs._AFFECTED_SHARED_PROFILE['sha'],
            'apple-main':inputs._AFFECTED_SHARED_PROFILE['sha'],'apple-ios':inputs._AFFECTED_SHARED_PROFILE['sha'],
            'android-main':'1314006455751831be60b143e46ce9c6f5398e26',
            'android-vr':'1314006455751831be60b143e46ce9c6f5398e26',
            'android-vr-pico':'1314006455751831be60b143e46ce9c6f5398e26',
            'android-phone':'f91169af7bdfedffb0b6ab9ab0ac1da28fd1f7fe'}
        self.assertEqual(set(profiles),P._CURRENT_OWNER_TARGETS)
        original_json=self.case.api.json
        def child_ref(endpoint):
            target=self.case.binding['base_ref']
            if target!='main' and endpoint==P.producer_api.PREFIX+'/git/ref/heads/'+target:
                self.case.api.calls.append(endpoint)
                return {'ref':'refs/heads/'+target,'object':{'type':'commit','sha':self.case.binding['base_sha']}}
            return original_json(endpoint)
        self.case.api.json=child_ref
        for target,sha in profiles.items():
            self.case.binding['base_ref']=target
            self.context['binding']['base_ref']=target
            self.context['source_context']['target']=target
            entry={'mode':'100644','type':'blob','sha':sha}
            self.context['source_context']['target_profile']=entry
            self.tree['tests/platform-profile.json']=entry
            self.context['refs']=self.case.adapter.current(17)[1]
            self.receipt['results']={name:{'status':'passed','fingerprint':inputs.suite_fingerprint(
                self.registry,name,self.tree,self.receipt['environment'])} for name in self.registry['suites']}
            self.receipt=self.fixtures.FIXTURES.signed(self.receipt,'receipt_digest')
            self.run=replace(self.run,final_publisher=replace(self.run.final_publisher,
                receipt_sha256=hashlib.sha256(P.protocol.canonical(self.receipt)).hexdigest()))
            # The real native chain descriptor binds the actual child base;
            # no prior main descriptor is relabelled as a child source.
            self.refresh()
            with self.subTest(target=target):
                self.assertEqual(self.case.binding['base_ref'],target)
                if target!='main':
                    self.assertFalse(P._owner_target_supported(self.context))
                    with self.assertRaises(H.Unavailable):self.verify(P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES)
                    self.assertEqual(P._completed_owner_outputs(self.context,self.receipt),
                        {'documentation_verified':'false','workflow_contracts_verified':'false'})
                    continue
                value=self.verify(P.DOCUMENTATION_SUITES|P.WORKFLOW_CONTRACT_SUITES)
                self.assertIs(value['verified'],True)
                self.assertEqual(P._completed_owner_outputs(self.context,self.receipt),
                    {'documentation_verified':'true','workflow_contracts_verified':'true'})
        # Android nonempty declarations are supported only when the separately
        # selected native shared owner actually omits platform owners. Enter
        # the new format prerequisite for this independent planning check so a
        # missing retained source3 does not conceal the platform guard.
        self.context['policy']=replace(self.context['policy'],producer=replace(
            self.context['policy'].producer,required_execution_schema=4))
        owner=self.context['plan']['owners']['shared-host'];owner['include_platform']=True
        self.assertFalse(P._owner_target_supported(self.context))
        self.assertEqual(P._completed_owner_outputs(self.context,self.receipt),
            {'documentation_verified':'false','workflow_contracts_verified':'false'})
        with self.assertRaises(H.Unavailable):self.verify()
        owner['include_platform']=False
        for change in ('subset','quick','missing-source','wrong-target','wrong-controller','unknown'):
            context=deepcopy(self.context)
            if change=='subset':context['plan']['owners']['shared-host']['suites']=list(context['registry']['suites'])[1:]
            elif change=='quick':context['profile']=C.PROFILE;context['selected']['full_host']=False
            elif change=='missing-source':del context['source_context']
            elif change=='wrong-target':context['source_context']['target']='main'
            elif change=='wrong-controller':context['source_context']['controller_digest']='sha256:'+'f'*64
            else:context['binding']['base_ref']='unknown'
            with self.subTest(change=change):
                self.assertFalse(P._owner_target_supported(context))
                self.assertEqual(P._completed_owner_outputs(context,self.receipt),
                    {'documentation_verified':'false','workflow_contracts_verified':'false'})


class ExecutionIntegrationTests(unittest.TestCase):
    def test_shared_role_publishes_the_finished_canonical_receipt_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);candidate=root/'candidate';candidate.mkdir()
            event=root/'event.json';event.write_text('{}')
            output=root/'output';output.touch(mode=0o600)
            destination=root/'receipt';destination.mkdir(mode=0o700)
            receipt={'schema':4,'results':{'fixture':{'status':'passed'}}}
            with (patch.dict(P.os.environ,{'GITHUB_WORKSPACE':str(root),
                    'GITHUB_EVENT_PATH':str(event),'GITHUB_OUTPUT':str(output)}),
                  patch.object(P,'protected_admission'),
                  patch.object(P.producer_api,'Adapter'),
                  patch.object(P,'shared_execution',return_value=receipt) as execute,
                  patch.object(P,'_directory',return_value=destination) as directory):
                self.assertEqual(P.main(['shared','--candidate',str(candidate)]),0)
            execute.assert_called_once()
            directory.assert_called_once_with('ci-protected-receipt',root_only=True)
            raw=(destination/'receipt.json').read_bytes()
            self.assertEqual(raw,P.protocol.canonical(receipt))
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o755)
            self.assertEqual(stat.S_IMODE((destination/'receipt.json').stat().st_mode),0o444)
            self.assertEqual(output.read_text(),'protected_executed=true\nreceipt_sha256='
                +hashlib.sha256(raw).hexdigest()+'\n')

    def test_receipt_output_rejects_invalid_values_and_other_numbered_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'output';output.touch(mode=0o600)
            with patch.dict(P.os.environ,{'GITHUB_OUTPUT':str(output)}):
                for values in ({'receipt_sha256':''},{'receipt_sha256':'true'},
                        {'receipt_sha256':'false'},{'receipt_sha256':'a'*40},
                        {'receipt_sha256':'g'*64},{'receipt_sha256':'A'*64},
                        {'receipt_sha256':'a'*64+'\nforged=true'},
                        {'receipt_sha512':'a'*64},{'receipt_sha256\nforged':'a'*64},
                        {'protected_executed':'true','receipt_sha256':'a'*40}):
                    with self.subTest(values=values),self.assertRaises(H.Unavailable):
                        P._output(values,protected=True)
                    self.assertEqual(output.read_bytes(),b'')

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
            'policy':SimpleNamespace(producer=SimpleNamespace(required_execution_schema=3)),
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

    def test_full_capture_requires_prepared_identity_and_unknown_profiles_never_probe(self):
        prepared={'fixture':'root-authenticated-map-only'}
        with patch.object(self.probe.runtime,'capture_isolated_host_environment',return_value={'full':'original'}) as capture:
            self.assertEqual(self.probe.shared_environment({'prepared':prepared}),{'full':'original'})
            for binding in ({},{'runtime_profile':'unknown'},{'diagnostic_only':1},{'diagnostic_only':True}):
                with self.subTest(binding=binding),self.assertRaises(ValueError):self.probe.shared_environment(binding)
            capture.assert_called_once_with(prepared)

    def test_protected_probe_cannot_choose_manual_diagnostic_capture_implicitly(self):
        import runtime_ci
        raw=b'fixed protected policy'
        entry={'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
        tree={C.POLICY:entry};binding={'runtime_profile':C.PROFILE,'source':'a'*40,'selection':{'suites':list(C.SUITES)},
                                     'profile_binding':{'fixed':'binding'}}
        diagnostic_binding={'kind':C.DIAGNOSTIC_KIND,'source_commit':'a'*40,
                            'actual_selection':binding['profile_binding']}
        def capture(*args,**options):
            options['read_blob'](entry['sha'])
            if 'source' in options:
                self.assertEqual(options['source'],'a'*40)
                self.assertEqual(options['source_root'],Path('/work'))
                return {'selection':diagnostic_binding}
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
            self.probe.shared_environment({**binding,'diagnostic_only':True,'profile_binding':diagnostic_binding})
            diagnostic.assert_called_once()
            with self.assertRaises(ValueError):self.probe.shared_environment({**binding,'diagnostic_only':True})
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

    def test_manual_ci37_forwards_actual_source_and_diagnostic_binding_before_fixed_inventory(self):
        registry=inputs.load_registry(C.ROOT/'.github/test-suites.json')
        tree={path:{'mode':'100644','type':'blob','sha':'a'*40} for path in (C.POLICY,'.github/test-suites.json')}
        tree[C.PINNED_SOURCE]=C._pinned_source_entry(C.ROOT)
        data=(C.ROOT/C.DATA_PATH).read_bytes()
        data_oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        tree[C.DATA_PATH]={'mode':'100644','type':'blob','sha':data_oid}
        policy={'schema':1,'enabled':False,'profile':C.PROFILE,'epoch':'manual-ci37-fixture',
            'not_before':'2026-10-16T00:00:00Z','max_age_seconds':259200,'suites':list(C.SUITES),
            'definition_digest':C.definition_digest(registry),'generation_digest':C.generation(tree,registry)}
        immutable=deepcopy(tree)
        diagnostic_binding={'kind':C.DIAGNOSTIC_KIND,'source_commit':'a'*40,'source_tree':'b'*40,
            'production_policy_digest':C.policy_identity(policy),'actual_selection':{'fixture':'diagnostic-only'}}
        def diagnostic(selected,candidate,trusted,actual_registry,**options):
            self.assertEqual(options['source'],'a'*40)
            self.assertEqual(options['source_root'],S.ROOT);self.assertEqual(options['root'],S.ROOT)
            self.assertEqual(selected,{'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs',
                'full_host':False,'include_platform':False})
            self.assertEqual(actual_registry,registry)
            if candidate!=immutable or trusted!=immutable:
                raise C.CIProfileError('fixture immutable source differs')
            self.assertEqual(options['read_blob'](data_oid),data)
            return deepcopy(diagnostic_binding)
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
              patch.object(C,'diagnostic_selection',side_effect=diagnostic) as selected_profile,
              patch.object(C,'SOURCE_READY',False),patch.object(S,'materialize_source',return_value={'digest':'fixed','git_context':{}}),
              patch.object(S,'project_policy',return_value={}),patch.object(S,'Batch',side_effect=batch),
              patch.object(S,'check_batch',side_effect=check) as checked,patch.object(S.execution,'_write_receipt')):
            result=S.run_host_ci37()
            context.assert_called_once();checked.assert_called_once()
            self.assertEqual(prepared.call_args.kwargs,{'profile':C.PROFILE})
            self.assertEqual(made[0].binding['selection']['suites'],list(C.SUITES))
            self.assertEqual(made[0].binding['profile_binding'],diagnostic_binding)
            selected_profile.assert_called_once()
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
        cases=[(set(),[]),({'ninja'},['ninja-build']),({'ctest'},['cmake']),
               ({'gmake','gcc'},['make','g++']),({'g++','gcc'},['g++'])]
        for missing,packages in cases:
            with self.subTest(missing=missing):
                result,recorded,resolved,expected=fixed_system_setup(quick['run'],missing)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(resolved,expected)
                self.assertEqual(recorded,[
                        '-n /usr/bin/apt-get update',
                        '-n /usr/bin/apt-get install --no-install-recommends -y '+' '.join(packages)] if packages else [])


class ProtectedSetupTemplateTests(unittest.TestCase):
    """Dormant workflow plans and fake shell tools, never host qualification."""
    def setUp(self):
        import yaml
        path=C.ROOT/'tools/repository-checks/workflows/producers/protected-project-tests.yml'
        self.rows=yaml.safe_load(path.read_bytes())['jobs']['project-tests']['steps']
        self.steps={row['name']:row for row in self.rows}

    def plan(self,protected,full,executed,*,success=True,admitted='true'):
        import re
        values={'needs.route.outputs.protected_full':protected,'steps.host.outputs.full_host':full,
                'steps.protected.outputs.protected_executed':executed,
                'steps.protected-source.outputs.admitted':admitted}
        def atom(value):
            match=re.fullmatch(r"([a-z_.-]+) (==|!=) '(true|false)'",value)
            self.assertIsNotNone(match,value)
            actual=values[match[1]]
            return (actual==match[3]) if match[2]=='==' else (actual!=match[3])
        names=('Independently select affected host contracts','Set up Java','Verify runner prerequisites',
            'Install QML and portable C++ contract prerequisites','Prepare the protected trusted host environment',
            'Prepare the protected CI37 host environment','Verify protected CI37 runner prerequisites',
            'Execute the selected protected shared owner','Set up Java for pre-execution fallback',
            'Verify fallback runner prerequisites','Prepare isolated host evidence validators',
            'Run independently selected host contracts')
        # All these conditions use GitHub's implicit success() gate. In
        # particular no failed/cancelled protected execution may reach legacy.
        return [row['name'] for row in self.rows if row['name'] in names and success and
            ('if' not in row or any(all(atom(part) for part in term.split(' && '))
                for term in row['if'].split(' || ')))]

    def test_full_protected37_legacy37_and_preexecution_fallback_plans(self):
        select='Independently select affected host contracts'
        java=['Set up Java','Verify runner prerequisites']
        qt='Install QML and portable C++ contract prerequisites'
        full='Prepare the protected trusted host environment'
        quick=['Prepare the protected CI37 host environment','Verify protected CI37 runner prerequisites']
        execute='Execute the selected protected shared owner'
        restore=['Set up Java for pre-execution fallback','Verify fallback runner prerequisites']
        legacy=['Prepare isolated host evidence validators','Run independently selected host contracts']
        self.assertEqual(self.plan('true','true','true'),[select,*java,qt,full,execute])
        self.assertEqual(self.plan('true','false','true'),[select,*quick,execute])
        self.assertEqual(self.plan('false','false',''),[select,*java,*legacy])
        self.assertEqual(self.plan('true','false','false'),[select,*quick,execute,*restore,*legacy])
        self.assertEqual(self.plan('true','true','false'),[select,*java,qt,full,execute,*legacy])
        self.assertEqual(self.plan('true','false','',success=False),[])
        for admitted in ('false','','unknown'):
            with self.subTest(admitted=admitted):
                self.assertEqual(self.plan('true','false','',admitted=admitted),[select,*java,*legacy])
                self.assertEqual(self.plan('true','true','',admitted=admitted),[select,*java,qt,*legacy])
        for name in (*restore,*legacy):
            self.assertNotIn('always()',self.steps[name]['if'])
            self.assertNotIn('continue-on-error',self.steps[name])
        order=[row['name'] for row in self.rows]
        self.assertLess(order.index('Set up Python'),order.index(select))
        self.assertLess(order.index('Set up Node.js'),order.index(select))
        self.assertLess(order.index(select),order.index('Set up Java'))

    def test_original_full_preparation_java_and_qt_are_preserved(self):
        import yaml
        original=yaml.safe_load((C.ROOT/'tools/repository-checks/workflows/host/project-tests.yml').read_bytes())
        old={row['name']:row for row in original['jobs']['project-tests']['steps']}
        for name in ('Set up Java','Verify runner prerequisites'):
            self.assertEqual({key:value for key,value in self.steps[name].items() if key!='if'},old[name])
        name='Install QML and portable C++ contract prerequisites'
        original=deepcopy(self.steps[name])
        original['run']=original['run'].replace('  cmake ninja-build \\\n','')
        original['run']=original['run'].split('for tool in bash cmake ctest',1)[0]
        self.assertEqual(original,old[name])
        for name,digest in (
            ('Verify runner prerequisites','36a8510ed3474fdb512d8c6932392e463e3e15dcca1488e68ba34a3b968a792a'),
            ('Prepare the protected trusted host environment','8971d9d719129a6f74c233bf864a73f5fea3f089f6ca862d155bd36afaa7aafd')):
            self.assertEqual(hashlib.sha256(self.steps[name]['run'].encode()).hexdigest(),digest)
        self.assertEqual(self.steps['Set up Java for pre-execution fallback']['uses'],old['Set up Java']['uses'])
        self.assertEqual(self.steps['Set up Java for pre-execution fallback']['with'],old['Set up Java']['with'])
        self.assertEqual(self.steps['Verify fallback runner prerequisites']['run'],old['Verify runner prerequisites']['run'])
        manual=yaml.safe_load((C.ROOT/'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml').read_bytes())
        quick=next(row for row in manual['jobs']['boundary-diagnostic']['steps']
                   if row['name']=='Prepare the fixed Qt-free CI37 diagnostic tools')['run']
        self.assertEqual(self.steps['Prepare the protected CI37 host environment']['run'],
                         quick.replace('-r tests/requirements-host.txt','-r trusted/tests/requirements-host.txt'))

    def test_actual_prerequisite_shell_queries_java_only_for_full_or_legacy(self):
        for name,java in (('Verify runner prerequisites',True),('Verify fallback runner prerequisites',True),
                          ('Verify protected CI37 runner prerequisites',False)):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary);log=folder/'queries'
                for tool in ('bash','jq','cmake','ninja','ctest','python3','node',*(('java',) if java else ())):
                    path=folder/tool
                    path.write_text('#!/bin/sh\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$SETUP_LOG"\n')
                    path.chmod(0o755)
                subprocess.run(['/usr/bin/bash','-euc',self.steps[name]['run']],check=True,capture_output=True,
                               env={'PATH':str(folder),'SETUP_LOG':str(log)})
                self.assertEqual(log.read_text().splitlines(),['python3 --version','node --version',
                                                               *(['java -version'] if java else [])])

    def test_actual_ci37_shell_installs_only_missing_fixed_native_tools(self):
        script=self.steps['Prepare the protected CI37 host environment']['run']
        cases=[(set(),[]),({'cmake','ctest'},['cmake']),({'ninja'},['ninja-build']),
               ({'make','gmake'},['make']),({'gmake','gcc'},['make','g++']),({'cc','c++'},['g++'])]
        for missing,packages in cases:
            with self.subTest(missing=missing):
                result,recorded,resolved,expected=fixed_system_setup(script,missing)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(resolved,expected)
                self.assertEqual(recorded,[
                    '-n /usr/bin/apt-get update',
                    '-n /usr/bin/apt-get install --no-install-recommends -y '+' '.join(packages)] if packages else [])
        self.assertNotIn('JAVA',script)
        self.assertNotIn('qml',script)

    def test_full_and_ci37_actual_shells_install_system_tools_even_when_host_path_has_them(self):
        import yaml
        manual=yaml.safe_load((C.ROOT/'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml').read_bytes())
        steps={row['name']:row for row in manual['jobs']['boundary-diagnostic']['steps']}
        scripts=(steps['Install existing mandatory portable host contract prerequisites']['run'],
                 steps['Prepare the fixed Qt-free CI37 diagnostic tools']['run'],
                 self.steps['Install QML and portable C++ contract prerequisites']['run'],
                 self.steps['Prepare the protected CI37 host environment']['run'])
        for script in scripts:
            with self.subTest(full='qml-module' in script):
                result,recorded,resolved,expected=fixed_system_setup(script,{'cmake','ctest','ninja'})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(resolved,expected)
                install=next(line.split() for line in recorded if ' install ' in line)
                self.assertEqual(install.count('cmake'),1);self.assertEqual(install.count('ninja-build'),1)
                result,_,_,_=fixed_system_setup(script,{'cmake','ctest','ninja'},install=False)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Missing fixed system prerequisite: cmake',result.stderr)

    def test_ci37_missing_fixed_binutils_or_base_tool_fails_before_preparation(self):
        import yaml
        manual=yaml.safe_load((C.ROOT/'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml').read_bytes())
        quick=next(row for row in manual['jobs']['boundary-diagnostic']['steps']
                   if row['name']=='Prepare the fixed Qt-free CI37 diagnostic tools')['run']
        for script in (quick,self.steps['Prepare the protected CI37 host environment']['run']):
            for tool in ('as','ld','ar','ranlib','sha256sum','env','ldd','dpkg-query'):
                with self.subTest(tool=tool,manual=script==quick):
                    result,recorded,_,_=fixed_system_setup(script,{tool})
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('Missing fixed system prerequisite: '+tool,result.stderr)
                    self.assertEqual(recorded,[])

    def test_required_runtime_tools_report_only_fixed_allowlisted_names(self):
        runtime=S.runtime
        for name in runtime._COMMANDS:
            with self.subTest(name=name),patch.object(runtime,'_checked_executable',
                    side_effect=runtime.RuntimeIdentityError('/private/path token=secret')) as lookup:
                with self.assertRaises(runtime.RuntimeIdentityError) as caught:runtime._required_tool(name)
                self.assertEqual(str(caught.exception),'a required host tool cannot be identified: '+name)
                lookup.assert_called_once_with(runtime._COMMANDS[name][0])
        for name in ('/private/path','secret-executable',None,1):
            with self.subTest(name=name),patch.object(runtime,'_checked_executable') as lookup:
                with self.assertRaisesRegex(runtime.RuntimeIdentityError,'^unsupported required host tool role$'):
                    runtime._required_tool(name)
                lookup.assert_not_called()

    def test_actual_ci37_three_root_validator_rejects_java_aliases_and_other_versions(self):
        script=self.steps['Prepare the protected CI37 host environment']['run']
        body=script.split("<<'PYROOTS'\n",1)[1].split('\nPYROOTS',1)[0]
        python='/opt/hostedtoolcache/Python/3.12.15/x64';node='/opt/hostedtoolcache/node/22.23.3/x64'
        cases=[([python,node],True,False),([python,node,'/usr/lib/jvm/temurin-17-jdk-amd64'],False,False),
               ([python,python],False,False),([python.replace('3.12.15','3.13.1'),node],False,False),
               ([python,node.replace('22.23.3','24.1.0')],False,False),([python,node],False,True)]
        for roots,accepted,alias in cases:
            with (self.subTest(roots=roots,alias=alias),patch('sys.argv',['-',*roots]),
                  patch.object(Path,'is_dir',return_value=True),patch.object(Path,'is_symlink',return_value=alias),
                  patch.object(Path,'resolve',lambda self,strict=False:self)):
                if accepted:exec(compile(body,'protected-ci37-roots','exec'),{})
                else:
                    with self.assertRaises(AssertionError):exec(compile(body,'protected-ci37-roots','exec'),{})

    def test_actual_protected_shell_accepts_unset_java_without_changing_full_forwarding(self):
        script=self.steps['Execute the selected protected shared owner']['run']
        for java in (None,'/usr/lib/jvm/temurin-17-jdk-amd64'):
            with self.subTest(java=java),tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary);log=folder/'arguments'
                node=folder/'node';node.write_text('#!/bin/sh\nprintf "/opt/hostedtoolcache/node/22.23.3/x64\\n"\n');node.chmod(0o755)
                sudo=folder/'sudo';sudo.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SETUP_LOG"\n');sudo.chmod(0o755)
                keys=('GITHUB_EVENT_NAME','GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_REF',
                    'GITHUB_WORKFLOW_REF','GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT',
                    'RUNNER_ENVIRONMENT','ImageOS','ImageVersion','GITHUB_BASE_REF','GITHUB_HEAD_REF',
                    'GITHUB_WORKSPACE','GITHUB_EVENT_PATH','RUNNER_TEMP','GITHUB_OUTPUT','GH_TOKEN')
                environment={key:'fixture' for key in keys}
                environment.update(PATH=str(folder),SETUP_LOG=str(log))
                if java is not None:environment['JAVA_HOME']=java
                subprocess.run(['/usr/bin/bash','-euc',script],check=True,capture_output=True,env=environment)
                arguments=log.read_text().splitlines()
                self.assertIn('QUALIFY_JAVA_HOME='+(java or ''),arguments)
                self.assertIn('QUALIFY_NODE_ROOT=/opt/hostedtoolcache/node/22.23.3/x64',arguments)
                self.assertIn('/usr/bin/env',arguments);self.assertIn('-i',arguments)
                self.assertIn('--property=Delegate=yes',arguments)
                self.assertIn('test -n "$JAVA_HOME"',self.steps['Prepare the protected trusted host environment']['run'])


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


class AndroidPlatformPartitionTests(unittest.TestCase):
    """Fixed source/owner planning and fake execution only; no Android tools."""
    @classmethod
    def setUpClass(cls):
        cls.registry_raw=(P.ROOT/'.github/test-suites.json').read_bytes()
        cls.registry=inputs._validate_registry(json.loads(cls.registry_raw))
        cls.declarations=json.loads((P.ROOT/'.github/android-owner-transfer.json').read_bytes())['profiles']
        cls.package=P._host_policy().package_policy()

    def setUp(self):
        self.target='android-main'
        self.profiles={target:(json.dumps({'schema':1,'platform':'android',
            'suites':row['required_suites']},indent=2)+'\n').encode()
            for target,row in self.declarations.items()}
        for target,raw in self.profiles.items():
            self.assertEqual(P.source_admission.blob_id(raw),P.source_admission.TARGET_PROFILES[target])
        self.names=list(self.registry['suites'])
        self.profile={'profile':P.FULL_PROFILE,'binding':None,'suites':self.names,
            'selection':{'suites':self.names,'full_host':True,'include_platform':True,'reason':'complete-legacy-context'}}
        registry_entry=P.source_admission.ordinary(P.source_admission.blob_id(self.registry_raw))
        _,template=P.source_admission.actual_bytes(P.ROOT,P.PLATFORM_TEMPLATE)
        self.trusted={'.github/test-suites.json':registry_entry,P.PLATFORM_TEMPLATE:template}
        self.base={'.github/test-suites.json':deepcopy(registry_entry)}
        self.tree=deepcopy(self.base)
        self.tree['.github/workflows/project-tests.yml']=deepcopy(template)
        self.package_boundary=SimpleNamespace(validate_tree_wiring=Mock(return_value=P.PLATFORM_GENERATION),
            candidate_plan=Mock(return_value={'host_mode':'full'}))
        self.policy=SimpleNamespace(package_policy=lambda:self.package_boundary)
        self.select_target(self.target)

    def select_target(self,target):
        self.target=target
        entry=P.source_admission.ordinary(P.source_admission.TARGET_PROFILES[target])
        self.base[P.source_admission.PROFILE]=deepcopy(entry)
        self.tree[P.source_admission.PROFILE]=deepcopy(entry)
        for row in self.declarations[target]['required_suites']:
            source=P.source_admission.ordinary('f'*40,'100755' if row['interpreter']=='bash' else '100644')
            self.base[row['entrypoint']]=deepcopy(source)
            self.tree[row['entrypoint']]=deepcopy(source)

    def partition(self):
        return P.platform_partition(self.policy,self.profile,self.registry,self.tree,self.base,self.trusted,
            target=self.target,read_blob=lambda oid:self.profiles[self.target])

    def test_all_four_exact_profiles_preserve_original_selection_and_full_common_E(self):
        original=deepcopy(self.profile)
        for target in self.declarations:
            self.select_target(target)
            with self.subTest(target=target):
                value=self.partition()
                self.assertEqual(len(value['commands']),19 if target=='android-phone' else 13)
                self.assertEqual(value['common_owner'],{'kind':'shared','suites':self.names,
                    'include_platform':False,'platform':{}})
                self.assertEqual([row['name'] for row in value['commands']],
                    [row['name'] for row in self.declarations[target]['required_suites']])
                self.assertEqual(self.profile,original)
                P.protocol.validate_plan({'owners':{'shared-host':value['common_owner']}})
        self.assertIn(P.PLATFORM_GENERATION,{row['name'] for row in self.package.workflow_generations()})

    def test_admitted_seven_target_ci_owner_does_not_invent_platform_work(self):
        names=list(C.SUITES)
        self.profile={'profile':C.PROFILE,'binding':{'generation_kind':C.SEVEN_CONTROLLER_KIND,
            'profile':C.PROFILE,'suites':names},'suites':names,
            'selection':{'suites':names,'full_host':False,'include_platform':False,
                         'reason':'reviewed-ci-only-inputs'}}
        original=deepcopy(self.profile)
        for target in self.declarations:
            self.select_target(target)
            with self.subTest(target=target):self.assertIsNone(self.partition())
        self.assertEqual(self.profile,original)
        for mutation in ('binding','old-kind','profile','order','platform','target-profile'):
            self.profile=deepcopy(original);saved=deepcopy(self.base)
            if mutation=='binding':self.profile['binding']=None
            elif mutation=='old-kind':self.profile['binding']['generation_kind']=C.CONTROLLER_KIND
            elif mutation=='profile':self.profile['profile']=P.FULL_PROFILE
            elif mutation=='order':self.profile['suites']=list(reversed(names))
            elif mutation=='platform':self.profile['selection']['include_platform']=True
            else:self.base[P.source_admission.PROFILE]['sha']='e'*40
            with self.subTest(mutation=mutation),self.assertRaises(P.PreExecutionUnavailable):self.partition()
            self.base=saved

    def test_old_or_unknown_generation_cannot_enable_platform_partition(self):
        for name in ('protected-producer-seven-target-ci-v1','unknown'):
            with self.subTest(name=name):
                self.package_boundary.validate_tree_wiring.return_value=name
                self.assertIsNone(self.partition())

    def test_no_partial_ci37_registry_drift_or_candidate_template_can_supply_authority(self):
        for kind in ('ci37','partial','order','setup','platform','registry','template'):
            self.setUp()
            if kind=='ci37':self.profile['profile']=C.PROFILE
            elif kind=='partial':self.profile['selection']['suites']=self.names[:-1]
            elif kind=='order':self.profile['selection']['suites']=list(reversed(self.names))
            elif kind=='setup':self.profile['selection']['full_host']=False
            elif kind=='platform':self.profile['selection']['include_platform']=False
            elif kind=='registry':self.tree['.github/test-suites.json']['sha']='e'*40
            else:self.tree['.github/workflows/project-tests.yml']['sha']='e'*40
            with self.subTest(kind=kind),self.assertRaises(P.PreExecutionUnavailable):self.partition()

    def test_profile_and_implementation_modes_aliases_missing_and_unauthenticated_blobs_reject(self):
        for kind in ('profile','profile-mode','profile-alias','removed','mode','alias','wrong-bytes','oversize'):
            self.setUp();path=self.declarations[self.target]['required_suites'][0]['entrypoint']
            if kind=='profile':self.tree[P.source_admission.PROFILE]['sha']='e'*40
            elif kind=='profile-mode':self.base[P.source_admission.PROFILE]['mode']='100755'
            elif kind=='profile-alias':self.tree[P.source_admission.PROFILE]['mode']='120000'
            elif kind=='removed':del self.tree[path]
            elif kind=='mode':self.tree[path]['mode']='100755'
            elif kind=='alias':self.tree[path]['mode']='120000'
            elif kind=='wrong-bytes':self.profiles[self.target]=b'{}\n'
            else:self.profiles[self.target]=b' '*64_001
            with self.subTest(kind=kind),self.assertRaises(P.PreExecutionUnavailable):self.partition()

    def execution_fixture(self,delegated=None):
        partition=self.partition()
        candidate=Path('/unexecuted-platform-candidate')
        context={'candidate':candidate,'binding':{'merge_sha':'a'*40,'merge_tree':'b'*40},
            'platform_partition':partition,'registry':self.registry}
        patches=[patch.object(P.execution,'checkout_identity',return_value=('a'*40,'b'*40)),
            patch.object(P,'current_platform_job'),patch.object(P,'pending_platform_owner',return_value=delegated or {}),
            patch.object(P,'platform_prerequisites',return_value={}),patch.object(P,'_platform_bookend')]
        return context,patches

    def run_fake(self,context,patches,runner):
        with ExitStack() as stack:
            mocks=[stack.enter_context(patch) for patch in patches]
            value=P.platform_execution(context,{}, {},object(),report=Path('/outside/report.xml'),runner=runner)
        return value,mocks

    def test_platform_only_executes_exact_selected_commands_without_shared_capture(self):
        context,patches=self.execution_fixture()
        observed=[]
        def runner(candidate,commands,report):
            observed.extend(commands)
            return 0,[{'name':row['name'],'status':'passed'} for row in commands]
        with patch.object(P.shared,'check_batch',side_effect=AssertionError('no shared workload')), \
             patch.object(P.execution,'capture_execution_environment',side_effect=AssertionError('no reusable platform E')):
            value,_=self.run_fake(context,patches,runner)
        self.assertEqual(observed,context['platform_partition']['commands'])
        self.assertFalse(value['reusable']);self.assertFalse(value['qualification'])
        self.assertEqual(len(value['executed']),13)

    def test_only_existing_pico_handoff_can_remove_one_platform_command(self):
        proof={'pico4-device-free':{'owner':'required-android','candidate':'a'*40,
            'plan':'sha256:'+'1'*64,'inventory':'sha256:'+'2'*64}}
        context,patches=self.execution_fixture(proof)
        runner=Mock(side_effect=lambda c,rows,r:(0,[{'name':row['name'],'status':'passed'} for row in rows]))
        value,_=self.run_fake(context,patches,runner)
        self.assertEqual(len(value['executed']),12)
        self.assertNotIn('pico4-device-free',value['executed'])
        self.assertEqual(value['delegated'],proof)
        environment={'GITHUB_EVENT_NAME':'pull_request'}
        for observed in ({'different-owner':{}},{'pico4-device-free':{**proof['pico4-device-free'],'candidate':'c'*40}}):
            with patch.object(P,'_platform_handoff',return_value=SimpleNamespace(platform_owner=lambda *a,**k:observed)), \
                 self.assertRaises(P.execution.ExecutionError):P.pending_platform_owner(context,{},environment)
        with patch.object(P,'_platform_handoff',return_value=SimpleNamespace(platform_owner=Mock(side_effect=ValueError('unavailable')))):
            self.assertEqual(P.pending_platform_owner(context,{},environment),{})

    def test_started_failure_missing_owner_source_drift_and_late_admission_never_retry(self):
        for kind in ('failure','missing','reordered','source','late-admission'):
            context,patches=self.execution_fixture()
            if kind=='source':patches[0]=patch.object(P.execution,'checkout_identity',side_effect=[('a'*40,'b'*40),('c'*40,'b'*40)])
            if kind=='late-admission':patches[-1]=patch.object(P,'_platform_bookend',side_effect=H.Unavailable('changed'))
            def run(candidate,rows,report):
                records=[{'name':row['name'],'status':'passed'} for row in rows]
                if kind=='missing':records=records[:-1]
                if kind=='reordered':records.reverse()
                return (1 if kind=='failure' else 0),records
            runner=Mock(side_effect=run)
            with self.subTest(kind=kind),self.assertRaises(H.Unavailable):self.run_fake(context,patches,runner)
            self.assertEqual(runner.call_count,1)

    def test_missing_phone_ndk_fails_before_candidate_execution(self):
        self.select_target('android-phone');partition=self.partition()
        with self.assertRaises(H.Unavailable):P.platform_prerequisites(partition,Path('/unexecuted'),{})

    def test_future_template_separates_jobs_preserves_setup_and_requires_final_platform_gate(self):
        import yaml
        current=yaml.safe_load((P.ROOT/P.TEMPLATE).read_bytes())
        future=yaml.safe_load((P.ROOT/P.PLATFORM_TEMPLATE).read_bytes())
        self.assertEqual(set(future['jobs']),set(current['jobs'])|{'platform-tests'})
        self.assertIn('platform-tests',future['jobs']['project-results']['needs'])
        self.assertNotIn('platform-tests',future['jobs']['producer-publication']['needs'])
        old={row['name']:row for row in current['jobs']['project-tests']['steps']}
        new={row['name']:row for row in future['jobs']['project-tests']['steps']}
        for name in ('Install QML and portable C++ contract prerequisites',
                     'Prepare the protected trusted host environment','Prepare the protected CI37 host environment'):
            self.assertEqual(new[name],old[name])
        platform=future['jobs']['platform-tests']
        self.assertEqual(platform['name'],'Android platform tests')
        self.assertNotIn('ci-protected-receipt',json.dumps(platform))
        self.assertNotIn('producer-publication',platform['needs'])
        self.assertEqual(platform['steps'][-2]['name'],'Execute and verify the complete Android platform inventory')
        self.assertNotIn('platform --candidate',new['Run independently selected host contracts']['run'])

    def aggregate_fixture(self):
        partition=self.partition()
        plan={'candidate':'a'*40,'plan':'sha256:'+'b'*64,'host_mode':'full','tool_projects':[],'package_set':[]}
        package=SimpleNamespace(validate_wiring=Mock(return_value=P.PLATFORM_GENERATION),
            candidate_plan=Mock(return_value=plan),outputs=self.package.outputs,verify=self.package.verify)
        policy=SimpleNamespace(package_policy=lambda:package)
        needs={'route':{'result':'success','outputs':{**self.package.outputs(plan),
                'protected_full':'true','platform_required':'true'}},
            'project-tests':{'result':'success','outputs':{'protected_executed':'true'}},
            'tool-dependencies':{'result':'skipped','outputs':{}},
            'package-checks':{'result':'skipped','outputs':{}},
            'platform-tests':{'result':'success','outputs':{'required':'true','verified':'true',
                'partition':partition['digest'].removeprefix('sha256:')}}}
        return policy,needs,{'platform_partition':partition},plan

    def verify_aggregate(self,policy,needs,context):
        with patch.object(P,'_host_policy',return_value=policy),patch.object(P,'current_platform_context',return_value=context), \
             patch.object(P,'_platform_bookend'),patch.object(P,'completed_platform_job'):
            return P.verify_platform_project(Path('/unexecuted'),{}, {'GITHUB_SHA':'a'*40},object(),needs)

    def test_final_aggregate_requires_real_platform_job_and_keeps_generic_verifier_strict(self):
        policy,needs,context,plan=self.aggregate_fixture()
        self.assertEqual(self.verify_aggregate(policy,needs,context),self.package.receipt(plan))
        with self.assertRaises(ValueError):self.package.verify(needs,plan)
        for mutation in ('failed','cancelled','skipped','pending','missing','hash','claim','extra','route','common'):
            changed=deepcopy(needs)
            if mutation in {'failed','cancelled','skipped','pending'}:changed['platform-tests']['result']=mutation
            elif mutation=='missing':del changed['platform-tests']
            elif mutation=='hash':changed['platform-tests']['outputs']['partition']='0'*64
            elif mutation=='claim':changed['platform-tests']['outputs']['verified']='false'
            elif mutation=='extra':changed['platform-tests']['outputs']['unreviewed']='true'
            elif mutation=='route':changed['route']['outputs']['package_candidate']='c'*40
            else:changed['project-tests']['result']='failure'
            with self.subTest(mutation=mutation),self.assertRaises((H.Unavailable,ValueError)):
                self.verify_aggregate(policy,changed,context)

    def test_legacy_fallback_preserves_platform_work_without_claiming_a_native_receipt(self):
        policy,needs,context,plan=self.aggregate_fixture()
        needs['route']['outputs'].update(protected_full='false',platform_required='false')
        needs['project-tests']['outputs']={'protected_executed':'false'}
        needs['platform-tests']={'result':'skipped','outputs':{}}
        self.assertEqual(self.verify_aggregate(policy,needs,context),self.package.receipt(plan))
        needs['platform-tests']['outputs']={'required':'','verified':'','partition':''}
        self.assertEqual(self.verify_aggregate(policy,needs,context),self.package.receipt(plan))
        needs['route']['outputs']['platform_required']='true'
        with self.assertRaises(H.Unavailable):self.verify_aggregate(policy,needs,context)
        needs['route']['outputs']['platform_required']='false'
        policy.package_policy().validate_wiring.return_value='protected-producer-seven-target-ci-v1'
        with self.assertRaises(H.Unavailable):self.verify_aggregate(policy,needs,context)


    def test_platform_process_contract_preserves_timeouts_layers_and_private_environment(self):
        observed=[]
        def run(arguments,suites,cancelled,result_callback):
            self.assertEqual((arguments.timeout,arguments.host_timeout,arguments.fail_fast),(240,900,False))
            observed.extend(suites)
            for suite in suites:result_callback({'name':suite.name,'status':'passed'})
            return 0
        controller=SimpleNamespace(ROOT=Path('/original'),run_command=Mock(side_effect=AssertionError('no process')),
            Suite=lambda name,layer,command:SimpleNamespace(name=name,layer=layer,command=command),run_suites=run)
        commands=self.partition()['commands']
        with patch.object(P.execution,'_runner',return_value=controller),patch.object(P.signal,'signal'):
            status,rows=P._run_platform_suites(Path('/unexecuted'),commands,Path('/outside/report.xml'))
        self.assertEqual(status,0)
        self.assertEqual(len(rows),13)
        self.assertEqual([suite.layer for suite in observed],['quick']*13)
        self.assertEqual([suite.command[0] for suite in observed],
            [P.sys.executable if row['command'][0]=='python' else 'bash' for row in commands])
        self.assertEqual(controller.ROOT,Path('/original'))
        controller.run_command.assert_not_called()

    def push_event(self,target='android-main',job='platform-tests'):
        source='a'*40
        event={'ref':'refs/heads/'+target,'before':'b'*40,'after':source,'deleted':False,'forced':False,
            'repository':{'full_name':P.producer_api.REPOSITORY,'id':1319052603}}
        workflow='parent-qualification' if target in {'android-main','android-vr'} else 'project-tests'
        environment={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':P.producer_api.REPOSITORY,
            'GITHUB_REPOSITORY_ID':'1319052603','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1',
            'RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24','GITHUB_SHA':source,
            'GITHUB_WORKFLOW_SHA':source,'GITHUB_RUN_ID':'13','GITHUB_JOB':job,
            'GITHUB_REF':'refs/heads/'+target,'GITHUB_WORKFLOW_REF':P.producer_api.REPOSITORY+
                '/.github/workflows/'+workflow+'.yml@refs/heads/'+target}
        return event,environment

    def push_plan(self,current,mode='full'):
        return {'candidate':'a'*40,'tree':'c'*40,'base':'b'*40,'head':'a'*40,
            'paths':sorted(path for path in self.base.keys()|current.keys() if self.base.get(path)!=current.get(path)),
            'regular':True,'unknown':False,'host_mode':mode,'plan':'f'*64}

    def test_push_roles_authenticate_push_without_relabelling_an_open_pr(self):
        for target in self.declarations:
            event,environment=self.push_event(target)
            self.assertEqual(P._platform_push_native(event,environment),('a'*40,13))
        for key,value in (('GITHUB_EVENT_NAME','pull_request'),('GITHUB_JOB','unrelated'),
                ('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_SHA','b'*40),
                ('GITHUB_REPOSITORY','overte-org/overte'),('GITHUB_REF','refs/heads/main'),('GITHUB_REF','android-main')):
            event,environment=self.push_event();environment[key]=value
            with self.subTest(key=key),self.assertRaises((H.Unavailable,P.producer_api.ApiError)):
                P._platform_push_native(event,environment)
        event,environment=self.push_event();event['forced']=True
        with self.assertRaises(H.Unavailable):P._platform_push_native(event,environment)

    def test_actual_push_context_uses_complete_sources_and_original_selection_without_pr_api(self):
        import postmerge
        event,environment=self.push_event()
        _,parent=P.source_admission.actual_bytes(P.ROOT,P.PLATFORM_PARENT_TEMPLATE)
        local={**deepcopy(self.trusted),P.PLATFORM_PARENT_TEMPLATE:parent}
        current={**deepcopy(self.tree),'.github/workflows/parent-qualification.yml':parent}
        self.package_boundary.candidate_plan=Mock(return_value=self.push_plan(current))
        binding={'pull_request':23,'base_ref':self.target,'base_sha':'b'*40,
            'merge_sha':'a'*40,'merge_tree':'c'*40}
        refs={'target':'a'*40,'default':'d'*40,'default_ref':'main',
            'integration':{'workflow_path':'.github/workflows/parent-qualification.yml'}}
        adapter=SimpleNamespace(_integrated_current=Mock(return_value=(binding,refs)),
            current=Mock(side_effect=AssertionError('no invented open PR')),
            api=SimpleNamespace(immutable_blob=lambda oid:self.profiles[self.target]))
        self.policy.select=Mock(return_value=deepcopy(self.profile['selection']))
        def tree(_adapter,revision):return ('c'*40,{'a'*40:current,'b'*40:self.base,'d'*40:local}[revision])
        with patch.object(P,'_host_policy',return_value=self.policy),patch.object(postmerge,'full_tree',side_effect=tree), \
             patch.object(postmerge,'integrated_controller',return_value='sha256:'+'e'*64) as guard, \
             patch.object(postmerge,'integrated_controller_for_reuse',return_value='sha256:'+'e'*64) as precheck, \
             patch.object(P.execution,'checkout_identity',side_effect=lambda path:('d'*40,'f'*40) if path==P.ROOT else ('a'*40,'c'*40)), \
             patch.object(P.inputs,'full_tree',side_effect=lambda path,revision:local if path==P.ROOT else current):
            context=P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
        self.assertEqual(context['selected'],self.profile['selection'])
        self.assertFalse(context['platform_partition']['common_owner']['include_platform'])
        self.assertEqual(len(context['platform_partition']['commands']),13)
        guard.assert_called_once();precheck.assert_called_once();adapter.current.assert_not_called()

    def test_common_fallback_runs_only_full_common_once_and_never_emits_reusable_E(self):
        context,patches=self.execution_fixture()
        receipt={'reusable':False,'environment':None}
        with patch.object(P,'current_run'),patch.object(P,'_platform_bookend') as bookend, \
             patch.object(P.execution,'execute',return_value=(0,receipt)) as execute:
            self.assertEqual(P.legacy_common_fallback(context,{}, {},object(),report=Path('/outside/common.xml')),receipt)
        self.assertEqual(execute.call_args.args,(context['candidate'],list(self.registry['suites'])))
        self.assertEqual(execute.call_args.kwargs,{'include_platform':False,'junit':Path('/outside/common.xml'),'_impact_selection':True})
        bookend.assert_called_once()
        for result in ((1,receipt),(0,{'reusable':True,'environment':{}})):
            with patch.object(P,'current_run'),patch.object(P.execution,'execute',return_value=result) as execute, \
                 self.assertRaises(H.Unavailable):
                P.legacy_common_fallback(context,{}, {},object(),report=Path('/outside/common.xml'))
            self.assertEqual(execute.call_count,1)

    def test_native_platform_job_requires_unique_real_success_and_complete_execution_step(self):
        import postmerge
        from datetime import datetime,timezone
        now=datetime(2026,10,16,12,tzinfo=timezone.utc)
        raw={'name':P.PLATFORM_JOB,'steps':[{'name':'Execute and verify the complete Android platform inventory',
            'status':'completed','conclusion':'success','started_at':'2026-10-16T10:01:00Z',
            'completed_at':'2026-10-16T10:02:00Z'}]}
        job=SimpleNamespace(job_id=17,status='completed',conclusion='success',
            started_at='2026-10-16T10:00:00Z',completed_at='2026-10-16T10:03:00Z')
        adapter=SimpleNamespace(_job=Mock(return_value=job))
        value=P._completed_platform_job(adapter,{},[raw],P.PLATFORM_JOB,now)
        self.assertEqual(value['job_id'],17)
        self.assertEqual(adapter._job.call_args.args[2],15368)
        self.assertEqual(adapter._job.call_args.kwargs,{'final_name':P.PLATFORM_JOB})
        for kind in ('missing','duplicate','failed','skipped','pending','absent-step','failed-step','early','late','foreign-app'):
            rows=[deepcopy(raw)];observed=deepcopy(job);adapter._job=Mock(return_value=observed)
            if kind=='missing':rows=[]
            elif kind=='duplicate':rows*=2
            elif kind in {'failed','skipped'}:observed.conclusion=kind
            elif kind=='pending':observed.status='in_progress';observed.conclusion=None
            elif kind=='absent-step':rows[0]['steps']=[]
            elif kind=='failed-step':rows[0]['steps'][0]['conclusion']='failure'
            elif kind=='early':rows[0]['steps'][0]['started_at']='2026-10-16T09:00:00Z'
            elif kind=='late':rows[0]['steps'][0]['completed_at']='2026-10-16T13:00:00Z'
            else:adapter._job.side_effect=P.producer_api.ApiError('fixed app mismatch')
            with self.subTest(kind=kind),self.assertRaises((H.Unavailable,P.producer_api.ApiError)):
                P._completed_platform_job(adapter,{},rows,P.PLATFORM_JOB,now)
        run=SimpleNamespace(run_id=13)
        original={'id':13,'run_attempt':1,'status':'completed','conclusion':'success'}
        adapter=SimpleNamespace(_object=Mock(return_value=original),_pages=Mock(return_value=[raw]),_job=Mock(return_value=job))
        value=postmerge.original_platform_owner(adapter,run,self.partition(),now=now)
        self.assertFalse(value['reusable']);self.assertFalse(value['qualification'])
        original['run_attempt']=2
        with self.assertRaises(P.producer_api.ApiError):postmerge.original_platform_owner(adapter,run,self.partition(),now=now)

    def test_current_platform_native_api_rejects_app_suite_attempt_and_source_drift(self):
        from datetime import datetime,timezone
        now=datetime(2026,10,16,12,tzinfo=timezone.utc)
        attempt={'id':13,'workflow_id':350930890,'check_suite_id':19,
            'path':'.github/workflows/parent-qualification.yml','event':'push','head_sha':'a'*40,
            'head_branch':'android-main','run_attempt':1,'status':'in_progress','conclusion':None}
        raw={'id':17,'run_id':13,'run_attempt':1,'head_sha':'a'*40,'name':'Android platform tests',
            'check_run_url':'https://api.github.com/repos/noah-l-frank/overte/check-runs/17',
            'status':'completed','conclusion':'success','started_at':'2026-10-16T10:00:00Z',
            'completed_at':'2026-10-16T10:03:00Z','steps':[{
                'name':'Execute and verify the complete Android platform inventory',
                'status':'completed','conclusion':'success','started_at':'2026-10-16T10:01:00Z',
                'completed_at':'2026-10-16T10:02:00Z'}]}
        check={**{key:raw[key] for key in ('id','head_sha','name','status','conclusion','started_at','completed_at')},
            'app':{'id':15368},'check_suite':{'id':19}}
        records={'actions/runs/13':attempt,'actions/runs/13/attempts/1':deepcopy(attempt),
            'actions/runs/13/attempts/1/jobs?per_page=100&page=1':{'total_count':1,'jobs':[raw]},'check-runs/17':check}
        binding={'merge_sha':'a'*40};refs={'integration':{
            'workflow_path':'.github/workflows/parent-qualification.yml','workflow_id':350930890}}
        context={'run_id':13,'binding':binding,'refs':refs,'integration':refs['integration']}
        def make(data):
            api=SimpleNamespace(json=lambda path:deepcopy(data[path.removeprefix(P.producer_api.PREFIX+'/')]))
            adapter=P.producer_api.Adapter(api)
            adapter._integrated_current=Mock(return_value=(binding,refs))
            return adapter
        self.assertEqual(P.completed_platform_job(context,make(records),now=now)['job_id'],17)
        for kind in ('app','suite','attempt','head','workflow','missing','step','reference'):
            changed=deepcopy(records);adapter=make(changed)
            if kind=='app':changed['check-runs/17']['app']['id']=99
            elif kind=='suite':changed['check-runs/17']['check_suite']['id']=20
            elif kind=='attempt':changed['actions/runs/13']['run_attempt']=2
            elif kind=='head':changed['actions/runs/13/attempts/1']['head_sha']='b'*40
            elif kind=='workflow':
                for endpoint in ('actions/runs/13','actions/runs/13/attempts/1'):changed[endpoint]['path']='.github/workflows/project-tests.yml'
            elif kind=='missing':changed['actions/runs/13/attempts/1/jobs?per_page=100&page=1']={'total_count':0,'jobs':[]}
            elif kind=='step':changed['actions/runs/13/attempts/1/jobs?per_page=100&page=1']['jobs'][0]['steps'][0]['conclusion']='skipped'
            else:adapter._integrated_current.return_value=({'merge_sha':'b'*40},refs)
            with self.subTest(kind=kind),self.assertRaises((H.Unavailable,P.producer_api.ApiError)):
                P.completed_platform_job(context,adapter,now=now)

    def test_future_parent_keeps_required_name_after_both_independent_jobs(self):
        import ast,shlex,yaml
        parent=yaml.safe_load((P.ROOT/P.PLATFORM_PARENT_TEMPLATE).read_bytes())
        jobs=parent['jobs']
        self.assertEqual(set(jobs),{'route','common-parent','platform-tests','qualify-parent'})
        self.assertEqual(jobs['qualify-parent']['name'],'Qualify exact parent')
        self.assertEqual(set(jobs['qualify-parent']['needs']),{'route','common-parent','platform-tests'})
        self.assertEqual(jobs['qualify-parent']['if'],'always()')
        self.assertEqual(jobs['platform-tests']['needs'],'route')
        self.assertEqual(jobs['common-parent']['needs'],'route')
        self.assertIn('always() && !cancelled()',jobs['common-parent']['if'])
        self.assertIn('"main","apple-main"',jobs['common-parent']['if'])
        self.assertEqual(jobs['platform-tests']['if'],"needs.route.result == 'success' && needs.route.outputs.platform_required == 'true'")
        self.assertIn('"android-main","android-vr"',jobs['route']['if'])
        self.assertNotIn('needs',jobs['route'])
        self.assertEqual(jobs['route']['permissions'],{name:'read' for name in ('contents','actions','pull-requests','checks')})
        planned=next(step for step in jobs['route']['steps'] if step.get('id')=='plan')
        command=shlex.split(planned['run']);ast.parse(command[command.index('-c')+1])
        self.assertEqual(command[:4],['/usr/bin/python3','-I','-S','-B'])
        self.assertIn('parent-route',command)
        guard=next(step['run'] for step in jobs['route']['steps'] if step.get('id')=='protected-source')
        self.assertEqual(guard,next(step['run'] for step in jobs['common-parent']['steps'] if step.get('id')=='protected-source'))
        common={row['name']:row for row in jobs['common-parent']['steps']}
        for name in ('Run complete host qualification','Run independently selected parent host contracts',
                'Create content-addressed qualification evidence','Upload immutable qualification evidence'):
            self.assertIn("needs.route.outputs.platform_required != 'true'",common[name]['if'])
        self.assertNotIn('Independently derive Android common and platform ownership',common)
        self.assertIn('fallback-common',common['Execute common parent suites without claiming platform evidence']['run'])
        self.assertNotIn('include-platform',common['Execute common parent suites without claiming platform evidence']['run'])

    def test_parent_aggregate_never_waives_current_platform_from_original_common_proof(self):
        partition=self.partition();context={'platform_partition':partition,
            'binding':{'base_ref':self.target,'merge_sha':'a'*40},'refs':{'target':'a'*40,'default':'d'*40},
            'controller':'sha256:'+'e'*64,'selected':self.profile['selection']}
        needs={'route':{'result':'success','outputs':P.parent_route_outputs(context)},
            'common-parent':{'result':'success'},'platform-tests':{'result':'success',
            'outputs':{'required':'true','verified':'true','partition':partition['digest'].removeprefix('sha256:')}}}
        self.package_boundary.validate_wiring=Mock(return_value=P.PLATFORM_GENERATION)
        event,environment=self.push_event(job='qualify-parent')
        with patch.object(P,'_host_policy',return_value=self.policy), \
             patch.object(P,'current_platform_context',return_value=context), \
             patch.object(P,'_platform_bookend') as bookend,patch.object(P,'completed_platform_job') as native:
            P.verify_platform_parent(Path('/unexecuted'),event,environment,object(),needs)
            native.assert_called_once();bookend.assert_called_once()
            for key in ('route','common-parent','platform-tests'):
                for status in ('failure','cancelled','skipped','pending'):
                    changed=deepcopy(needs);changed[key]['result']=status
                    with self.subTest(key=key,status=status),self.assertRaises(H.Unavailable):
                        P.verify_platform_parent(Path('/unexecuted'),event,environment,object(),changed)
            with patch.object(P,'completed_platform_job',side_effect=H.Unavailable('missing native platform step')),self.assertRaises(H.Unavailable):
                P.verify_platform_parent(Path('/unexecuted'),event,environment,object(),needs)

    def test_unselected_parent_platform_requires_independent_route_and_no_dummy_success(self):
        context={'platform_partition':None,'binding':{'base_ref':self.target,'merge_sha':'a'*40},
            'refs':{'target':'a'*40,'default':'d'*40},'controller':'sha256:'+'e'*64,
            'selected':{'suites':list(C.SUITES),'full_host':False,'include_platform':False}}
        route=P.parent_route_outputs(context)
        needs={'route':{'result':'success','outputs':route},'common-parent':{'result':'success'},
            'platform-tests':{'result':'skipped','outputs':{}}}
        self.package_boundary.validate_wiring=Mock(return_value=P.PLATFORM_GENERATION)
        event,environment=self.push_event(job='qualify-parent')
        with patch.object(P,'_host_policy',return_value=self.policy), \
             patch.object(P,'current_platform_context',return_value=context),patch.object(P,'_platform_bookend'), \
             patch.object(P,'completed_platform_job',side_effect=AssertionError('no unselected platform proof')):
            P.verify_platform_parent(Path('/unexecuted'),event,environment,object(),needs)
            for change in ('pending','failed','skipped-route','candidate','digest','flag','extra','platform-success','platform-pending'):
                value=deepcopy(needs)
                if change=='pending':value['route']['result']='in_progress'
                elif change=='failed':value['route']['result']='failure'
                elif change=='skipped-route':value['route']['result']='skipped'
                elif change=='candidate':value['route']['outputs']['parent_candidate']='b'*40
                elif change=='digest':value['route']['outputs']['parent_plan']='0'*64
                elif change=='flag':value['route']['outputs']['platform_required']='true'
                elif change=='extra':value['route']['outputs']['verified']='true'
                elif change=='platform-success':value['platform-tests']={'result':'success','outputs':{'verified':'false'}}
                else:value['platform-tests']['result']='in_progress'
                with self.subTest(change=change),self.assertRaises(H.Unavailable):
                    P.verify_platform_parent(Path('/unexecuted'),event,environment,object(),value)

    def test_push_planning_skips_strict_only_for_independently_admitted_ci_owner(self):
        import postmerge
        event,environment=self.push_event(job='route')
        _,parent=P.source_admission.actual_bytes(P.ROOT,P.PLATFORM_PARENT_TEMPLATE)
        local={**deepcopy(self.trusted),P.PLATFORM_PARENT_TEMPLATE:parent}
        current={**deepcopy(self.tree),'.github/workflows/parent-qualification.yml':parent}
        self.package_boundary.candidate_plan=Mock(return_value=self.push_plan(current))
        binding={'pull_request':23,'base_ref':self.target,'base_sha':'b'*40,'merge_sha':'a'*40,'merge_tree':'c'*40}
        refs={'target':'a'*40,'default':'d'*40,'default_ref':'main',
            'integration':{'workflow_path':'.github/workflows/parent-qualification.yml'}}
        adapter=SimpleNamespace(_integrated_current=Mock(return_value=(binding,refs)),api=SimpleNamespace(immutable_blob=Mock()))
        selected={'suites':list(C.SUITES),'reason':'reviewed-ci-only-inputs','full_host':False,'include_platform':False}
        profile={'profile':C.PROFILE,'binding':{'generation_kind':C.SEVEN_CONTROLLER_KIND},
            'suites':list(C.SUITES),'selection':selected}
        self.policy.select=Mock(return_value=selected)
        with patch.object(P,'_host_policy',return_value=self.policy), \
             patch.object(postmerge,'full_tree',side_effect=lambda adapter,revision:('c'*40,
                {'a'*40:current,'b'*40:self.base,'d'*40:local}[revision])), \
             patch.object(postmerge,'integrated_controller_for_reuse',return_value='sha256:'+'e'*64), \
             patch.object(postmerge,'integrated_controller',side_effect=AssertionError('unselected plan is not strict execution')) as strict, \
             patch.object(P,'selection_profile_for_reuse',return_value=profile) as derive, \
             patch.object(P.execution,'checkout_identity',side_effect=lambda path:('d'*40,'f'*40) if path==P.ROOT else ('a'*40,'c'*40)), \
             patch.object(P.inputs,'full_tree',side_effect=lambda path,revision:local if path==P.ROOT else current):
            context=P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            self.assertIsNone(context['platform_partition']);derive.assert_called_once();strict.assert_not_called()
            for change in ('kind','profile','selection'):
                changed=deepcopy(profile)
                if change=='kind':changed['binding']['generation_kind']=C.CONTROLLER_KIND
                elif change=='profile':changed['profile']=P.FULL_PROFILE
                else:changed['selection']={**selected,'suites':selected['suites'][1:]}
                derive.return_value=changed
                with self.subTest(change=change),self.assertRaises(H.Unavailable):
                    P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            derive.return_value=profile
            selected['full_host']=True;selected['reason']='reviewed-ci-with-control-plane-update'
            full_profile={**profile,'profile':P.FULL_PROFILE,'binding':None}
            derive.return_value=full_profile
            context=P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            self.assertIsNone(context['platform_partition']);strict.assert_not_called()
            for field,value in (('profile',C.PROFILE),('binding',{'generation_kind':C.SEVEN_CONTROLLER_KIND}),
                    ('selection',{**selected,'include_platform':True})):
                derive.return_value={**full_profile,field:value}
                with self.subTest(full_field=field),self.assertRaises(H.Unavailable):
                    P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            derive.return_value=profile
            selected['full_host']=False
            selected['include_platform']=True
            with self.assertRaisesRegex(AssertionError,'strict execution'):
                P.current_platform_context(Path('/unexecuted'),event,environment,adapter)

    def test_push_nonhost_package_routes_require_complete_plan_and_never_invent_platform(self):
        import postmerge
        event,environment=self.push_event(job='route')
        _,parent=P.source_admission.actual_bytes(P.ROOT,P.PLATFORM_PARENT_TEMPLATE)
        local={**deepcopy(self.trusted),P.PLATFORM_PARENT_TEMPLATE:parent}
        current={**deepcopy(self.tree),'.github/workflows/parent-qualification.yml':parent}
        binding={'pull_request':23,'base_ref':self.target,'base_sha':'b'*40,'merge_sha':'a'*40,'merge_tree':'c'*40}
        refs={'target':'a'*40,'default':'d'*40,'default_ref':'main',
            'integration':{'workflow_path':'.github/workflows/parent-qualification.yml'}}
        adapter=SimpleNamespace(_integrated_current=Mock(return_value=(binding,refs)),api=SimpleNamespace(immutable_blob=Mock()))
        self.policy.select=Mock(side_effect=AssertionError('no host owner for bounded package route'))
        planned=self.package_boundary.candidate_plan=Mock()
        with patch.object(P,'_host_policy',return_value=self.policy), \
             patch.object(postmerge,'full_tree',side_effect=lambda adapter,revision:('c'*40,
                {'a'*40:current,'b'*40:self.base,'d'*40:local}[revision])), \
             patch.object(postmerge,'integrated_controller_for_reuse',return_value='sha256:'+'e'*64), \
             patch.object(postmerge,'integrated_controller',side_effect=AssertionError('no platform execution')), \
             patch.object(P,'selection_profile_for_reuse',side_effect=AssertionError('no shared owner')), \
             patch.object(P.execution,'checkout_identity',side_effect=lambda path:('d'*40,'f'*40) if path==P.ROOT else ('a'*40,'c'*40)), \
             patch.object(P.inputs,'full_tree',side_effect=lambda path,revision:local if path==P.ROOT else current):
            for mode,path in (('documentation','README.md'),('tool-dependencies','tools/jsdoc/package-lock.json'),
                    ('package-dependencies','script-archive/marketplace/S3Server/package-lock.json')):
                self.assertEqual(self.package.select([path],legacy_mode='documentation' if mode=='documentation' else 'full')['host_mode'],mode)
                planned.return_value=self.push_plan(current,mode)
                context=P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
                self.assertIsNone(context['selected']);self.assertIsNone(context['platform_partition'])
                self.assertEqual(P.parent_route_outputs(context)['platform_required'],'false')
                before=P.parent_route_outputs(context)['parent_plan']
                changed=deepcopy(context);changed['package_plan']['plan']='e'*64
                self.assertNotEqual(P.parent_route_outputs(changed)['parent_plan'],before)
            for field,value in (('candidate','f'*40),('tree','f'*40),('base','f'*40),('head','f'*40),
                    ('unknown',True),('paths',[]),('regular',False),('host_mode','unknown'),('host_mode','delegated-sync')):
                planned.return_value={**self.push_plan(current,'documentation'),field:value}
                with self.subTest(field=field,value=value),self.assertRaises(H.Unavailable):
                    P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            planned.return_value=self.push_plan(current,'documentation')
            context=P.current_platform_context(Path('/unexecuted'),event,environment,adapter)
            with patch.object(P,'current_platform_context',return_value={**context,'package_plan':{}}),self.assertRaises(H.Unavailable):
                P._platform_bookend(context,event,environment,adapter)

    def test_empty_parent_profile_requires_native_source_and_exact_skipped_jobs(self):
        import postmerge
        self.package_boundary.validate_wiring=Mock(return_value=P.PLATFORM_GENERATION)
        for target in ('main','apple-main'):
            event,environment=self.push_event(target,job='qualify-parent')
            environment['GITHUB_WORKFLOW_REF']=P.producer_api.REPOSITORY+'/.github/workflows/parent-qualification.yml@refs/heads/'+target
            profile=P.source_admission.ordinary(P.source_admission.SHARED_PROFILE)
            _,template=P.source_admission.actual_bytes(P.ROOT,P.PLATFORM_PARENT_TEMPLATE)
            current={P.source_admission.PROFILE:profile,'.github/workflows/parent-qualification.yml':template}
            local={P.source_admission.PROFILE:profile,P.PLATFORM_PARENT_TEMPLATE:template}
            binding={'base_ref':target,'base_sha':'b'*40}
            refs={'target':'a'*40,'default':'d'*40,'default_ref':'main',
                'integration':{'workflow_path':'.github/workflows/parent-qualification.yml'}}
            adapter=SimpleNamespace(_integrated_current=Mock(return_value=(binding,refs)))
            needs={'route':{'result':'skipped','outputs':{}},'common-parent':{'result':'success'},
                'platform-tests':{'result':'skipped','outputs':{}}}
            with patch.object(P,'_host_policy',return_value=self.policy), \
                 patch.object(postmerge,'full_tree',side_effect=lambda adapter,revision:('c'*40,
                    local if revision=='d'*40 else current)), \
                 patch.object(postmerge,'integrated_controller_for_reuse',return_value='sha256:'+'e'*64), \
                 patch.object(postmerge,'default_authority',return_value={'protected':True}), \
                 patch.object(P.execution,'checkout_identity',side_effect=lambda path:('d'*40,'c'*40) if path==P.ROOT else ('a'*40,'c'*40)), \
                 patch.object(P.inputs,'full_tree',side_effect=lambda path,revision:local if path==P.ROOT else current):
                P.verify_platform_parent(Path('/unexecuted'),event,environment,adapter,needs)
                for change in ('route-success','route-output','platform-success','profile'):
                    value=deepcopy(needs)
                    if change=='route-success':value['route']['result']='success'
                    elif change=='route-output':value['route']['outputs']={'platform_required':'false'}
                    elif change=='platform-success':value['platform-tests']['result']='success'
                    else:current[P.source_admission.PROFILE]={**profile,'mode':'100755'}
                    with self.subTest(target=target,change=change),self.assertRaises(H.Unavailable):
                        P.verify_platform_parent(Path('/unexecuted'),event,environment,adapter,value)
                current[P.source_admission.PROFILE]=profile

    def test_parent_route_outputs_bind_whole_current_plan_and_empty_output_is_finite(self):
        context={'platform_partition':None,'binding':{'base_ref':self.target,'merge_sha':'a'*40},
            'refs':{'target':'a'*40,'default':'d'*40},'controller':'sha256:'+'e'*64,'selected':self.profile['selection']}
        before=P.parent_route_outputs(context)
        for field in ('binding','refs','controller','selected'):
            changed=deepcopy(context)
            if field=='binding':changed[field]['base_sha']='b'*40
            elif field=='refs':changed[field]['default']='f'*40
            elif field=='controller':changed[field]='sha256:'+'f'*64
            else:changed[field]['suites']=changed[field]['suites'][1:]
            with self.subTest(field=field):self.assertNotEqual(P.parent_route_outputs(changed)['parent_plan'],before['parent_plan'])
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'output';output.touch(mode=0o600)
            with patch.dict(P.os.environ,{'GITHUB_OUTPUT':str(output)}):
                P._output(before);P._output({'platform_required':'false','platform_plan':''})
                valid=output.read_bytes()
                for value in ({'platform_required':'true','platform_plan':''},{'receipt_sha256':''},
                        {'receipt_sha256':'a'*40},{'parent_candidate':'not-a-commit'}):
                    with self.subTest(value=value),self.assertRaises(H.Unavailable):P._output(value)
                    self.assertEqual(output.read_bytes(),valid)


if __name__=='__main__':
    unittest.main()
