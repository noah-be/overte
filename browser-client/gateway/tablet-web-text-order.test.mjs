// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Execute actual QML methods with asynchronous WebEngine/Qt boundary controls.
// Not a native GUI proof. Source-owned queue protects asynchronous insert/Tab order.
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
function extract(name){const start=source.indexOf('    function '+name+'('),end=source.indexOf('\n    }',start);assert(start>=0&&end>start);return source.slice(start,end+6);}
const names=['modifiers','button','buttons','focusedItem','observeTextTarget','cancelTextInput','currentTextTarget','failTextInput','queueTextInput','finishTextInput','startWebText','passwordTextValid','continuePasswordText','text','keyCode','cancelPointer','fromScript'];
function setup(){
 const operations=[],errors=[],jobs=[],surface={children:[],objectName:'tabletRoot',shown:true},window={activeFocusItem:null},dom={activeElement:{nodeName:'INPUT',value:'',readOnly:false}};
 const web={parent:surface,url:'https://native-fixture.invalid/owned',runJavaScript:(script,callback)=>jobs.push({script,callback})},focus={parent:web};window.activeFocusItem=focus;
 const context={helper:null,pendingText:null,textInputQueue:[],textInputQueueUnits:0,pointerSurface:null,inputSurface:{item:surface,revision:7,navigationSequence:5,sequence:4,width:480,height:706},savedSurface:null,captureTarget:null,activeCapture:null,
  offscreenWindow:window,topRoot:()=>surface,find:()=>surface,textCommitTimer:{running:false,restart(){this.running=true;},stop(){this.running=false;}},
  Qt:{Key_Tab:9,Key_Return:13,NoModifier:0},nativeInput:{commitText:()=>true,commitWebText:(target,root,text)=>{assert.equal(target,focus);assert.equal(root,web);operations.push(['insert',text]);if(dom.activeElement.readOnly)return false;dom.activeElement.value=text;return true;}},events:{keyClick:(code)=>{operations.push(['key',code]);if(code===9){operations.push(['change',dom.activeElement.value]);dom.activeElement={nodeName:'INPUT',readOnly:true,value:'owned UUID'};}return true;},mousePress:()=>{operations.push(['press']);return true;},mouseRelease:()=>{operations.push(['release']);return true;}},activateClickedEditor(){},sendToScript:message=>errors.push(message)};
 context.helper=context;vm.createContext(context);vm.runInContext(names.map(extract).join('\n'),context);
 const message=(event,patch={})=>({kind:'input',event,revision:7,navigationSequence:5,sequence:4,frameSequence:4,key:'Tab',...patch});
 const complete=()=>{const {script,callback}=jobs.shift();const value=vm.runInNewContext(script,{location:{href:web.url},document:{activeElement:dom.activeElement,execCommand:(command,unused,text)=>{assert.equal(command,'insertText');operations.push(['insert',text]);if(dom.activeElement.readOnly)return false;dom.activeElement.value=text;return true;}}});if(callback)callback(value);};
 return {context,operations,errors,jobs,web,focus,window,surface,dom,message,complete};
}
test('actual QML WebEngine text holds Tab until commit callback then triggers native change on the intended field',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'Unicode Überte 世界'}));const pending=s.context.pendingText;
 s.context.fromScript(s.message('key'));assert.deepEqual(s.operations,[]);assert.equal(s.context.textInputQueue.length,1);
 s.complete();assert.deepEqual(s.operations,[['insert','Unicode Überte 世界'],['key',9],['change','Unicode Überte 世界']]);assert.equal(s.dom.activeElement.readOnly,true);assert.deepEqual(s.errors,[]);assert.equal(s.context.pendingText,null);assert.equal(pending.web,null);assert.equal(pending.focus,null);assert.equal(pending.surface,null);
});
test('consecutive asynchronous commits and pointer inputs retain dispatch order rather than retargeting a later field',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'first'}));s.context.fromScript(s.message('text',{text:'second'}));s.context.fromScript(s.message('press',{button:0,x:.5,y:.5}));s.context.fromScript(s.message('release',{button:0,x:.5,y:.5}));s.complete();assert.deepEqual(s.operations,[['insert','first']]);assert.equal(s.jobs.length,1);s.complete();assert.deepEqual(s.operations,[['insert','first'],['insert','second'],['press'],['release']]);assert.deepEqual(s.errors,[]);
});
for(const kind of ['resetInput','hide'])test('actual '+kind+' immediately revokes queued input and GUI references; late callback cannot replay',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'private canary'}));const pending=s.context.pendingText;s.context.fromScript(s.message('key'));s.context.fromScript({kind});assert.equal(s.context.pendingText,null);assert.equal(s.context.textInputQueue.length,0);assert.equal(s.context.textCommitTimer.running,false);assert.equal(pending.cancelled,true);assert.equal(pending.web,null);assert.equal(pending.focus,null);assert.equal(pending.surface,null);s.jobs.shift().callback(true);assert.deepEqual(s.operations,[]);assert.deepEqual(s.errors,[]);
});
test('timeout fails explicitly with no text leakage and no replay after late success',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'private canary'}));s.context.fromScript(s.message('key'));s.context.failTextInput(s.context.pendingText,'The native text commit did not finish within five seconds.');s.jobs.shift().callback(true);assert.equal(s.errors.length,1);assert.equal(s.errors[0].operation,'input');assert(!JSON.stringify(s.errors).includes('private canary'));assert.deepEqual(s.operations,[]);assert.equal(s.context.textCommitTimer.running,false);assert.match(source,/interval: 5000; repeat: false/);
});
for(const change of ['focus','view-parent','url','revision','navigation'])test('callback rejects changed captured '+change+' without later input',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'owned text'}));s.context.fromScript(s.message('key'));if(change==='focus')s.window.activeFocusItem={};if(change==='view-parent')s.web.parent={};if(change==='url')s.web.url+='-changed';if(change==='revision')s.context.inputSurface.revision++;if(change==='navigation')s.context.inputSurface.navigationSequence++;
 s.jobs.shift().callback(true);assert.equal(s.errors.length,1);assert.deepEqual(s.operations,[]);assert.equal(s.context.pendingText,null);
});
test('queue metadata and text are independently bounded while a WebEngine callback stalls',()=>{
 const s=setup();s.context.fromScript(s.message('text',{text:'secret'}));for(let i=0;i<65;i++)s.context.fromScript(s.message('key'));assert.equal(s.errors.length,1);assert.equal(s.context.pendingText,null);assert.equal(s.context.textInputQueue.length,0);assert.equal(s.context.textInputQueueUnits,0);
 const b=setup();b.context.fromScript(b.message('text',{text:'secret'}));for(let i=0;i<4;i++)b.context.fromScript(b.message('text',{text:'x'.repeat(65536)}));assert.equal(b.errors.length,1);assert.equal(b.context.textInputQueue.length,0);assert(!JSON.stringify(b.errors).includes('secret'));
});
test('readonly, noneditable and changed-document targets explicitly refuse insertion without direct field writes',()=>{
 for(const patch of [{readOnly:true},{disabled:true},{nodeName:'BODY'}]){
  const s=setup();Object.assign(s.dom.activeElement,patch);s.context.fromScript(s.message('text',{text:'visitor text'}));s.context.fromScript(s.message('key'));s.complete();assert.deepEqual(s.operations,[]);assert.equal(s.errors.length,1);
 }
 const s=setup();s.context.fromScript(s.message('text',{text:'visitor text'}));s.web.url+='-navigation';s.complete();assert.equal(s.errors.length,1);assert.deepEqual(s.operations,[]);
});

test('negative control reproduces the prior native empty-name/readonly-next-field outcome',()=>{
 const s=setup();
 const old=extract('text').replace('return startWebText(web,focused,value);', 'web.runJavaScript(\'document.execCommand("insertText",false,\'+JSON.stringify(value)+\');\');return true;');
 vm.runInContext(old,s.context);s.context.fromScript(s.message('text',{text:'own name'}));s.context.fromScript(s.message('key'));
 assert.equal(s.dom.activeElement.readOnly,true);assert.deepEqual(s.operations,[['key',9],['change','']]);s.complete();assert.deepEqual(s.operations,[['key',9],['change',''],['insert','own name']]);assert.equal(s.dom.activeElement.value,'owned UUID');
});
test('failed pending commit releases an existing held native pointer before clearing queued release',()=>{
 const s=setup();s.context.fromScript(s.message('press',{button:0,x:.5,y:.5}));s.context.fromScript(s.message('text',{text:'owned text'}));s.context.fromScript(s.message('release',{button:0,x:.5,y:.5}));
 s.context.failTextInput(s.context.pendingText,'The native text commit did not finish within five seconds.');assert.equal(s.context.pointerSurface,null);assert.deepEqual(s.operations,[['press'],['release']]);assert.equal(s.context.textInputQueue.length,0);
});
