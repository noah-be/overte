// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {validateBrowserGraphics,type BrowserGraphicsSettings,type BrowserGraphicsRequest} from '../shared/browser-graphics.mjs';
import {validateGraphicsLocalChange,validateGraphicsApplied} from '../shared/browser-graphics-local.mjs';
const equal=(a:BrowserGraphicsSettings,b:BrowserGraphicsSettings)=>a.fieldOfView===b.fieldOfView&&a.resolutionPercent===b.resolutionPercent&&a.localLights===b.localLights&&a.cameraClipping===b.cameraClipping;
/** Browser intent never applies before the native's ordinary owned request/ACK route. */
export class BrowserGraphicsIntent {
 private next=0;private closed=false;private pending?:{id:number;current:()=>boolean;desired:BrowserGraphicsSettings;timer:ReturnType<typeof setTimeout>;resolve:(settings:BrowserGraphicsSettings)=>void;reject:(error:Error)=>void};
 private hidden=()=>{if(this.options.document?.visibilityState!=='visible')this.cancel();};
 constructor(private options:{current():boolean;snapshot():BrowserGraphicsSettings;send(value:Record<string,unknown>):void;document?:Pick<Document,'visibilityState'|'addEventListener'|'removeEventListener'>}){options.document?.addEventListener('visibilitychange',this.hidden);}
 private active():boolean{return !this.closed&&this.options.current()&&(!this.options.document||this.options.document.visibilityState==='visible');}
 async changeResolution(value:number,current:()=>boolean=()=>true):Promise<BrowserGraphicsSettings>{
  if(this.closed||this.pending||!this.active()||!this.requestCurrent(current)||this.next>=Number.MAX_SAFE_INTEGER)return Promise.reject(Error('The current graphics route is unavailable'));
  const before=validateBrowserGraphics(this.options.snapshot()),id=++this.next,intent=validateGraphicsLocalChange({schemaVersion:1,browserRequestId:id,field:'resolutionPercent',value});
  if(!this.active()||!this.requestCurrent(current))return Promise.reject(Error('The current graphics route is unavailable'));
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>this.cancel(),8000);this.pending={id,current,desired:{...before,resolutionPercent:value},timer,resolve,reject};
   try{this.options.send({action:'graphicsChange',...intent});}catch{this.cancel();}
  });
 }
 permits(request:BrowserGraphicsRequest&{browserRequestId?:number}):boolean{
  const p=this.pending;try{if(this.closed||!p||!this.active())return false;if(!this.requestCurrent(p.current)){if(this.pending===p)this.cancel();return false;}return this.pending===p&&request.browserRequestId===p.id&&request.operation==='change'&&request.field==='resolutionPercent'&&request.value===p.desired.resolutionPercent;}catch{this.cancel();return false;}
 }
 complete(value:unknown):void{
  if(this.closed)return;const result=validateGraphicsApplied(value),p=this.pending;
  if(!p||result.browserRequestId!==p.id)return;
  let actual:BrowserGraphicsSettings;try{if(!this.active()||!this.requestCurrent(p.current)||this.pending!==p){if(this.pending===p)this.cancel();return;}actual=validateBrowserGraphics(this.options.snapshot());if(!this.requestCurrent(p.current)||this.pending!==p){if(this.pending===p)this.cancel();return;}}catch{this.cancel();return;}
  this.pending=undefined;clearTimeout(p.timer);
  if(result.accepted&&result.settings&&equal(actual,p.desired)&&equal(result.settings,actual))p.resolve(actual);
  else p.reject(Error('The native Graphics app did not confirm the actual suggested setting'));
 }
 private requestCurrent(current:()=>boolean):boolean{try{return current()===true;}catch{return false;}}
 cancel():void{const p=this.pending;if(!p)return;this.pending=undefined;clearTimeout(p.timer);try{this.options.send({action:'graphicsCancel',schemaVersion:1,browserRequestId:p.id});}catch{/* Revocation/leave also resets native authority. */}p.reject(Error('Graphics confirmation cancelled; check the effective settings'));}
 dispose():void{if(this.closed)return;this.cancel();this.closed=true;this.options.document?.removeEventListener('visibilitychange',this.hidden);}
}
