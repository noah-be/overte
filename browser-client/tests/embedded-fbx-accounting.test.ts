// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';import {BakedFbxPreparePool,type FbxPreparationWorker} from '../src/model-fbx-pool';import {preparedFbxBytes,embeddedFbxFields} from '../src/embedded-fbx-protocol';
const ready=()=>({buffer:new ArrayBuffer(16),phases:{decodeMs:1,materialBindingsMs:1},embeddedImages:[{digest:'a'.repeat(64),mimeType:'image/png',bytes:new ArrayBuffer(4)}],embeddedCounts:{converted:1,rawBytes:4,skippedOversize:0,skippedUnsupported:0}});
test('prepared cache charges actual descriptor bytes and refuses detached ready images without stale delivery',async()=>{
 const cache=new PreparedFbxCache();let calls=0;const producer=async()=>{calls++;return ready();};const first=await cache.get('approved-exact-route',producer),again=await cache.get('approved-exact-route',producer);
 assert.equal(cache.stats.bytes,20);assert.equal(calls,1);assert.equal(first.embeddedImages?.[0].bytes,again.embeddedImages?.[0].bytes);assert(Object.isFrozen(again.embeddedImages));
 structuredClone(first.embeddedImages![0].bytes,{transfer:[first.embeddedImages![0].bytes]});const renewed=await cache.get('approved-exact-route',producer);assert.equal(renewed.cacheHit,false);assert.equal(calls,2);assert.equal(cache.stats.bytes,20);assert.equal(cache.stats.evictions,1);cache.dispose();
});
test('actual pool handler refuses forged accounting/oversized descriptors and retires only the failed worker',async()=>{
 let reply!:FbxPreparationWorker;let terminated=0;
 const pool=new BakedFbxPreparePool({workerFactory:()=>reply={onmessage:null,onerror:null,onmessageerror:null,postMessage(){},terminate(){terminated++;}}});
 const pending=pool.prepare(new ArrayBuffer(1));reply.onmessage!({data:{id:1,...ready(),embeddedCounts:{converted:1,rawBytes:0,skippedOversize:0,skippedUnsupported:0}}} as MessageEvent);
 await assert.rejects(pending,/accounting/);assert.equal(terminated,1);assert.equal(pool.counters.outstanding,0);pool.dispose();
});
test('descriptor validator counts actual combined output and limits bytes even when declared counters lie',()=>{
 const value=ready();assert.equal(preparedFbxBytes(value).bytes,20);
 for(const bad of [{...value,embeddedImages:[{...value.embeddedImages[0],bytes:new ArrayBuffer(8*1024*1024+1)}]}, {...value,embeddedImages:[value.embeddedImages[0],value.embeddedImages[0]]}, {...value,embeddedCounts:{...value.embeddedCounts,converted:65}}])assert.throws(()=>embeddedFbxFields(bad));
 assert.throws(()=>preparedFbxBytes({...value,buffer:new ArrayBuffer(256*1024*1024)}),/256 MiB/);
});
test('actual pool preserves only bounded descriptor fields and cancelled late results cannot publish them',async()=>{
 const workers:FbxPreparationWorker[]=[];let terminated=0;
 const pool=new BakedFbxPreparePool({limit:1,workerFactory:()=>{const worker:FbxPreparationWorker={onmessage:null,onerror:null,onmessageerror:null,postMessage(){},terminate(){terminated++;}};workers.push(worker);return worker;}});
 const pending=pool.prepare(new ArrayBuffer(1)),value=ready();workers[0].onmessage!({data:{id:1,...value,untrustedExtra:'never retain'}} as MessageEvent);const output=await pending;
 assert.equal(output.embeddedImages![0].bytes,value.embeddedImages[0].bytes);assert(Object.isFrozen(output.embeddedImages));assert.equal('untrustedExtra' in output,false);
 const controller=new AbortController(),cancelled=pool.prepare(new ArrayBuffer(1),controller.signal),late=workers[0].onmessage!;controller.abort();await assert.rejects(cancelled,{name:'AbortError'});
 late({data:{id:2,...ready()}} as MessageEvent);assert.equal(pool.counters.outstanding,0);assert.equal(pool.counters.completed,1);assert.equal(terminated,1);pool.dispose();
});
