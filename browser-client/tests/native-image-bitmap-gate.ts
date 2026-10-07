// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-only hold at one owned Image's real bitmap-production boundary. Other
// createImageBitmap users pass through untouched; cleanup also handles a factory
// which completes after the fixture has already failed or timed out.
export function createNativeImageBitmapGate(ownedSource:()=>unknown,factory:typeof createImageBitmap){
 let claimed=false,closed=false,released=false,bitmap:ImageBitmap|undefined;
 let readyResolve!:(value:ImageBitmap)=>void,readyReject!:(error:unknown)=>void,deliverResolve!:()=>void;
 const ready=new Promise<ImageBitmap>((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
 void ready.catch(()=>{});
 const held=new Promise<void>(resolve=>deliverResolve=resolve);
 const invoke=(async(...args:unknown[])=>{
  if(args[0]!==ownedSource())return Reflect.apply(factory,globalThis,args);
  if(claimed)throw Error('Authored Image fixture bitmap gate already has an owned request');
  claimed=true;
  try{
   const produced=await Reflect.apply(factory,globalThis,args) as ImageBitmap;
   bitmap=produced;
   if(closed){produced.close();readyResolve(produced);return produced;}
   readyResolve(produced);
   await held;
   return produced;
  }catch(error){readyReject(error);throw error;}
 }) as typeof createImageBitmap;
 return {invoke,ready,
  deliver(){released=true;deliverResolve();},
  close(){if(closed)return;closed=true;if(bitmap&&!released)bitmap.close();deliverResolve();}
 };
}
