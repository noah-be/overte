// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual private World material methods and Three resources; metadata/byte I/O are controlled inputs.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
import {NativeCompressedColorCache,UnsupportedNativeCompression,nativeCompressedColorAlpha} from '../src/native-compressed-color';
import {applyNativeMaterialAlpha} from '../src/native-alpha-material';
import {colorTextureCandidate,readColorTextureMetadata} from '../src/color-texture-metadata';
const caps={s3tc:true,s3tcSRGB:true,maximumTextureSize:32768};
const format='COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT';
const metadata={version:1,compressed:{[format]:'mask.ktx'},original:'original.png'};
function fixtureBytes(){const data=new Uint8Array(64+52+4+16),v=new DataView(data.buffer);data.set([0xab,0x4b,0x54,0x58,0x20,0x31,0x31,0xbb,13,10,26,10]);[0x04030201,0,1,0,0x8c4f,0x1908,4,4,0,0,1,1,52].forEach((n,i)=>v.setUint32(12+4*i,n,true));v.setUint32(64,45,true);data.set(new TextEncoder().encode('hifi.gpu\0'),68);data[77]=1;v.setUint32(106,13,true);v.setUint32(116,16,true);return data;}
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function worldFixture(options:{enabled?:boolean;gpu?:boolean;fetcher?:typeof fetch}={}){
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),requests:string[]=[],images:string[]=[],imageTextures:THREE.Texture[]=[];
 const cache=new NativeCompressedColorCache({origin:'https://client.example',sessionId:'owned',authority:()=>!abort.signal.aborted?'approval1':null,
  resolveAsset:url=>`https://client.example/api/assets/owned?url=${encodeURIComponent(url)}`,capabilities:caps,
  fetch:options.fetcher??(async(input)=>{requests.push(new URL(String(input)).searchParams.get('url')!);return new Response(fixtureBytes());}) as typeof fetch});
 let factories=0;
 Object.assign(context,{abort,disposed:false,modelReaders:new WeakMap(),loadManagers:new Set(),loadPhases:new Map(),renderer:{capabilities:{maxTextureSize:32768,getMaxAnisotropy:()=>16},extensions:{has:()=>options.gpu!==false},getContext:()=>{throw Error('Compressed capability lookup must use current renderer caches');}},
  options:{resolveAsset:(url:string)=>url,onStatus(){},...(options.enabled===false?{}:{compressedColors:()=>{factories++;return cache;}})},
  imageCache:{loader:()=>({loadAsync:async(url:string)=>{images.push(url);const texture=new THREE.Texture({width:4,height:4} as TexImageSource);imageTextures.push(texture);return texture;}})}});
 return {context,cache,abort,requests,images,imageTextures,get factories(){return factories;}};
}

test('native metadata chooses only explicit color roles and supported codecs, including extensionless ATP identifiers',()=>{
 assert.deepEqual(colorTextureCandidate(metadata,'albedo',caps),{source:'mask.ktx',format:THREE.RGBA_S3TC_DXT5_Format});
 assert.deepEqual(colorTextureCandidate(metadata,'emissive',caps),{source:'mask.ktx',format:THREE.RGBA_S3TC_DXT5_Format});
 assert.equal(colorTextureCandidate(metadata,'linear',caps),undefined);assert.equal(colorTextureCandidate(metadata,'other',caps),undefined);
 assert.equal(colorTextureCandidate(metadata,'albedo',{...caps,s3tcSRGB:false}),undefined);
 assert.equal(colorTextureCandidate({version:1,compressed:{COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:'etc.ktx'}},'albedo',caps),undefined);
 assert.equal(colorTextureCandidate({version:1,compressed:{[format]:'atp:/'+ 'a'.repeat(64)}},'albedo',caps)?.source,'atp:/'+ 'a'.repeat(64));
 for(const bad of [{version:'1',compressed:{}},{version:1,compressed:[]},{version:1,compressed:{[format]:{} }},{version:1,compressed:{[format]:'x'.repeat(4097)}}])assert.throws(()=>colorTextureCandidate(bad,'albedo',caps));
});
test('actual material factory uses private compressed alpha without canvas inspection and keeps native explicit modes first',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const w=worldFixture();
 const material=await w.context.makeMaterial({albedoMap:'color.texmeta.json',opacityMap:'color.texmeta.json'},'https://assets.example/material.json');
 assert.ok(material.map instanceof THREE.CompressedTexture);assert.equal(nativeCompressedColorAlpha(material.map),'mask');assert.equal(material.alphaTest,.5);assert.equal(material.transparent,false);assert.equal(material.depthWrite,true);assert.equal(w.images.length,0);assert.deepEqual(w.requests,['https://assets.example/mask.ktx']);
 await applyNativeMaterialAlpha(material,{useAlpha:true,mode:'OPACITY_MAP_OPAQUE'});assert.equal(material.alphaTest,0);
 await applyNativeMaterialAlpha(material,{useAlpha:false,mode:'OPACITY_MAP_BLEND'});assert.equal(material.transparent,true);
 await applyNativeMaterialAlpha(material,{useAlpha:false,mode:'OPACITY_MAP_MASK'});assert.equal(material.alphaTest,.5);
 material.map.dispose();material.dispose();w.cache.dispose();
});
test('scalar/normal and unknown roles preserve PNG while albedo and emissive may use compressed bytes',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const w=worldFixture();const material=await w.context.makeMaterial({albedoMap:'a.texmeta.json',emissiveMap:'e.texmeta.json',normalMap:'n.texmeta.json',roughnessMap:'r.texmeta.json',metallicMap:'m.texmeta.json'},'https://assets.example/material.json');
 assert.ok(material.map instanceof THREE.CompressedTexture);assert.ok(material.emissiveMap instanceof THREE.CompressedTexture);
 assert.ok(!(material.normalMap instanceof THREE.CompressedTexture));assert.ok(!(material.roughnessMap instanceof THREE.CompressedTexture));assert.ok(!(material.metalnessMap instanceof THREE.CompressedTexture));
 assert.equal(w.factories,2);assert.equal(w.requests.length,1);assert.equal(w.images.length,3);
 const image=await w.context.texture('https://assets.example/i.texmeta.json');assert.ok(!(image instanceof THREE.CompressedTexture));assert.equal(w.factories,2);image.dispose();
 for(const map of [material.map,material.emissiveMap,material.normalMap,material.roughnessMap,material.metalnessMap])map?.dispose();material.dispose();w.cache.dispose();
 const disabled=worldFixture({enabled:false});const old=await disabled.context.makeMaterial({albedoMap:'a.texmeta.json'},'https://assets.example/material.json');assert.ok(!(old.map instanceof THREE.CompressedTexture));assert.equal(disabled.requests.length,0);old.map.dispose();old.dispose();disabled.cache.dispose();
});
test('known unsupported GPU/role may use the original; malformed KTX and denied authority never fall back',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const unsupported=worldFixture({fetcher:(async()=>{throw new UnsupportedNativeCompression('Known unsupported color role');}) as typeof fetch});
 const png=await unsupported.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo');assert.ok(!(png instanceof THREE.CompressedTexture));assert.equal(unsupported.images.length,1);png.dispose();unsupported.cache.dispose();
 const gpu=worldFixture({gpu:false});const original=await gpu.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo');assert.equal(gpu.requests.length,0);original.dispose();gpu.cache.dispose();
 const malformed=worldFixture({fetcher:(async()=>new Response(new Uint8Array(64))) as typeof fetch});await assert.rejects(malformed.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo'),/KTX1 signature/);assert.equal(malformed.images.length,0);malformed.cache.dispose();
 const denied=worldFixture();denied.context.options.compressedColors=()=>{throw Error('Current approval refused');};await assert.rejects(denied.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo'),/approval refused/);assert.equal(denied.images.length,0);denied.cache.dispose();
});
test('revocation while reading unsupported-codec metadata prevents its original-image fallback',async t=>{
 const ready=deferred<Response>();t.mock.method(globalThis,'fetch',()=>ready.promise);
 const w=worldFixture({gpu:false}),pending=w.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo');w.cache.dispose();ready.resolve(new Response(JSON.stringify(metadata)));
 await assert.rejects(pending,/authority was revoked/);assert.equal(w.images.length,0);
});
test('model cancellation disposes successful sibling maps and rejects deferred compressed bytes',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const ready=deferred<Response>(),w=worldFixture({fetcher:(async()=>ready.promise) as typeof fetch}),model=new AbortController();
 const pending=w.context.makeMaterial({albedoMap:'a.texmeta.json',normalMap:'normal.png'},'https://assets.example/material.json',model.signal);
 await tick();assert.equal(w.imageTextures.length,1);let disposed=0;w.imageTextures[0].addEventListener('dispose',()=>disposed++);model.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(disposed,1);ready.resolve(new Response(fixtureBytes()));await tick();assert.equal(w.cache.statistics.active,0);assert.equal(w.cache.statistics.retainedEntries,0);w.cache.dispose();
});
test('metadata byte limits cancel real streams and malformed codec bindings dispose their returned texture',async t=>{
 let cancelled=false;const signal=new AbortController().signal;
 await assert.rejects(readColorTextureMetadata(new Response(new ReadableStream<Uint8Array>({start(c){c.enqueue(new Uint8Array(65537));},cancel(){cancelled=true;}})),signal),/byte bound/);assert.equal(cancelled,true);
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({...metadata,compressed:{COMPRESSED_SRGB_S3TC_DXT1_EXT:'mask.ktx'}})));
 const w=worldFixture();let disposed=0;const load=w.cache.load.bind(w.cache);w.cache.load=async(...args)=>{const texture=await load(...args);texture.addEventListener('dispose',()=>disposed++);return texture;};await assert.rejects(w.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo'),/codec differs/);assert.equal(disposed,1);assert.equal(w.images.length,0);w.cache.dispose();
});

test('original-image delivery after unsupported codec rechecks captured approval and disposes revoked bytes',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const w=worldFixture({gpu:false}),ready=deferred<THREE.Texture>(),texture=new THREE.Texture();let disposed=0;texture.addEventListener('dispose',()=>disposed++);
 w.context.imageCache={loader:()=>({loadAsync:()=>ready.promise})};
 const pending=w.context.originalTexture('https://assets.example/a.texmeta.json',true,'albedo');await tick();w.cache.dispose();ready.resolve(texture);
 await assert.rejects(pending,/authority was revoked/);assert.equal(disposed,1);
});

test('model signal cancels a genuinely pending metadata stream before its next byte',async()=>{
 let cancelled=false;const controller=new AbortController();
 const pending=readColorTextureMetadata(new Response(new ReadableStream<Uint8Array>({cancel(){cancelled=true;}})),controller.signal);
 controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(cancelled,true);
});

function imageEntity(w:ReturnType<typeof worldFixture>,emissive?:boolean){
 const root=new THREE.Group(),entity={id:'owned-image',type:'Image',imageURL:'https://assets.example/image.texmeta.json',dimensions:{x:2,y:1,z:.01},emissive};
 w.context.objects=new Map([[entity.id,root]]);return {root,entity,pending:()=>w.context.populateEntity(entity,root),material:()=>{const mesh=root.children[0]?.children[0];assert.ok(mesh instanceof THREE.Mesh);assert.ok(mesh.material instanceof THREE.MeshBasicMaterial || mesh.material instanceof THREE.MeshStandardMaterial);return mesh.material;}};
}

test('actual Image entity admits audited compressed color without original pixels and retains existing alpha/UV state',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const w=worldFixture(),image=imageEntity(w);
 try{await image.pending();const material=image.material();assert.ok(material.map instanceof THREE.CompressedTexture);assert.equal(nativeCompressedColorAlpha(material.map),'mask');assert.equal(material.map.colorSpace,THREE.SRGBColorSpace);assert.equal(material.map.flipY,false);assert.deepEqual(material.map.matrix.elements,[1,0,0,0,-1,0,0,1,1]);assert.equal(material.transparent,true);assert.equal(material.alphaTest,0,'Image SIMPLE path blends image alpha, not the model opacity-map cutoff');assert.equal(material.depthWrite,false);assert.equal(material.side,THREE.DoubleSide);assert.equal(material.forceSinglePass,true);assert.equal(w.images.length,0);assert.deepEqual(w.requests,['https://assets.example/mask.ktx']);assert.equal(w.factories,1);}
 finally{image.root.traverse(object=>{if(object instanceof THREE.Mesh){(object.material as THREE.MeshBasicMaterial).map?.dispose();(object.material as THREE.MeshBasicMaterial).dispose();object.geometry.dispose();}});w.cache.dispose();}
});

test('Image entity keeps supported PNG fallback but refuses malformed KTX and expired authority',async t=>{
 // Controlled browser platform bridge, not an actual GPU/pixel proof. All sixteen
 // fixture pixels are opaque; the production inspector still validates counts.
 const originals=['createImageBitmap','Worker'].map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)] as const);
 t.after(()=>{for(const [name,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else Reflect.deleteProperty(globalThis,name);}});
 Object.defineProperty(globalThis,'createImageBitmap',{configurable:true,writable:true,value:async()=>({width:4,height:4,close(){}}) as ImageBitmap});
 class ImageAlphaWorker {
  onmessage?: (event:{data:unknown})=>void;
  postMessage(data:{id:number}){queueMicrotask(()=>this.onmessage?.({data:{id:data.id,total:16,opaque:16,intermediate:0}}));}
  terminate(){}
 }
 Object.defineProperty(globalThis,'Worker',{configurable:true,writable:true,value:ImageAlphaWorker});

 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 for(const options of [{gpu:false},{enabled:false}]){const w=worldFixture(options),image=imageEntity(w);await image.pending();const material=image.material();assert.ok(!(material.map instanceof THREE.CompressedTexture));assert.deepEqual(w.images,['https://assets.example/original.png']);assert.equal(w.requests.length,0);material.map?.dispose();material.dispose();image.root.traverse(object=>{if(object instanceof THREE.Mesh)object.geometry.dispose();});w.cache.dispose();}
 const bad=worldFixture({fetcher:(async()=>new Response(new Uint8Array(64))) as typeof fetch}),image=imageEntity(bad);await assert.rejects(image.pending(),/KTX1 signature/);assert.equal(bad.images.length,0);assert.equal(image.root.children[0].children.length,0);bad.cache.dispose();
 const denied=worldFixture();denied.context.options.compressedColors=()=>{throw Error('Current approval refused');};await assert.rejects(imageEntity(denied).pending(),/approval refused/);assert.equal(denied.images.length,0);denied.cache.dispose();
});

test('native Image defaultfalse is lit and explicit true retains unlit presentation',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 for(const emissive of [true,false,undefined]){
  const w=worldFixture(),image=imageEntity(w,emissive);
  try{await image.pending();const material=image.material();assert.equal(material.toneMapped,emissive!==true);assert.equal(material instanceof THREE.MeshBasicMaterial,emissive===true);assert.equal(material instanceof THREE.MeshStandardMaterial,emissive!==true);}
  finally{image.root.traverse(object=>{if(object instanceof THREE.Mesh){(object.material as THREE.MeshBasicMaterial).map?.dispose();(object.material as THREE.MeshBasicMaterial).dispose();object.geometry.dispose();}});w.cache.dispose();}
 }
});

test('Image entity cancellation releases pending compressed work with no late mesh or texture fallback',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const ready=deferred<Response>(),w=worldFixture({fetcher:(async()=>ready.promise) as typeof fetch}),image=imageEntity(w),pending=image.pending();await tick();w.abort.abort();w.cache.dispose();await assert.rejects(pending,{name:'AbortError'});assert.equal(image.root.children[0].children.length,0);assert.equal(w.images.length,0);ready.resolve(new Response(fixtureBytes()));await tick();assert.equal(w.cache.statistics.retainedEntries,0);assert.equal(w.cache.statistics.active,0);
});

test('actual World metadata reuse still checks each color approval and preserves independent texture samplers',async t=>{
 let requests=0;t.mock.method(globalThis,'fetch',async()=>{requests++;return new Response(JSON.stringify(metadata));});
 const w=worldFixture();
 try{
  const [a,b]=await Promise.all([w.context.texture('https://assets.example/reused.texmeta.json',true,'albedo'),w.context.texture('https://assets.example/reused.texmeta.json',true,'emissive')]);
  assert.equal(requests,1);assert.notEqual(a,b);assert.equal(a.source,b.source);assert.equal(w.factories,2);assert.equal(w.context.sourceTexts.stats.hits,1);a.dispose();b.dispose();
  w.context.options.compressedColors=()=>{throw Error('Current approval refused');};await assert.rejects(w.context.texture('https://assets.example/reused.texmeta.json',true,'albedo'),/approval refused/);assert.equal(requests,1,'Rejected approval must not gain access through a metadata hit');assert.equal(w.images.length,0);
 }finally{w.abort.abort();w.cache.dispose();}
});

test('one canceled actual World texture reader leaves the sibling metadata/color transfer intact',async t=>{
 const response=deferred<Response>();let requests=0;t.mock.method(globalThis,'fetch',()=>{requests++;return response.promise;});
 const w=worldFixture(),firstOwner=new AbortController();
 try{
  const first=w.context.texture('https://assets.example/shared.texmeta.json',true,'albedo',firstOwner.signal),second=w.context.texture('https://assets.example/shared.texmeta.json',true,'albedo');await tick();firstOwner.abort();await assert.rejects(first,{name:'AbortError'});response.resolve(new Response(JSON.stringify(metadata)));const texture=await second;assert.ok(texture instanceof THREE.CompressedTexture);assert.equal(requests,1);assert.equal(w.context.sourceTexts.stats.readers,0);assert.equal(w.requests.length,1);texture.dispose();
 }finally{response.resolve(new Response(JSON.stringify(metadata)));w.abort.abort();w.cache.dispose();}
});

test('actual World raw metadata drops prior permission generations and refuses revoked ready or pending delivery',async t=>{
 let requests=0,generation='one',approved=true;const delayed=deferred<Response>();t.mock.method(globalThis,'fetch',async()=>{requests++;return requests===3?delayed.promise:new Response(JSON.stringify({request:requests}));});
 const w=worldFixture();w.context.options.captureAssetAuthority=()=>{if(!approved)throw Error('Current asset approval refused');const captured=generation;return {generation:captured,assertCurrent(){if(!approved||generation!==captured)throw Error('Asset authority was revoked');}};};
 try{
  assert.equal(JSON.parse(await w.context.sourceText('authorized-metadata','metadata',64)).request,1);assert.equal(JSON.parse(await w.context.sourceText('authorized-metadata','metadata',64)).request,1);assert.equal(requests,1);
  const old=w.context.sourceTexts;generation='two';assert.equal(JSON.parse(await w.context.sourceText('authorized-metadata','metadata',64)).request,2);assert.equal(old.stats.disposed,true);assert.equal(old.stats.bytes,0);
  approved=false;await assert.rejects(w.context.sourceText('authorized-metadata','metadata',64),/approval refused/);assert.equal(requests,2);approved=true;
  const pending=w.context.sourceText('other-metadata','metadata',64);await tick();generation='three';delayed.resolve(new Response('{"stale":true}'));await assert.rejects(pending,/authority was revoked/);w.context.invalidateSourceTexts();assert.equal(w.context.sourceTexts,undefined);
 }finally{delayed.resolve(new Response('{}'));w.abort.abort();w.cache.dispose();}
});

test('actual World HTTP material selectors share source text while queries and ATP fragments stay distinct',async t=>{
 const requests:string[]=[];t.mock.method(globalThis,'fetch',async (input:RequestInfo|URL)=>{requests.push(String(input));return new Response('{"materials":[]}');});const w=worldFixture();
 try{
  await w.context.sourceText('https://assets.example/material.json?variant=1#first','material',1024);await w.context.sourceText('https://assets.example/material.json?variant=1#second','material',1024);await w.context.sourceText('https://assets.example/material.json?variant=2#first','material',1024);await w.context.sourceText('atp:/material.json#first','material',1024);await w.context.sourceText('atp:/material.json#second','material',1024);
  assert.deepEqual(requests,['https://assets.example/material.json?variant=1','https://assets.example/material.json?variant=2','atp:/material.json#first','atp:/material.json#second']);assert.equal(w.context.sourceTexts.stats.hits,1);
 }finally{w.abort.abort();w.cache.dispose();}
});

 test('actual Image removal aborts its reader while compressed bytes are pending',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
  const ready=deferred<Response>(),w=worldFixture({fetcher:(async()=>ready.promise) as typeof fetch}),image=imageEntity(w);
  Object.assign(w.context,{entities:new Map([[image.entity.id,image.entity]]),signatures:new Map(),meshCollisions:new Map(),modelGeometry:new WeakMap(),localLights:new Set(),modelBatches:new Map(),scene:new THREE.Scene(),colliders:[],pendingModelColliders:[]});
  const pending=image.pending();await tick();w.context.removeEntities([image.entity.id]);
  await assert.rejects(pending,{name:'AbortError'});assert.equal(w.context.modelReaders.get(image.root).signal.aborted,true);assert.equal(w.context.objects.size,0);assert.equal(image.root.children[0].children.length,0);
  ready.resolve(new Response(fixtureBytes()));await tick();assert.equal(w.cache.statistics.active,0);assert.equal(w.cache.statistics.retainedEntries,0);w.cache.dispose();
 });

test('actual Image late original delivery rejects its captured permission revision and disposes the reader clone',async()=>{
 const w=worldFixture(),image=imageEntity(w);image.entity.imageURL='https://assets.example/original.png';
 const ready=deferred<THREE.Texture>();let approved=true,captures=0,checks=0,disposed=0;
 w.context.options.captureAssetAuthority=()=>{captures++;return {generation:'old-permission',assertCurrent(){checks++;if(!approved)throw new DOMException('Image approval revoked','AbortError');}};};
 w.context.imageCache.loader=()=>({loadAsync:()=>ready.promise});
 const pending=image.pending();approved=false;const texture=new THREE.Texture({width:4,height:4} as TexImageSource);texture.addEventListener('dispose',()=>disposed++);ready.resolve(texture);
 await assert.rejects(pending,{name:'AbortError'});assert.equal(captures,1);assert.ok(checks>=2);assert.equal(disposed,1);assert.equal(image.root.children[0].children.length,0);w.cache.dispose();
});
test('malformed native Image color releases its successful compressed clone before publication',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(metadata)));
 const w=worldFixture(),image=imageEntity(w);Object.assign(image.entity,{color:{red:-1,green:0,blue:0}});
 await assert.rejects(image.pending(),/byte channels/);assert.equal(image.root.children[0].children.length,0);assert.equal(w.cache.statistics.active,0);w.cache.dispose();
});
