// SPDX-License-Identifier: Apache-2.0
import {WorldSourceTextCapacityError} from './world-source-text-cache';

type Result<T>={ok:true;value:T}|{ok:false;error:unknown};
/** Read only the next bounded immutable definition while the current template
 * waits. Template construction and application remain strictly serial. The
 * resolver must retain the original per-reader authority and response limits. */
export async function orderedFstDefinitions<E,D>(entries:readonly E[],resolve:(entry:E,signal:AbortSignal,speculative:boolean)=>Promise<D>,apply:(definition:D)=>Promise<void>,options:{signal:AbortSignal;assertCurrent():void;onEvent?:(event:'started'|'consumed'|'capacity-fallback')=>void}):Promise<void>{
 if(entries.length>256)throw Error('FST definition lookahead exceeds its ordered entry limit');
 const controller=new AbortController(),abort=()=>controller.abort(options.signal.reason);
 options.signal.addEventListener('abort',abort,{once:true});if(options.signal.aborted)abort();
 let pending:Promise<Result<D>>|undefined;
 const current=()=>{controller.signal.throwIfAborted();options.assertCurrent();};
 try{
  for(let index=0;index<entries.length;index++){
   current();let definition:D;
   if(pending){
    const result=await pending;pending=undefined;current();options.onEvent?.('consumed');
    if(result.ok)definition=result.value;
    else if(result.error instanceof WorldSourceTextCapacityError){
     // Optional prefetch has no right to enlarge capacity or hide other errors.
     // Retry only the typed admission refusal at the original ordered point.
     options.onEvent?.('capacity-fallback');definition=await resolve(entries[index],controller.signal,false);
    }else throw result.error;
   }else definition=await resolve(entries[index],controller.signal,false);
   current();
   if(index+1<entries.length){
    options.onEvent?.('started');
    // Both synchronous and async failures are observed immediately. They become
    // application failures only when their original ordered entry is reached.
    pending=Promise.resolve().then(()=>{current();return resolve(entries[index+1],controller.signal,true);}).then(value=>({ok:true,value}as const),error=>({ok:false,error}as const));
   }
   await apply(definition);current();
  }
 }finally{
  controller.abort();options.signal.removeEventListener('abort',abort);
  // An outstanding resolver already has a rejection handler. Its own bounded
  // source-text reader stops immediately; no mutable template was started.
  pending=undefined;
 }
}
