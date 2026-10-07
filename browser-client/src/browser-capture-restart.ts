// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {captureChange,type CaptureChange,type CaptureReason} from '../shared/browser-capture.mjs';
const processing=['echoCancellation','noiseSuppression','autoGainControl'] as const;
interface RestartOwner{
 current():boolean;
 acquire(constraints:MediaStreamConstraints):Promise<MediaStream>;
 retire():void;
 publish(stream:MediaStream,track:MediaStreamTrack):void;
 stop():void;
}
/** One prior consent, one exact same-device attempt and at most one exact restore.
 * The owner keeps its resource slot until this promise actually settles. */
export async function restartConsentedCapture(track:MediaStreamTrack,change:CaptureChange,owner:RestartOwner):Promise<CaptureReason>{
 change=captureChange(change.field,change.value);
 if(change.field==='inputGainPercent'||!owner.current()||track.readyState!=='live')return 'inactive';
 const old=track.getSettings(),constraints=track.getConstraints(),device=old.deviceId;
 // Device identity stays private. An absent identity cannot authorize another device.
 if(typeof device!=='string'||device.length===0||device.length>4096||processing.some(f=>typeof old[f]!=='boolean'))return 'unsupported';
 const previous={echoCancellation:old.echoCancellation!,noiseSuppression:old.noiseSuppression!,autoGainControl:old.autoGainControl!};
 const desired={...previous,[change.field]:change.value};
 const wanted=(values:typeof desired):MediaStreamConstraints=>({audio:{...constraints,deviceId:{exact:device},...Object.fromEntries(processing.map(f=>[f,{exact:values[f]}]))},video:false});
 const discard=(stream:MediaStream)=>{for(const candidate of stream.getTracks()){candidate.onended=null;candidate.stop();}};
 const attempt=async(values:typeof desired):Promise<CaptureReason|'permission-refused'>=>{
  if(!owner.current())return 'cancelled';
  let stream:MediaStream|undefined;
  try{
   stream=await owner.acquire(wanted(values));
   if(!owner.current()){discard(stream);return 'cancelled';}
   const tracks=stream.getTracks(),audio=stream.getAudioTracks();
   if(tracks.length!==1||audio.length!==1||tracks[0]!==audio[0]||audio[0].readyState!=='live'){discard(stream);return 'readback-mismatch';}
   const effective=audio[0].getSettings();
   if(effective.deviceId!==device||processing.some(f=>effective[f]!==values[f])){discard(stream);return 'readback-mismatch';}
   if(!owner.current()){discard(stream);return 'cancelled';}
   owner.publish(stream,audio[0]);
   return 'ok';
  }catch(error){if(stream)discard(stream);if(!owner.current())return 'cancelled';
   if(error instanceof DOMException&&error.name==='NotAllowedError')return 'permission-refused';
   return 'apply-refused';}
 };
 if(!owner.current())return 'cancelled';
 try{owner.retire();}catch{owner.stop();return 'rollback-refused';}
 const result=await attempt(desired);
 if(result==='ok'||result==='cancelled')return result;
 // A definitive browser permission denial cannot authorize another request.
 if(result==='permission-refused'){owner.stop();return 'rollback-refused';}
 if(!owner.current())return 'cancelled';
 const restored=await attempt(previous);
 if(restored==='cancelled')return restored;
 if(restored!=='ok'){owner.stop();return 'rollback-refused';}
 return result;
}
