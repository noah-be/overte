// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {embeddingOrigins,embeddingDocument,qualifyEmbedding,qualifyDeniedProbe,qualifyCanvasWire,fixtureCallbacks,SOURCE_PINS,AUTHORED_FIXTURE_SOURCE,sha} from './fullscreen-embedding-contract.mjs';
test('two exact owned loopback origins differ without new service, credentials or external requests',()=>{
 assert.deepEqual(embeddingOrigins('http://127.0.0.1:5187/'),{parent:'http://127.0.0.1:5187',child:'http://localhost:5187'});
 for(const u of ['http://localhost:5187/','https://127.0.0.1:5187/','http://secret@127.0.0.1:5187/','http://127.0.0.1:5187/?secret=1','http://127.0.0.1:5187/#fragment','http://127.0.0.1/','http://external.invalid:5187/'])assert.throws(()=>embeddingOrigins(u));
 const origins=embeddingOrigins('http://127.0.0.1:5187/');assert(!embeddingDocument(origins,false).body.includes('allowfullscreen'));assert(!embeddingDocument(origins,false).body.includes('allow='));assert(embeddingDocument(origins,true).body.includes('allowfullscreen'));assert(!embeddingDocument(origins,false).body.includes('sandbox'));assert.throws(()=>embeddingDocument({...origins,child:origins.parent},false));assert.throws(()=>embeddingDocument({...origins,child:'http://localhost:5188'},false));
});
function observation(delegated=false){return {crossOrigin:true,visible:true,connected:true,delegated,extraAllow:false,fullscreenEnabled:delegated,none:true,parentNone:true,buttonDisabled:!delegated,warning:!delegated,pixel:[40,80,100,255],ratio:480/706};}
test('actual embedding negative requires real denied capability, painted warning/input scope and both owner states',()=>{
 qualifyEmbedding(observation(),false);qualifyEmbedding(observation(true),true);
 for(const change of [{crossOrigin:false},{visible:false},{connected:false},{delegated:true},{extraAllow:true},{fullscreenEnabled:true},{none:false},{parentNone:false},{buttonDisabled:false},{warning:false},{pixel:[40,80,99,255]},{ratio:1}])assert.throws(()=>qualifyEmbedding({...observation(),...change},false));
 assert.throws(()=>qualifyEmbedding(observation(),true));
});
test('genuine trusted requestFullscreen TypeError is qualified only for exactly one connected current visible denied target',()=>{
 const p={trusted:true,calls:1,visible:true,connected:true,enabled:false,rejected:true,name:'TypeError',none:true};qualifyDeniedProbe(p);for(const change of [{trusted:false},{calls:2},{visible:false},{connected:false},{enabled:true},{rejected:false},{name:'UnknownError'},{none:false}])assert.throws(()=>qualifyDeniedProbe({...p,...change}));
});
test('unchanged native fixture coordinates/revision/frame and both real trusted pointer events remain mandatory',()=>{
 const input={revision:1,frameSequence:1,button:0,x:.5,y:.5},p={inputs:[{...input,event:'press'},{...input,event:'release'}],none:true},events=[{type:'pointerdown',trusted:true,button:0},{type:'pointerup',trusted:true,button:0}],bounds={width:480,height:706};qualifyCanvasWire(p,bounds,events);
 for(const field of ['revision','frameSequence','button','x','y']){const bad=structuredClone(p);bad.inputs[0][field]=field==='x'||field==='y'?.6:2;assert.throws(()=>qualifyCanvasWire(bad,bounds,events));}assert.throws(()=>qualifyCanvasWire({...p,inputs:[p.inputs[0]]},bounds,events));assert.throws(()=>qualifyCanvasWire(p,bounds,[{...events[0],trusted:false},events[1]]));assert.throws(()=>qualifyCanvasWire({...p,none:false},bounds,events));
});
test('exact historical authored callback is extracted and corrected active spec separately pinned; any callback modification refuses',async()=>{
 const active=await readFile(new URL('../tablet-fullscreen.browser.spec.ts',import.meta.url),'utf8');assert.equal(sha(active),SOURCE_PINS['tests/tablet-fullscreen.browser.spec.ts']);assert.throws(()=>fixtureCallbacks(active));const source=await readFile(new URL('../../'+AUTHORED_FIXTURE_SOURCE,import.meta.url),'utf8');assert.equal(sha(source),SOURCE_PINS[AUTHORED_FIXTURE_SOURCE]);const c=fixtureCallbacks(source);assert(c.install.toString().includes('new BrowserTablet'));assert(c.install.toString().includes('navigationSequence'));assert(c.proof.toString().includes('getImageData'));assert.throws(()=>fixtureCallbacks(source+'\n'));
});
test('runner uses actual cross-origin Frame, trusted driver input/API, fixed routes and original ten/forty-five-second gates',async()=>{
 const s=await readFile(new URL('./fullscreen-embedding-stock.mjs',import.meta.url),'utf8');for(const v of ['page.frames().find','await frame.evaluate(callbacks.install)','qualifyEmbedding(before,delegated)','await page.mouse.click','qualifyCanvasWire','await probe.click()','host.requestFullscreen()','qualifyDeniedProbe(denied)',"await clickNamed(frame,'Fullscreen')","await clickNamed(frame,'Exit fullscreen')",'headless:false','defaultViewport:null','originalFourBodiesExecuted:false','headerNegativeRequalified:false','await browser.close()','timeout:10000','actualCaseDeadline','sourceCoherent'])assert(s.includes(v));assert(!/dispatchEvent|Object.defineProperty|fullscreenEnabled\s*=|fullscreenElement\s*=[^=]|setDeviceMetricsOverride|setFocusEmulationEnabled|--no-sandbox|--use-angle/.test(s));assert(s.includes("'focusmanager.testmode':false"));assert(!s.includes('setViewport('));assert(s.includes('if(firefox)await sizeSystemFirefoxWindow'));
});
