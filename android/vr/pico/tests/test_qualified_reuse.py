#!/usr/bin/env python3
"""Synthetic origin/receipt negatives using the actual SH009 and Pico validators."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from test_source_inputs import Fixture, SOURCE, ROOT, sha

spec = importlib.util.spec_from_file_location('qualified', ROOT/'android/vr/pico/release/qualified-reuse.py')
Q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Q)

class QualifiedReuse(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.f = Fixture(self.root)
        self.spec = copy.deepcopy(self.f.spec)
        self.spec.update(dependencySourceRevision=SOURCE, attemptRoot=str(self.root),
                         producerSourceFiles={'fixture.py':'a'*64}, coldOrigins=[], localBuilds=[])
        for phase in ('target','host-tools'):
            d = self.root/'cold'/phase
            d.mkdir(parents=True)
            for name in ('closure.json','index.json',phase+'.json',phase+'-expected.json',phase+'.COMPLETE'):
                shutil.copyfile(self.root/name,d/name)
            self.spec['coldOrigins'].append(dict(sourceRevision=SOURCE,phase=phase,
                sourceClosure=f'cold/{phase}/closure.json',recipeIndex=f'cold/{phase}/index.json',
                actualGraph=f'cold/{phase}/{phase}.json',expectedGraph=f'cold/{phase}/{phase}-expected.json',
                checkpoint=f'cold/{phase}/{phase}.COMPLETE'))
            for n in list(self.f.graphs[phase]['graph']['nodes'].values())[1:]:n['binary']='Cache'
            self.f.graph(phase,update_expected=False)

    def run_phase(self):
        return Q.verify(self.spec,lambda p:self.root/p,'target',SOURCE,self.root/'closure.json',self.root/'index.json')

    def test_real_cold_origins_accept_cache_without_relabeling(self):
        r=self.run_phase()
        self.assertTrue(all(n['observedBinary']=='Cache' for n in r['packages']))
        self.assertTrue(all(n['productionSourceRevision']==SOURCE for n in r['packages']))
        self.assertEqual(json.loads((self.root/'target.json').read_text())['graph']['nodes']['1']['binary'],'Cache')

    def test_cache_without_origin_rejected(self):
        self.spec['coldOrigins']=[]
        from artifact_identity import IdentityError
        with self.assertRaisesRegex(IdentityError,'UNPROVEN_CACHE'):self.run_phase()

    def test_successful_new_build_origin_and_failed_receipt(self):
        from artifact_identity import IdentityError
        node=self.f.graphs['target']['graph']['nodes']['1']
        node.update(binary='Build',rrev='1'*32,prev='2'*32)
        node['ref']=node['ref'].split('#')[0]+'#'+'1'*32
        closure=json.loads((self.root/'closure.json').read_text())
        closure['nodes'][0]['recipe_revision']='1'*32
        (self.root/'closure.json').write_text(json.dumps(closure))
        self.f.graph('target',True)
        expected=self.root/'target-expected.json';j=json.loads(expected.read_text())
        for n in list(j['graph']['nodes'].values())[1:]:n['binary']='Build'
        expected.write_text(json.dumps(j))
        for name in ('target.json','target-expected.json','target.COMPLETE'):
            shutil.copyfile(self.root/name,self.root/('fresh-'+name))
        receipt=dict(exitCode=0,sourceRevision=SOURCE,resultSha256=sha(self.root/'fresh-target.json'),
                     expectedGraphSha256=sha(self.root/'fresh-target-expected.json'),network='none',
                     producerSourceFiles=self.spec['producerSourceFiles'])
        (self.root/'receipt.json').write_text(json.dumps(receipt))
        self.spec['localBuilds']=[dict(actualGraph='fresh-target.json',expectedGraph='fresh-target-expected.json',
                                      checkpoint='fresh-target.COMPLETE',receipt='receipt.json')]
        node['binary']='Cache';self.f.graph('target',False)
        self.assertEqual(self.run_phase()['packages'][0]['prev'],'2'*32)
        receipt['exitCode']=1;(self.root/'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(IdentityError,'WORKER_RECEIPT'):self.run_phase()

    def test_reject_short_application_source(self):
        from artifact_identity import IdentityError
        with self.assertRaisesRegex(IdentityError,'APPLICATION_SOURCE'):
            Q.verify(self.spec,lambda p:self.root/p,'target','1234567',self.root/'closure.json',self.root/'index.json')

    def test_reject_unknown_prev_remote_and_skipped_final_node(self):
        from artifact_identity import IdentityError
        for field,value in [('prev','1'*32),('remote','untrusted'),('binary','Skip')]:
            with self.subTest(field=field):
                node=self.f.graphs['target']['graph']['nodes']['1'];old=node.get(field);node[field]=value
                self.f.graph('target',update_expected=False)
                with self.assertRaises(IdentityError):self.run_phase()
                node[field]=old
        self.f.graph('target',update_expected=False)

    def test_reject_forged_build_without_worker_receipt(self):
        from artifact_identity import IdentityError
        self.f.graphs['target']['graph']['nodes']['1']['binary']='Build';self.f.graph('target',False)
        with self.assertRaisesRegex(IdentityError,'MISSING_BUILD_RECEIPT'):self.run_phase()

    def test_reject_original_cold_checkpoint_tampering(self):
        from artifact_identity import IdentityError
        p=self.root/'cold/target/target.COMPLETE';p.write_text(p.read_text().replace(SOURCE,'0'*40))
        with self.assertRaises(IdentityError):self.run_phase()

    def test_new_recipe_even_with_valid_prev_is_not_old_origin(self):
        from artifact_identity import IdentityError
        node=self.f.graphs['target']['graph']['nodes']['1'];node['rrev']='1'*32;node['ref']=node['ref'].split('#')[0]+'#'+'1'*32
        self.f.graph('target',True)
        # Readiness must continue declaring planned Build, not Cache.
        p=self.root/'target-expected.json';j=json.loads(p.read_text())
        for n in list(j['graph']['nodes'].values())[1:]:n['binary']='Build'
        p.write_text(json.dumps(j))
        with self.assertRaises(IdentityError):self.run_phase()

if __name__=='__main__':unittest.main()
