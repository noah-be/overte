// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Local, already-recorded exact input; no network, DOM images or GPU. Output is
// aggregate-only. This actual FBXLoader dependency test is not a pixel proof.
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {Loader,LoadingManager,Texture,Mesh} from 'three';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {pruneNativeIgnoredFbxTextures,normalizeNativeFbxTransparency} from '../src/baked-fbx';
const digest=(v:Uint8Array|string)=>createHash('sha256').update(v).digest('hex');
const args=process.argv.slice(2);assert.equal(args.length,2,'Supply exact private input and safe output');
const bytes=await readFile(args[0]);assert.equal(digest(bytes),'54a2529473e3178ee5154a310d4cf1a3b6add52e8f28578074d8730dd03d5996');
const input=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),pruned=pruneNativeIgnoredFbxTextures(input),urls=new Set<string>();
const originalURL=URL.createObjectURL;URL.createObjectURL=function(blob){const url=originalURL.call(URL,blob);urls.add(url);return url;};
const warn=console.warn;let warnings=0;console.warn=()=>{warnings++;};
function parse(buffer:ArrayBuffer){
 const requests:{suffix:string}[]=[],manager=new LoadingManager();
 class ControlledImageLoader extends Loader{load(url:string){requests.push({suffix:/\.dds$/i.test(url)?'dds':url.startsWith('blob:')?'blob':'other'});return new Texture({width:1,height:1});}}
 manager.addHandler(/.*/,new ControlledImageLoader(manager));
 const root=new FBXLoader(manager).parse(normalizeNativeFbxTransparency(buffer),'https://fixture.invalid/');
 const meshes:any[]=[],materials=new Set<any>(),textures=new Set<Texture>();
 root.traverse(object=>{if(!(object instanceof Mesh))return;const g=object.geometry;
  const material=(Array.isArray(object.material)?object.material:[object.material]).map((m:any)=>{materials.add(m);const maps:Record<string,any>={};for(const slot of ['map','normalMap','bumpMap','emissiveMap','specularMap','alphaMap','aoMap','displacementMap'])if(m[slot]){const t=m[slot];textures.add(t);maps[slot]={wrapS:t.wrapS,wrapT:t.wrapT,offset:t.offset.toArray(),repeat:t.repeat.toArray(),rotation:t.rotation,flipY:t.flipY,colorSpace:t.colorSpace};}return {type:m.type,opacity:m.opacity,transparent:m.transparent,side:m.side,color:m.color?.toArray(),emissive:m.emissive?.toArray(),maps};});
  meshes.push({attrs:Object.fromEntries(Object.entries(g.attributes).map(([key,raw])=>{const a=raw as THREE.BufferAttribute;return [key,{size:a.itemSize,hash:digest(new Uint8Array(a.array.buffer,a.array.byteOffset,a.array.byteLength))}];})),index:g.index&&digest(new Uint8Array(g.index.array.buffer,g.index.array.byteOffset,g.index.array.byteLength)),groups:g.groups,material});
 });
 root.traverse(object=>{if(object instanceof Mesh){object.geometry.dispose();if('skeleton'in object)(object as any).skeleton.dispose();}});for(const material of materials)material.dispose();for(const texture of textures)texture.dispose();
 return {requestCounts:{total:requests.length,dds:requests.filter(r=>r.suffix==='dds').length,blob:requests.filter(r=>r.suffix==='blob').length,other:requests.filter(r=>r.suffix==='other').length},meshCount:meshes.length,renderBindingDigest:digest(JSON.stringify(meshes))};
}
let before,after;
try{before=parse(input);after=parse(pruned.buffer);}finally{console.warn=warn;URL.createObjectURL=originalURL;for(const url of urls)URL.revokeObjectURL(url);}
assert.equal(digest(new Uint8Array(input)),digest(bytes));assert.equal(pruned.removedTextures,3);assert.equal(pruned.removedVideos,3);assert.equal(before.requestCounts.dds,3);assert.equal(after.requestCounts.dds,0);assert.equal(before.requestCounts.blob,after.requestCounts.blob);assert.equal(before.renderBindingDigest,after.renderBindingDigest);
const report={scope:'Actual recorded FBXLoader dependency/render-binding CPU proof, no GPU pixels/native visual/load-speed claim',inputSHA256:digest(bytes),inputBytes:bytes.byteLength,preparedBytes:pruned.buffer.byteLength,removedTextures:pruned.removedTextures,removedVideos:pruned.removedVideos,retainedTextures:pruned.retainedTextures,before,after,warnings,createdBlobURLs:urls.size,releasedBlobURLs:urls.size,completed:true};await writeFile(args[1],JSON.stringify(report,null,2)+'\n',{mode:0o600});console.log(JSON.stringify(report));
