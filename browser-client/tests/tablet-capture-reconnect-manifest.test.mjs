// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {readFile,writeFile,mkdtemp,mkdir,rm,realpath,lstat,unlink,symlink} from 'node:fs/promises';import {tmpdir} from 'node:os';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
import {readCaptureV10Source,recoverCaptureV10Input} from './integration/capture-environment-source-fixture.mjs';
import {readCaptureV9History,readCaptureV9Source,decodeCaptureV9History,recoverCaptureV9Input} from './integration/capture-reconnect-source-fixture.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),client=fileURLToPath(new URL('../',import.meta.url)),bytes=await readFile(new URL('./fixtures/capture-reconnect-v10-complete-source-manifest.json',import.meta.url)),m=JSON.parse(bytes),oldBytes=await readFile(new URL('./fixtures/capture-status-v9-complete-source-manifest.json',import.meta.url)),old=JSON.parse(oldBytes),prep=await readCaptureV10Source('browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs');
const a=prep.indexOf('const manifestBytes=await readFile(proposal);'),z=prep.indexOf('const directory=await mkdtemp(',a);assert(a>=0&&z>a);const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor,checkSource=new AsyncFunction('assert','readFile','realpath','lstat','path','sha','source','proposal',prep.slice(a,z)+'return m;');
async function fixture(fn){const dir=await mkdtemp(path.join(tmpdir(),'capture-reconnect-guard-'));try{const source=path.join(dir,'browser-client');for(const r of m.files){if(!r.path.startsWith('browser-client/'))continue;const relative=r.path.slice(15),dest=path.join(source,relative);await mkdir(path.dirname(dest),{recursive:true});await writeFile(dest,await recoverCaptureV10Input('browser-client/'+relative,await readFile(path.join(client,relative))),{mode:0o600,flag:'wx'});}const proposal=path.join(dir,'manifest.json');await writeFile(proposal,bytes);return await fn(source,proposal,dir);}finally{await rm(dir,{recursive:true,force:true});}}
const check=(source,proposal)=>checkSource(assert,readFile,realpath,lstat,path,sha,source,proposal);

test('successor enumerates every original119 row and only exact declared migrations/additions',async()=>{
 assert.equal(sha(oldBytes),'e78d679622ce9d3494cadab32288b5c52925267fb3c0f62ffc380e6771220802');assert.equal(old.files.length,119);assert.equal(m.version,10);const d=m.reconnectDerivation;
 assert.equal(d.previousManifestSHA256,sha(oldBytes));assert.equal(m.files.length,119+d.addedRows.length);assert.equal(m.files.length,new Set(m.files.map(r=>r.path)).size);
 for(const r of old.files){const n=m.files.filter(v=>v.path===r.path);assert.equal(n.length,1);const change=d.migrations[r.path];if(change){assert.equal(change.beforeSHA256,r.afterSHA256);assert.equal(n[0].beforeSHA256,r.afterSHA256);assert.equal(n[0].afterSHA256,change.afterSHA256);}else assert.deepEqual(n[0],r);}
 for(const key of ['limits','verification','packagePins'])assert.deepEqual(m[key],old[key]);assert.deepEqual(m.dependencyPins,{...old.dependencyPins,'browser-client/src/world.ts':d.migrations['browser-client/src/world.ts'].afterSHA256});
 const doc=m.files.find(r=>r.path==='docs/browser-client/BROWSER_MICROPHONE_CONTROLS.md');assert.equal(doc.afterSHA256,'68f392980cdece6f0eac13fff65de89d1a22d8ed94bebd037b0b538d8d38a178');assert.equal(d.preexistingOutsideClientDocumentationSHA256,'a01bc236eef5b602b695b0f0aa52d38004a0ba43e17519375b1eec4e49ae58d5');
});
test('production preparer recovers whole original after exactly one expected-manifest literal',async()=>{
 assert.equal(prep.split(sha(bytes)).length,2);const recovered=prep.replace(sha(bytes),sha(oldBytes));assert.equal(recovered,await readCaptureV9Source('tests/integration/prepare-tablet-capture-acceptance.mjs'));assert.equal(sha(Buffer.from(recovered)),'00c666b3ed34f9539ede609a6e35a03864e9f7542b0c8e0112cd5919a771ca42');assert(!prep.includes('capture-reconnect-source-fixture'));
});
test('actual extracted production source gate accepts the complete successor',()=>fixture(async(s,p)=>assert.equal((await check(s,p)).version,10)));
test('old and invented manifests refuse before any source read',()=>fixture(async(s,p)=>{
 for(const b of [oldBytes,Buffer.from(JSON.stringify({...m,version:9})),Buffer.from(JSON.stringify({...m,files:[]}))]){await writeFile(p,b);let reads=0;await assert.rejects(()=>checkSource(assert,async f=>{if(f!==p)reads++;return readFile(f);},realpath,lstat,path,sha,s,p));assert.equal(reads,0);}
}));
test('each changed source/recovery/regression row refuses byte drift and all original119 sources remain checked',()=>fixture(async(s,p)=>{
 for(const name of [...Object.keys(m.reconnectDerivation.migrations),...m.reconnectDerivation.addedRows]){const f=path.join(s,name.slice(15)),b=await readFile(f);await writeFile(f,Buffer.concat([b,Buffer.from('\n')]));await assert.rejects(()=>check(s,p),/Exact reviewed capture composition required/);await writeFile(f,b);}
 for(const r of m.files.filter(r=>r.path.startsWith('browser-client/'))){const b=await readFile(path.join(s,r.path.slice(15)));assert.equal(sha(b),r.afterSHA256);}
}));
test('cache and history symlink aliases refuse original canonical-source gate',async()=>{
 for(const relative of ['src/prepared-fbx-cache.ts','tests/fixtures/capture-v9-reconnect-before.json.gz','tests/integration/capture-reconnect-source-fixture.mjs'])await fixture(async(s,p,d)=>{const f=path.join(s,relative),other=path.join(d,'alias');await writeFile(other,await readFile(f));await unlink(f);await symlink(other,f);await assert.rejects(()=>check(s,p));});
});
test('seven whole before inputs recover exact bytes; corrupted/bounded/unknown history refuses',async()=>{
 const history=await readCaptureV9History();assert.equal(Object.keys(history.files).length,7);assert(Object.isFrozen(history)&&Object.isFrozen(history.files));
 for(const [name,row]of Object.entries(history.files)){assert.equal(sha(Buffer.from(row.source)),row.sha256);assert(Object.isFrozen(row));}
 for(const name of Object.keys(m.reconnectDerivation.migrations)){const rel=name.slice(15),b=await readFile(path.join(client,rel));assert.equal((await recoverCaptureV9Input(rel,b)).toString(),history.files[rel].source);await assert.rejects(()=>recoverCaptureV9Input(rel,Buffer.concat([b,Buffer.from('\n')])));}
 const b=await readFile(new URL('./fixtures/capture-v9-reconnect-before.json.gz',import.meta.url)),bad=Buffer.from(b);bad[bad.length-1]^=1;assert.throws(()=>decodeCaptureV9History(bad));assert.throws(()=>decodeCaptureV9History(Buffer.alloc(131073)));assert.throws(()=>decodeCaptureV9History(new Uint8Array(b)));await assert.rejects(()=>readCaptureV9Source('unknown'));
});
test('old production receipt metadata cannot authenticate a current-source rebuilt distribution',()=>{
 const d=m.reconnectDerivation;assert.equal(d.oldProductionReceiptSHA256,'20cedb53d46a8b8b123b82bb385b6b380458c08cdaaa98256d506e97f0fc0212');assert.equal(d.oldProductionReceiptCompleteManifestSHA256,sha(oldBytes));assert.notEqual(d.oldProductionReceiptCompleteManifestSHA256,sha(bytes));assert.equal(d.oldProductionReceiptPreparerSHA256,'00c666b3ed34f9539ede609a6e35a03864e9f7542b0c8e0112cd5919a771ca42');assert.notEqual(d.oldProductionReceiptPreparerSHA256,sha(Buffer.from(prep)));assert.equal(d.actualProductionBuildQualified,false);assert.equal(d.actualNativeOrBrowserQualified,false);
});
