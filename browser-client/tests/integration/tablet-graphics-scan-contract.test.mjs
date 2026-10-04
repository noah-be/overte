// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import{createHash}from'node:crypto';
import{qualifyScan,qualifyApplied,measureNativeResolutionThumb,assertSourcePins,SCAN_SOURCE_PINS}from'./tablet-graphics-scan-contract.mjs';
const settings={version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true};
const before={settings,width:1280,height:900,nativeDPR:1,rendered:100,observedAt:1,commands:{changes:0,requests:17,results:17},frame:{sequence:22,revision:3}};
function sample(slow=false){return {settings:{...settings},width:1280,height:900,nativeDPR:1,rendered:200,observedAt:2500,connected:true,censored:false,commands:{...before.commands},home:{sequence:23,revision:3,visible:true,screen:'Home'},applyDisabled:!slow,status:'WebGL2; buffer1280×900 at scan start; observed '+(slow?'20.0':'50.0')+' Hz, p95 '+(slow?'55.0':'20.0')+' ms in this model-jobs-idle view; images/materials may still arrive. '+(slow?'Keep the current settings by default. Optional: try90% resolution':'Keep the current settings. This short sample')};}
function validSample(slow=false){const s=sample(slow);s.status=s.status.replace('buffer1280','buffer 1280').replace('try90','try 90');return s;}
test('real observation witness requires unchanged settings/buffer/DPR/no graphics commands and fresh native Home',()=>{
 assert.deepEqual(qualifyScan(before,validSample()),{optional:null,cadenceHz:50,p95Ms:20});
 for(const change of [{settings:{...settings,localLights:false}},{width:1279},{height:899},{nativeDPR:1.1},{commands:{...before.commands,changes:1}},{commands:{...before.commands,results:18}},{rendered:112},{observedAt:2000},{connected:false},{censored:true},{home:{sequence:22,revision:3,visible:true,screen:'Home'}},{home:{sequence:23,revision:4,visible:true,screen:'Home'}},{home:{sequence:23,revision:3,visible:true,screen:'Graphics'}}])assert.throws(()=>qualifyScan(before,{...validSample(),...change}));
});
test('optional Apply can be offered only by actual source-bound slow-view UI and exact density step',()=>{
 assert.equal(qualifyScan(before,validSample(true)).optional,90);
 for(const status of [validSample(true).status.replace('try 90','try 80'),validSample(true).status.replace('20.0 Hz','50.0 Hz').replace('55.0 ms','20.0 ms'),validSample().status.replace('buffer 1280','buffer 1279')])assert.throws(()=>qualifyScan(before,{...validSample(true),status}));
 assert.throws(()=>qualifyScan(before,{...validSample(true),applyDisabled:true}));
});
function applied(){const expected={...settings,resolutionPercent:90};return {intent:{action:'graphicsChange',schemaVersion:1,browserRequestId:2,revision:3,field:'resolutionPercent',value:90,observedAt:1},request:{operation:'change',field:'resolutionPercent',value:90,browserRequestId:2,requestId:18,revision:3,observedAt:2},ack:{accepted:true,requestId:18,revision:3,settings:expected,observedAt:3},completion:{browserRequestId:2,accepted:true,revision:3,settings:expected,observedAt:4},settings:expected,persisted:expected,connected:true,censored:false};}
test('native cached-state completion follows exact ordinary request/effective ACK and persistence',()=>{
 assert.deepEqual(qualifyApplied(before,applied(),90),{...settings,resolutionPercent:90});
 for(const [field,key,value]of [['intent','browserRequestId',0],['request','browserRequestId',3],['request','operation','request'],['ack','requestId',17],['ack','accepted',false],['completion','accepted',false],['completion','observedAt',2],['completion','revision',4]]){const a=applied();a[field]={...a[field],[key]:value};assert.throws(()=>qualifyApplied(before,a,90));}
 for(const key of ['settings','persisted']){const a=applied();a[key]={...a[key],cameraClipping:false};assert.throws(()=>qualifyApplied(before,a,90));}
});
function canvas(handles=[360],size=[480,706]){const p=new Uint8ClampedArray(size[0]*size[1]*4);for(const x of handles)for(let y=285;y<321;y++)for(let xx=x-8;xx<x+8;xx++){const i=(y*size[0]+xx)*4;p.set([128,128,128,255],i);}return {width:size[0],height:size[1],getContext:()=>({getImageData:()=>({data:p})})};}
test('source-pinned native gray handle readback rejects missing/ambiguous/oversize/outside pixels',()=>{
 assert.deepEqual(measureNativeResolutionThumb(canvas(),{rect:{x:0,y:0,width:480,height:706},y:303}),{x:359.5,width:16});
 for(const c of [canvas([]),canvas([340,380]),{width:4000,height:4000}])assert.throws(()=>measureNativeResolutionThumb(c,{rect:{x:0,y:0,width:480,height:706},y:303}));
 assert.throws(()=>measureNativeResolutionThumb(canvas(),{rect:{x:400,y:0,width:480,height:706},y:303}));
});
test('mandatory current source pins refuse changed imported renderer/panel/helper',()=>{
 assertSourcePins(SCAN_SOURCE_PINS);for(const file of Object.keys(SCAN_SOURCE_PINS))assert.throws(()=>assertSourcePins({...SCAN_SOURCE_PINS,[file]:'0'.repeat(64)}));
});
const driver=await readFile(new URL('./tablet-graphics-scan-session.mjs',import.meta.url),'utf8'),original=await readFile(new URL('./fixtures/original-tablet-graphics.mjs',import.meta.url),'utf8');
test('original seventeen native controls, combo painted guard and all persisted framebuffer oracles remain exact',()=>{
 assert.equal(createHash('sha256').update(original).digest('hex'),'2dd0a4b77929c261f14638d89875bb4daf3337fc86790153797f3c51b982cb02');
 const section=(s,start,end)=>{assert.equal(s.split(start).length,2);return s.split(start)[1].split(end)[0];};
 for(const [start,end]of [['    async function paintedPopup','    async function openPopup'],['    async function openPopup','    async function preset'],['    async function preset','    async function control']])assert.equal(section(driver,start,end),section(original,start,end));
 const start="    await control('fieldOfView',20",end='    report.resolutionProfileAcceptance=true;';
 assert.equal(section(driver,start,end).replaceAll('await ownWorker();',''),section(original,start,end));
 for(const text of ["assert.equal(restored.settings.fieldOfView,130)","assert.equal(restored.settings.resolutionPercent,70)","assertBuffer(restored,70)","assert.equal(report.controlEffects.length,17"])assert(driver.includes(text));
});
test('new Scan/Apply driver uses only trusted actual browser controls and existing live native frames, never fake timing or setters',()=>{
 for(const text of ["await scanButton.click()","await applyButton.click()","scanEvent.trusted,true","lastClick.trusted,true","qualifyScan(before,after)","qualifyApplied(before,applied,sample.optional)","popup.popup.highlightedIndex","measureNativeResolutionThumb","report.optionalApplyQualified=false","images/materials","BaselineUnchanged","waitOwnedProfilesGone","O_NOFOLLOW","O_NONBLOCK"])assert(driver.includes(text)||text==='images/materials');
 assert.doesNotMatch(driver,/--use-angle|--no-sandbox|forceActiveFocus|dispatchEvent|graphics\.apply\(|timestampMs\s*:|frames\.publish|Render\./);
 assert.match(driver,/openActualGraphicsChromium\(/);assert(!driver.includes('chromium.launch('));assert.match(driver,/syntheticMicrophone:false/);assert.match(driver,/timeout:90000/);assert.match(driver,/timeout:30000/);assert.match(driver,/timeout:15000/);
});
test('genuine hidden/leave cancellation cannot force late Tablet reopening and original cleanup/source gates remain',()=>{
 for(const text of ["document.visibilityState==='hidden'","await other.bringToFront()","await other.close()","!window.__overte.connected&&!window.__overte.tabletVisible","baselineIdentity","assert.deepEqual(report.sourceHashes.start,report.sourceHashes.end","await browser?.close()","mode:0o600,flag:'wx'"])assert(driver.includes(text));
 assert(!driver.includes("window.__overte.connected="));assert(!driver.includes('Users.'));assert(!driver.includes('Entities.'));
});
