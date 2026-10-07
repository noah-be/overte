// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {PassThrough}from'node:stream';import{readFile,lstat,rm}from'node:fs/promises';import{createHash}from'node:crypto';
import{networkTestStderr,projectNetworkTestStderr,persistPrivateNetworkTestStderr}from'./network-test-stderr.mjs';
function child(){return {stderr:new PassThrough()};}
test('the same child stream remains observed across readiness and after native-start; split errors use only fixed projection',async()=>{
 const owner=child(),capture=networkTestStderr();capture.watch(owner);
 owner.stderr.write(Buffer.from('startup\n'));owner.stderr.write(Buffer.from('bwrap: capset fai'));owner.stderr.write(Buffer.from('led: Operation not permitted\n'));
 const row=capture.projection();assert.equal(row.operation,'bubblewrap-capset');assert.equal(row.errnoReported,1);assert.equal(row.truncated,false);
 await capture.finish();assert.equal(owner.stderr.listenerCount('data'),0);
});
test('a small retained prefix never keeps the oversized source buffer backing array',async()=>{
 const owner=child(),capture=networkTestStderr();capture.watch(owner);const bytes=Buffer.alloc(1024*1024,97);owner.stderr.write(bytes);bytes.fill(0);
 const row=capture.projection();assert.equal(row.retainedBytes,16384);assert.equal(row.observedBytes,1024*1024);assert(row.truncated);assert.equal(row.operation,'unclassified');await capture.finish();
});
test('one16KiB aggregate budget applies to all four known child streams',async()=>{
 const capture=networkTestStderr(),children=Array.from({length:4},child);children.forEach(c=>capture.watch(c));assert.throws(()=>capture.watch(child()),/ownership refused/);
 children.forEach(c=>c.stderr.write(Buffer.alloc(10000,97)));assert.equal(capture.projection().retainedBytes,16384);assert.equal(capture.projection().observedBytes,40000);await capture.finish();
});
test('unknown/private paths and forged errno prose never become public strings',()=>{
 const text=Buffer.from('secret-value https://private.example/id\nbwrap: bind /private/file: Permission denied\nbwrap: capset failed: secret-value\n');
 const row=projectNetworkTestStderr(text,text.length);assert.equal(row.operation,'unclassified');assert.equal(row.errnoReported,null);assert(!JSON.stringify(row).includes('secret-value'));assert(!JSON.stringify(row).includes('private.example'));assert(!JSON.stringify(row).includes('/private'));
});
test('conflicting known operation lines and incomplete censored suffix refuse classification',()=>{
 const bytes=Buffer.from('bwrap: capset failed: Operation not permitted\nbwrap: setting up uid map: Permission denied\n');assert.equal(projectNetworkTestStderr(bytes,bytes.length).operation,'unclassified');
 const suffix=Buffer.from('bwrap: capset failed: Operation not permitted');assert.equal(projectNetworkTestStderr(suffix,suffix.length+1).operation,'unclassified');
});
test('Python traceback reports only fixed exception/errno and inline probe line without private paths',()=>{
 const bytes=Buffer.from('Traceback (most recent call last):\n  File "<string>", line 17, in <module>\n  File "/private/secret.py", line 123, in open\nPermissionError: [Errno 13] Permission denied: "/private/secret-proof.json"\n');
 const row=projectNetworkTestStderr(bytes,bytes.length);assert.deepEqual(row.pythonException,{kind:'PermissionError',errnoReported:13});assert.equal(row.pythonProbeLine,17);
 assert(!JSON.stringify(row).includes('/private'));assert(!JSON.stringify(row).includes('secret'));
});
test('conflicting, incomplete and unapproved Python errors remain unclassified',()=>{
 for(const text of ['PermissionError: [Errno 13] private\nFileNotFoundError: [Errno 2] private\n','OSError: [Errno 999] private\n','CustomPrivateError: [Errno 13] private\n']){
  const bytes=Buffer.from(text);assert.equal(projectNetworkTestStderr(bytes,bytes.length).pythonException,null);
 }
 const bytes=Buffer.from('PermissionError: [Errno 13] private');assert.equal(projectNetworkTestStderr(bytes,bytes.length+1).pythonException,null);
 const frame=Buffer.from('  File "<string>", line 257, in <module>\n');assert.equal(projectNetworkTestStderr(frame,frame.length).pythonProbeLine,null);
});
test('native boundary refusal is a boolean only for the exact existing fixed message',()=>{
 for(const [text,expected]of [['Native capability boundary refused.\n',true],['Native capability boundary refused: private\n',false]]){
  const bytes=Buffer.from(text);assert.equal(projectNetworkTestStderr(bytes,bytes.length).nativeBoundaryRefused,expected);
 }
});
test('immutable owner refusal projects only its exact reviewed category without exception prose',()=>{
 const bytes=Buffer.from('owner_admission.Refusal: owner-profile\n');assert.equal(projectNetworkTestStderr(bytes,bytes.length).admissionRefusal,'owner-profile');
 for(const text of ['owner_admission.Refusal: private-secret\n','owner_admission.Refusal: owner-profile private-secret\n','owner_admission.Refusal: owner-profile\nowner_admission.Refusal: worker-executable\n']){
  const input=Buffer.from(text),row=projectNetworkTestStderr(input,input.length);assert.equal(row.admissionRefusal,null);assert(!JSON.stringify(row).includes('private-secret'));
 }
});
test('mixed known and unknown or malformed owner markers refuse the complete owner classification',()=>{
 for(const suffix of ['owner_admission.Refusal: private-secret\n','owner_admission.Refusal: owner-profile private-secret\n']){
  const bytes=Buffer.from('owner_admission.Refusal: owner-profile\n'+suffix),row=projectNetworkTestStderr(bytes,bytes.length);
  assert.equal(row.admissionRefusal,null);assert(!JSON.stringify(row).includes('private-secret'));
 }
});
test('truncated owner capture never implies a complete consistent owner-refusal category',()=>{
 const bytes=Buffer.from('owner_admission.Refusal: owner-profile\nowner_admission.Refusal: owner-');
 const row=projectNetworkTestStderr(bytes,bytes.length+1);assert.equal(row.admissionRefusal,null);assert.equal(row.truncated,true);
});
test('exact current trusted-C marker and existing safe preparation projection remain reusable',()=>{
 const bytes=Buffer.from('OVERTE_NET_TRUSTED_FAILURE={"version":1,"phase":"route-install-ack","errnoObserved":1}\n');
 assert.deepEqual(projectNetworkTestStderr(bytes,bytes.length).preparation.trustedSetupFailure,{version:1,phase:'route-install-ack',errnoObserved:1});
});
test('unknown input types/counts cannot enter diagnostic serialization',()=>{
 for(const args of [["secret",6],[Buffer.alloc(16385),16385],[Buffer.alloc(2),1],[Buffer.alloc(1),NaN],[Buffer.alloc(1),1,'private']])assert.throws(()=>projectNetworkTestStderr(...args),/projection refused/);
});
test('owned artifact preserves exact raw bytes only in0600file/0700directory',{skip:process.platform!=='linux'},async()=>{
 const bytes=Buffer.from('bwrap: capset failed: Operation not permitted\n');const receipt=await persistPrivateNetworkTestStderr(bytes);
 try{assert.equal((await lstat(receipt.directory)).mode&0o777,0o700);assert.equal((await lstat(receipt.file)).mode&0o777,0o600);assert.deepEqual(await readFile(receipt.file),bytes);}finally{await rm(receipt.directory,{recursive:true,force:true});}
});
test('capture stop removes listeners and rejects later watches',async()=>{
 const owner=child(),capture=networkTestStderr();capture.watch(owner);await capture.finish();assert.equal(owner.stderr.listenerCount('data'),0);assert.throws(()=>capture.watch(child()),/ownership refused/);
});
test('owned artifact refusal cannot replace the original failure or publish raw messages',{skip:process.platform!=='linux'},async(t)=>{
 const uid=process.getuid();t.mock.method(process,'getuid',()=>uid+1);
 for(const frozen of [false,true]){
  const original=Error('original assertion failure'),error=frozen?Object.freeze(original):original;
  const owner=child(),capture=networkTestStderr();capture.watch(owner);owner.stderr.write(Buffer.from('private-secret-unclassified\n'));
  await capture.finish(error);assert.equal(error,original);
  if(frozen)assert.equal(error.message,'original assertion failure');
  else{assert(error.message.startsWith('original assertion failure [network-test-stderr: '));assert(error.message.includes('"artifactSaved":false'));assert(!error.message.includes('private-secret'));}
 }
});
test('all original three actual-control expressions and cleanup/deadlines recover byte-exactly',async()=>{
 let source=await readFile(new URL('./network-sandbox.test.mjs',import.meta.url),'utf8');
 source=source.replace("import { networkTestStderr } from './network-test-stderr.mjs';\n",'');
 assert.equal(source.split('    const stderr = networkTestStderr(); let failed;\n').length,4);source=source.replaceAll('    const stderr = networkTestStderr(); let failed;\n','');
 assert.equal(source.split('owned.push(child); stderr.watch(child); return child;').length,3);source=source.replaceAll('owned.push(child); stderr.watch(child); return child;',"owned.push(child); child.stderr.on('data', () => {}); return child;");
 source=source.replaceAll('        failed=error; throw preparationFailure(error);','        throw preparationFailure(error);');
 source=source.replace("child.stderr.pipe(process.stderr,{end:false});return child;","child.stderr.on('data',()=>{});return child;");
 source=source.replace('        stderr.watch(parent);',"        parent.stderr.on('data', () => {});");
 source=source.replace('    } catch(error) { failed=error; throw error; } finally {','    } finally {');
 assert.equal(source.split('        await stderr.finish(failed);\n').length,4);source=source.replaceAll('        await stderr.finish(failed);\n','');
 assert.equal(createHash('sha256').update(source).digest('hex'),'6f9ed987dc29f7ef2f4f2a68e00b96ddacd71c449cbdb49a3311f4a2ad49e90f');
});
