// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Execute actual authored diagnostic functions without importing a browser.
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {stripTypeScriptTypes} from 'node:module';import vm from 'node:vm';
const fixture=await readFile(new URL('./fixtures/embedded-world.ts',import.meta.url),'utf8'),launcher=await readFile(new URL('./integration/embedded-world.mjs',import.meta.url),'utf8');
function marked(source,label){const start=`// BEGIN ${label}`,end=`// END ${label}`;assert.equal(source.split(start).length,2);assert.equal(source.split(end).length,2);const a=source.indexOf(start),z=source.indexOf(end);assert(z>a);return source.slice(a,z);}
const {createEmbeddedDiagnostic,recordEmbeddedFrame,sampleEmbeddedRender,recordEmbeddedContext}=vm.runInNewContext(stripTypeScriptTypes(marked(fixture,'bounded embedded diagnostic'),{mode:'strip'})+';({createEmbeddedDiagnostic,recordEmbeddedFrame,sampleEmbeddedRender,recordEmbeddedContext})');
function consumers(timers={setTimeout,clearTimeout}){return vm.runInNewContext(marked(launcher,'strict fixed-field diagnostic consumer.')+';({validateEmbeddedDiagnostic,collectEmbeddedFailureDiagnostic})',{assert,...timers});}
const {validateEmbeddedDiagnostic,collectEmbeddedFailureDiagnostic}=consumers(),sampler=()=>({version:1,source:{version:1}}),input=()=>JSON.parse(JSON.stringify(createEmbeddedDiagnostic()));
function record(d,frame,state,pixel=[0,0,0,0],calls=0){recordEmbeddedFrame(d,frame,pixel,0,sampler(),sampler(),calls);recordEmbeddedContext(d,state);}

test('actual sampler observes render counters and lost state around exactly one original render with identical arguments',()=>{
 const events=[],scene={},camera={};let currentFrame=7,lost=false;
 const renderer={info:{render:{get frame(){events.push('frame');return currentFrame;}}},render(s,c){events.push('render');assert.equal(s,scene);assert.equal(c,camera);currentFrame++;lost=true;}};
 const gl={isContextLost(){events.push('lost');return lost;},getError(){throw Error('Diagnostic must not consume GL errors');}};
 const row=sampleEmbeddedRender(0,renderer,gl,scene,camera);assert.deepEqual(Array.from(row),[0,7,8,0,1]);assert.deepEqual(events,['frame','lost','render','frame','lost']);
});
test('observed zero-draw context loss preserves original failed RGBA and eleven-column tuple',()=>{
 const d=input();d.phase='gpu-loop';d.decodedRGBA=[255,0,0,255];const renderer={info:{render:{frame:0}},render(){}},gl={isContextLost:()=>true};
 record(d,0,sampleEmbeddedRender(0,renderer,gl,{},{}));assert.deepEqual(Array.from(d.frames[0]),[0,0,0,0,0,0,1,1,1,1,0]);assert.deepEqual(Array.from(d.contextStates[0]),[0,0,0,1,1]);assert.equal(validateEmbeddedDiagnostic(d),d);assert.throws(()=>assert.equal(d.frames[0].slice(1,5).join(','),'255,0,0,255'));
});
test('counter advance with zero draws remains distinct from early return without claiming a cause',()=>{
 const d=input(),renderer={info:{render:{frame:4}},render(){this.info.render.frame++;}},gl={isContextLost:()=>false};record(d,0,sampleEmbeddedRender(0,renderer,gl,{},{}));assert.deepEqual(Array.from(d.contextStates[0]),[0,4,5,0,0]);assert.equal(d.frames[0][10],0);validateEmbeddedDiagnostic(d);
});
test('diagnostic sampling preserves an original render exception and makes no later observation or retry',()=>{
 const failure=Error('Original renderer failure');let calls=0,lostReads=0,frameReads=0;const renderer={info:{render:{get frame(){frameReads++;return 0;}}},render(){calls++;throw failure;}},gl={isContextLost(){lostReads++;return false;}};
 assert.throws(()=>sampleEmbeddedRender(0,renderer,gl,{},{}),e=>e===failure);assert.equal(calls,1);assert.equal(lostReads,1);assert.equal(frameReads,1);
});
test('actual producer bounds both records at20 and owns a copied context row',()=>{
 const d=input();for(let i=0;i<24;i++){const row=[i,i,i+1,0,0];record(d,i,row,[255,0,0,255],1);row[1]=900;}assert.equal(d.frames.length,20);assert.equal(d.contextStates.length,20);assert.equal(d.contextStates[0][1],0);assert.equal(d.contextStates[19][0],19);validateEmbeddedDiagnostic(d);
});
test('strict consumer rejects context privacy fields missing paired rows malformed counters and nonbinary states',()=>{
 const good=input();record(good,0,[0,0,1,0,0]);validateEmbeddedDiagnostic(good);
 for(const mutate of [d=>delete d.contextStates,d=>d.contextStates=[],d=>d.contextStates.push([1,1,2,0,0]),d=>d.contextStates[0].push('private'),d=>d.contextStates[0][0]=1,d=>d.contextStates[0][1]=-1,d=>d.contextStates[0][2]=NaN,d=>d.contextStates[0][1]=1000001,d=>d.contextStates[0][3]=true,d=>d.contextStates[0][4]=2,d=>d.contextStates[0][4]='0',d=>d.secret='private',d=>d.version=1]){const d=structuredClone(good);mutate(d);assert.throws(()=>validateEmbeddedDiagnostic(d));}
});
test('strict current consumer retains phase RGBA upload-version and original frame bounds',()=>{
 const good=input();record(good,0,[0,0,1,0,0]);for(const mutate of [d=>d.phase='private',d=>d.decodedRGBA=[256,0,0,255],d=>d.frames[0][5]=-1,d=>d.frames[0][9]=1000001,d=>d.frames[0][10]=NaN,d=>d.frames[0][0]=1,d=>d.frames=Array(21).fill(d.frames[0])]){const d=structuredClone(good);mutate(d);assert.throws(()=>validateEmbeddedDiagnostic(d));}
});
test('actual current collection skips all RPC after original30s deadline',async()=>{let calls=0;const result=await collectEmbeddedFailureDiagnostic({evaluate(){calls++;throw Error('Forbidden after deadline');}},'Embedded World fixture exceeded 30 seconds');assert.equal(calls,0);assert.equal(result.pixelDiagnosticRefusal,'original-fixture-deadline');});
test('actual current500ms refusal clears its timer and consumes a late rejection without a second read',async()=>{
 let expire,cleared=0,scheduled=0,reject,calls=0;const unhandled=[],listener=e=>unhandled.push(e);process.on('unhandledRejection',listener);
 try{const {collectEmbeddedFailureDiagnostic:collect}=consumers({setTimeout(fn,ms){expire=fn;scheduled=ms;return 31;},clearTimeout(timer){assert.equal(timer,31);cleared++;}});const pending=collect({evaluate(){calls++;return new Promise((_,no)=>{reject=no;});}},'Actual GPU embedded pixels changed');await new Promise(done=>setImmediate(done));assert.equal(scheduled,500);expire();const result=await pending;assert.equal(result.pixelDiagnosticRefusal,'unavailable-or-invalid');assert.equal(cleared,1);reject(Error('Late evaluation'));await new Promise(done=>setImmediate(done));assert.equal(unhandled.length,0);assert.equal(calls,1);}finally{process.off('unhandledRejection',listener);}
});
test('actual current collection accepts only the paired bounded data and preserves consumer refusal',async()=>{const good=input();record(good,0,[0,0,1,0,0]);const result=await collectEmbeddedFailureDiagnostic({evaluate:()=>good},'Original failure');assert.equal(result.pixelDiagnostic,good);const bad=structuredClone(good);bad.contextStates[0][4]=true;const refused=await collectEmbeddedFailureDiagnostic({evaluate:()=>bad},'Original failure');assert.equal(refused.pixelDiagnosticRefusal,'unavailable-or-invalid');});
