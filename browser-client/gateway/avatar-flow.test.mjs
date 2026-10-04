// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import vm from 'node:vm';
import {EventEmitter} from 'node:events';
import {AvatarSnapshotSender} from './avatar-snapshot-sender.mjs';
import {attachNativeAvatarProjection} from './native-avatar-stdout-projection.mjs';
import {projectAvatarTail,collectAvatarSamples,writeAvatarSamples} from '../tools/curate-avatar-samples.mjs';
const source=readFileSync(new URL('./server.mjs',import.meta.url),'utf8');
function slice(first,last){assert.equal(source.split(first).length,2);assert.equal(source.split(last).length,2);return source.slice(source.indexOf(first),source.indexOf(last));}
const flowSource=slice('function avatarFlowEnabled(session) {','const cookie = request =>');
const environment={env:{OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS:'1'},stdout:{write(){}}};
const functions=vm.runInNewContext(flowSource+'\n({noteAvatarFlow,snapshotAvatarFlow,emitAvatarProjection})',{process:environment});
const plain=value=>JSON.parse(JSON.stringify(value));
const snapshot=owner=>plain(functions.snapshotAvatarFlow(owner));
const value=(target=false)=>({type:'avatars',selfId:'self',avatars:[{id:'peer',displayName:'Native-Lab-Participant',position:target?{x:4,y:1.8,z:2}:{x:3,y:1.8,z:3}}]});
function fixture({sync=false,enabled=true,onHook}={}) {
 let owner,probes=0;const callbacks=[],texts=[];
 const socket={readyState:1,bufferedAmount:0,send(text,callback){texts.push(text);callbacks.push(callback);if(sync)callback();}};
 const sender=new AvatarSnapshotSender(socket,()=>{probes++;return owner;},()=>{},()=>{},enabled?(event,item)=>{onHook?.(event,item);return functions.noteAvatarFlow(sender,event,item);}:undefined);
 const makeOwner=()=>({browser:socket,native:{},permissionRevision:1,permissionsApproved:true,connected:false,closed:false,publicPlace:false,avatarSender:sender,lastNativeMessage:1000,isCurrent(){probes++;return owner===this;}});
 owner=makeOwner();return {socket,sender,texts,callbacks,get owner(){return owner;},probes:()=>probes,replace(){sender.invalidate(owner);owner=makeOwner();return owner;}};
}
function ingress(f,message=value()) {functions.noteAvatarFlow(f.sender,'ingress',{owner:f.owner,message,at:f.owner.lastNativeMessage,currentNative:true});}
function sample(){return {version:1,kind:'sample',at:1000,interstitialState:'unknown',interstitialSignalAgeMs:null,sequence:1,role:'fixture-peer',batchMs:null,publishedPoseAgeMs:null,avatarBuildMs:null,jointNamesMs:null,jointRotationsMs:null,jointTranslationsMs:null,postPublicationPoseDeltaMeters:null,postPublicationProbeMs:null,peerPacketRateHz:null,peerGlobalPositionUpdateRateHz:null,peerSimulationRateHz:null,capturedFixtureTargetDistanceMeters:null,nativeDelivery:null,gatewayDelivery:null};}
const line=row=>Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify(row)+'\n');
function project(row,mode){const child=new EventEmitter();child.stdout=new EventEmitter();const rows=[];attachNativeAvatarProjection(child,{enabled:true,publicPlace:false,mode,emit:text=>rows.push(JSON.parse(text.slice('BROWSER_AVATAR_SAMPLE '.length)))});child.stdout.emit('data',line(row));child.emit('close');return rows;}
function gatewayRow(f){let text;environment.stdout.write=value=>text=value;functions.emitAvatarProjection(f.owner,'BROWSER_AVATAR_SAMPLE '+JSON.stringify(sample())+'\n');return JSON.parse(text.slice('BROWSER_AVATAR_SAMPLE '.length));}

test('received unapproved envelope uses original branch and does not offer',()=>{
 const first="            if(avatarFlowEnabled(session) && message.type==='avatars')";
 const last="            if (message.type === 'pushToTalkState')";
 const body=slice(first,last);
 const receive=vm.runInNewContext('(function(session,native,message){'+body+'return true})',{process:environment,avatarFlowEnabled:vm.runInNewContext(flowSource+'\navatarFlowEnabled',{process:environment}),noteAvatarFlow:functions.noteAvatarFlow});
 const f=fixture();f.owner.permissionsApproved=false;
 assert.equal(receive(f.owner,f.owner.native,value(true)),undefined);
 const state=snapshot(f.owner);assert.equal(state.ingress[1],0);assert.equal(state.ingress[2],false);assert.equal(state.counts[0],1);assert.equal(state.counts[1],0);
 assert.equal(f.sender.pending,null);assert.equal(f.sender.flight,null);
});
test('approved before connected remains accepted and immutable target is captured',()=>{
 const f=fixture();const input=value(true);ingress(f,input);assert.equal(f.sender.offer(f.owner,input,1000),true);input.avatars[0].position.x=99;
 const state=snapshot(f.owner);assert.equal(state.ingress[3],false);assert.equal(state.flight[2],0);assert.equal(state.offer[2],0);assert.equal(JSON.parse(f.texts[0]).avatars[0].position.x,4);
});
test('held old flight and latest complete target pending remain separate',()=>{
 const f=fixture();f.sender.offer(f.owner,value(),1000);f.owner.lastNativeMessage=1600;ingress(f,value(true));f.sender.offer(f.owner,value(true),1600);
 const state=snapshot(f.owner);assert.equal(state.flight[0],1000);assert.equal(state.flight[2],Math.SQRT2);assert.equal(state.pending[0],1600);assert.equal(state.pending[2],0);assert.equal(state.pending[1],Buffer.byteLength(JSON.stringify(value(true))));assert.equal(f.texts.length,1);
});
test('old callback attribution survives replacement and keeps actual token lifetime',()=>{
 const f=fixture();f.sender.offer(f.owner,value(),1000);const newer=f.replace();newer.lastNativeMessage=1600;f.sender.offer(newer,value(true),1600);
 let state=snapshot(newer);assert.equal(state.flight[3],1);assert.equal(state.pending[3],0);
 f.callbacks[0]();newer.lastNativeMessage=2200;state=snapshot(newer);assert.equal(state.callback[3],1);assert.equal(state.flight[3],0);assert.equal(state.counts[6],1);
});
test('synchronous callback precedes write observation without counter equations',()=>{
 const events=[];const f=fixture({sync:true,onHook:event=>events.push(event)});assert.equal(f.sender.offer(f.owner,value(true),1000),true);
 assert.ok(events.indexOf('callback-success')<events.indexOf('write-observed'));const state=snapshot(f.owner);assert.equal(state.callback[2],0);assert.equal(state.flight,null);assert.equal(state.counts[5],1);assert.equal(state.counts[6],1);
});
test('late error closes channel while preserving original retired callback attribution',()=>{
 const f=fixture();f.sender.offer(f.owner,value(),1000);const owner=f.replace();owner.lastNativeMessage=1600;f.sender.offer(owner,value(true),1600);f.callbacks[0](Error('private exception'));
 const state=snapshot(owner);assert.equal(f.sender.closed,true);assert.equal(state.pending,null);assert.equal(state.callback[2],1);assert.equal(state.callback[3],1);assert.equal(state.counts[7],1);
});
test('duplicate callback has no duplicate observation or slot retarget',()=>{
 const f=fixture();f.sender.offer(f.owner,value(),1000);f.callbacks[0]();f.callbacks[0]();assert.equal(snapshot(f.owner).counts[6],1);
});
test('same revision revoke clears pending and old cached snapshot without budget reset',()=>{
 const f=fixture();f.sender.offer(f.owner,value(),1000);snapshot(f.owner);f.owner.lastNativeMessage=1100;f.sender.offer(f.owner,value(true),1100);
 f.owner.permissionsApproved=false;f.sender.invalidate(f.owner);f.owner.permissionsApproved=true;
 assert.equal(snapshot(f.owner),null);assert.equal(f.sender.pending,null);f.owner.lastNativeMessage=1600;
 const state=snapshot(f.owner);assert.equal(state.sequence,2);assert.equal(state.offer[0],0);assert.equal(state.flight[3],1);assert.equal(state.counts[8],1);
});
test('diagnostics do not add authority or socket getter evaluations',()=>{
 const off=fixture({enabled:false}),on=fixture();for(const f of [off,on]){f.sender.offer(f.owner,value(true),1000);f.sender.offer(f.owner,value(),1600);f.callbacks[0]();}
 assert.equal(on.probes(),off.probes());let reads=0;Object.defineProperty(on.socket,'bufferedAmount',{get(){reads++;return 0;}});snapshot(on.owner);assert.equal(reads,0);
});
test('off mode adds no flow field, capture hook or exported row state',()=>{
 const f=fixture({enabled:false});f.sender.offer(f.owner,value(),1000);assert.equal(Object.hasOwn(f.sender,'onFlow'),false);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);assert.equal(Object.hasOwn(f.sender.flight.item,'flowDistance'),false);
});
test('public session does not contribute physical managed event counters',()=>{
 const f=fixture();f.owner.publicPlace=true;f.sender.offer(f.owner,value(true),1000);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);assert.equal(Object.hasOwn(f.sender.flight.item,'flowDistance'),false);assert.equal(snapshot(f.owner),null);
});
test('throwing diagnostic hook leaves original send and callback outcome',()=>{
 const f=fixture({onHook(){throw Error('private');}});assert.equal(f.sender.offer(f.owner,value(true),1000),true);assert.equal(f.texts.length,1);f.callbacks[0]();assert.equal(f.sender.closed,false);
});
test('validated pending assignment remains observed when actual send throws',()=>{
 const f=fixture();f.socket.send=()=>{throw Error('send failed');};assert.throws(()=>f.sender.offer(f.owner,value(true),1000),/send failed/);
 const state=snapshot(f.owner);assert.equal(state.counts[2],1);assert.equal(state.counts[4],1);assert.equal(state.offer[0],3);assert.equal(state.offer[2],null);assert.equal(state.flight,null);
});
test('callback retains fixed primitive metadata and no serialized payload reference',()=>{
 const f=fixture();f.sender.offer(f.owner,value(true),1000);f.callbacks[0]();assert.equal(Object.hasOwn(f.sender.avatarFlow.callback.item,'text'),false);assert.equal(Object.hasOwn(f.sender.avatarFlow.callback.item,'flowDistance'),false);
});
test('128/500 physical budget terminal is sticky across owner replacement',()=>{
 const f=fixture();ingress(f);f.sender.avatarFlow.counts[0]=65535;ingress(f);
 for(let i=0;i<128;i++){f.owner.lastNativeMessage=1000+i*500;const state=snapshot(f.owner);assert.equal(state.sequence,i+1);}
 const owner=f.replace();owner.lastNativeMessage=100000;
 const terminal=snapshot(owner);assert.deepEqual(terminal.censored,[true,true]);assert.equal(terminal.sequence,128);for(const key of ['counts','ingress','offer','flight','pending','callback'])assert.equal(terminal[key],null);
});
test('real emitter -> mode-bound projector -> collector is strict and no wire fields change',()=>{
 const f=fixture();f.sender.offer(f.owner,value(true),1000);const row=gatewayRow(f);assert.equal(row.version,2);assert.equal(row.gatewayAvatarFlow.flight[2],0);
 assert.equal(project(row,'gateway-log').length,1);assert.equal(project(row,'native-child').length,0);assert.equal(project(sample(),'native-child').length,1);assert.equal(project(sample(),'gateway-log').length,0);
 assert.equal(projectAvatarTail(line(row),false,'gateway-log').rows.length,1);assert.equal(projectAvatarTail(line(row),false,'native-child').rows.length,0);
 assert.equal(Object.hasOwn(JSON.parse(f.texts[0]),'gatewayAvatarFlow'),false);
});
test('unknown keys, codes, bytes, null rules and old missing-flow rows refuse',()=>{
 const f=fixture();f.sender.offer(f.owner,value(true),1000);const row=gatewayRow(f);
 const mutations=[r=>delete r.gatewayAvatarFlow,r=>r.extra='private',r=>r.gatewayAvatarFlow.extra=1,r=>r.gatewayAvatarFlow.flight[3]=2,r=>r.gatewayAvatarFlow.flight[1]=50332673,r=>r.gatewayAvatarFlow.counts[0]=65536,r=>r.gatewayAvatarFlow.offer[1]=null,r=>r.gatewayAvatarFlow.censored[1]=true,r=>r.gatewayAvatarFlow.ingress=[1000,-1,true,false,true]];
 for(const change of mutations){const bad=structuredClone(row);change(bad);assert.equal(project(bad,'gateway-log').length,0);}
 assert.throws(()=>projectAvatarTail(line(row),false,'unknown'),/input-refused/);
});

test('received source memory mismatch is observed without adding a connected admission gate',()=>{
 const f=fixture();functions.noteAvatarFlow(f.sender,'ingress',{owner:f.owner,message:value(true),at:1000,currentNative:false});
 const state=snapshot(f.owner);assert.equal(state.ingress[4],false);assert.equal(state.ingress[3],false);assert.equal(f.sender.offer(f.owner,value(true),1000),true);
});
test('callback then throw and reentrant revocation retain original fail and token rules',()=>{
 const f=fixture();f.socket.send=(_text,callback)=>{callback();f.sender.invalidate(f.owner);throw Error('original-after-callback');};
 assert.throws(()=>f.sender.offer(f.owner,value(true),1000),/original-after-callback/);const state=snapshot(f.owner);
 assert.equal(state.counts[6],1);assert.equal(state.counts[5],0);assert.equal(state.counts[4],1);assert.equal(state.callback[3],1);assert.equal(f.sender.closed,true);
});
test('synchronous callback with reentrant newest offer stays bounded pending until original next offer',()=>{
 const f=fixture();let calls=0;
 f.socket.send=(_text,callback)=>{calls++;if(calls===1){f.sender.offer(f.owner,value(true),1600);callback();}};
 assert.equal(f.sender.offer(f.owner,value(),1000),true);assert.equal(calls,1);assert.equal(f.sender.pending.at,1600);
 f.owner.lastNativeMessage=1600;let state=snapshot(f.owner);assert.equal(state.callback[0],1000);assert.equal(state.pending[2],0);
 f.sender.offer(f.owner,value(true),2200);assert.equal(calls,2);assert.equal(f.sender.flight.item.at,2200);
});
test('counter censor is retained even when existing500ms spacing reuses a stored sample',()=>{
 const f=fixture();ingress(f);snapshot(f.owner);f.sender.avatarFlow.counts[0]=65535;ingress(f);f.owner.lastNativeMessage=1100;
 const state=snapshot(f.owner);assert.equal(state.sequence,1);assert.equal(state.at,1000);assert.equal(state.censored[0],true);
});
test('native author v1 remains accepted in both fixed source modes while sample rows cannot fall back',()=>{
 const author={version:1,kind:'author-transmission',at:1000,interstitialState:'unknown',interstitialSignalAgeMs:null,
  cachedMyAvatarSendRateHz:null,cachedAvatarMixerOutPps:null,authorGlobalPositionOutboundKbps:null,authorLocalPositionOutboundKbps:null,statsFreshness:'not-forced-or-established'};
 for(const mode of ['native-child','gateway-log']){assert.equal(project(author,mode).length,1);assert.equal(project({...author,version:2},mode).length,0);}
});
test('actual owned native and gateway files use distinct strict modes and exclusive safe output',async()=>{
 const root=await mkdtemp(join(tmpdir(),'avatar-flow-files-'));await mkdir(join(root,'logs'),{mode:0o700});
 try {
  const f=fixture();f.sender.offer(f.owner,value(true),1000);const gateway=gatewayRow(f);
  await writeFile(join(root,'logs/native.log'),line(sample()),{mode:0o600});await writeFile(join(root,'logs/gateway.log'),line(gateway),{mode:0o600});
  const report=await collectAvatarSamples(root,'a'.repeat(40));assert.equal(report.logs[0].rows[0].version,1);assert.equal(report.logs[1].rows[0].version,2);assert.equal(report.logs[1].rows[0].gatewayAvatarFlow.flight[2],0);
  const output=join(root,'safe.json');await writeAvatarSamples(output,report);assert.equal(JSON.parse(readFileSync(output)).logs[1].rows.length,1);assert.ok(!readFileSync(output,'utf8').includes('Native-Lab-Participant'));
  await assert.rejects(writeAvatarSamples(output,report),{code:'EEXIST'});
  await writeFile(join(root,'logs/gateway.log'),line(sample()),{mode:0o600});const old=await collectAvatarSamples(root,'a'.repeat(40));assert.equal(old.logs[1].rows.length,0);assert.equal(old.logs[1].rejectedMarkerLines,1);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('public interlude invalidation clears stale managed descriptors without counting public events',()=>{
 const f=fixture();f.sender.offer(f.owner,value(true),1000);snapshot(f.owner);const counts=f.sender.avatarFlow.counts.slice();
 f.owner.publicPlace=true;f.sender.invalidate(f.owner);assert.equal(f.sender.avatarFlow.snapshot,null);assert.deepEqual(f.sender.avatarFlow.counts,counts);
 f.owner.publicPlace=false;f.owner.lastNativeMessage=1100;assert.equal(snapshot(f.owner),null);
});
