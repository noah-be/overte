// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored passive fixture. No input, focus, ACK, DOM or wire mutation.
export function createPeopleTrustedBinding({canvas,audit,parseAudit,ignoreControl,homeControl,canonicalPeopleID,createOracle,isActive,document,AbortController,TextEncoder}){
 if(!canvas||!audit.proofs)throw Error('Owned People event binding unavailable');
 let records=[],target=null,current=null,retired=false,nextIntent=0;
 const proofs=new Map(),completed=new Map(),abort=new AbortController(),MAX_RECORD_BYTES=32*(16384+256);
 const failures={};
 function failure(reason){failures[reason]=Math.min(2147483647,(failures[reason]??0)+1);if(current)current.failed=true;}
 function qualify(f){return target?.kind==='home'?homeControl(records,f):target?.kind==='ignore'?ignoreControl(records,f,target.peer,target.ignored):null;}
 function remember(p,kind){if(p.refusal)return p;if(proofs.size>=16||proofs.has(p.proofOrdinal))throw Error('Owned People event proof bound');proofs.set(p.proofOrdinal,{...p,kind});return p;}
 const oracle=createOracle({canvas,isActive,currentFrame:()=>audit.frame,currentNavigation:()=>audit.navigation,qualify,sample:(el,p)=>remember(audit.proofs.sample(el,p),target.kind)});
 function update(value){
  if(retired||typeof value!=='string'||value.length>MAX_RECORD_BYTES||new TextEncoder().encode(value).length>MAX_RECORD_BYTES)throw Error('Owned People record byte bound');
  const next=parseAudit(value);if(next.length>32)throw Error('Owned People record count bound');records=next;
 }
 function bindTarget(value){
  if(!value||!['home','ignore'].includes(value.kind))throw Error('Owned People target invalid');
  target=value.kind==='home'?{kind:'home'}:{kind:'ignore',peer:canonicalPeopleID(value.peer),ignored:value.ignored};
  if(target.kind==='ignore'&&typeof target.ignored!=='boolean')throw Error('Owned People ignore target invalid');
 }
 function sampleCurrent(){const f=audit.frame;if(!isActive()||!f)return {refusal:'no-displayed-frame'};const p=qualify(f);if(!p)return {refusal:'native-control-not-qualified'};const s=audit.proofs.sample(canvas,p);if(s.refusal)return s;return {refusal:null,point:{...p},sample:s};}
 function observedEvent(event,kind){
  if(retired||event.target!==canvas||!current)return;
  try{
   const r=kind==='press'?oracle.pointerDown(event):oracle.pointerUp(event);
   if(!r.pending)failure(r.refusal||'event-not-pending');
  }catch{failure('event-observer-refused');}
 }
 document.addEventListener('pointerdown',e=>observedEvent(e,'press'),{capture:true,signal:abort.signal});
 document.addEventListener('pointerup',e=>observedEvent(e,'release'),{capture:true,signal:abort.signal});
 document.addEventListener('pointercancel',e=>{if(e.target===canvas&&current){failure('physical-pointer-cancelled');oracle.invalidate();}},{capture:true,signal:abort.signal});
 return {
  prepare(value,text){if(retired)throw Error('Owned People event binding retired');update(text);bindTarget(value);return sampleCurrent();},
  arm(value,text,expected){
   if(retired||nextIntent>=1000000||completed.size>=16)throw Error('Owned People intent bound');
   if(current&&!current.done&&!current.failed)throw Error('Owned People prior click unfinished');
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
  complete(id){if(!Number.isSafeInteger(id)||id<1)throw Error('Owned People intent missing');const row=completed.get(id);if(!row||row.failed||!row.done||!row.press||!row.release)throw Error('Trusted actual People press/release proof incomplete');completed.delete(id);if(current?.intentOrdinal===id)current=null;return {intentOrdinal:id,kind:row.kind,press:{...row.press},release:{...row.release}};},
  readProofMetadata(){return [...proofs.values()].map(p=>({...p,frame:{...p.frame,tabletRect:p.frame.tabletRect?{...p.frame.tabletRect}:undefined},canvas:{...p.canvas},image:p.image?{...p.image}:null}));},
  forgetProof(id){proofs.delete(id);},
  invalidate(){oracle.invalidate();records=[];target=null;if(current&&!current.done)failure('authority-or-visibility-revoked');current=null;},
  retire(){if(retired)return;retired=true;abort.abort();oracle.retire();records=[];target=null;current=null;proofs.clear();completed.clear();},
  diagnostics(){return {retired,recordCount:records.length,eventProofCount:proofs.size,completedCount:completed.size,current:current?{intentOrdinal:current.intentOrdinal,done:current.done,failed:current.failed}:null,failures:{...failures},oracle:oracle.diagnostics()};}
 };
}
export function peopleTrustedBindingInstallerSource(bindingsSource,createOracle){
 return '(()=>{'+bindingsSource+'const createOracle=('+createOracle.toString()+');const createBinding=('+createPeopleTrustedBinding.toString()+');window.__peopleTrustedFactory=()=>createBinding({canvas:document.querySelector("canvas[aria-label=\\\"Native tablet apps and dialogs\\\"]"),audit:window.__peopleAudit,parseAudit:parsePeopleAudit,ignoreControl:peopleIgnoreControl,homeControl:peopleHomeControl,canonicalPeopleID:canonicalPeopleID,createOracle:createOracle,isActive:()=>window.__overte?.connected===true&&window.__overte?.tabletVisible===true&&window.__peopleAudit.state?.visible===true,document:document,AbortController:AbortController,TextEncoder:TextEncoder});})();';
}
