// SPDX-License-Identifier: Apache-2.0
/** Exclusive leaf wall intervals, never CPU/GPU time or proven critical path. */
export const MODEL_RESIDENCE_STAGES = ['queued','loader-other','mapping-metadata','prepared-fbx','fbx-parse','original-image-dependencies','native-alpha','fst-definition','fst-template','post-loader-other','geometry-commit','graphics-publication'] as const;
export type ModelResidenceStage = typeof MODEL_RESIDENCE_STAGES[number];
export type ModelResidenceTerminal = 'completed'|'refused'|'cancelled'|'censored';
export const FST_WALL_OBSERVATIONS=['map-readers','alpha'] as const;
type FstWaitStage=typeof FST_WALL_OBSERVATIONS[number];
type FstCount='mapping'|'template-attempt'|'template-completed'|'map-reader';
interface FstDetail { mappingCount:number;templateAttempts:number;templateCompleted:number;mapReaderAttempts:number;countsCensored:boolean;waitsCensored:boolean;waits:Record<FstWaitStage,{started:number;completed:number;totalWallMs:number;maxWallMs:number}> }
interface Row { fst?:FstDetail; ordinal:number; started:number; dispatched?:number; loaderEnded?:number; finished:number; terminal:ModelResidenceTerminal; stages:number[] }
const noop=()=>{};
const MAX_FST_COUNTS=256,MAX_FST_WAITS=256;
function fstDetail():FstDetail{return {mappingCount:0,templateAttempts:0,templateCompleted:0,mapReaderAttempts:0,countsCensored:false,waitsCensored:false,waits:{'map-readers':{started:0,completed:0,totalWallMs:0,maxWallMs:0},alpha:{started:0,completed:0,totalWallMs:0,maxWallMs:0}}};}
const MAX_OWNERS=512,MAX_ROWS=64,MAX_DEPTH=24,MAX_BYTES=128*1024,MAX_DURATION=300000;
export class ModelSlotResidence {
 private owners=new WeakMap<object,ModelResidenceToken>();private active=new Set<ModelResidenceToken>();private rows:Row[]=[];
 private count=0;private closed=false;private origin?:number;private clockInvalid=0;private refusedOwners=0;private clockReads=0;
 private readonly totals=new Float64Array(MODEL_RESIDENCE_STAGES.length);private readonly terminals={completed:0,refused:0,cancelled:0,censored:0};
 private readonly abort=()=>this.dispose();
 constructor(private signal:AbortSignal,private clock:()=>number=()=>performance.now()) { signal.addEventListener('abort',this.abort,{once:true});if(signal.aborted)this.dispose(); }
 read():number|undefined { this.clockReads=Math.min(1000000,this.clockReads+1);try {const now=this.clock();if(Number.isFinite(now)&&now>=0)return now;}catch{}this.clockInvalid=Math.min(1000000,this.clockInvalid+1);return undefined; }
 start(owner:object,signal:AbortSignal):ModelResidenceToken|undefined {
  if(this.closed||signal.aborted||this.owners.has(owner))return;
  if(this.count>=MAX_OWNERS){this.refusedOwners=Math.min(1000000,this.refusedOwners+1);return;}
  const now=this.read();if(now===undefined)return;
  this.origin??=now;const token=new ModelResidenceToken(this,++this.count,now,signal);this.owners.set(owner,token);this.active.add(token);return token;
 }
 get(owner:object){return this.owners.get(owner);}
 retire(token:ModelResidenceToken,row:Row):void {
  if(!this.active.delete(token))return;this.terminals[row.terminal]++;
  for(let i=0;i<this.totals.length;i++)this.totals[i]+=row.stages[i];
  this.rows.push(row);if(this.rows.length>MAX_ROWS)this.rows.shift();
 }
 snapshot(){
  const origin=this.origin??0;
  const recent=this.rows.map(row=>({ordinal:row.ordinal,terminal:row.terminal,startedMs:row.started-origin,finishedMs:row.finished-origin,residenceMs:row.finished-row.started,
   queueMs:row.dispatched===undefined?null:row.dispatched-row.started,loaderRunMs:row.loaderEnded===undefined||row.dispatched===undefined?null:row.loaderEnded-row.dispatched,
   fst:row.fst?{...row.fst,scope:'Actual FST calls for this owner; template cohort/alpha wall observations may overlap. Not HTTP requests or exclusive CPU/GPU time.',waits:Object.fromEntries(FST_WALL_OBSERVATIONS.map(stage=>[stage,{...row.fst!.waits[stage]}]))}:undefined,
   exclusiveLeafWallMs:Object.fromEntries(MODEL_RESIDENCE_STAGES.map((stage,i)=>[stage,row.stages[i]]))}));
  const result={enabled:true,scope:'This World only; exclusive leaf wall labels, not CPU/GPU time or proven critical-path attribution',maximumOwners:MAX_OWNERS,maximumRetainedRows:MAX_ROWS,maximumNesting:MAX_DEPTH,maximumSerializedBytes:MAX_BYTES,
   owners:this.count,active:this.active.size,refusedOwners:this.refusedOwners,clockInvalid:this.clockInvalid,clockReads:this.clockReads,retainedRows:recent.length,earlierRowsOmitted:Math.max(0,this.count-this.active.size-recent.length),closed:this.closed,terminals:{...this.terminals},
   exclusiveLeafWallMs:Object.fromEntries(MODEL_RESIDENCE_STAGES.map((stage,i)=>[stage,this.totals[i]])),recent};
  // Fixed rows/fields above normally fit comfortably. Keep the report bounded
  // even if a future schema grows; no runtime admission or owner changes.
  if(new TextEncoder().encode(JSON.stringify(result)).byteLength>MAX_BYTES)return {...result,recent:[],retainedRows:0,reportCensored:true};
  return {...result,reportCensored:false};
 }
 dispose(){if(this.closed)return;this.closed=true;this.signal.removeEventListener('abort',this.abort);for(const token of [...this.active])token.finish('cancelled');this.owners=new WeakMap();}
}
export class ModelResidenceToken {
 private ended=false;private last:number;private leaf:ModelResidenceStage='queued';private stack:{stage:ModelResidenceStage;key:object}[]=[];private stages=new Float64Array(MODEL_RESIDENCE_STAGES.length);
 private fst?:FstDetail;
 private dispatched?:number;private loaderEnded?:number;private readonly abort=()=>this.finish('cancelled');
 constructor(private owner:ModelSlotResidence,private ordinal:number,private started:number,private signal:AbortSignal){this.last=started;signal.addEventListener('abort',this.abort,{once:true});}
 private charge(now:number):boolean {const elapsed=now-this.last;if(elapsed<0||elapsed>MAX_DURATION)return false;this.stages[MODEL_RESIDENCE_STAGES.indexOf(this.leaf)]+=elapsed;this.last=now;return true;}
 private time():number|undefined {if(this.ended)return;const now=this.owner.read();if(now===undefined||!this.charge(now)){this.finish('censored',this.last);return;}return now;}
 dispatch(){const now=this.time();if(now===undefined)return;this.dispatched=now;this.leaf='loader-other';}
 /** Fixed per-owner counters; never read model/material/source data. */
 fstCount(kind:FstCount):void {
  if(this.ended)return;
  const field=kind==='mapping'?'mappingCount':kind==='template-attempt'?'templateAttempts':kind==='template-completed'?'templateCompleted':kind==='map-reader'?'mapReaderAttempts':undefined;
  if(!field)return;
  const detail=this.fst??=fstDetail();if(detail[field]>=MAX_FST_COUNTS){detail.countsCensored=true;return;}detail[field]++;
 }
 /** Independent intervals deliberately never touch exclusive-leaf state or its stack. */
 fstWait(stage:FstWaitStage):()=>void {
  if(this.ended||!FST_WALL_OBSERVATIONS.includes(stage))return noop;
  const detail=this.fst??=fstDetail(),wait=detail.waits[stage];
  if(wait.started>=MAX_FST_WAITS){detail.waitsCensored=true;return noop;}
  const started=this.owner.read();if(started===undefined){detail.waitsCensored=true;return noop;}wait.started++;
  let done=false;
  return()=>{if(done||this.ended)return;done=true;const ended=this.owner.read();
   if(ended===undefined||ended<started||ended-started>MAX_DURATION){detail.waitsCensored=true;return;}
   const elapsed=ended-started;wait.completed++;wait.totalWallMs+=elapsed;wait.maxWallMs=Math.max(wait.maxWallMs,elapsed);
  };
 }
 loaderFinished(){const now=this.time();if(now===undefined)return;this.loaderEnded=now;this.leaf='post-loader-other';}
 span(stage:ModelResidenceStage):()=>void {
  if(this.ended)return noop;
  if(!MODEL_RESIDENCE_STAGES.includes(stage)||this.stack.length>=MAX_DEPTH){this.finish('censored');return noop;}
  if(this.time()===undefined)return noop;
  const key={};this.stack.push({stage:this.leaf,key});this.leaf=stage;let stopped=false;
  return()=>{if(stopped||this.ended)return;stopped=true;const top=this.stack[this.stack.length-1];if(top?.key!==key){this.finish('censored');return;}if(this.time()===undefined)return;this.leaf=top.stage;this.stack.pop();};
 }
 finish(terminal:ModelResidenceTerminal,at?:number):void {
  if(this.ended)return;const now=at??this.owner.read();if(now!==undefined&&!this.charge(now))terminal='censored';
  if(this.fst&&FST_WALL_OBSERVATIONS.some(stage=>this.fst!.waits[stage].started!==this.fst!.waits[stage].completed))this.fst.waitsCensored=true;
  this.ended=true;this.signal.removeEventListener('abort',this.abort);this.stack.length=0;
  this.owner.retire(this,{fst:this.fst,ordinal:this.ordinal,started:this.started,dispatched:this.dispatched,loaderEnded:this.loaderEnded,finished:this.last,terminal:now===undefined?'censored':terminal,stages:Array.from(this.stages)});
 }
}
