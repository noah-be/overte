#!/usr/bin/env python3
"""Actual V3 validator with temporary Git histories and synthetic Conan evidence.

No producer, Conan package build, APK or device is invoked. Fixtures prove rejection logic only.
"""
# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from test_source_inputs import Fixture, ROOT, sha, ADAPTER
from artifact_identity import IdentityError

module_spec = importlib.util.spec_from_file_location('pico_v3', ROOT/'android/vr/pico/release/qualified-reuse-v3.py')
V3 = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(V3)


class QualifiedReuseV3(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'evidence'
        self.root.mkdir()
        self.repo = Path(self.temporary.name)/'repository'
        self.repo.mkdir()
        self.fixture = Fixture(self.root)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'V3 fixture')
        # Real Git object identities and byte maps, with explicit fixture producer files.
        for name in ('conanfile.py','android/common/conan/conanfile-pico.py'):
            self.write_repo(name, 'fixture producer\n')
        for name in ('source-closure.lock.json','qt-source.lock.json','qt-license.lock.tsv',
                     'base-toolchain.lock.json','toolchain-provisioning.lock.json','recipe-exports/pkglist.json'):
            self.write_repo(V3.SOURCE_ROOT+'manifests/'+name, '{}')
        for name in ('android/common/conan/patches/qt-pico-android-runtime.patch',
                     V3.SOURCE_ROOT+'recipes/qt/patches/qt-pico-android-runtime.patch'):
            self.write_repo(name, (ROOT/'android/common/conan/patches/qt-pico-android-runtime.patch').read_text())
        self.write_repo('android/vr/pico/conan/openxr-16k', 'fixture scoped configuration\n')
        closure = json.loads((self.root/'closure.json').read_text())
        index = {'recipes': {}}
        for node in closure['nodes']:
            name = V3.SOURCE_ROOT+'manifests/recipe-exports/'+node['reference']+'/export/conanfile.py'
            self.write_repo(name, '# fixture '+node['reference']+'\n')
            digest = sha(self.repo/name)
            index['recipes'][node['reference']] = {'rrev':node['recipe_revision'], 'files':{'export/conanfile.py':digest}}
            node['recipe'] = {'path':name,'sha256':digest,'exported_files':{name:digest}}
            if any(context['graph']=='host-tools' for context in node['contexts']):node['contexts'].append({'graph':'bootstrap'})
        self.write_repo(V3.INDEX, json.dumps(index))
        (self.root/'index.json').write_text(json.dumps(index))
        closure['recipe_export_index']['sha256'] = sha(self.root/'index.json')
        (self.root/'closure.json').write_text(json.dumps(closure))
        self.write_repo(V3.MANIFEST, json.dumps(closure))
        self.git('add', '.')
        self.git('commit', '-qm', 'Historical fixture producer')
        self.old = self.git('rev-parse', 'HEAD').strip()
        self.old_map = V3.git_map(self.repo, self.old)
        self.write_repo('android/common/conan/conanfile-pico.py', 'changed current fixture producer\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Current fixture producer')
        self.current = self.git('rev-parse', 'HEAD').strip()
        self.current_map = V3.git_map(self.repo, self.current)
        self.spec = copy.deepcopy(self.fixture.spec)
        self.spec.update(contract='overte-pico-qualified-inputs-v3', sourceRevision=self.current,
                         dependencySourceRevision=self.current, attemptRoot=str(self.root),
                         producerRevisions={revision:{'sourceRevision':revision,'sourceFiles':files,
                             'sourceFilesSha256':V3.object_hash(files)} for revision,files in
                             ((self.old,self.old_map),(self.current,self.current_map))},
                         coldOrigins=[], localBuilds=[], phases={})
        self.fixture.graphs['bootstrap'] = copy.deepcopy(self.fixture.graphs['host-tools'])
        for phase, graph in self.fixture.graphs.items():
            # The texture/compiler package's dependency provides a real recursive PREV join.
            graph['graph']['nodes']['1']['dependencies']={'2':{'ref':graph['graph']['nodes']['2']['ref']}}
            self.spec['coldOrigins'].append(self.record('cold-'+phase,phase,self.old,graph,cold=True))
            warm = copy.deepcopy(graph)
            for node in list(warm['graph']['nodes'].values())[1:]:node['binary']='Cache'
            self.spec['phases'][phase] = self.record('final-'+phase,phase,self.current,warm)

    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.repo),*args], text=True)

    def write_repo(self, name, text):
        path=self.repo/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_text(text)

    def record(self, name, phase, revision, graph, cold=False, legacy=False):
        root=self.root/name;root.mkdir(exist_ok=True)
        files=self.spec['producerRevisions'][revision]['sourceFiles']
        def write(name, value):
            path=root/name;path.write_text(value if isinstance(value,str) else json.dumps(value));return path
        actual=write('actual.json',graph)
        ready=copy.deepcopy(graph)
        for node in list(ready['graph']['nodes'].values())[1:]:node.update(binary='Build',prev=None)
        write('ready.json',ready)
        shutil.copyfile(self.root/'closure.json',root/'closure.json')
        shutil.copyfile(self.root/'index.json',root/'index.json')
        checkpoint=dict(attempt_root=str(self.root),name=phase,source_commit=revision,
            manifest_sha256=sha(root/'closure.json'),recipe_index_sha256=sha(root/'index.json'),result_sha256=sha(actual),jobs='1')
        write('phase.COMPLETE',''.join(k+'='+v+'\n' for k,v in checkpoint.items()))
        item=dict(sourceRevision=revision,producerSourceFilesSha256=V3.object_hash(files),phase=phase,
                  attemptRoot=str(self.root),actualGraph=name+'/actual.json',expectedGraph=name+'/ready.json',
                  checkpoint=name+'/phase.COMPLETE',sourceClosure=name+'/closure.json',recipeIndex=name+'/index.json')
        item['bindings']={k:sha(self.root/v) for k,v in item.items() if k in
                          ('actualGraph','expectedGraph','checkpoint','sourceClosure','recipeIndex')}
        if not cold:
            receipt=dict(contract='overte-pico-local-producer-receipt-v1' if legacy else 'overte-pico-local-producer-receipt-v3',
                sourceRevision=revision,producerSourceFiles=files,exitCode=0,network='none',jobs=1,
                resultSha256=sha(actual),expectedGraphSha256=sha(root/'ready.json'))
            if not legacy:
                write('build.log','fixture completed Conan invocation\n')
                write('worker.exit','0\n')
                item.update(buildLog=name+'/build.log',workerExit=name+'/worker.exit')
                item['bindings'].update({k:sha(self.root/item[k]) for k in ('buildLog','workerExit')})
                execution=dict(sourceRevision=revision,producerSourceFilesSha256=V3.object_hash(files),
                    configurationSha256=V3.object_hash({}),phase=phase,attemptRoot=str(self.root),
                    bindings=copy.deepcopy(item['bindings']),exitCode=0,network='none',jobs=1,
                    command=['conan','install','fixture'])
                write('invocation.json',execution)
                item['invocation']=name+'/invocation.json';item['bindings']['invocation']=sha(root/'invocation.json')
                receipt.update(producerSourceFilesSha256=V3.object_hash(files),configurationSha256=V3.object_hash({}),
                    checkpointSha256=sha(root/'phase.COMPLETE'),sourceClosureSha256=sha(root/'closure.json'),
                    recipeIndexSha256=sha(root/'index.json'),buildLogSha256=sha(root/'build.log'),
                    workerExitSha256=sha(root/'worker.exit'),invocationSha256=sha(root/'invocation.json'))
            write('receipt.json',receipt)
            item['receipt']=name+'/receipt.json';item['bindings']['receipt']=sha(root/'receipt.json')
        return item

    def verify(self):
        V3.verify_producer_files(self.repo,self.spec)
        return V3.verify(self.spec,lambda path:self.root/path,'target',self.current,
                         self.root/'closure.json',self.root/'index.json',self.repo)

    def change_receipt(self, item, mutate):
        path=self.root/item['receipt'];receipt=json.loads(path.read_text());mutate(receipt)
        path.write_text(json.dumps(receipt));item['bindings']['receipt']=sha(path)

    def test_revision_separated_maps_and_cache_origins(self):
        result=self.verify()
        self.assertNotEqual(self.old_map,self.current_map)
        self.assertTrue(all(row['observedBinary']=='Cache' and row['productionSourceRevision']==self.old for row in result['packages']))
        self.assertEqual(result['dependencySourceRevision'],self.current)
        self.assertEqual(json.loads((self.root/'final-target/actual.json').read_text())['graph']['nodes']['1']['binary'],'Cache')

    def test_linux_host_build_reuse_preserves_recursive_identity(self):
        graph=json.loads((self.root/self.spec['phases']['host-tools']['actualGraph']).read_text())
        for node in list(graph['graph']['nodes'].values())[1:]:node['context']='build'
        self.spec['phases']['host-tools']=self.record('linux-role-final','host-tools',self.current,graph)
        self.verify()
        # Changing a child PREV still invalidates the parent's original dependency proof.
        graph['graph']['nodes']['2']['prev']='3'*32
        self.spec['phases']['host-tools']=self.record('linux-role-changed-child','host-tools',self.current,graph)
        with self.assertRaisesRegex(IdentityError,'UNPROVEN_CACHE'):self.verify()

    def test_linux_role_normalization_does_not_relax_current_readiness(self):
        item=self.spec['phases']['host-tools']
        graph=json.loads((self.root/item['actualGraph']).read_text())
        graph['graph']['nodes']['2']['context']='build'
        item=self.record('role-readiness-mismatch','host-tools',self.current,graph)
        self.spec['phases']['host-tools']=item
        readiness=self.root/item['expectedGraph']
        planned=json.loads(readiness.read_text());planned['graph']['nodes']['2']['context']='host'
        readiness.write_text(json.dumps(planned));item['bindings']['expectedGraph']=sha(readiness)
        self.change_receipt(item,lambda receipt:receipt.update(expectedGraphSha256=sha(readiness)))
        # Pin the changed bytes through the real invocation/receipt, so context itself rejects them.
        invocation=self.root/item['invocation'];execution=json.loads(invocation.read_text())
        execution['bindings']['expectedGraph']=sha(readiness)
        invocation.write_text(json.dumps(execution));item['bindings']['invocation']=sha(invocation)
        self.change_receipt(item,lambda receipt:receipt.update(invocationSha256=sha(invocation)))
        with self.assertRaisesRegex(IdentityError,'PICO_V3_IDENTITY'):self.verify()

    def test_android_role_and_linux_platform_changes_cannot_reuse(self):
        original=copy.deepcopy(self.spec)
        for phase,field,value in (('target','context','build'),('host-tools','arch','aarch64'),
                                  ('host-tools','os','Android')):
            with self.subTest(phase=phase,field=field,value=value):
                graph=json.loads((self.root/original['phases'][phase]['actualGraph']).read_text())
                node=graph['graph']['nodes']['2']
                if field=='context':node[field]=value
                else:node['settings'][field]=value
                self.spec['phases'][phase]=self.record('platform-'+field+'-'+value,phase,self.current,graph)
                with self.assertRaisesRegex(IdentityError,'UNPROVEN_CACHE'):self.verify()
                self.spec=copy.deepcopy(original)

    def test_shared_dependency_dag_is_memoized_without_depth_or_cycle_bypass(self):
        template=copy.deepcopy(self.fixture.graphs['host-tools']['graph']['nodes']['2'])
        nodes={}
        for index in range(45):
            node=copy.deepcopy(template);node['id']=str(index)
            node['dependencies']={str(child):{'ref':template['ref']} for child in (index+1,index+2) if child<45}
            nodes[str(index)]=node
        memo={};digest=V3.semantic_node(nodes,'0',memo=memo)
        self.assertEqual(len(memo),45);self.assertEqual(len(digest),64)
        self.assertEqual(digest,V3.semantic_node(nodes,'0',memo=memo))
        with self.assertRaisesRegex(IdentityError,'DEPENDENCY_DEPTH'):
            V3.semantic_node(nodes,'0',active=tuple('ancestor-'+str(i) for i in range(20)),memo=memo)
        nodes['44']['prev']='9'*32
        self.assertNotEqual(digest,V3.semantic_node(nodes,'0'))
        nodes['44']['dependencies']={'0':{'ref':template['ref']}}
        with self.assertRaisesRegex(IdentityError,'DEPENDENCY_CYCLE'):V3.semantic_node(nodes,'0')

    def test_actual_validator_proves_shared_cache_graph_once_per_node(self):
        graph=copy.deepcopy(self.fixture.graphs['target'])
        template=copy.deepcopy(graph['graph']['nodes']['2'])
        nodes={'0':copy.deepcopy(graph['graph']['nodes']['0'])}
        nodes['0']['dependencies']={'1':{'ref':template['ref']}}
        for index in range(1,46):
            node=copy.deepcopy(template);node['id']=str(index)
            node['dependencies']={str(child):{'ref':template['ref']} for child in (index+1,index+2) if child<=45}
            nodes[str(index)]=node
        graph['graph']['nodes']=nodes
        self.spec['coldOrigins'].append(self.record('shared-cold','target',self.old,graph,cold=True))
        for node in list(nodes.values())[1:]:node['binary']='Cache'
        self.spec['phases']['target']=self.record('shared-final','target',self.current,graph)
        result=self.verify()
        self.assertEqual(len(result['packages']),45)
        self.assertTrue(all(row['productionSourceRevision']==self.old and
                            row['productionSourceFilesSha256']==V3.object_hash(self.old_map)
                            for row in result['packages']))

    def test_evidence_count_is_bounded(self):
        self.spec['coldOrigins']*=65
        with self.assertRaisesRegex(IdentityError,'EVIDENCE_LIMIT'):self.verify()

    def test_map_and_revision_swaps(self):
        for field in ('sourceFiles','sourceRevision'):
            with self.subTest(field=field):
                original=copy.deepcopy(self.spec)
                old=self.spec['producerRevisions'][self.old]
                old[field]=self.current_map if field=='sourceFiles' else self.current
                old['sourceFilesSha256']=V3.object_hash(old['sourceFiles'])
                with self.assertRaises(IdentityError):self.verify()
                self.spec=original

    def test_current_bytes_and_historical_blob_tampering(self):
        self.write_repo('android/common/conan/conanfile-pico.py','tampered\n')
        with self.assertRaisesRegex(IdentityError,'CURRENT_SOURCE_MAP'):self.verify()
        self.write_repo('android/common/conan/conanfile-pico.py','changed current fixture producer\n')
        old=self.spec['producerRevisions'][self.old];old['sourceFiles']['conanfile.py']='1'*64
        old['sourceFilesSha256']=V3.object_hash(old['sourceFiles'])
        with self.assertRaisesRegex(IdentityError,'HISTORICAL_SOURCE_MAP'):self.verify()

    def test_git_tree_is_not_a_producer_commit(self):
        tree=self.git('rev-parse',self.old+'^{tree}').strip()
        with self.assertRaisesRegex(IdentityError,'PRODUCER_COMMIT'):V3.git_map(self.repo,tree)

    def test_missing_final_receipt_and_current_symlink(self):
        item=self.spec['phases']['target'];receipt=item.pop('receipt')
        with self.assertRaisesRegex(IdentityError,'ARTIFACT_REQUIRED'):self.verify()
        item['receipt']=receipt
        path=self.repo/'conanfile.py';data=path.read_bytes();path.unlink()
        destination=Path(self.temporary.name)/'foreign-producer.py';destination.write_bytes(data);path.symlink_to(destination)
        with self.assertRaisesRegex(IdentityError,'CURRENT_SOURCE_MAP'):self.verify()

    def test_historical_receipt_uses_its_own_map(self):
        graph=copy.deepcopy(self.fixture.graphs['target'])
        item=self.record('historical-local','target',self.old,graph,legacy=True)
        self.spec['localBuilds']=[item]
        self.verify()
        self.change_receipt(item,lambda receipt:receipt.update(producerSourceFiles=self.current_map))
        with self.assertRaisesRegex(IdentityError,'WORKER_RECEIPT'):self.verify()

    def test_transport_receipt_is_not_build_evidence(self):
        item=self.spec['phases']['target']
        self.change_receipt(item,lambda receipt:receipt.update(contract='overte-conan-package-transport-v1'))
        with self.assertRaisesRegex(IdentityError,'WORKER_RECEIPT'):self.verify()

    def test_all_final_phases_and_current_receipts_are_required(self):
        for phase in V3.PHASES:
            with self.subTest(phase=phase):
                item=self.spec['phases'].pop(phase)
                with self.assertRaisesRegex(IdentityError,'FINAL_PHASES'):self.verify()
                self.spec['phases'][phase]=item
        item=self.spec['phases']['target']
        self.change_receipt(item,lambda receipt:receipt.update(contract='overte-pico-local-producer-receipt-v1'))
        with self.assertRaisesRegex(IdentityError,'CURRENT_RECEIPT'):self.verify()

    def test_original_artifacts_and_worker_exit_are_bound(self):
        for name in ('actualGraph','expectedGraph','checkpoint','receipt','sourceClosure','recipeIndex','invocation','buildLog','workerExit'):
            with self.subTest(name=name):
                path=self.root/self.spec['phases']['target'][name];data=path.read_bytes();path.write_bytes(data+b' ')
                with self.assertRaisesRegex(IdentityError,'ARTIFACT_BINDING'):self.verify()
                path.write_bytes(data)
        item=self.spec['phases']['target'];path=self.root/item['workerExit'];path.write_text('1\n')
        item['bindings']['workerExit']=sha(path)
        self.change_receipt(item,lambda receipt:receipt.update(workerExitSha256=sha(path)))
        with self.assertRaisesRegex(IdentityError,'WORKER_EXIT'):self.verify()

    def test_invocation_map_and_configuration_rebinding_is_rejected(self):
        item=self.spec['phases']['target']
        for field,value in (('producerSourceFilesSha256',V3.object_hash(self.old_map)),('configurationSha256','a'*64),
                            ('checkpointSha256','b'*64),('exitCode',1),('network','allowed')):
            with self.subTest(field=field):
                original=(self.root/item['receipt']).read_text()
                self.change_receipt(item,lambda receipt:receipt.update({field:value}))
                with self.assertRaises(IdentityError):self.verify()
                (self.root/item['receipt']).write_text(original);item['bindings']['receipt']=sha(self.root/item['receipt'])

    def test_unproven_cache_remote_and_skipped_final(self):
        self.spec['coldOrigins']=[]
        with self.assertRaisesRegex(IdentityError,'UNPROVEN_CACHE'):self.verify()

    def test_transitive_prev_must_match_build_origin(self):
        graph=copy.deepcopy(self.fixture.graphs['target'])
        for node in list(graph['graph']['nodes'].values())[1:]:node['binary']='Skip'
        graph['graph']['nodes']['2'].update(prev='2'*32,binary='Build')
        self.spec['localBuilds']=[self.record('new-child','target',self.current,graph)]
        final=self.spec['phases']['target'];actual=self.root/final['actualGraph']
        nodes=json.loads(actual.read_text());nodes['graph']['nodes']['2']['prev']='2'*32
        # A new proven child binary cannot retroactively change the dependencies of the old parent.
        self.spec['phases']['target']=self.record('changed-child-final','target',self.current,nodes)
        with self.assertRaisesRegex(IdentityError,'UNPROVEN_CACHE'):self.verify()

    def test_wrong_cold_origin_revision_and_map(self):
        item=self.spec['coldOrigins'][0]
        item.update(sourceRevision=self.current,producerSourceFilesSha256=V3.object_hash(self.current_map))
        with self.assertRaises(IdentityError):self.verify()

    def test_real_configuration_git_and_staged_bytes(self):
        item=self.record('configured-old','target',self.old,copy.deepcopy(self.fixture.graphs['target']),legacy=True)
        staged=self.root/'scoped-profile';shutil.copyfile(self.repo/'android/vr/pico/conan/openxr-16k',staged)
        config={'sourceRevision':self.old,'sourcePath':'android/vr/pico/conan/openxr-16k',
                'sha256':sha(staged),'stagedPath':'scoped-profile'}
        item.update(buildConfigurationIds=['openxr-16k'],buildConfigurations={'openxr-16k':config})
        self.change_receipt(item,lambda receipt:receipt.update(buildConfigurationIds=['openxr-16k'],
                                                             buildConfigurations={'openxr-16k':config}))
        self.spec['localBuilds']=[item];self.verify()
        staged.write_text('changed configuration')
        with self.assertRaisesRegex(IdentityError,'CONFIGURATION_BYTES'):self.verify()

    def test_invocation_semantics_survive_rehash_attack(self):
        item=self.spec['phases']['target'];path=self.root/item['invocation']
        execution=json.loads(path.read_text());execution['sourceRevision']=self.old
        path.write_text(json.dumps(execution));item['bindings']['invocation']=sha(path)
        self.change_receipt(item,lambda receipt:receipt.update(invocationSha256=sha(path)))
        with self.assertRaisesRegex(IdentityError,'INVOCATION'):self.verify()

    def test_remote_and_changed_package_origins(self):
        original=copy.deepcopy(self.spec)
        graph=json.loads((self.root/self.spec['phases']['target']['actualGraph']).read_text())
        for field,value in (('remote','untrusted'),('prev','1'*32),('package_id','2'*40)):
            with self.subTest(field=field):
                changed=copy.deepcopy(graph);changed['graph']['nodes']['1'][field]=value
                self.spec['phases']['target']=self.record('changed-'+field,'target',self.current,changed)
                with self.assertRaises(IdentityError):self.verify()
                self.spec=copy.deepcopy(original)

    def test_final_skip_and_origin_revision_swap(self):
        item=self.spec['phases']['target'];graph=json.loads((self.root/item['actualGraph']).read_text())
        graph['graph']['nodes']['2']['binary']='Skip'
        self.spec['phases']['target']=self.record('skipped-final','target',self.current,graph)
        with self.assertRaises(IdentityError):self.verify()

    def prepare_consumer(self):
        # Actual resolver selects packages/tools/QML and verifies all bytes; binaries are fixture ELF headers.
        target=self.fixture.packages['target','qt'];self.fixture.elf(target/'bin/uic',62,True)
        for name in ('qualified-reuse.py','qualified-reuse-v3.py'):
            self.write_repo('android/vr/pico/release/'+name,(ROOT/'android/vr/pico/release'/name).read_text())
        self.write_repo('android/vr/pico/apps/picoInterface/src/main/res/values/qt_dependencies.xml',
                        (ROOT/'android/vr/pico/apps/picoInterface/src/main/res/values/qt_dependencies.xml').read_text())
        self.spec['files']={p.relative_to(self.root).as_posix():sha(p) for p in self.root.rglob('*') if p.is_file()}
        binding=self.root/'binding.json';binding.write_text(json.dumps(self.spec))
        original=ADAPTER.REPO;ADAPTER.REPO=self.repo
        self.addCleanup(setattr,ADAPTER,'REPO',original)
        return binding

    def test_full_existing_consumer_v3_route(self):
        binding=self.prepare_consumer()
        result=ADAPTER.resolve(self.root,binding,sha(binding),self.current)
        self.assertEqual(result['status'],'PICO_INPUT_BYTES_BOUND_NATIVE_VERIFICATION_PENDING')
        self.assertIn('PICO_V3',result['provenance']['target']['qualification'])

    def test_current_source_is_rechecked_after_resolution(self):
        binding=self.prepare_consumer()
        original=subprocess.run
        def changed(command, *args, **kwargs):
            result=original(command,*args,**kwargs)
            if command[:2]==['git','apply']:
                self.write_repo('conanfile.py','late changed producer bytes\n')
            return result
        with patch.object(subprocess,'run',side_effect=changed):
            with self.assertRaisesRegex(IdentityError,'CURRENT_SOURCE_MAP'):
                ADAPTER.resolve(self.root,binding,sha(binding),self.current)


if __name__=='__main__': unittest.main()
