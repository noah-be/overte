// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { EventEmitter } from 'node:events';
import { attachNativeAvatarProjection } from './native-avatar-stdout-projection.mjs';
import { projectAvatarTail } from '../tools/curate-avatar-samples.mjs';
const producer = readFileSync(new URL('./native-avatar-sample-diagnostics.js', import.meta.url), 'utf8');
const create = vm.runInNewContext(producer + '\ncreateNativeAvatarSampleDiagnostics;');
const field = 'capturedFixtureTargetDistanceMeters';
const marker = 'BROWSER_AVATAR_SAMPLE ';
function fixture({ mode, position = { x: 3, y: 1.8, z: 3 }, self = false, name = 'Native-Lab-Participant' } = {}) {
    let valid = true; const lines = [], calls = [];
    const nativeAvatar = { get position() { calls.push('position'); return position; } };
    const manager = { getAvatarUpdateRate(_id, key) { calls.push(key || 'packet'); return 2; },
        getAvatarSimulationRate() { calls.push('simulation'); return 4; } };
    const diag = create({ mode, now: () => 1000, current: () => valid, authority: () => 'own-authority',
        avatarList: manager, print: line => lines.push(line + '\n') });
    diag.beginBatch(); const row = diag.beginAvatar(); diag.poseSampled(row);
    diag.completed(row, { id: '11111111-2222-3333-4444-555555555555', displayName: name,
        position, private: 'PRIVATE_FIXTURE' }, self, nativeAvatar);
    return { diag, lines, calls, revoke: () => { valid = false; },
        publish: () => { diag.published(); return projectAvatarTail(Buffer.from(lines.join(''))); } };
}
test('actual producer and offline consumer distinguish fresh unchanged old pose from the exact Core target', () => {
    const old = fixture(), fresh = fixture({ position: { x: 4, y: 1.8, z: 2 } });
    const a = old.publish().rows[0], b = fresh.publish().rows[0];
    assert.equal(a[field], Math.SQRT2); assert.equal(b[field], 0);
    assert.equal(a.postPublicationPoseDeltaMeters, 0); assert.equal(b.postPublicationPoseDeltaMeters, 0);
    assert.equal(a.peerSimulationRateHz, 4); assert.equal(a.peerGlobalPositionUpdateRateHz, 2);
    const stripped = row => Object.fromEntries(Object.entries(row).filter(([key]) => key !== field));
    assert.deepEqual(stripped(a), stripped(b)); assert.deepEqual(old.calls, fresh.calls);
});
test('only captured pose contributes; full original native getter/rate calls remain once and unchanged', () => {
    const f = fixture(); const out = f.publish();
    assert.deepEqual(f.calls, ['position', 'packet', 'globalPosition', 'simulation']);
    assert.equal(out.rows[0][field], Math.SQRT2);
    assert(!JSON.stringify(out).includes('PRIVATE')); assert(!JSON.stringify(out).includes('11111111'));
});
test('passive mode computes only captured DTO distance without any native getter or rate probe', () => {
    const f = fixture({ mode: 'passive', position: { x: 4, y: 1.8, z: 2 } });
    const row = f.publish().rows[0]; assert.equal(row[field], 0); assert.deepEqual(f.calls, []);
    for (const key of ['peerSimulationRateHz', 'peerPacketRateHz', 'postPublicationPoseDeltaMeters', 'postPublicationProbeMs']) assert.equal(row[key], null);
});
test('missing, nonfinite, coercible, overflowing and throwing captured positions stay null without prose leakage', () => {
    for (const position of [null, 0, false, '', 4, 'PRIVATE_FIXTURE', [], {}, {x: NaN,y:1.8,z:2}, {x:Infinity,y:1.8,z:2}, {x:'4',y:1.8,z:2},
        {x:1e308,y:1.8,z:2}, { get x() { throw Error('PRIVATE_FIXTURE'); }, y:1.8,z:2 }]) {
        const f = fixture({ mode: 'passive', position }); const out = f.publish();
        assert.equal(out.rows[0][field], null); assert(!JSON.stringify(out).includes('PRIVATE'));
    }
});
test('self and other avatars are never assigned the fixture target', () => {
    const self = fixture({ self: true }); assert.equal(self.publish().rows[0][field], null);
    const other = fixture({ name: 'Other participant' }); assert.deepEqual(other.publish().rows, []);
});
test('revoked or stopped ownership cannot emit a target diagnostic or perform later native probes', () => {
    for (const action of ['revoke', 'stop']) {
        const f = fixture(); if (action === 'revoke') f.revoke(); else f.diag.stop();
        assert.deepEqual(f.publish().rows, []); assert.deepEqual(f.calls, []);
    }
    const f = fixture({ mode: 'passive' });
    const position = { get x() { f.revoke(); return 4; }, y: 1.8, z: 2 };
    f.diag.beginBatch(); const row = f.diag.beginAvatar(); f.diag.poseSampled(row);
    f.diag.completed(row,{displayName:'Native-Lab-Participant',position},false,{});
    assert.deepEqual(f.publish().rows, []); assert.deepEqual(f.calls, []);
});
test('actual streaming and offline consumers agree on the exact new scalar and original per-child cap', () => {
    const f = fixture(); f.publish(); const child = new EventEmitter(); child.stdout = new EventEmitter(); const rows = [];
    attachNativeAvatarProjection(child,{enabled:true,publicPlace:false,emit:line=>rows.push(JSON.parse(line.slice(marker.length)))});
    for (const byte of Buffer.from(f.lines[0])) child.stdout.emit('data',Buffer.from([byte]));
    assert.deepEqual(rows,projectAvatarTail(Buffer.from(f.lines[0])).rows);
    child.stdout.emit('data',Buffer.from(f.lines[0].repeat(512)));
    assert.equal(rows.length,512); assert.equal(child.stdout.listenerCount('data'),0);
});
test('strict new schema rejects old missing scalar, unknown fields, invalid numbers and nonfixture nonnull values', () => {
    const row = fixture().publish().rows[0];
    const old = {...row}; delete old[field];
    const bad = [old, {...row,[field]:'PRIVATE_FIXTURE'}, {...row,[field]:-1}, {...row,[field]:300001},
        {...row,role:'self'}, {...row,privatePose:{x:4}}];
    for (const value of bad) assert.equal(projectAvatarTail(Buffer.from(marker+JSON.stringify(value)+'\n')).rows.length,0);
    const overflow = JSON.stringify({...row,[field]:0}).replace('\"'+field+'\":0','\"'+field+'\":1e400');
    assert.equal(projectAvatarTail(Buffer.from(marker+overflow+'\n')).rows.length,0);
    const self = {...row,role:'self',[field]:null};
    assert.equal(projectAvatarTail(Buffer.from(marker+JSON.stringify(self)+'\n')).rows.length,1);
    for (const value of [null,0,300000]) assert.equal(projectAvatarTail(Buffer.from(marker+JSON.stringify({...row,[field]:value})+'\n')).rows.length,1);
});
test('original Core target, movement assertions and callbacks remain the source of diagnostic scope', () => {
    const core = readFileSync(new URL('../tests/integration/real-session.mjs',import.meta.url),'utf8');
    assert(core.includes('const peerTarget = {x:4,y:1.8,z:2};'));
    assert(core.includes("'Browser receives second native participant movement'"));
    for (const token of ['setInterval(', 'setTimeout(', 'sendAvatarDataPacket(', 'forceUpdateStats(', 'MyAvatar.position =']) assert(!producer.includes(token));
});

test('the immediately previous sampler pin refuses current manager-composed plain/full/passive author bytes', async () => {
    const source = readFileSync(new URL('../lab/native-participant.js',import.meta.url));
    const diagnostics = readFileSync(new URL('./native-avatar-sample-diagnostics.js',import.meta.url));
    const text = readFileSync(new URL('../tests/integration/tablet-ptt-native-peer.mjs',import.meta.url),'utf8');
    const current = await import('../tests/integration/tablet-ptt-native-peer.mjs');
    const anchor = "export const AUTHOR_DIAGNOSTICS_SHA256='"+current.AUTHOR_DIAGNOSTICS_SHA256+"';";
    assert.equal(text.split(anchor).length-1,1);
    const oldText = text.replace(anchor,"export const AUTHOR_DIAGNOSTICS_SHA256='1c386213ac2ddb89ae313db55a6df4df2ecd0a38a1d6be93ef545384bc4299fd';");
    const previous = await import('data:text/javascript;base64,'+Buffer.from(oldText).toString('base64'));
    for (const mode of ['plain','full','passive']) {
        const served = mode==='plain' ? source : Buffer.concat([Buffer.from('var BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS = true;\nvar BROWSER_LAB_AVATAR_SAMPLE_DIAGNOSTICS_MODE = '+JSON.stringify(mode)+';\n'),diagnostics,Buffer.from('\n'),source]);
        assert.equal(current.admitServedAuthor(served,{source,diagnostics}).registration,'current-'+mode);
        assert.throws(()=>previous.admitServedAuthor(served,{source,diagnostics}));
    }
});
