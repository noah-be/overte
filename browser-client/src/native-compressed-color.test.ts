// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {NativeCompressedColorCache,nativeCompressedColorAlpha,nativeCompressedColorMaterialAlpha,setCompressedColorFlipY,UnsupportedNativeCompression} from './native-compressed-color';
// Self-contained component fixtures exercise lifecycle without requiring downloaded world assets in CI.
// Real saved Hub bytes are tested independently by lab/audit-native-ktx.test.mjs and the GPU fixture.
function fixture(size:number,alpha:boolean){
 const count=Math.floor(Math.log2(size))+1,key=new TextEncoder().encode('hifi.gpu\0'),payload=new Uint8Array(36);payload[0]=1;new DataView(payload.buffer).setUint32(29,alpha?13:1,true);
 const metadataSize=4+Math.ceil((key.length+payload.length)/4)*4;let dimension=size,length=64+metadataSize;
 for(let level=0;level<count;level++){length+=4+Math.ceil(dimension/4)**2*(alpha?16:8);dimension=Math.max(1,Math.floor(dimension/2));}
 const bytes=new Uint8Array(length),view=new DataView(bytes.buffer);bytes.set([0xab,0x4b,0x54,0x58,0x20,0x31,0x31,0xbb,13,10,26,10]);
 const header=[0x04030201,0,1,0,alpha?0x8c4f:0x8c4c,alpha?0x1908:0x1907,size,size,0,0,1,count,metadataSize];header.forEach((number,index)=>view.setUint32(12+index*4,number,true));
 view.setUint32(64,key.length+payload.length,true);bytes.set(key,68);bytes.set(payload,68+key.length);let offset=64+metadataSize;dimension=size;
 for(let level=0;level<count;level++){const size=Math.ceil(dimension/4)**2*(alpha?16:8);view.setUint32(offset,size,true);offset+=4;bytes.fill(0x42,offset,offset+size);offset+=size;dimension=Math.max(1,Math.floor(dimension/2));}
 return bytes;
}
const leaf=fixture(512,true),opaque=fixture(768,false);
function deferred<T>(){let resolve!: (value:T)=>void;let reject!:(reason:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function configuration(fetcher: typeof fetch,extra={}) {return {origin:'https://client.example',sessionId:'owned-session',authority:()=> 'revision1|domain',resolveAsset:(url:string)=>`https://client.example/api/assets/owned-session?url=${encodeURIComponent(url)}`,capabilities:{s3tc:true,s3tcSRGB:true,maximumTextureSize:32768},fetch:fetcher,...extra};}
function response(data=leaf){return new Response(data.slice(),{headers:{'content-length':String(data.length)}});}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
test('validated native-format blocks share one approved download while textures, samplers and alpha provenance stay independent',async()=>{
 const fetchReady=deferred<Response>();let requests=0;
 const cache=new NativeCompressedColorCache(configuration((async(_url,init)=>{requests++;assert.equal(init?.credentials,'same-origin');assert.equal(init?.redirect,'error');return fetchReady.promise;}) as typeof fetch));
 const first=cache.load('https://allowed.example/leaf.ktx',{sampler:{wrapS:THREE.ClampToEdgeWrapping,repeat:[2,3],offset:[.1,.2],flipY:true}});
 const second=cache.load('https://allowed.example/leaf.ktx',{sampler:{wrapS:THREE.RepeatWrapping,flipY:false}});
 fetchReady.resolve(response());const [a,b]=await Promise.all([first,second]);
 assert.equal(requests,1);assert.notEqual(a,b);assert.equal(a.source,b.source);assert.notEqual(a.mipmaps,b.mipmaps);assert.equal(a.mipmaps[0].data,b.mipmaps[0].data);
 assert.equal(a.format,THREE.RGBA_S3TC_DXT5_Format);assert.equal(a.colorSpace,THREE.SRGBColorSpace);assert.equal(a.wrapS,THREE.ClampToEdgeWrapping);assert.equal(b.wrapS,THREE.RepeatWrapping);
 assert.equal(a.flipY,false);assert.equal(a.matrixAutoUpdate,false);
 const uv=new THREE.Vector2(.2,.3).applyMatrix3(a.matrix);assert.ok(Math.abs(uv.x-.5)<1e-12);assert.ok(Math.abs(uv.y-(-.1))<1e-12);
 assert.equal(nativeCompressedColorAlpha(a),'mask');assert.equal(nativeCompressedColorAlpha(new THREE.Texture()),undefined);
 assert.equal(nativeCompressedColorMaterialAlpha(a,{useAlpha:true}),'mask');assert.equal(nativeCompressedColorMaterialAlpha(a,{useAlpha:false}),'opaque');
 assert.equal(nativeCompressedColorMaterialAlpha(a,{useAlpha:true,mode:'OPACITY_MAP_OPAQUE'}),'opaque');assert.equal(nativeCompressedColorMaterialAlpha(a,{useAlpha:false,mode:'OPACITY_MAP_BLEND'}),'blend');
 const spoof=new THREE.CompressedTexture([],1,1);spoof.userData={nativeUsage:{classification:'mask'}};assert.equal(nativeCompressedColorAlpha(spoof),undefined);
 a.dispose();assert.equal(nativeCompressedColorAlpha(a),undefined);assert.equal(nativeCompressedColorAlpha(b),'mask');
 const version=b.source.version,c=await cache.load('https://allowed.example/leaf.ktx');assert.equal(requests,1);assert.equal(nativeCompressedColorAlpha(c),'mask');assert.equal(c.source,b.source);assert.equal(b.source.version,version);
 b.dispose();c.dispose();cache.dispose();assert.equal(cache.statistics.retainedBytes,0);
});
test('deadline rejects readers at the original bound, retaining ownership until an uncancellable fetch settles',async()=>{
 const ready=deferred<Response>();let signal:AbortSignal|undefined;
 const cache=new NativeCompressedColorCache(configuration((async(_u,init)=>{signal=init?.signal as AbortSignal;return ready.promise;}) as typeof fetch,{deadlineMs:15,maximumActive:1}));
 await assert.rejects(cache.load('a'),/deadline/);assert.equal(signal?.aborted,true);assert.equal(cache.statistics.active,1);assert.equal(cache.statistics.readers,0);
 await assert.rejects(cache.load('a'),{name:'AbortError'});
 ready.resolve(response());await tick();assert.equal(cache.statistics.active,0);assert.equal(cache.statistics.retainedEntries,0);cache.dispose();
});
test('revocation during streaming rejects data, cancels its real reader and never retains stale bytes',async()=>{
 let authority:string|null='revision1|domain',cancelled=false;let stream!:ReadableStreamDefaultController<Uint8Array>;
 const cache=new NativeCompressedColorCache(configuration((async()=>new Response(new ReadableStream<Uint8Array>({start(c){stream=c;},cancel(){cancelled=true;}}))) as typeof fetch,{authority:()=>authority}));
 const pending=cache.load('a');await tick();stream.enqueue(leaf.slice(0,256));await tick();authority=null;stream.enqueue(leaf.slice(256));await assert.rejects(pending,{name:'AbortError'});
 assert.equal(cancelled,true);await tick();assert.equal(cache.statistics.retainedBytes,0);assert.equal(cache.statistics.active,0);cache.dispose();
});
test('an oversized streamed response is cancelled even without a content-length header',async()=>{
 let cancelled=false;
 const cache=new NativeCompressedColorCache(configuration((async()=>new Response(new ReadableStream<Uint8Array>({start(c){c.enqueue(new Uint8Array(1025));},cancel(){cancelled=true;}}))) as typeof fetch,{maximumAssetBytes:1024}));
 await assert.rejects(cache.load('a'),/byte bound/);assert.equal(cancelled,true);await tick();assert.equal(cache.statistics.retainedEntries,0);cache.dispose();
});
test('cache delivery rechecks approval and refuses credentials, wrong sessions or unvalidated alternate routes',async()=>{
 let authority:string|null='revision1|domain';let requests=0;
 const config=configuration((async()=>{requests++;return response();}) as typeof fetch,{authority:()=>authority});
 const cache=new NativeCompressedColorCache(config);(await cache.load('https://allowed.example/leaf.ktx')).dispose();
 const late=cache.load('https://allowed.example/leaf.ktx');authority='revision2|domain';await assert.rejects(late,/authority changed/);assert.equal(requests,1);
 (await cache.load('https://allowed.example/leaf.ktx')).dispose();assert.equal(requests,2);cache.dispose();
 for(const address of ['https://evil.example/api/assets/owned-session?url=x','https://client.example/api/assets/other?url=x','https://user:password@client.example/api/assets/owned-session?url=x','https://client.example/api/assets/owned-session?url=x&extra=1','https://client.example/api/assets/owned-session?url=x#fragment']){
  const refused=new NativeCompressedColorCache({...config,resolveAsset:()=>address});await assert.rejects(refused.load('x'),/owned gateway session/);refused.dispose();
 }
});
test('ready readers obey the same cap and release their slot on cancellation or changed authority',async()=>{
 let authority:string|null='revision1|domain';
 const cache=new NativeCompressedColorCache(configuration((async()=>response()) as typeof fetch,{authority:()=>authority,maximumReaders:2}));
 (await cache.load('a')).dispose();await tick();
 const controller=new AbortController(),first=cache.load('a',{signal:controller.signal}),second=cache.load('a');
 assert.equal(cache.statistics.readers,2);const refused=assert.rejects(cache.load('a'),/readers/);controller.abort();authority='revision2|domain';
 await Promise.all([refused,assert.rejects(first,{name:'AbortError'}),assert.rejects(second,/authority changed/)]);assert.equal(cache.statistics.readers,0);cache.dispose();
});
test('non-string, empty and oversized UTF-8 authority identities are refused without retaining keys or fetching',async()=>{
 let requests=0;
 for(const authority of [42,{},'', 'x'.repeat(4097),'界'.repeat(1366)]){
  const cache=new NativeCompressedColorCache(configuration((async()=>{requests++;return response();}) as typeof fetch,{authority:()=>authority as string}));
  await assert.rejects(cache.load('a'),/bounded nonempty scope token/);assert.deepEqual(cache.statistics,{retainedBytes:0,retainedEntries:0,active:0,queued:0,readers:0});cache.dispose();
 }
 assert.equal(requests,0);
});
test('one reader cancellation preserves shared bytes; last cancellation keeps a real pending fetch slot until settlement',async()=>{
 const pending=deferred<Response>();let aborted=false;let requests=0;
 const cache=new NativeCompressedColorCache(configuration((async(_u,init)=>{requests++;init?.signal?.addEventListener('abort',()=>{aborted=true;});return requests===1?pending.promise:response();}) as typeof fetch,{maximumActive:1}));
 const a=new AbortController(),b=new AbortController();
 const first=cache.load('atp:/leaf.ktx',{signal:a.signal}),second=cache.load('atp:/leaf.ktx',{signal:b.signal});
 a.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(aborted,false);b.abort();await assert.rejects(second,{name:'AbortError'});assert.equal(aborted,true);assert.equal(cache.statistics.active,1);
 const replacement=cache.load('atp:/other.ktx');assert.equal(requests,1);assert.equal(cache.statistics.queued,1);
 pending.resolve(response());(await replacement).dispose();assert.equal(requests,2);
 await tick();assert.equal(cache.statistics.active,0);cache.dispose();
});
test('stream, retained bytes and queue bounds are enforced without malformed KTX fallback',async()=>{
 let calls=0;
 const cache=new NativeCompressedColorCache(configuration((async()=>{calls++;return response();}) as typeof fetch,{maximumCacheBytes:leaf.length,maximumCacheEntries:1}));
 (await cache.load('a')).dispose();(await cache.load('b')).dispose();assert.equal(cache.statistics.retainedEntries,1);assert.equal(cache.statistics.retainedBytes,leaf.length);
 (await cache.load('a')).dispose();assert.equal(calls,3);cache.dispose();
 const over=new NativeCompressedColorCache(configuration((async()=>response()) as typeof fetch,{maximumAssetBytes:leaf.length-1}));await assert.rejects(over.load('a'),/byte bound/);over.dispose();
 const malformed=new NativeCompressedColorCache(configuration((async()=>response(new Uint8Array(64))) as typeof fetch));await assert.rejects(malformed.load('a'),/KTX1 signature/);malformed.dispose();
 const unsupported=new NativeCompressedColorCache(configuration((async()=>response()) as typeof fetch,{capabilities:{s3tc:true,s3tcSRGB:false,maximumTextureSize:32768}}));await assert.rejects(unsupported.load('a'),UnsupportedNativeCompression);unsupported.dispose();
 const ready=deferred<Response>();const bounded=new NativeCompressedColorCache(configuration((async()=>ready.promise) as typeof fetch,{maximumActive:1,maximumQueued:1}));const x=bounded.load('x'),y=bounded.load('y');await assert.rejects(bounded.load('z'),/queued/);bounded.dispose();await Promise.all([assert.rejects(x,{name:'AbortError'}),assert.rejects(y,{name:'AbortError'})]);ready.resolve(response());await tick();assert.equal(bounded.statistics.active,0);
});
test('opaque non-power-of-two mip dimensions are integral and texture clone cannot inherit trusted alpha',async()=>{
 const cache=new NativeCompressedColorCache(configuration((async()=>response(opaque)) as typeof fetch));const texture=await cache.load('opaque');
 assert.equal(texture.mipmaps.length,10);assert.deepEqual(texture.mipmaps.slice(-3).map(m=>[m.width,m.height]),[[6,6],[3,3],[1,1]]);assert.equal(nativeCompressedColorAlpha(texture),'opaque');
 const clone=texture.clone();assert.equal(nativeCompressedColorAlpha(clone),undefined);assert.throws(()=>setCompressedColorFlipY(clone,true),/owned/);
 texture.source=new THREE.TextureSource({width:1,height:1});assert.equal(nativeCompressedColorAlpha(texture),undefined);texture.dispose();clone.dispose();cache.dispose();
});

test('metadata approval capture rejects later authority changes and disposal without allocating readers',()=>{
 let authority='revision1';const cache=new NativeCompressedColorCache(configuration((async()=>response()) as typeof fetch,{authority:()=>authority}));
 const first=cache.captureApproval();first();authority='revision2';assert.throws(first,/revoked/);
 const second=cache.captureApproval();second();cache.dispose();assert.throws(second,/revoked/);assert.throws(()=>cache.captureApproval(),/revoked/);
 assert.deepEqual(cache.statistics,{retainedBytes:0,retainedEntries:0,active:0,queued:0,readers:0});
});
