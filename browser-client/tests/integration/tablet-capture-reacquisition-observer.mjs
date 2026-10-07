// SPDX-License-Identifier: Apache-2.0
// Copied acceptance ONLY: preserves the original media method, arguments and Promise.
export function installCaptureReacquisitionObserver(){
 const audit=window.__pttAudit,media=navigator.mediaDevices,descriptor=Object.getOwnPropertyDescriptor(media,'getUserMedia');
 const fail=()=>{throw Error('Capture reacquisition proof refused');};
 if(!audit||!Array.isArray(audit.tracks)||audit.tracks.length>4||!descriptor||typeof descriptor.value!=='function'||!descriptor.writable||Object.hasOwn(window,'__captureReacquisition'))fail();
 const original=descriptor.value,fields=['echoCancellation','noiseSuppression','autoGainControl'];
 let pending=null,ordinal=0,retired=false,unexpected=0,observationFailures=0,identity=null;
 const records=[];
 const counter=()=>{const n=audit.getUserMediaCalls;if(!Number.isSafeInteger(n)||n<0||n>2147483647)fail();return n;};
 const tracks=()=>{if(!Array.isArray(audit.tracks)||audit.tracks.length>4)fail();return audit.tracks;};
 const live=()=>tracks().filter(track=>track.readyState==='live');
 const settings=track=>{const value=track.getSettings();if(!value||typeof value.deviceId!=='string'||!value.deviceId||value.deviceId.length>4096||fields.some(field=>typeof value[field]!=='boolean'))fail();return value;};
 const authority=()=>{if(window.__overte?.connected!==true||!Number.isSafeInteger(audit.revision)||audit.revision<1||!Number.isSafeInteger(audit.navigation)||audit.navigation<0)fail();return [audit.revision,audit.navigation];};
 const initial=live();if(initial.length!==1)fail();identity=settings(initial[0]).deviceId;
 function sameAuthority(row){try{const value=authority();return value[0]===row.authority[0]&&value[1]===row.authority[1];}catch{return false;}}
 function observedFailure(){observationFailures=Math.min(32,observationFailures+1);}
 function wrapper(...args){
  const row=pending;
  if(!row||retired)unexpected=Math.min(32,unexpected+1);
  else{
   row.calls++;
   try{
    // Preserve all live/unknown records. Only already-ended records are removed.
    const existing=tracks(),retained=existing.filter(track=>track.readyState!=='ended');
    row.pruned+=existing.length-retained.length;audit.tracks=retained;
    if(row.calls===1){row.oldEndedBeforeAcquisition=row.old.readyState==='ended';row.authorityAtCall=sameAuthority(row);}
    const value=args.length===1?args[0]?.audio:null;
    const matches=!!value&&args[0]?.video===false&&value.deviceId?.exact===identity&&fields.every(field=>value[field]?.exact===row.expected[field]);
    if(!matches)row.constraintsMatch=false;
   }catch{row.constraintsMatch=false;observedFailure();}
  }
  let result;
  try{result=original.apply(this,args);}catch(error){if(row)row.rejected=true;throw error;}
  try{Promise.resolve(result).then(stream=>{
   if(retired||pending!==row||!row)return;
   const audio=stream.getAudioTracks();if(audio.length!==1){observedFailure();return;}
   row.newTrack=audio[0];row.resolved=true;
  },()=>{if(!retired&&row&&pending===row)row.rejected=true;}).catch(observedFailure);}catch{observedFailure();}
  return result;
 }
 Object.defineProperty(media,'getUserMedia',{...descriptor,value:wrapper});
 const api={
  arm(field,value){
   if(retired||pending||ordinal>=6||!fields.includes(field)||typeof value!=='boolean')fail();
   const current=live();if(current.length!==1)fail();const prior=settings(current[0]);if(prior.deviceId!==identity||prior[field]===value)fail();
   const expected=Object.fromEntries(fields.map(key=>[key,key===field?value:prior[key]]));
   pending={ordinal:++ordinal,field,value,old:current[0],expected,authority:authority(),before:counter(),calls:0,pruned:0,constraintsMatch:true,oldEndedBeforeAcquisition:false,authorityAtCall:false,resolved:false,rejected:false,newTrack:null};
   return ordinal;
  },
  complete(id){
   const row=pending;if(retired||!row||row.ordinal!==id)fail();
   const current=live();if(row.calls!==1||counter()!==row.before+1||!row.resolved||row.rejected||observationFailures||unexpected||!row.constraintsMatch||!row.oldEndedBeforeAcquisition||!row.authorityAtCall||!sameAuthority(row)||row.old.readyState!=='ended'||current.length!==1||current[0]!==row.newTrack||row.newTrack.readyState!=='live')fail();
   const actual=settings(row.newTrack);if(actual.deviceId!==identity||fields.some(field=>actual[field]!==row.expected[field]))fail();
   const safe={ordinal:row.ordinal,field:row.field,value:row.value,getUserMediaCallsDelta:1,prunedEnded:row.pruned,oldEndedBeforeAcquisition:true,oldEnded:true,newLive:true,sameDevice:true,allThreeEffectiveSettings:true,effectiveSettings:Object.fromEntries(fields.map(field=>[field,actual[field]])),authorityCurrent:true,liveTrackCount:1};
   records.push(safe);row.old=null;row.newTrack=null;pending=null;return {...safe,effectiveSettings:{...safe.effectiveSettings}};
  },
  summary(){return {version:1,retired,operations:records.map(row=>({...row,effectiveSettings:{...row.effectiveSettings}})),pending:pending!==null,unexpectedCalls:unexpected,observationFailures};},
  retire(){
   if(retired)return;retired=true;
   const current=Object.getOwnPropertyDescriptor(media,'getUserMedia');
   if(current?.value===wrapper)Object.defineProperty(media,'getUserMedia',descriptor);
   if(pending){pending.old=null;pending.newTrack=null;pending=null;}identity=null;
  }
 };
 Object.defineProperty(window,'__captureReacquisition',{value:api,configurable:true});
 return {installed:true,liveTrackCount:1,operationsLimit:6,originalTrackBound:4};
}
