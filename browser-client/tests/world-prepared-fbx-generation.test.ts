// SPDX-License-Identifier: Apache-2.0
// Actual World methods and PreparedFbxCache; no browser, network or renderer.
import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserWorld} from '../src/world';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import type {PreparedBakedFbx} from '../src/model-fbx-pool';

function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return{promise,resolve};}
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
const prepared=(byte:number):PreparedBakedFbx=>({buffer:Uint8Array.of(byte).buffer,phases:{materialBindingsMs:0,decodeMs:0}});
const outcome=<T>(promise:Promise<T>)=>promise.then(value=>({value,error:undefined}),error=>({value:undefined,error:error as Error}));
const hooks=['invalidateSourceTexts','invalidateModelParses'] as const;

function fixture(){
  const world:any=Object.create(BrowserWorld.prototype),abort=new AbortController();
  let generation=1,approved=true,byte=1,fetches=0,preparations=0,resolutions=0;
  const producerSignals:AbortSignal[]=[];
  let responseGate:ReturnType<typeof deferred<Response>>|undefined,prepareGate:ReturnType<typeof deferred<PreparedBakedFbx>>|undefined;
  const previousFetch=globalThis.fetch;
  globalThis.fetch=async(_input,init)=>{fetches++;producerSignals.push(init!.signal as AbortSignal);return responseGate?responseGate.promise:new Response(Uint8Array.of(byte));};
  Object.assign(world,{abort,disposed:false,preparedFbxEpoch:0,preparedFbx:new PreparedFbxCache({signal:abort.signal}),
    options:{resolveAsset(){resolutions++;return 'https://owned.invalid/api/assets/same-session?url=owned.fbx';},captureAssetAuthority(){const captured=generation;return{generation:String(captured),assertCurrent(){if(!approved||generation!==captured)throw new DOMException('Approval ended','AbortError');}};}},
    fbxPreparePool:{async prepare(buffer:ArrayBuffer){preparations++;return prepareGate?prepareGate.promise:{buffer,phases:{materialBindingsMs:0,decodeMs:0}};}},
    embeddedFbxCounts:{preparations:0,convertedImages:0,extractedBytes:0,skippedOversize:0,skippedUnsupported:0},recordLoadDuration(){},recordLoadPhase(){}});
  return{world,abort,producerSignals,counts:()=>({fetches,preparations,resolutions}),
    read:(signal=abort.signal)=>world.loadPreparedFbx('atp:/owned.fbx',signal) as Promise<PreparedBakedFbx&{cacheHit:boolean}>,
    revoke(){approved=false;},reapprove(){generation++;approved=true;byte=2;},
    holdResponse(){responseGate=deferred<Response>();return responseGate;},
    holdPreparation(){prepareGate=deferred<PreparedBakedFbx>();return prepareGate;},
    releasePreparation(){prepareGate=undefined;},
    close(){abort.abort();world.preparedFbx.dispose();globalThis.fetch=previousFetch;}};
}

test('World prepared FBX ready hits retain same-approval dedupe and borrowed byte identity',async()=>{
  const f=fixture();try{const first=await f.read(),next=await f.read();assert.equal(next.buffer,first.buffer);assert.equal(next.cacheHit,true);assert.equal(f.counts().fetches,1);assert.equal(f.counts().preparations,1);}finally{f.close();}
});

for(const hook of hooks){
  test(`World ${hook} drops ready bytes before same-route reapproval`,async()=>{
    const f=fixture();try{const old=await f.read();f.revoke();f.world[hook]();f.reapprove();const current=await f.read();assert.equal(new Uint8Array(current.buffer)[0],2);assert.notEqual(current.buffer,old.buffer);assert.equal(current.cacheHit,false);assert.equal(f.counts().fetches,2);}finally{f.close();}
  });
  test(`World ${hook} rejects pending readers immediately and ignores late old producer`,async()=>{
    const f=fixture();try{const gate=f.holdPreparation(),oldCache=f.world.preparedFbx,old=outcome(f.read());await tick();assert.equal(f.counts().preparations,1);f.revoke();f.world[hook]();assert.equal((await old).error!.name,'AbortError');assert.equal(f.producerSignals[0].aborted,true);assert.equal(oldCache.stats.readers,0);assert.equal(oldCache.stats.active,0);assert.equal(oldCache.stats.bytes,0);
      f.reapprove();f.releasePreparation();const fresh=await f.read();gate.resolve(prepared(99));await tick();assert.equal((await f.read()).buffer,fresh.buffer);assert.equal(new Uint8Array(fresh.buffer)[0],2);assert.equal(oldCache.stats.ready,1);assert.equal(oldCache.stats.bytes,1);assert.equal(f.counts().fetches,2);
    }finally{f.close();}
  });
  test(`World ${hook} rejects a queued ready delivery before publication`,async()=>{
    const f=fixture();try{await f.read();const queued=outcome(f.read());f.world[hook]();assert.equal((await queued).error!.name,'AbortError');assert.equal(f.world.preparedFbx.stats.readers,0);}finally{f.close();}
  });
}

test('World captured generation rollover invalidates ready bytes without a separate callback',async()=>{
  const f=fixture();try{await f.read();f.reapprove();const fresh=await f.read();assert.equal(new Uint8Array(fresh.buffer)[0],2);assert.equal(f.counts().fetches,2);}finally{f.close();}
});
test('World refuses revoked authority before resolving or fetching an FBX route',async()=>{
  const f=fixture();try{f.revoke();await assert.rejects(f.read(),{name:'AbortError'});assert.deepEqual(f.counts(),{fetches:0,preparations:0,resolutions:0});}finally{f.close();}
});
test('World rechecks approval after an awaited FBX response before preparation',async()=>{
  const f=fixture();try{const gate=f.holdResponse(),read=outcome(f.read());await tick();f.revoke();gate.resolve(new Response(Uint8Array.of(1)));assert.equal((await read).error!.name,'AbortError');assert.equal(f.counts().preparations,0);assert.equal(f.world.preparedFbx.stats.ready,0);}finally{f.close();}
});
test('World late preparation cannot publish or cache bytes after captured approval ends',async()=>{
  const f=fixture();try{const gate=f.holdPreparation(),read=outcome(f.read());await tick();f.revoke();gate.resolve(prepared(1));assert.equal((await read).error!.name,'AbortError');assert.equal(f.world.preparedFbx.stats.ready,0);assert.equal(f.world.preparedFbx.stats.readers,0);}finally{f.close();}
});
test('World rechecks approval after awaited response bytes before preparation',async()=>{
  const f=fixture();try{const gate=f.holdResponse(),body=deferred<ArrayBuffer>(),response=new Response(Uint8Array.of(1));response.arrayBuffer=()=>body.promise;const read=outcome(f.read());await tick();gate.resolve(response);await tick();f.revoke();body.resolve(Uint8Array.of(1).buffer);assert.equal((await read).error!.name,'AbortError');assert.equal(f.counts().preparations,0);}finally{f.close();}
});
test('World epoch rejects a resolved ready result revoked before its awaiting continuation',async()=>{
  const f=fixture();try{await f.read();const read=outcome(f.read());queueMicrotask(()=>f.world.invalidateModelParses());assert.equal((await read).error!.name,'AbortError');assert.equal(f.world.preparedFbx.stats.ready,0);}finally{f.close();}
});
test('World rechecks approval on asynchronous ready-cache delivery',async()=>{
  const f=fixture();try{await f.read();const read=outcome(f.read());f.revoke();assert.equal((await read).error!.name,'AbortError');assert.equal(f.counts().fetches,1);}finally{f.close();}
});
test('World one-reader cancellation preserves a joined current-authority producer',async()=>{
  const f=fixture();try{const gate=f.holdPreparation(),reader=new AbortController(),a=outcome(f.read(reader.signal)),b=f.read();await tick();assert.equal(f.counts().fetches,1);reader.abort();assert.equal((await a).error!.name,'AbortError');assert.equal(f.producerSignals[0].aborted,false);gate.resolve(prepared(7));assert.equal(new Uint8Array((await b).buffer)[0],7);assert.equal((await f.read()).cacheHit,true);}finally{f.close();}
});
test('World disposal signal refuses prepared FBX access before route resolution',async()=>{
  const f=fixture();try{f.abort.abort();await assert.rejects(f.read(),{name:'AbortError'});assert.equal(f.counts().resolutions,0);}finally{f.close();}
});
test('World first metadata read does not revoke a same-approval prepared FBX producer',async()=>{
  const f=fixture();try{const gate=f.holdPreparation(),read=f.read();await tick();await f.world.sourceText('https://owned.invalid/material.json','material',64,f.abort.signal);assert.equal(f.producerSignals[0].aborted,false);gate.resolve(prepared(3));assert.equal(new Uint8Array((await read).buffer)[0],3);}finally{f.close();}
});
test('World metadata generation rollover revokes old prepared bytes without losing current metadata',async()=>{
  const f=fixture();try{await f.read();f.reapprove();const text=await f.world.sourceText('https://owned.invalid/material.json','material',64,f.abort.signal);assert.equal(text,String.fromCharCode(2));const read=await f.read();assert.equal(new Uint8Array(read.buffer)[0],2);assert.equal(f.world.sourceTexts.stats.ready,1);assert.equal(f.counts().fetches,3);}finally{f.close();}
});
test('actual prepared cache invalidation preserves a fresh reader admitted by an old producer abort listener',async()=>{
  const cache=new PreparedFbxCache(),gate=deferred<PreparedBakedFbx>();let fresh:Promise<PreparedBakedFbx>|undefined;
  const old=outcome(cache.get('owned',signal=>{signal.addEventListener('abort',()=>{fresh=cache.get('owned',async()=>prepared(2));},{once:true});return gate.promise;}));
  try{await tick();cache.invalidate();assert.equal((await old).error!.name,'AbortError');assert(fresh);assert.equal(new Uint8Array((await fresh).buffer)[0],2);gate.resolve(prepared(1));await tick();assert.equal(cache.stats.ready,1);assert.equal(cache.stats.readers,0);}finally{cache.dispose();}
});
test('World rollover publishes its generation before abort listeners and never stomps a nested newer approval',async()=>{
  const f=fixture();try{const gate=f.holdPreparation(),old=outcome(f.read());await tick();let nested:ReturnType<typeof f.read>|undefined;f.producerSignals[0].addEventListener('abort',()=>{f.reapprove();f.releasePreparation();nested=f.read();},{once:true});f.reapprove();const superseded=outcome(f.read());assert.equal((await old).error!.name,'AbortError');assert.equal((await superseded).error!.name,'AbortError');assert(nested);const fresh=await nested;assert.equal(f.world.preparedFbxGeneration,'3');gate.resolve(prepared(99));await tick();assert.equal((await f.read()).buffer,fresh.buffer);assert.equal(f.counts().fetches,2);}finally{f.close();}
});
