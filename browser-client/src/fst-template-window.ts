// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
type Result<R> = {ok:true;value:R}|{ok:false;error:unknown};
/** Two fully-proven FST templates at most. The caller owns every created
 * template before resolving; it may apply results only after this ordered list
 * succeeds. Failure waits for all issued producers before caller cleanup. */
export async function orderedFstTemplates<D,R>(definitions:readonly D[],create:(definition:D,signal:AbortSignal)=>Promise<R>,
 options:{signal:AbortSignal;assertCurrent():void}):Promise<R[]> {
 if(!Array.isArray(definitions)||definitions.length>256)throw Error('Invalid complete FST template plan');
 const controller=new AbortController(),abort=()=>controller.abort(options.signal.reason);
 const current=()=>{controller.signal.throwIfAborted();options.assertCurrent();};
 options.signal.addEventListener('abort',abort,{once:true});if(options.signal.aborted)abort();
 const issued:Promise<Result<R>>[]=[],results:R[]=[];let failed=false;
 const start=(index:number)=>{
  current();
  issued.push(Promise.resolve().then(()=>{current();return create(definitions[index],controller.signal);})
   .then(value=>({ok:true,value}as const),error=>{failed=true;return {ok:false,error}as const;}));
 };
 try {
  current();if(definitions.length)start(0);if(definitions.length>1)start(1);
  for(let index=0;index<definitions.length;index++){
   const result=await issued[index];current();
   if(!result.ok)throw result.error;
   results.push(result.value);
   // A known out-of-order failure stops further admission; its original index
   // still determines the thrown failure after preceding results settle.
   if(!failed&&issued.length<definitions.length)start(issued.length);
  }
  current();return results;
 } finally {
  controller.abort();options.signal.removeEventListener('abort',abort);
  await Promise.all(issued);
 }
}
