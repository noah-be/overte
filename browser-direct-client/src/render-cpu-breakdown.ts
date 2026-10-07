// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {RenderDispatchAttributionFrame,DISPATCH_ATTRIBUTION_LIMITS,type DispatchAttributionRecord,type AttributionReason} from './render-dispatch-attribution';
import type {Camera,Scene,WebGLRenderer} from 'three';
export type RenderReadiness='emptyScene'|'loading'|'modelJobsIdle';
const labels=['sceneMatrices','cameraMatrices','sceneBeforeHook','drawDispatch','renderRemainder','total'] as const;
type Label=typeof labels[number];
const bounds=[.25,.5,1,2,4,8,16,32,64,128,256,512,1000,5000] as const;
const phases=()=>Object.fromEntries(labels.map(label=>[label,{count:0,totalMs:0,maxMs:0,histogram:Array(bounds.length+1).fill(0) as number[]}])) as Record<Label,ReturnType<typeof metric>>;
function metric(){return {count:0,totalMs:0,maxMs:0,histogram:Array(bounds.length+1).fill(0) as number[]};}
function add(target:ReturnType<typeof metric>,value:number){target.count++;target.totalMs+=value;target.maxMs=Math.max(target.maxMs,value);const index=bounds.findIndex(bound=>value<=bound);target.histogram[index<0?bounds.length:index]++;}
/** Resolve a public method through bounded data descriptors without invoking accessors. */
function readDiagnosticMethod(target:object,key:string):Function{let current:object|null=target;for(let depth=0;current&&depth<6;depth++,current=Object.getPrototypeOf(current)){const descriptor=Object.getOwnPropertyDescriptor(current,key);if(descriptor){if(!('value'in descriptor)||typeof descriptor.value!=='function')throw Error('Unsupported diagnostic method descriptor');return descriptor.value;}}throw Error('Unsupported diagnostic method chain');}
interface Frame{live:boolean;invalid:boolean;clockCalls:number;calls:number;depth:number;last:number;start:number;firstDispatch?:number;afterSceneHook?:number;firstListInterval?:number;values:Record<Label,number>;stack:{child:number}[]}
interface Options{now?:()=>number;sampleEveryFrames?:number;dispatchAttribution?:boolean}
/** Default-off, sampled public-call CPU diagnostics. Never bypasses a renderer
 * operation. Wrappers exist only during the synchronous measured callback, are
 * instance-scoped, and restore exact descriptors in finally. Private projectObject
 * is not exposed by Three: the residual includes traversal/culling/sort, skeleton
 * preparation, lights, output passes, driver scheduling and unassigned work.
 * No GPU query, getError/getParameter/readPixels/finish or scene state mutation. */
export class RenderCpuBreakdown{
 private readonly attributionEnabled:boolean;private attributionCpuMs=0;private attributionSamples=0;private attributionCapacitySkippedSamples=0;private readonly attributionPopulations:Record<RenderReadiness,{samples:number;completeSamples:number;censoredSamples:number;reasons:Partial<Record<AttributionReason,number>>;completeTotals:Partial<Record<keyof DispatchAttributionRecord,number>>;partialTotals:Partial<Record<keyof DispatchAttributionRecord,number>>;totals:Partial<Record<keyof DispatchAttributionRecord,number>>}>={emptyScene:{samples:0,completeSamples:0,censoredSamples:0,reasons:{},completeTotals:{},partialTotals:{},totals:{}},loading:{samples:0,completeSamples:0,censoredSamples:0,reasons:{},completeTotals:{},partialTotals:{},totals:{}},modelJobsIdle:{samples:0,completeSamples:0,censoredSamples:0,reasons:{},completeTotals:{},partialTotals:{},totals:{}}};
 private readonly now:()=>number;private readonly every:number;private ordinal=0;private active=false;private disposed=false;private contextLost=false;
 private readonly abort=()=>this.dispose();
 private readonly populations=Object.fromEntries((['emptyScene','loading','modelJobsIdle'] as const).map(label=>[label,{samples:0,phases:phases(),drawDispatchCalls:metric(),reportedDrawCalls:metric(),reportedTriangles:metric(),afterSceneHookToFirstDispatch:metric(),firstDispatchObserved:0,clockCalls:0}])) as Record<RenderReadiness,{samples:number;phases:ReturnType<typeof phases>;drawDispatchCalls:ReturnType<typeof metric>;reportedDrawCalls:ReturnType<typeof metric>;reportedTriangles:ReturnType<typeof metric>;afterSceneHookToFirstDispatch:ReturnType<typeof metric>;firstDispatchObserved:number;clockCalls:number}>;
 private readonly counts={observedFrames:0,scheduledFrames:0,completedFrames:0,failedRenders:0,invalidFrames:0,capacitySkippedFrames:0,reentrantFrames:0,installationRefusals:0,foreignHookChanges:0};
 constructor(private readonly signal:AbortSignal,options:Options={}){this.attributionEnabled=options.dispatchAttribution===true;this.now=options.now??(()=>performance.now());this.every=options.sampleEveryFrames??8;if(!Number.isInteger(this.every)||this.every<1||this.every>120)throw Error('Invalid render CPU diagnostic sample interval');if(signal.aborted)this.disposed=true;else signal.addEventListener('abort',this.abort,{once:true});}
 measure<T>(renderer:WebGLRenderer,scene:Scene,camera:Camera,readiness:RenderReadiness,render:()=>T):T{
  if(this.disposed||this.contextLost)return render();
  if(this.active){this.counts.reentrantFrames++;return render();}
  if(this.counts.observedFrames>=16384||this.counts.scheduledFrames>=2048){this.counts.capacitySkippedFrames++;return render();}
  this.counts.observedFrames++;const scheduled=this.ordinal===0;this.ordinal=(this.ordinal+1)%this.every;if(!scheduled)return render();
  if(!Object.hasOwn(this.populations,readiness)){this.counts.invalidFrames++;return render();}
  this.counts.scheduledFrames++;this.active=true;
  const frame:Frame={live:true,invalid:false,clockCalls:0,calls:0,depth:0,last:0,start:0,values:Object.fromEntries(labels.map(label=>[label,0])) as Record<Label,number>,stack:[]};
  const attribution=this.attributionEnabled&&this.attributionSamples<512&&this.attributionCpuMs<500?new RenderDispatchAttributionFrame(this.now,Math.min(2,500-this.attributionCpuMs)):undefined;
  if(this.attributionEnabled&&!attribution)this.attributionCapacitySkippedSamples++;
  const restorers:(()=>void)[]=[];
  const read=()=>{frame.clockCalls++;try{const value=this.now();if(!Number.isFinite(value)||value<frame.last){frame.invalid=true;return frame.last;}frame.last=value;return value;}catch{frame.invalid=true;return frame.last;}};
  const install=(target:object,key:string,label:Label)=>{
   const own=Object.getOwnPropertyDescriptor(target,key),original=readDiagnosticMethod(target,key);
   if(typeof original!=='function'||own&&(!('value'in own)||own.writable===false))throw Error('Diagnostic boundary is not an owned writable method');
   const wrapper=function(this:unknown,...args:unknown[]){
    if(!frame.live)return Reflect.apply(original,this,args);
    if(label==='drawDispatch'){
     if(this===renderer)attribution?.observeDraw(args[2],args[3],args[4]);else attribution?.censor('unsupported-input');
     frame.calls++;if(frame.calls>4096){frame.invalid=true;return Reflect.apply(original,this,args);}
    }
    if(frame.depth>=8){frame.invalid=true;return Reflect.apply(original,this,args);}
    const started=read();
    if(label==='drawDispatch'&&frame.firstDispatch===undefined){frame.firstDispatch=started;if(frame.afterSceneHook!==undefined)frame.firstListInterval=started-frame.afterSceneHook;}
    const slot={child:0};frame.stack.push(slot);frame.depth++;
    try{return Reflect.apply(original,this,args);}
    finally{
     if(label==='drawDispatch')attribution?.finishDraw();
     const ended=read(),elapsed=ended-started;frame.depth--;frame.stack.pop();
     if(elapsed<slot.child||elapsed<0)frame.invalid=true;else frame.values[label]+=elapsed-slot.child;
     const parent=frame.stack.at(-1);if(parent)parent.child+=elapsed;
     if(label==='sceneBeforeHook'&&frame.firstDispatch===undefined)frame.afterSceneHook=ended;
    }
   };
   Object.defineProperty(target,key,own?{...own,value:wrapper}:{value:wrapper,writable:true,configurable:true,enumerable:false});
   restorers.push(()=>{try{if(Object.getOwnPropertyDescriptor(target,key)?.value!==wrapper)throw Error('Foreign diagnostic boundary replacement');if(own)Object.defineProperty(target,key,own);else if(!Reflect.deleteProperty(target,key))throw Error('Foreign diagnostic boundary descriptor change');}catch{frame.invalid=true;this.counts.foreignHookChanges++;}});
  };
  let installed=false,completed=false;
  try{
   try{install(scene,'updateMatrixWorld','sceneMatrices');install(camera,'updateMatrixWorld','cameraMatrices');install(scene,'onBeforeRender','sceneBeforeHook');install(renderer,'renderBufferDirect','drawDispatch');installed=true;}
   catch{this.counts.installationRefusals++;frame.live=false;for(const restore of restorers.splice(0).reverse())restore();}
   if(!installed)return render();
   if(attribution){
    try{
     const gl=Reflect.apply(readDiagnosticMethod(renderer,'getContext'),renderer,[]) as WebGL2RenderingContext,key='useProgram',own=Object.getOwnPropertyDescriptor(gl,key),original=readDiagnosticMethod(gl,key);
     if(typeof original!=='function'||own&&(!('value'in own)||own.writable===false))throw Error('Unwritable program boundary');
     const wrapper=function(this:WebGL2RenderingContext,...args:Parameters<WebGL2RenderingContext['useProgram']>){const result=Reflect.apply(original,this,args);if(frame.live){if(this===gl)attribution.observeProgram(args[0]);else attribution.censor('unsupported-input');}return result;};
     Object.defineProperty(gl,key,own?{...own,value:wrapper}:{value:wrapper,writable:true,configurable:true,enumerable:false});
     restorers.push(()=>{try{if(Object.getOwnPropertyDescriptor(gl,key)?.value!==wrapper)throw Error('Foreign program boundary');if(own)Object.defineProperty(gl,key,own);else if(!Reflect.deleteProperty(gl,key))throw Error('Foreign program descriptor');}catch{attribution.censor('foreign-hook');}});
    }catch{attribution.censor('installation-refused');}
   }
   frame.start=read();
   try{const result=render();completed=true;return result;}
   catch(error){this.counts.failedRenders++;throw error;}
   finally{frame.values.total=read()-frame.start;}
  }finally{
   frame.live=false;
   try{for(const restore of restorers.reverse())restore();}
   finally{
    this.active=false;
    if(attribution){const reason:AttributionReason|undefined=this.disposed?'aborted':this.contextLost?'context-lost':!installed?'installation-refused':!completed?'render-failed':frame.invalid?'timing-invalid':undefined;const record=attribution.finish(reason),population=this.attributionPopulations[readiness];this.attributionSamples++;this.attributionCpuMs+=record.cpuMs;population.samples++;if(record.complete)population.completeSamples++;else population.censoredSamples++;if(record.reason)population.reasons[record.reason]=(population.reasons[record.reason]??0)+1;for(const [key,value]of Object.entries(record))if(typeof value==='number'){const typed=key as keyof DispatchAttributionRecord;population.totals[typed]=(population.totals[typed]??0)+value;const exact=record.complete?population.completeTotals:population.partialTotals;exact[typed]=(exact[typed]??0)+value;}}
    if(installed&&completed){
     const assigned=frame.values.sceneMatrices+frame.values.cameraMatrices+frame.values.sceneBeforeHook+frame.values.drawDispatch;
     frame.values.renderRemainder=frame.values.total-assigned;
     if(this.disposed||this.contextLost||frame.invalid||frame.values.total>5000||frame.values.renderRemainder<0){this.counts.invalidFrames++;}
     else{
      const population=this.populations[readiness];population.samples++;this.counts.completedFrames++;
      for(const label of labels)add(population.phases[label],frame.values[label]);
      add(population.drawDispatchCalls,frame.calls);population.clockCalls+=frame.clockCalls;
      const calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;
      if(Number.isFinite(calls)&&calls>=0&&calls<=1e9)add(population.reportedDrawCalls,calls);
      if(Number.isFinite(triangles)&&triangles>=0&&triangles<=1e9)add(population.reportedTriangles,triangles);
      if(frame.firstDispatch!==undefined)population.firstDispatchObserved++;
      if(frame.firstListInterval!==undefined&&frame.firstListInterval>=0)add(population.afterSceneHookToFirstDispatch,frame.firstListInterval);
     }
    }
   }
  }
 }
 loseContext(){this.contextLost=true;}
 snapshot(){const copy=(value:ReturnType<typeof metric>)=>({...value,histogram:[...value.histogram],meanMs:value.count?value.totalMs/value.count:null});return {enabled:true,dispatchAttribution:{enabled:this.attributionEnabled,samples:this.attributionSamples,capacitySkippedSamples:this.attributionCapacitySkippedSamples,cpuMs:this.attributionCpuMs,limits:{...DISPATCH_ATTRIBUTION_LIMITS},scope:'sampled-renderBufferDirect-call-entries',entryEvidence:'call-entries-not-confirmed-GL-draws',programEvidence:'actual-useProgram-calls',materialEvidence:'identity-only-not-value-equivalence',populations:Object.fromEntries(Object.entries(this.attributionPopulations).map(([key,value])=>[key,{...value,reasons:{...value.reasons},completeTotals:{...value.completeTotals},partialTotals:{...value.partialTotals},totals:{...value.totals}}]))},status:this.disposed?'disposed':this.contextLost?'context-lost':'sampling',sampleEveryFrames:this.every,maximumSamples:2048,maximumObservedFrames:16384,maximumBoundaryCallsPerSample:4096,maximumFrameMs:5000,active:this.active,...this.counts,histogramUpperBoundsMs:[...bounds],populations:Object.fromEntries(Object.entries(this.populations).map(([label,p])=>[label,{samples:p.samples,phases:Object.fromEntries(labels.map(key=>[key,copy(p.phases[key])])),drawDispatchCalls:{samples:p.drawDispatchCalls.count,totalCalls:p.drawDispatchCalls.totalMs,maxCalls:p.drawDispatchCalls.maxMs,meanCalls:p.drawDispatchCalls.count?p.drawDispatchCalls.totalMs/p.drawDispatchCalls.count:null},reportedDrawCalls:{samples:p.reportedDrawCalls.count,totalCalls:p.reportedDrawCalls.totalMs,maxCalls:p.reportedDrawCalls.maxMs,meanCalls:p.reportedDrawCalls.count?p.reportedDrawCalls.totalMs/p.reportedDrawCalls.count:null},reportedTriangles:{samples:p.reportedTriangles.count,totalTriangles:p.reportedTriangles.totalMs,maxTriangles:p.reportedTriangles.maxMs,meanTriangles:p.reportedTriangles.count?p.reportedTriangles.totalMs/p.reportedTriangles.count:null},afterSceneHookToFirstDispatch:copy(p.afterSceneHookToFirstDispatch),firstDispatchObserved:p.firstDispatchObserved,clockCalls:p.clockCalls}]))};}
 dispose(){if(this.disposed)return;this.disposed=true;this.signal.removeEventListener('abort',this.abort);}
}
