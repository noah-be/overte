// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact source dependencies and explicit state for current dispatch VM fixtures.
// These controlled Timer methods are not a genuine Qt/runtime completion proof.
import vm from 'node:vm';
import assert from 'node:assert/strict';
const methods=['focusedItem','cancelTextInput','currentTextTarget','failTextInput','queueTextInput','finishTextInput','startWebText','text'];
export function installQmlTextInputFixture(source,context){
 const functions=methods.map(name=>{
  const match=source.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));
  assert(match,'Current QML text-input dependency '+name);return match[0];
 });
 context.pendingText=null;context.textInputQueue=[];context.textInputQueueUnits=0;
 context.textCommitTimer={running:false,restart(){this.running=true;},stop(){this.running=false;}};
 vm.runInContext(functions.join('\n'),context);
 // The QML Item exposes these real source methods under its helper id too.
 // Retain the fixture's existing native UI parenting and capture dependencies.
 context.helper??={};for(const name of methods)context.helper[name]=context[name];
 return context;
}
