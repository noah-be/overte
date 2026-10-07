// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored passive fixture. No input, focus, ACK, DOM or wire mutation.
export function createPttTrustedBinding({canvas,audit,parseAudit,pttControl,createOracle,isActive,document,AbortController,TextEncoder}){
 if(!canvas||!audit.proofs)throw Error('Owned PTT event binding unavailable');
 let records=[],target=null,current=null,retired=false,nextIntent=0;
 const proofs=new Map(),completed=new Map(),abort=new AbortController(),MAX_RECORD_BYTES=32*(4096+256);
 const failures={},pointerEvents=[];
 function failure(reason){failures[reason]=Math.min(2147483647,(failures[reason]??0)+1);if(current)current.failed=true;}
 function qualify(f){if(!target||!f)return null;const record=records.findLast(r=>r.sequence===f.sequence&&r.revision===f.revision&&r.navigationSequence===f.navigationSequence);if(!record?.nativeBuildVersion)return null;return pttControl(records,f,target.kind,target.expected);}
 function remember(p,kind){if(p.refusal)return p;if(proofs.size>=16||proofs.has(p.proofOrdinal))throw Error('Owned PTT event proof bound');proofs.set(p.proofOrdinal,{...p,kind});return p;}
 const oracle=createOracle({canvas,isActive,currentFrame:()=>audit.frame,currentNavigation:()=>audit.navigation,qualify,sample:(el,p)=>remember(audit.proofs.sample(el,p),target.kind)});
 function update(value){
  if(retired||typeof value!=='string'||value.length>MAX_RECORD_BYTES||new TextEncoder().encode(value).length>MAX_RECORD_BYTES)throw Error('Owned PTT record byte bound');
  const next=parseAudit(value);if(next.length>32)throw Error('Owned PTT record count bound');records=next;
 }
 function bindTarget(value){
  if(!value||!['audio-app','desktop-ptt'].includes(value.kind))throw Error('Owned PTT target invalid');
  if(value.kind==='desktop-ptt'&&typeof value.expected!=='boolean')throw Error('Owned PTT expected state invalid');
  target={kind:value.kind,expected:value.expected};
 }
 function sampleCurrent(){const f=audit.frame;if(!isActive()||!f)return {refusal:'no-displayed-frame'};const p=qualify(f);if(!p)return {refusal:'native-control-not-qualified'};const s=audit.proofs.sample(canvas,p);if(s.refusal)return s;return {refusal:null,point:{...p,width:f.width,height:f.height,surface:f.surface,tabletRect:{...f.tabletRect}},sample:s};}
 function observedEvent(event,kind){
  if(retired||!current)return;
  pointerEvents.push({kind,targetSame:event.target===canvas,isTrusted:event.isTrusted===true,button:Number.isInteger(event.button)&&event.button>=-32768&&event.button<=32767?event.button:null,buttons:Number.isInteger(event.buttons)&&event.buttons>=0&&event.buttons<=65535?event.buttons:null,pointerId:Number.isInteger(event.pointerId)&&event.pointerId>=-2147483648&&event.pointerId<=2147483647?event.pointerId:null,isPrimary:typeof event.isPrimary==='boolean'?event.isPrimary:null,pointerType:['mouse','pen','touch',''].includes(event.pointerType)?event.pointerType:'unknown'});
  if(pointerEvents.length>32)pointerEvents.shift();
  if(event.target!==canvas)return;
  try{
   const r=kind==='press'?oracle.pointerDown(event):oracle.pointerUp(event);
   if(!r.pending)failure(r.refusal||'event-not-pending');
  }catch{failure('event-observer-refused');}
 }
 document.addEventListener('pointerdown',e=>observedEvent(e,'press'),{capture:true,signal:abort.signal});
 document.addEventListener('pointerup',e=>observedEvent(e,'release'),{capture:true,signal:abort.signal});
 document.addEventListener('pointercancel',e=>{if(e.target===canvas&&current){failure('physical-pointer-cancelled');oracle.invalidate();}},{capture:true,signal:abort.signal});
 return {
  prepare(value,text){if(retired)throw Error('Owned PTT event binding retired');update(text);bindTarget(value);return sampleCurrent();},
  arm(value,text,expected){
   if(retired||nextIntent>=1000000||completed.size>=16)throw Error('Owned PTT intent bound');
   if(current&&!current.done&&!current.failed)throw Error('Owned PTT prior click unfinished');
   oracle.invalidate();update(text);bindTarget(value);
   const f=audit.frame,p=f&&isActive()?qualify(f):null;
   if(!p)return {refusal:'native-control-not-qualified'};
   if(!expected||f.revision!==expected.revision||f.navigationSequence!==expected.navigationSequence||f.sequence<expected.sequence||f.width!==expected.width||f.height!==expected.height||f.surface!==expected.surface||!['x','y','width','height'].every(k=>f.tabletRect?.[k]===expected.tabletRect?.[k]&&p.rect[k]===expected.rect?.[k]))return {refusal:'frame-or-control-owner-changed'};
   const b=canvas.getBoundingClientRect();if(![b.left,b.top,b.width,b.height,p.x,p.y,f.width,f.height].every(Number.isFinite)||b.width<=0||b.height<=0)return {refusal:'canvas-bounds-refused'};
   current={intentOrdinal:++nextIntent,kind:target.kind,done:false,failed:false,press:null,release:null};
   oracle.arm({...p,width:f.width,height:f.height,surface:f.surface,tabletRect:f.tabletRect});
   return {refusal:null,intentOrdinal:current.intentOrdinal,x:b.left+p.x/f.width*b.width,y:b.top+p.y/f.height*b.height};
  },
  wire(message){
   if(retired)return;
   if(message?.type!=='tablet')return;
   if(['open','home','back','close'].includes(message.action)){oracle.invalidate();target=null;records=[];if(current&&!current.done){failure('navigation-during-physical-click');}current=null;return;}
   if(message.action!=='input'||!['press','release','cancel'].includes(message.event)||!current)return;
   if(message.event==='cancel'){failure('production-pointer-cancelled');oracle.invalidate();return;}
   try{
    const r=oracle.sent(message);if(!r.accepted){failure(r.refusal||'production-event-unmatched');return;}
    if(message.event==='press'){if(current.press){failure('duplicate-production-press');return;}current.press=r;}
    else {if(!current.press||current.release||r.eventOrdinal!==current.press.eventOrdinal||r.proofOrdinal!==current.press.proofOrdinal){failure('production-release-owner-mismatch');return;}current.release=r;current.done=true;completed.set(current.intentOrdinal,{...current});}
   }catch{failure('wire-observer-refused');}
  },
  complete(id){if(!Number.isSafeInteger(id)||id<1)throw Error('Owned PTT intent missing');const row=completed.get(id);if(!row||row.failed||!row.done||!row.press||!row.release)throw Error('Trusted actual PTT press/release proof incomplete');completed.delete(id);if(current?.intentOrdinal===id)current=null;return {intentOrdinal:id,kind:row.kind,press:{...row.press},release:{...row.release}};},
  readProofMetadata(){return [...proofs.values()].map(p=>{const frame={...p.frame};if(frame.tabletRect)frame.tabletRect={...frame.tabletRect};return {...p,frame,canvas:{...p.canvas},image:p.image?{...p.image}:null};});},
  forgetProof(id){proofs.delete(id);},
  invalidate(){oracle.invalidate();records=[];target=null;if(current&&!current.done)failure('authority-or-visibility-revoked');current=null;},
  retire(){if(retired)return;retired=true;abort.abort();oracle.retire();records=[];target=null;current=null;proofs.clear();completed.clear();pointerEvents.length=0;},
  diagnostics(){return {retired,recordCount:records.length,eventProofCount:proofs.size,completedCount:completed.size,current:current?{intentOrdinal:current.intentOrdinal,done:current.done,failed:current.failed}:null,failures:{...failures},pointerEvents:pointerEvents.map(row=>({...row})),oracle:oracle.diagnostics()};}
 };
}
export function pttTrustedBindingInstallerSource(bindingsSource,createOracle){
 return '(()=>{'+bindingsSource+'const createOracle=('+createOracle.toString()+');const createBinding=('+createPttTrustedBinding.toString()+');window.__pttTrustedFactory=()=>createBinding({canvas:document.querySelector("canvas[aria-label=\\\"Native tablet apps and dialogs\\\"]"),audit:window.__pttAudit,parseAudit:parsePttAudit,pttControl:pttClickControl,createOracle:createOracle,isActive:()=>window.__overte?.connected===true&&window.__overte?.tabletVisible===true&&window.__pttAudit.tabletState?.visible===true,document:document,AbortController:AbortController,TextEncoder:TextEncoder});})();';
}
