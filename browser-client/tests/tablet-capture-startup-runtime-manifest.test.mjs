// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Current V31 gate and exact historical V30 CPU inputs remain separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdtemp,mkdir,rm,lstat,realpath,unlink,symlink,chmod,link} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {readCaptureV30History,readCaptureV30Source,recoverCaptureV30Input,decodeCaptureV30History,readCurrentStartupRuntimeSource} from './integration/capture-startup-runtime-source-fixture.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),client=fileURLToPath(new URL('../',import.meta.url)),root=path.dirname(client);
const bytes=await readFile(new URL('./fixtures/capture-startup-runtime-v31-complete-source-manifest.json',import.meta.url)),m=JSON.parse(bytes);
const oldBytes=await readFile(new URL('./fixtures/capture-avatar-consumption-v30-complete-source-manifest.json',import.meta.url)),old=JSON.parse(oldBytes);
const prep=await readFile(new URL('./integration/prepare-tablet-capture-acceptance.mjs',import.meta.url),'utf8'),d=m.startupRuntimeDerivation;
const a=prep.indexOf('const manifestBytes=await readFile(proposal);'),z=prep.indexOf('const directory=await mkdtemp(',a);
assert(a>=0&&z>a);
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const gate=new AsyncFunction('assert','readFile','realpath','lstat','path','sha','source','proposal',prep.slice(a,z)+'return m;');
async function fixture(fn){
 const dir=await mkdtemp(path.join(tmpdir(),'capture-startup-runtime-'));
 try{
  for(const row of m.files){const dest=path.join(dir,row.path);await mkdir(path.dirname(dest),{recursive:true,mode:0o700});await writeFile(dest,await readFile(path.join(root,row.path)),{mode:0o600,flag:'wx'});}
  for(const relative of ['.github/workflows/browser-client.yml','browser-client/lab/README.md']){const dest=path.join(dir,relative);await mkdir(path.dirname(dest),{recursive:true,mode:0o700});await writeFile(dest,await readFile(path.join(root,relative)),{mode:0o600,flag:'wx'});}
  const proposal=path.join(dir,'manifest.json');await writeFile(proposal,bytes,{mode:0o600,flag:'wx'});
  return await fn(path.join(dir,'browser-client'),proposal,dir);
 }finally{await rm(dir,{recursive:true,force:true});}
}
const check=(s,p)=>gate(assert,readFile,realpath,lstat,path,sha,s,p);
test('V31 retains all265 source rows with honest current migrations and existing-source admissions',()=>{
 assert.equal(m.version,31);assert.equal(old.version,30);assert.equal(old.files.length,265);
 assert.equal(m.files.length,265+d.addedRows.length);assert.equal(new Set(m.files.map(r=>r.path)).size,m.files.length);
 assert.equal(d.previousManifestSHA256,sha(oldBytes));
 for(const row of old.files){const change=d.sourceMigrations[row.path];assert.deepEqual(m.files.find(r=>r.path===row.path),change?{...row,beforeSHA256:row.afterSHA256,afterSHA256:change.afterSHA256,bytes:change.bytes}:row);}
 for(const n of d.addedRows){assert(!old.files.some(r=>r.path===n));assert.equal(m.files.find(r=>r.path===n).beforeSHA256,d.admittedExistingSourceSHA256[n]??null);}
 const expected=structuredClone(old);Object.assign(expected,{version:31,scope:m.scope,files:m.files,startupRuntimeDerivation:d});Object.assign(expected.reacquisitionDerivation.chromeEnvironmentSourcePins,d.chromeEnvironmentMigrations);assert.deepEqual(m,expected);
 assert.equal(d.actualRuntimeAcceptance,false);assert.equal(d.productionHistoryFallback,false);
});
test('actual V31 production gate admits only exact current source and unchanged finite path boundary',()=>fixture(async(s,p)=>{
 assert.equal((await check(s,p )).version,31);assert(prep.includes('(?:src|shared|gateway|tests|native-input|tools)'));
 assert(!prep.includes('recoverCapture'));assert(!prep.includes('source-fixture'));assert(!m.files.some(r=>r.path.startsWith('browser-client/lab/')));
}));
test('old V30 and unknown or newline manifest refuse before any source read',()=>fixture(async(s,p)=>{
 for(const input of [oldBytes,Buffer.from(JSON.stringify({...m,version:30})),Buffer.concat([bytes,Buffer.from('\n')])]){
  await writeFile(p,input);let reads=0;await assert.rejects(()=>gate(assert,async f=>{if(f!==p)reads++;return readFile(f);},realpath,lstat,path,sha,s,p));assert.equal(reads,0);
 }
}));
test('every changed and admitted current row rejects drift old missing and alias',()=>fixture(async(s,p,dir)=>{
 const h=await readCaptureV30History();
 for(const n of [...Object.keys(d.sourceMigrations),...d.addedRows]){
  const f=path.join(dir,n),current=await readFile(f);await writeFile(f,Buffer.concat([current,Buffer.from('\n')]));await assert.rejects(()=>check(s,p));
  if(Object.hasOwn(h.files,n)&&h.files[n].sha256!==sha(current)){await writeFile(f,await readCaptureV30Source(n));await assert.rejects(()=>check(s,p));}
  await unlink(f);await assert.rejects(()=>check(s,p));const alias=path.join(dir,'alias');await writeFile(alias,current);await symlink(alias,f);await assert.rejects(()=>check(s,p));await unlink(f);await unlink(alias);await writeFile(f,current);
 }
}));
test('production preparer is one exact digest replacement and has no historical loader',async()=>{
 const before=await readCaptureV30Source('browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs');
 assert.equal(prep.split(sha(bytes)).length,2);assert.equal(prep.replace(sha(bytes),sha(oldBytes)),before);
});
test('whole bounded V30 history and old assertions remain exact',async()=>{
 const h=await readCaptureV30History();assert.equal(Object.keys(h.files).length,d.historyInputCount);assert(Object.isFrozen(h)&&Object.isFrozen(h.files));
 for(const[n,r]of Object.entries(h.files))assert.equal(sha(Buffer.from(await readCaptureV30Source(n))),r.sha256);
 for(const[n,hash]of Object.entries(d.originalAssertionBodiesSHA256)){
  const current=await readFile(path.join(root,n),'utf8'),before=await readCaptureV30Source(n);assert.equal(current.slice(current.indexOf("test('")),before.slice(before.indexOf("test('")));assert.equal(sha(Buffer.from(before.slice(before.indexOf("test('")))),hash);
 }
 const archive=await readFile(new URL('./fixtures/capture-v30-startup-runtime-before.json.gz',import.meta.url)),bad=Buffer.from(archive);bad[bad.length-1]^=1;
 assert.throws(()=>decodeCaptureV30History(bad));assert.throws(()=>decodeCaptureV30History(Buffer.alloc(131073)));assert.throws(()=>decodeCaptureV30History(new Uint8Array(archive)));
});
test('V30 CPU normalization is finite whole source with unknown current refusal',async()=>{
 for(const n of Object.keys(d.currentNormalizedSourceSHA256)){
  const before=Buffer.from(await readCaptureV30Source(n)),current=await readFile(path.join(root,n));assert.deepEqual(await recoverCaptureV30Input(n,before),before);assert.deepEqual(await recoverCaptureV30Input(n,current),before);
  for(const input of [Buffer.concat([before,Buffer.from('\n')]),Buffer.concat([current,Buffer.from('\n')]),Buffer.from('unknown')])await assert.rejects(()=>recoverCaptureV30Input(n,input));
 }
 await assert.rejects(()=>readCaptureV30Source('unknown'));
});
test('all49 browser specs and unchanged native sampler collector Core and World retain source identity',async()=>{
 assert.equal(Object.keys(d.currentBrowserSpecSHA256).length,49);assert.deepEqual(d.currentBrowserSpecSHA256,old.avatarConsumptionDerivation.currentBrowserSpecSHA256);
 for(const[n,h]of Object.entries(d.currentBrowserSpecSHA256))assert.equal(sha(await readFile(path.join(root,n))),h);
 for(const[n,h]of Object.entries(d.unchangedSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
 for(const[n,h]of Object.entries(m.reacquisitionDerivation.chromeEnvironmentSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
 assert.equal(d.nativeChildSampleVersion,1);assert.equal(d.gatewaySampleVersion,2);assert.equal(d.innerFlowVersion,2);
 assert.equal(d.applicationConsumptionVersion,1);assert.equal(d.productionBehaviorPackets.length,3);
 for(const[n,h]of Object.entries(d.extraBrowserSpecSHA256))assert.equal(sha(await readFile(path.join(root,n))),h);
 for(const[n,r]of Object.entries(d.acceptedSourceBytes))assert.equal(sha(await readFile(path.join(root,n))),r.sha256);
 assert.equal(d.runtimeQualificationPerformed,false);assert.equal(d.deadlinesOrAuthorityRelaxed,false);
});
test('strict current held-file reader rejects old altered absent unsafe and unknown physical inputs',async()=>{
 const n='browser-client/gateway/server.mjs',current=await readFile(path.join(root,n)),before=Buffer.from(await readCaptureV30Source(n));assert.deepEqual(await readCurrentStartupRuntimeSource(n,path.join(root,n)),current);
 const dir=await mkdtemp(path.join(tmpdir(),'v31-held-'));
 try{
  const f=path.join(dir,'input');for(const b of [before,Buffer.concat([current,Buffer.from('\n')]),Buffer.from('unknown'),Buffer.alloc(262145)]){await writeFile(f,b,{mode:0o600});await assert.rejects(()=>readCurrentStartupRuntimeSource(n,f));}
  await unlink(f);await assert.rejects(()=>readCurrentStartupRuntimeSource(n,f));const target=path.join(dir,'target');await writeFile(target,current,{mode:0o600});await symlink(target,f);await assert.rejects(()=>readCurrentStartupRuntimeSource(n,f));await unlink(f);await link(target,f);await assert.rejects(()=>readCurrentStartupRuntimeSource(n,f));await unlink(f);await writeFile(f,current,{mode:0o600});await chmod(f,0o622);await assert.rejects(()=>readCurrentStartupRuntimeSource(n,f));await assert.rejects(()=>readCurrentStartupRuntimeSource('unknown',target));
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('original pruning-v1 synchronous reader receives only whole V30 inputs after strict current admission',async()=>{
 const {prepareStartupV30HistoryReaders}=await import('./integration/capture-startup-runtime-source-fixture.mjs');
 const {readFileSync:raw}=await import('node:fs');
 const moduleURL=new URL('./native-ignored-fbx-diagnostics.test.mjs',import.meta.url);
 const wrapper=await prepareStartupV30HistoryReaders(moduleURL,raw);
 for(const n of ['browser-client/tests/fixtures/native-ignored-fbx-pixels.ts','browser-client/tests/integration/native-ignored-fbx-pixels.mjs']){
  const file=path.join(root,n),before=await readCaptureV30Source(n);
  assert.equal(wrapper.readFileSync(file,'utf8'),before);assert.equal(wrapper.readFileSync(new URL('file://'+file),'utf8'),before);
  const refused=await prepareStartupV30HistoryReaders(moduleURL,()=>Buffer.from('changed-after-held-read'));
  assert.throws(()=>refused.readFileSync(file,'utf8'));
 }
});
test('finite ancestor passthrough is backed by exact whole immutable archive sources',async()=>{
 const {readdir}=await import('node:fs/promises');const {gunzipSync}=await import('node:zlib');const backed=new Map();
 for(const filename of await readdir(path.join(client,'tests/fixtures'))){if(!filename.endsWith('.json.gz'))continue;
  const archive=JSON.parse(gunzipSync(await readFile(path.join(client,'tests/fixtures',filename)),{maxOutputLength:524288}));
  if(!archive.files||typeof archive.files!=='object')continue;
  for(const[n,row]of Object.entries(archive.files)){if(typeof row?.source!=='string')continue;const b=Buffer.from(row.source);assert.equal(sha(b),row.sha256);backed.set(n+'@'+row.sha256,b);}
 }
 for(const[n,hashes]of Object.entries(d.ancestorSourceSHA256))for(const h of hashes){const b=backed.get(n+'@'+h);assert(b);assert.deepEqual(await recoverCaptureV30Input(n,b),b);await assert.rejects(()=>recoverCaptureV30Input(n,Buffer.concat([b,Buffer.from('\n')])));}
});
