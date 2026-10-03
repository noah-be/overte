// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export const CPU_FRAME_SEGMENTS=['setup','physicsPose','avatarCamera','localLights','renderSubmission','diagnostics'] as const;
export type CpuFrameSegment=typeof CPU_FRAME_SEGMENTS[number];
export type CpuFrameReadiness='emptyScene'|'loading'|'modelJobsIdle'|'paused';
type Token=Readonly<object>;
const LIMITS=[.25,.5,1,2,4,8,16,32,64,128,256,512,1000,5000];
interface Stat{count:number;totalMs:number;maxMs:number;histogram:number[]}
const stat=():Stat=>({count:0,totalMs:0,maxMs:0,histogram:Array(LIMITS.length+1).fill(0)});
interface Population{samples:number;total:Stat;segments:Record<CpuFrameSegment,Stat>}
const population=():Population=>({samples:0,total:stat(),segments:Object.fromEntries(CPU_FRAME_SEGMENTS.map(name=>[name,stat()])) as Record<CpuFrameSegment,Stat>});
/** World-lifetime synchronous spans. modelJobsIdle is not asset readiness.
 * No GL query, timer, graph reference, async
 * span, frame-time/FPS claim, or paired GPU population is introduced. */
export class WorldCpuFrameTiming{
 private readonly every:number;private readonly maximum:number;private readonly now:()=>number;
 private ordinal=0;private contextLost=false;private disposed=false;private active?:{token:Token;started:number;last:number;label:CpuFrameReadiness;durations:number[]};
 private readonly populations={emptyScene:population(),loading:population(),modelJobsIdle:population(),paused:population()};
 private readonly counts={observedFrames:0,sampledFrames:0,completedFrames:0,failedFrames:0,invalidFrames:0,orphanedFrames:0};
 private readonly abort=()=>this.dispose();
 constructor(private readonly signal:AbortSignal,options:{sampleEveryFrames?:number;maximumSamples?:number;now?:()=>number}={}){
  this.every=options.sampleEveryFrames??8;this.maximum=options.maximumSamples??2048;this.now=options.now??(()=>performance.now());
  if(!Number.isInteger(this.every)||this.every<1||this.every>120||!Number.isInteger(this.maximum)||this.maximum<1||this.maximum>2048)throw Error('Invalid bounded CPU frame sampling');
  if(signal.aborted)this.disposed=true;else signal.addEventListener('abort',this.abort,{once:true});
 }
 beginFrame(label:CpuFrameReadiness):Token|undefined{
  if(this.disposed||this.contextLost)return;
  if(!Object.hasOwn(this.populations,label))return;
  if(this.active){this.active=undefined;this.counts.orphanedFrames++;}
  if(this.counts.sampledFrames>=this.maximum||this.counts.observedFrames>=this.maximum*this.every)return;
  this.counts.observedFrames++;
  const scheduled=this.ordinal===0;this.ordinal=(this.ordinal+1)%this.every;if(!scheduled)return;
  const started=this.now();if(!Number.isFinite(started)){this.counts.invalidFrames++;return;}
  const token=Object.freeze({});this.active={token,started,last:started,label,durations:Array(CPU_FRAME_SEGMENTS.length).fill(0)};this.counts.sampledFrames++;return token;
 }
 segment(token:Token|undefined,name:CpuFrameSegment):boolean{
  const active=this.active;if(this.disposed||this.contextLost||!token||active?.token!==token)return false;
  const index=CPU_FRAME_SEGMENTS.indexOf(name),at=this.now();
  if(index<0||!Number.isFinite(at)||at<active.last||at-active.started>5000){this.active=undefined;this.counts.invalidFrames++;return false;}
  active.durations[index]+=at-active.last;active.last=at;return true;
 }
 endFrame(token:Token|undefined,completed:boolean):boolean{
  if(!token||this.active?.token!==token)return false;
  if(!completed){this.active=undefined;this.counts.failedFrames++;return false;}
  if(!this.segment(token,'diagnostics'))return false;
  const active=this.active!;this.active=undefined;
  const bucket=this.populations[active.label];bucket.samples++;this.counts.completedFrames++;
  const add=(target:Stat,value:number)=>{target.count++;target.totalMs+=value;target.maxMs=Math.max(target.maxMs,value);const position=LIMITS.findIndex(limit=>value<=limit);target.histogram[position<0?LIMITS.length:position]++;};
  add(bucket.total,active.last-active.started);CPU_FRAME_SEGMENTS.forEach((name,index)=>add(bucket.segments[name],active.durations[index]));return true;
 }
 loseContext(){this.contextLost=true;if(this.active){this.active=undefined;this.counts.orphanedFrames++;}}
 getSnapshot(){
  const copy=(value:Stat)=>({...value,histogram:value.histogram.slice(),meanMs:value.count?value.totalMs/value.count:null});
  return{enabled:true,status:this.disposed?'disposed':this.contextLost?'context-lost':this.counts.sampledFrames>=this.maximum||this.counts.observedFrames>=this.maximum*this.every?'complete':'sampling',sampleEveryFrames:this.every,maximumSamples:this.maximum,maximumObservedFrames:this.maximum*this.every,maximumFrameMs:5000,active:!!this.active,...this.counts,histogramUpperBoundsMs:LIMITS.slice(),populations:Object.fromEntries(Object.entries(this.populations).map(([name,value])=>[name,{samples:value.samples,total:copy(value.total),segments:Object.fromEntries(CPU_FRAME_SEGMENTS.map(segment=>[segment,copy(value.segments[segment])]))}]))};
 }
 dispose(){if(this.disposed)return;this.disposed=true;this.signal.removeEventListener('abort',this.abort);if(this.active){this.active=undefined;this.counts.orphanedFrames++;}}
}
