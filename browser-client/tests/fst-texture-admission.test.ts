// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {Loader,LoadingManager,Texture,MeshBasicMaterial,Mesh,SkinnedMesh,type Object3D} from 'three';
import {prepareFstTextureAdmission,type ResolvedFstReplacement} from '../src/fst-texture-admission';
import {extractEmbeddedFbxImages} from '../src/baked-fbx';
import {EmbeddedFbxImages} from '../src/embedded-fbx-images';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const owner=()=>new AbortController();
const recipe=(selector='mat::A',name='Replacement',extra:Record<string,unknown>={}):ResolvedFstReplacement=>{
 const template=new MeshBasicMaterial({name,map:new Texture({width:1,height:1}),color:0xffffff});
 return {selector,definition:{model:'hifi_pbr',name,unlit:true,albedoMap:'replacement.png',...extra},template};
};
function load(buffer:ArrayBuffer){
 const requests:string[]=[],manager=new LoadingManager();
 class AdmissionLoader extends Loader{load(url:string){requests.push(this.path+url);return new Texture({width:1,height:1});}}
 manager.addHandler(/\.png$/,new AdmissionLoader(manager));
 const root=new FBXLoader(manager).parse(buffer,'https://fixture.example/');let mesh!:Mesh;
 root.traverse(object=>{if(object instanceof Mesh)mesh=object;});assert(mesh);return {root,mesh,requests};
}
function geometry(mesh:Mesh){return {attributes:Object.fromEntries(Object.entries(mesh.geometry.attributes).map(([key,value])=>[key,{itemSize:value.itemSize,array:Array.from(value.array)}])),indices:mesh.geometry.index?Array.from(mesh.geometry.index.array):null,groups:mesh.geometry.groups.map(group=>({...group}))};}
function cleanup(root:Object3D){const materials=new Set<any>(),textures=new Set<Texture>();root.traverse(object=>{if(object instanceof Mesh){object.geometry.dispose();for(const material of Array.isArray(object.material)?object.material:[object.material])materials.add(material);}});for(const material of materials){for(const value of Object.values(material))if(value instanceof Texture)textures.add(value);material.dispose();}for(const texture of textures)texture.dispose();}
for(const wide of [false,true])test(`actual Three FBXLoader ${wide?64:32}bit parse admits only surviving original maps; shared source and geometry stay exact`,()=>{
 const input=fstTextureAdmissionFbx({wide}),original=new Uint8Array(input.slice(0)),replacement=recipe(),signal=owner().signal;
 const result=prepareFstTextureAdmission(input,[replacement],[],signal,()=>{});assert(result);assert.equal(result.removedTextures,1);assert.equal(result.removedVideos,1);assert.equal(result.retainedTextures,2);assert.equal(result.replacedMaterialCount,1);
 const before=load(input),after=load(result.buffer);
 assert.deepEqual(before.requests,['https://fixture.example/shared.png','https://fixture.example/unused-a.png','https://fixture.example/only-b.png']);
 assert.deepEqual(after.requests,['https://fixture.example/shared.png','https://fixture.example/only-b.png']);
 assert.deepEqual(geometry(after.mesh),geometry(before.mesh));assert.deepEqual(after.mesh.geometry.groups,[{start:0,count:3,materialIndex:0},{start:3,count:3,materialIndex:1}]);
 const old=before.mesh.material as any[],next=after.mesh.material as any[];assert.equal(old[0].map,old[1].map);assert.equal(next[0].map,next[1].map);
 assert.equal(next[1].normalMap.wrapS,old[1].normalMap.wrapS);assert.equal(next[1].normalMap.wrapT,old[1].normalMap.wrapT);assert.equal(next[1].map.colorSpace,old[1].map.colorSpace);
 assert.equal(next[0].normalMap,null);assert(next[1].normalMap);assert.deepEqual(new Uint8Array(input),original);
 assert.equal(((replacement.template as MeshBasicMaterial).map!.image as {width:number}).width,1);cleanup(before.root);cleanup(after.root);(replacement.template as MeshBasicMaterial).map!.dispose();replacement.template.dispose();
});
test('complete all-material coverage avoids every original texture request; unmatched or partial mappings retain shared inputs',()=>{
 const input=fstTextureAdmissionFbx(),replacement=recipe('all'),signal=owner().signal;
 const result=prepareFstTextureAdmission(input,[replacement],[],signal,()=>{});assert(result);assert.equal(result.removedTextures,3);assert.equal(result.removedVideos,3);const parsed=load(result.buffer);assert.deepEqual(parsed.requests,[]);cleanup(parsed.root);
 assert.equal(prepareFstTextureAdmission(input,[recipe('mat::unmatched')],[],signal,()=>{}),undefined);
 const uncertain=prepareFstTextureAdmission(fstTextureAdmissionFbx({unknownTextureConsumer:true}),[recipe()],[],signal,()=>{});assert.equal(uncertain,undefined);
});
test('ordered mapping selectors follow replacement names, keeping the same complete-material coverage as real source assignments',()=>{
 const input=fstTextureAdmissionFbx(),signal=owner().signal;
 const result=prepareFstTextureAdmission(input,[recipe('mat::A','Renamed'),recipe('mat::Renamed','Final')],[],signal,()=>{});assert(result);assert.equal(result.replacedMaterialCount,1);assert.equal(result.removedTextures,1);
 const all=prepareFstTextureAdmission(input,[recipe('all','Renamed'),recipe('mat::A','Ignored')],[],signal,()=>{});assert(all);assert.equal(all.replacedMaterialCount,2);assert.equal(all.removedTextures,3);
});
test('fallthrough custom unsupported maps/fields and incomplete actual templates refuse omission without changing original admission',()=>{
 const input=fstTextureAdmissionFbx(),signal=owner().signal;
 for(const extra of [{defaultFallthrough:true},{albedo:'fallthrough'},{roughness:'fallthrough'},{albedoMap:'fallthrough'},{model:'hifi_shader_simple'},{procedural:{}},{bumpMap:'original.png'},{opacityMap:'separate.png'},{texCoordTransform0:{}},{unknown:true},{roughness:NaN}])assert.equal(prepareFstTextureAdmission(input,[recipe('all','Replacement',extra)],[],signal,()=>{}),undefined);
 const incomplete=recipe('all');(incomplete.template as MeshBasicMaterial).map=null;assert.equal(prepareFstTextureAdmission(input,[incomplete],[],signal,()=>{}),undefined);
 const original=load(input);assert.equal(original.requests.length,3);cleanup(original.root);
});
test('embedded omitted descriptors are not leased; retained Video filename aliases preserve all needed exact markers',async()=>{
 const signal=owner().signal,prepared=await extractEmbeddedFbxImages(fstTextureAdmissionFbx({embedded:true}));assert.equal(prepared.images.length,3);
 const result=prepareFstTextureAdmission(prepared.buffer,[recipe()],prepared.images,signal,()=>{});assert(result);assert.equal(result.embeddedImages.length,2);assert.equal(result.usedEmbeddedMarkers.size,2);assert.equal(result.removedVideos,1);
 assert.equal(prepareFstTextureAdmission(prepared.buffer,[recipe()],[],signal,()=>{}),undefined);
 const all=prepareFstTextureAdmission(prepared.buffer,[recipe('all')],prepared.images,signal,()=>{});assert(all);assert.equal(all.embeddedImages.length,0);assert.equal(all.usedEmbeddedMarkers.size,0);
 const alias=await extractEmbeddedFbxImages(fstTextureAdmissionFbx({embedded:true,duplicateVideoName:true}));const retained=prepareFstTextureAdmission(alias.buffer,[recipe()],alias.images,signal,()=>{});assert(retained);assert.equal(retained.removedTextures,1);assert.equal(retained.removedVideos,0);assert.equal(retained.embeddedImages.length,3);
});
test('owner abort or authority replacement never becomes silent fallback or mutates/disposes borrowed templates',()=>{
 const input=fstTextureAdmissionFbx(),replacement=recipe('all'),stopped=owner();stopped.abort();let disposed=0;replacement.template.addEventListener('dispose',()=>disposed++);
 assert.throws(()=>prepareFstTextureAdmission(input,[replacement],[],stopped.signal,()=>{}),{name:'AbortError'});
 let checks=0;assert.throws(()=>prepareFstTextureAdmission(input,[replacement],[],owner().signal,()=>{if(++checks===2)throw Error('Current visitor authority ended');}),/authority ended/);assert.equal(checks,2);assert.equal(disposed,0);assert((replacement.template as MeshBasicMaterial).map);
 const huge=new ArrayBuffer(32*1024*1024+1);assert.equal(prepareFstTextureAdmission(huge,[replacement],[],owner().signal,()=>{}),undefined);
 assert.equal(prepareFstTextureAdmission(new TextEncoder().encode('; FBX7.4 unsupported ASCII proof').buffer,[replacement],[],owner().signal,()=>{}),undefined);
});
test('actual skinned FBX retains identical skeleton, vertex indices and weights after pruning only unreachable maps',()=>{
 const input=fstTextureAdmissionFbx({skin:true}),result=prepareFstTextureAdmission(input,[recipe()],[],owner().signal,()=>{});assert(result);
 const original=load(input),after=load(result.buffer);assert(original.mesh instanceof SkinnedMesh);assert(after.mesh instanceof SkinnedMesh);
 assert.equal(after.mesh.skeleton.bones.length,1);assert.deepEqual(after.mesh.skeleton.bones.map(bone=>bone.name),original.mesh.skeleton.bones.map(bone=>bone.name));
 assert.deepEqual(geometry(after.mesh),geometry(original.mesh));assert.equal(after.mesh.geometry.attributes.skinWeight.getX(0),1);assert.equal(after.mesh.geometry.attributes.skinIndex.getX(5),0);cleanup(original.root);cleanup(after.root);original.mesh.skeleton.dispose();after.mesh.skeleton.dispose();
});
test('actual embedded registry leases only surviving bytes under the original prepared owner and sibling cancellation stays isolated',async()=>{
 const world=owner(),a=owner(),b=owner(),registry=new EmbeddedFbxImages(world.signal),prepared=await extractEmbeddedFbxImages(fstTextureAdmissionFbx({embedded:true}));
 const result=prepareFstTextureAdmission(prepared.buffer,[recipe()],prepared.images,a.signal,()=>{});assert(result);const markers=[...result.usedEmbeddedMarkers];assert.equal(markers.length,2);
 const first=registry.register(prepared.buffer,result.embeddedImages,a.signal),second=registry.register(prepared.buffer,result.embeddedImages,b.signal);
 const urls=markers.map(marker=>first.resolveURL(marker));assert.equal(registry.statistics.createdURLs,2);assert.equal(second.resolveURL(markers[0]),urls[0]);assert.equal(registry.statistics.reusedURLs,1);
 a.abort();assert.throws(()=>first.resolveURL(markers[0]),{name:'AbortError'});assert.equal(second.resolveURL(markers[0]),urls[0]);
 const bytes=await(await fetch(urls[0])).arrayBuffer();assert.equal(bytes.byteLength,result.embeddedImages[0].bytes.byteLength);
 const removed=prepared.images.find(image=>!result.embeddedImages.includes(image));assert(removed);assert.throws(()=>second.resolveURL(`data:${removed.mimeType};base64,overte-embedded-${removed.digest}`),/Unregistered/);
 b.abort();world.abort();assert.equal(registry.statistics.entries,0);assert.equal(registry.statistics.revokedURLs,2);assert.equal(registry.statistics.scopes,0);
});
