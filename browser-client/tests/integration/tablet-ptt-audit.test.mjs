// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {readFileSync} from 'node:fs';import path from 'node:path';
import {PTT_AUDIT_QML,PTT_AUDIT_PREFIX,instrumentPttAudit,parsePttAudit,pttClickControl,assertPaintedPttControl} from './tablet-ptt-audit.mjs';
const frame={sequence:8,revision:2,navigationSequence:5,width:480,height:706,tabletRect:{x:0,y:0,width:480,height:706}};
function fixture(){
 const output=[],item={children:[],parent:null,visible:true,opacity:1},audio={parent:item,title:'Audio Settings',switchWidth:40,switchHeight:16,pushToTalk:false,muted:true,children:[],visible:true,opacity:1};item.children=[audio];
 const wrapper={parent:audio,labelTextOn:'Push To Talk (T)',checked:false,children:[],visible:true,opacity:1,enabled:true};audio.children=[wrapper];
 const control={parent:wrapper,checked:false,down:false,visualPosition:0,visible:true,opacity:1,enabled:true,children:[],background:{width:40,height:44,mapToItem(target){assert.equal(target,item);return{x:30,y:200};}},indicator:{}};wrapper.children=[control];
 let enabled=false,held=false,muted=true;const native={};for(const [key,read] of Object.entries({pushToTalkDesktop:()=>enabled,pushingToTalk:()=>held,mutedDesktop:()=>muted}))Object.defineProperty(native,key,{get:read,set(){throw Error('A passive audit cannot write native state');}});
 const ctx={About:{buildVersion:'2026.04.1'},AudioScriptingInterface:native,console:{log(value){output.push(value);}}};vm.runInNewContext(PTT_AUDIT_QML.replace('    property int pttAuditCount: 0','    var pttAuditCount=0;').replace('    property int pttAuditBytes: 0','    var pttAuditBytes=0;')+'\nthis.run=pttAudit;',ctx);
 return {item,audio,wrapper,control,output,run(){ctx.run(item,frame);return parsePttAudit(output.at(-1))[0];},setState(e,h=false,m=true){enabled=e;held=h;muted=m;wrapper.checked=control.checked=e;},home(){const button={parent:item,text:'AUDIO',sortOrder:1,isActive:false,buttonIndex:0,enabled:true,visible:true,opacity:1,width:120,height:110,children:[],mapToItem(){return{x:15,y:45};}};item.children=[button];return button;}};
}
test('actual shipping QML without an objectName reads a unique Desktop native switch and real background geometry without any setter',()=>{
 const f=fixture(),r=f.run(),point=pttClickControl([r],frame,'desktop-ptt',false);assert.deepEqual(point.rect,{x:30,y:200,width:40,height:44});assert.equal(point.x,50);assert.equal(point.y,222);
 f.setState(true);assert(pttClickControl([f.run()],frame,'desktop-ptt',true));assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
});
test('genuine Audio app recognition does not authorize an arbitrary matching text label',()=>{
 const f=fixture();f.home();assert(pttClickControl([f.run()],frame,'audio-app'));f.item.children[0].sortOrder=99;assert.equal(pttClickControl([f.run()],frame,'audio-app'),null);
});
test('stale ACK frame, navigation and permission revision cannot authorize a native click',()=>{
 const f=fixture(),record=f.run();for(const key of ['sequence','revision','navigationSequence'])assert.equal(pttClickControl([record],{...frame,[key]:frame[key]+1},'desktop-ptt',false),null);
});
test('wrong native mode/held/mute, hidden or disabled control and partial clipping refuse',()=>{
 const f=fixture();f.setState(false,true,true);assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);f.setState(false,false,false);assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
 f.setState(false);f.wrapper.enabled=false;assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);f.wrapper.enabled=true;f.audio.visible=false;assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);f.audio.visible=true;
 f.control.background.mapToItem=()=>({x:475,y:200});assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
});
test('ambiguous Audio roots, duplicate controls and VR label do not authorize desktop changes',()=>{
 const f=fixture();f.item.children.push({...f.audio,children:[]});assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);f.item.children.pop();f.wrapper.children.push({...f.control});assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);f.wrapper.children.pop();f.wrapper.labelTextOn='Push To Talk';assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
});
test('node/depth/child/duplicate bounds mark partial captures and no partial result authorizes a click',()=>{
 for(const setup of [f=>f.item.children.push(f.audio),f=>f.wrapper.children.push(...Array.from({length:257},()=>({parent:f.wrapper,children:[]}))),f=>{let p=f.audio;for(let i=0;i<26;i++){const n={parent:p,children:[]};p.children.push(n);p=n;}},f=>{for(let i=0;i<35;i++){const n={parent:f.audio,children:[]};n.children=Array.from({length:125},()=>({parent:n,children:[]}));f.audio.children.push(n);}}]){const f=fixture();setup(f);const record=f.run();assert(record.truncated);assert.equal(pttClickControl([record],frame,'desktop-ptt',false),null);}
});
test('strict passive schema refuses private fields and invalid numeric/capture bounds',()=>{
 const f=fixture(),record=f.run();for(const value of [{...record,token:'PRIVATE'},{...record,sequence:0},{...record,nodes:4097},{...record,native:{...record.native,device:'PRIVATE'}}])assert.throws(()=>parsePttAudit(PTT_AUDIT_PREFIX+JSON.stringify(value)));assert.throws(()=>parsePttAudit('x'.repeat(4*1024*1024+1)));
});
test('emission is bounded by original count and bytes without unbounded retained trees',()=>{
 const f=fixture();for(let i=0;i<600;i++)f.run();assert.equal(f.output.length,512);assert(Buffer.byteLength(f.output.join('\n'))<524288+512*(PTT_AUDIT_PREFIX.length+1));
});
test('fixed instrumentation inserts only a passive capture read and refuses duplicate/unknown source anchors',()=>{
 const qml=readFileSync(path.join(process.env.OVERTE_PTT_SOURCE_CLIENT||process.cwd(),'gateway/tablet-capture.qml'),'utf8'),after=instrumentPttAudit(qml);
 assert.equal(after.replace(PTT_AUDIT_QML,'').replace('\n                pttAudit(item,message);',''),qml);assert.throws(()=>instrumentPttAudit(after));assert.throws(()=>instrumentPttAudit('unknown'));
 for(const action of ['runJavaScript','forceActiveFocus','setMuted','setPTT','click(','chooseCheckedByUser(','pushToTalkDesktop ='])assert(!PTT_AUDIT_QML.includes(action));
});
test('actual painted calibration requires opaque contrast instead of merely a rectangle',()=>{
 const blank=new Uint8Array(16*16*4);assert.throws(()=>assertPaintedPttControl(blank,16,16));for(let i=0;i<blank.length;i+=4)blank.set([i<blank.length/2?40:200,40,40,255],i);assert(assertPaintedPttControl(blank,16,16));
});

test('shipping root signature refuses wrong or missing title, dimensions and genuine boolean properties',()=>{
 for(const [key,bad] of [['title','Audio'],['switchWidth',41],['switchHeight',17],['pushToTalk',0],['muted','true']]){
  const f=fixture();f.audio[key]=bad;assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
 }
 for(const key of ['title','switchWidth','switchHeight','pushToTalk','muted']){
  const f=fixture();delete f.audio[key];assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
 }
 const f=fixture();delete f.audio.title;f.audio.objectName='settings.audio';assert.equal(pttClickControl([f.run()],frame,'desktop-ptt',false),null);
});
test('shipping descriptor getters are passive and native/root setters are never called',()=>{
 const f=fixture();let setters=0,reads=0;
 for(const [key,value] of Object.entries({title:'Audio Settings',switchWidth:40,switchHeight:16,pushToTalk:false,muted:true}))
  Object.defineProperty(f.audio,key,{configurable:true,get(){reads++;return value;},set(){setters++;throw Error('No root setter is permitted');}});
 assert(pttClickControl([f.run()],frame,'desktop-ptt',false));assert(reads>=5);assert.equal(setters,0);
});
test('unreadable root getters and inconsistent visual ownership fail closed without calibration',()=>{
 const f=fixture();Object.defineProperty(f.audio,'title',{get(){throw Error('Private getter failure');}});const r=f.run();assert(r.truncated);assert.equal(pttClickControl([r],frame,'desktop-ptt',false),null);assert(!f.output.join('').includes('Private getter failure'));
 for(const corrupt of [f=>{f.control.parent=f.item;},f=>{f.wrapper.parent=f.item;},f=>{f.audio.parent={children:[]};}]){
  const f=fixture();corrupt(f);const r=f.run();assert(r.truncated);assert.equal(pttClickControl([r],frame,'desktop-ptt',false),null);
 }
});
test('cyclic visual child references refuse even when a complete shipping signature was visited',()=>{
 const f=fixture();f.control.children=[f.audio];const r=f.run();assert(r.truncated);assert.equal(pttClickControl([r],frame,'desktop-ptt',false),null);
});

test('primitive child values refuse and the original 4096-node limit remains exercised',()=>{
 const primitive=fixture();primitive.audio.children.push(42);const rejected=primitive.run();assert(rejected.truncated);assert.equal(pttClickControl([rejected],frame,'desktop-ptt',false),null);
 const f=fixture();for(let i=0;i<35;i++){const n={parent:f.audio,children:[]};n.children=Array.from({length:125},()=>({parent:n,children:[]}));f.audio.children.push(n);}
 const r=f.run();assert.equal(r.nodes,4096);assert(r.truncated);assert.equal(pttClickControl([r],frame,'desktop-ptt',false),null);
});
