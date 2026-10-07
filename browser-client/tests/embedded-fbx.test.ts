// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';
import {LoadingManager,Mesh,MeshPhongMaterial} from 'three';import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {extractEmbeddedFbxImages,adaptBakedFbx,normalizeNativeFbxTransparency} from '../src/baked-fbx';import {EmbeddedFbxImages} from '../src/embedded-fbx-images';import {WorldImageCache} from '../src/world-image-cache';import {embeddedFbx,embeddedPNG} from './fixtures/embedded-fbx';
class ImageInput extends EventTarget{crossOrigin='';naturalWidth=1;naturalHeight=1;src='';removeAttribute(){this.src='';}async decode(){}load(){this.dispatchEvent(new Event('load'));}}
const turn=()=>new Promise(r=>setTimeout(r,0));
function modelMap(root:ReturnType<FBXLoader['parse']>){let mesh:Mesh|undefined;root.traverse(o=>{if(o instanceof Mesh)mesh=o;});assert(mesh);return {mesh,map:(mesh.material as MeshPhongMaterial).map!};}
for(const wide of [false,true])test(`actual ${wide?64:32}-bit FBX parser reuses approved embedded bytes/source with independent Texture samplers`,async()=>{
 const raw=embeddedFbx(undefined,undefined,wide),prepared=await extractEmbeddedFbxImages(normalizeNativeFbxTransparency(raw)),buffer=await adaptBakedFbx(prepared.buffer);assert.equal(prepared.counts.converted,1);assert.deepEqual(new Uint8Array(prepared.images[0].bytes),embeddedPNG);
 const world=new AbortController(),images:ImageInput[]=[],cache=new WorldImageCache({signal:world.signal,createImage:()=>{const image=new ImageInput();images.push(image);return image as unknown as HTMLImageElement;}}),sources=new EmbeddedFbxImages(world.signal);
 const roots=[];const scopes=[];
 for(let i=0;i<2;i++){const scope=sources.register(buffer,prepared.images,world.signal),manager=new LoadingManager();scopes.push(scope);manager.setURLModifier(scope.resolveURL);manager.addHandler(/\.png$/i,cache.loader(manager));roots.push(new FBXLoader(manager).parse(buffer,''));}
 assert.equal(images.length,1,'Repeated real FBX parse must not create a second image');images[0].load();await turn();
 const a=modelMap(roots[0]),b=modelMap(roots[1]);assert.notEqual(a.map,b.map);assert.equal(a.map.source,b.map.source);assert.equal(a.map.image,b.map.image);assert.equal(a.mesh.geometry.getAttribute('position').count,3);assert.deepEqual(a.mesh.geometry.attributes.position.array,b.mesh.geometry.attributes.position.array);
 a.map.repeat.set(2,3);assert.deepEqual(b.map.repeat.toArray(),[1,1]);assert.equal(sources.statistics.createdURLs,1);assert.equal(sources.statistics.reusedURLs,1);assert.equal(cache.stats().sourceKinds.blob.uniqueImages,1);
 for(const scope of scopes)scope.close();world.abort();assert.equal(sources.statistics.bytes,0);assert.equal(sources.statistics.entries,0);assert.equal(sources.statistics.revokedURLs,1);for(const r of roots){const {mesh,map}=modelMap(r);map.dispose();mesh.geometry.dispose();(mesh.material as MeshPhongMaterial).dispose();}
});
test('unmodified real parser produces two distinct blob URLs for identical raw embedded content',async()=>{
 const raw=embeddedFbx(),world=new AbortController(),images:ImageInput[]=[],cache=new WorldImageCache({signal:world.signal,createImage:()=>{const image=new ImageInput();images.push(image);return image as unknown as HTMLImageElement;}}),roots=[];
 for(let i=0;i<2;i++){const manager=new LoadingManager();manager.addHandler(/\.png$/i,cache.loader(manager));roots.push(new FBXLoader(manager).parse(raw,''));}
 assert.equal(images.length,2);assert.notEqual(images[0].src,images[1].src);for(const image of images)image.load();await turn();assert.notEqual(modelMap(roots[0]).map.source,modelMap(roots[1]).map.source);assert.equal(cache.stats().sourceKinds.blob.uniqueImages,2);
 for(const image of images)URL.revokeObjectURL(image.src);world.abort();for(const r of roots){const {mesh,map}=modelMap(r);map.dispose();mesh.geometry.dispose();(mesh.material as MeshPhongMaterial).dispose();}
});
test('source leases survive registry pressure until parse/decode owner closes; abort revokes all owned URLs',async()=>{
 const prepared=await extractEmbeddedFbxImages(embeddedFbx()),world=new AbortController(),sources=new EmbeddedFbxImages(world.signal,{bytes:embeddedPNG.length,entries:1,scopes:2}),a=new AbortController(),b=new AbortController();
 const marker=`data:image/png;base64,overte-embedded-${prepared.images[0].digest}`,first=sources.register(prepared.buffer,prepared.images,a.signal),url=first.resolveURL(marker);assert.equal((await fetch(url)).status,200);
 const second=sources.register(prepared.buffer.slice(0),prepared.images,b.signal);assert.throws(()=>second.resolveURL(marker),/resource bound/);assert.equal((await fetch(url)).status,200,'Held bytes cannot be evicted');a.abort();const replacement=second.resolveURL(marker);assert.notEqual(replacement,url);await assert.rejects(fetch(url));assert.throws(()=>first.resolveURL(marker),{name:'AbortError'});world.abort();await assert.rejects(fetch(replacement));assert.deepEqual(sources.statistics,{createdURLs:2,reusedURLs:0,revokedURLs:2,bytes:0,entries:0,scopes:0,distinctContents:0,repeatedContentEntries:0,distinctContentBytes:0,repeatedContentBytes:0});
});
test('unsupported/oversized embedded data retains its original native content and reports honest fallback',async()=>{
 const large=embeddedFbx(new Uint8Array(8*1024*1024+1));const result=await extractEmbeddedFbxImages(large);assert.equal(result.buffer,large);assert.equal(result.images.length,0);assert.equal(result.counts.skippedOversize,1);
 const unknown=embeddedFbx(embeddedPNG,'tga');const next=await extractEmbeddedFbxImages(unknown);assert.equal(next.buffer,unknown);assert.equal(next.counts.skippedUnsupported,1);
 const ascii=new TextEncoder().encode('; FBX7.4').buffer;assert.equal((await extractEmbeddedFbxImages(ascii)).buffer,ascii);
});

test('runtime descriptor, owner and configuration validation cannot bypass resource limits',async()=>{
 const world=new AbortController(),prepared=await extractEmbeddedFbxImages(embeddedFbx()),sources=new EmbeddedFbxImages(world.signal);
 assert.throws(()=>new EmbeddedFbxImages(world.signal,{entries:1} as never),/resource bound/);
 assert.throws(()=>sources.register(prepared.buffer,undefined as never,world.signal),/Invalid embedded image owner/);
 assert.throws(()=>sources.register(prepared.buffer,[null] as never,world.signal),/Invalid embedded source descriptor/);
 assert.throws(()=>sources.register(prepared.buffer,[{...prepared.images[0],digest:undefined}] as never,world.signal),/Invalid embedded source descriptor/);
 assert.equal(sources.statistics.scopes,0);assert.equal(sources.statistics.bytes,0);
 const scope=sources.register(prepared.buffer,prepared.images,world.signal);assert.throws(()=>scope.resolveURL('data:image/png;base64,overte-embedded-'+ '0'.repeat(64)),/Unregistered/);world.abort();
 assert.throws(()=>sources.register(prepared.buffer,prepared.images,world.signal),{name:'AbortError'});
});
test('identical prepared bytes never share blob identities across revoked visitor worlds',async()=>{
 const prepared=await extractEmbeddedFbxImages(embeddedFbx()),a=new AbortController(),b=new AbortController(),first=new EmbeddedFbxImages(a.signal),second=new EmbeddedFbxImages(b.signal);
 const marker=`data:image/png;base64,overte-embedded-${prepared.images[0].digest}`,urlA=first.register(prepared.buffer,prepared.images,a.signal).resolveURL(marker),urlB=second.register(prepared.buffer,prepared.images,b.signal).resolveURL(marker);
 assert.notEqual(urlA,urlB);a.abort();await assert.rejects(fetch(urlA));assert.equal((await fetch(urlB)).status,200);b.abort();assert.equal(first.statistics.bytes+second.statistics.bytes,0);
});
