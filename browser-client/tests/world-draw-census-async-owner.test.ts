// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {BrowserWorld} from '../src/world';
function fixture(count=3){
 const world:any=Object.create(BrowserWorld.prototype),abort=new AbortController(),objects=new Map<string,T.Object3D>(),entities=new Map<string,Record<string,unknown>>(),signatures=new Map<string,string>();
 let current=true,captures=0,checks=0,clock=0;
 Object.assign(world,{disposed:false,enabled:true,abort,objects,entities,signatures,scene:new T.Scene(),compilingGraphics:0,drawCensusRequest:0,modelScheduler:{stats:{active:0,queued:0}},options:{captureAssetAuthority(){captures++;return{assertCurrent(){checks++;if(!current)throw Error('Private synthetic revocation');}};}}});
 const geometry=new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3)),material=new T.MeshBasicMaterial();
 for(let i=0;i<count;i++){const id='private-owner-'+i,root=new T.Group();root.userData.modelLoaded=true;root.userData.shadersReady=true;root.add(new T.Mesh(geometry,material));objects.set(id,root);entities.set(id,{id,type:'Model'});signatures.set(id,'private-signature-'+i);}
 return{world,objects,entities,signatures,abort,now:()=>clock+=.002,revoke(){current=false;},captures:()=>captures,checks:()=>checks};
}
for(const reason of ['disabled','disposed','aborted','no-authority','capture-refused','active-model','queued-model','compiling','owner-bound','entity-bound'])test('actual async World refuses '+reason+' before iterating source maps',async()=>{
 const f=fixture();let reads=0;for(const map of [f.objects,f.entities])map[Symbol.iterator]=function*(){reads++;yield* Map.prototype.entries.call(this);return undefined;};
 if(reason==='disabled')f.world.enabled=false;if(reason==='disposed')f.world.disposed=true;if(reason==='aborted')f.abort.abort();
 if(reason==='no-authority')f.world.options.captureAssetAuthority=undefined;if(reason==='capture-refused')f.world.options.captureAssetAuthority=()=>{throw Error('Private capture detail');};
 if(reason==='active-model')f.world.modelScheduler.stats.active=1;if(reason==='queued-model')f.world.modelScheduler.stats.queued=1;if(reason==='compiling')f.world.compilingGraphics=1;
 if(reason==='owner-bound')Object.defineProperty(f.objects,'size',{value:1025});if(reason==='entity-bound')Object.defineProperty(f.entities,'size',{value:16385});
 const r=await f.world.getDrawCensusAsync();assert(r.partial);assert(r.reasons['owner-revoked']);assert.equal(r.counts.owners,0);assert.equal(reads,0);assert(!JSON.stringify(r).includes('Private'));
});
test('actual World scans293 settled owners with one captured authority and charged source bookkeeping',async()=>{
 const f=fixture(293),r=await f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});assert.equal(r.partial,false);assert.equal(r.counts.owners,293);assert.equal(r.exactGeometryAndMaterialIdentity.members,293);assert.equal(f.captures(),1);assert(f.checks()>1);assert(r.counts.metadataBytes>293*224);assert(!JSON.stringify(r).includes('private-'));
});
for(const change of ['entity','root','signature','root-ready','root-loaded','root-failed','entity-added','root-added','scene-pose','scene-parent','active','compile','authority'])test('actual async World censors an inter-turn '+change+' change',async()=>{
 const f=fixture(293);let mutated=false;
 // MessageChannel continuation yields to timers; mutate only while its promise is unresolved.
 const pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});
 queueMicrotask(()=>{mutated=true;const id='private-owner-0',root=f.objects.get(id)!;
  if(change==='entity')f.entities.set(id,{...f.entities.get(id)!});if(change==='root')f.objects.set(id,root.clone());if(change==='signature')f.signatures.set(id,'new-private-signature');
  if(change==='root-ready')root.userData.shadersReady=false;if(change==='root-loaded')root.userData.modelLoaded=false;if(change==='root-failed')root.userData.modelFailed=true;
  if(change==='entity-added')f.entities.set('new-private-entity',{type:'Box'});if(change==='root-added')f.objects.set('new-private-root',new T.Group());
  if(change==='scene-pose')f.world.scene.position.x=1;if(change==='scene-parent')new T.Group().add(f.world.scene);
  if(change==='active')f.world.modelScheduler.stats.active=1;if(change==='compile')f.world.compilingGraphics=1;if(change==='authority')f.revoke();
 });
 const r=await pending;assert(mutated);assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert(r.reasons['owner-revision-changed']||r.reasons['owner-revoked']);
});
test('actual World material-child and animation facts retain the existing exclusions',async()=>{
 const f=fixture();f.entities.set('child',{type:'Material',parentID:'private-owner-0'});f.entities.set('private-owner-1',{id:'private-owner-1',type:'Model',animation:{url:'private-animation'}});
 const r=await f.world.getDrawCensusAsync();assert.equal(r.partial,false);assert.equal(r.counts.candidateParts,1);assert.equal(r.reasons['material-child'],1);assert.equal(r.reasons.animation,1);
});
test('source adapter bookkeeping cannot escape the existing aggregate metadata cap',async()=>{
 const f=fixture();const r=await f.world.getDrawCensusAsync({maximumMetadataBytes:1});assert(r.partial);assert(r.reasons['metadata-byte-budget']);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert.equal(r.counts.owners,0);
});
test('rejected dynamic owner pose updates do not invalidate unchanged static candidates',async()=>{
 const f=fixture(293),id='private-owner-0',root=f.objects.get(id)!;
 f.entities.set(id,{id,type:'Model',dynamic:true});
 const pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});
 queueMicrotask(()=>{root.position.x=10;root.quaternion.x=.1;root.matrix.elements[12]=10;root.children[0].position.y=3;root.children[0].matrix.elements[13]=3;root.updateMatrixWorld(true);f.entities.set(id,{id,type:'Model',dynamic:true,position:{x:10,y:0,z:0}});});
 const r=await pending;assert.equal(r.partial,false);assert.equal(r.counts.owners,293);assert.equal(r.counts.candidateParts,292);assert.equal(r.exactGeometryAndMaterialIdentity.members,292);assert.equal(r.reasons.dynamic,1);
});
test('a rejected dynamic owner becoming static still censors every terminal group',async()=>{
 const f=fixture(293),id='private-owner-0';f.entities.set(id,{id,type:'Model',dynamic:true});
 const pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});queueMicrotask(()=>f.entities.set(id,{id,type:'Model',dynamic:false}));
 const r=await pending;assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert(r.reasons['owner-revision-changed']);
});
test('a newer census cancels and releases the earlier borrowed roots before scanning',async()=>{
 const f=fixture(293),pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});await Promise.resolve();
 const replacement=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});
 const old=await pending;assert(old.partial);assert.equal(old.exactGeometryAndMaterialIdentity.groups,0);
 assert.equal((await replacement).partial,false);assert.equal(f.world.drawCensusRun,undefined);assert.equal(f.world.drawCensusAbort,undefined);
 assert.equal((await f.world.getDrawCensusAsync()).partial,false);
});
test('superseded waiting requests never capture graphs or begin another scan',async()=>{
 const f=fixture(293),first=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});await Promise.resolve();
 const waiting=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1}),latest=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});
 assert.equal((await first).partial,true);const replaced=await waiting;assert(replaced.partial);assert.equal(replaced.counts.owners,0);
 assert.equal((await latest).partial,false);assert.equal(f.captures(),2);assert.equal(f.world.drawCensusRun,undefined);
});
test('whole-World abort releases the async census slot and refuses subsequent source iteration',async()=>{
 const f=fixture(293),pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});f.abort.abort();
 const r=await pending;assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert.equal(f.world.drawCensusRun,undefined);assert.equal((await f.world.getDrawCensusAsync()).counts.owners,0);
});
test('disabling the actual World closes an undelivered census task immediately and permits a fresh connected revision',async()=>{
 const f=fixture(293),Original=globalThis.MessageChannel,previousDocument=globalThis.document;
 const closed:number[][]=[];let deliver=false;
 globalThis.MessageChannel=class extends Original {constructor(){super();const pair=[0,0];closed.push(pair);
  const post=this.port2.postMessage.bind(this.port2);this.port2.postMessage=(...args:any[])=>{if(deliver)post(...args as [any]);};
  for(const [index,port]of [this.port1,this.port2].entries()){const close=port.close.bind(port);port.close=()=>{pair[index]++;close();};}
 }};
 Object.assign(f.world,{simulationClock:{reset(){}},keys:new Set(),velocity:new T.Vector3(),touchMove:new T.Vector2(),self:new T.Group(),thirdPerson:false,canvas:{}});
 globalThis.document={pointerLockElement:null} as unknown as Document;
 try{
  const pending=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});await Promise.resolve();
  assert.deepEqual(closed,[[0,0]],'The actual scan is waiting on an undelivered owned task');
  f.world.setEnabled(false);
  assert.deepEqual(closed,[[1,1]],'Both ports close during the disabling call, before awaiting its finalizer');
  const censored=await pending;assert(censored.partial);assert.equal(censored.exactGeometryAndMaterialIdentity.groups,0);
  assert.equal(f.world.drawCensusRun,undefined);assert.equal(f.world.drawCensusAbort,undefined);
  deliver=true;f.world.setEnabled(true);
  const fresh=await f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});assert.equal(fresh.partial,false);assert.equal(fresh.counts.owners,293);
  assert.deepEqual(closed,[[1,1],[1,1]]);assert.equal(f.world.drawCensusRun,undefined);
 }finally{globalThis.MessageChannel=Original;globalThis.document=previousDocument;}
});
