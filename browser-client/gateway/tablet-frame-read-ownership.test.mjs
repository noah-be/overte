// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {TabletSession} from './tablet.mjs';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==','base64');
async function fixture(run){
 const directory=await mkdtemp(path.join(tmpdir(),'overte-frame-read-owner-')),browser=[],native=[];
 const session=new TabletSession({framePath:path.join(directory,'tablet.png'),sendBrowser:value=>browser.push(value),sendNative:value=>native.push(value),isActive:()=>true,getRevision:()=>1});
 const command=(action,sequence,extra={})=>session.receive({type:'tablet',action,sequence,revision:1,...extra});
 const frame=(sequence,navigationSequence)=>session.receiveNative({type:'tablet',kind:'frameReady',revision:1,navigationSequence,sequence,width:1,height:1,surface:'tablet'});
 try{command('open',1);await run({directory,session,browser,native,command,frame});}
 finally{session.close();await rm(directory,{recursive:true,force:true});}
}
test('a real failed frame-file read from the previous navigation cannot emit an error after Home revoked its owner',()=>fixture(async({session,browser,command,frame})=>{
 const reading=frame(1,1);assert.equal(session.pendingFrame,1);command('home',2);assert.equal(session.pendingFrame,0);await reading;
 assert.equal(session.navigationSequence,2);assert.equal(browser.filter(value=>value.kind==='error').length,0);
}));
test('a late previous-view read failure preserves the current real PNG frame and its pending acknowledgement',()=>fixture(async({session,browser,native,command,frame})=>{
 const obsolete=frame(1,1);command('home',2);
 await writeFile(`${session.framePath}.1.2.png`,png);
 const current=frame(2,2);assert.equal(session.pendingFrame,2);await Promise.all([obsolete,current]);
 assert.equal(browser.filter(value=>value.kind==='error').length,0);assert.equal(browser.filter(value=>value.kind==='frame').length,1);
 assert.equal(session.pendingFrame,2);assert.equal(native.some(value=>value.action==='frameAck'),false);
 command('frameAck',3,{frameSequence:2,displayed:true});assert.equal(session.pendingFrame,0);assert.equal(session.displayedFrame,2);assert.equal(native.at(-1).displayed,true);
}));
test('a real failed read still emits one bounded error and releases the same active frame owner without false displayed acknowledgement',()=>fixture(async({session,browser,native,frame})=>{
 await frame(1,1);assert.equal(browser.filter(value=>value.kind==='error').length,1);assert.equal(session.pendingFrame,0);assert.equal(session.displayedFrame,0);assert.equal(native.at(-1).action,'frameAck');assert.equal(native.at(-1).frameSequence,1);assert.equal(native.at(-1).displayed,false);
}));
