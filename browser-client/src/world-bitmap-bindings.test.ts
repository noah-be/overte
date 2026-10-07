// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {Group,Mesh,PlaneGeometry,Material,MeshBasicMaterial,MeshStandardMaterial,Texture,RepeatWrapping,DataTexture} from 'three';
import {WorldBitmapUpload,SessionUploadTexture} from './world-bitmap-upload';
import {prepareWorldBitmapBindings} from './world-bitmap-bindings';
import {ModelResources} from './model-resources';
import {applyNativeMaterialAlpha,getNativeAlphaOptions,hasNativeAlphaShader} from './native-alpha-material';
import {installNativeZeroLightShader,hasNativeZeroLightShader} from './native-zero-lights';
class DecodedImage{naturalWidth=2;naturalHeight=2;}
function setup(){const descriptor=Object.getOwnPropertyDescriptor(globalThis,'HTMLImageElement');Object.defineProperty(globalThis,'HTMLImageElement',{value:DecodedImage,configurable:true});
 const world=new AbortController(),jobs:{resolve:(bitmap:ImageBitmap)=>void;reject:(error:unknown)=>void}[]=[],bitmaps:{closes:number;bitmap:ImageBitmap}[]=[];
 const owner=new WorldBitmapUpload({signal:world.signal,createBitmap:()=>new Promise((resolve,reject)=>jobs.push({resolve,reject}))});
 const image=()=>new Texture(new DecodedImage() as unknown as HTMLImageElement),root=new Group(),material=new MeshBasicMaterial({map:image()}),mesh=new Mesh<PlaneGeometry,Material>(new PlaneGeometry(),material);root.add(mesh);
 const pixels=()=>{const counter={closes:0,bitmap:undefined as unknown as ImageBitmap};counter.bitmap={width:2,height:2,close(){counter.closes++;}} as ImageBitmap;bitmaps.push(counter);return counter;};
 return{world,owner,jobs,root,material,mesh,image,pixels,close(){world.abort();const resources=new ModelResources();resources.capture(root);resources.releaseKeeping();if(descriptor)Object.defineProperty(globalThis,'HTMLImageElement',descriptor);else Reflect.deleteProperty(globalThis,'HTMLImageElement');}};
}
const tick=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();};
test('atomic publication preserves shared slots, independent samplers, versions and original dispose ownership',async()=>{const s=setup();try{
 const original=s.material.map!,other=original.clone();other.wrapS=RepeatWrapping;const second=new MeshBasicMaterial({map:other}),same=new MeshBasicMaterial({map:original});s.root.add(new Mesh(new PlaneGeometry(),second),new Mesh(new PlaneGeometry(),same));let oldDisposals=0,otherDisposals=0;original.addEventListener('dispose',()=>oldDisposals++);other.addEventListener('dispose',()=>otherDisposals++);
 const version=s.material.version,sourceVersion=original.source.version,p=prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(s.jobs.length,1);assert.equal(s.material.map,original);const bitmap=s.pixels();s.jobs[0].resolve(bitmap.bitmap);const stats=await p;
 assert.equal(stats.converted,2);assert.equal(s.material.map,same.map);assert.notEqual(s.material.map,second.map);assert.equal(s.material.map!.source,second.map!.source);assert.equal(second.map!.wrapS,RepeatWrapping);assert.equal(s.material.version,version+1);assert.equal(original.source.version,sourceVersion);assert.equal(oldDisposals,1);assert.equal(otherDisposals,1);assert.equal(s.owner.stats().leases,2);
 const again=await prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(again.converted,0);assert.equal(s.material.version,version+1);s.close();assert.equal(bitmap.closes,1);
 }finally{s.close();}});
test('premultiplied, compressed/data and foreign shader bindings retain exact original maps and listeners',async()=>{const s=setup();try{
 s.material.map!.premultiplyAlpha=true;let disposed=0;s.material.map!.addEventListener('dispose',()=>disposed++);const original=s.material.map;const stats=await prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(stats.fallbacks,1);assert.equal(s.material.map,original);assert.equal(disposed,0);assert.equal(s.jobs.length,0);
 s.material.map=new DataTexture(new Uint8Array(4),1,1);const data=s.material.map;await prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(s.material.map,data);s.material.map=original;s.material.onBeforeCompile=()=>{};const foreign=await prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(foreign.unsupported,1);assert.equal(s.material.map,original);assert.equal(s.jobs.length,0);
 }finally{s.close();}});
for(const change of ['material','map','sampler','authority','removed-mesh'])test('late '+change+' change cannot publish or dispose the changed borrowed root',async()=>{const s=setup();try{
 const original=s.material.map!;let originalDisposed=0;original.addEventListener('dispose',()=>originalDisposed++);let current=true;const p=prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{if(!current)throw new DOMException('Revoked','AbortError');});
 if(change==='material')s.mesh.material=new MeshBasicMaterial({map:original});if(change==='map')s.material.map=s.image();if(change==='sampler')original.offset.x=.3;if(change==='authority')current=false;if(change==='removed-mesh')s.root.remove(s.mesh);
 const bitmap=s.pixels();s.jobs[0].resolve(bitmap.bitmap);await assert.rejects(p);assert(!(s.material.map instanceof SessionUploadTexture));assert.equal(originalDisposed,0);assert.equal(s.owner.stats().leases,0);s.owner.close();assert.equal(bitmap.closes,1);
 }finally{s.close();}});
test('reader cancellation settles before platform completion and closes late pixels without publishing',async()=>{const s=setup();try{
 const reader=new AbortController(),original=s.material.map,p=prepareWorldBitmapBindings(s.root,s.owner,reader.signal,()=>{});reader.abort();await assert.rejects(p,{name:'AbortError'});assert.equal(s.material.map,original);assert.equal(s.owner.stats().active,1);const bitmap=s.pixels();s.jobs[0].resolve(bitmap.bitmap);await tick();assert.equal(bitmap.closes,1);assert.equal(s.owner.stats().bytes,0);
 }finally{s.close();}});
test('one driver failure cancels other logical readers without replacing original maps',async()=>{const s=setup();try{
 const second=new MeshBasicMaterial({map:s.image()}),original=s.material.map;s.root.add(new Mesh(new PlaneGeometry(),second));const p=prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(s.jobs.length,2);s.jobs[0].reject(Error('Real conversion error'));await assert.rejects(p,/Real conversion error/);assert.equal(s.material.map,original);assert.equal(s.owner.stats().readers,0);const bitmap=s.pixels();s.jobs[1].resolve(bitmap.bitmap);await tick();assert.equal(bitmap.closes,1);
 }finally{s.close();}});
test('bounded whole-root deadline preserves original maps and does not free a physically unresolved conversion',async t=>{t.mock.timers.enable({apis:['setTimeout']});const s=setup();try{
 s.owner.close();const abort=new AbortController();let resolve!:(image:ImageBitmap)=>void;const owner=new WorldBitmapUpload({signal:abort.signal,deadlineMs:60000,createBitmap:()=>new Promise(yes=>{resolve=yes;})});const original=s.material.map;const p=prepareWorldBitmapBindings(s.root,owner,abort.signal,()=>{}),observed=assert.rejects(p,/transaction exceeded its bounded deadline/);
 t.mock.timers.tick(30000);await observed;assert.equal(s.material.map,original);assert.equal(owner.stats().active,1);assert.equal(owner.stats().readers,0);const bitmap=s.pixels();resolve(bitmap.bitmap);await tick();assert.equal(bitmap.closes,1);assert.equal(owner.stats().bytes,0);abort.abort();
 }finally{s.close();}});

for(const composed of [false,true])test('actual owned native mask'+(composed?' + zero-light':'')+' hooks and cutoff remain exact across map publication',async()=>{const s=setup();try{
 const material=new MeshStandardMaterial({map:s.material.map,opacity:.7});s.mesh.material=material;await applyNativeMaterialAlpha(material,{useAlpha:true,mode:'OPACITY_MAP_MASK',cutoff:.3},s.world.signal);if(composed)installNativeZeroLightShader(material);
 const compile=material.onBeforeCompile,key=material.customProgramCacheKey,options=getNativeAlphaOptions(material),state={alphaTest:material.alphaTest,transparent:material.transparent,opacity:material.opacity,side:material.side,depthWrite:material.depthWrite};
 const pending=prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{}),pixels=s.pixels();s.jobs[0].resolve(pixels.bitmap);const stats=await pending;assert.equal(stats.converted,1);assert.equal(material.onBeforeCompile,compile);assert.equal(material.customProgramCacheKey,key);assert.deepEqual(getNativeAlphaOptions(material),options);assert.deepEqual({alphaTest:material.alphaTest,transparent:material.transparent,opacity:material.opacity,side:material.side,depthWrite:material.depthWrite},state);assert(composed?hasNativeZeroLightShader(material):hasNativeAlphaShader(material));
 }finally{s.close();}});

test('atomic publication rechecks decoded HTML input after one prepared reader settles while another is still pending',async()=>{const s=setup();try{
 const second=new MeshBasicMaterial({map:s.image()}),original=s.material.map!,secondOriginal=second.map!;s.root.add(new Mesh(new PlaneGeometry(),second));let disposed=0;original.addEventListener('dispose',()=>disposed++);secondOriginal.addEventListener('dispose',()=>disposed++);
 const pending=prepareWorldBitmapBindings(s.root,s.owner,s.world.signal,()=>{});assert.equal(s.jobs.length,2);const a=s.pixels(),b=s.pixels();s.jobs[0].resolve(a.bitmap);
 for(let attempt=0;attempt<8&&s.owner.stats().leases===0;attempt++)await tick();assert.equal(s.owner.stats().leases,1);
 // The traversal dispatches the last child first. This mutation is after its
 // prepare() promise returned, so only the final transaction guard can see it.
 Object.defineProperty(secondOriginal.image,'currentSrc',{value:'https://example.test/changed-after-reader.png',writable:true,configurable:true});s.jobs[1].resolve(b.bitmap);
 await assert.rejects(pending,{name:'AbortError'});assert.equal(s.material.map,original);assert.equal(second.map,secondOriginal);assert.equal(disposed,0);assert.equal(s.owner.stats().leases,0);s.owner.close();assert.equal(a.closes,1);assert.equal(b.closes,1);assert.equal(s.owner.stats().bytes,0);
 }finally{s.close();}});
