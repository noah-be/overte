// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {WorldSourceTextCache,readWorldSourceText} from './world-source-text-cache';
const deferred=<T>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(yes=>resolve=yes);return {promise,resolve};};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
test('actual HTTP text transfer is coalesced while an independently canceled reader cannot cancel its sibling',async()=>{
 const owner=new AbortController(),a=new AbortController(),b=new AbortController(),cache=new WorldSourceTextCache(owner.signal),began=deferred<void>(),finish=deferred<void>();let requests=0;
 const server=createServer(async(_req,res)=>{requests++;began.resolve();await finish.promise;res.end('{"color":"actual"}');});server.listen(0,'127.0.0.1');await once(server,'listening');const address=server.address();assert(address&&typeof address==='object');const url=`http://127.0.0.1:${address.port}/source`;
 const producer=async(signal:AbortSignal)=>readWorldSourceText(await fetch(url,{signal}),signal,65536);
 try{const first=cache.get(url,65536,producer,a.signal),second=cache.get(url,65536,producer,b.signal);await began.promise;a.abort();await assert.rejects(first,{name:'AbortError'});finish.resolve();assert.equal(await second,'{"color":"actual"}');assert.equal(await cache.get(url,65536,producer),'{"color":"actual"}');assert.equal(requests,1);assert.equal(cache.stats.hits,2);assert.equal(cache.stats.readers,0);}
 finally{finish.resolve();cache.dispose();server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));}
});
test('abandoned same-route generation cannot deliver or replace later source text',async()=>{
 const owner=new AbortController(),reader=new AbortController(),cache=new WorldSourceTextCache(owner.signal),old=deferred<string>();let signal!:AbortSignal;
 const first=cache.get('authorized-session-route',64,s=>{signal=s;return old.promise;},reader.signal);await tick();reader.abort();await assert.rejects(first,{name:'AbortError'});assert(signal.aborted);
 assert.equal(await cache.get('authorized-session-route',64,async()=> 'current'),'current');old.resolve('stale');await tick();assert.equal(await cache.get('authorized-session-route',64,async()=> 'wrong'),'current');cache.dispose();
});
test('failed source is retried; parsed metadata mutations cannot alter immutable cached source',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal);await assert.rejects(cache.get('source',64,async()=>{throw Error('upstream failed');}),/upstream failed/);
 const text=await cache.get('source',64,async()=>'{"map":"original"}');JSON.parse(text).map='mutated';assert.equal(JSON.parse(await cache.get('source',64,async()=> 'wrong')).map,'original');assert.equal(cache.stats.misses,2);cache.dispose();
});
test('exact routes and byte contracts do not share; ready and in-flight delivery honor cancellation',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal);assert.equal(await cache.get('session-a',64,async()=> 'a'),'a');assert.equal(await cache.get('session-b',64,async()=> 'b'),'b');assert.equal(await cache.get('session-a',32,async()=> 'smaller'),'smaller');
 const reader=new AbortController(),ready=cache.get('session-a',64,async()=> 'wrong',reader.signal);reader.abort();await assert.rejects(ready,{name:'AbortError'});
 const late=deferred<string>(),pending=cache.get('waiting',64,()=>late.promise);await tick();owner.abort();await assert.rejects(pending,{name:'AbortError'});late.resolve('late');await tick();assert.deepEqual({...cache.stats,hits:0,misses:0},{hits:0,misses:0,bytes:0,ready:0,active:0,readers:0,evictions:0,disposed:true});await assert.rejects(cache.get('session-a',64,async()=> 'a'),{name:'AbortError'});
});
test('LRU retains at most512 entries and8MiB, charging both strings and exact route keys',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal);for(let i=0;i<513;i++)await cache.get('route-'+i,64,async()=> String(i));assert.equal(cache.stats.ready,512);assert.equal(cache.stats.evictions,1);
 const big='x'.repeat(1024*1024);for(let i=0;i<6;i++)await cache.get('big-'+i,1024*1024,async()=>big);assert(cache.stats.bytes<=8*1024*1024);assert(cache.stats.ready<=512);const before=cache.stats.misses;await cache.get('big-0',1024*1024,async()=>big);assert.equal(cache.stats.misses,before+1);cache.dispose();
});
test('pending keys and readers are bounded without starting refused producers',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal),wait=deferred<string>();const pending=[];for(let i=0;i<32;i++)pending.push(cache.get('route-'+i,64,()=>wait.promise));let called=false;await assert.rejects(cache.get('overflow',64,async()=>{called=true;return 'bad';}),/pending/);assert.equal(called,false);
 for(let i=32;i<256;i++)pending.push(cache.get('route-0',64,()=>wait.promise));await assert.rejects(cache.get('route-0',64,()=>wait.promise),/readers/);owner.abort();await Promise.all(pending.map(p=>assert.rejects(p,{name:'AbortError'})));wait.resolve('late');
});
test('30second producer deadline cancels the actual stalled body without weakening retry',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal);let cancelled=false;
 const pending=cache.get('stalled',64,async signal=>readWorldSourceText(new Response(new ReadableStream<Uint8Array>({cancel(){cancelled=true;}})),signal,64));await Promise.resolve();await Promise.resolve();t.mock.timers.tick(30000);await assert.rejects(pending,/deadline/);assert(cancelled);assert.equal(cache.stats.active,0);assert.equal(await cache.get('stalled',64,async()=> 'retry'),'retry');cache.dispose();
});
test('encoded bounds, malformed UTF-8, empty strings and already-ended body authority are explicit',async()=>{
 const signal=new AbortController().signal;let stopped=false;await assert.rejects(readWorldSourceText(new Response(new ReadableStream<Uint8Array>({cancel(){stopped=true;}}),{headers:{'content-length':'65'}}),signal,64),/encoded/);assert(stopped);
 await assert.rejects(readWorldSourceText(new Response('x'.repeat(65)),signal,64),/encoded/);await assert.rejects(readWorldSourceText(new Response(new Uint8Array([255])),signal,64),/encoded|UTF-8/);
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal);assert.equal(await cache.get('empty',64,async()=> ''),'');await assert.rejects(cache.get('bad',64,async()=> 'x'.repeat(65)),/oversized/);await assert.rejects(cache.get('bad',0,async()=> ''),/bounded/);cache.dispose();
 const ended=new AbortController();ended.abort();stopped=false;await assert.rejects(readWorldSourceText(new Response(new ReadableStream<Uint8Array>({cancel(){stopped=true;}})),ended.signal,64),{name:'AbortError'});assert(stopped);
});

test('one-byte views of mutable large backing buffers are copied immediately without retaining chunk aliases',async()=>{
 const backing=new Uint8Array(1024*1024);let offset=0;
 const body=new ReadableStream<Uint8Array>({pull(controller){if(offset===8192){controller.close();return;}backing[0]=97+offset%26;offset++;controller.enqueue(backing.subarray(0,1));}},{highWaterMark:0});
 const text=await readWorldSourceText(new Response(body),new AbortController().signal,8192);assert.equal(text.length,8192);assert.equal(text,Array.from({length:8192},(_,i)=>String.fromCharCode(97+i%26)).join(''));
});

test('bounded percent-encoded Unicode gateway routes retain their exact identity',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal),route=new URL('https://client.example/api/assets/current');route.searchParams.set('url','https://assets.example/'+ '界'.repeat(4000));const key=route.href;assert(key.length>16384&&key.length<65536);assert.equal(await cache.get(key,64,async()=> 'unicode'),'unicode');assert(cache.stats.bytes>=key.length*2);await assert.rejects(cache.get('x'.repeat(65537),64,async()=> 'bad'),/bounded/);cache.dispose();
});
