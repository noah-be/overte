// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BoxGeometry,CompressedTexture,DataTexture,Group,Mesh,MeshBasicMaterial,RGBA_S3TC_DXT5_Format,Texture,UnsignedByteType} from 'three';
import {WorldTexturePreparation} from './world-texture-preparation';
const texture=()=>{const value=new CompressedTexture([{width:2,height:2,data:new Uint8Array(16)}],2,2,RGBA_S3TC_DXT5_Format,UnsignedByteType);value.needsUpdate=true;return value;};
const root=(maps:Texture[])=>{const value=new Group();for(const map of maps)value.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial({map})));return value;};
function dispose(value:Group){value.traverse(object=>{if(object instanceof Mesh){object.geometry.dispose();const material=object.material as MeshBasicMaterial;material.map?.dispose();material.dispose();}});}
const turn=()=>new Promise(resolve=>setImmediate(resolve));
test('actual maps are borrowed unchanged; dedup is Texture identity rather than shared Source or assumed upload count',async()=>{
 const owner=new AbortController(),a=texture(),b=a.clone();b.wrapS=1000;const scene=root([a,a,b]),calls:Texture[]=[],versions=[a.version,b.version,a.source.version];let disposed=0;a.addEventListener('dispose',()=>disposed++);b.addEventListener('dispose',()=>disposed++);
 const queue=new WorldTexturePreparation({initTexture(value){calls.push(value);}},{signal:owner.signal});await queue.prepare(scene,()=>{});
 assert.deepEqual(calls,[a,b]);assert.equal(a.source,b.source);assert.deepEqual([a.version,b.version,a.source.version],versions);assert.equal(disposed,0);assert.equal(queue.stats.initCalls,2);assert.equal(queue.stats.compressedCalls,2);assert.equal(queue.stats.references,0);owner.abort();dispose(scene);
});
test('ready cache hits still call public renderer initialization; unchanged Source is not authority to skip a different sampler',async()=>{
 const owner=new AbortController(),a=texture(),scene=root([a]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});await queue.prepare(scene,()=>{});a.wrapT=1000;await queue.prepare(scene,()=>{});assert.equal(calls,2);assert.equal(queue.stats.completed,2);owner.abort();dispose(scene);
});
test('dynamic, render-target, empty and update-free textures never enter the static material preparation path',async()=>{
 const owner=new AbortController(),dynamic=new DataTexture(new Uint8Array(16),2,2),empty=new Texture(),target=texture();dynamic.needsUpdate=true;target.isRenderTargetTexture=true;const scene=root([dynamic,empty,target]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});await queue.prepare(scene,()=>{});assert.equal(calls,0);assert.equal(queue.stats.submitted,0);assert.equal(queue.stats.skipped,3);owner.abort();dispose(scene);
});
test('two real task boundaries prevent concurrent models from accumulating their uploads in a single synchronous call stack',async()=>{
 const owner=new AbortController(),first=root([texture(),texture()]),second=root([texture()]);const calls:Texture[]=[],queue=new WorldTexturePreparation({initTexture(value){calls.push(value);}},{signal:owner.signal});const a=queue.prepare(first,()=>{}),b=queue.prepare(second,()=>{});assert.equal(calls.length,0);await Promise.all([a,b]);assert.equal(calls.length,3);assert.equal(calls[0],((first.children[0] as Mesh).material as MeshBasicMaterial).map);assert.equal(calls[1],((second.children[0] as Mesh).material as MeshBasicMaterial).map);assert.equal(calls[2],((first.children[1] as Mesh).material as MeshBasicMaterial).map);assert.equal(queue.stats.completed,2);assert.equal(queue.stats.active,0);owner.abort();dispose(first);dispose(second);
});
test('root authority replacement during upload cannot prepare later borrowed maps or report successful readiness',async()=>{
 const owner=new AbortController(),scene=root([texture(),texture()]);let current=true,calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;current=false;}},{signal:owner.signal});await assert.rejects(queue.prepare(scene,()=>{if(!current)throw new DOMException('Replaced root','AbortError');}),{name:'AbortError'});assert.equal(calls,1);assert.equal(queue.stats.completed,0);assert.equal(queue.stats.cancelled,1);owner.abort();dispose(scene);
});
test('queued reader cancellation releases only its references; another model still receives complete preparation',async()=>{
 const owner=new AbortController(),reader=new AbortController(),first=root([texture()]),second=root([texture()]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});const a=queue.prepare(first,()=>{}),b=queue.prepare(second,()=>{},reader.signal);const refusal=assert.rejects(b,{name:'AbortError'});reader.abort();await refusal;await a;assert.equal(calls,1);assert.equal(queue.stats.references,0);assert.equal(queue.stats.completed,1);owner.abort();dispose(first);dispose(second);
});
test('world cancellation closes its actual pending MessageChannel and releases every queued reference without preparing pixels',async()=>{
 const owner=new AbortController(),a=root([texture()]),b=root([texture()]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});const first=queue.prepare(a,()=>{}),second=queue.prepare(b,()=>{});const refusals=[assert.rejects(first,{name:'AbortError'}),assert.rejects(second,{name:'AbortError'})];owner.abort();await Promise.all(refusals);await turn();assert.equal(calls,0);assert.equal(queue.stats.references,0);assert.equal(queue.stats.queued,0);assert.equal(queue.stats.active,0);assert(queue.stats.disposed);dispose(a);dispose(b);
});
test('failed renderer initialization releases queue ownership and lets a later genuine job run',async()=>{
 const owner=new AbortController(),a=root([texture()]),b=root([texture()]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){if(++calls===1)throw Error('Driver initialization failed');}},{signal:owner.signal});await assert.rejects(queue.prepare(a,()=>{}),/Driver/);await queue.prepare(b,()=>{});assert.equal(calls,2);assert.equal(queue.stats.failed,1);assert.equal(queue.stats.completed,1);assert.equal(queue.stats.references,0);owner.abort();dispose(a);dispose(b);
});
test('pending jobs and borrowed references are bounded before renderer work; refusal does not discard prior owners',async()=>{
 const owner=new AbortController(),a=root([texture()]),b=root([texture()]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal,maximumJobs:1,maximumReferences:1});const first=queue.prepare(a,()=>{});await assert.rejects(queue.prepare(b,()=>{}),/Too many/);assert.equal(queue.stats.references,1);await first;assert.equal(calls,1);owner.abort();dispose(a);dispose(b);
});
test('real queue deadline closes a pending continuation and never becomes successful readiness',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const owner=new AbortController(),scene=root([texture()]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});const pending=queue.prepare(scene,()=>{}),refusal=assert.rejects(pending,/deadline/);t.mock.timers.tick(30000);await refusal;await turn();assert.equal(calls,0);assert.equal(queue.stats.failed,1);assert.equal(queue.stats.references,0);owner.abort();dispose(scene);
});

test('real Texture disposal revokes a pending borrow before public initialization can resurrect its GPU resource',async()=>{
 const owner=new AbortController(),map=texture(),scene=root([map]);let calls=0;const queue=new WorldTexturePreparation({initTexture(){calls++;}},{signal:owner.signal});const loading=queue.prepare(scene,()=>{}),refusal=assert.rejects(loading,{name:'AbortError'});map.dispose();await refusal;await turn();assert.equal(calls,0);assert.equal(queue.stats.references,0);assert.equal(queue.stats.cancelled,1);owner.abort();dispose(scene);
});
