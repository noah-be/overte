// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,open,readdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {writeAtomicFixtureCommand} from './integration/atomic-fixture-command.mjs';

test('an existing HTTP-style reader retains complete old JSON while a new reader gets the complete command',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-command-contract-'));
    const filename=path.join(directory,'command.json'),old={sequence:1,action:'arm'},next={sequence:2,action:'cleanup'};
    let reader;
    try {
        await writeFile(filename,JSON.stringify(old)+'\n');reader=await open(filename,'r');
        await writeAtomicFixtureCommand(filename,next);
        assert.deepEqual(JSON.parse(await reader.readFile('utf8')),old);
        assert.deepEqual(JSON.parse(await readFile(filename,'utf8')),next);
        assert.deepEqual(await readdir(directory),['command.json']);
        // The previous in-place write changes the inode held by a reader.
        await reader.close();reader=await open(filename,'r');
        await writeFile(filename,JSON.stringify(old)+'\n');
        assert.notDeepEqual(JSON.parse(await reader.readFile('utf8')),next);
    } finally {await reader?.close();await rm(directory,{recursive:true,force:true});}
});

test('continuous concurrent readers never observe partial JSON during actual fixture publication',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-command-concurrent-')),filename=path.join(directory,'command.json');
    try {
        await writeAtomicFixtureCommand(filename,{sequence:0,payload:'a'.repeat(16000)});
        const read=async()=>{for(let i=0;i<100;i++){const row=JSON.parse(await readFile(filename,'utf8'));assert(Number.isSafeInteger(row.sequence));assert.equal(row.payload.length,16000);}};
        await Promise.all([read(),read(),(async()=>{for(let sequence=1;sequence<=40;sequence++)await writeAtomicFixtureCommand(filename,{sequence,payload:'a'.repeat(16000)});})()]);
        assert.deepEqual(await readdir(directory),['command.json']);
    } finally {await rm(directory,{recursive:true,force:true});}
});

test('oversized or invalid commands refuse before replacing a valid command',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-command-bound-')),filename=path.join(directory,'command.json');
    try {
        await writeAtomicFixtureCommand(filename,{sequence:0});
        for(const value of [null,[],{payload:'x'.repeat(65536)}])await assert.rejects(writeAtomicFixtureCommand(filename,value));
        assert.deepEqual(JSON.parse(await readFile(filename,'utf8')),{sequence:0});assert.deepEqual(await readdir(directory),['command.json']);
    } finally {await rm(directory,{recursive:true,force:true});}
});
