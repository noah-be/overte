// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Executes actual World→prepared-cache→graph memo→Three FBX parser→FST material
// assignments. Only HTTP, worker transport and image decode are I/O boundaries.
import test from 'node:test';
import assert from 'node:assert/strict';
import {Loader,LoadingManager,Group,Mesh,Texture} from 'three';
import {BrowserWorld} from '../src/world';
import {FstGraphCache} from '../src/fst-graph-cache';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {ModelResources} from '../src/model-resources';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const load=BrowserWorld.prototype as unknown as {loadModel(source:string,visited:Set<string>,base:undefined,signal:AbortSignal,publish:(model:Group)=>void):Promise<Group>};
const wait=async(predicate:()=>boolean)=>{for(let i=0;i<1000;i++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}assert.fail('Actual mapped consumer did not reach its required image stage');};
for(const kind of ['zero','unknown','positive'] as const)test(`actual repeated ${kind} mapped consumers share one inspection and preparation with independently owned geometry/materials`,async t=>{
 const world=Object.create(BrowserWorld.prototype),owner=new AbortController(),memo=new FstGraphCache(owner.signal);
 const bytes=fstTextureAdmissionFbx({nativeEndRecords:true,withoutOriginalTextures:kind==='zero',ambiguousID:kind==='unknown'?'negative':undefined}),before=bytes.slice(0);
 const finishes:Array<(texture:Texture)=>void>=[],published:Group[]=[],requests:string[]=[],returned:Group[]=[];
 let fetches=0,prepares=0,authorityChecks=0,revoked=false;
 class Images extends Loader{load(url:string){requests.push(this.path+url);return new Texture({width:1,height:1});}}
 Object.assign(world,{abort:owner,disposed:false,nativeCullDefaults:false,loadManagers:new Set(),preparedFbx:new PreparedFbxCache({signal:owner.signal}),fstGraphCache:memo,
  imageCache:{loader:(manager:LoadingManager)=>new Images(manager)},
  fbxPreparePool:{prepare:async(buffer:ArrayBuffer)=>{prepares++;return{buffer,phases:{materialBindingsMs:0,decodeMs:0}};}},
  options:{resolveAsset:(url:string)=>url,onStatus(){},captureAssetAuthority:()=>({generation:'same-active-visitor',assertCurrent(){authorityChecks++;owner.signal.throwIfAborted();if(revoked)throw new DOMException('Old authority','AbortError');}})},
  sourceText:async(url:string)=>url.split('?')[0].endsWith('.fst')?'filename = same.fbx\nmaterialMap = '+JSON.stringify([{all:'replacement.json#Replacement'}]):JSON.stringify({materials:[{name:'Replacement',unlit:true,albedoMap:'replacement.png'}]}),
  texture:async()=>new Promise<Texture>(resolve=>finishes.push(resolve)),configureAlpha:async()=>{},recordLoadPhase(){},recordLoadDuration(){},
 });
 t.mock.method(globalThis,'fetch',async(input:unknown)=>{assert.equal(String(input),'https://approved.example/same.fbx');fetches++;return new Response(bytes.slice(0));});
 const loads=Array.from({length:6},(_,i)=>load.loadModel.call(world,`https://approved.example/mapped.fst?consumer=${i}`,new Set(),undefined,owner.signal,model=>published.push(model)));
 try{
  await wait(()=>finishes.length===6);
  assert.equal(fetches,1);assert.equal(prepares,1);assert.equal(memo.stats.inspections,1);
  if(kind==='positive'){assert.equal(published.length,0);assert.equal(requests.length,0);}
  else{assert.equal(published.length,6);assert.equal(requests.length,kind==='zero'?0:18);for(const model of published){let vertices=0;model.traverse(object=>{if(object instanceof Mesh)vertices+=object.geometry.attributes.position.count;});assert.equal(vertices,6);}}
  for(const finish of finishes)finish(new Texture({width:1,height:1}));returned.push(...await Promise.all(loads));
  assert.equal(new Set(returned).size,6);assert.equal(memo.stats.inspections,1);assert.equal(memo.stats.hits,kind==='positive'?11:5);
  const geometries=new Set(),materials=new Set(),maps=new Set();for(const model of returned)model.traverse(object=>{if(object instanceof Mesh){geometries.add(object.geometry);for(const material of Array.isArray(object.material)?object.material:[object.material]){materials.add(material);if((material as any).map)maps.add((material as any).map);}}});
  assert.equal(geometries.size,6);assert.equal(materials.size,12);assert.equal(maps.size,6);assert(authorityChecks>=6*4,'Every consumer must still check actual authority around asynchronous work');
  const stats=memo.stats;revoked=true;await assert.rejects(load.loadModel.call(world,'https://approved.example/mapped.fst?consumer=revoked',new Set(),undefined,owner.signal,()=>assert.fail('Revoked geometry published')),{name:'AbortError'});
  assert.deepEqual(memo.stats,stats,'A memo hit cannot bypass the current FST authority');assert.equal(fetches,1);assert.equal(prepares,1);assert.deepEqual(new Uint8Array(bytes),new Uint8Array(before));
 }finally{for(const model of returned){const resources=new ModelResources();resources.capture(model);resources.releaseKeeping();}owner.abort();}
});
