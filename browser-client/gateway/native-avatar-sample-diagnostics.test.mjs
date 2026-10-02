// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('./native-avatar-sample-diagnostics.js',import.meta.url),'utf8');
const bridge=readFileSync(new URL('./native-bridge.js',import.meta.url),'utf8');
const avatarFunction=bridge.slice(bridge.indexOf('    function avatarData('),bridge.indexOf('    function state()'));
function fixture(enabled=true,blocking=true){
 let time=1000,current=true,authority='revision-1',reads=0,nowCalls=0;const logs=[],calls=[],signal=new Set();
 let peerPosition={x:3,y:1.8,z:3};
 const q={x:0,y:0,z:0,w:1},t={x:0,y:0,z:0};
 const peer={displayName:'Native-Lab-Participant',skeletonModelURL:'PRIVATE_URL',orientation:q,scale:1,
  get position(){reads++;return {...peerPosition};},getJointNames(){calls.push('peer-names');return ['Hips'];},
  getJointRotations(){calls.push('peer-rotations');if(blocking){time+=2000;peerPosition={x:4,y:1.8,z:2};}return [q];},
  getJointTranslations(){calls.push('peer-translations');return[t];},getUpdateRate(name){calls.push('peer-rate-'+name);return name?12:30;}};
 const self={displayName:'PRIVATE_NAME',skeletonModelURL:'PRIVATE_URL',position:{x:0,y:0,z:0},orientation:q,scale:1,
  getJointNames(){calls.push('self-names');return ['Hips'];},getJointRotations(){calls.push('self-rotations');if(blocking)time+=400;return[q];},getJointTranslations(){calls.push('self-translations');return[t];}};
 const context={rigCache:{},MyAvatar:self,avatarSampleDiagnostics:null,Date:{now(){nowCalls++;return time;}}};
 vm.runInNewContext(source+'\n'+avatarFunction+'\nthis.sample=avatarData;this.create=createNativeAvatarSampleDiagnostics;',context);
 const window={interstitialModeEnabled:true,interstitialModeChanged:{connect(fn){signal.add(fn);},disconnect(fn){signal.delete(fn);}}};
 const stats={myAvatarSendRate:9,avatarMixerOutPps:10,forceUpdateStats(){throw Error('MUST NOT FORCE');}};
 const diag=enabled?context.create({now(){return time;},current(){return current;},authority(){return authority;},window,stats,print(text){assert(text.startsWith('BROWSER_AVATAR_SAMPLE '));logs.push(JSON.parse(text.slice('BROWSER_AVATAR_SAMPLE '.length)));}}):null;
 context.avatarSampleDiagnostics=diag;
 return{diag,peer,self,logs,calls,signal,context,sample:context.sample,reads:()=>reads,nowCalls:()=>nowCalls,
  advance(n){time+=n;},setCurrent(v){current=v;},setAuthority(v){authority=v;},setPosition(v){peerPosition=v;}};
}
function batch(f){f.diag?.beginBatch();const peer=f.sample('PRIVATE_PEER_ID',f.peer),self=f.sample('PRIVATE_SELF_ID',f.self);f.diag?.published();return JSON.parse(JSON.stringify([peer,self]));}
test('original position and rig order remain unchanged while true blocking reads reveal pose sample age and fresh postpublication delta',()=>{
 const baseline=fixture(false),instrumented=fixture();assert.deepEqual(batch(instrumented),batch(baseline));
 const log=instrumented.logs.find(x=>x.role==='fixture-peer');assert.equal(log.publishedPoseAgeMs,2400);assert.equal(log.jointRotationsMs,2000);assert.equal(log.jointNamesMs,0);assert.equal(log.jointTranslationsMs,0);assert.equal(log.postPublicationPoseDeltaMeters,Math.SQRT2);
 assert.equal(log.peerPacketRateHz,30);assert.equal(log.peerGlobalPositionUpdateRateHz,12);assert.equal(baseline.reads(),1);assert.equal(instrumented.reads(),2);
 assert.deepEqual(instrumented.calls.filter(x=>!x.includes('rate-')),baseline.calls);assert(!JSON.stringify(instrumented.logs).includes('PRIVATE'));
 assert.equal(log.interstitialState,'unknown','Enabled setting must not be inferred as actual active loading state');
});
test('stale raw native avatar position is distinguishable from a old sample whose original rig read blocked',()=>{
 const f=fixture(true,false);batch(f);const log=f.logs.find(x=>x.role==='fixture-peer');assert.equal(log.publishedPoseAgeMs,0);assert.equal(log.postPublicationPoseDeltaMeters,0);assert.equal(log.jointRotationsMs,0);
});
test('sampling is bounded, does not retain peer payload after publication and avoids any probe when no sampled batch is due',()=>{
 const f=fixture(true,false);batch(f);const reads=f.reads(),count=f.logs.length;batch(f);assert.equal(f.logs.length,count);assert.equal(f.reads(),reads+1,'Only the original pose read happens in unsampled batches');
 f.advance(500);batch(f);assert.equal(f.logs.length,count+2);
 for(let i=0;i<300;i++){f.advance(500);batch(f);}assert.equal(f.logs.length,512);
 const before=f.reads();f.advance(500);batch(f);assert.equal(f.logs.length,512);assert.equal(f.reads(),before+1);
});
test('native-empty rig still skips both transform getters and reports no claimed transform timing',()=>{
 const f=fixture();f.peer.getJointNames=()=>[];f.peer.getJointRotations=()=>{throw Error('MUST SKIP');};f.peer.getJointTranslations=()=>{throw Error('MUST SKIP');};batch(f);
 const log=f.logs.find(x=>x.role==='fixture-peer');assert.equal(log.jointRotationsMs,null);assert.equal(log.jointTranslationsMs,null);
});
test('early no-rig-method return keeps its original packet and safe pose diagnostics',()=>{
 const f=fixture(true,false);delete f.peer.getJointNames;const out=batch(f);assert.equal(out[0].jointNames,undefined);assert.equal(f.logs.find(x=>x.role==='fixture-peer').jointNamesMs,null);
});
test('authority revocation between rig sampling and diagnostic publication performs no extra native reads or logs',()=>{
 const f=fixture(true,false);f.diag.beginBatch();f.sample('PRIVATE',f.peer);const reads=f.reads();f.setAuthority('revision-2');f.diag.published();assert.equal(f.reads(),reads);assert.equal(f.logs.length,0);
 f.setCurrent(false);f.diag.beginBatch();assert.equal(f.diag.beginAvatar(),null);
});
test('signal observations are distinct from unrefreshed Stats and stop disconnects the exact callback',()=>{
 const f=fixture(true,false);assert.equal(f.signal.size,1);for(const fn of f.signal)fn(true);batch(f);assert(f.logs.every(x=>x.interstitialState==='active'));
 f.diag.authorObservation();const last=f.logs.at(-1);assert.equal(last.statsFreshness,'not-forced-or-established');assert.equal(last.cachedMyAvatarSendRateHz,9);
 f.diag.stop();f.diag.stop();assert.equal(f.signal.size,0);const count=f.logs.length;batch(f);assert.equal(f.logs.length,count);
});
test('unknown native rate/read errors are not reflected as credentials or fabricated zero rates',()=>{
 const f=fixture(true,false);f.peer.getUpdateRate=()=>{throw Error('PRIVATE_CREDS');};batch(f);const log=f.logs.find(x=>x.role==='fixture-peer');assert.equal(log.peerPacketRateHz,null);assert.equal(log.peerGlobalPositionUpdateRateHz,null);assert(!JSON.stringify(f.logs).includes('PRIVATE'));
});
test('operator-only builder enables only managed native sessions and never adds a browser wire message or changes the peer gate',()=>{
 const server=readFileSync(new URL('./server.mjs',import.meta.url),'utf8');assert(server.includes("avatarSampleDiagnostics: !this.publicPlace && process.env.OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS === '1'"));
 assert(bridge.includes("send({ type: 'avatars', avatars: avatars, selfId: String(MyAvatar.sessionUUID) }); flush();\n            if (avatarSampleDiagnostics) avatarSampleDiagnostics.published();"));
 assert(!source.includes('socket.send'));assert(!source.includes('forceUpdateStats('));assert(!source.includes('sendAvatarDataPacket'));
});

test('pose age includes a blocking orientation getter after the unchanged original position getter',()=>{
 const f=fixture(true,false),q={x:0,y:0,z:0,w:1};Object.defineProperty(f.peer,'orientation',{get(){f.advance(600);return q;}});
 const out=batch(f);assert.deepEqual(out[0].position,{x:3,y:1.8,z:3});assert.equal(f.logs.find(x=>x.role==='fixture-peer').publishedPoseAgeMs,600);
});

test('lab opt-in preparation preserves the exact ordinary author script when disabled and hashes all diagnostic sources in the original journey',()=>{
 const manager=readFileSync(new URL('../lab/manage.py',import.meta.url),'utf8'),participant=readFileSync(new URL('../lab/native-participant.js',import.meta.url),'utf8');
 assert(manager.includes('if os.environ.get("OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS") == "1":'));
 assert(manager.includes('else:\n        shutil.copyfile(SOURCE/"native-participant.js",ROOT/"http/native-participant.js")'));
 assert(manager.includes('"OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS":os.environ.get("OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS", "")'));
 assert(participant.includes('report("command-applied", command);\n            if (avatarSampleDiagnostics) avatarSampleDiagnostics.authorObservation();'));
 const journey=readFileSync(new URL('../tests/integration/real-session.mjs',import.meta.url),'utf8');
 assert(journey.includes("'browser-client/gateway/native-avatar-sample-diagnostics.js'"));assert(journey.includes("'browser-client/lab/manage.py'"));
 assert(journey.includes('await delay(2800);'));assert(journey.includes('const avatars = capturedPeer.avatars;'));assert(journey.includes("'Browser receives second native participant movement'"));
});

test('authority changed by a postpublication pose read prevents later rate reads and printing',()=>{
 const f=fixture(true,false);let reads=0;Object.defineProperty(f.peer,'position',{get(){if(++reads===2)f.setAuthority('revision-2');return{x:3,y:1.8,z:3};}});
 const out=batch(f);assert.equal(out[0].position.x,3);assert.equal(f.logs.length,0);assert(!f.calls.some(x=>x.includes('rate-')));
});
