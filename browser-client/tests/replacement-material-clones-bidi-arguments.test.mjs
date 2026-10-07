// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {BidiSerializer} from '../node_modules/puppeteer-core/lib/puppeteer/bidi/Serializer.js';
import {cloneBidiArguments} from './integration/replacement-material-clones-bidi-arguments.mjs';
import {cloneVariants} from './integration/replacement-material-clones-registration.mjs';

test('actual pinned BiDi serializer refuses original VM object but accepts the exact plain projection',()=>{
 const args=vm.runInNewContext('[async({enabled,variant})=>({enabled,variant}),{enabled:false,variant:"opaque"}]');
 assert.throws(()=>BidiSerializer.serialize(args[1]),/Custom object serialization not possible/);
 const projected=cloneBidiArguments(args);assert.equal(projected[0],args[0]);assert.equal(Object.getPrototypeOf(projected[1]),Object.prototype);
 assert.deepEqual(BidiSerializer.serialize(projected[1]),{type:'object',value:[[{type:'string',value:'enabled'},{type:'boolean',value:false}],[{type:'string',value:'variant'},{type:'string',value:'opaque'}]]});
});
test('every original variant and baseline/candidate flag retain exact primitive values and function identity',()=>{
 for(const variant of cloneVariants)for(const enabled of[false,true]){
  const args=vm.runInNewContext('[async({enabled,variant})=>({enabled,variant}),{enabled,variant}]',{enabled,variant});
  const projected=cloneBidiArguments(args);assert.equal(projected[0],args[0]);assert.deepEqual(projected[1],{enabled,variant});assert.doesNotThrow(()=>BidiSerializer.serialize(projected[1]));assert.notEqual(projected[1],args[1]);
 }
});
test('projection never invokes getters, proxy traps, formatters or unknown fields',()=>{
 let calls=0;const fn=()=>{},getter={get enabled(){calls++;throw Error('Do not inspect');},variant:'opaque'};
 const proxy=new Proxy({enabled:false,variant:'opaque'},{ownKeys(){calls++;throw Error('Do not inspect');}});
 for(const value of[getter,proxy,{enabled:false,variant:'opaque',secret:'private'},{enabled:false,variant:'opaque',[Symbol('private')]:1}])assert.throws(()=>cloneBidiArguments([fn,value]));
 const inherited=Object.create({get enabled(){calls++;throw Error('Do not inspect');}});inherited.variant='opaque';assert.throws(()=>cloneBidiArguments([fn,inherited]));assert.equal(calls,0);
});
test('unsupported evaluation signatures and values refuse before a browser invocation',()=>{
 for(const args of[null,[],[()=>{}],[()=>{},{enabled:false,variant:'opaque'},1],['code',{enabled:false,variant:'opaque'}],[()=>{},null],[()=>{},{enabled:1,variant:'opaque'}],[()=>{},{enabled:false,variant:'unknown'}]])assert.throws(()=>cloneBidiArguments(args));
});
