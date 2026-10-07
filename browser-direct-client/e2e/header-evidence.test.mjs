// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHeaderObserver } from './header-evidence.mjs';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList.ts';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders.ts';
import Packet from '../src/protocol/vircadia/domain/networking/udt/Packet.ts';
import ControlPacket from '../src/protocol/vircadia/domain/networking/udt/ControlPacket.ts';
import SequenceNumber from '../src/protocol/vircadia/domain/networking/udt/SequenceNumber.ts';

const bytes = packet => { const data = packet.getMessageData(); return new Uint8Array(data.data.buffer, data.data.byteOffset, data.packetSize).slice(); };
const control = (type, sequence) => { const packet = ControlPacket.create(type, 4); packet.writeSequenceNumber(new SequenceNumber(sequence)); return bytes(packet); };
const actualFragments = initial => {
    const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
    list.write(new Uint8Array(64000).fill(0xa5)); list.closeCurrentPacket(); list.preparePackets(42);
    return list.getPackets().map((packet, index) => { packet.writeSequenceNumber(new SequenceNumber((initial + index) % 0x8000000)); return bytes(packet); });
};

for (const initial of [1001, 0x7fffffd]) test(`header evidence distinguishes actual missing/repeated parts and ACKs across wrap from ${initial}`, () => {
    const observer = createHeaderObserver(), fragments = actualFragments(initial);
    observer.accept(control(ControlPacket.Handshake, initial));
    for (let index = 0; index < fragments.length; index++) if (index !== 1 && index !== 5) observer.accept(fragments[index]);
    let result = observer.snapshot();
    assert.equal(result.trackedMissingSequences, 2);
    assert.equal(result.messages[0].lastSeen, true); assert.equal(result.messages[0].firstMissingPart, 1);
    assert.equal(result.messages[0].missingParts, 2); assert.equal(result.wirePartsComplete, 0);
    observer.accept(fragments[5]); observer.accept(fragments[5]);
    result = observer.snapshot(); assert.equal(result.trackedMissingSequences, 1); assert.equal(result.repeatedReliable, 1);
    assert.equal(result.messages[0].repeatedParts, 1); assert.equal(result.messages[0].firstMissingPart, 1);
    observer.accept(fragments[1]);
    observer.accept(control(ControlPacket.ACK, initial)); observer.accept(control(ControlPacket.ACK, initial));
    const last = (initial + fragments.length - 1) % 0x8000000;
    observer.accept(control(ControlPacket.ACK, last));
    result = observer.snapshot();
    assert.equal(result.trackedMissingSequences, 0); assert.equal(result.wirePartsComplete, 1);
    assert.equal(result.messages[0].expectedParts, fragments.length); assert.equal(result.messages[0].missingParts, 0);
    assert.equal(result.ackFrontier, last); assert.equal(result.ackAdvances, 1); assert.equal(result.repeatedAcks, 1);
    assert.ok(!JSON.stringify(result).includes('165,165'), 'No original payload data is serialized');
});

test('native obfuscation leaves only safe type/version diagnostics and never modifies actual packets', () => {
    const observer = createHeaderObserver();
    for (let level = 0; level < 4; level++) {
        const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
        list.write(new Uint8Array(16)); list.closeCurrentPacket(); list.preparePackets(100 + level);
        const packet = list.getPackets()[0]; packet.obfuscate(level);
        const actual = bytes(packet), before = actual.slice(); observer.accept(actual);
        assert.deepEqual(actual, before);
    }
    const result = observer.snapshot();
    assert.deepEqual(result.obfuscationLevels, [1, 1, 1, 1]);
    assert.equal(Object.keys(result.packetTypes).length, 1);
    assert.ok(Object.keys(result.packetTypes)[0].startsWith(`${PacketType.AssetGetReply}:`));
    assert.equal(result.messages.every(message => message.positions[Packet.PacketPosition.ONLY] === 1), true);
    assert.equal(result.wirePartsComplete, 4);
});

test('malformed and oversized data are bounded without payload retention', () => {
    const observer = createHeaderObserver();
    observer.accept('private payload'); observer.accept(new Uint8Array(3)); observer.accept(new Uint8Array(1425));
    observer.accept(new Uint8Array([0, 0, 0, 0x60]));
    const result = observer.snapshot();
    assert.equal(result.nonBinary, 1); assert.equal(result.malformed, 3); assert.deepEqual(result.messages, []);
    assert.ok(!JSON.stringify(result).includes('private payload'));
});

test('header observer emits explicit eviction rather than keeping unlimited message bitmaps', () => {
    const observer = createHeaderObserver();
    for (let index = 0; index < 40; index++) {
        const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
        list.write(new Uint8Array(1)); list.closeCurrentPacket(); list.preparePackets(index + 1);
        observer.accept(bytes(list.getPackets()[0]));
    }
    const result = observer.snapshot(); assert.equal(result.messages.length, 32); assert.equal(result.messageEvictions, 8);
    assert.equal(result.wirePartsComplete, 40); assert.ok(result.messages.every(message => !Object.hasOwn(message, 'parts')));
    const old = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
    old.write(new Uint8Array(1)); old.closeCurrentPacket(); old.preparePackets(1); observer.accept(bytes(old.getPackets()[0]));
    const later = observer.snapshot(), recreated = later.messages.find(message => message.number === 1);
    assert.equal(recreated.historyIncomplete, true); assert.equal(recreated.missingParts, null);
    assert.equal(later.reobservedEvictedMessages, 1); assert.equal(later.wirePartsComplete, 40, 'An observed late duplicate does not count as another unique complete message');
});
