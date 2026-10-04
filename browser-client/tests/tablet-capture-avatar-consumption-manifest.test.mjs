// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Current V30 gate and exact historical V29 CPU inputs remain separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdtemp,mkdir,rm,lstat,realpath,unlink,symlink,chmod,link} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {readCaptureV29History,readCaptureV29Source,recoverCaptureV29Input,decodeCaptureV29History,readCurrentAvatarConsumptionSource} from './integration/capture-avatar-consumption-source-fixture.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),client=fileURLToPath(new URL('../',import.meta.url)),root=path.dirname(client);
const bytes=await readFile(new URL('./fixtures/capture-avatar-consumption-v30-complete-source-manifest.json',import.meta.url)),m=JSON.parse(bytes);
const oldBytes=await readFile(new URL('./fixtures/capture-pruning-flight-v29-complete-source-manifest.json',import.meta.url)),old=JSON.parse(oldBytes);
const prep=await readFile(new URL('./integration/prepare-tablet-capture-acceptance.mjs',import.meta.url),'utf8'),d=m.avatarConsumptionDerivation;
const a=prep.indexOf('const manifestBytes=await readFile(proposal);'),z=prep.indexOf('const directory=await mkdtemp(',a);
assert(a>=0&&z>a);
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const gate=new AsyncFunction('assert','readFile','realpath','lstat','path','sha','source','proposal',prep.slice(a,z)+'return m;');
async function fixture(fn){
 const dir=await mkdtemp(path.join(tmpdir(),'capture-avatar-consumption-'));
 try{
  for(const row of m.files){const dest=path.join(dir,row.path);await mkdir(path.dirname(dest),{recursive:true,mode:0o700});await writeFile(dest,await readFile(path.join(root,row.path)),{mode:0o600,flag:'wx'});}
  for(const relative of ['.github/workflows/browser-client.yml','browser-client/lab/README.md']){const dest=path.join(dir,relative);await mkdir(path.dirname(dest),{recursive:true,mode:0o700});await writeFile(dest,await readFile(path.join(root,relative)),{mode:0o600,flag:'wx'});}
  const proposal=path.join(dir,'manifest.json');await writeFile(proposal,bytes,{mode:0o600,flag:'wx'});
  return await fn(path.join(dir,'browser-client'),proposal,dir);
 }finally{await rm(dir,{recursive:true,force:true});}
}
const check=(s,p)=>gate(assert,readFile,realpath,lstat,path,sha,s,p);
test('V30 retains all256 source rows with honest current migrations and existing-source admissions',()=>{
 assert.equal(m.version,30);assert.equal(old.version,29);assert.equal(old.files.length,256);
 assert.equal(m.files.length,256+d.addedRows.length);assert.equal(new Set(m.files.map(r=>r.path)).size,m.files.length);
 assert.equal(d.previousManifestSHA256,sha(oldBytes));
 for(const row of old.files){const change=d.sourceMigrations[row.path];assert.deepEqual(m.files.find(r=>r.path===row.path),change?{...row,beforeSHA256:row.afterSHA256,afterSHA256:change.afterSHA256,bytes:change.bytes}:row);}
 for(const n of d.addedRows){assert(!old.files.some(r=>r.path===n));assert.equal(m.files.find(r=>r.path===n).beforeSHA256,d.admittedExistingSourceSHA256[n]??null);}
 const expected=structuredClone(old);Object.assign(expected,{version:30,scope:m.scope,files:m.files,avatarConsumptionDerivation:d});assert.deepEqual(m,expected);
 assert.equal(d.actualRuntimeAcceptance,false);assert.equal(d.productionHistoryFallback,false);
});
test('actual V30 production gate admits only exact current source and unchanged finite path boundary',()=>fixture(async(s,p)=>{
 assert.equal((await check(s,p)).version,30);assert(prep.includes('(?:src|shared|gateway|tests|native-input|tools)'));
 assert(!prep.includes('recoverCapture'));assert(!prep.includes('source-fixture'));assert(!m.files.some(r=>r.path.startsWith('browser-client/lab/')));
}));
test('old V29 and unknown or newline manifest refuse before any source read',()=>fixture(async(s,p)=>{
 for(const input of [oldBytes,Buffer.from(JSON.stringify({...m,version:29})),Buffer.concat([bytes,Buffer.from('\n')])]){
  await writeFile(p,input);let reads=0;await assert.rejects(()=>gate(assert,async f=>{if(f!==p)reads++;return readFile(f);},realpath,lstat,path,sha,s,p));assert.equal(reads,0);
 }
}));
test('every changed and admitted current row rejects drift old missing and alias',()=>fixture(async(s,p,dir)=>{
 const h=await readCaptureV29History();
 for(const n of [...Object.keys(d.sourceMigrations),...d.addedRows]){
  const f=path.join(dir,n),current=await readFile(f);await writeFile(f,Buffer.concat([current,Buffer.from('\n')]));await assert.rejects(()=>check(s,p));
  if(Object.hasOwn(h.files,n)&&h.files[n].sha256!==sha(current)){await writeFile(f,await readCaptureV29Source(n));await assert.rejects(()=>check(s,p));}
  await unlink(f);await assert.rejects(()=>check(s,p));const alias=path.join(dir,'alias');await writeFile(alias,current);await symlink(alias,f);await assert.rejects(()=>check(s,p));await unlink(f);await unlink(alias);await writeFile(f,current);
 }
}));
test('production preparer is one exact digest replacement and has no historical loader',async()=>{
 const before=await readCaptureV29Source('browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs');
 assert.equal(prep.split(sha(bytes)).length,2);assert.equal(prep.replace(sha(bytes),sha(oldBytes)),before);
});
test('whole bounded V29 history and old assertions remain exact',async()=>{
 const h=await readCaptureV29History();assert.equal(Object.keys(h.files).length,d.historyInputCount);assert(Object.isFrozen(h)&&Object.isFrozen(h.files));
 for(const[n,r]of Object.entries(h.files))assert.equal(sha(Buffer.from(await readCaptureV29Source(n))),r.sha256);
 for(const[n,hash]of Object.entries(d.originalAssertionBodiesSHA256)){
  const current=await readFile(path.join(root,n),'utf8'),before=await readCaptureV29Source(n);assert.equal(current.slice(current.indexOf("test('")),before.slice(before.indexOf("test('")));assert.equal(sha(Buffer.from(before.slice(before.indexOf("test('")))),hash);
 }
 const archive=await readFile(new URL('./fixtures/capture-v29-avatar-consumption-before.json.gz',import.meta.url)),bad=Buffer.from(archive);bad[bad.length-1]^=1;
 assert.throws(()=>decodeCaptureV29History(bad));assert.throws(()=>decodeCaptureV29History(Buffer.alloc(131073)));assert.throws(()=>decodeCaptureV29History(new Uint8Array(archive)));
});
test('V29 CPU normalization is finite whole source with unknown current refusal',async()=>{
 for(const n of Object.keys(d.currentNormalizedSourceSHA256)){
  const before=Buffer.from(await readCaptureV29Source(n)),current=await readFile(path.join(root,n));assert.deepEqual(await recoverCaptureV29Input(n,before),before);assert.deepEqual(await recoverCaptureV29Input(n,current),before);
  for(const input of [Buffer.concat([before,Buffer.from('\n')]),Buffer.concat([current,Buffer.from('\n')]),Buffer.from('unknown')])await assert.rejects(()=>recoverCaptureV29Input(n,input));
 }
 await assert.rejects(()=>readCaptureV29Source('unknown'));
});
test('all49 browser specs and unchanged native sampler collector Core and World retain source identity',async()=>{
 assert.equal(Object.keys(d.currentBrowserSpecSHA256).length,49);assert.deepEqual(d.currentBrowserSpecSHA256,old.pruningFlightDerivation.currentBrowserSpecSHA256);
 for(const[n,h]of Object.entries(d.currentBrowserSpecSHA256))assert.equal(sha(await readFile(path.join(root,n))),h);
 for(const[n,h]of Object.entries(d.unchangedSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
 for(const[n,h]of Object.entries(m.reacquisitionDerivation.chromeEnvironmentSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
 assert.equal(d.nativeChildSampleVersion,1);assert.equal(d.gatewaySampleVersion,2);assert.equal(d.innerFlowVersion,2);
 assert.equal(d.physicalFlightReleasedOnlyByMatchingSendCallback,true);assert.equal(d.logicalCreditReleasedOnlyByCurrentApplicationAck,true);
 assert.equal(d.maximumSerializedAvatarSnapshotReferences,2);assert.equal(d.creditTimeoutOrRetryAdded,false);
 assert.equal(d.synchronousWorldApplicationIsNotGpuOrNativeAcceptance,true);
});
test('strict current held-file reader rejects old altered absent unsafe and unknown physical inputs',async()=>{
 const n='browser-client/gateway/server.mjs',current=await readFile(path.join(root,n)),before=Buffer.from(await readCaptureV29Source(n));assert.deepEqual(await readCurrentAvatarConsumptionSource(n,path.join(root,n)),current);
 const dir=await mkdtemp(path.join(tmpdir(),'v30-held-'));
 try{
  const f=path.join(dir,'input');for(const b of [before,Buffer.concat([current,Buffer.from('\n')]),Buffer.from('unknown'),Buffer.alloc(262145)]){await writeFile(f,b,{mode:0o600});await assert.rejects(()=>readCurrentAvatarConsumptionSource(n,f));}
  await unlink(f);await assert.rejects(()=>readCurrentAvatarConsumptionSource(n,f));const target=path.join(dir,'target');await writeFile(target,current,{mode:0o600});await symlink(target,f);await assert.rejects(()=>readCurrentAvatarConsumptionSource(n,f));await unlink(f);await link(target,f);await assert.rejects(()=>readCurrentAvatarConsumptionSource(n,f));await unlink(f);await writeFile(f,current,{mode:0o600});await chmod(f,0o622);await assert.rejects(()=>readCurrentAvatarConsumptionSource(n,f));await assert.rejects(()=>readCurrentAvatarConsumptionSource('unknown',target));
 }finally{await rm(dir,{recursive:true,force:true});}
});
