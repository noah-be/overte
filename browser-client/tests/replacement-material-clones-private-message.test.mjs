// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {privateCloneMessage,evaluateCloneFixture} from './integration/replacement-material-clones-diagnostics.mjs';

test('native subclass own data message is available without invoking its formatter or getters',()=>{
 class DriverError extends Error {get stack(){throw Error('Do not format');}}
 const error=new DriverError('authored private driver refusal');
 Object.defineProperty(error,'stack',{configurable:true,get(){throw Error('Do not format');}});
 assert.deepEqual(privateCloneMessage(error),{messageAvailable:true,message:'authored private driver refusal',messageTruncated:false});
});
test('unknown objects, proxies and native message getters are refused without executing user code',()=>{
 let reads=0;const unknown={get message(){reads++;throw Error('Do not read');}},error=new Error();
 Object.defineProperty(error,'message',{get(){reads++;throw Error('Do not read');}});
 const proxy=new Proxy(new Error('private'),{getOwnPropertyDescriptor(){reads++;throw Error('Do not trap');}});
 for(const value of[unknown,error,proxy,null,'private'])assert.deepEqual(privateCloneMessage(value),{messageAvailable:false,message:null,messageTruncated:false});
 assert.equal(reads,0);
});
test('private own messages have an exact UTF8 byte bound without splitting astral characters',()=>{
 const message='🙂'.repeat(5000),result=privateCloneMessage(new Error(message));
 assert.equal(Buffer.byteLength(result.message,'utf8'),8192);assert.equal(result.message,'🙂'.repeat(2048));assert.equal(result.messageTruncated,true);
});
test('actual evaluation still occurs once, retains original exception identity and adds private data only',async()=>{
 class DriverError extends Error{}const error=new DriverError('authored private refusal'),record={};let calls=0;
 await assert.rejects(evaluateCloneFixture({async evaluate(){calls++;throw error;}},[()=>{}, {enabled:false}],record),value=>value===error);
 assert.equal(calls,1);assert.equal(record.failureOperation,'evaluate-baseline');assert.equal(record.privateMessage.message,error.message);assert.deepEqual(record.failureDiagnostic,{errorClass:'error',reason:'unclassified'});
});
