// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {sizeSystemFirefoxWindow} from './system-firefox.mjs';
const target={width:1280,height:900},density=5/3;
const timeout=()=>Object.assign(Error('Controlled public wait timeout'),{name:'TimeoutError'});
const plain=value=>JSON.parse(JSON.stringify(value));
function fixture({already=false,wm='quantized',viewport='pending',source=sizeSystemFirefoxWindow.toString(),clockTimers=false,requested=target}={}){
 let now=0,requests=0,waits=0,disposals=0,closed=false,pendingReject;
 const trace=[],state={innerWidth:1280,innerHeight:already?900:956,devicePixelRatio:density};
 let bounds={width:1332,height:1092};
 let nextTimer=0;const timers=new Map();
 const schedule=clockTimers?(callback,delay)=>{const id=++nextTimer;timers.set(id,{callback,at:now+delay});return id;}:setTimeout;
 const cancel=clockTimers?id=>timers.delete(id):clearTimeout;
 const context=vm.createContext({...state,Date:{now:()=>now},setTimeout:schedule,clearTimeout:cancel});
 const run=vm.runInContext('('+source+')',context);
 const browser={
  async setWindowBounds(id,value){assert.equal(id,'owned-window');trace.push(['bounds',plain(value)]);if(value.height===undefined)return;requests++;bounds={width:value.width,height:value.height};
   if(wm==='exact')context.innerHeight=900;
   else if(wm==='carry'){bounds.height=value.height-1;context.innerHeight=value.height===1037?900:899;}
   else if(wm==='slow'){now=10000;context.innerHeight=899;}
   else context.innerHeight=value.height===1037?901:899;
  },
  async getWindowBounds(id){assert.equal(id,'owned-window');trace.push(['getBounds']);return{...bounds};},
  async close(){closed=true;trace.push(['close']);pendingReject?.(Object.assign(Error('Owned target closed'),{name:'TargetCloseError'}));},
 };
 const page={
  async windowId(){trace.push(['windowId']);return'owned-window';},
  async evaluate(fn){trace.push(['evaluate']);return fn();},
  async waitForFunction(fn,options,size){waits++;trace.push(['wait',options.timeout,plain(size)]);assert.ok(options.timeout>0&&options.timeout<=10000-now);
   if(fn(size))return{async dispose(){disposals++;}};
   now+=options.timeout;throw timeout();
  },
  setViewport(value){trace.push(['viewport',plain(value)]);assert.equal(closed,false);if(viewport!=='float32-density')assert.equal(Object.hasOwn(value,'deviceScaleFactor'),false,'Explicit DPR emulation quantizes the genuine native double to Float32 in Firefox; actual native density is independently required');
   if(viewport==='forbidden')throw Error('Unexpected viewport fallback');
   if(viewport==='error')return Promise.reject(Object.assign(Error('Unrelated protocol refusal'),{name:'ProtocolError'}));
   if(viewport!=='no-effect'){context.innerWidth=value.width;context.innerHeight=value.height;}
   if(viewport==='wrong-density')context.devicePixelRatio=1;
   if(viewport==='float32-density'&&Object.hasOwn(value,'deviceScaleFactor'))context.devicePixelRatio=Math.fround(value.deviceScaleFactor);
   if(viewport==='fulfilled')return Promise.resolve();
   if(viewport==='timeout')return Promise.reject(Object.assign(Error('browsingContext.setViewport timed out. Increase protocolTimeout.'),{name:'ProtocolError'}));
   return new Promise((_,reject)=>{pendingReject=reject;});
  },
 };
 return{run:()=>run(browser,page,requested),browser,page,context,trace,clock:()=>now,
  expire:()=>{const [id,timer]=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];timers.delete(id);now=timer.at;timer.callback();},timerCount:()=>timers.size,
  setTime:value=>{now=value;},requests:()=>requests,waits:()=>waits,disposals:()=>disposals};
}

test('an already exact owned viewport and first exact WM result require no further resize or viewport override',async()=>{
 for(const options of [{already:true},{wm:'exact'}]){const f=fixture({...options,viewport:'forbidden'});const result=plain(await f.run());assert.equal(result.method,'public-window');assert.equal(result.viewportAcknowledgementAtReturn,'not-requested');assert.equal(result.actual.density,density);assert.equal(f.requests(),options.already?0:1);assert.equal(f.trace.some(value=>value[0]==='viewport'),false);assert.equal(f.disposals(),options.already?0:1);}
});

test('carried requested bounds repair one-pixel WM rounding, whereas a fresh-bounds or single-attempt negative control repeats the lost correction',async()=>{
 const actual=fixture({wm:'carry',viewport:'forbidden'});await actual.run();assert.deepEqual(actual.trace.filter(value=>value[0]==='bounds'&&value[1].height).map(value=>value[1].height),[1036,1037]);
 for(const [expression,replacement]of [['requestedBounds?.height??bounds.height','bounds.height'],['attempts < 3','attempts < 1']]){
  const source=sizeSystemFirefoxWindow.toString();assert.equal(source.split(expression).length,2);const old=fixture({wm:'carry',viewport:'forbidden',source:source.replace(expression,replacement)});await assert.rejects(old.run(),/Unexpected viewport fallback/);assert.equal(old.requests(),replacement==='attempts < 1'?1:3);
 }
});

test('recorded899-to901 WM quantization falls back to actual exact effect at unchanged native DPR despite a pending ACK',async()=>{
 const f=fixture();const result=plain(await f.run());assert.equal(f.requests(),3);assert.equal(result.method,'public-viewport-effect');assert.equal(result.viewportAcknowledgementAtReturn,'pending');assert.deepEqual(result.actual,{width:1280,height:900,density});assert.ok(result.durationMs<10000);assert.equal(f.disposals(),1);
 const previous=f.trace.length,unhandled=[];const onUnhandled=value=>unhandled.push(value);process.on('unhandledRejection',onUnhandled);
 try{await f.browser.close();await new Promise(resolve=>setImmediate(resolve));assert.equal(f.trace.length,previous+1);assert.deepEqual(unhandled,[]);assert.equal(result.viewportAcknowledgementAtReturn,'pending','A later target-close rejection never invents an ACK');}
 finally{process.off('unhandledRejection',onUnhandled);}
});

test('a fixed inner viewport refuses negative WM corrections before RPC and requires exact fallback effect at native density',async()=>{
 const exercise=async source=>{
  const f=fixture({source,viewport:'fulfilled',requested:{width:360,height:560}}),requested=[];
  f.browser.getWindowBounds=async()=>({width:460,height:700});
  f.browser.setWindowBounds=async(_id,value)=>{
   if(value.width===undefined)return;
   requested.push(plain(value));
   if(!Number.isSafeInteger(value.width)||value.width<=0)throw Error('Public window rejected negative width');
  };
  return{f,requested,pending:f.run()};
 };
 const current=sizeSystemFirefoxWindow.toString(),actual=await exercise(current);
 const result=plain(await actual.pending);
 assert.equal(actual.requested.length,0,'The first computed width is -460; no invalid window RPC is authorized');
 assert.equal(result.method,'public-viewport-effect');
 assert.deepEqual(result.actual,{width:360,height:560,density});
 assert(result.durationMs<10000);
 const guard='if (![requestedBounds.width,requestedBounds.height].every(value=>Number.isSafeInteger(value)&&value>0)) break;';
 assert.equal(current.split(guard).length,2);
 const original=await exercise(current.replace(guard,''));
 await assert.rejects(original.pending,/Public window rejected negative width/);
 assert.equal(original.requested.length,1);
 assert.equal(original.f.trace.some(value=>value[0]==='viewport'),false);
});

test('fulfilled and timeout acknowledgements are distinguished but both still require observed exact dimensions/density',async()=>{
 for(const [viewport,ack]of [['fulfilled','fulfilled'],['timeout','timed-out']]){const f=fixture({viewport});const result=plain(await f.run());assert.equal(result.viewportAcknowledgementAtReturn,ack);assert.deepEqual(result.actual,{width:1280,height:900,density});}
 const wrong=fixture({viewport:'wrong-density'});try{await assert.rejects(wrong.run(),error=>error.name==='TimeoutError');assert.equal(wrong.clock(),10000);}finally{await wrong.browser.close();}
});

test('never-exact effect uses only remaining original deadline and3WM attempts; exhaustion prevents late fallback allocation',async()=>{
 const never=fixture({viewport:'no-effect'});try{await assert.rejects(never.run(),error=>error.name==='TimeoutError');assert.equal(never.requests(),3);assert.equal(never.clock(),10000);assert.deepEqual(never.trace.filter(value=>value[0]==='wait').map(value=>value[1]),[500,500,500,8500]);}finally{await never.browser.close();}
 const slow=fixture({wm:'slow'});await assert.rejects(slow.run(),/within ten seconds/);assert.equal(slow.requests(),1);assert.equal(slow.trace.some(value=>value[0]==='viewport'),false);
});

test('ordinary non-timeout protocol errors propagate immediately without subsequent mutation or suppressed failure',async()=>{
 const wm=fixture(),error=Error('Unexpected window API failure');wm.page.waitForFunction=async()=>{throw error;};await assert.rejects(wm.run(),value=>value===error);assert.equal(wm.requests(),1);assert.equal(wm.trace.some(value=>value[0]==='viewport'),false);
 const fallback=fixture({viewport:'error'});await assert.rejects(fallback.run(),error=>error.name==='ProtocolError'&&error.message==='Unrelated protocol refusal');assert.equal(fallback.requests(),3);
});

test('invalid requested dimensions perform no page/window mutation or fallback RPC',async()=>{
 for(const viewport of [null,{}, {width:0,height:900},{width:1280,height:NaN},{width:1280.5,height:900},{width:1280,height:Infinity}]){
  const f=fixture();await assert.rejects(sizeSystemFirefoxWindow(f.browser,f.page,viewport),/Invalid actual Firefox window dimensions/);assert.deepEqual(f.trace,[]);
 }
});

test('effect/owner identity is independently rechecked and late successful handles are released after an earlier RPC error',async()=>{
 const f=fixture({viewport:'fulfilled'});let ids=0;f.page.windowId=async()=>++ids===1?'owned-window':'different-window';await assert.rejects(f.run(),/owned Firefox viewport or native density changed/);
 const late=fixture({viewport:'error'});let resolveEffect,dispose=0;const original=late.page.waitForFunction;late.page.waitForFunction=(fn,options,size)=>options.timeout<=500?original(fn,options,size):new Promise(resolve=>{resolveEffect=resolve;});
 await assert.rejects(late.run(),/Unrelated protocol refusal/);resolveEffect({async dispose(){dispose++;}});await new Promise(resolve=>setImmediate(resolve));assert.equal(dispose,1,'A losing pending effect observer never leaks its returned handle');
});

test('a stalled public window call cannot exceed the original10sec or launch a late resize after rejection',async()=>{
 const f=fixture({clockTimers:true});let rejectBounds;f.browser.getWindowBounds=()=>new Promise((_,reject)=>{rejectBounds=reject;});
 const pending=f.run();const rejected=assert.rejects(pending,/within ten seconds/);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.timerCount(),1);f.expire();await rejected;assert.equal(f.clock(),10000);assert.equal(f.timerCount(),0);assert.equal(f.requests(),0);
 const length=f.trace.length,unhandled=[],observe=value=>unhandled.push(value);process.on('unhandledRejection',observe);
 try{rejectBounds(Error('Late public API rejection'));await new Promise(resolve=>setImmediate(resolve));assert.equal(f.trace.length,length);assert.deepEqual(unhandled,[]);}finally{process.off('unhandledRejection',observe);}
});

test('an operation delayed in the microtask queue beyond the deadline never touches the owned page/window',async()=>{
 let now=0,timer=0;const context={Date:{now:()=>now},setTimeout(){now=10000;return ++timer;},clearTimeout(){}};
 const run=vm.runInNewContext('('+sizeSystemFirefoxWindow.toString()+')',context);
 const untouched=new Proxy({},{get(){throw Error('An expired operation must not access the owned API');}});
 await assert.rejects(run(untouched,untouched,target),/within ten seconds/);
});


test('recorded explicit-native DPR Float32 rounding is refused; the same public viewport with default density preserves the original native double',async()=>{
 const native=fixture({viewport:'float32-density'});assert.equal((await native.run()).actual.density,density);
 const current=sizeSystemFirefoxWindow.toString(),expression='page.setViewport({width:expected.width,height:expected.height})';assert.equal(current.split(expression).length,2);
 const old=fixture({viewport:'float32-density',source:current.replace(expression,'page.setViewport({width:expected.width,height:expected.height,deviceScaleFactor:expected.density})')});
 await assert.rejects(old.run(),error=>error.name==='TimeoutError');assert.equal(old.context.devicePixelRatio,1.6666666269302368);assert.notEqual(old.context.devicePixelRatio,density);assert.equal(old.requests(),3);
});
