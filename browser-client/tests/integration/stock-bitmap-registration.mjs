// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// The only adaptation is exact assertion registration/import binding.
import {expect} from '@playwright/test';import {transformWithOxc} from 'vite';import {readFile} from 'node:fs/promises';import vm from 'node:vm';import path from 'node:path';import assert from 'node:assert/strict';
export const bitmapCases=Object.freeze([
 Object.freeze({file:'tests/world-bitmap-upload.browser.spec.ts',name:'already decoded bitmap variants preserve exact HTML texture pixels and owned sampler teardown',attachment:'bitmap-upload-parity',variant:'twelve-exact-variants'}),
 Object.freeze({file:'tests/world-bitmap-integration.browser.spec.ts',name:'actual World 4096 images preserve residual alpha, native UVs, samplers, exact pixels and lease cleanup',attachment:'world-4096-bitmap-original-comparison',variant:'world-4096-direct-image'}),
]);
export async function registeredBitmapBodies(client){
 const entries=[];for(const description of bitmapCases){const file=path.join(client,description.file),source=await readFile(file,'utf8'),marker="import {test,expect} from '@playwright/test';";
  assert.equal(source.split(marker).length,2,'Only the exact original registered import is adapted');
  const adapted=source.replace(marker,'const test=injectedTest,expect=injectedExpect;'),compiled=await transformWithOxc(adapted,file);let callback;
  vm.runInNewContext(compiled.code,{injectedExpect:expect,injectedTest:(name,body)=>{assert.equal(name,description.name);assert.equal(callback,undefined,'Exactly one ORIGINAL registered test');assert.equal(typeof body,'function');callback=body;}},{timeout:1000});
  assert(callback);entries.push(Object.freeze({...description,callback}));
 }return Object.freeze(entries);
}
/** Every nested owned resource closes even when an earlier close throws.
 * The caller's original test failure is never replaced by cleanup failure. */
export async function finishStockBitmapCleanup({context,browser,server},report){
 try{if(context)try{await context.close();report.cleanup.contextsClosed++;}catch{report.cleanup.contextFailure=true;report.completed=false;process.exitCode=1;}}
 finally{try{if(browser)try{await browser.close();report.cleanup.browser='closed';}catch{report.cleanup.browser='failed';report.completed=false;process.exitCode=1;}}
 finally{if(server)try{await server.close();report.cleanup.server='closed';}catch{report.cleanup.server='failed';report.completed=false;process.exitCode=1;}}}
}
