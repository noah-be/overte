// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored browser-only observer. No application wire, ACK, draw or input changes.
export function currentSitFrameMetadata(){
 const frame=window.__sitAudit.frame;
 return frame?{sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,width:frame.width,height:frame.height,tabletRect:frame.tabletRect,surface:frame.surface}:null;
}
export function sampleSitDisplayedControl(el,point){
 const frame=window.__sitAudit.frame;
 if(!frame)return {refusal:'no-displayed-frame'};
 for(const [key,reason]of [['sequence','frame-sequence-changed'],['revision','frame-revision-changed'],['navigationSequence','frame-navigation-changed']])if(frame[key]!==point[key])return {refusal:reason};
 const r=point.rect,x=Math.floor(r.x*el.width/frame.width),y=Math.floor(r.y*el.height/frame.height),width=Math.ceil(r.width*el.width/frame.width),height=Math.ceil(r.height*el.height/frame.height);
 if(![x,y,width,height,el.width,el.height,frame.width,frame.height].every(Number.isSafeInteger)||width<8||height<8||width>512||height>512||width*height>65536||x<0||y<0||x+width>el.width||y+height>el.height)return {refusal:'mapped-control-out-of-bounds'};
 const image=el.getContext('2d').getImageData(x,y,width,height);
 if(window.__sitAudit.frame!==frame||frame.sequence!==point.sequence||frame.revision!==point.revision||frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,frame:{sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,width:frame.width,height:frame.height,tabletRect:frame.tabletRect,surface:frame.surface},canvas:{width:el.width,height:el.height},image:{width,height,rgba:Array.from(image.data)},nativePNG:frame.data};
}
export function freshSitClickCoordinates(el,point){
 const frame=window.__sitAudit.frame;
 if(!frame)return {refusal:'no-displayed-frame'};
 for(const [key,reason]of [['sequence','frame-sequence-changed'],['revision','frame-revision-changed'],['navigationSequence','frame-navigation-changed']])if(frame[key]!==point[key])return {refusal:reason};
 const b=el.getBoundingClientRect();
 if(![b.x,b.y,b.width,b.height,frame.width,frame.height,point.x,point.y].every(Number.isFinite)||b.width<=0||b.height<=0||point.x<0||point.y<0||point.x>=frame.width||point.y>=frame.height)return {refusal:'canvas-bounds-refused'};
 if(window.__sitAudit.frame!==frame||frame.sequence!==point.sequence||frame.revision!==point.revision||frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,x:b.x+point.x/frame.width*b.width,y:b.y+point.y/frame.height*b.height};
}
export function createSitControlProofQueue(sample,painted){
 const rows=new Map();let bytes=0,ordinal=0,retired=false;
 const copyFrame=f=>({...f,tabletRect:f.tabletRect?{...f.tabletRect}:undefined});
 const MAX_ROWS=16,MAX_BYTES=32*1024*1024,MAX_PNG=2*1024*1024;
 function requireLive(){if(retired)throw Error('Owned Sit proof queue retired');}
 function owned(id){requireLive();if(!Number.isSafeInteger(id)||id<1||!rows.has(id))throw Error('Owned Sit proof missing');return rows.get(id);}
 return {
  sample(el,point){
   requireLive();if(rows.size>=MAX_ROWS||ordinal>=1000000)throw Error('Owned Sit proof count bound');
   const frame=window.__sitAudit.frame,result=sample(el,point);
   if(result.refusal)return result;
   const image=result.image;painted(image);
   const png=result.nativePNG;
   if(typeof png!=='string'||png.length===0||png.length>Math.ceil(MAX_PNG/3)*4||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(png))throw Error('Owned native Sit PNG bound');
   const pngBytes=atob(png).length;
   if(pngBytes<1||pngBytes>MAX_PNG)throw Error('Owned native Sit PNG bound');
   const weight=png.length*2+image.rgba.length+256;
   if(!Number.isSafeInteger(weight)||weight>MAX_BYTES-bytes)throw Error('Owned Sit proof byte bound');
   // The assertion and PNG validation are synchronous. Preserve exact identity
   // after all reads; neither a canvas repaint nor an ACK can interleave here.
   if(window.__sitAudit.frame!==frame||frame?.sequence!==point.sequence||frame?.revision!==point.revision||frame?.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
   const id=++ordinal,proof={proofOrdinal:id,frame:copyFrame(result.frame),canvas:{...result.canvas},image:{width:image.width,height:image.height,rgba:Uint8Array.from(image.rgba)},nativePNG:png,weight};
   rows.set(id,proof);bytes+=weight;
   return {refusal:null,proofOrdinal:id,frame:copyFrame(proof.frame),canvas:{...proof.canvas},image:{width:image.width,height:image.height}};
  },
  metadata(){requireLive();return {ordinals:[...rows.keys()],count:rows.size,bytes};},
  read(id){const p=owned(id);return {proofOrdinal:id,frame:copyFrame(p.frame),canvas:{...p.canvas},image:{width:p.image.width,height:p.image.height,rgba:Array.from(p.image.rgba)},nativePNG:p.nativePNG};},
  release(id){const p=owned(id);rows.delete(id);bytes-=p.weight;},
  retire(){rows.clear();bytes=0;retired=true;},
 };
}
// Same exact original Node assertion source and minimal numeric/assert bindings.
// No import/node dependency is serialized to the browser.
export function sitProofQueueInstallerSource(sample,painted){
 return '(()=>{const assert=(value,message)=>{if(!value)throw Error(message||"Actual native Sit painted assertion failed");};assert.equal=(actual,expected)=>assert(actual===expected);const sample=('+sample.toString()+');const painted=('+painted.toString()+');const create=('+createSitControlProofQueue.toString()+');window.__sitProofFactory=()=>create(sample,painted);})();';
}
