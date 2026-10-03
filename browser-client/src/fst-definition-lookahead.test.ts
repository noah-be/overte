// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {orderedFstDefinitions} from './fst-definition-lookahead';
import {WorldSourceTextCache,WorldSourceTextCapacityError} from './world-source-text-cache';
const deferred=<T>()=>{let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
test('one next definition overlaps the current template only; all material applications remain ordered',async()=>{
 const signal=new AbortController(),gate=deferred<void>(),events:string[]=[];
 const run=orderedFstDefinitions([0,1,2],async(e,_s,p)=>{events.push('definition:'+e+':'+p);return e;},async d=>{events.push('template:'+d);if(d===0)await gate.promise;events.push('apply:'+d);},{signal:signal.signal,assertCurrent(){}});
 await tick();assert.deepEqual(events,['definition:0:false','template:0','definition:1:true']);gate.resolve();await run;
 assert.deepEqual(events.filter(e=>e.startsWith('apply')),['apply:0','apply:1','apply:2']);assert(events.indexOf('template:1')>events.indexOf('apply:0'));assert(events.indexOf('definition:2:true')>events.indexOf('apply:0'));
});
test('early speculative rejection is observed immediately but the exact error surfaces at its ordered point',async()=>{
 const gate=deferred<void>(),error=new Error('authored definition refusal'),events:string[]=[];let unhandled=0;const onUnhandled=()=>unhandled++;process.on('unhandledRejection',onUnhandled);
 try{const run=orderedFstDefinitions([0,1],async e=>{if(e===1)throw error;return e;},async e=>{events.push('template:'+e);await gate.promise;events.push('applied:'+e);},{signal:new AbortController().signal,assertCurrent(){}});const terminal=assert.rejects(run,e=>e===error);await tick();assert.equal(unhandled,0);assert.deepEqual(events,['template:0']);gate.resolve();await terminal;assert.deepEqual(events,['template:0','applied:0']);}finally{process.removeListener('unhandledRejection',onUnhandled);}
});
test('earlier template failure cancels only its prefetched text reader; another reader finishes',async()=>{
 const world=new AbortController(),owner=new AbortController(),cache=new WorldSourceTextCache(world.signal),text=deferred<string>(),gate=deferred<void>(),error=new Error('template error');
 const other=cache.get('next',64,()=>text.promise);const run=orderedFstDefinitions([0,1],async(e,s)=>e===0?'first':cache.get('next',64,()=>text.promise,s),async()=>{await gate.promise;throw error;},{signal:owner.signal,assertCurrent(){}});const terminal=assert.rejects(run,e=>e===error);await tick();assert.equal(cache.stats.readers,2);gate.resolve();await terminal;assert.equal(cache.stats.readers,1);text.resolve('second');assert.equal(await other,'second');assert.equal(cache.stats.active,0);cache.dispose();
});
test('owner cancellation and late definition cannot create the next template',async()=>{
 const owner=new AbortController(),next=deferred<number>(),gate=deferred<void>(),templates:number[]=[];let prefetchedSignal:AbortSignal|undefined;
 const run=orderedFstDefinitions([0,1],async(e,s)=>{if(e){prefetchedSignal=s;return next.promise;}return e;},async e=>{templates.push(e);await gate.promise;},{signal:owner.signal,assertCurrent(){}});const terminal=assert.rejects(run,{name:'AbortError'});await tick();owner.abort();gate.resolve();await terminal;assert(prefetchedSignal?.aborted);next.resolve(1);await tick();assert.deepEqual(templates,[0]);
});
test('generation revocation refuses before next application without masking its exact error',async()=>{
 const owner=new AbortController(),gate=deferred<void>(),error=new Error('authority ended');let current=true,calls=0;
 const run=orderedFstDefinitions([0,1],async e=>e,async()=>{calls++;await gate.promise;},{signal:owner.signal,assertCurrent(){if(!current)throw error;}});const terminal=assert.rejects(run,e=>e===error);await tick();current=false;gate.resolve();await terminal;assert.equal(calls,1);
});
test('only typed optional capacity admission retries once; parser HTTP and abort failures are never retried',async()=>{
 for(const error of [new WorldSourceTextCapacityError('pending'),new Error('Too many pending world source texts'),new TypeError('decode'),new DOMException('revoked','AbortError')]){
  const calls:string[]=[],events:string[]=[];const run=orderedFstDefinitions([0,1],async(e,_s,p)=>{calls.push(e+':'+p);if(e&&p)throw error;return e;},async()=>{}, {signal:new AbortController().signal,assertCurrent(){},onEvent:e=>events.push(e)});
  if(error instanceof WorldSourceTextCapacityError){await run;assert.deepEqual(calls,['0:false','1:true','1:false']);assert(events.includes('capacity-fallback'));}else{await assert.rejects(run,e=>e===error);assert.deepEqual(calls,['0:false','1:true']);}
 }
});
test('unchanged text-cache limits issue typed refusal without starting refused producers',async()=>{
 const owner=new AbortController(),cache=new WorldSourceTextCache(owner.signal),waiting=deferred<string>(),jobs:Promise<string>[]=[];let calls=0;
 for(let i=0;i<32;i++)jobs.push(cache.get('route-'+i,64,()=>waiting.promise));
 await assert.rejects(cache.get('extra',64,async()=>{calls++;return 'wrong';}),e=>e instanceof WorldSourceTextCapacityError&&e.capacity==='pending');
 for(let i=32;i<256;i++)jobs.push(cache.get('route-0',64,()=>waiting.promise));
 await assert.rejects(cache.get('route-0',64,async()=>{calls++;return 'wrong';}),e=>e instanceof WorldSourceTextCapacityError&&e.capacity==='readers');assert.equal(calls,0);owner.abort();await Promise.all(jobs.map(p=>assert.rejects(p,{name:'AbortError'})));waiting.resolve('late');
});
test('empty single and out-of-budget entries never create speculative readers',async()=>{
 for(const list of [[],[0]]){let speculative=0;await orderedFstDefinitions(list,async(e,_s,p)=>{if(p)speculative++;return e;},async()=>{}, {signal:new AbortController().signal,assertCurrent(){}});assert.equal(speculative,0);}
 let called=0;await assert.rejects(orderedFstDefinitions(Array.from({length:257},(_,i)=>i),async e=>{called++;return e;},async()=>{}, {signal:new AbortController().signal,assertCurrent(){}}),/entry limit/);assert.equal(called,0);
});
test('whole source owner ending retires speculative readers and never consumes late text',async()=>{
 const world=new AbortController(),reader=new AbortController(),cache=new WorldSourceTextCache(world.signal),waiting=deferred<string>(),gate=deferred<void>(),templates:string[]=[];
 const run=orderedFstDefinitions([0,1],async(e,s)=>e?cache.get('next',64,()=>waiting.promise,s):'first',async d=>{templates.push(d);await gate.promise;},{signal:reader.signal,assertCurrent(){world.signal.throwIfAborted();}});const terminal=assert.rejects(run,{name:'AbortError'});
 await tick();assert.equal(cache.stats.readers,1);world.abort();assert.equal(cache.stats.readers,0);gate.resolve();await terminal;waiting.resolve('late');await tick();assert.deepEqual(templates,['first']);
});
