// SPDX-License-Identifier: Apache-2.0
// Browser primitives are fault-injected; these are scheduler tests, not browser proof.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nativeTextureAlpha } from '../src/texture-alpha';

test('alpha inspection releases stalled, cancelled and overloaded browser work without accepting stale results', async t => {
  const workers: FakeWorker[] = [];
  class FakeWorker {
    terminated = false;
    posts: { id: number; bitmap: ImageBitmap }[] = [];
    onmessage?: (event: {data:unknown}) => void;
    onerror?: () => void;
    constructor() { workers.push(this); }
    postMessage(value: {id:number;bitmap:ImageBitmap}) { this.posts.push(value); }
    terminate() { this.terminated = true; }
    complete(opaque = 1, intermediate = 0, total = 1) {
      this.onmessage?.({data:{id:this.posts.at(-1)!.id,total,opaque,intermediate}});
    }
  }
  type Bitmap = ImageBitmap & { closed: boolean };
  function bitmap(width=1,height=1): Bitmap {
    const value={width,height,closed:false,close(){this.closed=true;}};
    return value as Bitmap;
  }
  const savedWorker=Object.getOwnPropertyDescriptor(globalThis,'Worker');
  const savedBitmap=Object.getOwnPropertyDescriptor(globalThis,'createImageBitmap');
  let create: () => Promise<ImageBitmap> = async()=>bitmap();
  Object.defineProperty(globalThis,'Worker',{configurable:true,value:FakeWorker});
  Object.defineProperty(globalThis,'createImageBitmap',{configurable:true,value:()=>create()});
  t.after(()=>{
    // Clear the module's owned mock worker before restoring browser globals.
    workers.at(-1)?.onerror?.();
    if(savedWorker)Object.defineProperty(globalThis,'Worker',savedWorker);else Reflect.deleteProperty(globalThis,'Worker');
    if(savedBitmap)Object.defineProperty(globalThis,'createImageBitmap',savedBitmap);else Reflect.deleteProperty(globalThis,'createImageBitmap');
  });
  t.mock.timers.enable({apis:['setTimeout']});
  const image=()=>({width:1,height:1});
  const outcome=(promise:ReturnType<typeof nativeTextureAlpha>)=>promise.then(value=>({value,error:undefined}),error=>({value:undefined,error:error as Error}));
  async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}

  await t.test('never-resolving bitmap creation expires and a late bitmap is closed',async()=>{
    let release!: (value:ImageBitmap)=>void;
    create=()=>new Promise(resolve=>{release=resolve;});
    const stalled=outcome(nativeTextureAlpha({image:image()}));
    create=async()=>bitmap();
    const next=outcome(nativeTextureAlpha({image:image()}));
    t.mock.timers.tick(30000);await flush();
    assert.match((await stalled).error!.message,/exceeded 30 seconds/);
    const owned=workers.at(-1)!;owned.complete();await flush();assert.equal((await next).value,'opaque');
    const late=bitmap();release(late);await flush();assert(late.closed,'A discarded late native bitmap must be closed');
  });
  await t.test('a nonresponsive worker expires and stale worker callbacks cannot corrupt the replacement',async()=>{
    const stalled=outcome(nativeTextureAlpha({image:image()}));await flush();const old=workers.at(-1)!;
    const next=outcome(nativeTextureAlpha({image:image()}));t.mock.timers.tick(30000);await flush();
    assert.match((await stalled).error!.message,/exceeded 30 seconds/);assert(old.terminated);
    const replacement=workers.at(-1)!;assert.notEqual(replacement,old);old.complete();old.onerror?.();
    assert(!replacement.terminated);replacement.complete(0,0,1);await flush();assert.equal((await next).value,'mask');
  });
  await t.test('last-reader cancellation immediately releases a stalled primitive and same-image retry',async()=>{
    let release!: (value:ImageBitmap)=>void;create=()=>new Promise(resolve=>{release=resolve;});
    const source=image(),abort=new AbortController();const cancelled=outcome(nativeTextureAlpha({image:source},abort.signal));
    abort.abort();await flush();assert.equal((await cancelled).error!.name,'AbortError');
    create=async()=>bitmap();const retry=outcome(nativeTextureAlpha({image:source}));await flush();workers.at(-1)!.complete();await flush();assert.equal((await retry).value,'opaque');
    const late=bitmap();release(late);await flush();assert(late.closed);
  });
  await t.test('one cancelled reader cannot terminate a shared active image inspection',async()=>{
    const source=image(),abort=new AbortController();const first=outcome(nativeTextureAlpha({image:source},abort.signal)),second=outcome(nativeTextureAlpha({image:source}));
    await flush();const owned=workers.at(-1)!;const count=owned.posts.length;abort.abort();await flush();assert.equal((await first).error!.name,'AbortError');assert(!owned.terminated);
    owned.complete(0,0,1);await flush();assert.equal((await second).value,'mask');assert.equal(owned.posts.length,count);
  });
  await t.test('32 queued jobs plus 128 backpressure waiters drain in order; actual excess fails explicitly',async()=>{
    const controllers=Array.from({length:162},()=>new AbortController());
    const pending=controllers.map(controller=>outcome(nativeTextureAlpha({image:image()},controller.signal)));await flush();
    assert.match((await pending[161]).error!.message,/Too many pending/);
    controllers[1].abort();await flush();assert.equal((await pending[1]).error!.name,'AbortError');
    const extra=outcome(nativeTextureAlpha({image:image()}));await flush();
    let previous=0;
    for(let i=0;i<161;i++){
      if(i===1)continue;
      const owned=workers.at(-1)!;const id=owned.posts.at(-1)!.id;assert(id>previous,'Backpressure must preserve FIFO admission');previous=id;
      owned.complete();await flush();assert.equal((await pending[i]).value,'opaque');
    }
    workers.at(-1)!.complete();await flush();assert.equal((await extra).value,'opaque');
    const after=outcome(nativeTextureAlpha({image:image()}));await flush();workers.at(-1)!.complete();await flush();assert.equal((await after).value,'opaque');
  });
  await t.test('queued cancellation and decode-budget failure leave the following image usable',async()=>{
    const first=outcome(nativeTextureAlpha({image:image()}));await flush();
    const abort=new AbortController(),cancelled=outcome(nativeTextureAlpha({image:image()},abort.signal));abort.abort();await flush();assert.equal((await cancelled).error!.name,'AbortError');
    workers.at(-1)!.complete();await flush();assert.equal((await first).value,'opaque');
    const oversized=bitmap(8193,8192);create=async()=>oversized;
    const rejected=await outcome(nativeTextureAlpha({image:image()}));assert.match(rejected.error!.message,/Decoded.*64 megapixels/);assert(oversized.closed);
    create=async()=>bitmap();const next=outcome(nativeTextureAlpha({image:image()}));await flush();workers.at(-1)!.complete();await flush();assert.equal((await next).value,'opaque');
  });
});
