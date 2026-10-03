// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DirectSession } from '../src/direct-session';
import type NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import NodeType from '../src/protocol/vircadia/domain/networking/NodeType';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';
import type { SessionEvent } from '../src/session-contract';

const bridgeID = 'b42a2c92-2a33-400d-a6b4-30e3d3ff2282';

function interaction(entityId: string) {
    const packets: NLPacketList[] = [], events: SessionEvent[] = [];
    const server = { getActiveSocket: () => ({}) };
    // Execute the actual production packet writer. Only native service discovery
    // and network delivery are replaced, so no domain/browser resources open.
    const session = Object.create(DirectSession.prototype) as DirectSession;
    Object.assign(session, {
        ready: true, entities: new Map([[entityId, { id: entityId, type: 'Model' }]]),
        callbacks: { event: (event: SessionEvent) => events.push(event) },
        nodeList: {
            soloNodeOfType(type: number) { assert.equal(type, NodeType.EntityScriptServer); return server; },
            sendPacketList(packet: NLPacketList, recipient: unknown) {
                assert.equal(recipient, server); packet.closeCurrentPacket(); packets.push(packet);
            },
        },
    });
    session.sendInteraction(entityId);
    return { packets, events };
}

test('a real braced Hub entity click writes the same native UUID and method bytes as canonical text', () => {
    const method = Buffer.from('clickDownOnEntity', 'utf8');
    const length = Buffer.alloc(4); length.writeUInt32LE(method.length);
    const expected = Buffer.concat([
        Buffer.from('b42a2c922a33400da6b430e3d3ff2282', 'hex'), length, method, Buffer.alloc(2),
    ]);
    for (const id of [bridgeID, `{${bridgeID}}`, `{${bridgeID.toUpperCase()}}`]) {
        const result = interaction(id);
        assert.deepEqual(result.events, []); assert.equal(result.packets.length, 1);
        const packets = result.packets[0].getPackets(); assert.equal(packets.length, 1);
        const packet = packets[0];
        assert.equal(packet.getType(), PacketType.EntityScriptCallMethod);
        assert.equal(packet.isReliable(), true);
        assert.equal(packet.isPartOfMessage(), true);
        // Native reliable sourced/verified message packets have a 32-byte header.
        assert.equal(packet.getDataSize(), 32 + expected.length);
        assert.deepEqual(Buffer.from(packet.getMessageData().buffer.subarray(32, packet.getDataSize())), expected);
    }
});

test('malformed current entity identifiers report a bounded error without sending or throwing through the worker', () => {
    for (const id of [`{${bridgeID}`, `${bridgeID}}`, `{{${bridgeID}}}`, `${bridgeID}junk`, 'not-a-uuid']) {
        const result = interaction(id);
        assert.deepEqual(result.packets, []);
        assert.deepEqual(result.events, [{ type: 'error', message: 'The selected entity has an invalid native identifier.' }]);
    }
});
