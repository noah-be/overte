// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exercise authored diagnostic functions without importing the browser fixture.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile as readCurrentFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';import path from 'node:path';
import {recoverCaptureV18Input} from './integration/capture-embedded-context-source-fixture.mjs';
const readFile=async(input,options)=>{const bytes=await readCurrentFile(input),file=input instanceof URL?fileURLToPath(input):path.resolve(input),relative=path.relative(fileURLToPath(new URL('../../',import.meta.url)),file),recovered=await recoverCaptureV18Input(relative,bytes);return typeof options==='string'?recovered.toString(options):recovered;};
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';

const fixture=await readFile(new URL('./fixtures/embedded-world.ts',import.meta.url),'utf8');
const launcher=await readFile(new URL('./integration/embedded-world.mjs',import.meta.url),'utf8');
function marked(source,label){
 const start=`// BEGIN ${label}`,end=`// END ${label}`;
 assert.equal(source.split(start).length,2,'Diagnostic start marker must be unique');
 assert.equal(source.split(end).length,2,'Diagnostic end marker must be unique');
 const a=source.indexOf(start),z=source.indexOf(end);assert(z>a);
 return source.slice(a,z);
}
const producer=stripTypeScriptTypes(marked(fixture,'bounded embedded diagnostic'),{mode:'strip'});
const {createEmbeddedDiagnostic,recordEmbeddedFrame}=vm.runInNewContext(producer+';({createEmbeddedDiagnostic,recordEmbeddedFrame})');
const consumer=marked(launcher,'strict fixed-field diagnostic consumer.');
function functions(timers={setTimeout,clearTimeout}){
 return vm.runInNewContext(consumer+';({validateEmbeddedDiagnostic,boundedEmbeddedDiagnosticRead,collectEmbeddedFailureDiagnostic})',{assert,...timers});
}
const {validateEmbeddedDiagnostic,boundedEmbeddedDiagnosticRead,collectEmbeddedFailureDiagnostic}=functions();
const input=()=>JSON.parse(JSON.stringify(createEmbeddedDiagnostic()));
const sampler=()=>({version:1,source:{version:2}});

test('diagnostic preserves the actual numeric failed RGBA without making the exact pixel assertion pass',()=>{
 const record=input(),pixel=[0,13,29,0];record.phase='gpu-loop';record.decodedRGBA=[255,0,0,255];
 recordEmbeddedFrame(record,0,pixel,1,sampler(),sampler(),1);
 assert.deepEqual(Array.from(record.frames[0]),[0,0,13,29,0,1,1,1,2,2,1]);
 assert.deepEqual(pixel,[0,13,29,0]);assert.throws(()=>assert.equal(pixel.join(','),'255,0,0,255'));
 assert.equal(validateEmbeddedDiagnostic(record),record);
});
test('actual diagnostic producer caps records at the original20 rendered frames',()=>{
 const record=input();for(let frame=0;frame<24;frame++)recordEmbeddedFrame(record,frame,[255,0,0,255],1,sampler(),sampler(),1);
 assert.equal(record.frames.length,20);assert.equal(record.frames[19][0],19);validateEmbeddedDiagnostic(record);
});
test('consumer rejects extra private fields invalid phases and malformed numeric or oversized frame records',()=>{
 for(const change of [r=>r.token='must not leave diagnostics',r=>r.phase='foreign',r=>r.version=2,r=>r.decodedRGBA=[256,0,0,255],r=>r.frames=Array(21).fill([]),r=>r.frames=[[1,0,0,0,0,0,1,1,1,1,1]],r=>r.frames=[[0,0,0,0,0,NaN,1,1,1,1,1]],r=>r.frames=[[0,0,0,0,0,-1,1,1,1,1,1]],r=>r.frames=[[0,0,0,0,0,1000001,1,1,1,1,1]]]){
  const record=input();change(record);assert.throws(()=>validateEmbeddedDiagnostic(record));
 }
});
test('original30s fixture refusal makes zero diagnostic RPC calls',async()=>{
 let calls=0;const result=await collectEmbeddedFailureDiagnostic({evaluate:()=>{calls++;throw Error('must not run');}},'Embedded World fixture exceeded 30 seconds');
 assert.equal(calls,0);assert.equal(result.pixelDiagnosticRefusal,'original-fixture-deadline');
});
test('never-settling RPC has the real500ms timer and reaches final cleanup with primary unchanged',{timeout:3000},async()=>{
 let scheduled,cleared=0,cleaned=false;const primary='Actual GPU embedded pixels changed';
 const {collectEmbeddedFailureDiagnostic:collect}=functions({setTimeout:(callback,ms)=>{scheduled=ms;return setTimeout(callback,ms);},clearTimeout:timer=>{cleared++;clearTimeout(timer);}});
 try{const result=await collect({evaluate:()=>new Promise(()=>{})},primary);assert.equal(result.pixelDiagnosticRefusal,'unavailable-or-invalid');assert.equal(primary,'Actual GPU embedded pixels changed');}
 finally{cleaned=true;}
 assert(cleaned);assert.equal(scheduled,500);assert.equal(cleared,1);
});
test('late resolve and reject remain handled after bounded refusal without a second RPC',{timeout:4000},async()=>{
 for(const rejectLate of [false,true]){
  let resolve,reject,calls=0;const events=[],listener=error=>events.push(error);process.on('unhandledRejection',listener);
  try{
   const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
   const result=await collectEmbeddedFailureDiagnostic({evaluate:()=>{calls++;return promise;}},'original-pixel-failure');
   assert.equal(result.pixelDiagnosticRefusal,'unavailable-or-invalid');assert.equal(calls,1);
   if(rejectLate)reject(Error('late diagnostic'));else resolve(input());
   await new Promise(done=>setImmediate(done));assert.equal(events.length,0);assert.equal(calls,1);
  }finally{process.off('unhandledRejection',listener);}
 }
});
test('settled valid malformed rejected and synchronously throwing reads each clear the secondary timer',async()=>{
 let scheduled=0,cleared=0;const {collectEmbeddedFailureDiagnostic:collect}=functions({setTimeout:(callback,ms)=>{assert.equal(ms,500);scheduled++;return setTimeout(callback,ms);},clearTimeout:timer=>{cleared++;clearTimeout(timer);}});
 const valid=await collect({evaluate:()=>Promise.resolve(input())},'original-pixel-failure');assert.equal(valid.pixelDiagnostic.version,1);
 for(const evaluate of [()=>Promise.resolve({credential:'not exported'}),()=>Promise.reject(Error('private rejection')),()=>{throw Error('synchronous private exception');}]){
  const result=await collect({evaluate},'original-pixel-failure');assert.deepEqual(Object.keys(result),['pixelDiagnosticRefusal']);assert.equal(result.pixelDiagnosticRefusal,'unavailable-or-invalid');
 }
 assert.equal(scheduled,4);assert.equal(cleared,4);
});
