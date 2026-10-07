// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ModelLoadScheduler} from '../src/model-load-scheduler';
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const deferred=()=>{let resolve!:(value:number)=>void;const promise=new Promise<number>(yes=>resolve=yes);return{promise,resolve};};
test('arrival bursts coalesce one priority pass and never evaluate queued priorities while six slots are busy',async()=>{
  const scheduler=new ModelLoadScheduler(),loads=Array.from({length:12},deferred),started:number[]=[];let evaluations=0;
  const promises=loads.map((load,i)=>scheduler.schedule({priority:()=>{evaluations++;return[i,i];},run:async()=>{started.push(i);return load.promise;}}));
  await flush();assert.equal(scheduler.stats.priorityPasses,1);assert.equal(evaluations,12);assert.deepEqual(started,[0,1,2,3,4,5]);
  const extra=scheduler.schedule({priority:()=>{evaluations++;return[99,99];},run:async()=>99});await flush();assert.equal(evaluations,12);
  loads.forEach((load,i)=>load.resolve(i));assert.deepEqual(await Promise.all(promises),loads.map((_,i)=>i));assert.equal(await extra,99);scheduler.dispose();
});
test('five nearby dispatches retain priority, sixth oldest request prevents starvation, and ties are FIFO',async()=>{
  const scheduler=new ModelLoadScheduler(),started:number[]=[];
  const requests=[100,4,2,3,1,0,2].map((distance,i)=>scheduler.schedule({priority:()=>[distance,distance],run:async()=>{started.push(i);return i;}}));
  await Promise.all(requests);assert.deepEqual(started,[5,4,2,6,3,0,1]);scheduler.dispose();
});
test('queued cancellation removes metadata and cannot start later',async()=>{
  const scheduler=new ModelLoadScheduler({limit:1}),load=deferred(),controller=new AbortController();let ran=false;
  const active=scheduler.schedule({priority:()=>[0,0],run:async()=>load.promise});await flush();
  const cancelled=scheduler.schedule({priority:()=>[1,1],signal:controller.signal,run:async()=>{ran=true;return 1;}});
  const rejection=assert.rejects(cancelled,{name:'AbortError'});controller.abort();await rejection;assert.equal(scheduler.stats.queued,0);load.resolve(0);await active;await flush();assert.equal(ran,false);scheduler.dispose();
});
test('active cancellation rejects immediately, aborts owned work, retains slot until settlement and discards late object',async()=>{
  const scheduler=new ModelLoadScheduler({limit:1}),controller=new AbortController(),load=deferred();let owned:AbortSignal|undefined,discarded=0,second=false;
  const first=scheduler.schedule({priority:()=>[0,0],signal:controller.signal,run:async signal=>{owned=signal;return load.promise;},discard:()=>{discarded++;}});await flush();
  const rejection=assert.rejects(first,{name:'AbortError'});controller.abort();await rejection;assert.equal(owned?.aborted,true);
  const next=scheduler.schedule({priority:()=>[0,0],run:async()=>{second=true;return 2;}});await flush();assert.equal(second,false);assert.equal(scheduler.stats.active,1);
  load.resolve(1);assert.equal(await next,2);assert.equal(discarded,1);scheduler.dispose();
});
test('world revocation cancels active and pending, releases listeners and does not start another load',async()=>{
  const controller=new AbortController(),scheduler=new ModelLoadScheduler({signal:controller.signal,limit:1}),load=deferred();let runs=0;
  const first=scheduler.schedule({priority:()=>[0,0],run:async signal=>{runs++;assert.equal(signal.aborted,false);return load.promise;}});await flush();
  const second=scheduler.schedule({priority:()=>[1,1],run:async()=>{runs++;return 2;}});
  const checks=[assert.rejects(first,{name:'AbortError'}),assert.rejects(second,{name:'AbortError'})];controller.abort();await Promise.all(checks);load.resolve(1);await flush();assert.equal(runs,1);assert.equal(scheduler.stats.active,0);assert.equal(scheduler.stats.queued,0);await assert.rejects(scheduler.schedule({priority:()=>[0,0],run:async()=>0}),{name:'AbortError'});
});
test('resource bound and bad priorities reject honestly without blocking subsequent models',async()=>{
  const scheduler=new ModelLoadScheduler({limit:1,maximumPending:1}),load=deferred();const active=scheduler.schedule({priority:()=>[0,0],run:async()=>load.promise});await flush();
  const bad=scheduler.schedule({priority:()=>[NaN,0],run:async()=>1});await assert.rejects(scheduler.schedule({priority:()=>[0,0],run:async()=>2}),/Too many/);load.resolve(0);await active;await assert.rejects(bad,/Invalid model/);
  assert.equal(await scheduler.schedule({priority:()=>[0,0],run:async()=>3}),3);scheduler.dispose();
});
