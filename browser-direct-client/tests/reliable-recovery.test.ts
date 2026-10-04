// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import ReceivedMessage from '../src/protocol/vircadia/domain/networking/ReceivedMessage';
import SockAddr from '../src/protocol/vircadia/domain/networking/SockAddr';
import Connection from '../src/protocol/vircadia/domain/networking/udt/Connection';
import CongestionControl from '../src/protocol/vircadia/domain/networking/udt/CongestionControl';
import ControlPacket from '../src/protocol/vircadia/domain/networking/udt/ControlPacket';
import LossList from '../src/protocol/vircadia/domain/networking/udt/LossList';
import Packet from '../src/protocol/vircadia/domain/networking/udt/Packet';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';
import SequenceNumber from '../src/protocol/vircadia/domain/networking/udt/SequenceNumber';
import type Socket from '../src/protocol/vircadia/domain/networking/udt/Socket';

test('loss intervals remove only retransmitted members and preserve other missing packets', () => {
    const list = new LossList();
    list.append(new SequenceNumber(10), new SequenceNumber(14));
    assert.equal(list.remove(new SequenceNumber(9)), false);
    assert.equal(list.remove(new SequenceNumber(15)), false);
    assert.equal(list.getLength(), 5);
    assert.equal(list.remove(new SequenceNumber(12)), true);
    assert.equal(list.remove(new SequenceNumber(12)), false);
    assert.equal(list.getLength(), 4);
    for (const value of [10, 14, 11, 13]) assert.equal(list.remove(new SequenceNumber(value)), true);
    assert.equal(list.isEmpty(), true);
});

for (const initial of [1001, SequenceNumber.MAX - 2]) {
    test(`actual reliable asset fragments recover dropped/reordered packets and ACK progress from sequence ${initial}`, () => {
        const source = Uint8Array.from({ length: 64 * 1024 }, (_, index) => (index * 13) & 255);
        const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
        list.write(source); list.closeCurrentPacket(); list.preparePackets(7);
        const sender = new SockAddr(), acknowledgements: number[] = [];
        let message: ReceivedMessage | undefined;
        const deliveredParts: number[] = [];
        const socket = {
            writeBasePacket(control: ControlPacket) {
                if (control.getType() === ControlPacket.ACK) acknowledgements.push(control.getMessageData().data.getUint32(4, true));
                return control.getMessageData().packetSize;
            },
            messageReceived(packet: Packet) {
                deliveredParts.push(packet.getMessagePartNumber());
                const native = NLPacket.fromBase(packet);
                if (message) message.appendPacket(native); else message = new ReceivedMessage(native);
            },
            messageFailed() { assert.fail('A loss/retransmission within one handshake must retain the pending message.'); },
        } as unknown as Socket;
        const connection = new Connection(socket, sender, new CongestionControl());
        const handshake = ControlPacket.create(ControlPacket.Handshake, 4);
        handshake.writeSequenceNumber(new SequenceNumber(initial));
        connection.processControl(ControlPacket.fromReceivedPacket(handshake.getMessageData().data, 8, sender));
        const packets = list.getPackets().map((packet, part) => {
            packet.writeSequenceNumber(new SequenceNumber((initial + part) % (SequenceNumber.MAX + 1)));
            const data = packet.getMessageData();
            const copy = data.data.buffer.slice(data.data.byteOffset, data.data.byteOffset + data.packetSize);
            return Packet.fromReceivedPacket(new DataView(copy), data.packetSize, sender);
        });
        assert.ok(packets.length > 20);
        const deliver = (part: number) => {
            const packet = packets[part];
            const accepted = connection.processReceivedSequenceNumber(new SequenceNumber(packet.getMessageData().sequenceNumber));
            if (accepted) connection.queueReceivedMessagePacket(packet);
            return accepted;
        };
        const missing = new Set([1, 5, 7]);
        for (let part = 0; part < packets.length; part++) if (!missing.has(part)) assert.equal(deliver(part), true);
        assert.deepEqual(deliveredParts, [0], 'ordered assembly waits at the first actual missing part');
        assert.equal(acknowledgements.at(-1), initial);
        assert.equal(deliver(5), true, 'an out-of-order retransmission closes its own loss interval');
        assert.equal(deliver(7), true);
        assert.equal(deliver(10), false, 'already accepted packets are duplicates, not losses');
        assert.equal(acknowledgements.at(-1), initial, 'later recovery cannot ACK across the still-missing first part');
        assert.equal(deliver(1), true, 'the first gap must be recoverable');
        assert.deepEqual(deliveredParts, packets.map((_, index) => index));
        assert.equal(acknowledgements.at(-1), (initial + packets.length - 1) % (SequenceNumber.MAX + 1));
        assert.ok(message?.getMessageData().isComplete);
        const body = message.getMessage();
        assert.deepEqual(new Uint8Array(body.buffer, body.byteOffset, body.byteLength), source);
        assert.equal(deliver(1), false, 'post-completion retransmission cannot reopen a delivered message');
        connection.dispose();
    });
}
