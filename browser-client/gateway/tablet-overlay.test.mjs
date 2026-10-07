// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {installQmlTextInputFixture} from './fixtures/tablet-qml-text-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
function extract(name){const result=source.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));assert(result, name);return result[0];}
function fixture(){
 const calls=[],replies=[],callbacks=[];
 function item(name,width,height){return {objectName:name,width,height,visible:true,opacity:1,children:[],grabToImage(callback){calls.push(['grab',this]);callbacks.push(callback);return true;}};}
 function attach(parent,child){parent.children.push(child);child.parent=parent;return child;}
 const top=item('',1280,900),desktop=attach(top,item('desktop',1280,900)),tablet=attach(desktop,item('tabletRoot',480,706));
 tablet.mapToItem=(target)=>target===top?{x:600,y:100}:{x:0,y:0};
 const helper=attach(desktop,item('',1,1)),overlay=attach(top,item('',1280,900)),popup=attach(overlay,item('',225,144));
 const context=vm.createContext({helper,Controls:{Overlay:{overlay}},captureSurface:'tablet',captureTarget:null,pointerSurface:null,inputSurface:null,savedSurface:null,activeCapture:null,privateGrab:null,
 events:{mousePress:(target,x,y)=>{calls.push(['press',target,x,y]);return true;}},Qt:{LeftButton:1},sendToScript:message=>replies.push(message)});
 context.nativeInput={grabPrivateGui:(item,token)=>item.grabToImage(result=>context.completePrivateGrab(token,result))};
 vm.runInContext(['topRoot','find','hasDialog','popupTarget','target','modifiers','button','buttons','cancelPointer','completePrivateGrab','grabOwned','fromScript'].map(extract).join('\n'),context);installQmlTextInputFixture(source,context);
 return {context,top,desktop,tablet,overlay,popup,calls,replies,callbacks};
}
test('a genuine Controls2 overlay sibling is absent from tablet/Desktop grabs and selects their private UI ancestor',()=>{
 const f=fixture();assert(!f.tablet.children.includes(f.popup));assert(!f.desktop.children.includes(f.overlay));assert.equal(f.context.hasDialog(f.desktop,f.tablet,0),false);
 assert.equal(f.context.target(),f.top);assert.equal(f.context.captureSurface,'dialogs');
 f.overlay.visible=false;assert.equal(f.context.target(),f.tablet);assert.equal(f.context.captureSurface,'tablet');
});
test('actual production capture and pointer coordinates include the overlay while preserving the tablet rectangle',()=>{
 const f=fixture();f.context.fromScript({kind:'capture',navigationSequence:1,revision:2,sequence:7,path:'/private/owned-frame.png'});
 assert.equal(f.calls[0][1],f.top);assert.equal(f.context.captureTarget,null);assert.equal(f.callbacks.length,1);
 let saved;f.callbacks[0]({saveToFile:path=>{saved=path;return true;}});
 assert.equal(saved,'/private/owned-frame.png');assert.equal(f.replies[0].surface,'dialogs');assert.equal(f.replies[0].width,1280);assert.equal(f.replies[0].height,900);
 assert.deepEqual({...f.replies[0].tabletRect},{x:600,y:100,width:480,height:706});
 f.context.fromScript({kind:'displayFrame',navigationSequence:1,revision:2,sequence:7});
 f.context.fromScript({kind:'input',event:'press',button:0,navigationSequence:1,revision:2,frameSequence:7,x:900/1280,y:300/900});assert.deepEqual(f.calls.at(-1),['press',f.top,900,300]);
});
test('hidden, transparent or empty overlay cannot switch the ordinary tablet capture',()=>{
 for(const change of [f=>f.overlay.visible=false,f=>f.overlay.opacity=0,f=>f.overlay.children=[],f=>f.popup.visible=false,f=>f.popup.opacity=0,f=>f.popup.width=0]){const f=fixture();change(f);assert.equal(f.context.target(),f.tablet);}
});
test('foreign-window overlay and excessive popup children are refused before GPU work',()=>{
 for(const change of [f=>f.overlay.parent={children:[]},f=>f.overlay.children=Array.from({length:257},()=>f.popup)]){const f=fixture();change(f);f.context.fromScript({kind:'capture',navigationSequence:1,revision:3,sequence:8,path:'/private/owned.png'});assert.equal(f.callbacks.length,0);assert.equal(f.replies.length,1);assert.equal(f.replies[0].kind,'error');assert.equal(f.replies[0].revision,3);assert.equal(f.replies[0].operation,'capture');}
});
test('existing dialogs keep the Desktop scope when there is no visible Controls2 popup',()=>{
 const f=fixture();f.overlay.visible=false;const dialog={objectName:'GeneralPreferences',shown:true,visible:true,width:600,height:500,children:[]};f.desktop.children.push(dialog);assert.equal(f.context.target(),f.desktop);assert.equal(f.context.captureSurface,'dialogs');
});
test('popup capture preserves cancelled GPU ownership and the original allocation limits',()=>{
 const f=fixture();f.context.fromScript({kind:'capture',navigationSequence:1,revision:5,sequence:10,path:'/private/owned.png'});f.context.fromScript({kind:'cancelCapture'});let saved=0;f.callbacks[0]({saveToFile:()=>{saved++;return true;}});assert.equal(saved,0);assert.equal(f.replies.at(-1).cancelled,true);
 const huge=fixture();huge.top.width=2049;huge.context.fromScript({kind:'capture',navigationSequence:1,revision:5,sequence:11,path:'/private/owned.png'});assert.equal(huge.callbacks.length,0);assert.equal(huge.replies.at(-1).kind,'error');
});
