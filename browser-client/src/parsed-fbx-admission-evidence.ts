// SPDX-License-Identifier: Apache-2.0
// Passive fixed aggregates only. Never authorizes a cache hit or skips a producer.
export const FBX_ADMISSION_STAGES=['nodes','geometry','materials','textures','skeleton','budget','image-stamp','unspecified'] as const;
export type FbxAdmissionStage=typeof FBX_ADMISSION_STAGES[number];
export const FBX_ADMISSION_LOCATIONS=['provisional-inspection','ready-inspection','producer-rejection'] as const;
export type FbxAdmissionLocation=typeof FBX_ADMISSION_LOCATIONS[number];
const stages=new WeakMap<object,FbxAdmissionStage>();
export function markFbxAdmissionStage(error:unknown,stage:FbxAdmissionStage):void{if(error&&typeof error==='object'&&!stages.has(error))stages.set(error,stage);}
export function fbxAdmissionStage(error:unknown):FbxAdmissionStage{return error&&typeof error==='object'?stages.get(error)??'unspecified':'unspecified';}
type Reason='graph'|'image'|'capacity'|'changed'|'abort'|'other';
interface Identity {starts:number;typedFailures:number;graphFailures:number}
export interface FbxProducerEvidence {identity?:Identity;recorded:boolean}
const counts=<T extends string>(keys:readonly T[])=>Object.fromEntries(keys.map(key=>[key,0])) as Record<T,number>;
/** Bounds are cumulative metadata charges, not a claim about live GC residency.
 * Prepared buffers are weak keys; no source/scene/image/URL is returned. */
export class ParsedFbxAdmissionEvidence {
 private identities=new WeakMap<ArrayBuffer,Map<string,Identity>>();private closed=false;
 private charges=0;private keyBytes=0;private censored=false;
 private starts=0;private repeatStarts=0;private repeatAfterTypedRefusal=0;private repeatAfterGraphRefusal=0;
 private failures=0;private reasons=counts<Reason>(['graph','image','capacity','changed','abort','other']);
 private stageCounts=counts(FBX_ADMISSION_STAGES);private locations=counts(FBX_ADMISSION_LOCATIONS);
 start(buffer:ArrayBuffer,key:string):FbxProducerEvidence {
  if(this.closed)return {recorded:false};this.starts++;
  const group=this.identities.get(buffer),known=group?.get(key);
  if(known){this.repeatStarts++;if(known.typedFailures)this.repeatAfterTypedRefusal++;if(known.graphFailures)this.repeatAfterGraphRefusal++;known.starts++;return {identity:known,recorded:false};}
  const weight=key.length*2;
  if(this.charges>=512||this.keyBytes+weight>1024*1024){this.censored=true;return {recorded:false};}
  const identity:Identity={starts:1,typedFailures:0,graphFailures:0};let owned=group;if(!owned){owned=new Map();this.identities.set(buffer,owned);}owned.set(key,identity);this.charges++;this.keyBytes+=weight;return {identity,recorded:false};
 }
 failure(attempt:FbxProducerEvidence,error:unknown,location:FbxAdmissionLocation,typedReason?:'graph'|'image'|'capacity'|'changed'):void {
  if(this.closed||attempt.recorded)return;attempt.recorded=true;this.failures++;
  let reason:Reason=['graph','image','capacity','changed'].includes(typedReason??'')?typedReason!:'other';
  if(reason==='other')try{const getter=Object.getOwnPropertyDescriptor(DOMException.prototype,'name')?.get;if(getter&&getter.call(error)==='AbortError')reason='abort';}catch{}
  this.reasons[reason]++;this.locations[location]++;this.stageCounts[fbxAdmissionStage(error)]++;
  if(attempt.identity&&['graph','image','capacity','changed'].includes(reason)){attempt.identity.typedFailures++;if(reason==='graph')attempt.identity.graphFailures++;}
 }
 get snapshot(){return {schema:1,producerStarts:this.starts,producerFailures:this.failures,repeatProducerStarts:this.repeatStarts,repeatAfterTypedRefusal:this.repeatAfterTypedRefusal,repeatAfterGraphRefusal:this.repeatAfterGraphRefusal,identityCharges:this.charges,keyBytesCharged:this.keyBytes,maximumIdentityCharges:512,maximumKeyBytesCharged:1024*1024,censored:this.censored,closed:this.closed,reasons:{...this.reasons},stages:{...this.stageCounts},locations:{...this.locations},scope:'Per-World exact prepared-buffer/route-base producer starts. Fixed failure aggregates counted once per producer; no immutable eligibility or live-GC claim.'};}
 dispose():void{if(this.closed)return;this.closed=true;this.identities=new WeakMap();this.charges=0;this.keyBytes=0;}
}
