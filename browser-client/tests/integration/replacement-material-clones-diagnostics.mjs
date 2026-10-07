// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Public failure/event projections are fixed. Bounded original stacks are private-report only.
// No retries, changed evaluation, native reads, console text or public raw exception.
import {randomUUID} from 'node:crypto';import{mkdir,writeFile}from'node:fs/promises';import path from'node:path';import{types}from'node:util';
const own=(value,key)=>{try{const d=Object.getOwnPropertyDescriptor(value,key);return d&&'value'in d?d.value:undefined;}catch{return undefined;}};
// Trust only the owned Node harness's initial native Error stack accessor/formatter.
// Do not evaluate arbitrary error getters, custom prototypes or changed formatters.
const stackGetter=Object.getOwnPropertyDescriptor(new Error(),'stack')?.get;
const stackFormatter=Object.getOwnPropertyDescriptor(Error,'prepareStackTrace');
const errorToString=Error.prototype.toString;
const errorPrototypes=new Set([Error.prototype,TypeError.prototype,ReferenceError.prototype,RangeError.prototype,SyntaxError.prototype,AggregateError.prototype,EvalError.prototype,URIError.prototype]);
const prototypeFields=[...errorPrototypes].map(prototype=>[prototype,...['name','message','toString'].map(key=>[key,Object.getOwnPropertyDescriptor(prototype,key)])]);
const samePrototypeFields=()=>prototypeFields.every(([prototype,...fields])=>fields.every(([key,initial])=>{const current=Object.getOwnPropertyDescriptor(prototype,key);return current?.get===initial?.get&&current?.set===initial?.set&&current?.value===initial?.value;}));
const sameFormatter=()=>{const now=Object.getOwnPropertyDescriptor(Error,'prepareStackTrace');return now?.get===stackFormatter?.get&&now?.set===stackFormatter?.set&&now?.value===stackFormatter?.value;};
export function privateCloneException(error){
 let stack;try{
  const descriptor=Object.getOwnPropertyDescriptor(error,'stack');
  if(descriptor&&'value'in descriptor)stack=descriptor.value;
  else if(types.isNativeError(error)&&descriptor?.get===stackGetter&&typeof stackGetter==='function'&&sameFormatter()&&samePrototypeFields()&&Error.prototype.toString===errorToString){
   const message=Object.getOwnPropertyDescriptor(error,'message'),name=Object.getOwnPropertyDescriptor(error,'name');
   if(!message||!('value'in message)||typeof message.value!=='string'||message.value.length>8192||name&&(!('value'in name)||typeof name.value!=='string'||name.value.length>128))return {stackAvailable:false,stack:null,stackTruncated:false};
   if(Object.hasOwn(error,'toString'))return {stackAvailable:false,stack:null,stackTruncated:false};
   let prototype=Object.getPrototypeOf(error),depth=0;
   while(prototype&&prototype!==Object.prototype){if(++depth>4||!errorPrototypes.has(prototype))return {stackAvailable:false,stack:null,stackTruncated:false};prototype=Object.getPrototypeOf(prototype);}
   stack=stackGetter.call(error);
  }
 }catch{}
 if(typeof stack!=='string')return {stackAvailable:false,stack:null,stackTruncated:false};
 // Scan at most8192 code units, retain <=8192 UTF-8 bytes. No whole-stack encoding.
 let end=0,bytes=0;while(end<stack.length&&end<8192){const point=stack.codePointAt(end),units=point>0xffff?2:1,size=point<=0x7f?1:point<=0x7ff?2:point<=0xffff?3:4;if(bytes+size>8192)break;bytes+=size;end+=units;}
 return {stackAvailable:true,stack:stack.slice(0,end),stackTruncated:end<stack.length};
}
// An own native-Error data message does not require executing a stack formatter
// or an unknown subclass getter. Retain it only in the protected attempt report.
export function privateCloneMessage(error){
 if(types.isProxy(error)||!types.isNativeError(error))return {messageAvailable:false,message:null,messageTruncated:false};
 const message=own(error,'message');
 if(typeof message!=='string')return {messageAvailable:false,message:null,messageTruncated:false};
 let end=0,bytes=0;while(end<message.length&&end<8192){const point=message.codePointAt(end),units=point>0xffff?2:1,size=point<=0x7f?1:point<=0x7ff?2:point<=0xffff?3:4;if(bytes+size>8192)break;bytes+=size;end+=units;}
 return {messageAvailable:true,message:message.slice(0,end),messageTruncated:end<message.length};
}
const fixtureRefusals=[
 ['Required imported World graph is not ready','fixture-graph-ready-deadline'],
 ['A fixed view changed pixels over actual twenty rendered frames','fixture-unstable-pixels'],
 ['Fixed material/program state changed across genuine rendered frames','fixture-material-program-change'],
 ['Duplicate material disposal','fixture-duplicate-material-disposal'],
 ['Authored triangle center must remain on screen','fixture-projected-triangle-center-offscreen'],
 ['Two genuine imported FBX triangle centers required','fixture-triangle-centers-missing'],
];
export function cloneFailureDiagnostic(error){
 let errorClass='unclassified';try{let prototype=Object.getPrototypeOf(error);for(let depth=0;prototype&&depth<4;depth++,prototype=Object.getPrototypeOf(prototype)){
  const known=[[TypeError.prototype,'type-error'],[ReferenceError.prototype,'reference-error'],[RangeError.prototype,'range-error'],[SyntaxError.prototype,'syntax-error'],[AggregateError.prototype,'aggregate-error'],[Error.prototype,'error']].find(([p])=>prototype===p);if(known){errorClass=known[1];break;}
 }}catch{}
 const name=own(error,'name'),named={Error:'error',TypeError:'type-error',ReferenceError:'reference-error',RangeError:'range-error',SyntaxError:'syntax-error',AggregateError:'aggregate-error',TimeoutError:'timeout-error'};if(typeof name==='string'&&Object.hasOwn(named,name))errorClass=named[name];
 let reason='unclassified';const message=own(error,'message');if(typeof message==='string'&&message.length<=8192){
  if(message.includes('Execution context was destroyed')||message.includes('Execution context is not available in detached frame or worker'))reason='evaluation-context-destroyed';
  else if(message.includes('Target page, context or browser has been closed')||message.includes('Target closed'))reason='target-closed';
  else{const refusal=fixtureRefusals.find(([literal])=>message.includes(literal));if(refusal)reason=refusal[1];}
 }
 const matcher=own(error,'matcherResult');if(matcher&&typeof matcher==='object'&&own(matcher,'pass')===false)reason='registered-assertion-refused';
 if(reason==='unclassified'&&errorClass==='timeout-error')reason='deadline';
 return {errorClass,reason};
}
export function observeCloneDriver(page){
 const state={mainFrameNavigations:0,pageErrorCount:0,pageErrorClasses:[],requestFailures:0,consoleErrors:0,consoleWarnings:0,observationRefusals:0,censored:false};
 const increment=key=>{if(state[key]<256)state[key]++;else state.censored=true;};
 const onPageError=error=>{increment('pageErrorCount');if(state.pageErrorClasses.length<16)state.pageErrorClasses.push(cloneFailureDiagnostic(error));else state.censored=true;};
 const onNavigate=frame=>{try{if(frame.parentFrame()===null)increment('mainFrameNavigations');}catch{increment('observationRefusals');}};
 const onRequestFailure=()=>increment('requestFailures');
 const onConsole=message=>{try{const type=message.type();if(type==='error')increment('consoleErrors');else if(type==='warning'||type==='warn')increment('consoleWarnings');}catch{increment('observationRefusals');}};
 const listeners=[['pageerror',onPageError],['framenavigated',onNavigate],['requestfailed',onRequestFailure],['console',onConsole]];for(const[event,callback]of listeners)page.on(event,callback);
 let closed=false;return {read:()=>({...state,pageErrorClasses:state.pageErrorClasses.map(value=>({...value}))}),close:()=>{if(closed)return;closed=true;for(const[event,callback]of listeners)try{page.off(event,callback);}catch{increment('observationRefusals');}}};
}
export async function evaluateCloneFixture(page,args,record){
 const enabled=own(args[1],'enabled');const operation=enabled===true?'evaluate-candidate':enabled===false?'evaluate-baseline':'evaluate-other';record.lastEvaluation=operation;
 try{return await page.evaluate(...args);}catch(error){record.failureOperation=operation;record.failureDiagnostic=cloneFailureDiagnostic(error);record.privateException=privateCloneException(error);record.privateMessage=privateCloneMessage(error);throw error;}
}
export async function persistCloneAttempt(parent,engine,report){
 if(!['system-chromium','system-firefox'].includes(engine))throw Error('Unsupported owned clone proof engine');
 await mkdir(parent,{recursive:true,mode:0o700});const attempt=path.join(parent,randomUUID());await mkdir(attempt,{mode:0o700});const bytes=JSON.stringify(report,null,2)+'\n';await writeFile(path.join(attempt,engine+'.private.json'),bytes,{flag:'wx',mode:0o600});return bytes;
}
