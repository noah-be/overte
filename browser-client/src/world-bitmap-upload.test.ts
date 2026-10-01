// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {Texture,RepeatWrapping,SRGBColorSpace,LinearSRGBColorSpace,NoColorSpace} from 'three';
import {WorldBitmapUpload,SessionUploadTexture,isOwnedUploadBitmap,BitmapUploadCapacityError,BitmapUploadUnsupportedVariantError} from './world-bitmap-upload';
const image=(width=2,height=2)=>({naturalWidth:width,naturalHeight:height}) as HTMLImageElement;
function bitmap(width=2,height=2){let closes=0;return{image:{width,height,close(){closes++;}} as ImageBitmap,closes:()=>closes};}
function deferred<T>(){let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};}
const micro=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();};
function setup(options:Partial<ConstructorParameters<typeof WorldBitmapUpload>[0]>={}){const world=new AbortController(),jobs:Array<{image:HTMLImageElement;options:ImageBitmapOptions;task:ReturnType<typeof deferred<ImageBitmap>>}>=[];
 const owner=new WorldBitmapUpload({signal:world.signal,isImage:v=>!!v&&typeof v==='object'&&'naturalWidth'in v,createBitmap:(image,options)=>{const task=deferred<ImageBitmap>();jobs.push({image,options,task});return task.promise;},...options});
 return{world,owner,jobs};}
test('conversion consumes exact existing image once, preserves distinct sampler clones and shared Source version',async()=>{
 const s=setup(),original=new Texture(image());original.name='owned sampler';original.wrapS=RepeatWrapping;original.colorSpace=SRGBColorSpace;original.offset.set(.1,.2);original.repeat.set(2,3);const sourceVersion=original.source.version;
 const a=s.owner.prepare(original,new AbortController().signal),b=s.owner.prepare(original,new AbortController().signal);assert.equal(s.jobs.length,1);assert.equal(s.jobs[0].image,original.image);assert.deepEqual(s.jobs[0].options,{imageOrientation:'flipY',premultiplyAlpha:'none',colorSpaceConversion:'none'});
 const pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const [first,second]=await Promise.all([a,b]);assert(first instanceof SessionUploadTexture);assert.notEqual(first,second);assert.equal(first.source,second.source);assert.equal(first.wrapS,original.wrapS);assert.deepEqual(first.offset.toArray(),[.1,.2]);assert.deepEqual(first.repeat.toArray(),[2,3]);assert.equal(first.name,original.name);assert.equal(original.source.version,sourceVersion);
 const sharedVersion=first.source.version,clone=first.clone();clone.offset.x=.4;assert.notEqual(clone.offset,first.offset);assert.equal(first.offset.x,.1);assert.equal(clone.source,first.source);assert.equal(first.source.version,sharedVersion);assert.equal(s.owner.stats().leases,3);
 s.world.abort();assert.equal(pixels.closes(),0);first.dispose();first.dispose();second.dispose();assert.equal(pixels.closes(),0);clone.dispose();assert.equal(pixels.closes(),1);assert.equal(s.owner.stats().bytes,0);assert.equal(s.owner.stats().leases,0);assert.equal(isOwnedUploadBitmap(pixels.image),true);
});
test('final flip and color variants share only exact compatible image bindings',async()=>{
 const s=setup(),first=new Texture(image()),other=first.clone();other.flipY=false;other.colorSpace=LinearSRGBColorSpace;
 const one=s.owner.prepare(first,new AbortController().signal),two=s.owner.prepare(other,new AbortController().signal);assert.equal(s.jobs.length,2);assert.deepEqual(s.jobs[1].options,{imageOrientation:'from-image',premultiplyAlpha:'none',colorSpaceConversion:'none'});
 const a=bitmap(),b=bitmap();s.jobs[0].task.resolve(a.image);s.jobs[1].task.resolve(b.image);const [x,y]=await Promise.all([one,two]);assert.notEqual(x.source,y.source);assert(s.owner.isCurrent(x));assert(s.owner.isCurrent(y));y.flipY=true;assert(!s.owner.isCurrent(y));s.world.abort();x.dispose();y.dispose();assert.equal(a.closes(),1);assert.equal(b.closes(),1);
});
test('premultiplied variants retain the original upload without a conversion or pixel-budget reservation',async()=>{
 const s=setup(),original=new Texture(image());original.premultiplyAlpha=true;
 await assert.rejects(s.owner.prepare(original,new AbortController().signal),BitmapUploadUnsupportedVariantError);
 assert.equal(s.jobs.length,0);assert.equal(s.owner.stats().bytes,0);assert.equal(s.owner.stats().readers,0);assert.equal(s.owner.stats().liveEntries,0);s.world.abort();
});
test('an actual throwing texture-disposal listener cannot strand its owned bitmap lease',async()=>{
 const s=setup(),pending=s.owner.prepare(new Texture(image()),new AbortController().signal),pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const texture=await pending;
 const failure=Error('Actual dispose listener failed'),listener=()=>{throw failure;};texture.addEventListener('dispose',listener);s.world.abort();
 assert.throws(()=>texture.dispose(),error=>error===failure);assert.equal(s.owner.stats().leases,0);assert.equal(s.owner.stats().bytes,0);assert.equal(pixels.closes(),1);
 texture.removeEventListener('dispose',listener);texture.dispose();assert.equal(pixels.closes(),1);
});
test('one reader cancellation cannot invalidate a shared live consumer or ready Source',async()=>{
 const s=setup(),t=new Texture(image()),a=new AbortController(),b=new AbortController();const one=s.owner.prepare(t,a.signal),two=s.owner.prepare(t,b.signal);a.abort();await assert.rejects(one,{name:'AbortError'});const pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const kept=await two;assert(s.owner.isCurrent(kept));assert.equal(pixels.closes(),0);s.owner.close();kept.dispose();assert.equal(pixels.closes(),1);
});
test('last reader cancels immediately, but unresolved platform conversion keeps reserved capacity until late close',async()=>{
 const s=setup({maximumActive:1,maximumBytes:16}),reader=new AbortController(),pending=s.owner.prepare(new Texture(image()),reader.signal);reader.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(s.owner.stats().active,1);assert.equal(s.owner.stats().bytes,16);await assert.rejects(s.owner.prepare(new Texture(image()),new AbortController().signal),BitmapUploadCapacityError);
 const late=bitmap();s.jobs[0].task.resolve(late.image);await micro();assert.equal(late.closes(),1);assert.equal(s.owner.stats().active,0);assert.equal(s.owner.stats().bytes,0);assert.equal(s.owner.stats().liveEntries,0);
});
test('deadline rejects and never releases a blocked conversion slot for unbounded orphan work',async()=>{
 const s=setup({maximumActive:1,deadlineMs:10}),pending=s.owner.prepare(new Texture(image()),new AbortController().signal);await assert.rejects(pending,/deadline/);assert.equal(s.owner.stats().active,1);const later=s.owner.prepare(new Texture(image()),new AbortController().signal);const observed=assert.rejects(later,/deadline/);assert.equal(s.jobs.length,1);await observed;const pixels=bitmap();s.jobs[0].task.resolve(pixels.image);await micro();assert.equal(pixels.closes(),1);assert.equal(s.jobs.length,1);assert.equal(s.owner.stats().bytes,0);
});
test('world revoke rejects queued/active work and cannot publish late pixels or create more conversions',async()=>{
 const s=setup({maximumActive:1}),reader=new AbortController(),one=s.owner.prepare(new Texture(image()),reader.signal),two=s.owner.prepare(new Texture(image()),reader.signal);s.world.abort();await Promise.all([assert.rejects(one,{name:'AbortError'}),assert.rejects(two,{name:'AbortError'})]);assert.equal(s.jobs.length,1);const late=bitmap();s.jobs[0].task.resolve(late.image);await micro();assert.equal(late.closes(),1);assert.equal(s.owner.stats().active,0);assert.equal(s.owner.stats().bytes,0);await assert.rejects(s.owner.prepare(new Texture(image()),reader.signal),{name:'AbortError'});
});
test('ready cache eviction cannot close another live clone or evade total pixel bounds',async()=>{
 const s=setup({maximumEntries:1,maximumBytes:32}),a=s.owner.prepare(new Texture(image()),new AbortController().signal),firstPixels=bitmap();s.jobs[0].task.resolve(firstPixels.image);const first=await a,clone=first.clone();const b=s.owner.prepare(new Texture(image()),new AbortController().signal),secondPixels=bitmap();s.jobs[1].task.resolve(secondPixels.image);const second=await b;assert.equal(s.owner.stats().retainedEntries,1);assert.equal(s.owner.stats().bytes,32);assert.equal(firstPixels.closes(),0);first.dispose();assert.equal(firstPixels.closes(),0);clone.dispose();assert.equal(firstPixels.closes(),1);assert.equal(s.owner.stats().bytes,16);s.world.abort();second.dispose();assert.equal(secondPixels.closes(),1);
});
for(const change of ['source','version','flip','premultiply','color'])test('late binding change refuses publication: '+change,async()=>{
 const s=setup(),original=new Texture(image()),pending=s.owner.prepare(original,new AbortController().signal);
 if(change==='source')original.source=new Texture(image()).source;if(change==='version')original.needsUpdate=true;if(change==='flip')original.flipY=false;if(change==='premultiply')original.premultiplyAlpha=true;if(change==='color')original.colorSpace=SRGBColorSpace;
 const pixels=bitmap();s.jobs[0].task.resolve(pixels.image);await assert.rejects(pending,/binding changed/);s.world.abort();assert.equal(pixels.closes(),1);assert.equal(s.owner.stats().leases,0);
});
test('copying a managed clone releases its previous lease and copying after world revoke refuses',async()=>{
 const s=setup(),a=s.owner.prepare(new Texture(image()),new AbortController().signal),pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const first=await a,clone=first.clone();assert.equal(s.owner.stats().leases,2);clone.copy(first);assert.equal(s.owner.stats().leases,2);s.world.abort();assert.throws(()=>first.clone(),{name:'AbortError'});clone.dispose();first.dispose();assert.equal(pixels.closes(),1);
});
test('sync conversion failure, async rejection and wrong dimensions release all reservation exactly once',async()=>{
 for(const kind of ['sync','async','dimensions']){
  const pixels=bitmap(1,1),s=setup({createBitmap:()=>{if(kind==='sync')throw Error('conversion failed');if(kind==='async')return Promise.reject(Error('conversion failed'));return Promise.resolve(pixels.image);}});
  await assert.rejects(s.owner.prepare(new Texture(image()),new AbortController().signal),kind==='dimensions'?/dimensions/:/conversion failed/);assert.equal(s.owner.stats().active,0);assert.equal(s.owner.stats().bytes,0);assert.equal(s.owner.stats().pending,0);assert.equal(pixels.closes(),kind==='dimensions'?1:0);s.world.abort();
 }
});
test('late conversion rejection after reader abort releases its still-owned reservation',async()=>{
 const s=setup(),reader=new AbortController(),p=s.owner.prepare(new Texture(image()),reader.signal);reader.abort();await assert.rejects(p,{name:'AbortError'});s.jobs[0].task.reject(Error('platform stopped'));await micro();assert.equal(s.owner.stats().active,0);assert.equal(s.owner.stats().bytes,0);
});
test('unsupported compressed/render-target/color variants and oversized pixels fail before any conversion',async()=>{
 const s=setup();for(const t of [new Texture({} as HTMLImageElement),new Texture(image(8193,8193))])await assert.rejects(s.owner.prepare(t,new AbortController().signal));const t=new Texture(image());t.colorSpace='display-p3';await assert.rejects(s.owner.prepare(t,new AbortController().signal),/not supported/);t.colorSpace=NoColorSpace;t.isRenderTargetTexture=true;await assert.rejects(s.owner.prepare(t,new AbortController().signal),/not supported/);assert.equal(s.jobs.length,0);assert.equal(s.owner.stats().bytes,0);s.world.abort();
});

test('disposed sampler and unmanaged raw copies cannot satisfy current owned publication',async()=>{
 const s=setup(),p=s.owner.prepare(new Texture(image()),new AbortController().signal),pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const first=await p,unowned=new Texture().copy(first);assert(!s.owner.isCurrent(unowned));first.dispose();assert(!s.owner.isCurrent(first));s.world.abort();assert.throws(()=>first.clone(),{name:'AbortError'});assert.equal(pixels.closes(),1);unowned.dispose();
});
test('throwing platform close cannot orphan settled slots or retained accounting',async()=>{
 const s=setup(),reader=new AbortController(),p=s.owner.prepare(new Texture(image()),reader.signal);reader.abort();await assert.rejects(p,{name:'AbortError'});s.jobs[0].task.resolve({width:2,height:2,close(){throw Error('close failed');}} as ImageBitmap);await micro();assert.equal(s.owner.stats().active,0);assert.equal(s.owner.stats().bytes,0);assert.equal(s.owner.stats().closeFailures,1);
});

test('a repeatedly shared pending Source cannot retain unbounded reader continuations',async()=>{
 const s=setup({maximumReaders:2}),texture=new Texture(image()),a=new AbortController(),b=new AbortController(),one=s.owner.prepare(texture,a.signal),two=s.owner.prepare(texture,b.signal);
 assert.equal(s.owner.stats().readers,2);await assert.rejects(s.owner.prepare(texture,new AbortController().signal),BitmapUploadCapacityError);assert.equal(s.jobs.length,1);a.abort();await assert.rejects(one,{name:'AbortError'});assert.equal(s.owner.stats().readers,1);
 const third=s.owner.prepare(texture,new AbortController().signal);assert.equal(s.owner.stats().readers,2);const pixels=bitmap();s.jobs[0].task.resolve(pixels.image);const [first,second]=await Promise.all([two,third]);assert.equal(s.owner.stats().readers,0);s.world.abort();first.dispose();second.dispose();assert.equal(pixels.closes(),1);
});
