// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// https://registry.khronos.org/webgl/extensions/EXT_disjoint_timer_query_webgl2/
interface TimerExtension {TIME_ELAPSED_EXT:number;GPU_DISJOINT_EXT:number;QUERY_COUNTER_BITS_EXT:number}
interface Options {maxPending?:number;timeoutMs?:number;now?:()=>number;onWarning?:(message:string)=>void}
interface Entry {query:WebGLQuery;started:number}

/** Optional, bounded GPU diagnostics only. No shader, resolution or renderer
 * state is changed. Poll from a later animation task; never spin or gl.finish.
 * QUERY_RESULT is read only after AVAILABLE and a valid disjoint check.
 */
export class GpuTimeObserver {
  readonly supported:boolean;
  readonly timeoutMs:number;
  private readonly extension?:TimerExtension;
  private readonly maxPending:number;
  private readonly now:()=>number;
  private active?:Entry;
  private pending:Entry[]=[];
  private disposed=false;
  private contextLost=false;
  private warned=false;
  private readonly released=new WeakSet<WebGLQuery>();
  private readonly stats={completed:0,totalGpuMs:0,maxGpuMs:0,peakQueries:0,skippedCapacity:0,skippedExternal:0,disjointDropped:0,timedOut:0,failed:0};
  constructor(private readonly gl:WebGL2RenderingContext,private readonly options:Options={}){
    this.maxPending=options.maxPending??8;const requestedTimeout=options.timeoutMs??5000;
    if(!Number.isInteger(this.maxPending)||this.maxPending<1||this.maxPending>16||!Number.isFinite(requestedTimeout)||requestedTimeout<1||requestedTimeout>10000)throw Error('Invalid bounded GPU diagnostic options');
    this.now=options.now??(()=>performance.now());let extension:TimerExtension|undefined,bits=0;
    try{extension=gl.getExtension('EXT_disjoint_timer_query_webgl2') as TimerExtension|null??undefined;if(extension)bits=Number(gl.getQuery(extension.TIME_ELAPSED_EXT,extension.QUERY_COUNTER_BITS_EXT));}catch{extension=undefined;}
    this.supported=!!extension&&Number.isInteger(bits)&&bits>=32&&bits<=64;
    this.extension=this.supported?extension:undefined;
    // Refuse queries before the finite counter can wrap, even on 32-bit GPUs.
    this.timeoutMs=this.supported?Math.min(requestedTimeout,Math.floor((2**Math.min(bits,53)-1)/1e6/2)):requestedTimeout;
  }
  private warn(){if(this.warned)return;this.warned=true;try{this.options.onWarning?.('Optional GPU timing was unavailable or invalid; CPU/frame measurements remain available.');}catch{/* Diagnostics must not interrupt rendering. */}}
  private release(entry:Entry,active=false){
    if(this.released.has(entry.query))return;this.released.add(entry.query);
    try{if(active&&!this.gl.isContextLost()&&this.gl.getQuery(this.extension!.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY)===entry.query)this.gl.endQuery(this.extension!.TIME_ELAPSED_EXT);}catch{this.stats.failed++;}
    try{this.gl.deleteQuery(entry.query);}catch{this.stats.failed++;}
  }
  private discard(){if(this.active){this.release(this.active,true);this.active=undefined;}for(const entry of this.pending)this.release(entry);this.pending=[];}
  begin():boolean{
    if(this.disposed||!this.extension)return false;
    try{if(this.gl.getQuery(this.extension.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY)!==null&&!this.active){this.stats.skippedExternal++;return false;}}catch{this.stats.failed++;this.warn();return false;}
    this.poll();if(this.contextLost||this.active)return false;
    if(this.pending.length>=this.maxPending){this.stats.skippedCapacity++;return false;}
    try{
      if(this.gl.getQuery(this.extension.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY)!==null){this.stats.skippedExternal++;return false;}
      const started=this.now();if(!Number.isFinite(started))throw Error('Invalid GPU diagnostic clock');
      const query=this.gl.createQuery();if(!query)throw Error('GPU query allocation was refused');
      const entry={query,started};this.active=entry;
      this.gl.beginQuery(this.extension.TIME_ELAPSED_EXT,query);
      if(this.gl.getQuery(this.extension.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY)!==query)throw Error('GPU query ownership was refused');
      this.stats.peakQueries=Math.max(this.stats.peakQueries,this.pending.length+1);return true;
    }catch{this.stats.failed++;if(this.active)this.release(this.active,true);this.active=undefined;this.warn();return false;}
  }
  end():boolean{
    if(!this.active||!this.extension)return false;
    const entry=this.active;this.active=undefined;
    try{
      if(this.gl.isContextLost()){this.contextLost=true;this.release(entry);this.discard();return false;}
      if(this.gl.getQuery(this.extension.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY)!==entry.query)throw Error('Owned GPU query was ended outside the observer');
      this.gl.endQuery(this.extension.TIME_ELAPSED_EXT);this.pending.push(entry);return true;
    }catch{this.stats.failed++;this.release(entry,true);this.warn();return false;}
  }
  poll():void{
    if(this.disposed||!this.extension)return;
    try{
      if(this.gl.isContextLost()){this.contextLost=true;this.discard();return;}
      const current=this.gl.getQuery(this.extension.TIME_ELAPSED_EXT,this.gl.CURRENT_QUERY);
      if(current!==null&&current!==this.active?.query){
        // Reading the global disjoint flag can consume another profiler's
        // state. Leave foreign query ownership/results alone; expire only our
        // handles from the local monotonic deadline.
        this.stats.skippedExternal++;const now=this.now();
        if(this.active){this.stats.failed++;this.release(this.active);this.active=undefined;}
        this.pending=this.pending.filter(entry=>{if(!Number.isFinite(now)||now<entry.started||now-entry.started>=this.timeoutMs){this.stats.timedOut++;this.release(entry);return false;}return true;});
        return;
      }
      if(this.gl.getParameter(this.extension.GPU_DISJOINT_EXT)){this.stats.disjointDropped+=this.pending.length+(this.active?1:0);this.discard();return;}
      const now=this.now();if(!Number.isFinite(now))throw Error('Invalid GPU diagnostic clock');
      if(this.active&&(now<this.active.started||now-this.active.started>=this.timeoutMs)){this.stats.timedOut++;this.release(this.active,true);this.active=undefined;}
      const remaining:Entry[]=[];
      for(let index=0;index<this.pending.length;index++){
        const entry=this.pending[index];
        if(now<entry.started||now-entry.started>=this.timeoutMs){this.stats.timedOut++;this.release(entry);continue;}
        if(!this.gl.getQueryParameter(entry.query,this.gl.QUERY_RESULT_AVAILABLE)){remaining.push(entry);continue;}
        // Disjoint state may change while checking availability. Never read a
        // time result in that state, or claim it as zero milliseconds.
        if(this.gl.getParameter(this.extension.GPU_DISJOINT_EXT)){
          const dropped=[...remaining,...this.pending.slice(index)];this.stats.disjointDropped+=dropped.length+(this.active?1:0);
          for(const item of dropped)this.release(item);if(this.active)this.release(this.active,true);this.active=undefined;this.pending=[];return;
        }
        const nanoseconds=this.gl.getQueryParameter(entry.query,this.gl.QUERY_RESULT);
        if(this.gl.getParameter(this.extension.GPU_DISJOINT_EXT)){
          const dropped=[...remaining,...this.pending.slice(index)];this.stats.disjointDropped+=dropped.length+(this.active?1:0);
          for(const item of dropped)this.release(item);if(this.active)this.release(this.active,true);this.active=undefined;this.pending=[];return;
        }
        if(typeof nanoseconds!=='number'||!Number.isSafeInteger(nanoseconds)||nanoseconds<0||nanoseconds/1e6>=this.timeoutMs){this.stats.failed++;this.warn();}
        else{const milliseconds=nanoseconds/1e6;this.stats.completed++;this.stats.totalGpuMs+=milliseconds;this.stats.maxGpuMs=Math.max(this.stats.maxGpuMs,milliseconds);}
        this.release(entry);
      }
      this.pending=remaining;
    }catch{this.stats.failed++;this.discard();this.warn();}
  }
  getSnapshot(){return {supported:this.supported,disposed:this.disposed,contextLost:this.contextLost,timeoutMs:this.timeoutMs,active:!!this.active,pending:this.pending.length,...this.stats};}
  dispose(){if(this.disposed)return;this.discard();this.disposed=true;}
}
