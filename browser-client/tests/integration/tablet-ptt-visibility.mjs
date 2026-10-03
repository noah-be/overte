// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored harness-only fixed scalars. No DOM writes, input or browser protocol.
export function readPttVisibilitySnapshot(){
 const a=window.__pttAudit,events=a?.events,observed=a?.visibilityObservation,state=a?.state,commands=a?.commands;
 const count=value=>Number.isSafeInteger(value)&&value>=0&&value<=65535?value:null;
 const flag=value=>typeof value==='boolean'?value:null;
 const last=Array.isArray(commands)&&commands.length<=128?commands.at(-1):null;
 return {version:1,document:{hidden:flag(document.hidden),visibilityState:['visible','hidden','prerender','unloaded'].includes(document.visibilityState)?document.visibilityState:'unknown',hasFocus:flag(document.hasFocus())},events:{keyDown:count(events?.keyDown),keyUp:count(events?.keyUp),focus:count(observed?.focus),blur:count(events?.blur),hidden:count(events?.hidden),trustedFocus:count(observed?.trustedFocus),trustedBlur:count(observed?.trustedBlur),trustedHidden:count(observed?.trustedHidden)},state:{enabled:flag(state?.enabled),held:flag(state?.held),muted:flag(state?.muted)},command:{held:flag(last?.held),sequence:Number.isSafeInteger(last?.sequence)&&last.sequence>=0&&last.sequence<=Number.MAX_SAFE_INTEGER?last.sequence:null}};
}
export function observePttVisibilityEvents(){
 const a=window.__pttAudit;
 a.visibilityObservation={focus:0,trustedFocus:0,trustedBlur:0,trustedHidden:0};
 const increment=key=>{if(a.visibilityObservation[key]<65535)a.visibilityObservation[key]++;};
 window.addEventListener('focus',event=>{increment('focus');if(event.isTrusted===true)increment('trustedFocus');});
 window.addEventListener('blur',event=>{if(event.isTrusted===true)increment('trustedBlur');});
 document.addEventListener('visibilitychange',event=>{if(document.hidden&&event.isTrusted===true)increment('trustedHidden');});
}
export function validatePttVisibilitySnapshot(snapshot){
 const keys=(value,expected)=>{if(!value||typeof value!=='object'||Array.isArray(value)||JSON.stringify(Object.keys(value).sort())!==JSON.stringify([...expected].sort()))throw Error('Fixed PTT visibility schema refused');};
 const flag=value=>value===null||typeof value==='boolean';const count=value=>value===null||(Number.isSafeInteger(value)&&value>=0&&value<=65535);
 keys(snapshot,['version','document','events','state','command']);if(snapshot.version!==1)throw Error('Fixed PTT visibility version refused');
 keys(snapshot.document,['hidden','visibilityState','hasFocus']);if(!flag(snapshot.document.hidden)||!flag(snapshot.document.hasFocus)||!['visible','hidden','prerender','unloaded','unknown'].includes(snapshot.document.visibilityState))throw Error('Fixed PTT document scalars refused');
 keys(snapshot.events,['keyDown','keyUp','focus','blur','hidden','trustedFocus','trustedBlur','trustedHidden']);if(!Object.values(snapshot.events).every(count))throw Error('Fixed PTT event counters refused');
 keys(snapshot.state,['enabled','held','muted']);if(!Object.values(snapshot.state).every(flag))throw Error('Fixed PTT state scalars refused');
 keys(snapshot.command,['held','sequence']);if(!flag(snapshot.command.held)||!(snapshot.command.sequence===null||Number.isSafeInteger(snapshot.command.sequence)&&snapshot.command.sequence>=0))throw Error('Fixed PTT command scalars refused');
 if(JSON.stringify(snapshot).length>1024)throw Error('PTT visibility record byte bound');return snapshot;
}
const PHASES=Object.freeze(['before-second-tab','before-other-front','after-other-front','original-hidden-wait-refused']);
/** Preserve original action failures: read/persistence diagnostics never replace them. */
export async function recordPttVisibilityCheckpoint(report,page,phase,persist){
 if(!PHASES.includes(phase))throw Error('Unknown PTT visibility checkpoint');
 report.windowVisibility??={version:1,scope:'Authored document visibility/focus only; browser window topology not established',records:[],readRefused:0,persistRefused:0};
 const d=report.windowVisibility;if(d.records.length>=8)throw Error('PTT visibility checkpoint bound');
 let snapshot,timer;try{snapshot=validatePttVisibilitySnapshot(await Promise.race([page.evaluate(readPttVisibilitySnapshot),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Bounded PTT visibility read refused')),1000);})]));}catch{d.readRefused=Math.min(8,d.readRefused+1);snapshot=null;}finally{clearTimeout(timer);}
 d.records.push({phase,snapshot});
 try{await persist();}catch{d.persistRefused=Math.min(8,d.persistRefused+1);}
}
