// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Passive harness-only fixed scalars at the original trusted KeyT audit listener.
export function readPttKeyDownSnapshot(){
 const a=window.__pttAudit,button=document.querySelector('#microphone'),state=a?.state;
 const flag=v=>typeof v==='boolean'?v:null;
 const number=(v,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&v>=0&&v<=max?v:null;
 const last=Array.isArray(a?.commands)&&a.commands.length<=128?a.commands.at(-1):null;
 const tracks=Array.isArray(a?.tracks)&&a.tracks.length<=4?a.tracks:null;
 const pressed=button?.getAttribute('aria-pressed');
 return {version:1,microphone:{disabled:flag(button?.disabled),ariaPressed:['true','false'].includes(pressed)?pressed:'unknown'},
  getUserMediaCalls:number(a?.getUserMediaCalls,65535),liveTrackCount:tracks?tracks.filter(t=>t.readyState==='live').length:null,
  native:{enabled:flag(state?.enabled),held:flag(state?.held),muted:flag(state?.muted),sequence:number(state?.sequence),permissionRevision:number(state?.permissionRevision)},
  connected:flag(window.__overte?.connected),tabletVisible:flag(window.__overte?.tabletVisible),command:{held:flag(last?.held),sequence:number(last?.sequence)}};
}
export function validatePttKeyDownSnapshots(rows){
 if(!Array.isArray(rows)||rows.length>16)throw Error('PTT key snapshot count refused');
 const keys=(v,expected)=>{if(!v||typeof v!=='object'||Array.isArray(v)||JSON.stringify(Object.keys(v).sort())!==JSON.stringify([...expected].sort()))throw Error('PTT key snapshot schema refused');};
 const flag=v=>v===null||typeof v==='boolean';
 const number=(v,max=Number.MAX_SAFE_INTEGER)=>v===null||(Number.isSafeInteger(v)&&v>=0&&v<=max);
 return rows.map(row=>{
  keys(row,['version','microphone','getUserMediaCalls','liveTrackCount','native','connected','tabletVisible','command']);
  keys(row.microphone,['disabled','ariaPressed']);keys(row.native,['enabled','held','muted','sequence','permissionRevision']);keys(row.command,['held','sequence']);
  if(row.version!==1||!flag(row.microphone.disabled)||!['true','false','unknown'].includes(row.microphone.ariaPressed)
   ||!number(row.getUserMediaCalls,65535)||!number(row.liveTrackCount,4)||!['enabled','held','muted'].every(k=>flag(row.native[k]))
   ||!number(row.native.sequence)||!number(row.native.permissionRevision)||!flag(row.connected)||!flag(row.tabletVisible)||!flag(row.command.held)||!number(row.command.sequence))throw Error('PTT key snapshot scalar refused');
  if(JSON.stringify(row).length>512)throw Error('PTT key snapshot byte bound');
  return {...row,microphone:{...row.microphone},native:{...row.native},command:{...row.command}};
 });
}
