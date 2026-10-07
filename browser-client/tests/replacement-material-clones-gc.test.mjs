// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import{execFile}from'node:child_process';import{promisify}from'node:util';
test('actual isolated GC releases template/resources/root/texture/clone while closed bank remains retained',async()=>{const execute=promisify(execFile);const child=new URL('./fixtures/replacement-material-clones-gc.mjs',import.meta.url);const result=await execute(process.execPath,['--expose-gc','--import','tsx',child.pathname],{cwd:new URL('..',import.meta.url),timeout:15000,maxBuffer:2048});assert.equal(result.stderr,'');assert.deepEqual(JSON.parse(result.stdout),{bankRetained:true,weakReferences:5,released:5});});
