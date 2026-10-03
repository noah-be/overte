// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {installQmlTextInputFixture} from './fixtures/tablet-qml-text-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
function navigationTablet(context,config){
 const helper=context.createBrowserTablet(config),receive=helper.receive;let sequence=0,navigationSequence=0;
 helper.receive=message=>{sequence++;if(['open','home','back','close'].includes(message.action))navigationSequence=sequence;receive({sequence,navigationSequence,...message});};return helper;
}

import {readFile,mkdtemp,writeFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {TabletSession,validateTabletInput} from './tablet.mjs';
const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
function extract(name){const match=source.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));assert(match,name);return match[0];}
function fixture(){
 const actions=[],replies=[],callbacks=[];
 const item=(name,width,height)=>({objectName:name,width,height,visible:true,opacity:1,children:[],grabToImage(callback){callbacks.push(callback);return true;}});
 const attach=(parent,child)=>{parent.children.push(child);child.parent=parent;return child;};
 const top=item('',1280,900),desktop=attach(top,item('desktop',1280,900)),tablet=attach(desktop,item('tabletRoot',480,706)),helper=attach(desktop,item('',1,1));
 const overlay=attach(top,item('',1280,900));overlay.visible=false;attach(overlay,item('',225,144));tablet.mapToItem=target=>target===top?{x:600,y:100}:{x:0,y:0};
 const context=vm.createContext({helper,Controls:{Overlay:{overlay}},captureSurface:'tablet',captureTarget:null,pointerSurface:null,inputSurface:null,savedSurface:null,activeCapture:null,privateGrab:null,
 events:{mouseRelease:()=>true,mousePress:(target,x,y)=>{actions.push(['press',target,x,y]);return true;},mouseMove:(target,x,y)=>{actions.push(['move',target,x,y]);return true;},keyClick:()=>{throw new Error('Native keys must use the owned Application route');}},Qt:{LeftButton:1,Key_Return:13,NoModifier:0},sendToScript:message=>replies.push(message)});
 context.nativeInput={grabPrivateGui:(item,token)=>item.grabToImage(result=>context.completePrivateGrab(token,result)),clickApplicationKey:(surface,key,mods)=>{assert.equal(surface,context.inputSurface.item);assert.equal(mods,0);actions.push(['key',context.keyCode(key)]);return true;}};
 vm.runInContext(['topRoot','find','hasDialog','popupTarget','target','modifiers','button','buttons','keyCode','focusedEditors','activateClickedEditor','cancelPointer','completePrivateGrab','grabOwned','fromScript'].map(extract).join('\n'),context);installQmlTextInputFixture(source,context);
 const capture=(sequence,revision=2)=>{context.fromScript({kind:'capture',revision,sequence,navigationSequence:1,path:'/private/owned.png'});return callbacks.at(-1);};
 const finish=callback=>callback({saveToFile:()=>true});
 const ack=(sequence,revision=2)=>context.fromScript({kind:'displayFrame',sequence,revision,navigationSequence:1});
 const pointer=(sequence,revision=2)=>{context.fromScript({kind:'input',event:'press',revision,navigationSequence:1,frameSequence:sequence,button:0,x:.5,y:.5});context.fromScript({kind:'input',event:'release',revision,navigationSequence:1,frameSequence:sequence,button:0,x:.5,y:.5});};
 return {context,top,tablet,overlay,actions,replies,capture,finish,ack,pointer};
}
test('capture start and completed unseen popup keep the displayed tablet input target until exact ACK',()=>{
 const f=fixture();f.finish(f.capture(1));f.ack(1);f.pointer(1);assert.deepEqual(f.actions.at(-1),['press',f.tablet,240,353]);
 f.overlay.visible=true;const pending=f.capture(2);f.pointer(1);assert.deepEqual(f.actions.at(-1),['press',f.tablet,240,353]);
 f.finish(pending);f.pointer(1);assert.deepEqual(f.actions.at(-1),['press',f.tablet,240,353]);
 f.ack(2);f.pointer(2);assert.deepEqual(f.actions.at(-1),['press',f.top,640,450]);
 const count=f.actions.length;f.pointer(1);assert.equal(f.actions.length,count,'Old canvas coordinates cannot hit the new popup surface');
});
test('wrong sequence or authority cannot commit a surface; recorded dimensions survive later resizing',()=>{
 const f=fixture();f.overlay.visible=true;f.finish(f.capture(4));f.ack(3);f.ack(4,9);f.pointer(4);assert.equal(f.actions.length,0);
 f.ack(4);f.top.width=900;f.top.height=600;f.pointer(4);assert.deepEqual(f.actions.at(-1),['press',f.top,640,450]);
 f.pointer(4,9);assert.equal(f.actions.length,1);
});
test('cancelled or revoked captures cannot restore saved surfaces and pre-display keyboard input has no effects',()=>{
 const f=fixture();f.context.fromScript({kind:'input',event:'key',key:'Enter',revision:2,navigationSequence:1});assert.equal(f.actions.length,0);
 const capture=f.capture(1);f.context.fromScript({kind:'cancelCapture'});f.finish(capture);f.ack(1);f.pointer(1);assert.equal(f.actions.length,0);assert.equal(f.replies.at(-1).cancelled,true);
 f.finish(f.capture(2));f.ack(2);f.context.fromScript({kind:'input',event:'key',key:'Enter',revision:2,navigationSequence:1});assert.deepEqual(f.actions.at(-1),['key',13]);
 f.context.fromScript({kind:'resetInput'});f.ack(2);f.pointer(2);f.context.fromScript({kind:'input',event:'key',key:'Enter',revision:2,navigationSequence:1});assert.equal(f.actions.length,1);
 f.finish(f.capture(3));f.context.fromScript({kind:'hide'});f.ack(3);f.pointer(3);assert.equal(f.actions.length,1);
});
test('protocol requires a real display acknowledgement and bounded pointer source frame',()=>{
 const ack={type:'tablet',action:'frameAck',sequence:1,revision:2,frameSequence:4,displayed:false};assert.deepEqual(validateTabletInput(ack),ack);
 for(const displayed of [undefined,1,'true',null])assert.throws(()=>validateTabletInput({...ack,displayed}));
 const pointer={type:'tablet',action:'input',event:'move',sequence:2,revision:2,frameSequence:4,x:.5,y:.5,button:0,buttons:0,modifiers:0};assert.equal(validateTabletInput(pointer).frameSequence,4);
 for(const frameSequence of [undefined,0,-1,1.5,Infinity,Number.MAX_SAFE_INTEGER+1])assert.throws(()=>validateTabletInput({...pointer,frameSequence}));
});
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
test('real PNG bridge only admits pointer frames actually ACKed; automatic and failed display releases do not commit',async()=>{
 const directory=await mkdtemp(join(tmpdir(),'tablet-display-')),native=[],browser=[];let revision=2;
 const session=new TabletSession({framePath:join(directory,'frame'),sendNative:value=>native.push(value),sendBrowser:value=>browser.push(value),getRevision:()=>revision,isActive:()=>true});let sequence=0;
 const pointer=frameSequence=>{session.receive({type:'tablet',action:'input',event:'press',revision,sequence:++sequence,frameSequence,x:.5,y:.5,button:0,buttons:1,modifiers:0});session.receive({type:'tablet',action:'input',event:'release',revision,sequence:++sequence,frameSequence,x:.5,y:.5,button:0,buttons:0,modifiers:0});};
 const frame=async frameSequence=>{await writeFile(`${session.framePath}.${revision}.${frameSequence}.png`,png);await session.receiveNative({type:'tablet',kind:'frameReady',revision,navigationSequence:session.navigationSequence,sequence:frameSequence,width:1,height:1,surface:'tablet'});};
 const ack=(frameSequence,displayed)=>session.receive({type:'tablet',action:'frameAck',revision,sequence:++sequence,frameSequence,displayed});
 try{
  session.receive({type:'tablet',action:'open',revision,sequence:++sequence});await frame(1);const initial=native.length;pointer(1);assert.equal(native.length,initial);ack(1,true);pointer(1);assert.equal(native.at(-1).action,'input');
  await frame(2);session.releaseFrame(revision,2);assert.equal(native.at(-1).displayed,false);const released=native.length;pointer(2);assert.equal(native.length,released);pointer(1);assert.equal(native.length,released+2);
  await frame(3);ack(3,false);const failed=native.length;pointer(3);assert.equal(native.length,failed);
  await frame(4);ack(2,true);pointer(4);assert.equal(native.length,failed,'Late ACK for released frame cannot approve current frame');
  ack(4,true);pointer(4);assert.equal(native.at(-1).frameSequence,4);
  revision=3;const before=native.length;pointer(4);assert.equal(native.length,before,'Approval change revokes displayed source frame');
 }finally{session.close();await rm(directory,{recursive:true,force:true});}
});
test('actual native helper forwards display commits only for a live completed browser ACK; automatic release and stale revisions do not commit',async()=>{
 const qml=[],timers=[],output=[],handlers=new Set(),screens=new Set();
 const signal=members=>({connect:fn=>members.add(fn),disconnect:fn=>members.delete(fn)});
 const context=vm.createContext({Settings:{getValue:(key,fallback)=>fallback,setValue:()=>{}},
 Tablet:{getTablet:()=>({screenChanged:signal(screens),loadQMLSource:()=>{}})},Audio:{muted:true},
 OverlayWindow:function(){this.fromQml=signal(handlers);this.sendToQml=message=>{qml.push(message);if(message.kind==='readyProbe')for(const handler of handlers)handler({kind:'helperReady',revision:message.revision,probe:message.probe});};this.close=()=>{};},
 Script:{load:()=>{},setTimeout:()=>{},setInterval:fn=>timers.push(fn),clearInterval:()=>{}},Date});
 vm.runInContext(await readFile(new URL('./native-tablet.js',import.meta.url),'utf8'),context);
 const helper=navigationTablet(context,{qmlURL:'file:///private/capture.qml',framePath:'/private/frame',defaultScriptsURL:'file:///installed/defaultScripts.js',send:message=>output.push(message)});
 const tick=()=>timers[0](),finish=frame=>{for(const handler of handlers)handler({kind:'frame',revision:frame.revision,sequence:frame.sequence,navigationSequence:frame.navigationSequence,saved:true,width:480,height:706,surface:'tablet'});tick();};
 helper.setAuthority(2,true);helper.receive({action:'open',revision:2});tick();const first=qml.at(-1);finish(first);
 helper.receive({action:'frameAck',revision:2,frameSequence:first.sequence,displayed:false});assert.equal(qml.filter(value=>value.kind==='displayFrame').length,0);
 tick();const second=qml.at(-1);finish(second);
 helper.receive({action:'frameAck',revision:2,frameSequence:first.sequence,displayed:true});assert.equal(qml.filter(value=>value.kind==='displayFrame').length,0);
 helper.receive({action:'frameAck',revision:2,frameSequence:second.sequence,displayed:true});assert.deepEqual({...qml.at(-1)},{kind:'displayFrame',revision:2,sequence:second.sequence,navigationSequence:second.navigationSequence});
 helper.setAuthority(3,false);assert(qml.some(value=>value.kind==='resetInput'));const count=qml.length;helper.receive({action:'frameAck',revision:2,frameSequence:second.sequence,displayed:true});assert.equal(qml.length,count);helper.close();
});
test('held native drag keeps its owned tablet coordinates across a displayed popup, then releases before the next gesture',()=>{
 const f=fixture();f.finish(f.capture(1));f.ack(1);
 const send=(event,frameSequence,patch={})=>f.context.fromScript({kind:'input',event,revision:2,navigationSequence:1,frameSequence,button:0,x:.5,y:.5,...patch});
 send('press',1);assert.deepEqual(f.actions.at(-1),['press',f.tablet,240,353]);
 f.overlay.visible=true;f.finish(f.capture(2));f.ack(2);send('move',1,{x:.75});assert.deepEqual(f.actions.at(-1),['move',f.tablet,360,353]);
 const held=f.actions.length;send('press',2);assert.equal(f.actions.length,held,'A second gesture cannot steal the active native mouse grab');
 send('release',1);send('press',2);assert.deepEqual(f.actions.at(-1),['press',f.top,640,450]);
 send('cancel',2);assert.equal(f.context.pointerSurface,null);send('press',1);assert.deepEqual(f.actions.at(-1),['press',f.top,640,450],'The old surface cannot start another gesture');
});
test('actual gateway retains one held gesture while current display changes and navigation synchronously cancels it',async()=>{
 const directory=await mkdtemp(join(tmpdir(),'tablet-gesture-')),native=[];const session=new TabletSession({framePath:join(directory,'frame'),sendNative:value=>native.push(value),sendBrowser:()=>{},getRevision:()=>2,isActive:()=>true});let sequence=0;
 const command=value=>session.receive({type:'tablet',revision:2,sequence:++sequence,...value});
 const frame=async id=>{await writeFile(`${session.framePath}.2.${id}.png`,png);await session.receiveNative({type:'tablet',kind:'frameReady',revision:2,navigationSequence:session.navigationSequence,sequence:id,width:1,height:1,surface:'tablet'});command({action:'frameAck',frameSequence:id,displayed:true});};
 const pointer=(event,id)=>command({action:'input',event,frameSequence:id,button:0,buttons:event==='press'?1:0,x:.5,y:.5,modifiers:0});
 try{
  command({action:'open'});await frame(1);pointer('press',1);await frame(2);pointer('move',1);assert.equal(native.at(-1).frameSequence,1);
  const before=native.length;pointer('press',2);assert.equal(native.length,before);pointer('release',1);pointer('press',2);assert.equal(native.at(-1).frameSequence,2);
  pointer('cancel',2);assert.equal(session.pointerFrame,null);pointer('press',1);assert.equal(native.at(-1).event,'cancel');
  pointer('press',2);command({action:'home'});assert.equal(session.pointerFrame,null);assert.equal(session.displayedFrame,0);const navigation=native.length;pointer('release',2);assert.equal(native.length,navigation);
 }finally{session.close();await rm(directory,{recursive:true,force:true});}
});
