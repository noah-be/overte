#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pure curation contracts, not native domain integration evidence."""
import importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('curate',Path(__file__).with_name('curate-core-journey.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CurationTests(unittest.TestCase):
    def fixture(self):
        return {'completed':True,'syntheticMicrophone':True,'durationSeconds':0,
                'browserVersion':'firefox/156.0','nativeVersion':'2026.04.1',
                'startedAt':'2026-10-01T01:02:03.456Z',
                'checkpoints':[{'name':name,'at':'2026-10-01T01:02:03.456Z'} for name in module.CHECKPOINTS]}
    def test_explicit_completed_short_synthetic_journey_preserves_named_proof(self):
        result=module.curate(self.fixture(),'firefox')
        self.assertTrue(result['completed']);self.assertEqual(result['status'],'passed')
        self.assertEqual(result['browserVersion'],'firefox/156.0')
        self.assertEqual(len(result['checkpoints']),18)
    def test_identifiers_credentials_paths_logs_and_input_labels_are_dropped(self):
        raw=self.fixture();secret='PRIVATE_SENTINEL_DO_NOT_PUBLISH'
        raw.update(error=secret,domain=secret,profile=secret,administratorPassword=secret)
        raw['checkpoints'][0].update(pose={'displayName':secret},nativeSelfId=secret,events=[secret],source=secret)
        raw['checkpoints'][8].update(input=secret,browser={'deviceLabel':secret},nativeOutput={'rms':.12,'peak':.5,'device':secret})
        raw['sourceSHA256']={'/private/'+secret:'a'*64,'browser-client/gateway/server.mjs':'b'*64}
        result=module.curate(raw,'chromium')
        self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(result['checkpoints'][8]['nativeOutput'],{'rms':.12,'peak':.5})
        self.assertEqual(result['sourceSHA256'],{'browser-client/gateway/server.mjs':'b'*64})
    def test_incomplete_wrong_audio_and_endurance_cannot_be_presented_as_passed(self):
        for key,value in [('completed',False),('syntheticMicrophone',False),('durationSeconds',1800)]:
            raw=self.fixture();raw[key]=value;self.assertFalse(module.curate(raw,'chromium')['completed'])
        raw=self.fixture();raw['checkpoints'].pop();self.assertFalse(module.curate(raw,'chromium')['completed'])
    def test_invalid_and_unbounded_fields_do_not_leak_or_define_metrics(self):
        raw=self.fixture();raw['browserVersion']='/private/device';raw['startedAt']='private'
        raw['checkpoints'][2].update(before={'x':0,'y':0,'z':0},after={'x':3,'y':0,'z':4},performance={'fps':float('nan'),'drawCalls':9,'device':'private'})
        result=module.curate(raw,'chromium')
        self.assertNotIn('browserVersion',result);self.assertNotIn('startedAt',result)
        self.assertEqual(result['checkpoints'][2]['distanceMeters'],5)
        self.assertEqual(result['checkpoints'][2]['renderPerformance'],{'drawCalls':9})
        raw['checkpoints']=[{}]*257
        with self.assertRaises(ValueError):module.curate(raw,'chromium')
    def test_commit_attestation_requires_exact_sha_and_cannot_publish_arbitrary_text(self):
        self.assertEqual(module.checked_commit('a'*40),'a'*40)
        for value in ('/private/secret','a'*64,'A'*40,'a'*40+'\n'):
            with self.assertRaises(ValueError):module.checked_commit(value)
    def test_owned_audio_helper_hash_is_retained_without_broadening_paths(self):
        raw=self.fixture()
        runtime='browser-client/tests/integration/owned-audio-process.mjs'
        digest='0f4ed9d41c59e5af93a7bc5451ab09d10c15ce05dbd440f5551b3d79974867a8'
        raw['sourceSHA256']={runtime:digest,
            '/private/profile/owned-audio-process.mjs':'a'*64,
            'browser-client/tests/integration/unapproved-audio-helper.mjs':'b'*64,
            runtime+'/child':'c'*64,
            'browser-client/tests/integration/../private/token':'d'*64}
        self.assertEqual(module.curate(raw,'chromium')['sourceSHA256'],{runtime:digest})
    def test_owned_audio_helper_still_requires_exact_digest(self):
        raw=self.fixture()
        runtime='browser-client/tests/integration/owned-audio-process.mjs'
        for invalid in ('PRIVATE_SENTINEL','0'*63,'A'*64,'0'*64+'\n'):
            raw['sourceSHA256']={runtime:invalid}
            self.assertEqual(module.curate(raw,'firefox')['sourceSHA256'],{})
    def test_native_peer_diagnostic_is_optional_and_cannot_change_journey_acceptance(self):
        raw=self.fixture();raw['nativePeerMovementDiagnostic']={
            'browser':{'snapshotPresent':True,'snapshotAgeMs':25,'avatarCount':2,'peerCount':1,
                'fixtureNameMatchCount':1,'peerProjectionTruncated':False,
                'peers':[{'fixtureNameMatch':True,'targetDistance':0}]},
            'native':{'status':'read','commandSequenceMatched':True,'commandAppliedAtMs':1791000000000,
                'observationAtMs':1791000001000,'observationTargetDistance':0,'bytesRead':4096}}
        result=module.curate(raw,'chromium');self.assertTrue(result['completed'])
        self.assertEqual(result['nativePeerMovementDiagnostic']['native']['commandAppliedAtMs'],1791000000000)
        raw['completed']=False
        self.assertFalse(module.curate(raw,'chromium')['completed'])
    def test_native_peer_diagnostic_drops_private_strings_and_bounds_rows_and_numbers(self):
        raw=self.fixture();secret='PRIVATE_SENTINEL'
        raw['nativePeerMovementDiagnostic']={'path':secret,'browser':{
            'snapshotAgeMs':float('inf'),'peerCount':-1,'displayName':secret,
            'peers':[{'fixtureNameMatch':True,'targetDistance':.1,'id':secret,'displayName':secret}]*100},
            'native':{'status':secret,'commandSequenceMatched':secret,'commandAppliedAtMs':float('nan'),
                'bytesRead':1048577,'rawLog':secret}}
        result=module.curate(raw,'firefox')['nativePeerMovementDiagnostic']
        self.assertNotIn(secret,json.dumps(result));self.assertEqual(len(result['browser']['peers']),16)
        self.assertIsNone(result['browser']['snapshotAgeMs']);self.assertIsNone(result['native']['bytesRead'])
        self.assertNotIn('status',result['native']);self.assertNotIn('commandSequenceMatched',result['native'])
    def test_native_peer_source_hashes_require_only_the_exact_reviewed_paths(self):
        raw=self.fixture();valid=('browser-client/tests/integration/native-peer-diagnostic.mjs','browser-client/lab/native-participant.js')
        raw['sourceSHA256']={key:'a'*64 for key in valid}
        raw['sourceSHA256']['/private/native-peer-diagnostic.mjs']='b'*64
        self.assertEqual(module.curate(raw,'chromium')['sourceSHA256'],{key:'a'*64 for key in valid})
    def test_empty_report_is_not_run_and_invalid_engine_is_rejected(self):
        self.assertEqual(module.curate({},'chromium')['status'],'not-run')
        with self.assertRaises(ValueError):module.curate({},'unexpected')

    def test_actual_native_producer_to_curator_preserves_separate_clock_references(self):
        import subprocess
        helper=Path(__file__).resolve().parents[1]/'tests/integration/native-peer-diagnostic.mjs'
        code="""import {projectNativePeerLog}from %s;
const sequence=1791077071000,target={x:4,y:1.8,z:2};
const text='BROWSER_LAB '+JSON.stringify({kind:'command-applied',at:sequence+300,data:{sequence,position:target,private:'PRIVATE'}})+'\\n';
process.stdout.write(JSON.stringify(projectNativePeerLog(text,{sequence,target,now:sequence+3200})));"""%json.dumps(helper.as_uri())
        child=subprocess.run(['node','--input-type=module','--eval',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(child.returncode,0);native=json.loads(child.stdout)
        raw=self.fixture();raw['nativePeerMovementDiagnostic']={'native':native}
        result=module.curate(raw,'chrome')['nativePeerMovementDiagnostic']['native']
        self.assertEqual(result['commandIssuedAtMs'],1791077071000)
        self.assertEqual(result['diagnosticReadAtMs'],1791077074200)
        self.assertEqual(result['commandAppliedAtMs'],1791077071300)
        self.assertTrue(module.curate(raw,'chrome')['completed']);self.assertNotIn('PRIVATE',json.dumps(result))
    def test_clock_projection_unknowns_and_nonfinite_values_cannot_define_timestamps(self):
        raw=self.fixture()
        for value in ('PRIVATE',True,False,-1,float('nan'),float('inf'),1e15+1):
            raw['nativePeerMovementDiagnostic']={'native':{'commandIssuedAtMs':value,'diagnosticReadAtMs':value,'unknownClock':'PRIVATE'}}
            result=module.curate(raw,'chrome')['nativePeerMovementDiagnostic']['native']
            self.assertIsNone(result['commandIssuedAtMs']);self.assertIsNone(result['diagnosticReadAtMs']);self.assertNotIn('PRIVATE',json.dumps(result))
    def test_new_clock_fields_are_optional_diagnostics_and_never_turn_failed_core_green(self):
        raw=self.fixture();raw['completed']=False
        raw['nativePeerMovementDiagnostic']={'native':{'commandIssuedAtMs':123,'diagnosticReadAtMs':456}}
        self.assertFalse(module.curate(raw,'chrome')['completed'])
        raw['nativePeerMovementDiagnostic']={'native':{'status':'missing'}}
        result=module.curate(raw,'chrome')['nativePeerMovementDiagnostic']['native']
        self.assertIsNone(result['commandIssuedAtMs']);self.assertIsNone(result['diagnosticReadAtMs'])

if __name__=='__main__':unittest.main()
