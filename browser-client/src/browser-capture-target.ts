// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {CAPTURE_FIELDS,captureChange,captureState,inactiveCapture,type CaptureChange,type CaptureState,type CaptureReason} from '../shared/browser-capture.mjs';
export interface CaptureBinding{
 track:MediaStreamTrack;gain:GainNode;
 current():boolean;
 inhibit(held:boolean):void;
 stop():void;
 committed(change:CaptureChange):void;
 restartProcessing?(change:CaptureChange,current:()=>boolean):Promise<CaptureReason>;
}
interface Clock{set:(fn:()=>void,ms:number)=>unknown;clear:(id:unknown)=>void}
/** A single already-consented microphone; only its exact private device may restart. */
export class BrowserCaptureTarget{
 private work=false;
 private cancellation?:()=>void;
 constructor(private binding:()=>CaptureBinding|undefined,private clock:Clock={set:(f,ms)=>setTimeout(f,ms),clear:id=>clearTimeout(id as ReturnType<typeof setTimeout>)}){}
 private owned(b:CaptureBinding):boolean{return b.current()&&this.binding()===b;}
 private current(b:CaptureBinding):boolean{return b.current()&&b.track.readyState==='live'&&this.binding()===b;}
 snapshot():CaptureState{
  const b=this.binding();if(!b||!this.current(b))return inactiveCapture();
  const raw=b.track.getSettings(),cap=b.track.getCapabilities?.()??{},controls=Object.fromEntries(CAPTURE_FIELDS.map(f=>[f,false])) as CaptureState['controls'];
  const settings:CaptureState['settings']={echoCancellation:null,noiseSuppression:null,autoGainControl:null,inputGainPercent:null,inputGain:null};
  for(const f of ['echoCancellation','noiseSuppression','autoGainControl'] as const){const value=raw[f],values=cap[f];if(typeof value==='boolean')settings[f]=value;controls[f]=typeof value==='boolean'&&Array.isArray(values)&&values.length<=8&&values.includes(true)&&values.includes(false);}
  const gain=b.gain.gain.value;if(Number.isFinite(gain)&&gain>=0&&gain<=2){settings.inputGain=gain;settings.inputGainPercent=Math.round(gain*100);controls.inputGainPercent=true;}
  if(!this.current(b))return inactiveCapture();return captureState({version:1,active:true,controls,settings});
 }
 /** Cancel only outstanding reconfiguration; normal mute/PTT authority stays owned by BrowserAudio. */
 cancelPending():void{this.cancellation?.();}
 async apply(change:CaptureChange,current:()=>boolean):Promise<{accepted:boolean;reason:CaptureReason;state:CaptureState}>{
  const desired=captureChange(change.field,change.value),before=this.snapshot(),b=this.binding();
  const result=(reason:CaptureReason)=>({accepted:reason==='ok',reason,state:this.snapshot()});
  if(!b||!before.active||!current()||!this.current(b))return result('inactive');
  if(this.work)return result('busy');if(!before.controls[desired.field])return result('unsupported');
  if(desired.field==='inputGainPercent'){
   const old=b.gain.gain.value;
   const rollback=()=>{if(!current()||!this.current(b)){if(this.current(b))b.stop();return false;}try{b.gain.gain.value=old;const actual=this.snapshot().settings.inputGain;if(actual!==null&&Math.abs(actual-old)<1e-6)return true;}catch{}b.stop();return false;};
   try{b.gain.gain.value=desired.value/100;if(!current()||!this.current(b)){if(this.current(b))b.stop();return result('cancelled');}const effective=this.snapshot();if(effective.settings.inputGainPercent!==desired.value||effective.settings.inputGain===null||Math.abs(effective.settings.inputGain-desired.value/100)>1e-6)return result(rollback()?'readback-mismatch':'rollback-refused');b.committed(desired);return result('ok');}
   catch{return result(rollback()?'apply-refused':'rollback-refused');}
  }
  const old=b.track.getConstraints();this.work=true;try{b.inhibit(true);}catch{this.work=false;if(this.current(b))b.stop();return result('apply-refused');}
  let stopped=false,timer:unknown,cancel:()=>void=()=>{},resolveStop:(reason:CaptureReason)=>void=()=>{};
  const interruption=new Promise<CaptureReason>(resolve=>{resolveStop=resolve;});
  cancel=()=>{if(stopped)return;stopped=true;if(this.owned(b))b.stop();resolveStop('cancelled');};this.cancellation=cancel;
  timer=this.clock.set(()=>{if(stopped)return;stopped=true;if(this.owned(b))b.stop();resolveStop('deadline');},8000);
  // Keep the one-operation resource slot until the actual browser operation
  // settles, even when the caller has already received cancellation/timeout.
  const operation=(async():Promise<CaptureReason>=>{
   let reason:CaptureReason='ok';
   try{
    if(!current()||!this.current(b)||stopped)return 'cancelled';
    if(b.restartProcessing){
     const fresh=await b.restartProcessing(desired,()=>!stopped&&current()&&this.owned(b));
     if(stopped||!current()){if(this.owned(b))b.stop();return 'cancelled';}
     // A failed exact restore deliberately ends this binding. Preserve that
     // terminal refusal while still giving external cancellation precedence.
     if(fresh==='rollback-refused')return fresh;
     if(!this.owned(b))return 'cancelled';
     if(fresh!=='ok')return fresh;
     const effective=this.snapshot();
     if(!effective.active||CAPTURE_FIELDS.some(f=>effective.settings[f]!== (f===desired.field?desired.value:before.settings[f]))){b.stop();return 'rollback-refused';}
     b.committed(desired);return 'ok';
    }
    try{await b.track.applyConstraints({...old,[desired.field]:{exact:desired.value}});}catch{reason='apply-refused';}
    if(stopped||!current()||!this.current(b)){if(this.current(b))b.stop();return 'cancelled';}
    if(reason==='ok'&&this.snapshot().settings[desired.field]!==desired.value)reason='readback-mismatch';
    if(reason!=='ok'){
     try{await b.track.applyConstraints(old);}catch{if(this.current(b))b.stop();return 'rollback-refused';}
     if(stopped||!current()||!this.current(b)){if(this.current(b))b.stop();return 'cancelled';}
     const restored=this.snapshot();if(CAPTURE_FIELDS.some(f=>restored.settings[f]!==before.settings[f])){b.stop();return 'rollback-refused';}
     return reason;
    }
    if(!current()||!this.current(b)||stopped){if(this.current(b))b.stop();return 'cancelled';}b.committed(desired);return 'ok';
   }catch{if(this.current(b))b.stop();return 'rollback-refused';}
   finally{this.clock.clear(timer);if(this.cancellation===cancel)this.cancellation=undefined;this.work=false;if(!stopped&&current()&&this.current(b))b.inhibit(false);}
  })();
  const reason=await Promise.race([operation,interruption]);return result(reason);
 }
}
