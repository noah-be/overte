// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import {spawnSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
test('ready private bitmap cache releases borrowed original HTML Source under actual V8 GC while live sampler remains valid',()=>{
 const result=spawnSync(process.execPath,['--expose-gc','--import','tsx',fileURLToPath(new URL('./bitmap-source-retention-child.mjs',import.meta.url))],{cwd:fileURLToPath(new URL('..',import.meta.url)),encoding:'utf8',timeout:10000});
 assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr);assert.deepEqual(JSON.parse(result.stdout),{originalSourceCollected:true,originalImageCollected:true,livePreparedSamplerPreserved:true,bytesAfterClose:0});
});
