// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,symlink,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {sandboxCommand} from './worker-sandbox.mjs';

async function fixture(run) {
    const directory=await mkdtemp(path.join(tmpdir(),'overte-create-boundary-'));
    try {
        const profile=path.join(directory,'profile'),installed=path.join(directory,'installed');
        const source=path.join(profile,'browser-create-properties.html');
        const target=path.join(installed,'scripts/system/create/entityProperties/html/entityProperties.html');
        await mkdir(profile);await mkdir(path.dirname(target),{recursive:true});
        await writeFile(source,'reviewed generated responsive HTML',{mode:0o600});
        await writeFile(target,'installed original HTML');
        const config={directory:profile,executable:process.execPath,env:{},roots:[installed]};
        await run({directory,profile,installed,source,target,config});
    } finally {await rm(directory,{recursive:true,force:true});}
}

test('Create binds only the exact generated owned HTML read-only to its exact installed target',async()=>fixture(async({source,target,config})=>{
    const launch=await sandboxCommand({...config,readOnlyOverrides:[{source,target}]});
    const index=launch.args.indexOf(source);
    assert.equal(launch.args[index-1],'--ro-bind');assert.equal(launch.args[index+1],target);
    assert.equal(await readFile(target,'utf8'),'installed original HTML');
}));

test('Create rejects wrong basename, nested or sibling profile, wrong installed suffix and outside roots',async()=>fixture(async({directory,profile,source,target,config})=>{
    const sibling=path.join(directory,'sibling');await mkdir(sibling);
    const nested=path.join(profile,'nested');await mkdir(nested);
    for(const candidate of [path.join(profile,'browser-create.html'),path.join(sibling,path.basename(source)),path.join(nested,path.basename(source))]) {
        await writeFile(candidate,'unapproved HTML');
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source:candidate,target}]}),/Only reviewed session/);
    }
    for(const candidate of [target.replace('entityProperties.html','other.html'),target.replace('/html/','/other/'),path.join(directory,'outside/scripts/system/create/entityProperties/html/entityProperties.html')]) {
        await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source,target:candidate}]}),/Only reviewed session/);
    }
}));

test('Create rejects source and target file symlinks and nonregular files',async()=>fixture(async({profile,source,target,config})=>{
    const original=path.join(profile,'owned-original.html');await writeFile(original,'owned');
    await rm(source);await symlink(original,source);
    await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source,target}]}),/regular trusted script files/);
    await rm(source);await writeFile(source,'generated');
    await rm(target);await symlink(original,target);
    await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source,target}]}),/regular trusted script files/);
    await rm(target);await mkdir(target);
    await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source,target}]}),/regular trusted script files/);
}));

test('Create rejects source-parent and installed-parent symlink aliases',async()=>fixture(async({directory,profile,source,target,config})=>{
    const profileAlias=path.join(directory,'profile-alias');await symlink(profile,profileAlias);
    await assert.rejects(sandboxCommand({...config,directory:profileAlias,readOnlyOverrides:[{source:path.join(profileAlias,path.basename(source)),target}]}),/canonical owned and installed script paths/);
    const html=path.dirname(target),actual=path.join(directory,'actual-html');await mkdir(actual);
    await writeFile(path.join(actual,path.basename(target)),'outside installed root');
    await rm(html,{recursive:true});await symlink(actual,html);
    await assert.rejects(sandboxCommand({...config,readOnlyOverrides:[{source,target}]}),/canonical owned and installed script paths/);
}));
