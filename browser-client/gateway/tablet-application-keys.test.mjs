// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const qml=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
const keyCode=qml.slice(qml.indexOf('    function keyCode(value) {'),qml.indexOf('    function cancelPointer() {'));
const modifiers=qml.split('\n').find(line=>line.includes('    function modifiers(flags)'));
const fromScript=qml.slice(qml.indexOf('    function fromScript(message) {')).replace(/\n}\s*$/,'');
function fixture(){
 const delivered=[],errors=[],texts=[],input={item:{owned:true},width:480,height:706,revision:2,navigationSequence:7,sequence:9};
 const Qt={NoModifier:0,ShiftModifier:0x02000000,ControlModifier:0x04000000,AltModifier:0x08000000,MetaModifier:0x10000000};
 for(const [i,name] of ['Backspace','Tab','Return','Delete','Insert','Home','End','PageUp','PageDown','Left','Right','Up','Down','Escape','F1','F2','F3','F4','F5','F6','F7','F8','F9','F10','F11','F12'].entries())Qt['Key_'+name]=0x01000000+i;
 const ctx={Qt,inputSurface:input,pointerSurface:null,pendingText:null,queueTextInput:m=>delivered.push({queued:m.sequence}),modifiers:null,events:{keyClick(){throw Error('Duplicate offscreen key delivery');},keyClickChar(){throw Error('Duplicate offscreen key delivery');}},nativeInput:{clickApplicationKey(surface,key,mods){delivered.push({surface,key,mods});return true;}},sendToScript:m=>errors.push(m),text:value=>{texts.push(value);return true;}};
 ctx.helper=ctx;vm.runInNewContext(modifiers+'\n'+keyCode+'\n'+fromScript,ctx);
 return {ctx,input,delivered,errors,texts,key:(extra={})=>ctx.fromScript({kind:'input',event:'key',revision:2,navigationSequence:7,key:'x',modifiers:0,sequence:12,...extra})};
}
test('actual QML ordinary ASCII key takes original application route exactly once',()=>{const f=fixture();f.key();assert.equal(f.delivered.length,1);assert.equal(f.delivered[0].surface,f.input.item);assert.equal(f.delivered[0].key,'x');assert.equal(f.delivered[0].mods,0);assert.equal(f.errors.length,0);assert.equal(f.texts.length,0);});
test('actual QML special keys and original modifier conversion use the same single owned route',()=>{for(const key of ['Enter','Tab','Backspace','ArrowLeft','Escape','F12']){const f=fixture();f.key({key,modifiers:15});assert.equal(f.delivered.length,1);assert.equal(f.delivered[0].key,key);assert.equal(f.delivered[0].mods,0x1e000000);assert.equal(f.errors.length,0);}});
test('Unicode remains the original text/IME path and never reaches application shortcuts',()=>{for(const key of ['é','中','😀']){const f=fixture();f.key({key});assert.deepEqual(f.texts,[key]);assert.equal(f.delivered.length,0);}});
test('missing displayed surface, wrong revision and navigation do not deliver keys',()=>{for(const change of [f=>f.ctx.inputSurface=null,f=>f.input.revision=3,f=>f.input.navigationSequence=8]){const f=fixture();change(f);f.key();assert.equal(f.delivered.length,0);assert.equal(f.errors.length,0);}});
test('gesture-owned displayed surface is required instead of a newly captured surface',()=>{const f=fixture();const own={...f.input,item:{gesture:true}};f.ctx.pointerSurface=own;f.key();assert.equal(f.delivered[0].surface,own.item);});
test('pending original text transaction queues the key instead of bypassing its ordering',()=>{const f=fixture();f.ctx.pendingText={};f.key();assert.deepEqual(f.delivered,[{queued:12}]);});
test('a refused native application route emits the original input error and never retries QtTest',()=>{const f=fixture();f.ctx.nativeInput.clickApplicationKey=()=>false;f.key();assert.equal(f.delivered.length,0);assert.equal(f.errors.length,1);assert.equal(f.errors[0].revision,2);assert.equal(f.errors[0].operation,'input');assert.match(f.errors[0].message,/could not accept that input/);});
