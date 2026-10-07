// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Read-only ACK qualifier; genuine browser Tab actions are owned by the caller.
export function qualifiedSitHomeStopAck(input){
 const data=(object,key)=>{if(!object||typeof object!=='object'||Array.isArray(object)||![Object.prototype,null].includes(Object.getPrototypeOf(object)))return undefined;const descriptor=Object.getOwnPropertyDescriptor(object,key);return descriptor&&'value'in descriptor?descriptor.value:undefined;};
 const positive=value=>Number.isSafeInteger(value)&&value>0;
 const previous=data(input,'previous'),command=data(input,'command'),frame=data(input,'frame'),state=data(input,'state');
 if(data(input,'connected')!==true||data(input,'tabletVisible')!==true||data(input,'entityChanged')!==false||data(input,'currentCanvas')!==true)return false;
 const beforeSequence=data(previous,'sequence'),beforeNavigation=data(previous,'navigationSequence'),revision=data(previous,'revision');
 if(![beforeSequence,beforeNavigation,revision].every(positive))return false;
 if(data(command,'action')!=='home'||data(command,'revision')!==revision||!positive(data(command,'sequence'))||data(command,'sequence')<=beforeNavigation)return false;
 if(!positive(data(frame,'sequence'))||data(frame,'sequence')<=beforeSequence||data(frame,'revision')!==revision||data(frame,'navigationSequence')!==data(command,'sequence')||data(frame,'surface')!=='tablet')return false;
 if(!['width','height'].every(key=>positive(data(frame,key))&&data(frame,key)<=4096)||!data(frame,'tabletRect'))return false;
 if(data(state,'revision')!==revision||data(state,'screen')!=='Home'||data(state,'visible')!==true||data(state,'loading')!==false)return false;
 const rect=data(frame,'tabletRect'),x=data(rect,'x'),y=data(rect,'y'),width=data(rect,'width'),height=data(rect,'height');
 return [x,y,width,height].every(Number.isFinite)&&x>=0&&y>=0&&width>0&&height>0&&x+width<=data(frame,'width')&&y+height<=data(frame,'height');
}
/** At most32 genuine Tab presses,15s total. No X/focus/native/controller command. */
export async function navigateSitHomeByTab({inspect,tab,now=()=>performance.now()}){
 if(typeof inspect!=='function'||typeof tab!=='function'||typeof now!=='function')throw Error('Owned Home navigation adapters required');
 const began=now();if(!Number.isFinite(began))throw Error('Owned Home navigation clock refused');
 const deadline=began+15000;let completedTabs=0;
 async function bounded(operation){const at=now();if(!Number.isFinite(at)||at<began||at>=deadline)throw Error('Owned Home Tab navigation deadline');const remaining=deadline-at;let timer;const work=Promise.resolve().then(operation);try{return await Promise.race([work,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned Home Tab navigation deadline')),remaining);})]);}finally{clearTimeout(timer);}}
 while(true){
  const current=await bounded(inspect);
  if(!current||current.current!==true||typeof current.focused!=='boolean')throw Error('Fresh owned Home/canvas authority required');
  // Check before any next Tab; sending Tab on the native canvas would be input.
  if(current.focused)return {completedTabs,maximumTabs:32,deadlineMs:15000};
  if(completedTabs>=32)throw Error('Owned Home Tab navigation count bound');
  await bounded(tab);completedTabs++;
 }
}
