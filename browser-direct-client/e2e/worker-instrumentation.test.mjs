// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { createHeaderObserver } from './header-evidence.mjs';
import { observeWorkerTransport } from './worker-instrumentation.mjs';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList.ts';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders.ts';
import SequenceNumber from '../src/protocol/vircadia/domain/networking/udt/SequenceNumber.ts';

function environment() {
    const scope = { ArrayBuffer, DataView, Uint32Array, Uint8Array, TextEncoder, Blob, performance };
    runInNewContext(`globalThis.overteTestOnlyHeaderObserverFactory = (${createHeaderObserver.toString()}); (${observeWorkerTransport.toString()})();`, scope);
    return scope;
}
class ActualAPIShapeChannel extends EventTarget {
    label = 'label'; readyState = 'open'; ordered = false; maxRetransmits = 0;
    writes = []; reject = false;
    send(value) { if (this.reject) throw new Error('Actual send failed'); this.writes.push(value); return 'sent'; }
    receive(value) { this.dispatchEvent(new MessageEvent('message', { data: value })); }
}
function fragments() {
    const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
    list.write(new TextEncoder().encode('PRIVATE-PAYLOAD '.repeat(300))); list.closeCurrentPacket(); list.preparePackets(42);
    return list.getPackets().map((packet, index) => {
        packet.writeSequenceNumber(new SequenceNumber(1000 + index));
        const message = packet.getMessageData();
        return new Uint8Array(message.data.buffer, message.data.byteOffset, message.packetSize).slice();
    });
}

test('worker observation retains actual native header counters without changing packets, send results or SDK delivery', () => {
    const scope = environment(), channel = new ActualAPIShapeChannel(), datagrams = fragments();
    const received = [], before = datagrams.map(value => value.slice());
    scope.overteTestOnlyWatchWorkerChannel(channel, 'A');
    scope.overteTestOnlyWatchWorkerChannel(channel, 'A');
    channel.addEventListener('message', event => received.push(event.data));
    for (const value of datagrams) { assert.equal(channel.send(value), 'sent'); channel.receive(value); }
    assert.equal(channel.writes.length, datagrams.length); assert.deepEqual(received, datagrams);
    datagrams.forEach((value, index) => assert.deepEqual(value, before[index]));
    const result = scope.overteWorkerTransportEvidence(), actual = result.channels[0];
    assert.equal(result.channels.length, 1); assert.equal(actual.owner, 'session-worker'); assert.equal(actual.nodeType, 'A');
    assert.equal(actual.headers.received.uniqueReliable, datagrams.length); assert.equal(actual.headers.received.wirePartsComplete, 1);
    assert.equal(actual.receivedBytes, datagrams.reduce((sum, value) => sum + value.byteLength, 0));
    channel.reject = true;
    assert.throws(() => channel.send(datagrams[0]), /Actual send failed/);
    assert.equal(scope.overteWorkerTransportEvidence().channels[0].sentMessages, datagrams.length);
    assert.ok(!JSON.stringify(result).includes('PRIVATE-PAYLOAD'));
    channel.readyState = 'closed'; assert.equal(scope.overteWorkerTransportEvidence().channels[0].readyState, 'closed');
});

test('worker observer emits bounded eviction and omits arbitrary labels and negotiation values', () => {
    const scope = environment(), first = new ActualAPIShapeChannel(), original = first.send;
    first.label = 'PRIVATE-CHANNEL'; scope.overteTestOnlyWatchWorkerChannel(first, 'PRIVATE-NODE');
    let result = scope.overteWorkerTransportEvidence();
    assert.equal(result.channels[0].nodeType, null); assert.equal(result.channels[0].label, '[omitted]');
    assert.ok(!JSON.stringify(result).includes('PRIVATE'));
    for (let index = 0; index < 32; index++) scope.overteTestOnlyWatchWorkerChannel(new ActualAPIShapeChannel(), 'A');
    result = scope.overteWorkerTransportEvidence();
    assert.equal(result.channels.length, 32); assert.equal(result.observerLimits.evictedChannels, 1);
    assert.equal(first.send, original, 'evicted channels release their test wrappers');
    first.receive(fragments()[0]);
    assert.ok(result.channels.every(channel => channel.receivedMessages === 0));
});
