// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
const focusFunction=source.match(/function focusedItem\(\) \{[\s\S]*?\n    \}/)[0];
const textFunction=source.match(/function text\(value\) \{[\s\S]*?\n    \}/)[0];
test('actual QML committed Unicode replaces the focused native selection without a QtTest Latin-1 assertion',()=>{
    const operations=[],focused={cursorPosition:5,selectionStart:0,selectionEnd:5,remove:(a,b)=>operations.push(['remove',a,b]),insert:(a,text)=>operations.push(['insert',a,text])};
    const context=vm.createContext({topRoot:()=>({Window:{window:{activeFocusItem:focused}}}),events:{keyClickChar:()=>{throw Error('Unicode must not enter QtTest Latin1');}},nativeInput:{commitText:(item,text)=>{operations.push(['commit',item,text]);return true;}},Qt:{NoModifier:0}});
    vm.runInContext(focusFunction+textFunction,context);assert.equal(context.text('Überte 世界 👋'),true);assert.deepEqual(operations,[['commit',focused,'Überte 世界 👋']]);
});
test('native WebEngine insertion JSON-quotes visitor text and only accepts an actual editable focused document',()=>{
    const scripts=[],surface={},web={parent:surface,url:'https://native-fixture.invalid/',runJavaScript:(script,callback)=>scripts.push({script,callback})},focused={parent:web};
    const context=vm.createContext({helper:null,pendingText:null,textInputQueue:[],textInputQueueUnits:0,pointerSurface:null,inputSurface:{item:surface,revision:1,navigationSequence:1},
        offscreenWindow:{activeFocusItem:focused},textCommitTimer:{restart(){},stop(){}},events:{keyClickChar:()=>{throw Error('not a Latin1 key');}},Qt:{NoModifier:0}});
    context.helper=context;
    const helpers=['cancelTextInput','currentTextTarget','failTextInput','queueTextInput','finishTextInput','startWebText'].map(name=>{
        const start=source.indexOf('    function '+name+'('),end=source.indexOf('\n    }',start);assert(start>=0&&end>start);return source.slice(start,end+6);
    }).join('\n');
    vm.runInContext(focusFunction+helpers+textFunction,context);const value='👋 "); window.stolen=true; //';assert.equal(context.text(value),true);
    const execution={location:{href:web.url},document:{activeElement:{nodeName:'INPUT'},execCommand:(command,unused,text)=>{assert.equal(command,'insertText');assert.equal(text,value);return true;}}};assert.equal(vm.runInNewContext(scripts[0].script,execution),true);assert.equal(execution.stolen,undefined);
});
test('unfocused composed Unicode returns a recoverable error instead of invoking unsafe native character overloads',()=>{
    const context=vm.createContext({topRoot:()=>({Window:{window:{activeFocusItem:null}}}),events:{keyClickChar:()=>{throw Error('unsafe character call');}},Qt:{NoModifier:0}});
    vm.runInContext(focusFunction+textFunction,context);assert.equal(context.text('👋'),false);
});
const clipboardFunction=source.match(/function clipboard\(message\) \{[\s\S]*?\n    \}/)[0];
test('native clipboard copies/cuts focused Unicode text and refuses password fields without any host clipboard API',()=>{
    const replies=[],removes=[],focused={selectedText:'Überte 世界 👋',selectionStart:1,selectionEnd:15,echoMode:0,remove:(a,b)=>removes.push([a,b])};
    const context=vm.createContext({topRoot:()=>({Window:{window:{activeFocusItem:focused}}}),sendToScript:item=>replies.push(item),nativeInput:{cutSelection:item=>{assert.equal(item,focused);removes.push([item.selectionStart,item.selectionEnd]);return true;}}});
    vm.runInContext(focusFunction+clipboardFunction,context);context.clipboard({revision:4,sequence:9,operation:'copy'});assert.equal(replies.at(-1).text,focused.selectedText);assert.equal(removes.length,0);
    context.clipboard({revision:4,sequence:10,operation:'cut'});assert.deepEqual(removes,[[1,15]]);
    focused.echoMode=2;context.clipboard({revision:4,sequence:11,operation:'copy'});assert.equal(replies.at(-1).text,'');assert.equal(replies.at(-1).requestId,11);assert.equal(removes.length,1);
});
test('native web clipboard selection excludes password inputs and only executes the fixed trusted selection script',()=>{
    const replies=[],focused={parent:{runJavaScript:(script,callback)=>{const result=vm.runInNewContext(script,{document:{activeElement:{type:'text',value:'Hello 世界',selectionStart:6,selectionEnd:8}},window:{getSelection:()=>''}});callback(result);}}};
    const context=vm.createContext({topRoot:()=>({Window:{window:{activeFocusItem:focused}}}),sendToScript:item=>replies.push(item)});vm.runInContext(focusFunction+clipboardFunction,context);
    context.clipboard({revision:1,sequence:1,operation:'copy'});assert.equal(replies[0].text,'世界');
    focused.parent.runJavaScript=(script,callback)=>callback(vm.runInNewContext(script,{document:{activeElement:{type:'password',value:'secret',selectionStart:0,selectionEnd:6}},window:{getSelection:()=>{throw Error('Password must not be read');}}}));
    context.clipboard({revision:1,sequence:2,operation:'copy'});assert.equal(replies[1].text,'');
});

test('native OffscreenSurface context owns text and clipboard focus when attached Window differs',()=>{
    const operations=[],replies=[],actualFocus={cursorPosition:2,selectionStart:0,selectionEnd:2,selectedText:'世界',echoMode:0,remove:(a,b)=>operations.push(['remove',a,b]),insert:(at,value)=>operations.push(['insert',at,value])};
    const context=vm.createContext({offscreenWindow:{activeFocusItem:actualFocus},topRoot:()=>({Window:{window:{activeFocusItem:null}}}),events:{keyClickChar:()=>{throw Error('Wrong Qt window');}},Qt:{NoModifier:0},sendToScript:value=>replies.push(value),nativeInput:{commitText:(item,text)=>{operations.push(['commit',item,text]);return true;}}});
    vm.runInContext(focusFunction+textFunction+clipboardFunction,context);
    assert.equal(context.focusedItem(),actualFocus);assert.equal(context.text('Überte 世界 👋'),true);
    assert.deepEqual(operations,[['commit',actualFocus,'Überte 世界 👋']]);
    context.clipboard({revision:2,sequence:7,operation:'copy'});assert.equal(replies[0].text,'世界');
});

test('actual clicked native editor activates its focus scope despite a covering input layer and refuses unrelated fields',()=>{
    const functions=source.match(/function focusedEditors\(item,depth,out,target,x,y,budget\) \{[\s\S]*?\n    \}/)[0]+source.match(/function activateClickedEditor\(item,x,y\) \{[\s\S]*?\n    \}/)[0];
    let activated=0;const container={visible:true,width:271,height:40};
    const editor={visible:true,focus:true,parent:container,insert:()=>{},forceActiveFocus:()=>activated++,children:[]};
    const target={visible:true,shown:true,children:[editor],childAt:()=>({objectName:'transparent-input-layer'}),mapToItem:(item,x,y)=>({x,y})};
    const context=vm.createContext({});vm.runInContext(functions,context);
    context.activateClickedEditor(target,256,24);assert.equal(activated,1,'Native pencil inside the field container activates the locally focused editor');
    editor.visible=false;context.activateClickedEditor(target,256,24);assert.equal(activated,1,'Hidden native fields cannot capture keyboard input');
    editor.visible=true;target.children.push({...editor});context.activateClickedEditor(target,256,24);assert.equal(activated,1,'Ambiguous native fields cannot select an arbitrary editor');
    target.children=[editor];editor.focus=false;context.activateClickedEditor(target,256,24);assert.equal(activated,1,'An unfocused field cannot capture input');
    editor.focus=true;context.activateClickedEditor(target,280,24);assert.equal(activated,1,'Clicking outside the real field container cannot select it');
    container.shown=true;context.activateClickedEditor(target,256,24);assert.equal(activated,1,'A whole window is never an editable field container');
});

test('native readonly or disabled fields cannot be edited through programmatic Unicode insertion or cut, while copy stays usable',()=>{
    const operations=[],replies=[],focused={readOnly:true,enabled:true,cursorPosition:4,selectionStart:0,selectionEnd:4,selectedText:'Read-only 世界',echoMode:0,insert:(at,text)=>operations.push(['insert',at,text]),remove:(a,b)=>operations.push(['remove',a,b])};
    const context=vm.createContext({offscreenWindow:{activeFocusItem:focused},events:{keyClickChar:()=>{throw Error('A readonly field must not fall through to another target');}},sendToScript:value=>replies.push(value),nativeInput:{commitText:(item,text)=>{operations.push(['commit',item,text]);return true;},cutSelection:item=>{operations.push(['cut',item]);return true;}},Qt:{NoModifier:0}});
    vm.runInContext(focusFunction+textFunction+clipboardFunction,context);
    assert.equal(context.text('unexpected overwrite'),false);context.clipboard({revision:1,sequence:1,operation:'copy'});assert.equal(replies.at(-1).text,'Read-only 世界');
    context.clipboard({revision:1,sequence:2,operation:'cut'});assert.deepEqual(operations,[],'Programmatic Qt remove must never bypass readOnly');
    focused.readOnly=false;focused.enabled=false;assert.equal(context.text('unexpected overwrite'),false);context.clipboard({revision:1,sequence:3,operation:'cut'});assert.deepEqual(operations,[],'Disabled native fields cannot change via the bridge');
    focused.enabled=true;assert.equal(context.text('permitted edit'),true);assert.deepEqual(operations,[['commit',focused,'permitted edit']]);
});
