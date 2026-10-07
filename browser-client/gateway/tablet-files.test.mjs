// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,writeFile,readFile,rename,symlink,readdir,appendFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {Readable} from 'node:stream';
import {createVisitorFiles,visitorFilename,visitorDownloadHeaders} from './tablet-files.mjs';
async function fixture(action){const directory=await mkdtemp(join(tmpdir(),'visitor-files-'));const files=await createVisitorFiles(directory);try{await action(files,directory);}finally{await files.close();await rm(directory,{recursive:true,force:true});}}
async function bytes(stream){const chunks=[];for await(const chunk of stream)chunks.push(chunk);return Buffer.concat(chunks);}
test('visitor workspace transfers actual bytes and exported files carry inert download headers',async()=>fixture(async(files)=>{
    const data=Buffer.from('{"Entities":[]}');assert.deepEqual(await files.upload('Überte scene.json',Readable.from([data])),{name:'Überte scene.json',size:data.length});
    assert.deepEqual(await files.list(),[{name:'Überte scene.json',size:data.length}]);
    const download=await files.download('Überte scene.json');assert.deepEqual(await bytes(download.stream),data);
    assert.equal(download.headers['x-content-type-options'],'nosniff');assert.match(download.headers['content-security-policy'],/^sandbox/);assert.match(download.headers['content-disposition'],/attachment/);
    await files.delete('Überte scene.json');assert.deepEqual(await files.list(),[]);
}));
test('descriptor-bound visitor access cannot follow a replaced directory into gateway-host files',async()=>fixture(async(files,directory)=>{
    await files.upload('safe.txt',Readable.from(['visitor data']));const outside=join(directory,'host-private');await mkdir(outside);await writeFile(join(outside,'safe.txt'),'host private data');
    await rename(join(directory,'files'),join(directory,'moved-files'));await symlink(outside,join(directory,'files'));
    assert.equal((await bytes((await files.download('safe.txt')).stream)).toString(),'visitor data');
    await files.upload('new.txt',Readable.from(['new visitor data']));assert.equal(await readFile(join(directory,'moved-files/new.txt'),'utf8'),'new visitor data');assert.deepEqual(await readdir(outside),['safe.txt']);
}));
test('native-created file symlinks never disclose host data and atomic upload replaces them safely',async()=>fixture(async(files,directory)=>{
    const secret=join(directory,'private.txt');await writeFile(secret,'operator secret');await symlink(secret,join(directory,'files/link.txt'));
    await assert.rejects(files.download('link.txt'));assert.deepEqual(await files.list(),[]);
    await files.upload('link.txt',Readable.from(['visitor replacement']));assert.equal(await readFile(secret,'utf8'),'operator secret');assert.equal((await bytes((await files.download('link.txt')).stream)).toString(),'visitor replacement');
}));
test('download stays bounded when native code appends after file admission',async()=>fixture(async(files,directory)=>{
    await files.upload('bounded.txt',Readable.from(['123']));const download=await files.download('bounded.txt');await appendFile(join(directory,'files/bounded.txt'),'456789');
    assert.equal(download.size,3);assert.equal((await bytes(download.stream)).toString(),'123');
}));
test('oversized streams remove partial files; ended sessions cannot reopen descriptors',async()=>fixture(async(files,directory)=>{
    const chunk=Buffer.alloc(1024*1024);async function* source(){for(let n=0;n<65;n++)yield chunk;}
    await assert.rejects(files.upload('too-large.bin',Readable.from(source())),/limit/);assert.deepEqual(await readdir(join(directory,'files')),[]);
    const first=files.close();assert.equal(files.close(),first);await first;await assert.rejects(files.list(),/ended/);
}));
test('file names and HTTP dispositions cannot inject paths, hidden files or headers',()=>{
    for(const name of ['../secret','.ssh','a/b','a\\b','a\nX-Header: secret','a\u0000b',''])assert.throws(()=>visitorFilename(name));
    assert.equal(visitorFilename('Avatar Überte.fst'),'Avatar Überte.fst');assert.throws(()=>visitorDownloadHeaders('large.bin',Infinity));
});
test('live download streams count toward the per-session descriptor limit and close releases every owned handle',async()=>fixture(async(files)=>{
    await files.upload('held.bin',Readable.from(['visitor data']));const streams=[];
    for(let index=0;index<16;index++)streams.push((await files.download('held.bin')).stream);
    await assert.rejects(files.download('held.bin'),/Too many/);
    await files.close();assert(streams.every(stream=>stream.closed));
}));
