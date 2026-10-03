// SPDX-License-Identifier: Apache-2.0
import {preparedFbxBytes} from './embedded-fbx-protocol';
import type {PreparedBakedFbx} from './model-fbx-pool';
export interface CachedPreparedFbx extends PreparedBakedFbx {cacheHit:boolean}
export type PreparedFbxProducer=(signal:AbortSignal)=>Promise<PreparedBakedFbx>;
interface Reader {signal?:AbortSignal;onAbort?:()=>void;entry?:Pending;hit:boolean;settled:boolean;resolve(value:CachedPreparedFbx):void;reject(error:unknown):void}
interface Pending {key:string;controller:AbortController;readers:Set<Reader>}
interface Ready {value:PreparedBakedFbx;bytes:number}
const MAX_READY=128,MAX_READY_BYTES=128*1024*1024,MAX_READY_KEY_BYTES=8*1024*1024,MAX_PENDING=16,MAX_READERS=256,MAX_KEY=65536;
const abortError=()=>new DOMException('Prepared FBX request cancelled','AbortError');
/** Per-world byte cache only. The caller must authorize the exact source first.
 * Buffers are borrowed read-only by parsers; never transfer cached output again. */
export class PreparedFbxCache {
  private readonly ready=new Map<string,Ready>();
  private readonly pending=new Map<string,Pending>();
  private readonly readers=new Set<Reader>();
  private readonly signal?:AbortSignal;
  private readonly onAbort=()=>this.dispose();
  private disposed=false;
  private bytes=0;private keyBytes=0;private hits=0;private misses=0;private evictions=0;
  constructor(options:{signal?:AbortSignal}={}){
    this.signal=options.signal;
    if(this.signal?.aborted)this.disposed=true;
    else this.signal?.addEventListener('abort',this.onAbort,{once:true});
  }
  get(key:string,producer:PreparedFbxProducer,signal?:AbortSignal):Promise<CachedPreparedFbx>{
    if(this.disposed||signal?.aborted)return Promise.reject(abortError());
    if(typeof key!=='string'||!key.length||key.length>MAX_KEY||typeof producer!=='function')return Promise.reject(Error('Prepared FBX requires an exact bounded authorized source key and producer'));
    if(this.readers.size>=MAX_READERS)return Promise.reject(Error('Prepared FBX cache exceeds its 256-reader limit'));
    let cached=this.ready.get(key);
    if(cached){try{if(preparedFbxBytes(cached.value).bytes!==cached.bytes)throw Error('Detached prepared resource');}catch{this.evict(key);cached=undefined;}}
    let pending=this.pending.get(key);const hit=!!cached||!!pending;
    if(!cached&&!pending&&this.pending.size>=MAX_PENDING)return Promise.reject(Error('Prepared FBX cache exceeds its 16-pending-key limit'));
    if(hit)this.hits++;else this.misses++;
    if(cached){this.ready.delete(key);this.ready.set(key,cached);}
    let created=false;
    if(!cached&&!pending){pending={key,controller:new AbortController(),readers:new Set()};this.pending.set(key,pending);created=true;}
    const owned=pending,value=cached?.value;
    return new Promise((resolve,reject)=>{
      const reader:Reader={signal,entry:owned,hit,settled:false,resolve,reject};
      reader.onAbort=()=>this.cancel(reader);this.readers.add(reader);owned?.readers.add(reader);
      signal?.addEventListener('abort',reader.onAbort,{once:true});
      // Ready reads also settle asynchronously through the same revocation gate.
      if(value)queueMicrotask(()=>this.deliver(reader,value));
      if(created)queueMicrotask(()=>this.start(owned!,producer));
    });
  }
  get stats(){return{hits:this.hits,misses:this.misses,bytes:this.bytes,keyBytes:this.keyBytes,ready:this.ready.size,active:this.pending.size,readers:this.readers.size,evictions:this.evictions,disposed:this.disposed};}
  private finish(reader:Reader,error?:unknown,value?:PreparedBakedFbx):void{
    if(reader.settled)return;
    let embedded={};if(value){try{embedded=preparedFbxBytes(value).fields;}catch(error){this.finish(reader,error);return;}}
    reader.settled=true;this.readers.delete(reader);reader.entry?.readers.delete(reader);
    if(reader.onAbort)reader.signal?.removeEventListener('abort',reader.onAbort);
    if(value)reader.resolve({buffer:value.buffer,phases:{...value.phases},...embedded,cacheHit:reader.hit});
    else reader.reject(error??abortError());
  }
  private deliver(reader:Reader,value:PreparedBakedFbx):void{
    if(this.disposed||reader.signal?.aborted){this.cancel(reader);return;}
    this.finish(reader,undefined,value);
  }
  private cancel(reader:Reader):void{
    if(reader.settled)return;const entry=reader.entry;this.finish(reader,abortError());
    if(entry&&!entry.readers.size&&this.pending.get(entry.key)===entry){this.pending.delete(entry.key);entry.controller.abort();}
  }
  private start(entry:Pending,producer:PreparedFbxProducer):void{
    if(this.disposed||entry.controller.signal.aborted||this.pending.get(entry.key)!==entry)return;
    // Both synchronous throws and asynchronous failures remove only this generation.
    void Promise.resolve().then(()=>{
      if(this.disposed||entry.controller.signal.aborted||this.pending.get(entry.key)!==entry)throw abortError();
      return producer(entry.controller.signal);
    }).then(value=>{
      if(this.disposed||entry.controller.signal.aborted||this.pending.get(entry.key)!==entry)return;
      if(!(value?.buffer instanceof ArrayBuffer)||!value.buffer.byteLength||value.buffer.byteLength>256*1024*1024||!value.phases||![value.phases.materialBindingsMs,value.phases.decodeMs].every(number=>Number.isFinite(number)&&number>=0&&number<=60000))throw Error('Prepared FBX producer returned invalid bytes or phases');
      const accounted=preparedFbxBytes(value);
      this.pending.delete(entry.key);
      const stored:PreparedBakedFbx={buffer:value.buffer,phases:Object.freeze({materialBindingsMs:value.phases.materialBindingsMs,decodeMs:value.phases.decodeMs}),...accounted.fields};
      const keyBytes=entry.key.length*2;
      if(accounted.bytes<=MAX_READY_BYTES&&keyBytes<=MAX_READY_KEY_BYTES){
        while(this.ready.size>=MAX_READY||this.bytes+accounted.bytes>MAX_READY_BYTES||this.keyBytes+keyBytes>MAX_READY_KEY_BYTES)this.evict(this.ready.keys().next().value!);
        this.ready.set(entry.key,{value:stored,bytes:accounted.bytes});this.bytes+=accounted.bytes;this.keyBytes+=keyBytes;
      }
      for(const reader of [...entry.readers])queueMicrotask(()=>this.deliver(reader,stored));
    }).catch(error=>{
      if(this.pending.get(entry.key)!==entry)return;
      this.pending.delete(entry.key);for(const reader of [...entry.readers])this.finish(reader,error);
    });
  }
  private evict(key:string):void{const value=this.ready.get(key);if(!value)return;this.ready.delete(key);this.bytes-=value.bytes;this.keyBytes-=key.length*2;this.evictions++;}
  dispose():void{
    if(this.disposed)return;this.disposed=true;this.signal?.removeEventListener('abort',this.onAbort);
    const pending=[...this.pending.values()];this.pending.clear();this.ready.clear();this.bytes=0;this.keyBytes=0;
    for(const entry of pending)entry.controller.abort();for(const reader of [...this.readers])this.finish(reader,abortError());
  }
}
