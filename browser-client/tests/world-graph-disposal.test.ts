// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld teardown methods; no WebGL/native/browser construction.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {cloneNativeMaterialForGeometry} from '../src/native-render-state';
import {BufferGeometry,Group,Line,Mesh,MeshBasicMaterial,Scene,Texture} from 'three';
import {FBXLoader} from 'three/examples/jsm/loaders/FBXLoader.js';
import {BrowserWorld} from '../src/world';
import {ModelResources} from '../src/model-resources';
import {ReplacementMaterialClones} from '../src/replacement-material-clones';
import {WorldBitmapUpload} from '../src/world-bitmap-upload';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
import {disposeObject as originalDisposeObject} from './fixtures/world-graph-disposal-original';
function count(resource:BufferGeometry|MeshBasicMaterial|Texture,strict=true):()=>number{
 let value=0;resource.addEventListener('dispose',()=>{value++;if(strict&&value>1)throw Error('Duplicate material disposal');});return()=>value;
}
function lifecycle(root:Group,abort=new AbortController()){
 const world=Object.create(BrowserWorld.prototype) as BrowserWorld,scene=new Scene();scene.add(root);
 const entities=new Map([['owned-model',{id:'owned-model',type:'Model'}]]),objects=new Map([['owned-model',root]]),avatars=new Map<string,Group>();
 let rendererDisposed=0,canvasRemoved=0;
 Object.assign(world,{scene,entities,objects,avatars,avatarModels:new Map(),signatures:new Map(),meshCollisions:new Map(),modelBatches:new Map(),modelGeometry:new WeakMap(),modelReaders:new WeakMap(),localLights:new Set(),colliders:[],pendingModelColliders:[],abort,disposed:false,enabled:true,loadManagers:new Set(),resizeObserver:{disconnect(){}},renderer:{dispose(){rendererDisposed++;}},canvas:{remove(){canvasRemoved++;}},self:new Group(),frame:0});
 return{world,scene,entities,objects,avatars,counts:()=>({rendererDisposed,canvasRemoved})};
}
function mappedGraph(enabled=true,extraMesh=true){
 const root=new Group(),parsed=new FBXLoader().parse(fstTextureAdmissionFbx({withoutOriginalTextures:true}),'');root.add(parsed);
 const resources=new ModelResources(),texture=new Texture(),template=new MeshBasicMaterial({map:texture}),bank=enabled?new ReplacementMaterialClones(template,resources):undefined;
 resources.capture(root);resources.captureMaterial(template);let imported:Mesh|undefined;
 parsed.traverse(object=>{if(object instanceof Mesh){imported=object;const old=Array.isArray(object.material)?object.material:[object.material];object.material=old.map(()=>bank?.forMesh(object)??cloneNativeMaterialForGeometry(template,object.geometry));}});
 assert(imported);assert.equal(imported.geometry.attributes.position.count,6);assert.equal((imported.material as MeshBasicMaterial[]).length,2);
 const shared=(imported.material as MeshBasicMaterial[])[0];if(enabled)assert.equal(shared,(imported.material as MeshBasicMaterial[])[1]);else assert.notEqual(shared,(imported.material as MeshBasicMaterial[])[1]);
 if(extraMesh)root.add(new Mesh(imported.geometry,shared));bank?.close();resources.capture(root);resources.releaseKeeping(root);
 return {root,texture,material:shared,materials:[...new Set(imported.material as MeshBasicMaterial[])],geometry:imported.geometry,resources};
}
// Exact actual removal method; only its original private cleanup binding is restored.
// No alternate World mutation/discovery/admission implementation is mirrored here.
const originalRemoveEntities=new Function('THREE','disposeObject',`return ({${BrowserWorld.prototype.removeEntities.toString()}}).removeEntities;`)(THREE,originalDisposeObject) as BrowserWorld['removeEntities'];
test('original actual World removal passes distinct OFF clones but reproduces ON shared-clone duplicate disposal',()=>{
 for(const enabled of [false,true]){
  const graph=mappedGraph(enabled,false),materials=graph.materials.map(material=>count(material)),f=lifecycle(graph.root);
  if(enabled){assert.throws(()=>originalRemoveEntities.call(f.world,['owned-model']),/Duplicate material disposal/);assert.deepEqual(materials.map(value=>value()),[2]);}
  else{originalRemoveEntities.call(f.world,['owned-model']);assert.deepEqual(materials.map(value=>value()),[1,1]);assert.equal(f.objects.size,0);}
 }
});
test('actual fixed removeEntities releases OFF and ON imported FBX graph resources once and retires owners',()=>{
 for(const enabled of [false,true]){
  const graph=mappedGraph(enabled,enabled),counts=[count(graph.geometry),...graph.materials.map(material=>count(material)),count(graph.texture)],f=lifecycle(graph.root);
  f.world.removeEntities(['owned-model']);assert.deepEqual(counts.map(value=>value()),counts.map(()=>1));assert.equal(f.objects.size,0);assert.equal(f.entities.size,0);assert.equal(f.scene.children.length,0);
  f.world.removeEntities(['owned-model']);assert.deepEqual(counts.map(value=>value()),counts.map(()=>1));
 }
});
test('actual remote participant removal deduplicates Mesh/Line geometry, repeated maps and material arrays',()=>{
 const root=new Group(),geometry=new BufferGeometry(),map=new Texture(),first=new MeshBasicMaterial({map,alphaMap:map}),second=new MeshBasicMaterial({map});root.add(new Mesh(geometry,[first,second,first]),new Line(geometry,second));
 const unrelated=new MeshBasicMaterial();root.userData.borrowedMaterial=unrelated;const untouched=count(unrelated),counts=[count(geometry),count(first),count(second),count(map)],f=lifecycle(new Group());
 f.avatars.set('own-fixture-peer',root);f.scene.add(root);f.world.setAvatars([]);assert.deepEqual(counts.map(value=>value()),[1,1,1,1]);assert.equal(f.avatars.size,0);assert.equal(root.parent,null);assert.equal(untouched(),0);
 f.world.setAvatars([]);assert.deepEqual(counts.map(value=>value()),[1,1,1,1]);
});
test('ModelResources transition retains shared borrowed bitmap until actual final whole-graph teardown',()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'ImageBitmap');class Bitmap{closed=0;close(){this.closed++;assert.equal(this.closed,1);}}
 Object.defineProperty(globalThis,'ImageBitmap',{configurable:true,value:Bitmap});
 try{
  const bitmap=new Bitmap(),first=new Texture(bitmap as unknown as ImageBitmap),second=first.clone(),old=new MeshBasicMaterial({map:first}),replacement=new MeshBasicMaterial({map:second,alphaMap:second}),root=new Group(),geometry=new BufferGeometry(),mesh=new Mesh(geometry,old);root.add(mesh);
  const resources=new ModelResources();resources.capture(root);resources.captureMaterial(replacement);mesh.material=replacement;resources.capture(root);resources.releaseKeeping(root);assert.equal(bitmap.closed,0);
  // Distinct retained Texture identities borrow the same bitmap data.
  const third=second.clone(),other=new MeshBasicMaterial({map:third});root.add(new Mesh(geometry,other));const counts=[count(geometry),count(replacement),count(other),count(second),count(third)];
  lifecycle(root).world.removeEntities(['owned-model']);assert.deepEqual(counts.map(value=>value()),[1,1,1,1,1]);assert.equal(bitmap.closed,1);
 }finally{if(original)Object.defineProperty(globalThis,'ImageBitmap',original);else delete (globalThis as {ImageBitmap?:unknown}).ImageBitmap;}
});
test('actual World.dispose preserves managed bitmap lease ownership and idempotent whole-world terminal state',async()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'ImageBitmap'),raf=Object.getOwnPropertyDescriptor(globalThis,'cancelAnimationFrame'),doc=Object.getOwnPropertyDescriptor(globalThis,'document');
 class Bitmap{width=2;height=2;closed=0;close(){this.closed++;assert.equal(this.closed,1);}}
 Object.defineProperty(globalThis,'ImageBitmap',{configurable:true,value:Bitmap});Object.defineProperty(globalThis,'cancelAnimationFrame',{configurable:true,value:()=>{}});Object.defineProperty(globalThis,'document',{configurable:true,value:{pointerLockElement:null}});
 try{
  const abort=new AbortController(),bitmap=new Bitmap(),owner=new WorldBitmapUpload({signal:abort.signal,isImage:()=>true,createBitmap:async()=>bitmap as unknown as ImageBitmap}),source=new Texture({naturalWidth:2,naturalHeight:2,complete:true,src:'authored-fixed-input',currentSrc:'authored-fixed-input'} as unknown as HTMLImageElement),managed=await owner.prepare(source,abort.signal),copy=managed.clone(),root=new Group(),geometry=new BufferGeometry(),first=new MeshBasicMaterial({map:managed,alphaMap:managed}),second=new MeshBasicMaterial({map:copy});root.add(new Mesh(geometry,[first,first,second]),new Line(geometry,second));
  const counts=[count(geometry),count(first),count(second),count(managed),count(copy)],f=lifecycle(root,abort);assert.equal(owner.stats().leases,2);
  f.world.dispose();assert.deepEqual(counts.map(value=>value()),[1,1,1,1,1]);assert.equal(bitmap.closed,1);assert.equal(owner.stats().closed,1);assert.equal(owner.stats().leases,0);assert.equal(owner.stats().bytes,0);assert.equal(f.objects.size,0);assert.equal(f.avatars.size,0);assert.equal(f.scene.children.length,0);assert.deepEqual(f.counts(),{rendererDisposed:1,canvasRemoved:1});
  f.world.dispose();assert.deepEqual(counts.map(value=>value()),[1,1,1,1,1]);assert.deepEqual(f.counts(),{rendererDisposed:1,canvasRemoved:1});assert.equal(bitmap.closed,1);
 }finally{for(const[key,descriptor]of [['ImageBitmap',original],['cancelAnimationFrame',raf],['document',doc]]as const){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete (globalThis as unknown as Record<string,unknown>)[key];}}
});
test('teardown does not swallow or replace an original resource listener failure',()=>{
 const root=new Group(),geometry=new BufferGeometry(),failure=Error('authored cleanup failure');root.add(new Mesh(geometry,new MeshBasicMaterial()));geometry.addEventListener('dispose',()=>{throw failure;});
 assert.throws(()=>lifecycle(root).world.removeEntities(['owned-model']),error=>error===failure);
});
