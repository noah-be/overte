// SPDX-License-Identifier: Apache-2.0
// Modified for Overte direct browser compatibility: verify direct HTTPS Unicode
// routes in place of the original gateway adapter while preserving cache checks.
import test from 'node:test';
import assert from 'node:assert/strict';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {BakedFbxPreparePool,type PreparedBakedFbx,type FbxPreparationWorker} from '../src/model-fbx-pool';
const prepared=(bytes=8):PreparedBakedFbx=>({buffer:new ArrayBuffer(bytes),phases:{materialBindingsMs:2,decodeMs:5}});
const handled=<T>(promise:Promise<T>)=>promise.then(result=>({result,error:undefined}),error=>({result:undefined,error:error as Error}));
function deferred(){let resolve!:(value:PreparedBakedFbx)=>void,reject!:(error:unknown)=>void;const promise=new Promise<PreparedBakedFbx>((ok,no)=>{resolve=ok;reject=no;});return{promise,resolve,reject};}
const flush=async()=>{for(let i=0;i<6;i++)await Promise.resolve();};

test('pending readers deduplicate preparation; ready hits borrow bytes while isolating phase records',async()=>{
  const cache=new PreparedFbxCache(),pending=deferred();let calls=0;
  try{const producer=()=>{calls++;return pending.promise;};const a=cache.get('https://assets.test/a.fbx',producer),b=cache.get('https://assets.test/a.fbx',producer);await flush();assert.equal(calls,1);pending.resolve(prepared());
    const [first,second]=await Promise.all([a,b]);assert.equal(first.buffer,second.buffer);assert.equal(first.cacheHit,false);assert.equal(second.cacheHit,true);first.phases.decodeMs=999;
    const ready=await cache.get('https://assets.test/a.fbx',()=>assert.fail('Ready bytes cannot re-run decoding'));
    assert.equal(ready.buffer,first.buffer);assert.equal(ready.phases.decodeMs,5);assert.equal(ready.cacheHit,true);
    assert.deepEqual(cache.stats,{hits:2,misses:1,bytes:8,keyBytes:50,ready:1,active:0,readers:0,evictions:0,disposed:false});
  }finally{cache.dispose();}
});

test('one reader abort cannot revoke another; the last pending reader immediately aborts its producer',async()=>{
  const cache=new PreparedFbxCache(),pending=deferred(),aAbort=new AbortController(),bAbort=new AbortController();let producerSignal:AbortSignal|undefined;
  const producer=(signal:AbortSignal)=>{producerSignal=signal;return pending.promise;};
  const a=handled(cache.get('https://assets.test/a.fbx',producer,aAbort.signal)),b=handled(cache.get('https://assets.test/a.fbx',producer,bAbort.signal));
  await flush();aAbort.abort();assert.equal((await a).error!.name,'AbortError');assert.equal(producerSignal!.aborted,false);assert.equal(cache.stats.active,1);
  bAbort.abort();assert.equal(producerSignal!.aborted,true);assert.equal((await b).error!.name,'AbortError');assert.equal(cache.stats.active,0);assert.equal(cache.stats.readers,0);
  pending.resolve(prepared());await flush();assert.equal(cache.stats.ready,0);cache.dispose();
});

test('revoked generation cannot overwrite a fresh producer for the same exact source',async()=>{
  const cache=new PreparedFbxCache(),stale=deferred(),fresh=deferred(),abort=new AbortController();
  const old=handled(cache.get('https://assets.test/a.fbx',()=>stale.promise,abort.signal));await flush();abort.abort();await old;
  const next=cache.get('https://assets.test/a.fbx',()=>fresh.promise);await flush();stale.resolve(prepared(1));await flush();assert.equal(cache.stats.active,1);assert.equal(cache.stats.ready,0);
  fresh.resolve(prepared(9));assert.equal((await next).buffer.byteLength,9);assert.equal(cache.stats.bytes,9);cache.dispose();
});

test('world revocation rejects active, pending and queued ready deliveries and clears all cache bytes',async()=>{
  const world=new AbortController(),cache=new PreparedFbxCache({signal:world.signal});await cache.get('https://assets.test/ready.fbx',async()=>prepared());
  const pending=deferred();let signal:AbortSignal|undefined;
  const active=handled(cache.get('https://assets.test/active.fbx',value=>{signal=value;return pending.promise;}));await flush();
  const ready=handled(cache.get('https://assets.test/ready.fbx',()=>assert.fail('No redecoding')));world.abort();
  assert.equal(signal!.aborted,true);assert.equal((await active).error!.name,'AbortError');assert.equal((await ready).error!.name,'AbortError');assert.equal(cache.stats.bytes,0);assert.equal(cache.stats.readers,0);
  pending.resolve(prepared(100));await flush();assert.equal(cache.stats.ready,0);await assert.rejects(cache.get('new',async()=>prepared()),{name:'AbortError'});cache.dispose();
});

test('ready-reader cancellation preserves the cached result and unrelated readers',async()=>{
  const cache=new PreparedFbxCache();await cache.get('https://assets.test/a.fbx',async()=>prepared());const abort=new AbortController();
  const cancelled=handled(cache.get('https://assets.test/a.fbx',()=>assert.fail(),abort.signal));const healthy=cache.get('https://assets.test/a.fbx',()=>assert.fail());abort.abort();
  assert.equal((await cancelled).error!.name,'AbortError');assert.equal((await healthy).buffer.byteLength,8);assert.equal(cache.stats.ready,1);cache.dispose();
});

test('early cancellation and the producer-start microtask race never invoke revoked work',async()=>{
  const cache=new PreparedFbxCache(),abort=new AbortController();let called=0;
  const result=handled(cache.get('https://assets.test/a.fbx',async()=>{called++;return prepared();},abort.signal));
  queueMicrotask(()=>abort.abort());assert.equal((await result).error!.name,'AbortError');await flush();assert.equal(called,0);cache.dispose();
});

test('exact keys remain distinct and metadata is bounded before producer invocation',async()=>{
  const cache=new PreparedFbxCache(),requests:ReturnType<typeof handled>[]=[];let calls=0;
  for(let i=0;i<16;i++)requests.push(handled(cache.get('https://assets.test/a.fbx?token='+i,()=>{calls++;return new Promise(()=>{});})));await flush();assert.equal(calls,16);
  await assert.rejects(cache.get('https://assets.test/extra.fbx',()=>assert.fail()),/16-pending/);
  await assert.rejects(cache.get('x'.repeat(65537),()=>assert.fail()),/bounded authorized source/);assert.equal(cache.stats.active,16);cache.dispose();await Promise.all(requests);
});

test('deduplicated reader metadata cannot grow without a bound',async()=>{
  const cache=new PreparedFbxCache(),requests=[];let calls=0;
  const producer=()=>{calls++;return new Promise<PreparedBakedFbx>(()=>{});};
  for(let i=0;i<256;i++)requests.push(handled(cache.get('https://assets.test/a.fbx',producer)));
  await assert.rejects(cache.get('https://assets.test/a.fbx',producer),/256-reader/);await flush();assert.equal(calls,1);assert.equal(cache.stats.readers,256);cache.dispose();await Promise.all(requests);
});

test('128 ready entries evict least-recently-used bytes while hits retain the current entry',async()=>{
  const cache=new PreparedFbxCache();for(let i=0;i<128;i++)await cache.get('https://assets.test/'+i,async()=>prepared());
  await cache.get('https://assets.test/0',()=>assert.fail());await cache.get('https://assets.test/128',async()=>prepared());assert.equal(cache.stats.ready,128);assert.equal(cache.stats.evictions,1);
  await cache.get('https://assets.test/0',()=>assert.fail());let reloaded=false;await cache.get('https://assets.test/1',async()=>{reloaded=true;return prepared();});assert(reloaded);assert.equal(cache.stats.ready,128);cache.dispose();
});

test('128 MiB ready budget evicts by bytes; larger valid output is delivered without caching',async()=>{
  const cache=new PreparedFbxCache();for(let i=0;i<2;i++)await cache.get('https://assets.test/'+i,async()=>prepared(64*1024*1024));assert.equal(cache.stats.bytes,128*1024*1024);
  await cache.get('https://assets.test/2',async()=>prepared(1));assert.equal(cache.stats.ready,2);assert.equal(cache.stats.bytes,64*1024*1024+1);assert.equal(cache.stats.evictions,1);
  const result=await cache.get('https://assets.test/oversize',async()=>prepared(128*1024*1024+1));assert.equal(result.buffer.byteLength,128*1024*1024+1);assert.equal(cache.stats.ready,2);cache.dispose();
});

test('failed, malformed or externally detached preparation is never retained as a successful hit',async()=>{
  const cache=new PreparedFbxCache();await assert.rejects(cache.get('https://assets.test/a',()=>{throw Error('Actual decoder failed');}),/Actual decoder failed/);assert.equal(cache.stats.active,0);
  await assert.rejects(cache.get('https://assets.test/a',async()=>({buffer:new ArrayBuffer(1),phases:{materialBindingsMs:NaN,decodeMs:1}})),/invalid bytes or phases/);assert.equal(cache.stats.ready,0);
  const value=await cache.get('https://assets.test/a',async()=>prepared());structuredClone(value.buffer,{transfer:[value.buffer]});const next=await cache.get('https://assets.test/a',async()=>prepared(7));assert.equal(next.cacheHit,false);assert.equal(next.buffer.byteLength,7);assert.equal(cache.stats.evictions,1);cache.dispose();
});


test('ready metadata retains only the two bounded CPU fields, never producer extras',async()=>{
  const cache=new PreparedFbxCache(),value=prepared();
  Object.assign(value.phases,{unexpected:new Uint8Array(1024)});
  const result=await cache.get('https://assets.test/a',async()=>value);
  assert.deepEqual(Object.keys(result.phases).sort(),['decodeMs','materialBindingsMs']);cache.dispose();
});


test('cache producer cancellation reaches the owned preparation pool only after its last reader leaves',async()=>{
  let terminated=false,preparations=0;
  const worker:FbxPreparationWorker={onmessage:null,onerror:null,onmessageerror:null,terminate(){terminated=true;},postMessage(value,transfers=[]){structuredClone(value,{transfer:transfers as ArrayBuffer[]});}};
  const pool=new BakedFbxPreparePool({limit:1,workerFactory:()=>worker}),cache=new PreparedFbxCache();
  const firstAbort=new AbortController(),secondAbort=new AbortController();
  const producer=(signal:AbortSignal)=>{preparations++;return pool.prepare(new ArrayBuffer(8),signal);};
  const first=handled(cache.get('https://assets.test/a',producer,firstAbort.signal)),second=handled(cache.get('https://assets.test/a',producer,secondAbort.signal));
  try{await flush();assert.equal(preparations,1);assert.equal(pool.counters.active,1);
    firstAbort.abort();assert.equal((await first).error!.name,'AbortError');assert.equal(terminated,false);assert.equal(pool.counters.active,1);
    secondAbort.abort();assert.equal((await second).error!.name,'AbortError');assert.equal(terminated,true);assert.equal(pool.counters.workers,0);assert.equal(pool.counters.inputBytes,0);await flush();assert.equal(cache.stats.ready,0);
  }finally{cache.dispose();pool.dispose();}
});


test('an actual 4096-code-unit Unicode HTTPS source remains cacheable after browser URL encoding',async()=>{
  const cache=new PreparedFbxCache(),prefix='https://assets.test/',suffix='.fbx';
  const asset=prefix+'漢'.repeat(4096-prefix.length-suffix.length)+suffix;assert.equal(asset.length,4096);
  const key=new URL(asset).href;
  assert(key.length>8192&&key.length<65536);assert.equal(decodeURI(key),asset);
  const preparedResult=await cache.get(key,async()=>prepared());assert.equal(preparedResult.buffer.byteLength,8);
  await cache.get(key,()=>assert.fail('Actual encoded source should hit'));assert.equal(cache.stats.hits,1);cache.dispose();
});
