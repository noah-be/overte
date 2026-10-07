// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {stripTypeScriptTypes} from 'node:module';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {preparedFbxBytes} from '../src/embedded-fbx-protocol';
import type {PreparedBakedFbx} from '../src/model-fbx-pool';
const prepared=(size=8):PreparedBakedFbx=>({buffer:new ArrayBuffer(size),phases:{materialBindingsMs:2,decodeMs:5}});
function originalCountControl(){
 const source=readFileSync(new URL('../src/prepared-fbx-cache.ts',import.meta.url),'utf8');
 assert.equal(source.match(/MAX_READY=128/g)?.length,1,'Counterfactual must change exactly the ready count bound');
 const withoutImports=source.replace('MAX_READY=128','MAX_READY=64').replace(/^import .*;$/gm,'');
 const compiled=stripTypeScriptTypes(withoutImports,{mode:'strip'}).replace('export class PreparedFbxCache','class PreparedFbxCache')+'\nPreparedFbxCache;';
 return vm.runInNewContext(compiled,{preparedFbxBytes,ArrayBuffer,DOMException,AbortController,queueMicrotask,setTimeout,clearTimeout}) as typeof PreparedFbxCache;
}
test('actual cache methods: observed123-key cardinality plus8 old-key repeats re-prepare under original64 but reuse under128',async()=>{
 const run=async(Cache:typeof PreparedFbxCache)=>{
  const cache=new Cache();let preparations=0;const firstBuffers=new Map<string,ArrayBuffer>();
  try{
   const producer=async()=>{preparations++;return prepared(32*1024);};
   for(let i=0;i<123;i++){const key=`https://assets.test/owned/${i}.fbx`;firstBuffers.set(key,(await cache.get(key,producer)).buffer);}
   let identicalBorrowedBuffers=0;
   for(let i=0;i<8;i++){const key=`https://assets.test/owned/${i}.fbx`,value=await cache.get(key,producer);if(value.buffer===firstBuffers.get(key))identicalBorrowedBuffers++;}
   return {preparations,identicalBorrowedBuffers,stats:cache.stats};
  }finally{cache.dispose();assert.equal(cache.stats.bytes,0);assert.equal(cache.stats.keyBytes,0);assert.equal(cache.stats.readers,0);}
 };
 const original=await run(originalCountControl()),candidate=await run(PreparedFbxCache);
 assert.equal(original.preparations,131);assert.equal(original.identicalBorrowedBuffers,0);assert.equal(original.stats.ready,64);assert.equal(original.stats.evictions,67);
 assert.equal(candidate.preparations,123);assert.equal(candidate.identicalBorrowedBuffers,8);assert.equal(candidate.stats.hits,8);assert.equal(candidate.stats.evictions,0);assert.equal(candidate.stats.bytes,123*32768);
});
test('8MiB UTF16 ready-key limit is exact even with small buffers; byte and LRU ownership release is charged on every eviction',async()=>{
 const cache=new PreparedFbxCache(),key=(i:number)=>'😀'.repeat(32766)+String(i).padStart(4,'0');
 try{
  assert.equal(key(0).length,65536);
  for(let i=0;i<64;i++)await cache.get(key(i),async()=>prepared(1));
  assert.equal(cache.stats.ready,64);assert.equal(cache.stats.keyBytes,8*1024*1024);assert.equal(cache.stats.bytes,64);
  await cache.get(key(0),()=>assert.fail('Existing key must be borrowed without producer'));
  await cache.get(key(64),async()=>prepared(1));assert.equal(cache.stats.ready,64);assert.equal(cache.stats.evictions,1);assert.equal(cache.stats.keyBytes,8*1024*1024);
  await cache.get(key(0),()=>assert.fail('Hit changed LRU order incorrectly'));
  const next=await cache.get('q',async()=>prepared(2));assert.equal(next.cacheHit,false);assert.equal(cache.stats.ready,64);assert.equal(cache.stats.evictions,2);assert.equal(cache.stats.keyBytes,8*1024*1024-131072+2);assert.equal(cache.stats.bytes,65);
 }finally{cache.dispose();assert.equal(cache.stats.keyBytes,0);cache.dispose();assert.equal(cache.stats.keyBytes,0);assert.equal(cache.stats.bytes,0);}
});
test('oversized single key is rejected before any producer/readers; exact UTF16 edge remains accepted',async()=>{
 const cache=new PreparedFbxCache();let calls=0;
 try{
  await assert.rejects(cache.get('😀'.repeat(32768)+'x',async()=>{calls++;return prepared();}),/bounded authorized source/);assert.equal(calls,0);assert.equal(cache.stats.readers,0);assert.equal(cache.stats.keyBytes,0);
  const value=await cache.get('😀'.repeat(32768),async()=>{calls++;return prepared();});assert.equal(value.buffer.byteLength,8);assert.equal(calls,1);assert.equal(cache.stats.keyBytes,131072);
 }finally{cache.dispose();}
});
test('detached ready output accounts key once before its replacement and repeated dispose never goes negative',async()=>{
 const cache=new PreparedFbxCache(),key='https://assets.test/owned/one.fbx';
 const first=await cache.get(key,async()=>prepared(8));assert.equal(cache.stats.keyBytes,key.length*2);
 structuredClone(first.buffer,{transfer:[first.buffer]});const second=await cache.get(key,async()=>prepared(9));
 assert.equal(second.cacheHit,false);assert.equal(cache.stats.evictions,1);assert.equal(cache.stats.bytes,9);assert.equal(cache.stats.keyBytes,key.length*2);
 cache.dispose();cache.dispose();assert.equal(cache.stats.keyBytes,0);assert.equal(cache.stats.bytes,0);assert.equal(cache.stats.evictions,1);
});
test('revocation before a ready delivery and stale producer completion release all exact key accounting synchronously',async()=>{
 const world=new AbortController(),cache=new PreparedFbxCache({signal:world.signal}),key='https://assets.test/owned/ready.fbx';
 await cache.get(key,async()=>prepared());
 let publish!:(value:PreparedBakedFbx)=>void;const pending=cache.get('https://assets.test/owned/pending.fbx',()=>new Promise<PreparedBakedFbx>(resolve=>{publish=resolve;})).then(()=>assert.fail('Stale producer escaped'),error=>assert.equal(error.name,'AbortError'));
 for(let i=0;i<4;i++)await Promise.resolve();
 // Create a genuine ready read and revoke before its delivery microtask.
 const queued=cache.get(key,()=>assert.fail()).then(()=>assert.fail('Queued ready bytes escaped'),error=>assert.equal(error.name,'AbortError'));
 world.abort();assert.equal(cache.stats.keyBytes,0);assert.equal(cache.stats.bytes,0);assert.equal(cache.stats.active,0);assert.equal(cache.stats.readers,0);
 await Promise.all([queued,pending]);publish(prepared());for(let i=0;i<4;i++)await Promise.resolve();assert.equal(cache.stats.keyBytes,0);assert.equal(cache.stats.ready,0);cache.dispose();
});
