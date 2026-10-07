// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFile} from 'node:fs/promises';import {createHash}from'node:crypto';
import {instrumentGraphicsGenerated,instrumentGraphicsCapture,parseGraphicsStateAudit,GRAPHICS_STATE_PREFIX,GRAPHICS_CAPTURE_PREFIX} from './tablet-graphics-state-audit.mjs';
import {buildBrowserGraphicsOverrides,GRAPHICS_SOURCE_SHA256} from '../../gateway/browser-graphics-overrides.mjs';
const native=JSON.parse(await readFile(new URL('../fixtures/native-graphics-2026.04.1/sources.json',import.meta.url),'utf8')).files;
const qml=await readFile(new URL('../../gateway/tablet-capture.qml',import.meta.url),'utf8');
const original=buildBrowserGraphicsOverrides(native,'overte.browser.graphics.'+'1'.repeat(32)),generated=instrumentGraphicsGenerated(original);
const func=(s,n)=>{const start=s.indexOf('function '+n+'(');assert(start>=0);let braces=0,quote='';for(let i=s.indexOf('{',start);i<s.length;i++){const c=s[i];if(quote){if(c==='\\')i++;else if(c===quote)quote='';continue;}if(c==='"'||c==="'"){quote=c;continue;}if(c==='{')braces++;if(c==='}'&&--braces===0)return s.slice(start,i+1);}throw Error('Missing function');};
test('six exact pinned native inputs; copied package changes only three QML observers and never original JS/channel handler',()=>{
 for(const [name,sha]of Object.entries(GRAPHICS_SOURCE_SHA256))assert.equal(createHash('sha256').update(native[name]).digest('hex'),sha);
 for(const name of ['settings.js','qml/SettingSlider.qml','qml/SettingBoolean.qml'])assert.equal(generated[name],original[name]);
 for(const name of ['Settings.qml','qml/pages/GraphicsSettings.qml','qml/SettingComboBox.qml']){assert(generated[name].includes(GRAPHICS_STATE_PREFIX));assert.throws(()=>instrumentGraphicsGenerated({...original,[name]:generated[name]}));}
 assert.throws(()=>instrumentGraphicsGenerated({...original,'Settings.qml':'unknown'}));
 assert.doesNotMatch(Object.values(generated).join('\n'),/Qt\.callLater|Timer\s*\{|forceActiveFocus|runJavaScript/);
});
test('actual authored setOptionIndex remains one assignment with identical user change publication; before/after exposes reset without repairing it',()=>{
 const execute=s=>{const log=[],c=vm.createContext({graphicsAuditCount:0,settingText:'Resolution preset',optionIndex:3,visible:true,enabled:true,console:{log:x=>log.push(x)}});let current=0,changes=[];c.control={highlightedIndex:0,popup:{visible:false}};Object.defineProperty(c.control,'currentIndex',{get:()=>current,set:v=>{current=v;changes.push(v);}});if(s.includes(GRAPHICS_STATE_PREFIX))vm.runInContext(func(s,'graphicsAudit'),c);vm.runInContext(func(s,'setOptionIndex'),c);c.setOptionIndex(3);assert.equal(current,3);return {changes,records:parseGraphicsStateAudit(log.join('\n')).records,c,log};};
 assert.deepEqual(execute(original['qml/SettingComboBox.qml']).changes,execute(generated['qml/SettingComboBox.qml']).changes);
 const value=execute(generated['qml/SettingComboBox.qml']);assert.deepEqual(value.records.map(r=>[r.reason,r.currentIndex]),[['set-before',0],['set-after',3]]);
 value.c.control.currentIndex=0;value.c.graphicsAudit('index-after');assert.equal(parseGraphicsStateAudit(value.log.join('\n')).records.at(-1).currentIndex,0,'A later native reset is reported, never corrected by diagnostics');
});
test('diagnostic console failure cannot suppress existing authored combo assignment',()=>{
 const c=vm.createContext({graphicsAuditCount:0,settingText:'Resolution preset',optionIndex:3,visible:true,enabled:true,control:{currentIndex:0,highlightedIndex:0,popup:{visible:false}},console:{log:()=>{throw Error('observer failure');}}});vm.runInContext(func(generated['qml/SettingComboBox.qml'],'graphicsAudit')+'\n'+func(generated['qml/SettingComboBox.qml'],'setOptionIndex'),c);c.setOptionIndex(3);assert.equal(c.control.currentIndex,3);
});
test('effective/state observers preserve original ready=false -> assignment -> ready=effective sequence and authentic widget updates',()=>{
 const body=s=>s.match(/case "browserGraphicsState":\n\s+([^\n]+)break;/)[1];
 for(const s of [original['Settings.qml'],generated['Settings.qml']]){const order=[],c=vm.createContext({graphicsAudit:()=>{},message:{ready:true,settings:{resolutionPercent:70},message:''}});for(const key of ['browserGraphicsReady','browserGraphicsState','browserGraphicsMessage'])Object.defineProperty(c,key,{set:v=>order.push([key,v])});vm.runInContext(body(s),c);assert.deepEqual(order,[['browserGraphicsReady',false],['browserGraphicsState',{resolutionPercent:70}],['browserGraphicsMessage',''],['browserGraphicsReady',true]]);}
 const body2=s=>s.match(/onBrowserStateChanged: \{([^\n]+)\}/)[1];for(const s of [original['qml/pages/GraphicsSettings.qml'],generated['qml/pages/GraphicsSettings.qml']]){const calls=[],c=vm.createContext({graphicsAudit:()=>{},localLightsControl:{update:()=>calls.push('lights')},clippingControl:{update:()=>calls.push('clipping')},resolutionProfileControl:{setOptionIndex:x=>calls.push(x)},resolutionProfileIndex:()=>3});vm.runInContext(body2(s),c);assert.deepEqual(calls,['lights','clipping',3]);}
});
test('actual capture observer reports fixed ready70/current0 mismatch with exact capture-attempt owner, no labels/paths/passwords',()=>{
 const logs=[],combo={visible:true,children:[],currentIndex:0,highlightedIndex:0,enabled:true,activeFocus:true,popup:{visible:true,opened:true},toString:()=> 'ComboBox_QMLTYPE_12(0xsecret, private-caption)'},page={visible:true,browserReady:true,browserState:{resolutionPercent:70,fieldOfView:70},resolutionProfileIndex:()=>{throw Error('Must not invoke');},children:[combo]},top={visible:true,children:[page]};
 const c=vm.createContext({graphicsCaptureAuditCount:0,topRoot:()=>top,console:{log:x=>logs.push(x)}});vm.runInContext(func(instrumentGraphicsCapture(qml),'graphicsCaptureAudit'),c);c.graphicsCaptureAudit(top,{sequence:56,revision:1,navigationSequence:7});const x=parseGraphicsStateAudit(logs.join('\n')).records[0];assert.equal(x.pages[0].ready,true);assert.equal(x.pages[0].resolutionPercent,70);assert.equal(x.controls[0].currentIndex,0);assert.equal(x.sequence,56);assert.equal(x.navigationSequence,7);assert(!logs[0].includes('secret'));assert(!logs[0].includes('caption'));assert(!logs[0].includes('url'));
 assert.equal(instrumentGraphicsCapture(qml).split('graphicsCaptureAudit(item,message);').length,2);assert.throws(()=>instrumentGraphicsCapture(instrumentGraphicsCapture(qml)));
});
test('capture/transition count and traversal bounds are censored honestly; malformed records refuse; unknown envelope data never projected',()=>{
 const logs=[],node={visible:true,currentIndex:0,highlightedIndex:0,popup:{visible:false,opened:false},enabled:true,activeFocus:false,children:[],toString:()=> 'QQuickComboBox'},top={visible:true,children:Array(300).fill(node)};
 const c=vm.createContext({graphicsCaptureAuditCount:0,topRoot:()=>top,console:{log:x=>logs.push(x)}});vm.runInContext(func(instrumentGraphicsCapture(qml),'graphicsCaptureAudit'),c);for(let i=0;i<300;i++)c.graphicsCaptureAudit(top,{sequence:i+1,revision:1,navigationSequence:1});assert.equal(logs.length,256);const parsed=parseGraphicsStateAudit(logs.join('\n'));assert.equal(parsed.censored,true);assert.equal(parsed.records[0].truncated,true);assert.equal(parsed.records[0].controls.length,4);
 const base={scope:'settings',ordinal:1,reason:'effective-after',ready:true,resolutionPercent:70,fieldOfView:70,graphicsPage:true,password:'secret',path:'/private'};const p=parseGraphicsStateAudit(GRAPHICS_STATE_PREFIX+JSON.stringify(base));assert(!JSON.stringify(p).includes('secret'));assert(!JSON.stringify(p).includes('/private'));
 for(const changes of [{ordinal:257},{reason:'remote-eval'},{scope:'secret'},{resolutionPercent:'secret'}])assert.throws(()=>parseGraphicsStateAudit(GRAPHICS_STATE_PREFIX+JSON.stringify({...base,...changes})));
 assert.throws(()=>parseGraphicsStateAudit('x'.repeat(4*1024*1024+1)));assert.throws(()=>parseGraphicsStateAudit(GRAPHICS_CAPTURE_PREFIX+'{}'));
});
test('copied runner preserves original control/popup bodies/deadlines except passive pre-cleanup read, no retry or native state setters',async()=>{
 const source=await readFile(new URL('./tablet-graphics-scan-state-audit.mjs',import.meta.url),'utf8'),root=await readFile(new URL('./tablet-graphics-scan-session.mjs',import.meta.url),'utf8');
 const section=(s,a,b)=>s.split(a)[1].split(b)[0];for(const[a,b]of [['    async function paintedPopup','    async function openPopup'],['    async function openPopup','    async function preset'],['    async function preset','    async function control']])assert.equal(section(source,a,b),section(root,a,b));
 const start="    await control('fieldOfView',20",end='    report.resolutionProfileAcceptance=true;';assert.equal(section(source,start,end).replace('await saveNativeGraphicsAudit();',''),section(root,start,end));
 assert(source.includes('Exact reviewed diagnostic generated controls'));assert(source.includes('nativeStateAuditReadRefused'));assert(source.includes('try{await saveNativeGraphicsAudit();}'));assert.doesNotMatch(source,/forceActiveFocus|dispatchEvent|Users\.|Entities\.|Render\./);
});
