// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Session-local decoded images; never enable Three's global asset Cache.
import * as THREE from 'three';
import {LoadingManager,type Source,Texture,TextureLoader} from 'three';
// Three 0.186.1 renamed Source; 0.186.0 typings still use its compatible type.
const TextureSource=(THREE as unknown as {TextureSource:new(data:HTMLImageElement)=>Source<HTMLImageElement>}).TextureSource;
type ImageSourceKind='http'|'https'|'data'|'blob'|'other';
interface SourceCounters {requests:number;uniqueImages:number;cacheHits:number;completed:number;failed:number;cancelled:number;evictions:number}
function sourceKind(key:string):ImageSourceKind{const scheme=/^([a-z]+):/i.exec(key)?.[1]?.toLowerCase();return scheme==='http'||scheme==='https'||scheme==='data'||scheme==='blob'?scheme:'other';}
function sourceCounters():SourceCounters{return {requests:0,uniqueImages:0,cacheHits:0,completed:0,failed:0,cancelled:0,evictions:0};}
interface ImageRecord {
  key:string;kind:ImageSourceKind;image:HTMLImageElement;source:Source<HTMLImageElement>;promise:Promise<ImageRecord>;resolve:(value:ImageRecord)=>void;reject:(error:unknown)=>void;
  status:'queued'|'active'|'ready'|'failed';consumers:number;pixels:number;keyBytes:number;timer?:ReturnType<typeof setTimeout>;stop?:()=>void;
}
interface Phase {count:number;totalMs:number;maxMs:number}
export interface WorldImageCacheOptions {
  signal:AbortSignal;maximumActive?:number;maximumPending?:number;maximumEntries?:number;maximumPixels?:number;maximumKeyBytes?:number;maximumPendingKeyBytes?:number;deadlineMs?:number;
  createImage?:()=>HTMLImageElement;
}
const abortError=()=>new DOMException('Session texture loading was cancelled','AbortError');
/** Images are shared; each material still owns its Texture and sampler/color-space.
 * HTMLImageElement has no bitmap.close(), so disposing a texture/model cannot
 * invalidate another model's image. Ready cache eviction drops only our lease.
 */
export class WorldImageCache {
  private readonly records=new Map<string,ImageRecord>();private readonly queue:ImageRecord[]=[];private active=0;private pending=0;private pixels=0;private keyBytes=0;private pendingKeyBytes=0;private closed=false;
  private readonly kinds:Record<ImageSourceKind,SourceCounters>={http:sourceCounters(),https:sourceCounters(),data:sourceCounters(),blob:sourceCounters(),other:sourceCounters()};
  private readonly counters={requests:0,uniqueImages:0,cacheHits:0,completed:0,failed:0,cancelled:0,evictions:0,peakActive:0};
  private readonly phases={imageLoad:{count:0,totalMs:0,maxMs:0} as Phase,imageDecode:{count:0,totalMs:0,maxMs:0} as Phase};
  private readonly maximumActive:number;private readonly maximumPending:number;private readonly maximumEntries:number;private readonly maximumPixels:number;private readonly maximumKeyBytes:number;private readonly maximumPendingKeyBytes:number;private readonly deadlineMs:number;
  constructor(private options:WorldImageCacheOptions){
    this.maximumActive=options.maximumActive??6;this.maximumPending=options.maximumPending??1024;this.maximumEntries=options.maximumEntries??512;this.maximumPixels=options.maximumPixels??128*1024*1024;this.maximumKeyBytes=options.maximumKeyBytes??8*1024*1024;this.maximumPendingKeyBytes=options.maximumPendingKeyBytes??256*1024*1024;this.deadlineMs=options.deadlineMs??30000;
    for(const value of [this.maximumActive,this.maximumPending,this.maximumEntries,this.maximumPixels,this.maximumKeyBytes,this.maximumPendingKeyBytes,this.deadlineMs])if(!Number.isSafeInteger(value)||value<1)throw Error('Invalid world image cache resource limit.');
    options.signal.addEventListener('abort',this.close,{once:true});if(options.signal.aborted)this.close();
  }
  stats(){return {...this.counters,sourceKinds:Object.fromEntries(Object.entries(this.kinds).map(([kind,value])=>[kind,{...value}])),active:this.active,queued:this.queue.length,pending:this.pending,retainedEntries:[...this.records.values()].filter(record=>record.status==='ready').length,retainedPixels:this.pixels,retainedKeyBytes:this.keyBytes,pendingKeyBytes:this.pendingKeyBytes,phases:{imageLoad:{...this.phases.imageLoad},imageDecode:{...this.phases.imageDecode}}};}
  loader(manager:LoadingManager):TextureLoader{return new ScopedTextureLoader(this,manager);}
  /** Snapshot one manager's cancellation authority; other managers keep their image. */
  acquire(key:string,signal:AbortSignal,crossOrigin:string):{source:Source<HTMLImageElement>;ready:Promise<ImageRecord>}{
    this.counters.requests++;const kind=sourceKind(key);this.kinds[kind].requests++;
    if(this.closed||signal.aborted)throw abortError();
    let entry=this.records.get(key);
    if(entry){this.counters.cacheHits++;this.kinds[kind].cacheHits++;this.records.delete(key);this.records.set(key,entry);}
    else{
      if(this.pending>=this.maximumPending)throw Error('Too many pending session texture images.');
      // JS string storage is at most two bytes per UTF-16 code unit. Embedded
      // data: images can have huge keys despite tiny decoded pixel dimensions.
      const keyBytes=key.length*2;
      if(keyBytes+this.pendingKeyBytes>this.maximumPendingKeyBytes)throw Error('Pending session texture URLs exceed their bounded memory budget.');
      let resolve!:(value:ImageRecord)=>void,reject!:(error:unknown)=>void;
      const promise=new Promise<ImageRecord>((yes,no)=>{resolve=yes;reject=no;});
      const image=this.options.createImage?.()??document.createElement('img');
      image.crossOrigin=crossOrigin;const record:ImageRecord={key,kind,image,source:new TextureSource(null as unknown as HTMLImageElement),promise,resolve,reject,status:'queued',consumers:0,pixels:0,keyBytes};
      entry=record;this.records.set(key,record);this.queue.push(record);this.pending++;this.pendingKeyBytes+=record.keyBytes;this.counters.uniqueImages++;this.kinds[kind].uniqueImages++;
      record.timer=setTimeout(()=>this.fail(record,Error('Session texture image exceeded its 30-second loading deadline.')),this.deadlineMs);
    }
    const current=entry;current.consumers++;
    let onAbort!:()=>void;
    const ready=new Promise<ImageRecord>((resolve,reject)=>{
      onAbort=()=>reject(abortError());signal.addEventListener('abort',onAbort,{once:true});current.promise.then(resolve,reject);
    }).finally(()=>{
      signal.removeEventListener('abort',onAbort);current.consumers--;
      if(!current.consumers&&(current.status==='queued'||current.status==='active'))this.fail(current,abortError());
    });
    this.pump();return {source:current.source,ready};
  }
  private phase(name:keyof WorldImageCache['phases'],started:number){const elapsed=performance.now()-started,phase=this.phases[name];phase.count++;phase.totalMs+=elapsed;phase.maxMs=Math.max(phase.maxMs,elapsed);}
  private pump(){
    while(!this.closed&&this.active<this.maximumActive&&this.queue.length){
      const record=this.queue.shift()!;if(record.status!=='queued')continue;
      record.status='active';this.active++;this.counters.peakActive=Math.max(this.counters.peakActive,this.active);
      const started=performance.now();
      const loaded=async()=>{
        if(record.status!=='active')return;this.phase('imageLoad',started);const decoding=performance.now();
        try{
          if(typeof record.image.decode==='function')await record.image.decode();
          if(record.status!=='active')return;this.phase('imageDecode',decoding);
          const {naturalWidth:width,naturalHeight:height}=record.image;
          if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<=0||height<=0||width*height>64*1024*1024)throw Error('Decoded session texture exceeds its 64-megapixel image limit.');
          record.stop?.();clearTimeout(record.timer);record.status='ready';this.active--;this.pending--;this.pendingKeyBytes-=record.keyBytes;record.pixels=width*height;this.pixels+=record.pixels;this.keyBytes+=record.keyBytes;
          record.source.data=record.image;record.source.needsUpdate=true;this.counters.completed++;this.kinds[record.kind].completed++;record.resolve(record);this.trim();this.pump();
        }catch(error){this.fail(record,error);}
      };
      const failed=()=>this.fail(record,Error('A session texture image could not be loaded.'));
      record.image.addEventListener('load',loaded);record.image.addEventListener('error',failed);
      record.stop=()=>{record.image.removeEventListener('load',loaded);record.image.removeEventListener('error',failed);};
      try { record.image.src=record.key; } catch(error) { this.fail(record,error); }
    }
  }
  private fail(record:ImageRecord,error:unknown){
    if(record.status==='ready'||record.status==='failed')return;
    const active=record.status==='active';record.status='failed';record.stop?.();clearTimeout(record.timer);if(active)this.active--;this.pending--;this.pendingKeyBytes-=record.keyBytes;
    const queued=this.queue.indexOf(record);if(queued>=0)this.queue.splice(queued,1);
    if(this.records.get(record.key)===record)this.records.delete(record.key);
    // Removing src cancels an owned pending Image request; assigning empty src
    // could instead start another request for the current document.
    record.image.removeAttribute('src');
    if(error instanceof DOMException&&error.name==='AbortError'){this.counters.cancelled++;this.kinds[record.kind].cancelled++;}else{this.counters.failed++;this.kinds[record.kind].failed++;}
    record.reject(error);this.pump();
  }
  private trim(){
    // An individually oversized embedded key/image cannot evict the useful
    // working set merely to be evicted itself at the end of the LRU scan.
    for(const [key,record]of this.records)if(record.status==='ready'&&(record.keyBytes>this.maximumKeyBytes||record.pixels>this.maximumPixels)){
      this.records.delete(key);this.pixels-=record.pixels;this.keyBytes-=record.keyBytes;this.counters.evictions++;this.kinds[record.kind].evictions++;
    }
    let retained=0;for(const value of this.records.values())if(value.status==='ready')retained++;
    for(const [key,record] of this.records){if(retained<=this.maximumEntries&&this.pixels<=this.maximumPixels&&this.keyBytes<=this.maximumKeyBytes)break;if(record.status!=='ready')continue;
      this.records.delete(key);this.pixels-=record.pixels;this.keyBytes-=record.keyBytes;retained--;this.counters.evictions++;this.kinds[record.kind].evictions++;
    }
  }
  /** Ready images survive in their owning Texture.Source until ordinary model GC. */
  readonly close=()=>{
    if(this.closed)return;this.closed=true;this.options.signal.removeEventListener('abort',this.close);
    for(const record of [...this.records.values()])if(record.status==='queued'||record.status==='active')this.fail(record,abortError());
    this.records.clear();this.queue.length=0;this.pixels=0;this.keyBytes=0;this.pendingKeyBytes=0;
  };
}
class ScopedTextureLoader extends TextureLoader {
  constructor(private cache:WorldImageCache,manager:LoadingManager){super(manager);}
  override load(url:string,onLoad?:(texture:Texture<HTMLImageElement>)=>void,_onProgress?:(event:ProgressEvent)=>void,onError?:(error:unknown)=>void):Texture<HTMLImageElement>{
    const resolved=this.manager.resolveURL(this.path?this.path+url:url),texture=new Texture<HTMLImageElement>();this.manager.itemStart(resolved);
    try{
      const image=this.cache.acquire(resolved,this.manager.abortController.signal,this.crossOrigin);
      // Mark only the new Texture's initial source. Assigning shared Source
      // first would increment its version on every cache hit and invalidate
      // existing GPU users, repeating uploads of an unchanged decoded image.
      texture.needsUpdate=true;texture.source=image.source;
      const failed=(error:unknown)=>this.reportError(resolved,texture,error,onError);
      // Supplied callbacks may throw. Convert onLoad failures to the consumer's
      // error path and finish manager accounting without an orphan rejection.
      void image.ready.then(()=>{try{onLoad?.(texture);}catch(error){failed(error);}},failed)
        .then(()=>{try{this.manager.itemEnd(resolved);}catch{/* A manager callback cannot orphan the owned request. */}});
    }catch(error){queueMicrotask(()=>{this.reportError(resolved,texture,error,onError);try{this.manager.itemEnd(resolved);}catch{/* Manager callback failure is isolated. */}});}
    return texture;
  }
  private reportError(url:string,texture:Texture,error:unknown,onError?:((error:unknown)=>void)):void{
    texture.dispose();
    try{onError?.(error);}catch{/* One consumer callback cannot break shared images or accounting. */}
    try{this.manager.itemError(url);}catch{/* Manager error listeners may also throw. */}
  }
}
