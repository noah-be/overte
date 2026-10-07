// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {finalizeNativeIgnoredFbxEvidence} from './integration/native-ignored-fbx-cleanup.mjs';
function fixture(overrides={}) {
 const calls=[];const source={'src/baked-fbx.ts':'a'.repeat(64)};
 const report={completed:true,pixels:{completed:true,exactPixels:true},modelRequests:1,unusedDDSRequests:1,sourceStart:source};
 return {report,calls,options:{report,closeBrowser:async()=>{calls.push('browser');},closeServer:async()=>{calls.push('server');},hashSources:async()=>{calls.push('sources');return {...source};},hashBundles:async()=>{calls.push('bundles');return {'entry.js':'b'.repeat(64)};},publish:async value=>{calls.push('publish');assert.equal(value,report);},now:()=> '2026-10-02T00:00:00.000Z',...overrides}};
}
test('successful actual finalizer preserves original pixels/request/source gates',async()=>{
 const f=fixture();assert.deepEqual(await finalizeNativeIgnoredFbxEvidence(f.options),{failed:false});
 assert.deepEqual(f.calls,['browser','server','sources','bundles','publish']);assert.equal(f.report.completed,true);assert.equal(f.report.sourceCoherent,true);
 assert.deepEqual(f.report.pixels,{completed:true,exactPixels:true});assert.equal(f.report.modelRequests,1);assert.equal(f.report.unusedDDSRequests,1);
 assert.deepEqual(f.report.cleanup,{browserClose:'closed',serverClose:'closed'});
});
test('rejected owned browser close still closes Vite and publishes failed evidence',async()=>{
 const f=fixture();f.options.closeBrowser=async()=>{f.calls.push('browser');throw Error('private credential/path');};
 assert.equal((await finalizeNativeIgnoredFbxEvidence(f.options)).failed,true);
 assert.deepEqual(f.calls,['browser','server','sources','bundles','publish']);assert.equal(f.report.completed,false);assert.equal(f.report.cleanup.browserClose,'failed');assert.equal(f.report.cleanup.serverClose,'closed');
 assert.equal(JSON.stringify(f.report).includes('private credential/path'),false);
});
test('synchronous and asynchronous close failures remain separate and still publish',async()=>{
 const f=fixture();f.options.closeBrowser=()=>{f.calls.push('browser');throw Error('secret A');};f.options.closeServer=async()=>{f.calls.push('server');throw Error('secret B');};
 await finalizeNativeIgnoredFbxEvidence(f.options);assert.equal(f.report.cleanup.browserClose,'failed');assert.equal(f.report.cleanup.serverClose,'failed');assert.equal(f.calls.at(-1),'publish');assert.equal(f.report.completed,false);
});
test('missing bundle directory produces fixed flag while retaining source and pixel evidence',async()=>{
 const f=fixture();f.options.hashBundles=async()=>{f.calls.push('bundles');throw Object.assign(Error('ENOENT private-directory'),{code:'ENOENT'});};
 assert.equal((await finalizeNativeIgnoredFbxEvidence(f.options)).failed,true);assert.equal(f.report.bundleHashFailure,true);assert.deepEqual(f.report.bundleSHA256,{});assert.equal(f.report.sourceCoherent,true);assert.equal(f.report.pixels.exactPixels,true);assert.equal(f.calls.at(-1),'publish');assert.equal(JSON.stringify(f.report).includes('private-directory'),false);
});
test('source hashing failure or mismatch never marks an incomplete source proof coherent',async()=>{
 const f=fixture();f.options.hashSources=async()=>{throw Error('private-source');};await finalizeNativeIgnoredFbxEvidence(f.options);assert.equal(f.report.sourceHashFailure,true);assert.equal(f.report.sourceCoherent,false);assert.equal(f.report.completed,false);assert.equal(f.calls.at(-1),'publish');
 const g=fixture();g.options.hashSources=async()=>({changed:'x'});await finalizeNativeIgnoredFbxEvidence(g.options);assert.equal(g.report.sourceCoherent,false);assert.equal(g.report.completed,false);assert.equal(g.calls.at(-1),'publish');
});
test('publication failure propagates only after both owned close attempts; absent resources are explicit',async()=>{
 const f=fixture();const failure=Error('publisher refused');f.options.publish=async()=>{f.calls.push('publish');throw failure;};await assert.rejects(finalizeNativeIgnoredFbxEvidence(f.options),error=>error===failure);assert.deepEqual(f.calls,['browser','server','sources','bundles','publish']);
 const g=fixture({closeBrowser:undefined,closeServer:undefined});await finalizeNativeIgnoredFbxEvidence(g.options);assert.deepEqual(g.report.cleanup,{browserClose:'not-created',serverClose:'not-created'});
});
