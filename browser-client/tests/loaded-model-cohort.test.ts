// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {LoadedModelCohort} from '../src/loaded-model-cohort';
import {BrowserWorld} from '../src/world';
function fixture(count=3){
 const world:any=Object.create(BrowserWorld.prototype),abort=new AbortController(),objects=new Map<string,T.Group>(),entities=new Map<string,any>(),signatures=new Map<string,string>(),scene=new T.Scene();
 let current=true,captures=0,checks=0,clock=0;
 Object.assign(world,{disposed:false,enabled:true,abort,objects,entities,signatures,scene,compilingGraphics:0,drawCensusRequest:0,modelScheduler:{stats:{active:0,queued:0}},options:{captureAssetAuthority(){captures++;return{assertCurrent(){checks++;if(!current)throw Error('PRIVATE');}};}}});
 const geometry=new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3)),material=new T.MeshBasicMaterial();
 const add=(id:string,type='Model',extra={})=>{const root=new T.Group();root.userData.modelLoaded=true;root.userData.shadersReady=true;root.userData.shaderRevision=1;root.add(new T.Mesh(geometry,material));scene.add(root);objects.set(id,root);entities.set(id,{id,type,position:{x:0,y:0,z:0},rotation:{x:0,y:0,z:0,w:1},...extra});signatures.set(id,'private-signature');return root;};
 for(let i=0;i<count;i++)add('private-'+i);
 return {world,source:{objects,entities,signatures,scene},objects,entities,signatures,scene,abort,add,geometry,material,
 now:()=>clock+=.04,revoke(){current=false;},captures:()=>captures,checks:()=>checks};
}
test('cohort selects at most64 eligible owners, explicitly without world coverage',async()=>{
 const f=fixture(293),r=await f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});
 assert.equal(r.partial,false);assert.equal(r.counts.owners,64);assert.equal(r.exactGeometryAndMaterialIdentity.members,64);
 assert(r.modelCohort.sourcePreparationMs>=0);const {sourcePreparationMs,...scope}=r.modelCohort;
 assert.deepEqual(scope,{scope:'captured-static-loaded-Model-cohort',maximumSelectedOwners:64,selectedOwners:64,eligibleAtCapture:293,modelOwnersAtCapture:293,selectionPartial:true,wholeWorldCoverage:false});
 assert.equal(f.captures(),1);assert(f.checks()>1);assert(!JSON.stringify(r).includes('private-'));
});
test('semantic equality permits reordered plain record clones, excluding irrelevant nonModel/dynamic changes',async()=>{
 const f=fixture(8);f.add('private-box','Box');f.add('private-dynamic','Model',{dynamic:true});
 const pending=f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});
 queueMicrotask(()=>{
  const e=f.entities.get('private-0');f.entities.set('private-0',{rotation:{w:1,z:0,y:0,x:0},position:{z:0,y:0,x:0},type:e.type,id:e.id,name:'IGNORED-NAME'});
  f.entities.set('private-box',{id:'private-box',type:'Box',position:{x:8,y:9,z:1}});
  f.entities.set('private-dynamic',{id:'private-dynamic',type:'Model',dynamic:true,position:{x:99,y:0,z:0}});
 });
 const r=await pending;assert.equal(r.partial,false);assert.equal(r.counts.owners,8);assert.equal(r.exactGeometryAndMaterialIdentity.members,8);
});
for(const change of ['position','rotation','dimensions','visible','velocity','script','animation','textures','user-data','root','signature','status','shader-revision','manual-transform','scene-transform','remove','material-child','prefix-addition','authority'])test('actual World censors selected '+change+' during owned task',async()=>{
 const f=fixture(10),pending=f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});
 queueMicrotask(()=>{const id='private-0',e=f.entities.get(id),root=f.objects.get(id)!;
  if(change==='position')f.entities.set(id,{...e,position:{x:1,y:0,z:0}});
  if(change==='rotation')f.entities.set(id,{...e,rotation:{x:0,y:1,z:0,w:0}});
  if(change==='dimensions')f.entities.set(id,{...e,dimensions:{x:2,y:3,z:4}});
  if(change==='visible')f.entities.set(id,{...e,visible:false});
  if(change==='velocity')f.entities.set(id,{...e,velocity:{x:1,y:0,z:0}});
  if(change==='script')f.entities.set(id,{...e,script:'PRIVATE'});
  if(change==='animation')f.entities.set(id,{...e,animation:{running:true}});
  if(change==='textures')f.entities.set(id,{...e,textures:'PRIVATE'});
  if(change==='user-data')f.entities.set(id,{...e,userData:'PRIVATE'});
  if(change==='root')f.objects.set(id,root.clone());if(change==='signature')f.signatures.set(id,'changed');
  if(change==='status')root.userData.shadersReady=false;if(change==='shader-revision')root.userData.shaderRevision=2;
  if(change==='manual-transform')root.position.x=4;if(change==='scene-transform')f.scene.scale.x=2;
  if(change==='remove')f.entities.delete(id);
  if(change==='material-child')f.entities.set('new-child',{id:'new-child',type:'Material',parentID:id});
  if(change==='prefix-addition')f.add('new-private-model');if(change==='authority')f.revoke();
 });
 const r=await pending;assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert.equal(r.exactGeometryAndAuditedMaterialValues.groups,0);
});
test('disjoint ready-model additions after the already capped prefix do not change its explicit membership',()=>{
 const f=fixture(64),cohort=new LoadedModelCohort(f.source);f.add('outside-selected-prefix');assert(cohort.current());assert.equal(cohort.reportScope.eligibleAtCapture,64);cohort.release();
});
test('source accessors refuse without invoking model getter or exposing private exceptions',async()=>{
 const f=fixture(),entity=f.entities.get('private-0');let getters=0;Object.defineProperty(entity,'position',{get(){getters++;throw Error('PRIVATE');}});
 const r=await f.world.getLoadedModelCohortCensusAsync();assert(r.partial);assert.equal(r.counts.owners,0);assert.equal(getters,0);assert(!JSON.stringify(r).includes('PRIVATE'));
});
test('source metadata cap remains charged and cannot be increased or bypassed by the scope adapter',async()=>{
 const f=fixture(),r=await f.world.getLoadedModelCohortCensusAsync({maximumMetadataBytes:1});assert(r.partial);assert.equal(r.counts.owners,0);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);
 await assert.rejects(f.world.getLoadedModelCohortCensusAsync({maximumMetadataBytes:2097153}),/Invalid draw census bound/);
});
for(const field of ['geometry','material','sampler','attribute-bytes'])test('full existing resource verification still censors watched '+field+' mutation',async()=>{
 const f=fixture(64),mesh=f.objects.get('private-0')!.children[0] as T.Mesh;
 f.material.map=new T.Texture();let turns=0;
 // Mutate only after the first owner has been watched, via the actual continuation hook.
 const Original=globalThis.MessageChannel;
 globalThis.MessageChannel=class extends Original {constructor(){super();const post=this.port2.postMessage.bind(this.port2);this.port2.postMessage=(value:any)=>{
  if(++turns===25){if(field==='geometry')mesh.geometry=mesh.geometry.clone();if(field==='material')mesh.material=f.material.clone();if(field==='sampler')f.material.map!.wrapS=T.RepeatWrapping;if(field==='attribute-bytes')f.geometry.attributes.position.setX(0,99);}
  post(value);
 };}};
 try{const r=await f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});assert(turns>=25);assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);}
 finally{globalThis.MessageChannel=Original;}
});
test('cohort release is immediate/idempotent and cannot publish stale source owners',()=>{
 const f=fixture(),cohort=new LoadedModelCohort(f.source);assert(cohort.current());cohort.release();cohort.release();assert.equal(cohort.current(),false);assert.equal(cohort.owners().length,0);
});
test('a fresh wholeWorld census replaces an undelivered model cohort only after both owned ports release',async()=>{
 const f=fixture(64),Original=globalThis.MessageChannel;let deliver=false;const closed:number[][]=[];
 globalThis.MessageChannel=class extends Original {constructor(){super();const pair=[0,0];closed.push(pair);const post=this.port2.postMessage.bind(this.port2);this.port2.postMessage=(v:any)=>{if(deliver)post(v);};for(const [i,p]of [this.port1,this.port2].entries()){const close=p.close.bind(p);p.close=()=>{pair[i]++;close();};}}};
 try{const old=f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});await Promise.resolve();assert.deepEqual(closed,[[0,0]]);
  deliver=true;const fresh=f.world.getDrawCensusAsync({now:f.now,maximumSliceMs:1});assert.deepEqual(closed,[[1,1]]);
  assert((await old).partial);assert.equal((await fresh).partial,false);assert.equal(f.world.drawCensusRun,undefined);assert.equal(f.world.drawCensusAbort,undefined);
 }finally{globalThis.MessageChannel=Original;}
});
test('world abort releases cohort task slot without scanning or publishing a fresh revoked cohort',async()=>{
 const f=fixture(64),pending=f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});f.abort.abort();assert((await pending).partial);assert.equal(f.world.drawCensusRun,undefined);assert.equal((await f.world.getLoadedModelCohortCensusAsync()).counts.owners,0);
});

test('scope cannot raise original CPU or five-second wall bounds and clears its request slot on invalid limits',async()=>{
 const f=fixture();for(const limits of [{maximumWallMs:5001},{maximumTotalCpuMs:2001},{maximumWallMs:0},{maximumTotalCpuMs:NaN}]){
  await assert.rejects(f.world.getLoadedModelCohortCensusAsync(limits),/Invalid Model cohort/);
  assert.equal(f.world.drawCensusRun,undefined);assert.equal(f.world.drawCensusAbort,undefined);
 }
});
test('successful report deducts source preparation from the same bounded continuation budgets',async()=>{
 const f=fixture(),r=await f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumWallMs:5000,maximumTotalCpuMs:1500});
 assert.equal(r.partial,false);assert(r.modelCohort.sourcePreparationMs>0);
 assert(r.scheduling.maximumWallMs<=Math.floor(5000-r.modelCohort.sourcePreparationMs));
 assert(r.scheduling.maximumTotalCpuMs<=Math.floor(1500-r.modelCohort.sourcePreparationMs));
});

for(const field of ['objects','entities','signatures','scene'])test('World source '+field+' identity replacement revokes selected cohort rather than retaining detached snapshots',async()=>{
 const f=fixture(64),pending=f.world.getLoadedModelCohortCensusAsync({now:f.now,maximumSliceMs:1});
 queueMicrotask(()=>{f.world[field]=field==='scene'?new T.Scene():new Map(f.world[field]);});
 const r=await pending;assert(r.partial);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);
});
test('scene parent accessor is refused without executing foreign getter',async()=>{
 const f=fixture();let read=0;Object.defineProperty(f.scene,'parent',{get(){read++;return null;}});
 const r=await f.world.getLoadedModelCohortCensusAsync();assert(r.partial);assert.equal(read,0);
});
