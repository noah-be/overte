// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {installQmlTextInputFixture} from './fixtures/tablet-qml-text-context.mjs';
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import vm from 'node:vm';
function navigationTablet(context,config){
 const helper=context.createBrowserTablet(config),receive=helper.receive;let sequence=0,navigationSequence=0;
 helper.receive=message=>{sequence++;if(['open','home','back','close'].includes(message.action))navigationSequence=sequence;receive({sequence,navigationSequence,...message});};return helper;
}
import {createHash} from 'node:crypto';
const native=await readFile(new URL('./native-tablet.js',import.meta.url),'utf8');
const qml=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
const wrapper=JSON.parse(await readFile(new URL('./fixtures/native-qml-window-2026.04.1.json',import.meta.url),'utf8')).source;
test('native asynchronous wrapper fixture is exact release2026.04.1 source f91d15a',()=>{assert.equal(createHash('sha256').update(wrapper).digest('hex'),'ede803f5d3e8787febb898d1a395306b2f6f81b80ab8013034027c068a861866');});
const wrapperDispatch=wrapper.match(/function fromScript\(message\) \{[\s\S]*?\n    \}/)[0];
// Execute the complete current dispatch dependencies. The real dispatcher now
// selects an engine-owned tablet grab or the separately tested private-root
// overload; omitting that production function raises a caught ReferenceError.
const qmlDispatch=['completePrivateGrab','grabOwned','fromScript'].map(name=>{
 const match=qml.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));
 assert(match,'Current QML dispatch dependency '+name);return match[0];
}).join('\n');
function signal(){const handlers=new Set();return {connect:fn=>handlers.add(fn),disconnect:fn=>handlers.delete(fn),emit:value=>{for(const fn of handlers)fn(value);}};}
function driver(){
 let now=0,tick,closed=0;const fromQml=signal(),screens=signal(),sent=[],commands=[],gpu=[],settings=new Map();
 const item={width:480,height:706,grabToImage:callback=>{gpu.push(callback);return true;}},tablet={mapToItem:()=>({x:0,y:0}),width:480,height:706};
 const ui=vm.createContext({target:()=>item,topRoot:()=>({}),find:()=>tablet,captureSurface:'tablet',captureTarget:null,activeCapture:null,privateGrab:null,pointerSurface:null,inputSurface:null,savedSurface:null,cancelPointer:()=>{},sendToScript:value=>fromQml.emit(value)});vm.runInContext(qmlDispatch,ui);installQmlTextInputFixture(qml,ui);
 const root={dynamicContent:null},windowContext=vm.createContext({root});vm.runInContext(wrapperDispatch,windowContext);
 const context=vm.createContext({Settings:{getValue:(key,fallback)=>settings.get(key)??fallback,setValue:(key,value)=>settings.set(key,value)},Tablet:{getTablet:()=>({screenChanged:screens,loadQMLSource:()=>{},returnToPreviousApp:()=>{}})},OverlayWindow:function(){this.fromQml=fromQml;this.sendToQml=value=>{commands.push(value);windowContext.fromScript(value);};this.close=()=>closed++;},Audio:{muted:true},Date:{now:()=>now},Script:{load:()=>{},setTimeout:()=>{},setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{}}});vm.runInContext(native,context);
 const helper=navigationTablet(context,{qmlURL:'file:///private/capture.qml',framePath:'/private/frame',defaultScriptsURL:'file:///installed/defaultScripts.js',send:value=>sent.push(value)});
 return {helper,commands,sent,gpu,ui,fromQml,tick:()=>tick(),now:value=>now=value,load:()=>{root.dynamicContent=ui;},complete:()=>gpu.shift()({saveToFile:()=>true}),closed:()=>closed};
}
test('pinned release wrapper silently drops initial messages; production probe retries until actual capture Item ack',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();assert.equal(d.gpu.length,0);assert.equal(d.commands.at(-1).kind,'readyProbe');const probe=d.commands.at(-1).probe;
 for(let i=1;i<20;i++){d.now(i*150);d.tick();assert.equal(d.commands.at(-1).probe,probe);assert.equal(d.gpu.length,0);}
 d.load();d.now(3000);d.tick();assert.equal(d.gpu.length,1);assert.equal(d.commands.at(-1).kind,'capture');assert.equal(d.commands.filter(c=>c.kind==='capture').length,1);d.complete();d.tick();assert.equal(d.sent.filter(v=>v.kind==='frameReady').length,1);d.helper.close();
});
test('probe and cold GPU share original30s deadline, delayed loading cannot grant another30s',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();d.now(29000);d.load();d.tick();assert.equal(d.gpu.length,1);d.now(30000);d.tick();d.tick();assert.match(d.sent.find(v=>v.kind==='error').message,/30 seconds/);d.complete();d.tick();assert.equal(d.sent.filter(v=>v.kind==='frameReady').length,0);d.helper.close();
});
test('no helper ack times out without any GPU allocation; explicit Home retries with fresh bounded probe',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();const old=d.commands.at(-1);d.now(30000);d.tick();d.tick();assert.equal(d.gpu.length,0);assert.match(d.sent.find(v=>v.kind==='error').message,/30 seconds/);const count=d.commands.length;d.now(90000);d.tick();assert.equal(d.commands.length,count);d.helper.receive({action:'home',revision:1});d.tick();assert(d.commands.at(-1).probe>old.probe);d.fromQml.emit({kind:'helperReady',revision:1,probe:old.probe});d.tick();assert.equal(d.gpu.length,0);d.load();d.tick();assert.equal(d.gpu.length,1);d.helper.close();
});
test('wrong revision/nonce, revoked or closed acknowledgements cannot authorize capture',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();const old=d.commands.at(-1);for(const value of [{kind:'helperReady',revision:2,probe:old.probe},{kind:'helperReady',revision:1,probe:old.probe+1}]){d.fromQml.emit(value);d.tick();assert.equal(d.gpu.length,0);}
 d.helper.setAuthority(2,false);d.fromQml.emit({kind:'helperReady',revision:1,probe:old.probe});d.tick();assert.equal(d.gpu.length,0);d.helper.setAuthority(3,true);d.helper.receive({action:'open',revision:3});d.tick();const current=d.commands.at(-1);assert(current.probe>old.probe);d.fromQml.emit({kind:'helperReady',revision:1,probe:old.probe});d.tick();assert.equal(d.gpu.length,0);d.helper.close();d.fromQml.emit({kind:'helperReady',revision:3,probe:current.probe});const count=d.commands.length;d.tick();assert.equal(d.commands.length,count);assert.equal(d.closed(),1);
});
test('100 rapid Home/back actions before loading do not reset totalcold budget or allocate a grab',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();for(let i=0;i<100;i++){d.now(i*150);d.helper.receive({action:i%2?'home':'back',revision:1});d.tick();}assert.equal(d.gpu.length,0);d.now(30000);d.tick();d.tick();assert.match(d.sent.find(v=>v.kind==='error').message,/30 seconds/);d.helper.close();
});
test('closing pre-load UI cancels old ack; a later explicit open receives a fresh30s budget',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.tick();const old=d.commands.at(-1);d.helper.receive({action:'close',revision:1});d.now(60000);d.fromQml.emit({kind:'helperReady',revision:1,probe:old.probe});d.helper.receive({action:'open',revision:1});d.tick();assert.equal(d.commands.at(-1).kind,'readyProbe');assert(d.commands.at(-1).probe>old.probe);d.load();d.tick();assert.equal(d.gpu.length,1);assert.equal(d.sent.filter(v=>v.kind==='error').length,0);d.helper.close();
});
test('actual QML readiness handler refuses unbounded or malformed metadata and performs no capture',()=>{
 const d=driver();const replies=[];d.ui.sendToScript=value=>replies.push(value);for(const value of [{revision:0,probe:1},{revision:1,probe:0},{revision:1,probe:1.5},{revision:1,probe:Infinity},{revision:'1',probe:1},{revision:1,probe:Number.MAX_SAFE_INTEGER+1}])d.ui.fromScript({kind:'readyProbe',...value});assert.equal(replies.length,0);assert.equal(d.gpu.length,0);d.ui.fromScript({kind:'readyProbe',revision:2,probe:3});assert.equal(replies.length,1);assert.equal(replies[0].kind,'helperReady');assert.equal(replies[0].revision,2);assert.equal(replies[0].probe,3);d.helper.close();
});
test('first GPU callback arriving after totalcold deadline never forwards even before the timer processes timeout',()=>{
 const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.load();d.tick();d.now(30001);d.complete();d.tick();assert.equal(d.sent.filter(v=>v.kind==='frameReady').length,0);assert.match(d.sent.find(v=>v.kind==='error').message,/30 seconds/);d.helper.close();
});
test('Home/back/open invalidate queued old pixels and cannot restore input from a previous navigation acknowledgement',()=>{
 for(const action of ['home','back','open']){
  const d=driver();d.helper.setAuthority(1,true);d.helper.receive({action:'open',revision:1});d.load();d.tick();const old=d.commands.at(-1);d.complete();
  d.helper.receive({action,revision:1});d.tick();assert.equal(d.sent.filter(value=>value.kind==='frameReady').length,0,'Already saved old pixels are removed from the native outbox');
  const current=d.commands.at(-1);assert(current.navigationSequence>old.navigationSequence);assert.equal(current.kind,'capture');
  d.helper.receive({action:'frameAck',revision:1,frameSequence:old.sequence,navigationSequence:old.navigationSequence,displayed:true});assert(!d.commands.some(value=>value.kind==='displayFrame'));
  d.complete();d.tick();const frame=d.sent.find(value=>value.kind==='frameReady');assert.equal(frame.navigationSequence,current.navigationSequence);
  d.helper.receive({action:'frameAck',revision:1,frameSequence:frame.sequence,navigationSequence:current.navigationSequence,displayed:true});assert.equal(d.commands.at(-1).kind,'displayFrame');d.helper.close();
 }
});
