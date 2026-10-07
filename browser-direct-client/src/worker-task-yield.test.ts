// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {WorkerTaskYield} from './worker-task-yield';
function observed(){const channel=new MessageChannel();const closed=[0,0];for(const [index,port]of[channel.port1,channel.port2].entries()){const original=port.close.bind(port);port.close=()=>{closed[index]++;original();};}return{channel,closed};}
test('Actual MessageChannel crosses a task boundary and releases both ports on normal completion',async()=>{
  const {channel,closed}=observed(),yielding=new WorkerTaskYield({channelFactory:()=>channel}),events:string[]=[];
  const pending=yielding.yield().then(()=>events.push('task'));events.push('sync');await Promise.resolve();assert.deepEqual(events,['sync']);await pending;
  await yielding.yield();yielding.close();yielding.close();assert.deepEqual(events,['sync','task']);assert.deepEqual(closed,[1,1]);await assert.rejects(yielding.yield(),{name:'AbortError'});
});
test('Abort rejects the pending continuation and closes real ports exactly once',async()=>{
  const {channel,closed}=observed(),controller=new AbortController(),yielding=new WorkerTaskYield({signal:controller.signal,channelFactory:()=>channel});
  const pending=yielding.yield();controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.deepEqual(closed,[1,1]);yielding.close();assert.deepEqual(closed,[1,1]);
});
test('A revoked worker never allocates a channel and overlapping continuations stay bounded',async()=>{
  const controller=new AbortController();controller.abort();let created=0;const revoked=new WorkerTaskYield({signal:controller.signal,channelFactory:()=>{created++;return new MessageChannel();}});await assert.rejects(revoked.yield(),{name:'AbortError'});assert.equal(created,0);
  const yielding=new WorkerTaskYield(),first=yielding.yield();await assert.rejects(yielding.yield(),/Only one/);await first;yielding.close();
});
test('Port startup and message-delivery failure close ownership and cannot leave a pending job',async()=>{
  const {channel,closed}=observed();channel.port2.postMessage=()=>{throw Error('Continuation delivery failed');};const yielding=new WorkerTaskYield({channelFactory:()=>channel});await assert.rejects(yielding.yield(),/delivery failed/);assert.deepEqual(closed,[1,1]);
  const failed=new WorkerTaskYield({channelFactory:()=>{throw Error('Channel refused');}});await assert.rejects(failed.yield(),/Channel refused/);await assert.rejects(failed.yield(),{name:'AbortError'});
});
