// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Browser-only test observer: no wire, ACK, draw, navigation or input changes.
export function currentPeopleFrameMetadata(){
 const f=window.__peopleAudit.frame;
 return f?{sequence:f.sequence,revision:f.revision,navigationSequence:f.navigationSequence,width:f.width,height:f.height,tabletRect:f.tabletRect?{...f.tabletRect}:undefined,surface:f.surface}:null;
}
export function samplePeopleDisplayedControl(el,point){
 const f=window.__peopleAudit.frame;
 if(!f)return {refusal:'no-displayed-frame'};
 for(const [key,reason]of [['sequence','frame-sequence-changed'],['revision','frame-revision-changed'],['navigationSequence','frame-navigation-changed']])if(f[key]!==point[key])return {refusal:reason};
 const r=point.rect,x=Math.floor(r.x*el.width/f.width),y=Math.floor(r.y*el.height/f.height),width=Math.ceil(r.width*el.width/f.width),height=Math.ceil(r.height*el.height/f.height);
 if(![x,y,width,height,el.width,el.height,f.width,f.height].every(Number.isSafeInteger)||width<8||height<8||width>512||height>512||width*height>65536||x<0||y<0||x+width>el.width||y+height>el.height)return {refusal:'mapped-control-out-of-bounds'};
 const d=el.getContext('2d').getImageData(x,y,width,height).data;
 if(window.__peopleAudit.frame!==f)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,frame:{sequence:f.sequence,revision:f.revision,navigationSequence:f.navigationSequence,width:f.width,height:f.height,tabletRect:f.tabletRect?{...f.tabletRect}:undefined,surface:f.surface},canvas:{width:el.width,height:el.height},image:{width,height,rgba:Array.from(d)},nativePNG:f.data};
}
// The original People painted-control contrast assertion, with the same >20 boundary.
export function paintedPeopleControl(image){
 if(image.width<8||image.height<8||image.width*image.height>65536||image.rgba.length!==image.width*image.height*4)return false;
 let lo=255,hi=0;for(let i=0;i<image.rgba.length;i+=4){const v=(image.rgba[i]+image.rgba[i+1]+image.rgba[i+2])/3;lo=Math.min(lo,v);hi=Math.max(hi,v);}
 return hi-lo>20;
}
export function assertPaintedPeopleControl(image){if(!paintedPeopleControl(image))throw Error('Actual native People painted contrast/bounds refused');}
export function freshPeopleClickCoordinates(el,point){
 const f=window.__peopleAudit.frame;
 if(!f)return {refusal:'no-displayed-frame'};
 for(const [key,reason]of [['sequence','frame-sequence-changed'],['revision','frame-revision-changed'],['navigationSequence','frame-navigation-changed']])if(f[key]!==point[key])return {refusal:reason};
 const b=el.getBoundingClientRect();
 if(![b.x,b.y,b.width,b.height,f.width,f.height,point.x,point.y].every(Number.isFinite)||b.width<=0||b.height<=0||point.x<0||point.y<0||point.x>=f.width||point.y>=f.height)return {refusal:'canvas-bounds-refused'};
 if(window.__peopleAudit.frame!==f)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,x:b.x+point.x/f.width*b.width,y:b.y+point.y/f.height*b.height};
}
export function createPeopleControlProofQueue(sample,painted){
 const rows=new Map();let bytes=0,ordinal=0,retired=false;
 const MAX_ROWS=16,MAX_BYTES=32*1024*1024,MAX_PNG=2*1024*1024;
 const copyFrame=f=>({sequence:f.sequence,revision:f.revision,navigationSequence:f.navigationSequence,width:f.width,height:f.height,tabletRect:f.tabletRect?{...f.tabletRect}:undefined,surface:f.surface});
 function requireLive(){if(retired)throw Error('Owned People proof queue retired');}
 function capacity(){requireLive();if(rows.size>=MAX_ROWS||ordinal>=1000000)throw Error('Owned People proof count bound');}
 function owned(id){requireLive();if(!Number.isSafeInteger(id)||id<1||!rows.has(id))throw Error('Owned People proof missing');return rows.get(id);}
 function png(value){if(typeof value!=='string'||!value.length||value.length>Math.ceil(MAX_PNG/3)*4||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value))throw Error('Owned People PNG bound');const n=atob(value).length;if(n<1||n>MAX_PNG)throw Error('Owned People PNG bound');return value;}
 function hold(f,canvas,image,nativePNG,displayedPNG=null){
  const weight=nativePNG.length*2+(displayedPNG?.length??0)*2+(image?.rgba.length??0)+512;
  if(!Number.isSafeInteger(weight)||weight>MAX_BYTES-bytes)throw Error('Owned People proof byte bound');
  if(window.__peopleAudit.frame!==f)return {refusal:'frame-changed-during-sample'};
  const id=++ordinal,p={proofOrdinal:id,frame:copyFrame(f),canvas:{...canvas},image:image?{width:image.width,height:image.height,rgba:Uint8Array.from(image.rgba)}:null,nativePNG,displayedPNG,weight};
  rows.set(id,p);bytes+=weight;
  return {refusal:null,proofOrdinal:id,frame:copyFrame(p.frame),canvas:{...p.canvas},image:p.image?{width:p.image.width,height:p.image.height}:null};
 }
 return {
  sample(el,point){capacity();const f=window.__peopleAudit.frame,result=sample(el,point);if(result.refusal)return result;if(!painted(result.image))return {refusal:'control-not-painted'};const nativePNG=png(result.nativePNG);if(window.__peopleAudit.frame!==f||f.sequence!==point.sequence||f.revision!==point.revision||f.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};return hold(f,result.canvas,result.image,nativePNG);},
  capture(el){capacity();const f=window.__peopleAudit.frame;if(!f)return {refusal:'no-displayed-frame'};
   if(![el.width,el.height].every(Number.isSafeInteger)||el.width<1||el.height<1||el.width>4096||el.height>4096||el.width*el.height>4*1024*1024)return {refusal:'capture-canvas-bounds-refused'};
   const nativePNG=png(f.data),url=el.toDataURL('image/png');if(typeof url!=='string'||!url.startsWith('data:image/png;base64,'))throw Error('Owned displayed People PNG bound');const displayedPNG=png(url.slice(22));
   return hold(f,{width:el.width,height:el.height},null,nativePNG,displayedPNG);
  },
  metadata(){requireLive();return {ordinals:[...rows.keys()],count:rows.size,bytes};},
  read(id){const p=owned(id);return {proofOrdinal:id,frame:copyFrame(p.frame),canvas:{...p.canvas},image:p.image?{width:p.image.width,height:p.image.height,rgba:Array.from(p.image.rgba)}:null,nativePNG:p.nativePNG,displayedPNG:p.displayedPNG};},
  release(id){const p=owned(id);rows.delete(id);bytes-=p.weight;},
  retire(){rows.clear();bytes=0;retired=true;}
 };
}
export function peopleProofQueueInstallerSource(sample,painted){
 return '(()=>{const sample=('+sample.toString()+');const painted=('+painted.toString()+');const create=('+createPeopleControlProofQueue.toString()+');window.__peopleProofFactory=()=>create(sample,painted);})();';
}
export function incrementPeopleRefusal(counts,reason){
 const allowed=['control-not-painted','no-displayed-frame','native-control-not-qualified','frame-sequence-changed','frame-revision-changed','frame-navigation-changed','frame-changed-during-sample','mapped-control-out-of-bounds','canvas-bounds-refused','capture-canvas-bounds-refused'];
 if(!allowed.includes(reason))throw Error('Unknown owned People refusal');
 const old=counts[reason]??0;if(!Number.isSafeInteger(old)||old<0||old>2147483647)throw Error('Invalid owned People refusal count');counts[reason]=Math.min(2147483647,old+1);
}
