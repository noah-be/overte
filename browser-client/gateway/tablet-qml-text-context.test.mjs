// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFile} from 'node:fs/promises';
import {installQmlTextInputFixture} from './fixtures/tablet-qml-text-context.mjs';
const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
test('dispatch fixture installs actual current text dependencies and preserves its native GUI parent/capture identity',()=>{
 const nativeParent={children:[]},helper={parent:nativeParent,objectName:'existing-capture-helper'};
 const context=vm.createContext({helper});installQmlTextInputFixture(source,context);
 assert.equal(helper.parent,nativeParent);assert.equal(helper.objectName,'existing-capture-helper');assert.equal(context.pendingText,null);assert.equal(context.textInputQueue.length,0);assert.equal(context.textInputQueueUnits,0);
 for(const name of ['focusedItem','cancelTextInput','currentTextTarget','failTextInput','queueTextInput','finishTextInput','startWebText','text']){assert.equal(typeof context[name],'function');assert.equal(helper[name],context[name]);assert(source.includes(context[name].toString()),name+' is the exact source method');}
});
test('dispatch fixture refuses missing production dependencies instead of replacing them with success stubs',()=>{
 for(const name of ['cancelTextInput','queueTextInput','startWebText'])assert.throws(()=>installQmlTextInputFixture(source.replace('function '+name+'(','function missing_'+name+'('),vm.createContext({helper:{}})),/Current QML text-input dependency/);
});
test('installed actual cancellation clears captured GUI references and explicit pending state',()=>{
 const context=vm.createContext({helper:{}});installQmlTextInputFixture(source,context);const record={web:{},focus:{},surface:{},cancelled:false};context.pendingText=record;context.textInputQueue.push({event:'key'});context.textInputQueueUnits=30;context.textCommitTimer.restart();context.cancelTextInput();
 assert.equal(record.cancelled,true);assert.equal(record.web,null);assert.equal(record.focus,null);assert.equal(record.surface,null);assert.equal(context.pendingText,null);assert.equal(context.textInputQueue.length,0);assert.equal(context.textInputQueueUnits,0);assert.equal(context.textCommitTimer.running,false);
});
