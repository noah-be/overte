// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {Loader,LoadingManager,Texture,Mesh,SkinnedMesh,type Object3D} from 'three';
import {pruneNativeIgnoredFbxTextures,normalizeNativeFbxTransparency} from '../src/baked-fbx';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
function load(buffer:ArrayBuffer){
 const requests:string[]=[],manager=new LoadingManager();
 class ImageLoader extends Loader{load(url:string){requests.push(this.path+url);return new Texture({width:1,height:1});}}
 manager.addHandler(/.*/,new ImageLoader(manager));
 const root=new FBXLoader(manager).parse(buffer,'https://fixture.example/');let mesh!:Mesh;
 root.traverse(object=>{if(object instanceof Mesh)mesh=object;});assert(mesh);return {root,mesh,requests};
}
function signature(mesh:Mesh){return {attributes:Object.fromEntries(Object.entries(mesh.geometry.attributes).map(([key,value])=>[key,{itemSize:value.itemSize,array:Array.from(value.array)}])),indices:mesh.geometry.index?Array.from(mesh.geometry.index.array):null,groups:mesh.geometry.groups.map(group=>({...group})),materials:(Array.isArray(mesh.material)?mesh.material:[mesh.material]).map((material:any)=>({name:material.name,opacity:material.opacity,transparent:material.transparent,color:material.color.toArray(),map:material.map?.name,normalMap:material.normalMap?.name,samplers:material.map&&[material.map.wrapS,material.map.wrapT,material.map.colorSpace,material.map.offset.toArray(),material.map.repeat.toArray()]}))};}
function cleanup(root:Object3D){const materials=new Set<any>(),textures=new Set<Texture>();root.traverse(object=>{if(object instanceof Mesh){object.geometry.dispose();for(const m of Array.isArray(object.material)?object.material:[object.material])materials.add(m);if(object instanceof SkinnedMesh)object.skeleton.dispose();}});for(const m of materials){for(const value of Object.values(m))if(value instanceof Texture)textures.add(value);m.dispose();}for(const texture of textures)texture.dispose();}
for(const wide of [false,true])for(const slot of ['Maya|TEX_global_specular_cube','Maya|TEX_global_diffuse_cube','Maya|TEX_brdf_lut'])test(`actual FBXLoader ${wide?64:32}bit removes only exact native-ignored ${slot} dependency and preserves rendered bytes`,()=>{
 const input=fstTextureAdmissionFbx({wide,ignoredSlot:slot,skin:true,nativeEndRecords:true}),immutable=new Uint8Array(input.slice(0)),result=pruneNativeIgnoredFbxTextures(input);
 assert.equal(result.removedTextures,1);assert.equal(result.removedVideos,1);assert.equal(result.retainedTextures,2);assert(result.buffer.byteLength<input.byteLength);
 const before=load(input),after=load(result.buffer);
 assert.deepEqual(before.requests,['https://fixture.example/shared.png','https://fixture.example/unused-a.png','https://fixture.example/only-b.png']);
 assert.deepEqual(after.requests,['https://fixture.example/shared.png','https://fixture.example/only-b.png']);
 assert.deepEqual(signature(after.mesh),signature(before.mesh));assert(before.mesh instanceof SkinnedMesh&&after.mesh instanceof SkinnedMesh);assert.deepEqual(after.mesh.skeleton.bones.map(b=>b.name),before.mesh.skeleton.bones.map(b=>b.name));
 assert.deepEqual(new Uint8Array(input),immutable);assert.equal(pruneNativeIgnoredFbxTextures(result.buffer).buffer,result.buffer);cleanup(before.root);cleanup(after.root);
});
test('used, unknown, mixed, missing-Video, ambiguous-ID and unknown-child bindings retain original exact buffer',()=>{
 const slot='Maya|TEX_global_specular_cube';
 for(const options of [{ignoredSlot:'Maya|TEX_global_specular_cube_extra'},{ignoredSlot:'Reflection'},{ignoredSlot:'SpecularColor'},{ignoredSlot:'DiffuseColor'},{ignoredSlot:slot,mixedConsumer:true},{ignoredSlot:slot,unknownTextureConsumer:true},{ignoredSlot:slot,unknownIncoming:true},{ignoredSlot:slot,noVideo:true},...(['duplicate','unsafe','negative','nonnumeric'] as const).map(ambiguousID=>({ignoredSlot:slot,ambiguousID}))]){
  const input=fstTextureAdmissionFbx(options),result=pruneNativeIgnoredFbxTextures(input);assert.equal(result.buffer,input);assert.equal(result.removedTextures,0);
 }
});
test('shared Video or filename aliases preserve exact Content while pruning only unused Texture ownership',()=>{
 for(const options of [{videoShared:true},{duplicateVideoName:true}]){
  const input=fstTextureAdmissionFbx({...options,embedded:true,ignoredSlot:'Maya|TEX_brdf_lut'}),result=pruneNativeIgnoredFbxTextures(input);assert.equal(result.removedTextures,1);assert.equal(result.removedVideos,0);
 }
});
test('ASCII and absent bindings keep original inputs; strict binary size/property bounds still reject malformed inputs',()=>{
 const ascii=new TextEncoder().encode('; FBX7.4 ASCII').buffer;assert.equal(pruneNativeIgnoredFbxTextures(ascii).buffer,ascii);
 const ordinary=fstTextureAdmissionFbx();assert.equal(pruneNativeIgnoredFbxTextures(ordinary).buffer,ordinary);
 const truncated=fstTextureAdmissionFbx().slice(0,120);assert.throws(()=>pruneNativeIgnoredFbxTextures(truncated),/bounds|hierarchy/);
 const huge=new Uint8Array(32*1024*1024+1);huge.set(new TextEncoder().encode('Kaydara FBX Binary  \0\x1a\0'));assert.throws(()=>pruneNativeIgnoredFbxTextures(huge.buffer),/input length/);
});

test('combined real worker normalization keeps one parse and the same explicit two-stage output; ordinary default alpha path remains exact',()=>{
 for(const wide of [false,true]){
  const input=fstTextureAdmissionFbx({wide,ignoredSlot:'Maya|TEX_brdf_lut'}),pruned=pruneNativeIgnoredFbxTextures(input);
  assert.deepEqual(new Uint8Array(normalizeNativeFbxTransparency(input,{pruneIgnoredTextures:true})),new Uint8Array(normalizeNativeFbxTransparency(pruned.buffer)));
  const ordinary=fstTextureAdmissionFbx({wide});assert.deepEqual(new Uint8Array(normalizeNativeFbxTransparency(ordinary,{pruneIgnoredTextures:true})),new Uint8Array(normalizeNativeFbxTransparency(ordinary)));
 }
});
