// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { EventEmitter } from 'node:events';
import { attachNativeAvatarProjection } from './native-avatar-stdout-projection.mjs';
import { projectAvatarTail } from '../tools/curate-avatar-samples.mjs';
const source = readFileSync(new URL('./native-avatar-sample-diagnostics.js', import.meta.url), 'utf8');
const create = vm.runInNewContext(source + '\ncreateNativeAvatarSampleDiagnostics;');
const id = '{11111111-2222-3333-4444-555555555555}';
function fixture({mode, simulation = 3, global = 2, local = 0} = {}) {
    let valid = true; const calls = [], lines = [];
    const avatarList = {getAvatarUpdateRate(peer, name) {calls.push(['update', peer, name]); return name ? 12 : 20;},
        getAvatarSimulationRate(peer, name) {calls.push(['simulation', peer, name]); return simulation;}};
    const avatar = {getDataRate(name) {calls.push(['author', name]); return name === 'globalPositionOutbound' ? global : local;}};
    const diag = create({mode, current: () => valid, now: () => 1000, avatarList, avatar,
        print: value => lines.push(value + '\n')});
    function published() {diag.beginBatch(); const row = diag.beginAvatar(); diag.poseSampled(row);
        const position = {x:0,y:1,z:0}; diag.completed(row, {id,displayName:'Native-Lab-Participant',position},false,{position});
        assert.equal(calls.length,0); diag.published();}
    return {calls,lines,avatarList,avatar,diag,published,revoke:()=>{valid=false;},rows:()=>lines.map(x=>JSON.parse(x.slice(22)))};
}
test('actual producer, streaming projector and offline tail consumer preserve three finite readbacks without private UUID', () => {
    const f = fixture(); f.published(); f.diag.authorObservation();
    assert.deepEqual(f.calls,[['update',id,''],['update',id,'globalPosition'],['simulation',id,''],
        ['author','globalPositionOutbound'],['author','localPositionOutbound']]);
    const result = projectAvatarTail(Buffer.from(f.lines.join('')));
    assert.equal(result.rejectedMarkerLines,0);assert.equal(result.rows.length,2);
    assert.equal(result.rows[0].peerSimulationRateHz,3); assert.equal(result.rows[1].authorGlobalPositionOutboundKbps,2);
    assert.equal(result.rows[1].authorLocalPositionOutboundKbps,0);assert(!JSON.stringify(result).includes(id));
    assert.equal(result.rows[1].statsFreshness,'not-forced-or-established');
});
test('missing capabilities stay null; no wrapper simulation or other data keys are probed', () => {
    const f = fixture(); delete f.avatarList.getAvatarSimulationRate;delete f.avatar.getDataRate;
    f.published(); f.diag.authorObservation(); const rows=projectAvatarTail(Buffer.from(f.lines.join(''))).rows;
    assert.equal(rows[0].peerSimulationRateHz,null);assert.equal(rows[1].authorGlobalPositionOutboundKbps,null);
    assert.equal(rows[1].authorLocalPositionOutboundKbps,null);assert.equal(f.calls.length,2);
});
test('exceptions, negative, overflow, NaN, strings remain null; actual native zero is retained', () => {
    for(const value of [-1,300001,NaN,'2',null,0,300000]) {
        const f=fixture({simulation:value,global:value,local:value});f.published();f.diag.authorObservation();
        const rows=projectAvatarTail(Buffer.from(f.lines.join(''))).rows, expected=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=300000?value:null;
        assert.equal(rows[0].peerSimulationRateHz,expected);assert.equal(rows[1].authorGlobalPositionOutboundKbps,expected);
    }
    const absent=fixture();absent.avatarList.getAvatarSimulationRate=()=>undefined;absent.avatar.getDataRate=()=>undefined;absent.published();absent.diag.authorObservation();assert.equal(projectAvatarTail(Buffer.from(absent.lines.join(''))).rows[0].peerSimulationRateHz,null);
    const f=fixture();f.avatarList.getAvatarSimulationRate=()=>{throw Error('PRIVATE_UUID_SECRET');};f.avatar.getDataRate=()=>{throw Error('PRIVATE_UUID_SECRET');};
    f.published();f.diag.authorObservation();const result=projectAvatarTail(Buffer.from(f.lines.join('')));
    assert.equal(result.rows[0].peerSimulationRateHz,null);assert.equal(result.rows[1].authorGlobalPositionOutboundKbps,null);
    assert(!JSON.stringify(result).includes('PRIVATE'));
});
test('full readback revocation prevents subsequent native rate calls and emission', () => {
    const f=fixture();f.avatarList.getAvatarSimulationRate=()=>{f.revoke();return 3;};f.published();
    assert.deepEqual(f.lines,[]);const calls=f.calls.length;f.diag.authorObservation();assert.equal(f.calls.length,calls);
    const a=fixture();a.avatar.getDataRate=name=>{a.calls.push(['author',name]);a.revoke();return 1;};a.diag.authorObservation();
    assert.deepEqual(a.calls,[['author','globalPositionOutbound']]);assert.deepEqual(a.lines,[]);
});
test('passive mode and stopped owner never read new native capabilities', () => {
    const f=fixture({mode:'passive'});f.published();f.diag.authorObservation();assert.deepEqual(f.calls,[]);
    const rows=projectAvatarTail(Buffer.from(f.lines.join(''))).rows;assert.equal(rows[0].peerSimulationRateHz,null);
    assert.equal(rows[1].authorGlobalPositionOutboundKbps,null);f.diag.stop();f.diag.authorObservation();assert.equal(f.calls.length,0);
});
test('private non-UUID peer never invokes simulation manager; author is independent of private peer identity', () => {
    const f=fixture();f.diag.beginBatch();const row=f.diag.beginAvatar();f.diag.poseSampled(row);const position={x:0,y:0,z:0};
    f.diag.completed(row,{id:'PRIVATE',displayName:'Native-Lab-Participant',position},false,{position});f.diag.published();
    assert.deepEqual(f.calls,[]);assert.equal(projectAvatarTail(Buffer.from(f.lines.join(''))).rows[0].peerSimulationRateHz,null);
});
test('new strict numeric fields reject missing/unknown schemas and preserve original per-child 512-row budget', () => {
    const f=fixture();f.published();const row=JSON.parse(f.lines[0].slice(22));
    for(const value of ['PRIVATE',-1,300001])assert.equal(projectAvatarTail(Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify({...row,peerSimulationRateHz:value})+'\n')).rows.length,0);
    const missing={...row};delete missing.peerSimulationRateHz;
    assert.equal(projectAvatarTail(Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify(missing)+'\n')).rows.length,0);
    assert.equal(projectAvatarTail(Buffer.from('BROWSER_AVATAR_SAMPLE '+JSON.stringify({...row,uuid:id})+'\n')).rows.length,0);
    const child=new EventEmitter();child.stdout=new EventEmitter();let count=0;attachNativeAvatarProjection(child,{enabled:true,publicPlace:false,emit:()=>count++});
    child.stdout.emit('data',Buffer.from(f.lines[0].repeat(600)));assert.equal(count,512);assert.equal(child.stdout.listenerCount('data'),0);
});
test('author config retains existing callbacks and no sampler sends, mutates avatar or forces Stats', () => {
    const participant=readFileSync(new URL('../lab/native-participant.js',import.meta.url),'utf8');
    assert(participant.includes('stats:typeof Stats'));assert(participant.includes('avatar:MyAvatar,'));
    for(const text of ['setInterval(', 'setTimeout(', 'sendAvatarDataPacket(', 'forceUpdateStats(', 'MyAvatar.position ='])assert(!source.includes(text));
});
test('capability getters that revoke authority cannot invoke the captured function or a later probe', () => {
    const f=fixture();let invoked=0;Object.defineProperty(f.avatarList,'getAvatarSimulationRate',{get(){f.revoke();return()=>{invoked++;return 1;};}});
    f.published();assert.equal(invoked,0);assert.deepEqual(f.lines,[]);
    const a=fixture();Object.defineProperty(a.avatar,'getDataRate',{get(){a.revoke();return()=>{invoked++;return 1;};}});
    a.diag.authorObservation();assert.equal(invoked,0);assert.deepEqual(a.lines,[]);
});
test('captured native methods preserve their original QObject receiver and exact one capability lookup', () => {
    const f=fixture();let lookups=0;Object.defineProperty(f.avatarList,'getAvatarSimulationRate',{get(){lookups++;return function(peer,key){assert.equal(this,f.avatarList);assert.equal(peer,id);assert.equal(key,'');return 4;};}});
    f.avatar.getDataRate=function(key){assert.equal(this,f.avatar);return key==='globalPositionOutbound'?7:0;};
    f.published();f.diag.authorObservation();const rows=projectAvatarTail(Buffer.from(f.lines.join(''))).rows;
    assert.equal(lookups,1);assert.equal(rows[0].peerSimulationRateHz,4);assert.equal(rows[1].authorGlobalPositionOutboundKbps,7);
});
