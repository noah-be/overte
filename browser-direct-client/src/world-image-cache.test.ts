// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {LoadingManager,SRGBColorSpace,NoColorSpace} from 'three';
import {WorldImageCache} from './world-image-cache';
class FakeImage extends EventTarget {
  crossOrigin='';naturalWidth=4;naturalHeight=4;url='';cancelled=0;decodeCount=0;
  set src(value:string){this.url=value;}get src(){return this.url;}
  removeAttribute(name:string){if(name==='src'){this.cancelled++;this.url='';}}
  async decode(){this.decodeCount++;}
  loaded(){this.dispatchEvent(new Event('load'));}failed(){this.dispatchEvent(new Event('error'));}
}
const turn=()=>new Promise<void>(resolve=>setTimeout(resolve,0));
function setup(options:Partial<ConstructorParameters<typeof WorldImageCache>[0]>={}){
  const controller=new AbortController(),images:FakeImage[]=[];
  const cache=new WorldImageCache({signal:controller.signal,createImage:()=>{const image=new FakeImage();images.push(image);return image as unknown as HTMLImageElement;},...options});
  return {cache,images,controller};
}
test('Two model managers share one real image/source identity while owning separate samplers and color spaces',async()=>{
  const {cache,images,controller}=setup(),a=new LoadingManager(),b=new LoadingManager();let loadedA=0,loadedB=0;a.onLoad=()=>loadedA++;b.onLoad=()=>loadedB++;
  const first=cache.loader(a).loadAsync('https://gateway.invalid/same.png'),second=cache.loader(b).loadAsync('https://gateway.invalid/same.png');
  assert.equal(images.length,1);images[0].loaded();const [left,right]=await Promise.all([first,second]);await turn();
  assert.notEqual(left,right);assert.equal(left.source,right.source);assert.equal(left.image,right.image);assert.equal(loadedA,1);assert.equal(loadedB,1);assert.equal(images[0].decodeCount,1);
  left.colorSpace=SRGBColorSpace;right.colorSpace=NoColorSpace;left.repeat.set(2,3);assert.deepEqual(right.repeat.toArray(),[1,1]);assert.equal(right.colorSpace,NoColorSpace);
  left.dispose();assert.equal(right.image,images[0],'Disposing a material texture must not invalidate its neighbor');assert.equal(images[0].cancelled,0);
  assert.equal(cache.stats().cacheHits,1);controller.abort();assert.equal(images[0].cancelled,0,'Closing ready cache releases references, not another texture image');
});
test('Every cached consumer retains its own manager start/end ordering including ready hits',async()=>{
  const {cache,images,controller}=setup(),manager=new LoadingManager(),events:string[]=[];
  manager.onStart=()=>events.push('start');manager.onLoad=()=>events.push('end');
  const loader=cache.loader(manager).setPath('https://gateway.invalid/textures/');
  const pending=loader.loadAsync('actual.png');assert.deepEqual(events,['start']);assert.equal(images[0].url,'https://gateway.invalid/textures/actual.png');images[0].loaded();await pending;await turn();
  const shared=(await pending).source,version=shared.version;
  const hit=loader.loadAsync('actual.png');assert.equal(shared.version,version,'A ready image hit cannot invalidate unchanged GPU source storage');assert.deepEqual(events,['start','end','start']);await hit;await turn();assert.deepEqual(events,['start','end','start','end']);assert.equal(images.length,1);controller.abort();
});
test('Manager cancellation cancels only its consumer and shared pending images stay alive for another model',async()=>{
  const {cache,images,controller}=setup(),a=new LoadingManager(),b=new LoadingManager();
  const first=cache.loader(a).loadAsync('https://gateway.invalid/shared.png'),second=cache.loader(b).loadAsync('https://gateway.invalid/shared.png');
  a.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(images[0].cancelled,0);images[0].loaded();await second;controller.abort();
});
test('Last consumer cancellation removes owned src and session revocation never starts queued images',async()=>{
  const {cache,images,controller}=setup({maximumActive:1}),a=new LoadingManager(),b=new LoadingManager();
  const first=cache.loader(a).loadAsync('https://gateway.invalid/one.png'),second=cache.loader(b).loadAsync('https://gateway.invalid/two.png');
  const settled=Promise.allSettled([first,second]);assert(images[0].url.endsWith('/one.png'));assert.equal(images[1].url,'');
  controller.abort();const results=await settled;assert(results.every(result=>result.status==='rejected'));assert.equal(images[0].cancelled,1);assert.equal(images[1].cancelled,1);assert.equal(cache.stats().active,0);assert.equal(cache.stats().queued,0);assert.equal(cache.stats().pending,0);
});
test('Decoded-cache entry/pixel eviction preserves existing texture images and never crosses world sessions',async()=>{
  const {cache,images,controller}=setup({maximumEntries:1,maximumPixels:16});
  const a=cache.loader(new LoadingManager()).loadAsync('https://gateway.invalid/a.png');images[0].loaded();const first=await a;
  const b=cache.loader(new LoadingManager()).loadAsync('https://gateway.invalid/b.png');images[1].loaded();await b;
  assert.equal(cache.stats().retainedEntries,1);assert.equal(cache.stats().retainedPixels,16);assert.equal(cache.stats().evictions,1);assert.equal(first.image,images[0]);assert.equal(images[0].cancelled,0);
  const another=setup(),fresh=another.cache.loader(new LoadingManager()).loadAsync('https://gateway.invalid/b.png');assert.equal(another.images.length,1);another.images[0].loaded();await fresh;another.controller.abort();controller.abort();
});
test('Bounded image concurrency promotes actual queued work and deadline frees the slot',async()=>{
  const {cache,images,controller}=setup({maximumActive:1,deadlineMs:15}),a=new LoadingManager(),b=new LoadingManager();
  const first=cache.loader(a).loadAsync('https://gateway.invalid/stalled.png'),second=cache.loader(b).loadAsync('https://gateway.invalid/next.png');
  const settled=Promise.allSettled([first,second]);assert.equal(cache.stats().peakActive,1);await settled;assert.equal(cache.stats().active,0);assert.equal(cache.stats().pending,0);assert.equal(cache.stats().failed,2);controller.abort();
});
test('Failed and oversized images report manager errors and are not retained as successful cache entries',async()=>{
  const {cache,images,controller}=setup(),manager=new LoadingManager();let errors=0;manager.onError=()=>errors++;
  const failed=cache.loader(manager).loadAsync('https://gateway.invalid/bad.png');images[0].failed();await assert.rejects(failed,/could not be loaded/);await turn();assert.equal(errors,1);
  const oversized=cache.loader(manager).loadAsync('https://gateway.invalid/huge.png');images[1].naturalWidth=65536;images[1].naturalHeight=65536;images[1].loaded();await assert.rejects(oversized,/megapixel/);await turn();assert.equal(errors,2);assert.equal(cache.stats().retainedEntries,0);controller.abort();
});
test('A throwing loader callback is reported and cannot orphan manager accounting or a shared consumer',async()=>{
  const {cache,images,controller}=setup(),manager=new LoadingManager(),neighbor=new LoadingManager();let error:unknown,completed=0;
  manager.onLoad=()=>completed++;manager.onError=()=>{throw Error('A failing manager observer');};
  cache.loader(manager).load('https://gateway.invalid/callback.png',()=>{throw Error('Malformed texture consumer');},undefined,value=>{error=value;});
  const other=cache.loader(neighbor).loadAsync('https://gateway.invalid/callback.png');images[0].loaded();const texture=await other;await turn();
  assert.match(String(error),/Malformed texture consumer/);assert.equal(completed,1);assert.equal(texture.image,images[0]);assert.equal(cache.stats().completed,1);controller.abort();
});
test('Synchronous image startup errors free the request slot and allow a real subsequent image',async()=>{
  const controller=new AbortController(),images:FakeImage[]=[];let created=0;
  class ThrowingImage extends FakeImage {override set src(_value:string){throw Error('Image request refused');}}
  const cache=new WorldImageCache({signal:controller.signal,maximumActive:1,createImage:()=>{
    const image=created++===0?new ThrowingImage():new FakeImage();images.push(image);return image as unknown as HTMLImageElement;
  }});
  const failed=cache.loader(new LoadingManager()).loadAsync('https://gateway.invalid/refused.png');await assert.rejects(failed,/Image request refused/);
  const success=cache.loader(new LoadingManager()).loadAsync('https://gateway.invalid/next.png');images[1].loaded();await success;
  assert.equal(cache.stats().peakActive,1);assert.equal(cache.stats().pending,0);controller.abort();
});
test('Large embedded URL keys cannot accumulate unbounded decoded-cache memory despite one-pixel images',async()=>{
  const {cache,images,controller}=setup({maximumKeyBytes:80,maximumPendingKeyBytes:400}),url='data:image/png;base64,'+'a'.repeat(100);
  const pending=cache.loader(new LoadingManager()).loadAsync(url);images[0].naturalWidth=1;images[0].naturalHeight=1;images[0].loaded();const texture=await pending;
  assert.equal(texture.image,images[0]);assert.equal(cache.stats().retainedEntries,0);assert.equal(cache.stats().retainedKeyBytes,0);assert.equal(cache.stats().pendingKeyBytes,0);assert.equal(images[0].cancelled,0);
  const rejected=cache.loader(new LoadingManager()).loadAsync('data:image/png;base64,'+'b'.repeat(200));await assert.rejects(rejected,/bounded memory budget/);assert.equal(images.length,1);controller.abort();
});

test('source-kind counters expose bounded aggregates without retaining data URLs or blob identities',async()=>{
 const {cache,images,controller}=setup(),loader=cache.loader(new LoadingManager());
 const secret='data:image/png;base64,private-fixture-not-for-output',blob='blob:https://gateway.invalid/private-token';
 const pending=[loader.loadAsync(secret),loader.loadAsync(secret),loader.loadAsync(blob)];
 for(const image of images)image.loaded();const textures=await Promise.all(pending);
 const kinds=cache.stats().sourceKinds;assert.deepEqual(kinds.data,{requests:2,uniqueImages:1,cacheHits:1,completed:1,failed:0,cancelled:0,evictions:0});
 assert.equal(kinds.blob.requests,1);assert.equal(kinds.blob.uniqueImages,1);assert.equal(Object.keys(kinds).length,5);
 assert(!JSON.stringify(cache.stats()).includes(secret));assert(!JSON.stringify(cache.stats()).includes('private-token'));
 kinds.data.requests=999;assert.equal(cache.stats().sourceKinds.data.requests,2,'Caller snapshots cannot mutate live counters');
 for(const texture of textures)texture.dispose();controller.abort();
});
