// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {installQmlTextInputFixture} from './fixtures/tablet-qml-text-context.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

const source=await readFile(new URL('./tablet-capture.qml',import.meta.url),'utf8');
function extract(name){const match=source.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));assert(match,name);return match[0];}
function fixture(){
 const calls=[],replies=[],saved=[],top={width:1024,height:745},tablet={width:480,height:706,mapToItem:()=>({x:247,y:40})};
 let callback;
 const context=vm.createContext({privateGrab:null,activeCapture:null,savedSurface:null,inputSurface:null,pointerSurface:null,captureTarget:null,captureSurface:'dialogs',
  target:()=>top,topRoot:()=>top,find:()=>tablet,cancelPointer:()=>{},sendToScript:value=>replies.push(value),
  nativeInput:{grabPrivateGui:(item,token)=>{calls.push({item,token});return true;}}});
 vm.runInContext(['completePrivateGrab','grabOwned','fromScript'].map(extract).join('\n'),context);installQmlTextInputFixture(source,context);
 const capture=(sequence,navigationSequence=1)=>context.fromScript({kind:'capture',revision:2,sequence,navigationSequence,path:'/private/owned-'+sequence+'.png'});
 const finish=(token,result={saveToFile:path=>{saved.push(path);return true;}})=>context.completePrivateGrab(token,result);
 return {context,top,tablet,calls,replies,saved,capture,finish,get callback(){return callback;}};
}
test('engine-free private root uses only the bounded plugin and correlates its original capture token',()=>{
 const f=fixture();f.top.grabToImage=()=>{throw Error('Engine-free QML overload must not run');};f.capture(7);
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].item,f.top);assert.equal(f.calls[0].token,7);
 f.finish(8);assert.equal(f.saved.length,0);assert.equal(f.replies.length,0);assert.equal(f.context.privateGrab.token,7);
 f.finish(7);assert.deepEqual(f.saved,['/private/owned-7.png']);assert.equal(f.context.privateGrab,null);
 assert.equal(f.replies[0].saved,true);assert.equal(f.replies[0].navigationSequence,1);assert.equal(f.replies[0].sequence,7);
});
test('ordinary engine-owned tablet continues using its existing public QML grab callback',()=>{
 const f=fixture();let callback;f.tablet.grabToImage=fn=>{callback=fn;return true;};
 let delivered=0;assert.equal(f.context.grabOwned(f.tablet,3,()=>delivered++),true);assert.equal(f.calls.length,0);
 callback({});assert.equal(delivered,1);assert.equal(f.context.privateGrab,null);
});
test('cancelled root capture retains one GPU ownership until real ready and cannot save or restore the old surface',()=>{
 const f=fixture();f.capture(7);f.context.fromScript({kind:'cancelCapture'});f.context.fromScript({kind:'resetInput'});
 f.capture(8,2);assert.equal(f.calls.length,1);assert.equal(f.replies[0].kind,'error','A second root allocation is refused while old GPU work exists');
 f.finish(6);assert.equal(f.context.privateGrab.token,7);f.finish(7);
 assert.equal(f.saved.length,0);assert.equal(f.context.savedSurface,null);assert.equal(f.replies.at(-1).cancelled,true);
 f.capture(9,2);assert.equal(f.calls.length,2);f.finish(9);assert.deepEqual(f.saved,['/private/owned-9.png']);assert.equal(f.context.savedSurface.navigationSequence,2);
});
test('destroyed or reparented native owner produces no pixels; original size bounds refuse before plugin allocation',()=>{
 const f=fixture();f.capture(7);f.finish(7,null);assert.equal(f.saved.length,0);assert.equal(f.replies[0].saved,false);assert.equal(f.context.savedSurface,null);
 f.top.width=2049;f.capture(8);assert.equal(f.calls.length,1);assert.equal(f.replies.at(-1).kind,'error');
});
