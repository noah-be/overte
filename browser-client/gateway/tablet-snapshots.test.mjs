// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {readFile,mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';import {pathToFileURL} from 'node:url';import vm from 'node:vm';
import {patchSnapshotSource,prepareSnapshotOverride} from './tablet-snapshots.mjs';
test('trusted Snapshot override preserves the actual installed app and delegates only local world capture',async()=>{
    const source=await readFile(new URL('../../scripts/system/snapshot.js',import.meta.url),'utf8'),channel='private-channel';
    const patched=patchSnapshotSource(source,channel);
    assert(!patched.includes('Window.takeSnapshot(false, includeAnimated, 1.91);'));assert(patched.includes('Messages.sendLocalMessage("private-channel"'));
    for(const original of ['function stillSnapshotTaken(','function processingGifStarted(','function processingGifCompleted('])assert(patched.includes(original));
    const callbacks=[],timers=[];const listener=patched.slice(patched.indexOf('function browserSnapshotResult('),patched.indexOf('Messages.subscribe("private-channel")'));
    const context=vm.createContext({Reticle:{},HMD:{openTablet:()=>{}},Menu:{setIsOptionChecked:()=>{}},ui:{sendMessage:()=>{}},reticleVisible:true,resetOverlays:false,setTakePhotoControllerMappingStatus:()=>{},stillSnapshotTaken:(...args)=>callbacks.push(['still',...args]),processingGifStarted:path=>callbacks.push(['started',path]),processingGifCompleted:path=>callbacks.push(['completed',path]),Script:{setTimeout:fn=>timers.push(fn)}});
    vm.runInContext(listener,context);context.browserSnapshotResult(channel,JSON.stringify({kind:'result',stillPath:'/private/files/still.png'}),'',true);assert.deepEqual(callbacks,[['still','/private/files/still.png',false]]);
    context.browserSnapshotResult(channel,JSON.stringify({kind:'result',stillPath:'/private/files/still.png',gifPath:'/private/files/animated.gif'}),'',true);assert.deepEqual(callbacks.at(-1),['started','/private/files/still.png']);timers[0]();assert.deepEqual(callbacks.at(-1),['completed','/private/files/animated.gif']);
    const count=callbacks.length;context.browserSnapshotResult('other',JSON.stringify({kind:'result',stillPath:'/outside.png'}),'',true);context.browserSnapshotResult(channel,JSON.stringify({kind:'result',stillPath:'/outside.png'}),'',false);assert.equal(callbacks.length,count);
    assert.throws(()=>patchSnapshotSource(source.replace('Window.takeSnapshot(false, includeAnimated, 1.91);','otherCall();'),channel),/cannot safely delegate/);
    const root=await mkdtemp(join(tmpdir(),'overte-snapshot-'));try{const installed=join(root,'installed'),session=join(root,'session');await mkdir(join(installed,'system'),{recursive:true});await mkdir(session);await writeFile(join(installed,'system/snapshot.js'),source);
        const override=await prepareSnapshotOverride(session,{defaultScriptsURL:pathToFileURL(join(installed,'defaultScripts.js')).href,channel});assert.equal(override.target,join(installed,'system/snapshot.js'));assert.equal(await readFile(override.source,'utf8'),patched);assert.equal(await readFile(override.target,'utf8'),source,'Installed operator script is unchanged');
    }finally{await rm(root,{recursive:true,force:true});}
});
