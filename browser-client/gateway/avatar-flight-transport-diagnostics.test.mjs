// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual current functions, bounded mocks and owned files only. No sockets.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {EventEmitter} from 'node:events';
import {AvatarSnapshotSender} from './avatar-snapshot-sender.mjs';
import {attachNativeAvatarProjection} from './native-avatar-stdout-projection.mjs';
import {projectAvatarTail} from '../tools/curate-avatar-samples.mjs';
const source=readFileSync(new URL('./server.mjs',import.meta.url),'utf8');
function section(first,last){assert.equal(source.split(first).length,2);assert.equal(source.split(last).length,2);return source.slice(source.indexOf(first),source.indexOf(last));}
const functions=section('const send = (socket, value, observe) => {','const cookie = request =>');
const avatar=()=>({type:'avatars',avatars:[{id:'private-id',displayName:'Native-Lab-Participant',position:{x:4,y:1.8,z:2}}]});
function fixture(enabled='1',publicPlace=false){
 let probes=0,currentOwner,ready=1,bytes=0;const callbacks=[],writes=[],reads=[];
 const socket={get readyState(){reads.push('ready');return ready;},get bufferedAmount(){reads.push('buffer');return bytes;},send(text,callback){writes.push(text);if(callback)callbacks.push(callback);}};
 const c={WebSocket:{OPEN:1},Buffer,process:{env:{OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS:enabled},stdout:{write(){}}}};
 vm.createContext(c);vm.runInContext(functions+'\nglobalThis.send=send;',c);
 const sender=new AvatarSnapshotSender(socket,()=>{probes++;return currentOwner;},()=>{},()=>{},['1','passive'].includes(enabled)?(event,item)=>c.noteAvatarFlow(sender,event,item):undefined);
 currentOwner={browser:socket,native:{},permissionRevision:1,permissionsApproved:true,connected:false,closed:false,publicPlace,avatarSender:sender,lastNativeMessage:1000,isCurrent(){probes++;return this===currentOwner;}};
 const f={c,socket,sender,callbacks,writes,reads,get owner(){return currentOwner;},probes:()=>probes,setReady(value){ready=value;},setBytes(value){bytes=value;},register(){c.registerAvatarOtherWrites(currentOwner);},snapshot(){return JSON.parse(JSON.stringify(c.snapshotAvatarFlow(currentOwner)));},replace(){sender.invalidate(currentOwner);currentOwner={...currentOwner,native:{},closed:false,lastNativeMessage:1600};return currentOwner;}};
 return f;
}
const plain=value=>JSON.parse(JSON.stringify(value));
function nativeSample(){return {version:1,kind:'sample',at:1000,interstitialState:'unknown',interstitialSignalAgeMs:null,sequence:1,role:'fixture-peer',batchMs:null,publishedPoseAgeMs:null,avatarBuildMs:null,jointNamesMs:null,jointRotationsMs:null,jointTranslationsMs:null,postPublicationPoseDeltaMeters:null,postPublicationProbeMs:null,peerPacketRateHz:null,peerGlobalPositionUpdateRateHz:null,peerSimulationRateHz:null,capturedFixtureTargetDistanceMeters:null,nativeDelivery:null,gatewayDelivery:null};}
function emitted(f){let line;f.c.process.stdout.write=value=>{line=value;};f.c.emitAvatarProjection(f.owner,'BROWSER_AVATAR_SAMPLE '+JSON.stringify(nativeSample())+'\n');return JSON.parse(line.slice('BROWSER_AVATAR_SAMPLE '.length));}
function projected(value,mode='gateway-log'){
 const child=new EventEmitter();child.stdout=new EventEmitter();const rows=[];
 attachNativeAvatarProjection(child,{enabled:true,publicPlace:false,mode,emit:line=>rows.push(JSON.parse(line.slice('BROWSER_AVATAR_SAMPLE '.length)))});
 child.stdout.emit('data',Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify(value)+'\n'));child.emit('close');return rows;
}

test('desired current same flight transport state differs from old pre-write witness',()=>{
 const f=fixture();f.sender.offer(f.owner,avatar(),1000);const token=f.sender.flight;f.setBytes(1972699);f.reads.length=0;const probes=f.probes();const value=f.snapshot();
 assert.equal(value.version,2);assert.deepEqual(value.transport,[1,1972699]);assert.equal(f.sender.flight,token);assert.deepEqual(f.reads,['ready','buffer']);assert.equal(f.probes(),probes);assert.equal(f.callbacks.length,1);
});
test('sampled transport reads only a held token at the original500ms cadence',()=>{
 const f=fixture();f.sender.offer(f.owner,avatar(),1000);f.reads.length=0;const first=f.snapshot();assert.equal(f.reads.length,2);
 f.owner.lastNativeMessage=1200;f.setBytes(99);assert.deepEqual(f.snapshot(),first);assert.equal(f.reads.length,2);
 f.owner.lastNativeMessage=1500;assert.deepEqual(f.snapshot().transport,[1,99]);assert.equal(f.reads.length,4);
 f.callbacks[0]();f.owner.lastNativeMessage=2000;f.reads.length=0;assert.equal(f.snapshot().transport,null);assert.equal(f.reads.length,0);
});
test('getter failures and bounded unknown values never release or declare healthy flight',()=>{
 for(const name of ['readyState','bufferedAmount']){
  const f=fixture();f.sender.offer(f.owner,avatar(),1000);const token=f.sender.flight;
  Object.defineProperty(f.socket,name,{get(){throw Error('private-error');}});
  const value=f.snapshot();assert.equal(value.transport,null);assert.notEqual(value.flight,null);assert.equal(f.sender.flight,token);assert.equal(f.callbacks.length,1);
 }
 for(const [ready,bytes,expected] of [[7,0,[null,0]],[1,64*1024*1024+1,[1,null]],[true,NaN,[null,null]],[3,0,[3,0]]]){
  const f=fixture();f.sender.offer(f.owner,avatar(),1000);f.setReady(ready);f.setBytes(bytes);assert.deepEqual(f.snapshot().transport,expected);
 }
});
test('reentrant callback replaces token during either getter and entire sample refuses',()=>{
 for(const name of ['readyState','bufferedAmount']){
  const f=fixture();f.sender.offer(f.owner,avatar(),1000);f.sender.offer(f.owner,avatar(),1100);let once=true;
  Object.defineProperty(f.socket,name,{get(){if(once){once=false;f.callbacks[0]();}return name==='readyState'?1:0;}});
  assert.equal(f.snapshot(),null);assert.equal(f.sender.avatarFlow.sequence,0);assert.notEqual(f.sender.flight,null);assert.equal(f.callbacks.length,2);
 }
});
test('reentrant invalidation and pending replacement refuse mixed-token sample',()=>{
 for(const action of ['invalidate','offer']){
  const f=fixture();f.sender.offer(f.owner,avatar(),1000);let once=true;
  Object.defineProperty(f.socket,'bufferedAmount',{get(){if(once){once=false;if(action==='invalidate')f.sender.invalidate(f.owner);else f.sender.offer(f.owner,avatar(),1500);}return 0;}});
  assert.equal(f.snapshot(),null);assert.equal(f.sender.avatarFlow.sequence,0);
 }
});
test('default-off/public snapshots add no getter or WeakMap registration state',()=>{
 for(const [mode,publicPlace]of [['',false],['unknown',false],['1',true]]){
  const f=fixture(mode,publicPlace);f.register();f.c.send(f.socket,{type:'state'});f.reads.length=0;
  Object.defineProperty(f.socket,'bufferedAmount',{get(){throw Error('off-getter');}});
  assert.equal(f.snapshot(),null);assert.equal(vm.runInContext('avatarOtherWrites',f.c),undefined);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);
 }
});
test('actual permissions branch registers after original approval and revision assignment only',()=>{
 const f=fixture();f.owner.permissionsApproved=false;f.owner.permissionRevision=undefined;
 const body=section("            if (message.type === 'permissions') {","            if(avatarFlowEnabled(session) && message.type==='avatars')");
 Object.assign(f.c,{validatePublicPermissions(){},validateNativePermissions(){},clearTimeout(){},sendNative:[]});
 const run=vm.runInContext('(function(session,native,message){'+body+'})',f.c);
 const native={send(){},close(){}};f.owner.permissionPolicy={permissions:{}};f.owner.assets={reset(){}};f.owner.pushToTalk={reset(){}};
 run(f.owner,native,{type:'permissions',permissionRevision:2,permissions:{}});
 assert.equal(f.owner.permissionsApproved,true);assert.equal(f.owner.permissionRevision,2);assert.notEqual(vm.runInContext('avatarOtherWrites',f.c),undefined);
 f.c.send(f.socket,{type:'state'});assert.deepEqual(f.snapshot().otherWrite,[0,16,0,1000,0]);
});
test('native/public/unknown socket writes are untouched and do not become a Browser witness',()=>{
 const f=fixture();f.register();const nativeWrites=[];const native={readyState:1,bufferedAmount:0,send:value=>nativeWrites.push(value)};
 f.c.send(native,{type:'state'});assert.deepEqual(nativeWrites,['{"type":"state"}']);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);
});
test('desired generic SAME serialized UTF8 write metadata and fixed classes',()=>{
 const f=fixture();f.register();const cases=[[{type:'state'},0],[{type:'entities'},1],[{type:'entityUpdates'},1],[{type:'tablet',png:'é'},2],[{type:'private-secret'},3],[{first:1,type:'tablet'},3]];
 for(let i=0;i<cases.length;i++){
  f.owner.lastNativeMessage=1000+i*500;const[value,kind]=cases[i];f.c.send(f.socket,value);const text=f.writes.at(-1);
  assert.equal(text,JSON.stringify(value));assert.deepEqual(f.snapshot().otherWrite,[kind,Buffer.byteLength(text),0,f.owner.lastNativeMessage,0]);
 }
});
test('generic guard/observe/read order and undefined payload behavior retain original semantics',()=>{
 const f=fixture();f.register();for(const bytes of [0,4*1024*1024]){
  f.setBytes(bytes);f.reads.length=0;const previous=f.writes.length,observed=[];f.c.send(f.socket,undefined,(...args)=>observed.push(args));
  assert.deepEqual(f.reads,['ready','buffer']);assert.equal(f.writes.length,previous+(bytes===0?1:0));if(bytes===0)assert.equal(f.writes.at(-1),undefined);
  assert.deepEqual(plain(observed),[[true,bytes,bytes===0]]);
 }
 f.setReady(3);f.reads.length=0;f.c.send(f.socket,{type:'state'});assert.deepEqual(f.reads,['ready']);
});
test('serialization and send exceptions remain original and publish no actual-write witness',()=>{
 const f=fixture();f.register();const value={toJSON(){throw Error('original-serialize');}};
 assert.throws(()=>f.c.send(f.socket,value),/original-serialize/);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);
 f.socket.send=()=>{throw Error('original-send');};assert.throws(()=>f.c.send(f.socket,{type:'state'}),/original-send/);assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);
});
test('serializer/send reentrant revoke-reapproval never commits original metadata',()=>{
 for(const action of ['serializer','send']){
  const f=fixture();f.register();const replace=()=>{f.sender.invalidate(f.owner);f.register();};
  const value=action==='serializer'?{toJSON(){replace();return {type:'tablet'};}}:{type:'tablet'};
  if(action==='send')f.socket.send=text=>{f.writes.push(text);replace();};
  f.c.send(f.socket,value);const s=f.snapshot();assert.equal(s.otherWrite,null);assert.equal(f.writes.at(-1),'{"type":"tablet"}');
 }
});
test('invalidate/close clear binding and last witness without resetting budgets',()=>{
 const f=fixture();f.register();f.c.send(f.socket,{type:'state'});assert.notEqual(f.snapshot().otherWrite,null);
 f.sender.invalidate(f.owner);f.c.send(f.socket,{type:'tablet'});assert.equal(vm.runInContext('avatarOtherWrites.get(globalThis.boundSocket)',Object.assign(f.c,{boundSocket:f.socket})),undefined);
 f.owner.lastNativeMessage=1600;assert.equal(f.snapshot().otherWrite,null);assert.equal(f.sender.avatarFlow.sequence,2);
 f.register();f.c.send(f.socket,{type:'tablet'});f.sender.close();f.owner.lastNativeMessage=2200;assert.equal(f.snapshot().otherWrite,null);
});
test('new owner does not inherit old non-avatar metadata and stale commit cannot retarget',()=>{
 const f=fixture();f.register();f.c.send(f.socket,{type:'tablet'});const old=f.c.beginAvatarOtherWrite(f.socket);f.replace();f.register();
 f.c.commitAvatarOtherWrite(old,'{"type":"state"}',0);f.owner.lastNativeMessage=1600;assert.equal(f.snapshot().otherWrite,null);
 f.c.send(f.socket,{type:'entities'});f.owner.lastNativeMessage=2100;assert.equal(f.snapshot().otherWrite[0],1);
});
test('diagnostic UTF8 cap is nullable without changing generic write admission',()=>{
 const f=fixture();f.register();const at=1000;const captured=f.c.beginAvatarOtherWrite(f.socket);const text='serialized';
 f.c.Buffer={byteLength:()=>48*1024*1024+1025}; // Pure cap branch; no large allocation/send.
 f.c.commitAvatarOtherWrite(captured,text,0);const value=f.snapshot();assert.equal(value.otherWrite[1],null);assert.equal(value.otherWrite[3],at);
 // This direct diagnostic fixture does not send or claim a valid large wire DTO.
});
test('flow128 terminal nulls both additions and throttle does not add getters',()=>{
 const f=fixture();f.register();f.sender.offer(f.owner,avatar(),1000);f.c.send(f.socket,{type:'state'});
 for(let i=0;i<129;i++){f.owner.lastNativeMessage=1000+i*500;f.snapshot();}
 const value=f.snapshot();assert.equal(value.sequence,128);assert.equal(value.censored[1],true);assert.equal(value.transport,null);assert.equal(value.otherWrite,null);assert.equal(value.counts,null);
 assert.equal(f.reads.length,260); // two original pump + two generic +128*two sampled
});
test('strict current gateway mode refuses old inner shape/missing/unknown/private transport',()=>{
 const f=fixture();f.register();f.sender.offer(f.owner,avatar(),1000);f.c.send(f.socket,{type:'tablet'});const good=emitted(f);
 assert.equal(projected(good).length,1);assert.equal(projected(good,'native-child').length,0);
 const controls=[v=>v.gatewayAvatarFlow.version=1,v=>delete v.gatewayAvatarFlow.transport,v=>delete v.gatewayAvatarFlow.otherWrite,v=>v.gatewayAvatarFlow.private='secret',v=>v.gatewayAvatarFlow.transport=[4,0],v=>v.gatewayAvatarFlow.transport=[1,64*1024*1024+1],v=>{v.gatewayAvatarFlow.flight=null;v.gatewayAvatarFlow.transport=[1,0];},v=>v.gatewayAvatarFlow.otherWrite=[4,1,0,1,0],v=>v.gatewayAvatarFlow.otherWrite=[2,0,0,1,0],v=>v.gatewayAvatarFlow.otherWrite=[2,1,4*1024*1024,1,0],v=>v.gatewayAvatarFlow.otherWrite=[2,1,0,1,2]];
 for(const change of controls){const value=structuredClone(good);change(value);assert.equal(projected(value).length,0);}
});
test('actual emitter→strict projector→current unchanged collector preserves finite current role',()=>{
 const f=fixture();f.register();f.sender.offer(f.owner,avatar(),1000);f.setBytes(1234);f.c.send(f.socket,{type:'tablet',png:'private-base64'});const row=emitted(f);const line=Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify(row)+'\n');
 const result=projectAvatarTail(line,false,'gateway-log');assert.equal(result.rows.length,1);assert.equal(result.rows[0].gatewayAvatarFlow.version,2);assert.deepEqual(result.rows[0].gatewayAvatarFlow.transport,[1,1234]);assert.equal(result.rows[0].gatewayAvatarFlow.otherWrite[0],2);assert.ok(!JSON.stringify(result).includes('private-base64'));assert.ok(!JSON.stringify(result).includes('private-id'));
 const native=nativeSample();assert.equal(projected(native,'native-child').length,1);assert.equal(projected({...native,gatewayAvatarFlow:null},'native-child').length,0);
});
test('diagnostic adds no extra original send/member/serializer/observe evaluations',()=>{
 for(const mode of ['','1']){
  const f=fixture(mode);f.register();const order=[];
  Object.defineProperty(f.socket,'send',{get(){order.push('send-member');return function(value){assert.equal(this,f.socket);order.push(['actual-send',value]);};}});
  const value={toJSON(){order.push('serialize');return {type:'state'};}};
  f.c.send(f.socket,value,()=>order.push('observe'));
  assert.deepEqual(order,['send-member','serialize',['actual-send','{"type":"state"}'],'observe']);
 }
});
test('registration and UTF8 diagnostic exceptions are swallowed after actual writes',()=>{
 const f=fixture();const owner=f.owner;Object.defineProperty(owner,'publicPlace',{get(){throw Error('private');},configurable:true});
 assert.doesNotThrow(()=>f.register());assert.equal(vm.runInContext('avatarOtherWrites',f.c),undefined);
 Object.defineProperty(owner,'publicPlace',{value:false});f.register();f.c.Buffer={byteLength(){throw Error('private');}};
 assert.doesNotThrow(()=>f.c.send(f.socket,{type:'tablet'}));assert.equal(f.writes.at(-1),'{"type":"tablet"}');assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);
});
test('public same-socket replacement cannot inherit an approved managed binding',()=>{
 const f=fixture();f.register();f.c.send(f.socket,{type:'state'});f.replace();f.owner.publicPlace=true;f.register();
 f.c.send(f.socket,{type:'tablet'});assert.equal(f.snapshot(),null);f.c.boundSocket=f.socket;
 assert.equal(vm.runInContext('avatarOtherWrites.get(boundSocket)',f.c),undefined);
});
test('current actual native projector→gateway flowv2 emitter→collector keeps original512-row quota',()=>{
 const f=fixture();f.register();f.sender.offer(f.owner,avatar(),1000);f.c.send(f.socket,{type:'tablet'});
 const output=[];f.c.process.stdout.write=text=>output.push(text);const child=new EventEmitter();child.stdout=new EventEmitter();
 attachNativeAvatarProjection(child,{enabled:true,publicPlace:false,emit:line=>f.c.emitAvatarProjection(f.owner,line)});
 for(let i=0;i<513;i++){
  f.owner.lastNativeMessage=1000+i*500;
  child.stdout.emit('data',Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify({...nativeSample(),sequence:Math.min(i+1,512)})+'\n'));
 }
 assert.equal(output.length,512);assert.equal(child.stdout.listenerCount('data'),0);
 const result=projectAvatarTail(Buffer.from(output.join('')),false,'gateway-log');assert.equal(result.rows.length,512);assert.equal(result.rejectedMarkerLines,0);
 assert.equal(result.rows[0].gatewayAvatarFlow.version,2);assert.equal(result.rows[0].gatewayAvatarFlow.transport[0],1);
 const terminal=result.rows.at(-1).gatewayAvatarFlow;assert.equal(terminal.censored[1],true);assert.equal(terminal.transport,null);assert.equal(terminal.otherWrite,null);
});
test('isolated original generic send VM remains byte-exact when no diagnostic binding exists',()=>{
 const text=section('const send = (socket, value, observe) => {','// Uses the already captured');
 const invoke=vm.runInNewContext(text+'\nsend',{WebSocket:{OPEN:1},JSON});const writes=[],observed=[];
 const socket={readyState:1,bufferedAmount:0,send:value=>writes.push(value)};
 invoke(socket,{type:'state'},(...args)=>observed.push(args));invoke(socket,undefined);
 assert.deepEqual(writes,['{"type":"state"}',undefined]);assert.deepEqual(plain(observed),[[true,0,true]]);
});
test('disabled flag after registration cannot count or commit unobserved generic traffic',()=>{
 const f=fixture();f.register();const captured=f.c.beginAvatarOtherWrite(f.socket);f.c.process.env.OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS='';
 f.c.send(f.socket,{type:'tablet'});f.c.commitAvatarOtherWrite(captured,'{"type":"tablet"}',0);
 assert.equal(Object.hasOwn(f.sender,'avatarFlow'),false);assert.equal(f.writes.at(-1),'{"type":"tablet"}');
});
