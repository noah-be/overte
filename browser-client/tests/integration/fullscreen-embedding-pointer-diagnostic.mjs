// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Passive actual event-target geometry; no input/focus/DOM/property mutation. */
export function installEmbeddingPointerDiagnostic(){
 const record={events:[],censored:false};window.__embeddingPointerDiagnostic=record;
 const number=v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=65536?v:null;
 for(const type of ['pointerdown','pointerup','pointermove','gotpointercapture','lostpointercapture','click'])document.addEventListener(type,event=>{
  if(record.events.length>=64){record.censored=true;return;}
  const host=document.getElementById('fullscreen-tablet-owner'),canvas=host?.querySelector('canvas'),keyboard=host?.querySelector('textarea'),iframe=document.getElementById('owned-fullscreen-frame'),rect=canvas?.getBoundingClientRect();
  const hit=Number.isFinite(event.clientX)&&Number.isFinite(event.clientY)?document.elementFromPoint(event.clientX,event.clientY):null;
  record.events.push({type,eventTargetCanvas:event.target===canvas,eventTargetKeyboard:!!keyboard&&event.target===keyboard,eventTargetIframe:!!iframe&&event.target===iframe,eventTargetOwned:!!host&&event.target instanceof Node&&host.contains(event.target),hitCanvas:!!canvas&&hit===canvas,trusted:event.isTrusted===true,button:number(event.button),buttons:number(event.buttons),pointerId:number(event.pointerId),isPrimary:event.isPrimary===true,pointerType:['mouse','pen','touch'].includes(event.pointerType)?event.pointerType:'other',clientX:number(event.clientX),clientY:number(event.clientY),canvasRect:rect?{x:number(rect.x),y:number(rect.y),width:number(rect.width),height:number(rect.height)}:null,connected:host?.isConnected===true,visible:document.visibilityState==='visible',displayedAck:window.__fullscreenTablet?.sent?.some(v=>v.action==='frameAck'&&v.displayed===true)===true});
 },{capture:true,passive:true});
}
export function readEmbeddingPointerDiagnostic(){
 const d=window.__embeddingPointerDiagnostic;
 const inputs=(window.__fullscreenTablet?.sent??[]).filter(v=>v.action==='input');
 return {events:d?.events??[],censored:d?.censored===true,wireCensored:inputs.length>64,wire:inputs.slice(-64).map(v=>({event:v.event,revision:v.revision,sequence:v.sequence,navigationSequence:v.navigationSequence,frameSequence:v.frameSequence,button:v.button,buttons:v.buttons,x:v.x,y:v.y}))};
}
