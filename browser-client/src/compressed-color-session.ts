// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Connected-session approval and per-world ownership for compressed color assets.
import {BrowserSession,type SessionCallbacks,type ServerMessage} from './session';
import {NativeCompressedColorCache,type CompressionCapabilities,type CompressedColorOptions} from './native-compressed-color';
import type {WorldSourceAuthority} from './world-source-text-cache';
export type SessionCompressionLimits=Omit<CompressedColorOptions,'origin'|'sessionId'|'authority'|'resolveAsset'|'capabilities'>;
interface Approval {sessionId: string; permissionRevision: number; epoch: number}
interface OwnedCache {cache: NativeCompressedColorCache; signal: AbortSignal; stop(): void}
function idle(cache: NativeCompressedColorCache){const state=cache.statistics;return state.active===0&&state.queued===0&&state.readers===0;}
function aborted(){return new DOMException('Compressed asset world was disposed','AbortError');}
class AssetApproval {
 private approval?: Approval;private boundSessionId='';private connectionEpoch=0;private approvalEpoch=0;
 private owned?: OwnedCache;private retired?: NativeCompressedColorCache;
 constructor(private origin: string,private matchesSession:(id:string)=>boolean){}
 get snapshot(){return this.approval?{...this.approval}:undefined;}
 capture():WorldSourceAuthority{
  const approval=this.approval,connection=this.connectionEpoch;
  if(!approval||!this.matchesSession(approval.sessionId))throw Error('World assets require the current connected session authority');
  return {generation:JSON.stringify([connection,approval.epoch,approval.sessionId,approval.permissionRevision]),assertCurrent:()=>{
   if(this.connectionEpoch!==connection||this.approval!==approval||!this.matchesSession(approval.sessionId))throw Error('World asset authority was revoked');
  }};
 }
 leave(){this.revoke();this.boundSessionId='';this.connectionEpoch++;}
 revoke(){this.approval=undefined;this.owned?.stop();}
 observe(message: Extract<ServerMessage,{type:'state'}>){
  if(message.state!=='connected'){
   this.revoke();
   if(message.sessionId){if(this.boundSessionId&&this.boundSessionId!==message.sessionId)throw Error('The asset session changed without a fresh connection');this.boundSessionId=message.sessionId;}
   return;
  }
  if(!message.sessionId||!/^[a-zA-Z0-9_-]{1,128}$/.test(message.sessionId)||!Number.isSafeInteger(message.permissionRevision)||message.permissionRevision!<1){this.revoke();throw Error('Connected asset authority is missing its session or permission revision');}
  if(this.boundSessionId&&this.boundSessionId!==message.sessionId){this.revoke();throw Error('The asset session changed without a fresh connection');}
  if(this.approval?.sessionId===message.sessionId&&this.approval.permissionRevision===message.permissionRevision)return;
  this.revoke();this.boundSessionId=message.sessionId;
  this.approval={sessionId:message.sessionId,permissionRevision:message.permissionRevision!,epoch:++this.approvalEpoch};
 }
 colors(capabilities:CompressionCapabilities,signal:AbortSignal,limits:SessionCompressionLimits={}){
  if(signal.aborted)throw aborted();
  const approval=this.approval;if(!approval||!this.matchesSession(approval.sessionId))throw Error('Compressed assets require the current connected session authority');
  if(this.owned){if(this.owned.signal!==signal)throw Error('A different world still owns this compressed asset cache');return this.owned.cache;}
  if(this.retired){if(!idle(this.retired))throw Error('Waiting for previous compressed asset readers to settle');this.retired=undefined;}
  const connection=this.connectionEpoch,token=JSON.stringify([connection,approval.epoch,approval.sessionId,approval.permissionRevision]);
  const current=()=>this.connectionEpoch===connection&&this.approval===approval&&this.matchesSession(approval.sessionId)&&!signal.aborted;
  const cache=new NativeCompressedColorCache({...limits,origin:this.origin,sessionId:approval.sessionId,capabilities,authority:()=>current()?token:null,
   resolveAsset:original=>{if(!current())throw Error('Compressed asset authority was revoked');const address=new URL(`/api/assets/${approval.sessionId}`,this.origin);address.searchParams.set('url',original);return address.href;}});
  const owned:OwnedCache={cache,signal,stop:()=>{
   if(this.owned!==owned)return;
   this.owned=undefined;signal.removeEventListener('abort',owned.stop);cache.dispose();if(!idle(cache))this.retired=cache;
  }};
  this.owned=owned;signal.addEventListener('abort',owned.stop,{once:true});return cache;
 }
}
/** All cache revocation precedes app callbacks and socket teardown. Only a connected state grants it; Tablet messages do not. */
export class CompressedColorSession extends BrowserSession {
 private readonly assets:AssetApproval;
 constructor(callbacks:SessionCallbacks){
  let matchesSession:(id:string)=>boolean=()=>false;
  const assets=new AssetApproval(new URL(window.location.href).origin,id=>matchesSession(id));
  super({message:message=>{if(message.type==='state')assets.observe(message);return callbacks.message(message);},audio:callbacks.audio,
   error:reason=>{assets.revoke();callbacks.error(reason);},closed:reason=>{assets.revoke();callbacks.closed(reason);}});
  this.assets=assets;matchesSession=id=>this.connected&&this.sessionId===id;
 }
 get compressedAssetApproval(){return this.assets.snapshot;}
 captureAssetAuthority(){return this.assets.capture();}
 compressedColors(capabilities:CompressionCapabilities,worldSignal:AbortSignal,limits:SessionCompressionLimits={}){return this.assets.colors(capabilities,worldSignal,limits);}
 override leave(){this.assets.leave();super.leave();}
}
