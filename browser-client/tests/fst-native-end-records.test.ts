// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {Loader,LoadingManager,Mesh,MeshBasicMaterial,Texture} from 'three';
import {prepareFstTextureAdmission} from '../src/fst-texture-admission';
import {inspectFbxOriginalTextures} from '../src/baked-fbx';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
function parse(bytes:ArrayBuffer){const manager=new LoadingManager(),requests:string[]=[];class Images extends Loader{load(url:string){requests.push(this.path+url);return new Texture({width:1,height:1});}}manager.addHandler(/\.png$/,new Images(manager));const model=new FBXLoader(manager).parse(bytes,'https://fixture.example/');let mesh!:Mesh;model.traverse(object=>{if(object instanceof Mesh)mesh=object;});assert(mesh);return{model,mesh,requests};}
function geometry(mesh:Mesh){return {groups:mesh.geometry.groups,attributes:Object.fromEntries(Object.entries(mesh.geometry.attributes).map(([key,value])=>[key,{size:value.itemSize,values:Array.from(value.array)}])),indices:mesh.geometry.index?Array.from(mesh.geometry.index.array):null};}
for(const wide of [false,true])test(`native-writer ${wide?64:32}-bit nonzero empty endings retain actual Three geometry and omit only unreachable images`,()=>{
 const original=fstTextureAdmissionFbx({wide,nativeEndRecords:true}),before=Uint8Array.from(new Uint8Array(original));const map=new Texture({width:1,height:1}),template=new MeshBasicMaterial({name:'Replacement',map});
 const result=prepareFstTextureAdmission(original,[{selector:'mat::A',definition:{name:'Replacement',unlit:true,albedoMap:'replacement.png'},template}],[],new AbortController().signal,()=>{});assert(result);assert.equal(result.removedTextures,1);assert.equal(result.removedVideos,1);
 const unmodified=parse(original),filtered=parse(result.buffer);assert.deepEqual(unmodified.requests,['https://fixture.example/shared.png','https://fixture.example/unused-a.png','https://fixture.example/only-b.png']);assert.deepEqual(filtered.requests,['https://fixture.example/shared.png','https://fixture.example/only-b.png']);assert.deepEqual(geometry(filtered.mesh),geometry(unmodified.mesh));assert.deepEqual(new Uint8Array(original),before);
 for(const loaded of [unmodified,filtered]){loaded.mesh.geometry.dispose();for(const material of loaded.mesh.material as MeshBasicMaterial[]){for(const value of Object.values(material))if(value instanceof Texture)value.dispose();material.dispose();}}map.dispose();template.dispose();
});
for(const kind of ['object','connection','objectChildren'] as const)test(`unnamed ${kind} with payload is never mistaken for a native empty ending`,()=>{
 assert.equal(inspectFbxOriginalTextures(fstTextureAdmissionFbx({nativeEndRecords:true,invalidUnnamedNode:kind})),undefined);
});

for(const kind of ['duplicate','nonnumeric','unsafe','negative'] as const)test(`native endings never weaken ${kind} ID refusal`,()=>{
 const original=fstTextureAdmissionFbx({nativeEndRecords:true,ambiguousID:kind}),before=Uint8Array.from(new Uint8Array(original));assert.equal(inspectFbxOriginalTextures(original),undefined);assert.deepEqual(new Uint8Array(original),before);
});
