// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createAvatarReceiveObserver } from './avatar-receive-evidence.mjs';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket.ts';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders.ts';
import BulkAvatarData from '../src/protocol/vircadia/domain/networking/packets/BulkAvatarData.ts';
import '../src/protocol/vircadia/domain/shared/DataViewExtensions.ts';

const nativeID = '10203040-5060-7080-90a0-b0c0d0e0f010';
function record({ flags = 1, x = 155.125, y = -96.9029, z = -400.1885, joint = 1, id = nativeID } = {}) {
    const parts = [], add = count => { const value = new Uint8Array(count); parts.push(value); return new DataView(value.buffer); };
    const initial = add(18); initial.setBigUint128(0, BigInt('0x' + id.replaceAll('-', '')), false); initial.setUint16(16, flags, true);
    const fixed = [12, 24, 6, 2, 12, 1, 20, 2, 18, 12, 24];
    for (let bit = 0; bit < fixed.length; bit++) if (flags & (1 << bit)) {
        const data = add(fixed[bit]); if (bit === 0) { data.setFloat32(0, x, true); data.setFloat32(4, y, true); data.setFloat32(8, z, true); }
    }
    if (flags & 0x800) { add(16); add(1).setUint8(0, 3); add(12); }
    if (flags & 0x1000) {
        add(1).setUint8(0, 1); add(1).setUint8(0, 1); const rotation = add(6); rotation.setUint16(0, joint, true);
        add(1).setUint8(0, 1); add(4).setFloat32(0, 1, true); add(6);
        if (flags & 0x4000) add(84);
    }
    if (flags & 0x2000) { add(1).setUint8(0, 1); add(2); }
    const result = new Uint8Array(parts.reduce((sum, value) => sum + value.length, 0)); let offset = 0;
    for (const value of parts) { result.set(value, offset); offset += value.length; }
    return result;
}
function datagram(payload, { message = false, level = 0, version = 55 } = {}) {
    const packet = NLPacket.create(PacketType.BulkAvatarData, payload.length, false, message, version);
    const initial = packet.getMessageData();
    initial.buffer.set(payload, NLPacket.totalNLHeaderSize(PacketType.BulkAvatarData, message));
    if (message) packet.writeMessageNumber(23, 0, 0);
    packet.obfuscate(level); const data = packet.getMessageData();
    return new Uint8Array(data.data.buffer, data.data.byteOffset, data.packetSize).slice();
}

for (const message of [false, true]) test(`actual SDK packet writer: four native XOR levels, ${message ? 'ONLY part0' : 'ordinary'} header and offset views`, () => {
    const observer = createAvatarReceiveObserver('{' + nativeID.toUpperCase() + '}');
    const payload = record({ flags: 0x7001 });
    assert.equal(BulkAvatarData.read(new DataView(payload.buffer)).length, 1, 'Independent SDK decoder agrees with complete record extent');
    for (let level = 0; level < 4; level++) {
        const packet = datagram(payload, { level, message }), surrounded = new Uint8Array(packet.length + 13).fill(0xe7);
        surrounded.set(packet, 7); const view = new DataView(surrounded.buffer, 7, packet.length), before = surrounded.slice();
        observer.accept(view); assert.deepEqual(surrounded, before, 'actual received bytes and adjacent bytes stay unchanged');
    }
    const result = observer.snapshot(); assert.equal(result.positions, 4); assert.deepEqual(result.obfuscationLevels, [1, 1, 1, 1]);
    assert.equal(result.last.firstBodyBytes, payload.length - 16); assert.equal(result.last.trailingRecordBytes, 0);
    assert.ok(result.last.jointChecksum); assert.equal(result.last.reliable, false); assert.equal(result.last.message, message);
    assert.equal(result.last.position.x, 155.125);
    assert.ok(Math.abs(result.last.position.z + 400.1885) < .0001);
    const serialized = JSON.stringify(result);
    for (const privateValue of [nativeID, nativeID.replaceAll('-', ''), 'sourceID', 'sessionUUID', 'payload']) assert.ok(!serialized.includes(privateValue));
});

test('all native optional sections bound the first checksum independently of later records and verified headers', () => {
    const observer = createAvatarReceiveObserver(nativeID), first = record({ flags: 0x7fff });
    const second = record({ x: 900, id: 'ffeeddcc-bbaa-9988-7766-554433221100' });
    const payload = new Uint8Array(first.length + second.length); payload.set(first); payload.set(second, first.length);
    assert.equal(BulkAvatarData.read(new DataView(payload.buffer)).length, 2);
    observer.accept(datagram(payload)); const before = observer.snapshot();
    const changedSecond = payload.slice(); changedSecond[changedSecond.length - 1] ^= 0xff;
    const packet = datagram(changedSecond); packet.fill(0xaf, 6, 24); observer.accept(packet);
    let result = observer.snapshot(); assert.equal(result.last.bodyChecksum, before.last.bodyChecksum);
    assert.equal(result.bodyChecksumChanges, 0); assert.equal(result.last.trailingRecordBytes, second.length);
    observer.accept(datagram(record({ flags: 0x7fff, joint: 2 })));
    result = observer.snapshot(); assert.equal(result.bodyChecksumChanges, 1); assert.equal(result.jointChecksumChanges, 1);
    assert.equal(result.positionChanges, 0, 'stationary position does not imply static joint bytes');
});

test('first-record identity, malformed/version/finite checks and every truncated prefix are explicit', () => {
    const observer = createAvatarReceiveObserver(nativeID), packet = datagram(record({ flags: 0x7001 }));
    for (let size = 0; size < packet.length; size++) assert.doesNotThrow(() => observer.accept(packet.subarray(0, size)));
    observer.accept(new Uint8Array(1425)); observer.accept('private body');
    observer.accept(datagram(record(), { version: 54 })); observer.accept(datagram(record({ x: Infinity })));
    observer.accept(datagram(record({ flags: 0x8001 }))); observer.accept(datagram(record({ flags: 0x4001 })));
    observer.accept(datagram(record({ id: 'ffeeddcc-bbaa-9988-7766-554433221100' })));
    const result = observer.snapshot(); assert.equal(result.positions, 0); assert.equal(result.oversized, 1); assert.equal(result.nonBinary, 1);
    assert.equal(result.wrongVersion, 1); assert.equal(result.nonFinitePosition, 1); assert.equal(result.unsupportedFlags, 1);
    assert.equal(result.unsupportedBodyLayout, 1); assert.equal(result.firstRecordOtherPeer, 1); assert.ok(result.truncated > 0);
    assert.throws(() => createAvatarReceiveObserver('{'+nativeID), /qualified/);
});

test('FIRST MIDDLE LAST and ONLY nonzero part refuse body interpretation; retained samples have explicit eviction', () => {
    const observer = createAvatarReceiveObserver(nativeID);
    for (const position of [1, 2, 3]) {
        const bytes = datagram(record(), { message: true }); new DataView(bytes.buffer).setUint32(4, (position * 0x40000000 + 23) >>> 0, true); observer.accept(bytes);
    }
    const bytes = datagram(record(), { message: true }); new DataView(bytes.buffer).setUint32(8, 1, true); observer.accept(bytes);
    assert.equal(observer.snapshot().unsupportedFragments, 4); assert.equal(observer.snapshot().firstRecordNativeMatches, 0);
    for (let index = 0; index < 70; index++) observer.accept(datagram(record({ x: index })));
    const result = observer.snapshot(); assert.equal(result.samples.length, 64); assert.equal(result.sampleEvictions, 6);
    assert.equal(result.positionChanges, 69); assert.equal(result.first.position.x, 0); assert.equal(result.last.position.x, 69);
    result.samples[0].position.x = -1; assert.equal(observer.snapshot().samples[0].position.x, 6);
});
