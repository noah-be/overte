// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { attachNativeAvatarProjection } from './native-avatar-stdout-projection.mjs';
const MARKER = 'BROWSER_AVATAR_SAMPLE ';
const sample = () => ({ version: 1, kind: 'sample', at: 1790899200123, sequence: 1,
    role: 'fixture-peer', batchMs: 500, publishedPoseAgeMs: 20, avatarBuildMs: 5,
    jointNamesMs: null, jointRotationsMs: 0, jointTranslationsMs: 1,
    postPublicationPoseDeltaMeters: 0.1, postPublicationProbeMs: 2,
    peerPacketRateHz: 30, peerGlobalPositionUpdateRateHz: 15, peerSimulationRateHz: null,
    capturedFixtureTargetDistanceMeters: null,
    interstitialState: 'unknown', interstitialSignalAgeMs: null });
const author = () => ({version: 1, kind: 'author-transmission', at: 1790899200123,
    interstitialState: 'inactive', interstitialSignalAgeMs: 300000,
    cachedMyAvatarSendRateHz: null, cachedAvatarMixerOutPps: 50,
    authorGlobalPositionOutboundKbps: null, authorLocalPositionOutboundKbps: null,
    statsFreshness: 'not-forced-or-established'});
function fixture(options = {}) {
    const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter();
    const rows = [];
    attachNativeAvatarProjection(child, { enabled: true, publicPlace: false, emit: row => rows.push(row), ...options });
    return { child, rows, feed: value => child.stdout.emit('data', Buffer.isBuffer(value) ? value : Buffer.from(value)) };
}
const line = (value = sample()) => MARKER + JSON.stringify(value) + '\n';
const decoded = rows => rows.map(row => { assert.ok(row.startsWith(MARKER)); return JSON.parse(row.slice(MARKER.length)); });

test('realistic decorated, CRLF, QString quoted and arbitrarily split native messages project canonical rows', () => {
    const f = fixture();
    const input = '[10/02 00:00:00][INFO][script] ' + line() + '[script] ' + JSON.stringify(line(author()).trim()) + '\r\n';
    for (const byte of Buffer.from(input)) f.feed(Buffer.from([byte]));
    assert.deepEqual(decoded(f.rows), [sample(), author()]);
});
test('private decorators and unmarked native output are never reflected', () => {
    const f = fixture(); const privateText = 'https://private.invalid/person?token=secret';
    f.feed(privateText + '\n' + privateText + ' ' + line());
    assert.equal(f.rows.length, 1); assert.ok(!f.rows[0].includes(privateText));
    assert.deepEqual(decoded(f.rows), [sample()]);
});
test('unknown schema fields, enums, primitive payloads and malformed or trailing JSON fail closed', () => {
    const f = fixture();
    for (const value of [null, [], true, { ...sample(), participantId: 'private' },
        { ...sample(), role: 'actual-private-name' }, { ...sample(), kind: 'private' },
        { ...sample(), interstitialState: 'guessed' }, { ...author(), statsFreshness: 'fresh' },
        { ...sample(), version: 2 }, { ...sample(), jointNamesMs: 'private-error' }]) f.feed(line(value));
    f.feed(MARKER + '{broken}\n'); f.feed(line().trim() + ' PRIVATE\n');
    f.feed(MARKER + JSON.stringify({ ...sample(), extra: MARKER }) + '\n');
    assert.deepEqual(f.rows, []);
});
test('exact bounded native numbers and nulls accepted; overflow, absent, wrong-type and invalid timestamps rejected', () => {
    const f = fixture();
    for (const [key, values] of [['batchMs', [-1, 300001, '0']],
        ['sequence', [0, 513, 1.5, null]], ['at', [-1, Number.MAX_SAFE_INTEGER + 1, 1.5, null]]]) {
        for (const value of values) f.feed(line({ ...sample(), [key]: value }));
    }
    f.feed(line().replace('"batchMs":500', '"batchMs":1e309'));
    const missing = sample(); delete missing.jointRotationsMs; f.feed(line(missing));
    f.feed(line({ ...sample(), batchMs: 300000, at: Number.MAX_SAFE_INTEGER, sequence: 512 }));
    assert.equal(f.rows.length, 1);
});
test('UTF8 failure and oversized lines discarded through newline, then recover without reflecting embedded marker', () => {
    const f = fixture();
    f.feed(Buffer.concat([Buffer.from([0xff]), Buffer.from(line())]));
    f.feed('x'.repeat(16384)); f.feed('extra ' + line());
    f.feed('x'.repeat(1024 * 1024) + line());
    assert.equal(f.rows.length, 0);
    f.feed(line()); assert.deepEqual(decoded(f.rows), [sample()]);
});
test('16KiB line bound is a byte bound and incomplete close releases listener without flushing', () => {
    const f = fixture();
    f.feed('é'.repeat(8192) + line()); assert.equal(f.rows.length, 0);
    f.feed(line().slice(0, -1)); f.child.emit('close'); f.feed('\n' + line());
    assert.equal(f.rows.length, 0); assert.equal(f.child.stdout.listenerCount('data'), 0);
});
test('512-row quota bounds valid emissions per child and releases parser; rejected rows do not consume quota', () => {
    const f = fixture(); f.feed('bad\n'.repeat(1000)); f.feed(line().repeat(600));
    assert.equal(f.rows.length, 512); assert.equal(f.child.stdout.listenerCount('data'), 0);
    f.feed(line()); assert.equal(f.rows.length, 512);
});
test('disabled, non-boolean enable and any public-place state attach nothing', () => {
    for (const options of [{ enabled: false }, { enabled: '1' }, { publicPlace: true }, { publicPlace: undefined }]) {
        const f = fixture(options); f.feed(line());
        assert.equal(f.child.stdout.listenerCount('data'), 0); assert.deepEqual(f.rows, []);
    }
});
test('diagnostic sink failure cannot throw into original child event lifecycle', () => {
    const f = fixture({ emit: () => { throw Error('private'); } });
    assert.doesNotThrow(() => f.feed(line().repeat(512)));
    assert.equal(f.child.stdout.listenerCount('data'), 0);
});
test('actual source-extracted process method preserves native spawn/stdio and excludes public/disabled/other labels', () => {
    const source = readFileSync(new URL('./server.mjs', import.meta.url), 'utf8');
    const begin = source.indexOf('    process(command, args, env, label, options) {');
    const end = source.indexOf('\n    async asset(', begin);
    assert.ok(begin >= 0 && end > begin);
    for (const [enabled, publicPlace, label, expected] of [
        ['1', false, 'Native Overte client', true], ['1', false, 'Private native network', true], ['passive', false, 'Private native network', true],
        ['passive', true, 'Private native network', false], ['PASSIVE', false, 'Native Overte client', false],
        ['0', false, 'Native Overte client', false], ['1', true, 'Native Overte client', false],
        ['1', false, 'Native audio', false]]) {
        const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter();
        const projected = [], spawns = []; let wireCalls = 0;
        const method = vm.runInNewContext('({' + source.slice(begin, end) + '}).process', {
            spawn: (...args) => { spawns.push(args); return child; }, attachNativeAvatarProjection,
            process: { env: { OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS: enabled }, stdout: { write: row => projected.push(row) } },
            send: () => { wireCalls++; }
        });
        const session = { processes: [], publicPlace, closed: false, browser: {}, close() { throw Error('unexpected close'); } };
        assert.equal(method.call(session, '/reviewed/native', ['--ordinary'], { ONLY: 'existing-env' }, label), child);
        child.stdout.emit('data', Buffer.from('[Qt] ' + line()));
        assert.equal(projected.length, expected ? 1 : 0); assert.equal(wireCalls, 0);
        assert.equal(spawns.length, 1); assert.deepEqual([...spawns[0][2].stdio], ['pipe', 'pipe', 'pipe']);
        assert.deepEqual(spawns[0][2].env, { ONLY: 'existing-env' });
        if (label !== 'Native audio') assert.equal(typeof session.diagnostics, 'function');
    }
});
test('actual unchanged native diagnostic emitter produces sample and author rows accepted without schema drift', () => {
    const f = fixture();
    const source = readFileSync(new URL('./native-avatar-sample-diagnostics.js', import.meta.url), 'utf8');
    const create = vm.runInNewContext(source + '\ncreateNativeAvatarSampleDiagnostics;');
    const diagnostics = create({ current: () => true, now: () => 1790899200123,
        print: message => f.feed('[INFO][script] ' + message + '\n'), stats: { myAvatarSendRate: 20, avatarMixerOutPps: 30 } });
    diagnostics.beginBatch(); const row = diagnostics.beginAvatar(); diagnostics.poseSampled(row);
    const position = { x: 0, y: 1, z: 0 };
    diagnostics.completed(row, { position, displayName: 'authored-self' }, true, { position });
    diagnostics.published(); diagnostics.authorObservation(); diagnostics.stop();
    assert.equal(f.rows.length, 2);
    assert.equal(decoded(f.rows)[0].role, 'self');
    assert.equal(decoded(f.rows)[1].cachedMyAvatarSendRateHz, 20);
});
test('passive emitter projects the unchanged strict schema without native diagnostic probes', () => {
    const f = fixture();
    const source = readFileSync(new URL('./native-avatar-sample-diagnostics.js', import.meta.url), 'utf8');
    const create = vm.runInNewContext(source + '\ncreateNativeAvatarSampleDiagnostics;');
    const forbidden = new Proxy({}, { get() { throw Error('private extra native read'); } });
    const diagnostics = create({ mode: 'passive', current: () => true, now: () => 1790899200123,
        print: message => f.feed('[INFO][script] ' + message + '\n'), stats: forbidden, avatarList: forbidden });
    diagnostics.beginBatch(); const row = diagnostics.beginAvatar(); diagnostics.poseSampled(row);
    const position = { x: 0, y: 1, z: 0 };
    diagnostics.completed(row, { position, displayName: 'Native-Lab-Participant' }, false, forbidden);
    diagnostics.published(); diagnostics.authorObservation(); diagnostics.stop();
    assert.equal(f.rows.length, 2);
    const rows = decoded(f.rows); assert.equal(rows[0].role, 'fixture-peer');
    assert.equal(rows[0].postPublicationProbeMs, null); assert.equal(rows[0].peerPacketRateHz, null);
    assert.equal(rows[1].cachedMyAvatarSendRateHz, null);
});
