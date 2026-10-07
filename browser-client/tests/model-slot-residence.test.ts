// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {ModelSlotResidence,MODEL_RESIDENCE_STAGES} from '../src/model-slot-residence';
import {BrowserWorld} from '../src/world';
import {OriginalModelParseWorld as OriginalWorld}from'./fixtures/model-slot-residence-original-parse';
function fixture(){let time=0,reads=0;const abort=new AbortController();const owner=new ModelSlotResidence(abort.signal,()=>{reads++;return time;});return {owner,abort,tick:(n:number)=>{time=n;},reads:()=>reads};}
test('nested exclusive leaf intervals do not double count waiting parents',()=>{
 const f=fixture(),token=f.owner.start({},new AbortController().signal)!;f.tick(2);token.dispatch();f.tick(3);const outer=token.span('fst-template');f.tick(5);const inner=token.span('native-alpha');f.tick(9);inner();f.tick(12);outer();f.tick(15);token.loaderFinished();f.tick(17);const shaders=token.span('graphics-publication');f.tick(22);shaders();token.finish('completed');
 const row=f.owner.snapshot().recent[0];assert.equal(row.residenceMs,22);assert.equal(row.queueMs,2);assert.equal(row.loaderRunMs,13);assert.equal(row.exclusiveLeafWallMs['fst-template'],5);assert.equal(row.exclusiveLeafWallMs['native-alpha'],4);assert.equal(row.exclusiveLeafWallMs['graphics-publication'],5);assert.equal(Object.values(row.exclusiveLeafWallMs).reduce((a,b)=>a+b,0),22);
});
test('real AbortSignal retires current owner, suppresses late spans and finish without more clock reads',()=>{
 const f=fixture(),signal=new AbortController(),token=f.owner.start({},signal.signal)!;token.dispatch();const end=token.span('original-image-dependencies');f.tick(7);signal.abort();const reads=f.reads();f.tick(20);end();token.span('fst-template')();token.finish('completed');assert.equal(f.reads(),reads);assert.deepEqual(f.owner.snapshot().terminals,{completed:0,refused:0,cancelled:1,censored:0});assert.equal(f.owner.snapshot().active,0);
});
test('World revocation is isolated and clears ownership rather than carrying tokens into another collector',()=>{
 const a=fixture(),b=fixture(),object={};a.owner.start(object,new AbortController().signal)!.dispatch();b.owner.start(object,new AbortController().signal)!.dispatch();a.tick(4);a.abort.abort();assert.equal(a.owner.snapshot().active,0);assert.equal(a.owner.get(object),undefined);assert.equal(b.owner.snapshot().active,1);assert.equal(a.owner.start({},new AbortController().signal),undefined);
});
test('512-owner and64-row bounds censor metadata without delaying an application owner',()=>{
 const f=fixture();for(let i=0;i<512;i++){const token=f.owner.start({},new AbortController().signal)!;f.tick(i+1);token.finish('completed');}
 const reads=f.reads();assert.equal(f.owner.start({},new AbortController().signal),undefined);assert.equal(f.reads(),reads);const snapshot=f.owner.snapshot();assert.equal(snapshot.owners,512);assert.equal(snapshot.refusedOwners,1);assert.equal(snapshot.recent.length,64);assert.equal(snapshot.earlierRowsOmitted,448);assert.equal(snapshot.recent[0].ordinal,449);assert.ok(Buffer.byteLength(JSON.stringify(snapshot))<=128*1024);
});
test('invalid or out-of-order observer state censors itself without throwing into owner flow',()=>{
 const f=fixture(),token=f.owner.start({},new AbortController().signal)!,a=token.span('fst-template');token.span('native-alpha');a();assert.equal(f.owner.snapshot().terminals.censored,1);assert.equal(f.owner.snapshot().active,0);assert.doesNotThrow(()=>token.finish('completed'));
 const bad=new ModelSlotResidence(new AbortController().signal,()=>NaN);assert.equal(bad.start({},new AbortController().signal),undefined);assert.equal(bad.snapshot().clockInvalid,1);
});
test('maximum nested spans retire only the observation; no native graph or promise access',()=>{
 const f=fixture(),token=f.owner.start({},new AbortController().signal)!;for(let i=0;i<25;i++)token.span('mapping-metadata');assert.equal(f.owner.snapshot().terminals.censored,1);assert.equal(f.owner.snapshot().maximumNesting,24);
});
test('two owners may overlap in wall time; aggregate is explicitly not end-to-end duration',()=>{
 const f=fixture(),a=f.owner.start({},new AbortController().signal)!,b=f.owner.start({},new AbortController().signal)!;a.dispatch();b.dispatch();const x=a.span('fst-template'),y=b.span('original-image-dependencies');f.tick(10);x();y();a.finish('completed');b.finish('completed');assert.equal(f.owner.snapshot().exclusiveLeafWallMs['fst-template'],10);assert.equal(f.owner.snapshot().exclusiveLeafWallMs['original-image-dependencies'],10);assert.equal(f.owner.snapshot().recent[0].residenceMs,10);
});
test('snapshot fixed scalars contain no owner getters, source labels, URLs or IDs',()=>{
 const f=fixture(),object={get source(){throw Error('must not read');},get name(){throw Error('must not read');}};f.owner.start(object,new AbortController().signal)!.finish('refused');const s=JSON.stringify(f.owner.snapshot());assert.ok(!s.includes('source'));assert.ok(!s.includes('must not read'));assert.deepEqual(Object.keys(f.owner.snapshot().exclusiveLeafWallMs),[...MODEL_RESIDENCE_STAGES]);
});
function world(prototype:object){const object=Object.create(prototype)as BrowserWorld;Object.assign(object,{options:{modelParseTurn:false},abort:new AbortController(),disposed:false,recordLoadPhase:()=>{}});return object as unknown as {parseTexturedModel(manager:THREE.LoadingManager,parse:()=>THREE.Object3D,signal:AbortSignal,weight:number,trace?:ReturnType<ModelSlotResidence['start']>):Promise<THREE.Object3D>};}
test('actual production World parser attributes synchronous parse separately from existing image wait',async()=>{
 const f=fixture(),token=f.owner.start({},new AbortController().signal)!,manager=new THREE.LoadingManager(),group=new THREE.Group();f.tick(1);token.dispatch();const object=world(BrowserWorld.prototype),signal=new AbortController();const promise=object.parseTexturedModel(manager,()=>{manager.itemStart('authored-Image');f.tick(4);return group;},signal.signal,0,token);
 await Promise.resolve();assert.equal(f.owner.snapshot().active,1);f.tick(10);manager.itemEnd('authored-Image');assert.equal(await promise,group);token.loaderFinished();token.finish('completed');const row=f.owner.snapshot().recent[0];assert.equal(row.exclusiveLeafWallMs['fbx-parse'],3);assert.equal(row.exclusiveLeafWallMs['original-image-dependencies'],6);assert.equal(row.residenceMs,10);
});
test('actual original and candidate parser off paths retain same result and original clock call count',async()=>{
 const descriptor=Object.getOwnPropertyDescriptor(globalThis,'performance')!;let reads=0;Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>++reads}});
 try{const execute=async(proto:object)=>{const object=world(proto),manager=new THREE.LoadingManager(),group=new THREE.Group(),signal=new AbortController();const before=reads;assert.equal(await object.parseTexturedModel(manager,()=>group,signal.signal,0),group);return reads-before;};assert.equal(await execute(BrowserWorld.prototype),await execute(OriginalWorld.prototype));}
 finally{Object.defineProperty(globalThis,'performance',descriptor);}
});
test('actual World parser failure preserves original thrown identity and manager accounting',async()=>{
 const f=fixture(),token=f.owner.start({},new AbortController().signal)!,error=new Error('authored failure'),manager=new THREE.LoadingManager(),object=world(BrowserWorld.prototype);token.dispatch();await assert.rejects(object.parseTexturedModel(manager,()=>{throw error;},new AbortController().signal,0,token),e=>e===error);token.finish('refused');assert.equal(f.owner.snapshot().terminals.refused,1);assert.equal(f.owner.snapshot().active,0);
});
import {ModelLoadScheduler}from'../src/model-load-scheduler';
function scheduledWorld(){
 const f=fixture(),root=new THREE.Group(),entity={id:'authored',type:'Model',collisionless:true,dimensions:{x:2,y:2,z:2}},signal=new AbortController(),objects=new Map([['authored',root]]),readers=new WeakMap<THREE.Group,AbortController>();
 const object=Object.create(BrowserWorld.prototype);let ready!:()=>void,complete!:(value:THREE.Group)=>void,publications=0;
 const entered=new Promise<void>(resolve=>{ready=resolve;});
 Object.assign(object,{abort:signal,modelResidence:f.owner,position:new THREE.Vector3(),objects,entities:new Map([['authored',entity]]),modelReaders:readers,modelGeometry:new WeakMap(),meshCollisions:new Map(),disposed:false,modelScheduler:new ModelLoadScheduler({signal:signal.signal}),updateMeshCollision:()=>{publications++;},loadModel:()=>{ready();return new Promise<THREE.Group>(resolve=>{complete=resolve;});}});
 const model=new THREE.Group();model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshBasicMaterial()));
 return {f,root,entity,object,entered,objects,readers,model,complete:(value:THREE.Group)=>complete(value),publications:()=>publications,signal};
}
test('actual queuedModel keeps owner/current transform and six-slot scheduler rules unchanged',async()=>{
 const q=scheduledWorld(),promise=q.object.queuedModel('authored.fbx',q.entity,q.root);await q.entered;assert.equal(q.object.modelScheduler.stats.active,1);q.root.position.x=9;q.f.tick(10);q.complete(q.model);assert.equal(await promise,q.model);assert.equal(q.root.matrixWorld.elements[12],9);assert.equal(q.publications(),1);q.f.owner.get(q.root)!.finish('completed');assert.equal(q.f.owner.snapshot().recent[0].loaderRunMs,10);q.signal.abort();
});
test('actual queuedModel removal/abort retires diagnostic and preserves late owner refusal and cleanup',async()=>{
 const q=scheduledWorld();let disposals=0;const geometry=(q.model.children[0]as THREE.Mesh).geometry;geometry.addEventListener('dispose',()=>{disposals++;});
 const promise=q.object.queuedModel('authored.fbx',q.entity,q.root);const rejected=assert.rejects(promise,(error:unknown)=>error instanceof DOMException&&error.name==='AbortError');await q.entered;q.f.tick(3);q.objects.delete('authored');q.readers.get(q.root)!.abort();await rejected;assert.equal(q.f.owner.snapshot().terminals.cancelled,1);q.complete(q.model);await new Promise(resolve=>setImmediate(resolve));assert.equal(q.publications(),0);assert.equal(disposals,1);assert.equal(q.f.owner.snapshot().terminals.completed,0);q.signal.abort();
});
