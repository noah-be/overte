// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact authorized routes only; instances belong to one visitor World.
interface Reader { signal?:AbortSignal; abort?:()=>void; entry?:Pending; settled:boolean; resolve(value:string):void; reject(error:unknown):void }
interface Pending { key:string; controller:AbortController; readers:Set<Reader>; timer:ReturnType<typeof setTimeout> }
interface Ready { value:string; bytes:number }
export interface WorldSourceAuthority { generation:string; assertCurrent():void }
const cancelled=()=>new DOMException('World text loading was cancelled','AbortError');
const MAX_READERS=256,MAX_PENDING=32,MAX_ENTRIES=512,MAX_BYTES=8*1024*1024,MAX_KEY=65536;
/** Share immutable source text, never mutable parsed material/metadata objects.
 * One reader ending cannot cancel another reader's transfer. A late result from
 * an abandoned generation cannot replace a new request for the same route. */
export class WorldSourceTextCache {
  private ready=new Map<string,Ready>();private pending=new Map<string,Pending>();private readers=new Set<Reader>();
  private closed=false;private bytes=0;private hits=0;private misses=0;private evictions=0;
  private readonly abort=()=>this.dispose();
  constructor(private signal:AbortSignal){if(signal.aborted)this.closed=true;else signal.addEventListener('abort',this.abort,{once:true});}
  get stats(){return {hits:this.hits,misses:this.misses,bytes:this.bytes,ready:this.ready.size,active:this.pending.size,readers:this.readers.size,evictions:this.evictions,disposed:this.closed};}
  get(key:string,maximumBytes:number,producer:(signal:AbortSignal)=>Promise<string>,signal?:AbortSignal):Promise<string>{
    if(this.closed||signal?.aborted)return Promise.reject(cancelled());
    if(typeof key!=='string'||!key||key.length>MAX_KEY||!Number.isSafeInteger(maximumBytes)||maximumBytes<1||maximumBytes>1024*1024||typeof producer!=='function')return Promise.reject(Error('World text requires a bounded authorized route and byte limit'));
    if(this.readers.size>=MAX_READERS)return Promise.reject(Error('Too many readers of world source text'));
    // Different response bounds are separate admission contracts.
    const slot=maximumBytes+':'+key,cached=this.ready.get(slot);let entry=this.pending.get(slot);
    if(!cached&&!entry&&this.pending.size>=MAX_PENDING)return Promise.reject(Error('Too many pending world source texts'));
    if(cached||entry)this.hits++;else this.misses++;
    if(cached){this.ready.delete(slot);this.ready.set(slot,cached);}
    let created=false;
    if(!cached&&!entry){
      const controller=new AbortController();entry={key:slot,controller,readers:new Set(),timer:setTimeout(()=>this.fail(slot,controller,Error('World source text exceeded its30second deadline')),30000)};
      this.pending.set(slot,entry);created=true;
    }
    const owned=entry;
    return new Promise((resolve,reject)=>{
      const reader:Reader={signal,entry:owned,settled:false,resolve,reject};reader.abort=()=>this.cancel(reader);this.readers.add(reader);owned?.readers.add(reader);signal?.addEventListener('abort',reader.abort,{once:true});
      if(cached)queueMicrotask(()=>this.deliver(reader,cached.value));
      if(created)queueMicrotask(()=>this.start(owned!,maximumBytes,producer));
    });
  }
  private finish(reader:Reader,error?:unknown,value?:string){
    if(reader.settled)return;reader.settled=true;this.readers.delete(reader);reader.entry?.readers.delete(reader);if(reader.abort)reader.signal?.removeEventListener('abort',reader.abort);
    if(value!==undefined)reader.resolve(value);else reader.reject(error??cancelled());
  }
  private deliver(reader:Reader,value:string){if(this.closed||reader.signal?.aborted)this.cancel(reader);else this.finish(reader,undefined,value);}
  private cancel(reader:Reader){const entry=reader.entry;this.finish(reader,cancelled());if(entry&&!entry.readers.size&&this.pending.get(entry.key)===entry){this.pending.delete(entry.key);clearTimeout(entry.timer);entry.controller.abort();}}
  private fail(key:string,controller:AbortController,error:unknown){const entry=this.pending.get(key);if(!entry||entry.controller!==controller)return;this.pending.delete(key);clearTimeout(entry.timer);controller.abort();for(const reader of [...entry.readers])this.finish(reader,error);}
  private start(entry:Pending,maximumBytes:number,producer:(signal:AbortSignal)=>Promise<string>){
    if(this.closed||this.pending.get(entry.key)!==entry)return;
    void Promise.resolve().then(()=>{entry.controller.signal.throwIfAborted();return producer(entry.controller.signal);}).then(value=>{
      if(this.closed||entry.controller.signal.aborted||this.pending.get(entry.key)!==entry)return;
      // Every UTF-16 unit needs at least one UTF-8 byte. The producer additionally
      // bounds encoded bytes before decoding; this checks its output contract.
      if(typeof value!=='string'||value.length>maximumBytes)throw Error('World text producer returned oversized or invalid text');
      this.pending.delete(entry.key);clearTimeout(entry.timer);const bytes=(value.length+entry.key.length)*2;
      if(bytes<=MAX_BYTES){while(this.ready.size>=MAX_ENTRIES||this.bytes+bytes>MAX_BYTES)this.evict(this.ready.keys().next().value!);this.ready.set(entry.key,{value,bytes});this.bytes+=bytes;}
      for(const reader of [...entry.readers])queueMicrotask(()=>this.deliver(reader,value));
    }).catch(error=>this.fail(entry.key,entry.controller,error));
  }
  private evict(key:string){const value=this.ready.get(key);if(!value)return;this.ready.delete(key);this.bytes-=value.bytes;this.evictions++;}
  dispose(){if(this.closed)return;this.closed=true;this.signal.removeEventListener('abort',this.abort);const pending=[...this.pending.values()];this.pending.clear();this.ready.clear();this.bytes=0;for(const entry of pending){clearTimeout(entry.timer);entry.controller.abort();}for(const reader of [...this.readers])this.finish(reader,cancelled());}
}

/** Bound encoded bytes before UTF-8 decode, cancel stalled bodies with the exact
 * producer authority, and reject invalid UTF-8 rather than changing source. */
export async function readWorldSourceText(response:Response,signal:AbortSignal,maximum:number):Promise<string>{
  if(!Number.isSafeInteger(maximum)||maximum<1||maximum>1024*1024){await response.body?.cancel();throw Error('Invalid world source text byte limit');}
  const declared=response.headers.get('content-length');
  if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>maximum)){await response.body?.cancel();throw Error('World source text exceeds its encoded byte limit');}
  if(!response.body)throw Error('World source text has no response body');
  const reader=response.body.getReader();let storage=new Uint8Array(Math.min(maximum,4096)),bytes=0;
  const abort=()=>{void reader.cancel(signal.reason).catch(()=>{});};signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
  try{signal.throwIfAborted();while(true){
    const next=await reader.read();signal.throwIfAborted();if(next.done)break;
    if(!(next.value instanceof Uint8Array)||next.value.byteLength>maximum-bytes)throw Error('World source text exceeds its encoded byte limit');
    const needed=bytes+next.value.byteLength;
    if(needed>storage.length){const grown=new Uint8Array(Math.min(maximum,Math.max(needed,storage.length*2)));grown.set(storage.subarray(0,bytes));storage=grown;}
    // Copy the view, never retain arbitrary response backing buffers or an
    // unbounded array of one-byte chunks. At most two bounded allocations exist.
    storage.set(next.value,bytes);bytes=needed;
  }}
  catch(error){await reader.cancel().catch(()=>{});throw error;}finally{signal.removeEventListener('abort',abort);reader.releaseLock();}
  return new TextDecoder('utf-8',{fatal:true}).decode(storage.subarray(0,bytes));
}
