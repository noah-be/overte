// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Proposed fixture observer only. Never prevents, dispatches or sends input.
export function createPeopleTrustedEventOracle({canvas,isActive,currentFrame,currentNavigation,qualify,sample}){
 let intent=null,pending=null,held=null,retired=false,ordinal=0;
 const failures={};
 const reject=reason=>{failures[reason]=Math.min(2147483647,(failures[reason]??0)+1);return {accepted:false,refusal:reason};};
 const copyRect=r=>({x:r.x,y:r.y,width:r.width,height:r.height});
 const sameRect=(a,b)=>a&&b&&['x','y','width','height'].every(k=>a[k]===b[k]);
 const integer=n=>Number.isSafeInteger(n)&&n>0;
 const live=f=>!retired&&isActive()===true&&f&&integer(f.sequence)&&integer(f.revision)&&integer(f.navigationSequence)&&f.navigationSequence===currentNavigation();
 const coordinates=(event,bounds)=>({x:Math.max(0,Math.min(1,(event.clientX-bounds.left)/Math.max(1,bounds.width))),y:Math.max(0,Math.min(1,(event.clientY-bounds.top)/Math.max(1,bounds.height)))});
 return {
  arm(value){
   if(retired||intent||pending||held||ordinal>=1000000)throw Error('Owned People trusted intent unavailable');
   if(!value||!integer(value.width)||!integer(value.height)||value.width>4096||value.height>4096||!['tablet','dialogs'].includes(value.surface)||!value.tabletRect||!['x','y','width','height'].every(k=>Number.isFinite(value.tabletRect[k]))||!integer(value.sequence)||!integer(value.revision)||!integer(value.navigationSequence)||!value.rect||!['x','y','width','height'].every(k=>Number.isFinite(value.rect[k]))||value.rect.width<=0||value.rect.height<=0)throw Error('Owned People trusted intent invalid');
   intent={sequence:value.sequence,revision:value.revision,navigationSequence:value.navigationSequence,rect:copyRect(value.rect),width:value.width,height:value.height,surface:value.surface,tabletRect:copyRect(value.tabletRect)};
  },
  // Install as a document capture-phase listener before the existing canvas handler.
  pointerDown(event){
   if(retired||!intent||pending||held)return reject('no-owned-intent');
   if(event.target!==canvas||event.isTrusted!==true||event.button!==0||event.buttons!==1||!(Number.isInteger(event.pointerId)&&event.pointerId>=0&&event.pointerId<=2147483647))return reject('trusted-primary-event-required');
   const f=currentFrame();
   if(!live(f)||f.revision!==intent.revision||f.navigationSequence!==intent.navigationSequence||f.sequence<intent.sequence)return reject('authority-or-navigation-changed');
   const p=qualify(f);
   if(!p||p.sequence!==f.sequence||p.revision!==f.revision||p.navigationSequence!==f.navigationSequence)return reject('current-native-control-not-qualified');
   if(f.width!==intent.width||f.height!==intent.height||f.surface!==intent.surface||!sameRect(f.tabletRect,intent.tabletRect)||!sameRect(p.rect,intent.rect))return reject('control-geometry-changed');
   const b=canvas.getBoundingClientRect();
   if(![b.left,b.top,b.width,b.height,f.width,f.height,event.clientX,event.clientY].every(Number.isFinite)||b.width<=0||b.height<=0||f.width<=0||f.height<=0||event.clientX<b.left||event.clientY<b.top||event.clientX>=b.left+b.width||event.clientY>=b.top+b.height)return reject('event-bounds-refused');
   const position=coordinates(event,b),x=position.x*f.width,y=position.y*f.height;
   if(x<p.rect.x||x>=p.rect.x+p.rect.width||y<p.rect.y||y>=p.rect.y+p.rect.height)return reject('event-outside-qualified-control');
   const proof=sample(canvas,p);
   if(proof.refusal)return reject('current-painted-proof-refused');
   if(currentFrame()!==f||!live(f))return reject('frame-changed-during-event');
   pending={id:++ordinal,frame:f,proof,point:p,position,pointerId:event.pointerId,button:event.button,modifiers:(event.shiftKey?1:0)|(event.ctrlKey?2:0)|(event.altKey?4:0)|(event.metaKey?8:0),bounds:{left:b.left,top:b.top,width:b.width,height:b.height},kind:'press'};
   intent=null;
   return {accepted:false,pending:true,eventOrdinal:pending.id,proofOrdinal:proof.proofOrdinal};
  },
  pointerUp(event){
   if(retired||!held||pending)return reject('no-owned-gesture');
   const f=currentFrame();
   if(event.target!==canvas||event.isTrusted!==true||event.pointerId!==held.pointerId||event.button!==held.button||event.buttons!==0)return reject('trusted-release-required');
   if(!live(f)||f.revision!==held.frame.revision||f.navigationSequence!==held.frame.navigationSequence)return reject('authority-or-navigation-changed');
   pending={...held,position:coordinates(event,held.bounds),modifiers:(event.shiftKey?1:0)|(event.ctrlKey?2:0)|(event.altKey?4:0)|(event.metaKey?8:0),kind:'release'};
   return {accepted:false,pending:true,eventOrdinal:held.id};
  },
  // Observe the existing WebSocket.send argument, never generate/modify it.
  sent(message){
   if(retired||!pending)return reject('no-pending-trusted-event');
   const p=pending,f=currentFrame();
   if(!live(f)||f.revision!==p.frame.revision||f.navigationSequence!==p.frame.navigationSequence||(p.kind==='press'&&f!==p.frame))return reject('authority-or-navigation-changed');
   if(!message||message.type!=='tablet'||message.action!=='input'||message.event!==p.kind||!integer(message.sequence)||message.sequence<=p.frame.navigationSequence||message.frameSequence!==p.frame.sequence||message.revision!==p.frame.revision||(message.navigationSequence!==undefined&&message.navigationSequence!==p.frame.navigationSequence)||message.x!==p.position.x||message.y!==p.position.y||message.button!==p.button||message.buttons!==(p.kind==='press'?1:0)||message.modifiers!==p.modifiers)return reject('production-input-does-not-match-event');
   pending=null;if(p.kind==='press')held=p;else held=null;
   return {accepted:true,eventOrdinal:p.id,proofOrdinal:p.proof.proofOrdinal,kind:p.kind,frame:{sequence:p.frame.sequence,revision:p.frame.revision,navigationSequence:p.frame.navigationSequence}};
  },
  invalidate(){intent=null;pending=null;held=null;},
  retire(){intent=null;pending=null;held=null;retired=true;},
  diagnostics(){return {armed:!!intent,pending:!!pending,held:!!held,retired,failures:{...failures}};}
 };
}
