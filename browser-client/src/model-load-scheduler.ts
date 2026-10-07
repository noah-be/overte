// SPDX-License-Identifier: Apache-2.0
export type ModelPriority = readonly [distance:number, centerDistance:number];
interface Task<T=unknown> {
  sequence:number; priority:()=>ModelPriority; run:(signal:AbortSignal)=>Promise<T>; discard?:(value:T)=>void;
  signal?:AbortSignal; onAbort?:()=>void; controller:AbortController; active:boolean; settled:boolean;
  resolve:(value:T)=>void; reject:(reason:unknown)=>void;
}
const abortError=()=>new DOMException('Model loading was cancelled','AbortError');
/** Coalesces arrivals, keeps six owned loads, and dispatches the oldest queued
 * request every sixth slot. Cancellation never frees an unsettled active slot. */
export class ModelLoadScheduler {
  private readonly queued:Task[]=[];private readonly active=new Set<Task>();
  private readonly signal?:AbortSignal;private readonly limit:number;private readonly maximumPending:number;
  private scheduled=false;private closed=false;private sequence=0;private dispatches=0;private priorityPasses=0;
  private readonly onAbort=()=>this.dispose();
  constructor(options:{signal?:AbortSignal;limit?:number;maximumPending?:number}={}){
    this.signal=options.signal;this.limit=options.limit??6;this.maximumPending=options.maximumPending??100000;
    if(!Number.isSafeInteger(this.limit)||this.limit<1||this.limit>6||!Number.isSafeInteger(this.maximumPending)||this.maximumPending<1||this.maximumPending>100000)throw Error('Invalid model scheduler resource limit');
    if(this.signal?.aborted)this.closed=true;else this.signal?.addEventListener('abort',this.onAbort,{once:true});
  }
  get stats(){return{active:this.active.size,queued:this.queued.length,dispatches:this.dispatches,priorityPasses:this.priorityPasses,disposed:this.closed};}
  schedule<T>(options:{priority:()=>ModelPriority;run:(signal:AbortSignal)=>Promise<T>;signal?:AbortSignal;discard?:(value:T)=>void}):Promise<T>{
    if(this.closed||options.signal?.aborted)return Promise.reject(abortError());
    if(this.queued.length>=this.maximumPending)return Promise.reject(Error('Too many pending model loads'));
    return new Promise<T>((resolve,reject)=>{
      const task:Task<T>={...options,sequence:this.sequence++,controller:new AbortController(),active:false,settled:false,resolve,reject};
      task.onAbort=()=>this.cancel(task as Task);task.signal?.addEventListener('abort',task.onAbort,{once:true});
      this.queued.push(task as Task);this.requestDrain();
    });
  }
  private requestDrain():void{
    // Do not enqueue a microtask for every entity arriving while all slots run.
    if(this.scheduled||this.closed||!this.queued.length||this.active.size>=this.limit)return;
    this.scheduled=true;queueMicrotask(()=>{this.scheduled=false;this.drain();});
  }
  private drain():void{
    if(this.closed||!this.queued.length||this.active.size>=this.limit)return;
    // Compute dynamic distance once per pending request, not in each comparator.
    this.priorityPasses++;const distances=new Map<Task,ModelPriority>();
    for(const task of [...this.queued]){
      try{const priority=task.priority();if(priority.length!==2||priority.some(value=>!Number.isFinite(value)||value<0))throw Error('Invalid model loading priority');distances.set(task,priority);}
      catch(error){this.finish(task,error);this.removeQueued(task);}
    }
    this.queued.sort((a,b)=>{const x=distances.get(a)!,y=distances.get(b)!;return x[0]-y[0]||x[1]-y[1]||a.sequence-b.sequence;});
    while(!this.closed&&this.active.size<this.limit&&this.queued.length){
      let index=0;if((this.dispatches+1)%6===0)for(let i=1;i<this.queued.length;i++)if(this.queued[i].sequence<this.queued[index].sequence)index=i;
      const task=this.queued.splice(index,1)[0];task.active=true;this.active.add(task);this.dispatches++;
      void Promise.resolve().then(()=>{
        if(this.closed||task.controller.signal.aborted)throw abortError();return task.run(task.controller.signal);
      }).then(value=>{
        if(this.closed||task.controller.signal.aborted){task.discard?.(value);this.finish(task,abortError());}
        else this.finish(task,undefined,value);
      },error=>this.finish(task,error)).catch(error=>this.finish(task,error)).finally(()=>{this.active.delete(task);this.requestDrain();});
    }
  }
  private removeQueued(task:Task):void{const index=this.queued.indexOf(task);if(index>=0)this.queued.splice(index,1);}
  private finish(task:Task,error?:unknown,value?:unknown):void{
    if(task.settled)return;task.settled=true;if(task.onAbort)task.signal?.removeEventListener('abort',task.onAbort);
    if(error!==undefined)task.reject(error);else task.resolve(value);
  }
  private cancel(task:Task):void{task.controller.abort();if(!task.active)this.removeQueued(task);this.finish(task,abortError());this.requestDrain();}
  dispose():void{
    if(this.closed)return;this.closed=true;this.signal?.removeEventListener('abort',this.onAbort);
    for(const task of [...this.queued,...this.active])this.cancel(task);this.queued.length=0;
  }
}
