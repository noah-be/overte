// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {captureRequest,captureResult,type CaptureResult} from '../shared/browser-capture.mjs';import {BrowserCaptureTarget} from './browser-capture-target';
export interface CaptureAcknowledgement extends CaptureResult{type:'tablet';action:'captureResult';revision:number}
export class BrowserCaptureController{
 private revision=0;private allowed=false;private closed=false;private generation=0;private last=0;
 constructor(private target:BrowserCaptureTarget,private current:(revision:number)=>boolean){}
 setAuthority(revision:number,allowed:boolean):void{if(this.closed)return;if(!Number.isSafeInteger(revision)||revision<1){revision=0;allowed=false;}if(this.revision!==revision||this.allowed!==allowed){this.target.cancelPending();this.generation++;this.last=0;}this.revision=revision;this.allowed=allowed;}
 cancelPending():void{this.generation++;this.target.cancelPending();}
 async receive(input:unknown,revision:number):Promise<CaptureAcknowledgement|undefined>{
  if(!this.active(revision))return;const request=captureRequest(input);if(request.requestId<=this.last)return;this.last=request.requestId;
  if(request.operation==='cancel')this.cancelPending();const operationGeneration=this.generation;const effectiveCurrent=()=>this.active(revision)&&operationGeneration===this.generation;
  let accepted=true,reason:CaptureResult['reason']='ok';
  if(request.operation==='change'){const applied=await this.target.apply(request,effectiveCurrent);accepted=applied.accepted;reason=applied.reason;}
  if(!effectiveCurrent())return;const result=captureResult({schemaVersion:1,requestId:request.requestId,accepted,reason,state:this.target.snapshot()});if(!effectiveCurrent())return;return{type:'tablet',action:'captureResult',revision,...result};
 }
 private active(revision:number):boolean{return !this.closed&&this.allowed&&revision===this.revision&&this.current(revision);}
 close():void{if(this.closed)return;this.closed=true;this.allowed=false;this.generation++;this.target.cancelPending();}
}
