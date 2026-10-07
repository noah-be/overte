// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld parser ownership boundary; no WebGL constructor or native claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Group,Mesh,PlaneGeometry,MeshBasicMaterial,LoadingManager,Vector3} from 'three';
import {BrowserWorld} from '../src/world';
import {ModelParseTurn,ModelParseCapacityError} from '../src/model-parse-turn';
import {MeshCollision} from '../src/mesh-collision';
const actual=BrowserWorld.prototype as unknown as {parseTexturedModel(manager:LoadingManager,parse:()=>Group,signal:AbortSignal,weight:number):Promise<Group>};
function fixture(enabled=true){
 const controller=new AbortController(),reader=new AbortController(),phases:string[]=[];
 let approved=true;
 const epoch=new AbortController();
 const turn=enabled?new ModelParseTurn(AbortSignal.any([controller.signal,epoch.signal])):undefined;
 const context=Object.create(BrowserWorld.prototype);
 Object.assign(context,{abort:controller,disposed:false,modelParseTurn:turn,modelParseEpoch:epoch,parseTurnCounts:{capacityFallbacks:0},
   options:{modelParseTurn:enabled,captureAssetAuthority:()=>({generation:'owned-session-revision',assertCurrent(){if(!approved)throw new DOMException('Approval changed','AbortError');}})},
   recordLoadPhase(name:string){phases.push(name);}});
 return {context,controller,reader,turn,phases,revoke(){approved=false;},run:(parse:()=>Group)=>actual.parseTexturedModel.call(context,new LoadingManager(),parse,reader.signal,32)};
}
function graph(){const root=new Group(),geometry=new PlaneGeometry(10,10),material=new MeshBasicMaterial();geometry.rotateX(-Math.PI/2);root.add(new Mesh(geometry,material));return {root,geometry,material};}
test('actual World optional path retains exact graph and genuine triangle collision while default remains synchronous',async()=>{
 for(const enabled of [false,true]){
  const f=fixture(enabled),g=graph();let calls=0;
  const pending=f.run(()=>{calls++;return g.root;});assert.equal(calls,enabled?0:1);
  assert.equal(await pending,g.root);const collision=new MeshCollision(g.root);
  assert.equal(collision.supports(new Vector3(0,.85,0)),true);assert.equal(collision.supports(new Vector3(30,.85,0)),false);collision.dispose();
  assert.equal(f.phases.filter(p=>p==='fbxParseQueueWait').length,enabled?1:0);
  f.controller.abort();g.geometry.dispose();g.material.dispose();
 }
});
test('actual World checks captured authority again before queued parser and starts no stale work',async()=>{
 const f=fixture();let calls=0;const pending=f.run(()=>{calls++;return graph().root;});f.revoke();
 await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,0);assert.equal(f.turn!.stats.queuedBytes,0);assert.deepEqual(f.phases,['fbxParseQueueWait']);f.controller.abort();
});
test('actual World reader cancellation starts no parse, texture phase or retained channel',async()=>{
 const f=fixture();let calls=0;const pending=f.run(()=>{calls++;return graph().root;});f.reader.abort();
 await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,0);assert.deepEqual(f.phases,[]);assert.equal(f.turn!.stats.taskChannelOpen,false);f.controller.abort();
});
test('actual World releases newly parsed resources exactly once when approval changes synchronously',async()=>{
 const f=fixture(),g=graph();let geometry=0,material=0;
 g.geometry.addEventListener('dispose',()=>geometry++);g.material.addEventListener('dispose',()=>material++);
 await assert.rejects(f.run(()=>{f.revoke();return g.root;}),{name:'AbortError'});
 assert.deepEqual([geometry,material],[1,1]);assert.equal(f.turn!.stats.queuedBytes,0);f.controller.abort();
});
test('actual World only typed capacity fallback rechecks authority; parser errors are never retried',async()=>{
 const f=fixture(),pending=Array.from({length:32},()=>f.turn!.run(()=>new Group(),{weight:0}));
 let calls=0;const g=graph();assert.equal(await f.run(()=>{calls++;return g.root;}),g.root);assert.equal(calls,1);assert.equal(f.context.parseTurnCounts.capacityFallbacks,1);
 f.controller.abort();await Promise.allSettled(pending);g.geometry.dispose();g.material.dispose();
 const other=fixture(),error=Error('Model parse queue capacity exceeded');calls=0;
 await assert.rejects(other.run(()=>{calls++;throw error;}),candidate=>candidate===error);assert.equal(calls,1);assert.equal(other.context.parseTurnCounts.capacityFallbacks,0);other.controller.abort();
});
test('actual World capacity admission cannot authorize fallback after synchronous revocation',async t=>{
 const f=fixture();let calls=0;
 t.mock.method(f.turn!,'run',async()=>{f.revoke();throw new ModelParseCapacityError();});
 await assert.rejects(f.run(()=>{calls++;return graph().root;}),{name:'AbortError'});
 assert.equal(calls,0);assert.equal(f.context.parseTurnCounts.capacityFallbacks,0);f.controller.abort();
});

test('actual World synchronous reconnect invalidation frees queued bytes and ports before fresh admission',async()=>{
 const f=fixture();let calls=0;const old=f.turn!;
 const pending=f.run(()=>{calls++;return graph().root;});
 f.context.invalidateModelParses();
 assert.equal(old.stats.closed,true);assert.equal(old.stats.queuedBytes,0);assert.equal(old.stats.taskChannelOpen,false);
 await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,0);
 const g=graph();assert.equal(await f.run(()=>g.root),g.root);assert.notEqual(f.context.modelParseTurn,old);
 f.controller.abort();g.geometry.dispose();g.material.dispose();
});
test('actual World reconnect invalidation cancels already parsed image dependencies and frees its graph once',async()=>{
 const f=fixture(),manager=new LoadingManager(),g=graph();let count=0;g.geometry.addEventListener('dispose',()=>count++);
 const pending=actual.parseTexturedModel.call(f.context,manager,()=>{manager.itemStart('delayed-image');return g.root;},f.reader.signal,32);
 while(!f.turn!.stats.parsed)await new Promise(resolve=>setTimeout(resolve,1));
 f.context.invalidateModelParses();await assert.rejects(pending,{name:'AbortError'});assert.equal(count,1);
 manager.itemEnd('delayed-image');assert.equal(count,1);f.controller.abort();
});
