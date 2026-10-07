// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {GraphicsEnvironmentScan,type GraphicsScanHost,type GraphicsScanCapabilities} from '../src/graphics-environment-scan';
import {GraphicsScanFrames,GraphicsScanCapacityError} from '../src/graphics-scan-frames';
import {DEFAULT_BROWSER_GRAPHICS} from '../shared/browser-graphics.mjs';
function fixture(deadline=5000){
    const abort=new AbortController();const frames=new GraphicsScanFrames(abort.signal);let state={...DEFAULT_BROWSER_GRAPHICS},current=true,visible=true,applied=0;
    class Visibility extends EventTarget{visibilityState:DocumentVisibilityState='visible';}
    const document=new Visibility();const caps:GraphicsScanCapabilities={webgl2:true,contextAntialias:true,maximumTextureDimension:32768,maximumRenderbufferDimension:32768,maximumViewportWidth:32768,maximumViewportHeight:32768,drawingBufferWidth:1280,drawingBufferHeight:800};
    const host:GraphicsScanHost={frames,document,current:()=>current,presentationVisible:()=>visible,settings:()=>({...state}),capabilities:()=>({...caps}),applyResolution:async percent=>{applied++;state={...state,resolutionPercent:percent};return {...state};}};
    const scan=new GraphicsEnvironmentScan(host,deadline);
    return {abort,frames,scan,host,document,caps,get state(){return state;},get applied(){return applied;},set current(value:boolean){current=value;},set visible(value:boolean){visible=value;},set state(value:typeof state){state=value;}};
}
function publish(f:ReturnType<typeof fixture>,interval:number,count:number){for(let i=0;i<=count;i++)f.frames.publish({timestampMs:i*interval,cpuSubmitMs:4,ready:true});}
test('explicit2second completed-render observations report cadence without applying any setting or deriving vendor identity',async()=>{
    const f=fixture();assert.equal(f.frames.active,false);const pending=f.scan.scan();assert.equal(f.frames.active,true);publish(f,20,100);const result=await pending;assert.equal(result.status,'complete');
    if(result.status==='complete'){assert.equal(result.report.observedCadenceHz,50);assert.equal(result.report.elapsedMs,2000);assert.equal(result.report.frameIntervals,100);assert.equal(result.report.p95IntervalMs,20);assert.equal(result.report.meanCpuSubmitMs,4);assert.equal(result.report.defaultRecommendation,'keep-current-settings');assert.equal(result.report.optionalResolutionPercent,null);assert.equal('vendor' in result.report.capabilities,false);}
    assert.equal(f.frames.active,false);assert.equal(f.applied,0);assert.deepEqual(f.state,DEFAULT_BROWSER_GRAPHICS);f.scan.dispose();
});
test('a slow sampled view still recommends keeping current quality and offers only one explicit density step',async()=>{
    const f=fixture();const pending=f.scan.scan();publish(f,50,40);const result=await pending;assert.equal(f.applied,0);assert.equal(result.status,'complete');
    if(result.status==='complete'){assert.equal(result.report.optionalResolutionPercent,90);assert.equal(result.report.defaultRecommendation,'keep-current-settings');result.report.optionalResolutionPercent=10;result.report.settings.fieldOfView=130;}
    const applied=await f.scan.applyOptionalResolution();assert.equal(applied.accepted,true);assert.equal(f.state.resolutionPercent,90);assert.equal(f.state.fieldOfView,70);assert.equal(f.state.localLights,true);assert.equal(f.state.cameraClipping,true);assert.equal((await f.scan.applyOptionalResolution()).accepted,false);f.scan.dispose();
});
test('increased density suggestions remain bounded and10% cannot be lowered',async()=>{
    for(const value of [10,20,200]){const f=fixture();f.state={...f.state,resolutionPercent:value};const pending=f.scan.scan();publish(f,50,40);const r=await pending;assert.equal(r.status,'complete');if(r.status==='complete')assert.equal(r.report.optionalResolutionPercent,value===10?null:value-10);f.scan.dispose();}
});
test('hidden, paused, disconnected, closed or WebGL1 contexts refuse without subscribing',async()=>{
    for(const condition of ['hidden','paused','disconnected','webgl1','closed']){const f=fixture();if(condition==='hidden')f.document.visibilityState='hidden';if(condition==='paused')f.visible=false;if(condition==='disconnected')f.current=false;if(condition==='webgl1')f.caps.webgl2=false;if(condition==='closed')f.scan.dispose();assert.equal((await f.scan.scan()).status,'refused');assert.equal(f.frames.active,false);assert.equal(f.applied,0);f.scan.dispose();}
});
test('visibility and whole-World cancellation settle promptly with no late frame/report/application',async()=>{
    for(const action of ['hide','abort','dispose','cancel']){const f=fixture();const pending=f.scan.scan();publish(f,20,4);if(action==='hide'){f.document.visibilityState='hidden';f.document.dispatchEvent(new Event('visibilitychange'));}if(action==='abort')f.abort.abort();if(action==='dispose')f.scan.dispose();if(action==='cancel')f.scan.cancel();assert.equal((await pending).status,'cancelled');assert.equal(f.frames.active,false);publish(f,50,40);assert.equal((await f.scan.applyOptionalResolution()).accepted,false);f.scan.dispose();}
});
test('permission/session or effective settings changes cancel the sample and suppress old suggestions',async()=>{
    for(const action of ['revision','settings']){const f=fixture();const pending=f.scan.scan();publish(f,20,5);if(action==='revision')f.current=false;else f.state={...f.state,localLights:false};f.frames.publish({timestampMs:120,cpuSubmitMs:1,ready:true});assert.equal((await pending).status,'cancelled');assert.equal((await f.scan.applyOptionalResolution()).accepted,false);f.scan.dispose();}
});
test('loading or malformed source timestamps are inconclusive, not hardware advice',async()=>{
    for(const frame of [{timestampMs:1,cpuSubmitMs:2,ready:false},{timestampMs:NaN,cpuSubmitMs:2,ready:true},{timestampMs:1,cpuSubmitMs:-1,ready:true}]){const f=fixture();const pending=f.scan.scan();f.frames.publish(frame);assert.equal((await pending).status,'inconclusive');assert.equal((await f.scan.applyOptionalResolution()).accepted,false);f.scan.dispose();}
});
test('at most512 intervals and5s default wall wait; no fake RAF or additional renderer is scheduled',async()=>{
    const f=fixture(10);const pending=f.scan.scan();publish(f,1,512);assert.equal((await pending).status,'inconclusive');assert.equal(f.frames.active,false);f.scan.dispose();
    const absent=fixture(10);const wait=absent.scan.scan();assert.equal((await wait).status,'inconclusive');assert.equal(absent.frames.active,false);absent.scan.dispose();
});
test('one source owner only; duplicate scanner request or second controller cannot evict the original reader',async()=>{
    const f=fixture();const pending=f.scan.scan();assert.equal((await f.scan.scan()).status,'refused');const second=new GraphicsEnvironmentScan(f.host);assert.equal((await second.scan()).status,'refused');assert.equal(f.frames.active,true);publish(f,20,100);assert.equal((await pending).status,'complete');second.dispose();f.scan.dispose();
});
test('source listener exception cannot stop original renderer, and obsolete disposer cannot remove a fresh owner',()=>{
    const a=new AbortController();const source=new GraphicsScanFrames(a.signal);let cancelled=0,observed=0;
    const remove=source.subscribe(()=>{throw Error('private listener');},()=>cancelled++);assert.throws(()=>source.subscribe(()=>{},()=>{}),GraphicsScanCapacityError);
    assert.doesNotThrow(()=>source.publish({timestampMs:1,cpuSubmitMs:1,ready:true}));assert.equal(cancelled,1);assert.equal(source.active,false);
    source.subscribe(()=>observed++,()=>{});remove();source.publish({timestampMs:2,cpuSubmitMs:1,ready:true});assert.equal(observed,1);source.dispose();assert.equal(source.active,false);a.abort();
});
test('current/capability getter exceptions and unknown/private fields produce fixed outputs only',async()=>{
    const f=fixture();f.host.current=()=>{throw Error('private account details');};const r=await f.scan.scan();assert.equal(r.status,'refused');assert(!JSON.stringify(r).includes('private'));f.scan.dispose();
    const bad=fixture();bad.host.capabilities=()=>({...bad.caps,maximumTextureDimension:Infinity,secret:'private'});assert.equal((await bad.scan.scan()).status,'refused');assert.equal(bad.frames.active,false);bad.scan.dispose();
});
test('failure in final current read still resolves and releases reader rather than stranding a completed waiter',async()=>{
    const f=fixture();let calls=0;f.host.current=()=>{if(++calls===103)throw Error('private final read');return true;};const pending=f.scan.scan();publish(f,20,100);const r=await pending;assert.equal(r.status,'refused');assert.equal(f.frames.active,false);f.scan.dispose();
});
test('a rejected or stale optional apply never reports success and captures actual effective results',async()=>{
    const f=fixture();let pending=f.scan.scan();publish(f,50,40);await pending;f.current=false;assert.equal((await f.scan.applyOptionalResolution()).accepted,false);assert.equal(f.applied,0);f.current=true;
    pending=f.scan.scan();publish(f,50,40);await pending;f.host.applyResolution=async()=>({...f.state});assert.equal((await f.scan.applyOptionalResolution()).accepted,false);f.scan.dispose();
});

test('pausing the current presentation cancels one observer but allows a later explicit scan',async()=>{
 const f=fixture();const one=f.scan.scan();f.frames.cancel();assert.equal((await one).status,'cancelled');const two=f.scan.scan();publish(f,20,100);assert.equal((await two).status,'complete');f.scan.dispose();
});
test('a completed optional suggestion expires after30seconds and cannot be applied with an older scene observation',async()=>{
 const f=fixture();let time=0;const scanner=new GraphicsEnvironmentScan(f.host,5000,()=>time);const p=scanner.scan();publish(f,50,40);await p;time=30001;assert.equal((await scanner.applyOptionalResolution()).accepted,false);assert.equal(f.applied,0);scanner.dispose();f.scan.dispose();
});

test('a pending ordinary native confirmation excludes another scan, including duplicate apply and cancelled-owner intervals',async()=>{
 const f=fixture();let complete!:(value:typeof f.state)=>void;
 f.host.applyResolution=()=>new Promise(resolve=>{complete=resolve;});
 try{
  const sample=f.scan.scan();publish(f,50,40);assert.equal((await sample).status,'complete');
  const applying=f.scan.applyOptionalResolution();assert.equal(f.frames.active,false);
  assert.equal((await f.scan.scan()).status,'refused');
  assert.equal((await f.scan.applyOptionalResolution()).accepted,false);
  // A refused second Apply must not release the first Apply's owner flag.
  assert.equal((await f.scan.scan()).status,'refused');
  f.scan.cancel();assert.equal((await f.scan.scan()).status,'refused');
  f.state={...f.state,resolutionPercent:90};complete({...f.state});
  assert.equal((await applying).accepted,false);
  const next=f.scan.scan();assert.equal(f.frames.active,true);publish(f,20,100);assert.equal((await next).status,'complete');
 }finally{f.scan.dispose();}
});
test('confirmation rejection and disposed ownership settle without retaining a scan exclusion or a frame reader',async()=>{
 for(const action of ['reject','dispose']){
  const f=fixture();let reject!:(value:Error)=>void,resolve!:(value:typeof f.state)=>void;
  f.host.applyResolution=()=>new Promise((yes,no)=>{resolve=yes;reject=no;});
  const p=f.scan.scan();publish(f,50,40);await p;
  const applying=f.scan.applyOptionalResolution();assert.equal((await f.scan.scan()).status,'refused');
  if(action==='dispose'){f.scan.dispose();resolve({...f.state,resolutionPercent:90});}else reject(Error('Private driver detail'));
  const result=await applying;assert.equal(result.accepted,false);assert(!result.message.includes('Private'));
  assert.equal(f.frames.active,false);
  if(action==='reject'){const next=f.scan.scan();publish(f,20,100);assert.equal((await next).status,'complete');}
  else assert.equal((await f.scan.scan()).status,'refused');
  f.scan.dispose();
 }
});
test('exact old scan admission expression reproduces a new observation while the authorized prior Apply still completes',async()=>{
 const [{readFile},{transformSync},{createContext,runInContext},graphics,frameModule]=await Promise.all([import('node:fs/promises'),import('esbuild'),import('node:vm'),import('../shared/browser-graphics.mjs'),import('../src/graphics-scan-frames')]);
 const source=await readFile(new URL('../src/graphics-environment-scan.ts',import.meta.url),'utf8');
 const guarded='this.cancelPending||this.applying||this.serial';assert.equal(source.split(guarded).length,2);
 const negative=source.replace(guarded,'this.cancelPending||this.serial');
 const module={exports:{} as any};const context=createContext({module,exports:module.exports,require:(name:string)=>name.includes('browser-graphics.mjs')?graphics:frameModule,setTimeout,clearTimeout,performance});
 runInContext(transformSync(negative,{loader:'ts',format:'cjs'}).code,context);
 const f=fixture();let complete!:(value:typeof f.state)=>void;f.host.applyResolution=()=>new Promise(resolve=>{complete=resolve;});
 const old=new module.exports.GraphicsEnvironmentScan(f.host);
 try{
  const sample=old.scan();publish(f,50,40);assert.equal((await sample).status,'complete');
  const applying=old.applyOptionalResolution();const next=old.scan();assert.equal(f.frames.active,true);
  f.state={...f.state,resolutionPercent:90};complete({...f.state});assert.equal((await applying).accepted,false);
  f.frames.publish({timestampMs:1,cpuSubmitMs:1,ready:true});assert.equal((await next).status,'cancelled');
  assert.equal(f.state.resolutionPercent,90);
 }finally{old.dispose();f.scan.dispose();}
});
