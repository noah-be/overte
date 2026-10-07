// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored browser-only observer. No application wire, ACK, draw or input changes.
export function createPttControlProofQueue(sample,painted){
 const rows=new Map();let bytes=0,ordinal=0,retired=false;
 const MAX_ROWS=16,MAX_BYTES=32*1024*1024,MAX_PNG=2*1024*1024;
 function requireLive(){if(retired)throw Error('Owned PTT proof queue retired');}
 function owned(id){requireLive();if(!Number.isSafeInteger(id)||id<1||!rows.has(id))throw Error('Owned PTT proof missing');return rows.get(id);}
 return {
  sample(el,point){
   requireLive();if(rows.size>=MAX_ROWS||ordinal>=1000000)throw Error('Owned PTT proof count bound');
   const frame=window.__pttAudit.frame,result=sample(el,point);
   if(result.refusal)return result;
   const image=result.image;painted(image.rgba,image.width,image.height);
   const png=result.nativePNG;
   if(typeof png!=='string'||png.length===0||png.length>Math.ceil(MAX_PNG/3)*4||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(png))throw Error('Owned native PTT PNG bound');
   const pngBytes=atob(png).length;
   if(pngBytes<1||pngBytes>MAX_PNG)throw Error('Owned native PTT PNG bound');
   const weight=png.length*2+image.rgba.length+256;
   if(!Number.isSafeInteger(weight)||weight>MAX_BYTES-bytes)throw Error('Owned PTT proof byte bound');
   // The assertion and PNG validation are synchronous. Preserve exact identity
   // after all reads; neither a canvas repaint nor an ACK can interleave here.
   if(window.__pttAudit.frame!==frame||frame?.sequence!==point.sequence||frame?.revision!==point.revision||frame?.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
   const id=++ordinal,proof={proofOrdinal:id,frame:{...result.frame},canvas:{...result.canvas},image:{width:image.width,height:image.height,rgba:Uint8Array.from(image.rgba)},nativePNG:png,weight};
   rows.set(id,proof);bytes+=weight;
   return {refusal:null,proofOrdinal:id,frame:{...proof.frame},canvas:{...proof.canvas},image:{width:image.width,height:image.height}};
  },
  metadata(){requireLive();return {ordinals:[...rows.keys()],count:rows.size,bytes};},
  read(id){const p=owned(id);return {proofOrdinal:id,frame:{...p.frame},canvas:{...p.canvas},image:{width:p.image.width,height:p.image.height,rgba:Array.from(p.image.rgba)},nativePNG:p.nativePNG};},
  release(id){const p=owned(id);rows.delete(id);bytes-=p.weight;},
  retire(){rows.clear();bytes=0;retired=true;},
 };
}
// Same exact original Node assertion source and minimal numeric/assert bindings.
// No import/node dependency is serialized to the browser.
export function pttProofQueueInstallerSource(sample,painted){
 return '(()=>{const assert=(value,message)=>{if(!value)throw Error(message||"Actual native PTT painted assertion failed");};const integer=(value,min,max)=>Number.isSafeInteger(value)&&value>=min&&value<=max;const sample=('+sample.toString()+');const painted=('+painted.toString()+');const create=('+createPttControlProofQueue.toString()+');window.__pttProofFactory=()=>create(sample,painted);})();';
}
