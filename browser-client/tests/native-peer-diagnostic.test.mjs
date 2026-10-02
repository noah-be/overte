// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { mkdtemp, writeFile, symlink, mkdir, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { captureNativePeerSnapshot, projectNativePeerLog, readNativePeerDiagnostic } from './integration/native-peer-diagnostic.mjs';
const target = {x:4,y:1.8,z:2};
const fixtureName = 'Native-Lab-Participant';
const line = record => 'unpublished private prefix BROWSER_LAB '+JSON.stringify(record)+'\n';
const operation = {sequence:42,target,now:1000};
const applied = {kind:'command-applied',at:800,data:{sequence:42,position:target,privateName:'NEVER-PUBLISH'}};
const observation = {kind:'observation',at:900,data:{position:target,selfId:'PRIVATE-ID',avatars:[{displayName:'PRIVATE-NAME'}]}};
function browserCapture(snapshot, at=600, now=850) {
    const snapshotTimes=new WeakMap(); if(snapshot && at!==null)snapshotTimes.set(snapshot,at);
    const audio={snapshots:snapshot?[snapshot]:[],snapshotTimes};
    const context=vm.createContext({window:{__labAudio:audio},performance:{now:()=>now},operation:{fixtureName,target}});
    return {result:vm.runInContext(`(${captureNativePeerSnapshot.toString()})(operation)`,context),audio};
}
test('one captured snapshot retains original avatars and identity timing, excluding self from projection',()=>{
    const avatars=[{id:'OWN-ID',displayName:'PRIVATE-OWN-NAME',position:{x:0,y:0,z:0}},
        {id:'PEER-ID',displayName:fixtureName,position:target}];
    const snapshot={type:'avatars',selfId:'OWN-ID',avatars};
    const {result,audio}=browserCapture(snapshot);
    assert.equal(result.avatars,avatars);assert.equal(result.diagnostic.snapshotAgeMs,250);
    assert.equal(result.diagnostic.peerCount,1);assert.equal(result.diagnostic.fixtureNameMatchCount,1);
    assert.equal(result.diagnostic.peers[0].targetDistance,0);
    audio.snapshots.push({type:'avatars',avatars:[]});
    assert.equal(result.avatars,avatars,'A later arrival cannot replace the original assertion snapshot');
    const json=JSON.stringify(result.diagnostic);for(const privateText of ['OWN-ID','PEER-ID',fixtureName,'PRIVATE-OWN-NAME'])assert(!json.includes(privateText));
    assert.equal(snapshot.arrivedAt,undefined,'Timing stays in WeakMap, never the protocol record');
});
test('missing timing, stale position and name mismatch remain distinguishable with bounded peer metadata',()=>{
    const avatars=Array.from({length:40},(_,index)=>({id:String(index),displayName:index===39?fixtureName:'PRIVATE',position:{x:3,y:1.8,z:3}}));
    const result=browserCapture({type:'avatars',selfId:'self',avatars},null).result;
    assert.equal(result.diagnostic.snapshotAgeMs,null);assert.equal(result.diagnostic.fixtureNameMatchCount,1);
    assert.equal(result.diagnostic.peerCount,40);assert.equal(result.diagnostic.peers.length,16);
    assert.equal(result.diagnostic.peerProjectionTruncated,true);
    assert.equal(result.diagnostic.peers[0].fixtureNameMatch,false);
    assert.equal(result.diagnostic.peers[0].targetDistance,Math.SQRT2);
});
test('no snapshot and nonfinite positions cannot invent a successful movement observation',()=>{
    assert.equal(browserCapture().result.diagnostic.snapshotPresent,false);
    const result=browserCapture({type:'avatars',selfId:'own',avatars:[{id:'peer',displayName:fixtureName,position:{x:Infinity,y:0,z:0}}]}).result;
    assert.equal(result.diagnostic.peers[0].targetDistance,null);
});
test('exact command sequence and independent later observation are projected without raw identities',()=>{
    const result=projectNativePeerLog(line(applied)+line(observation),operation);
    assert.equal(result.commandSequenceMatched,true);assert.equal(result.commandAppliedAtMs,800);
    assert.equal(result.commandAppliedAgeMs,200);assert.equal(result.observationAfterCommand,true);
    assert.equal(result.observationAgeMs,100);assert.equal(result.commandTargetDistance,0);
    assert.equal(result.observationTargetDistance,0);
    assert(!JSON.stringify(result).includes('PRIVATE'));assert(!('sequence' in result));
});
test('other-command success cannot be reported as the requested native operation',()=>{
    const result=projectNativePeerLog(line({...applied,data:{...applied.data,sequence:43}})+line(observation),operation);
    assert.equal(result.commandSequenceMatched,false);assert.equal(result.commandAppliedAtMs,null);
    assert.equal(result.commandTargetDistance,null);assert.equal(result.observationAfterCommand,null);
});
test('malformed records and future/nonfinite timestamps preserve explicit uncertainty',()=>{
    const result=projectNativePeerLog('BROWSER_LAB {bad}\n'+line({...applied,at:1200})+line({...observation,at:-1}),operation);
    assert.equal(result.commandAppliedAgeMs,null);assert.equal(result.observationAtMs,null);
    assert.equal(result.observationAfterCommand,null);
});
test('file reader rejects symlink and non-regular paths without exposing errors or paths',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-peer-tail-'));
    try {
        const file=path.join(directory,'native.log');await writeFile(file,line(applied));
        const link=path.join(directory,'link');await symlink(file,link);
        assert.deepEqual(await readNativePeerDiagnostic(link,operation),{status:'symlink-refused'});
        assert.deepEqual(await readNativePeerDiagnostic(directory,operation),{status:'not-regular'});
        assert.deepEqual(await readNativePeerDiagnostic(path.join(directory,'absent'),operation),{status:'missing'});
    } finally {await rm(directory,{recursive:true,force:true});}
});
test('one MiB bounded tail discards partial older record and still finds exact late command',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-peer-tail-'));
    try {
        const file=path.join(directory,'native.log');await writeFile(file,'x'.repeat(2*1024*1024)+'\n'+line(applied)+line(observation));
        const result=await readNativePeerDiagnostic(file,operation);
        assert.equal(result.bytesRead,1024*1024);assert.equal(result.tailTruncated,true);
        assert.equal(result.commandSequenceMatched,true);assert.equal(result.observationTargetDistance,0);
    } finally {await rm(directory,{recursive:true,force:true});}
});
test('production harness waits unchanged 2800 ms and asserts captured avatars after one diagnostic read',async()=>{
    const source=await readFile(new URL('./integration/real-session.mjs',import.meta.url),'utf8');
    assert(source.includes('await delay(2800);\n    return sequence;'));
    const section=source.slice(source.indexOf('const peerTarget ='),source.indexOf("await checkpoint('native-movement-synchronized')"));
    assert.equal((section.match(/page\.evaluate/g)||[]).length,1);
    assert.equal((section.match(/readNativePeerDiagnostic/g)||[]).length,1);
    assert(section.indexOf('const avatars = capturedPeer.avatars;')<section.indexOf('readNativePeerDiagnostic'));
    assert(section.includes("assert(avatars?.some(avatar=>avatar.displayName==='Native-Lab-Participant' && Math.abs(avatar.position.x-4)<.5),\n        'Browser receives second native participant movement');"));
});
