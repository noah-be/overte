// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import vm from 'node:vm';
import {instrumentTabletPopupAudit,POPUP_AUDIT_PREFIX} from './tablet-popup-audit.mjs';
const source=await readFile(new URL('../../gateway/tablet-capture.qml',import.meta.url),'utf8');
test('fixed popup audit adds one passive capture callback and refuses duplicated/unknown source',()=>{const result=instrumentTabletPopupAudit(source);assert(result.includes('popupAudit(item,message);'));assert.equal(result.split('import QtQuick.Controls 2.15 as Controls').length,2);assert.throws(()=>instrumentTabletPopupAudit(result));assert.throws(()=>instrumentTabletPopupAudit('unknown'));assert.equal(result.split('runJavaScript').length,source.split('runJavaScript').length);});
test('actual generated geometry observer is bounded and excludes widget names, text, paths and pointer addresses',()=>{
 const logs=[];const node=(tag)=>({visible:true,width:225,height:144,opacity:1,children:[],text:'secret password',url:'file:///host-secret',objectName:'private-caption',toString:()=>tag+'(0xdeadbeef, private-caption)',mapToItem:()=>({x:600,y:100})});
 const top=node('QQuickItem'),tablet=node('TabletRoot'),desktop=node('Desktop'),overlay=node('QQuickOverlay');overlay.parent=top;overlay.children=Array.from({length:300},()=>node('QQuickPopupItem'));
 const c=vm.createContext({popupAuditCount:0,popupAuditKey:'',topRoot:()=>top,find:(unused,name)=>name==='tabletRoot'?tablet:desktop,Controls:{Overlay:{overlay}},console:{log:value=>logs.push(value)}});
 const fn=instrumentTabletPopupAudit(source).match(/    function popupAudit\(item,message\) \{[\s\S]*?\n    \}/)[0];vm.runInContext(fn,c);
 c.popupAudit(top,{sequence:7,revision:3});c.popupAudit(top,{sequence:8,revision:3});assert.equal(logs.length,1);const data=JSON.parse(logs[0].slice(POPUP_AUDIT_PREFIX.length));assert.equal(data.scope,'offscreen-content');assert.equal(data.overlayInTop,true);assert.equal(data.children.length,12);assert.equal(data.truncated,true);assert.equal(data.sequence,7);
 assert(!logs[0].includes('secret'));assert(!logs[0].includes('private-caption'));assert(!logs[0].includes('deadbeef'));
 for(let i=0;i<80;i++){top.width=400+i;c.popupAudit(top,{sequence:9+i,revision:3});}assert.equal(logs.length,64);
});
test('fixed native ComboBox audit distinguishes genuine closed control focus from an opened popup without reading captions',()=>{
 const logs=[];const node=tag=>({visible:true,width:225,height:40,opacity:1,children:[],toString:()=>tag+'(0xdeadbeef, secret-caption)',mapToItem:()=>({x:224,y:310})});
 const top=node('QQuickItem'),tablet=node('TabletRoot'),desktop=node('Desktop'),overlay=node('QQuickOverlay');overlay.parent=top;
 const control=node('ComboBox_QMLTYPE_42');Object.assign(control,{currentIndex:3,highlightedIndex:-1,activeFocus:true,pressed:false,down:false,enabled:true,popup:{visible:false,opened:false,x:0,y:35,width:225,height:144,contentItem:node('QQuickListView')},delegateModel:{count:4},displayText:'secret selected identity'});
 top.children=[desktop,overlay];desktop.children=[tablet];tablet.children=[control];
 const c=vm.createContext({popupAuditCount:0,popupAuditKey:'',topRoot:()=>top,find:(unused,name)=>name==='tabletRoot'?tablet:desktop,Controls:{Overlay:{overlay}},console:{log:value=>logs.push(value)}});
 vm.runInContext(instrumentTabletPopupAudit(source).match(/    function popupAudit\(item,message\) \{[\s\S]*?\n    \}/)[0],c);
 c.popupAudit(tablet,{sequence:1,revision:2});assert.equal(logs.length,1);let data=JSON.parse(logs[0].slice(POPUP_AUDIT_PREFIX.length));assert.equal(data.controls.length,1);assert.equal(data.controls[0].activeFocus,true);assert.equal(data.controls[0].popup.visible,false);assert.equal(data.controls[0].currentIndex,3);
 control.popup.visible=true;control.popup.opened=true;control.highlightedIndex=3;overlay.children=[node('QQuickPopupItem')];c.popupAudit(top,{sequence:2,revision:2});assert.equal(logs.length,2);data=JSON.parse(logs[1].slice(POPUP_AUDIT_PREFIX.length));assert.equal(data.controls[0].popup.opened,true);assert.equal(data.controls[0].highlightedIndex,3);assert.equal(data.controls[0].delegateCount,4);
 assert(!logs.join('').includes('secret'));assert(!logs.join('').includes('deadbeef'));assert(!logs.join('').includes('caption'));
});
test('native control inventory obeys node, child and record bounds',()=>{
 const logs=[],top={visible:true,width:1280,height:900,children:[],toString:()=> 'QQuickItem',mapToItem:()=>({x:0,y:0})};
 const item={visible:true,width:225,height:40,children:[],toString:()=> 'ComboBox_QMLTYPE_42',mapToItem:()=>({x:0,y:0}),currentIndex:0,highlightedIndex:0,popup:{visible:false,width:225,height:144},delegateModel:{count:4}};top.children=Array.from({length:1000},()=>item);
 const c=vm.createContext({popupAuditCount:0,popupAuditKey:'',topRoot:()=>top,find:()=>null,Controls:{Overlay:{overlay:null}},console:{log:value=>logs.push(value)}});vm.runInContext(instrumentTabletPopupAudit(source).match(/    function popupAudit\(item,message\) \{[\s\S]*?\n    \}/)[0],c);
 c.popupAudit(top,{sequence:1,revision:2});const data=JSON.parse(logs[0].slice(POPUP_AUDIT_PREFIX.length));assert.equal(data.controls.length,4);assert.equal(data.controlsTruncated,true);assert(logs[0].length<8192);
});
