// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Shipping V32 source gates and exact historical V31 tests are separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile as readPhysicalFile,writeFile,mkdtemp,mkdir,rm,lstat,realpath,unlink,symlink} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {recoverCaptureV31Input,readCaptureV31Source,decodeCaptureV31History} from './integration/capture-movement-input-source-fixture.mjs';

import {normalizeStartupIntegrationInput,readStartupIntegrationParentSource} from './integration/capture-startup-integration-source-fixture.mjs';
const readFile=async(input,options)=>{const bytes=await readPhysicalFile(input),file=input instanceof URL?fileURLToPath(input):path.resolve(input),relative=path.relative(fileURLToPath(new URL('../../',import.meta.url)),file),recovered=normalizeStartupIntegrationInput('movement',relative,bytes);return typeof options==='string'?recovered.toString(options):recovered;};
const root=fileURLToPath(new URL('../../',import.meta.url)),sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const bytes=await readFile(new URL('./fixtures/capture-movement-input-v32-complete-source-manifest.json',import.meta.url)),m=JSON.parse(bytes);
const oldBytes=await readFile(new URL('./fixtures/capture-software-graphics-v31-complete-source-manifest.json',import.meta.url)),old=JSON.parse(oldBytes),d=m.movementInputDerivation;
const prep=readStartupIntegrationParentSource('movement','browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs');
const start=prep.indexOf('const manifestBytes=await readFile(proposal);'),end=prep.indexOf('const directory=await mkdtemp(',start);
assert(start>=0 && end>start);
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const gate=new AsyncFunction('assert','readFile','realpath','lstat','path','sha','source','proposal',prep.slice(start,end)+'return m;');

async function fixture(fn){
    const dir=await mkdtemp(path.join(tmpdir(),'capture-movement-input-'));
    try{
        for(const row of m.files){const file=path.join(dir,row.path);await mkdir(path.dirname(file),{recursive:true});await writeFile(file,await readFile(path.join(root,row.path)));}
        for(const relative of ['.github/workflows/browser-client.yml','browser-client/lab/README.md']){const file=path.join(dir,relative);await mkdir(path.dirname(file),{recursive:true});await writeFile(file,await readFile(path.join(root,relative)));}
        const proposal=path.join(dir,'manifest.json');await writeFile(proposal,bytes);
        return await fn(path.join(dir,'browser-client'),proposal,dir);
    }finally{await rm(dir,{recursive:true,force:true});}
}

test('V32 preserves every V31 row and records only the explicit movement repair',async()=>{
    assert.equal(old.version,31);assert.equal(m.version,32);assert.equal(d.previousManifestSHA256,sha(oldBytes));
    assert.equal(m.files.length,old.files.length+d.addedRows.length);assert.equal(new Set(m.files.map(r=>r.path)).size,m.files.length);
    for(const row of old.files){const change=d.sourceMigrations[row.path];assert.deepEqual(m.files.find(r=>r.path===row.path),change?{...row,beforeSHA256:row.afterSHA256,afterSHA256:change.afterSHA256,bytes:change.bytes}:row);}
    const expected=structuredClone(old);Object.assign(expected,{version:32,scope:m.scope,files:m.files,movementInputDerivation:d});assert.deepEqual(m,expected);
    assert.equal(d.actualRuntimeAcceptance,false);assert.equal(d.productionHistoryFallback,false);
    for(const[n,h]of Object.entries(d.externalSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
    for(const[n,h]of Object.entries(d.unchangedAcceptanceSourcePins))assert.equal(sha(await readFile(path.join(root,n))),h);
    for(const[n,h]of Object.entries(old.avatarConsumptionDerivation.currentBrowserSpecSHA256))assert.equal(sha(await readFile(path.join(root,n))),h);
});

test('actual shipping gate admits V32 and refuses V31 and manifest drift before source reads',()=>fixture(async(source,proposal)=>{
    assert.equal((await gate(assert,readFile,realpath,lstat,path,sha,source,proposal)).version,32);
    assert(!prep.includes('source-fixture'));assert(!prep.includes('recoverCapture'));
    for(const wrong of [oldBytes,Buffer.concat([bytes,Buffer.from('\n')])]){
        await writeFile(proposal,wrong);let reads=0;
        await assert.rejects(()=>gate(assert,async file=>{if(file!==proposal)reads++;return readFile(file);},realpath,lstat,path,sha,source,proposal));assert.equal(reads,0);
    }
}));

test('actual current gate rejects every repaired source when altered missing old or aliased',()=>fixture(async(source,proposal,dir)=>{
    for(const name of [...Object.keys(d.sourceMigrations),...d.addedRows]){
        const file=path.join(dir,name),current=await readFile(file);
        await writeFile(file,Buffer.concat([current,Buffer.from('\n')]));await assert.rejects(()=>gate(assert,readFile,realpath,lstat,path,sha,source,proposal));
        if(Object.hasOwn(d.currentNormalizedSourceSHA256,name)){await writeFile(file,await readCaptureV31Source(name));await assert.rejects(()=>gate(assert,readFile,realpath,lstat,path,sha,source,proposal));}
        await unlink(file);await assert.rejects(()=>gate(assert,readFile,realpath,lstat,path,sha,source,proposal));
        const alias=path.join(dir,'alias');await writeFile(alias,current);await symlink(alias,file);await assert.rejects(()=>gate(assert,readFile,realpath,lstat,path,sha,source,proposal));await unlink(file);await unlink(alias);await writeFile(file,current);
    }
}));

test('bounded exact V31 history preserves original assertion bodies and refuses unknown current bytes',async()=>{
    for(const[n,h]of Object.entries(d.currentNormalizedSourceSHA256)){
        const current=await readFile(path.join(root,n)),before=Buffer.from(await readCaptureV31Source(n));
        assert.equal(sha(current),h);assert.deepEqual(await recoverCaptureV31Input(n,current),before);assert.deepEqual(await recoverCaptureV31Input(n,before),before);
        for(const wrong of [Buffer.concat([current,Buffer.from('\n')]),Buffer.from('unknown')])await assert.rejects(()=>recoverCaptureV31Input(n,wrong));
    }
    for(const[n,h]of Object.entries(d.originalAssertionBodiesSHA256)){
        const before=await readCaptureV31Source(n),current=await readFile(path.join(root,n),'utf8');
        assert.equal(current.slice(current.indexOf("test('")),before.slice(before.indexOf("test('")));assert.equal(sha(Buffer.from(before.slice(before.indexOf("test('")))),h);
    }
    const archive=await readFile(new URL('./fixtures/capture-v31-movement-input-before.json.gz',import.meta.url));
    assert.equal(Object.keys(decodeCaptureV31History(archive).files).length,d.historyInputCount);
    const wrong=Buffer.from(archive);wrong[wrong.length-1]^=1;assert.throws(()=>decodeCaptureV31History(wrong));assert.throws(()=>decodeCaptureV31History(Buffer.alloc(131073)));
});

test('all actual Core actions assertions and deadlines remain byte-identical',async()=>{
    const name='browser-client/tests/integration/real-session.mjs';
    const before=await readCaptureV31Source(name),current=await readFile(path.join(root,name),'utf8');
    const anchor='    browser = await startBrowser();';
    assert.equal(before.split(anchor).length,2);assert.equal(current.split(anchor).length,2);
    assert.equal(current.slice(current.indexOf(anchor)),before.slice(before.indexOf(anchor)));
});
