// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Strict CPU historical inputs; no runtime admission or source fallback.
import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync as readCurrentFileSync} from 'node:fs';import {mkdtemp,writeFile,mkdir,rm,symlink,link} from 'node:fs/promises';
import {createHash} from 'node:crypto';import {join} from 'node:path';import {tmpdir} from 'node:os';import {pathToFileURL} from 'node:url';
import {recoverReviewedAvatarSource,readReviewedAvatarSource as readHistoricalAvatarSource,avatarDeliverySourcePins} from './fixtures/avatar-delivery-source-fixture.mjs';
import {prepareAvatarV26HistoryReaders} from './integration/capture-software-managed-source-fixture.mjs';
const {readFileSync,readReviewedAvatarSource}=await prepareAvatarV26HistoryReaders(readCurrentFileSync,readHistoricalAvatarSource,recoverReviewedAvatarSource);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const source=readFileSync(new URL('./fixtures/avatar-delivery-source-fixture.mjs',import.meta.url));
const archive=readFileSync(new URL('./fixtures/avatar-delivery-before.json.gz',import.meta.url));
test('all eight actual candidate whole sources authenticate before bounded CPU historical recovery',()=>{
 for(const [path,pin] of Object.entries(avatarDeliverySourcePins)){
  const url=new URL('../'+path.replace(/^browser-client\//,''),import.meta.url),bytes=readFileSync(url);
  assert.equal(sha(bytes),pin.after);assert.equal(sha(recoverReviewedAvatarSource(path,bytes)),pin.before);
  assert.equal(sha(readReviewedAvatarSource(url)),pin.before);assert.equal(typeof readReviewedAvatarSource(url,'utf8'),'string');
 }
});
test('old, changed, missing, wrong-type, oversized and unknown source bytes refuse without allowance',()=>{
 const [path,pin]=Object.entries(avatarDeliverySourcePins)[0],url=new URL('../'+path.replace(/^browser-client\//,''),import.meta.url),bytes=readFileSync(url),old=recoverReviewedAvatarSource(path,bytes);
 for(const bad of [old,Buffer.concat([bytes,Buffer.from('\n')]),undefined,bytes.toString(),Buffer.alloc(256*1024+1)])assert.throws(()=>recoverReviewedAvatarSource(path,bad),/history-refused/);
 assert.throws(()=>recoverReviewedAvatarSource('browser-client/src/world.ts',bytes),/history-refused/);
 assert.throws(()=>readReviewedAvatarSource(new URL('../src/world.ts',import.meta.url)),/history-refused/);
 assert.throws(()=>readReviewedAvatarSource(url,'base64'),/history-refused/);
 assert.throws(()=>readReviewedAvatarSource('file:///private'),/history-refused/);
 assert.equal(pin.after,sha(bytes));assert(Object.isFrozen(pin));
});
async function copyFixture(fn){const root=await mkdtemp(join(tmpdir(),'overte-avatar-history-'));try{const dir=join(root,'browser-client/tests/fixtures');await mkdir(dir,{recursive:true,mode:0o700});await writeFile(join(dir,'avatar-delivery-source-fixture.mjs'),source,{mode:0o600});await writeFile(join(dir,'avatar-delivery-before.json.gz'),archive,{mode:0o600});await fn(root,dir);}finally{await rm(root,{recursive:true,force:true});}}
test('actual held-source reader refuses missing, symlink and hardlinked known inputs in fresh own copies',async()=>copyFixture(async(root,dir)=>{
 const m=await import(pathToFileURL(join(dir,'avatar-delivery-source-fixture.mjs')));
 const path='gateway/native-bridge.js',dest=join(root,'browser-client',path);await mkdir(join(root,'browser-client/gateway'),{mode:0o700});
 assert.throws(()=>m.readReviewedAvatarSource(pathToFileURL(dest)),/history-refused/);
 const bytes=readFileSync(new URL('../'+path,import.meta.url)),target=join(root,'target');await writeFile(target,bytes,{mode:0o600});await symlink(target,dest);
 assert.throws(()=>m.readReviewedAvatarSource(pathToFileURL(dest)),/history-refused/);await rm(dest);await link(target,dest);
 assert.throws(()=>m.readReviewedAvatarSource(pathToFileURL(dest)),/history-refused/);await rm(dest);await writeFile(dest,bytes,{mode:0o600});
 assert.equal(sha(m.readReviewedAvatarSource(pathToFileURL(dest))),avatarDeliverySourcePins['browser-client/'+path].before);
}));
test('missing or altered authenticated whole archive refuses before history or production bytes are used',async()=>{
 for(const kind of ['missing','changed'])await copyFixture(async(root,dir)=>{
  const p=join(dir,'avatar-delivery-before.json.gz');if(kind==='missing')await rm(p);else await writeFile(p,Buffer.concat([archive,Buffer.from('PRIVATE')]),{mode:0o600});
  await assert.rejects(import(pathToFileURL(join(dir,'avatar-delivery-source-fixture.mjs'))),/history-refused/);
 });
});
test('CPU history helper has no production import and makes no live source or unknown path claim',()=>{
 for(const path of ['gateway/native-bridge.js','gateway/server.mjs','gateway/native-avatar-sample-diagnostics.js','gateway/native-avatar-stdout-projection.mjs','tests/integration/real-session.mjs','tests/integration/native-peer-diagnostic.mjs']){
  const bytes=readFileSync(new URL('../'+path,import.meta.url),'utf8');assert(!bytes.includes('avatar-delivery-source-fixture'));
 }
 assert(source.toString().includes('CPU historical input only'));assert(source.toString().includes('sha(bytes)!==pin.after'));
});
