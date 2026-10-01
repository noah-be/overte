// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Optional color-texture path; the application must supply its current session authority.
import * as THREE from 'three';
import {inspectNativeKtx, type NativeKtx} from '../shared/native-ktx.mjs';
import type {NativeTextureAlpha} from './texture-alpha';

export class UnsupportedNativeCompression extends Error {}
export interface CompressionCapabilities {s3tc: boolean; s3tcSRGB: boolean; maximumTextureSize: number}
export interface CompressedColorOptions {
 origin: string; sessionId: string; authority(): string|null; resolveAsset(url: string): string;
 capabilities: CompressionCapabilities; fetch?: typeof fetch;
 maximumAssetBytes?: number; maximumCacheBytes?: number; maximumCacheEntries?: number;
 maximumActive?: number; maximumQueued?: number; maximumReaders?: number; deadlineMs?: number;
}
export interface CompressedColorSampler {
 flipY?: boolean; wrapS?: THREE.Wrapping; wrapT?: THREE.Wrapping;
 repeat?: readonly [number,number]; offset?: readonly [number,number]; center?: readonly [number,number]; rotation?: number;
 anisotropy?: number; magFilter?: THREE.MagnificationTextureFilter; minFilter?: THREE.MinificationTextureFilter;
}
interface Entry {parsed: NativeKtx; bytes: number; source: THREE.CompressedTexture['source']}
interface Reader {finish(error?: unknown, entry?: Entry): void}
interface Job {key: string; address: string; authority: string; readers: Set<Reader>; controller: AbortController; timer: ReturnType<typeof setTimeout>; started: boolean; expired: boolean}
const owned = new WeakMap<THREE.Texture,{source: THREE.Texture['source']; mipmaps: THREE.CompressedTexture['mipmaps']; classification: NativeTextureAlpha;originalSize?:{width:number;height:number}}>();
function cancelled() {return new DOMException('Compressed color load cancelled','AbortError');}
function requireInteger(value: number, maximum: number) {if (!Number.isSafeInteger(value)||value<1||value>maximum) throw Error('Invalid compressed color resource limit');return value;}
/** No userData flag or caller-supplied metadata can establish this ownership. */
export function nativeCompressedColorAlpha(texture: THREE.Texture): NativeTextureAlpha|undefined {
 const entry=owned.get(texture);
 return entry&&texture.source===entry.source&&(texture as THREE.CompressedTexture).mipmaps===entry.mipmaps?entry.classification:undefined;
}
/** Native GPUKTX v2 original dimensions; only exact privately owned Sources qualify. */
export function nativeCompressedImageOriginalSize(texture:THREE.Texture):{width:number;height:number}|undefined {
 const entry=owned.get(texture),size=entry?.originalSize;
 return entry&&texture.source===entry.source&&(texture as THREE.CompressedTexture).mipmaps===entry.mipmaps&&size&&Number.isSafeInteger(size.width)&&Number.isSafeInteger(size.height)&&size.width>0&&size.height>0?{...size}:undefined;
}
/** Prototype material eligibility: authored modes win, then approved albedo usage. Unowned textures still require the original-image path. */
export function nativeCompressedColorMaterialAlpha(texture: THREE.Texture, options: {useAlpha: boolean; mode?: 'OPACITY_MAP_OPAQUE'|'OPACITY_MAP_MASK'|'OPACITY_MAP_BLEND'}): NativeTextureAlpha|undefined {
 const classification=nativeCompressedColorAlpha(texture);if(classification===undefined)return undefined;
 if(options.mode==='OPACITY_MAP_MASK')return 'mask';if(options.mode==='OPACITY_MAP_BLEND')return 'blend';
 return options.mode==='OPACITY_MAP_OPAQUE'||!options.useAlpha?'opaque':classification;
}
/** Compose an upload flip after the authored UV transform. Compressed blocks cannot use UNPACK_FLIP_Y_WEBGL. */
export function setCompressedColorFlipY(texture: THREE.CompressedTexture, flipY: boolean) {
 if (!owned.has(texture)) throw Error('UV compensation requires an owned compressed color texture');
 texture.updateMatrix();
 if (flipY) texture.matrix.premultiply(new THREE.Matrix3().set(1,0,0,0,-1,1,0,0,1));
 texture.matrixAutoUpdate=false;texture.flipY=false;
}
/** Authority-scoped CPU byte cache. Live model-owned textures remain outside the retained cache budget. */
export class NativeCompressedColorCache {
 private readonly options: CompressedColorOptions;
 private readonly limits: {asset: number; bytes: number; entries: number; active: number; queued: number; readers: number; deadline: number};
 private cache=new Map<string,Entry>();private jobs=new Map<string,Job>();private queue: Job[]=[];
 private retainedBytes=0;private active=0;private readers=0;private closed=false;
 constructor(options: CompressedColorOptions) {
  const origin=new URL(options.origin);if(origin.origin!==options.origin||!/^https?:$/.test(origin.protocol))throw Error('Compressed color origin must be an exact HTTP origin');
  if(!/^[a-zA-Z0-9_-]{1,128}$/.test(options.sessionId))throw Error('Invalid compressed color session scope');
  const caps=options.capabilities;if(typeof caps.s3tc!=='boolean'||typeof caps.s3tcSRGB!=='boolean'||!Number.isSafeInteger(caps.maximumTextureSize)||caps.maximumTextureSize<1)throw Error('Invalid compressed color GPU capabilities');
  this.options=options;
  this.limits={asset:requireInteger(options.maximumAssetBytes??32*1024*1024,32*1024*1024),bytes:requireInteger(options.maximumCacheBytes??64*1024*1024,128*1024*1024),entries:requireInteger(options.maximumCacheEntries??128,256),active:requireInteger(options.maximumActive??2,2),queued:requireInteger(options.maximumQueued??128,128),readers:requireInteger(options.maximumReaders??512,512),deadline:requireInteger(options.deadlineMs??30000,30000)};
 }
 get statistics(){return {retainedBytes:this.retainedBytes,retainedEntries:this.cache.size,active:this.active,queued:this.queue.length,readers:this.readers};}
 /** A metadata/original fallback must retain the approval that began its lookup. */
 captureApproval():()=>void {
  const authority=this.currentAuthority();if(this.closed||!authority)throw Error('Compressed color authority was revoked');
  return ()=>{if(!this.authorized(authority))throw Error('Compressed color authority was revoked');};
 }
 private currentAuthority(){
  const value=this.options.authority();if(value===null)return null;
  if(typeof value!=='string'||!value.length||value.length>4096||new TextEncoder().encode(value).length>4096)throw Error('Compressed color authority must be a bounded nonempty scope token');
  return value;
 }
 private authorized(authority: string){return !this.closed&&this.currentAuthority()===authority;}
 private address(original: string) {
  if(typeof original!=='string'||original.length<1||original.length>4096)throw Error('Compressed color asset URL exceeds its bound');
  const address=new URL(this.options.resolveAsset(original),this.options.origin);
  if(address.href.length>16384)throw Error('Compressed color gateway URL exceeds its bound');
  if(address.origin!==this.options.origin||address.username||address.password||address.hash||address.pathname!==`/api/assets/${this.options.sessionId}`||address.searchParams.size!==1||address.searchParams.get('url')!==original)throw Error('Compressed color asset escaped its owned gateway session');
  return address.href;
 }
 load(original: string, options: {signal?: AbortSignal; sampler?: CompressedColorSampler}={}): Promise<THREE.CompressedTexture> {
  if(options.signal?.aborted||this.closed)return Promise.reject(cancelled());
  let authority: string|null,address: string;try{authority=this.currentAuthority();if(!authority)throw Error('Compressed color requires an approved authority');address=this.address(original);}catch(error){return Promise.reject(error);}
  if(this.readers>=this.limits.readers)return Promise.reject(Error('Too many compressed color readers'));
  const key=JSON.stringify([authority,address]);let entry=this.cache.get(key);
  if(entry){this.readers++;this.cache.delete(key);this.cache.set(key,entry);return Promise.resolve().then(()=>{
   if(options.signal?.aborted)throw cancelled();if(!this.authorized(authority))throw Error('Compressed color authority changed');return this.texture(entry!,options.sampler);
  }).finally(()=>{this.readers--;});}
  let job=this.jobs.get(key);
  if(job&&(job.expired||job.controller.signal.aborted))return Promise.reject(cancelled());
  if(!job){
   if(this.active>=this.limits.active&&this.queue.length>=this.limits.queued)return Promise.reject(Error('Too many queued compressed color loads'));
   job={key,address,authority,readers:new Set(),controller:new AbortController(),started:false,expired:false,timer:setTimeout(()=>{},0)};clearTimeout(job.timer);
   const current=job;job.timer=setTimeout(()=>{current.expired=true;current.controller.abort();this.finish(current,Error('Compressed color load exceeded its deadline'));if(!current.started)this.remove(current);},this.limits.deadline);
   this.jobs.set(key,job);this.queue.push(job);
  }
  const current=job;this.readers++;
  const result=new Promise<THREE.CompressedTexture>((resolve,reject)=>{
   let finished=false;
   const abort=()=>reader.finish(cancelled());
   const reader: Reader={finish:(error,loaded)=>{
    if(finished)return;finished=true;options.signal?.removeEventListener('abort',abort);current.readers.delete(reader);this.readers--;
    if(error)reject(error);else try{if(!this.authorized(authority))throw Error('Compressed color authority changed');if(options.signal?.aborted)throw cancelled();resolve(this.texture(loaded!,options.sampler));}catch(reason){reject(reason);}
    if(!current.readers.size&&!loaded){current.controller.abort();if(!current.started)this.remove(current);}
   }};
   current.readers.add(reader);options.signal?.addEventListener('abort',abort,{once:true});
  });
  this.pump();return result;
 }
 private texture(entry: Entry, sampler: CompressedColorSampler={}) {
  for(const pair of [sampler.repeat,sampler.offset,sampler.center])if(pair&&(!Array.isArray(pair)||pair.length!==2||!pair.every(value=>Number.isFinite(value)&&Math.abs(value)<=1e6)))throw Error('Invalid compressed color UV transform');
  if(sampler.rotation!==undefined&&(!Number.isFinite(sampler.rotation)||Math.abs(sampler.rotation)>1e6))throw Error('Invalid compressed color UV rotation');
  if(sampler.anisotropy!==undefined&&(!Number.isFinite(sampler.anisotropy)||sampler.anisotropy<1||sampler.anisotropy>16))throw Error('Invalid compressed color anisotropy');
  const parsed=entry.parsed,texture=new THREE.CompressedTexture(parsed.mipmaps.map(m=>({data:m.data,width:m.width,height:m.height})),parsed.width,parsed.height,parsed.format.threeFormat as THREE.CompressedPixelFormat);
  texture.colorSpace=THREE.SRGBColorSpace;texture.generateMipmaps=false;
  texture.minFilter=parsed.completeMipChain?THREE.LinearMipmapLinearFilter:THREE.LinearFilter;
  texture.wrapS=sampler.wrapS??THREE.RepeatWrapping;texture.wrapT=sampler.wrapT??THREE.RepeatWrapping;
  if(sampler.repeat)texture.repeat.fromArray(sampler.repeat);if(sampler.offset)texture.offset.fromArray(sampler.offset);if(sampler.center)texture.center.fromArray(sampler.center);
  texture.rotation=sampler.rotation??0;texture.anisotropy=sampler.anisotropy??1;
  if(sampler.magFilter!==undefined)texture.magFilter=sampler.magFilter;
  if(sampler.minFilter!==undefined)texture.minFilter=sampler.minFilter;
  // Mark only this new Texture's initial source; a ready shared source must not force another GPU upload.
  texture.needsUpdate=true;texture.source=entry.source;
  owned.set(texture,{source:texture.source,mipmaps:texture.mipmaps,classification:parsed.nativeUsage.classification,originalSize:parsed.nativeUsage.originalSize});
  // Native source packets omit orientation and retain original Qt image row order. Explicit T=u reverses it.
  setCompressedColorFlipY(texture,(sampler.flipY??true)!==(parsed.orientation==='S=r,T=u'));
  texture.addEventListener('dispose',()=>owned.delete(texture));return texture;
 }
 private finish(job: Job,error?: unknown,entry?: Entry){for(const reader of [...job.readers])reader.finish(error,entry);}
 private remove(job: Job){clearTimeout(job.timer);if(this.jobs.get(job.key)===job)this.jobs.delete(job.key);this.queue=this.queue.filter(candidate=>candidate!==job);}
 private pump(){while(!this.closed&&this.active<this.limits.active&&this.queue.length){const job=this.queue.shift()!;if(!job.readers.size||job.expired){this.remove(job);continue;}job.started=true;this.active++;void this.download(job).then(entry=>{
   if(job.controller.signal.aborted||!this.authorized(job.authority)||!job.readers.size)throw cancelled();
   if(entry.bytes<=this.limits.bytes){this.cache.set(job.key,entry);this.retainedBytes+=entry.bytes;while(this.retainedBytes>this.limits.bytes||this.cache.size>this.limits.entries){const oldest=this.cache.keys().next().value!;this.retainedBytes-=this.cache.get(oldest)!.bytes;this.cache.delete(oldest);}}
   this.finish(job,undefined,entry);
  }).catch(error=>this.finish(job,error)).finally(()=>{this.active--;this.remove(job);this.pump();});}}
 private async download(job: Job): Promise<Entry> {
  if(!this.authorized(job.authority))throw Error('Compressed color authority changed');
  const response=await (this.options.fetch??fetch)(job.address,{credentials:'same-origin',redirect:'error',signal:job.controller.signal});
  if(!response.ok||!response.body){await response.body?.cancel();throw Error('Compressed color asset request failed');}
  const declared=response.headers.get('content-length');if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>this.limits.asset)){await response.body.cancel();throw Error('Compressed color asset exceeds its byte bound');}
  const reader=response.body.getReader(),chunks: Uint8Array[]=[];let count=0;
  try{while(true){const next=await reader.read();if(job.controller.signal.aborted||!this.authorized(job.authority))throw cancelled();if(next.done)break;count+=next.value.byteLength;if(count>this.limits.asset)throw Error('Compressed color asset exceeds its byte bound');chunks.push(next.value);}}
  catch(error){await reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
  const data=new Uint8Array(count);let at=0;for(const chunk of chunks){data.set(chunk,at);at+=chunk.length;}
  const parsed=inspectNativeKtx(data),caps=this.options.capabilities;
  if(!parsed.nativeUsage.color||parsed.nativeUsage.normal||!parsed.format.srgb)throw new UnsupportedNativeCompression('Only audited sRGB native color compression is supported');
  if(!caps.s3tc||!caps.s3tcSRGB||parsed.width>caps.maximumTextureSize||parsed.height>caps.maximumTextureSize)throw new UnsupportedNativeCompression('Native color compression is unsupported by this GPU');
  const source=new THREE.TextureSource({width:parsed.width,height:parsed.height});source.needsUpdate=true;
  return {parsed,bytes:data.byteLength,source};
 }
 dispose(){if(this.closed)return;this.closed=true;this.cache.clear();this.retainedBytes=0;for(const job of this.jobs.values()){job.controller.abort();this.finish(job,cancelled());if(!job.started)this.remove(job);}this.queue=[];}
}
