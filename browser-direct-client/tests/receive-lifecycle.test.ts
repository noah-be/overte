// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import PacketReceiver from '../src/protocol/vircadia/domain/networking/PacketReceiver';
import SockAddr from '../src/protocol/vircadia/domain/networking/SockAddr';
import Connection from '../src/protocol/vircadia/domain/networking/udt/Connection';
import CongestionControl from '../src/protocol/vircadia/domain/networking/udt/CongestionControl';
import ControlPacket from '../src/protocol/vircadia/domain/networking/udt/ControlPacket';
import Packet from '../src/protocol/vircadia/domain/networking/udt/Packet';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';
import SequenceNumber from '../src/protocol/vircadia/domain/networking/udt/SequenceNumber';
import type Socket from '../src/protocol/vircadia/domain/networking/udt/Socket';

function sender(port: number): SockAddr { const address = new SockAddr(); address.setPort(port); return address; }
function fragments(source: Uint8Array, number: number, address: SockAddr): Packet[] {
    const list = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
    list.write(source); list.closeCurrentPacket(); list.preparePackets(number);
    return list.getPackets().map((packet, index) => {
        packet.writeSequenceNumber(new SequenceNumber(1001 + index));
        const data = packet.getMessageData();
        const owned = data.buffer.slice(0, data.packetSize);
        return Packet.fromReceivedPacket(new DataView(owned.buffer), owned.byteLength, address);
    });
}
function receiver() {
    const output: Uint8Array[] = [], receiver = new PacketReceiver(0);
    receiver.registerListener(PacketType.AssetGetReply, PacketReceiver.makeSourcedListenerReference(message => {
        const body = message.getMessage(); output.push(new Uint8Array(body.buffer, body.byteOffset, body.byteLength));
    }));
    return { receiver, output };
}

test('actual receive keys keep address/message pairs distinct even when concatenated decimal digits collide', () => {
    const { receiver: actual, output } = receiver(), first = new Uint8Array(5000).fill(17), second = new Uint8Array(5000).fill(91);
    const left = fragments(first, 23, sender(1)), right = fragments(second, 3, sender(12));
    actual.handleVerifiedMessagePacket(left[0]);
    for (const packet of right) actual.handleVerifiedMessagePacket(packet);
    assert.equal(output.length, 1); assert.deepEqual(output[0], second);
    for (const packet of left.slice(1)) actual.handleVerifiedMessagePacket(packet);
    assert.equal(output.length, 2); assert.deepEqual(output[1], first);
});

test('actual connection disposal fails and releases an unfinished receive message before the next connection can assemble', () => {
    const { receiver: actual, output } = receiver(), failed: number[] = [], address = sender(1);
    const socket = {
        writeBasePacket(control: ControlPacket) { return control.getDataSize(); },
        messageReceived: actual.handleVerifiedMessagePacket,
        messageFailed(connection: Connection, number: number) {
            failed.push(number); actual.handleMessageFailure(connection.getDestination(), number);
        },
    } as unknown as Socket;
    const connection = new Connection(socket, address, new CongestionControl());
    const handshake = ControlPacket.create(ControlPacket.Handshake, 4);
    handshake.writeSequenceNumber(new SequenceNumber(1001));
    connection.processControl(ControlPacket.fromReceivedPacket(handshake.getMessageData().data, 8, address));
    const old = fragments(new Uint8Array(5000).fill(17), 23, address);
    assert.equal(connection.processReceivedSequenceNumber(new SequenceNumber(1001)), true);
    connection.queueReceivedMessagePacket(old[0]);
    connection.dispose(); connection.dispose();
    assert.deepEqual(failed, [23], 'disposed unfinished messages must reach the real receive failure handler once');
    assert.equal(output.length, 0);
    const fresh = new Uint8Array(5000).fill(91);
    for (const packet of fragments(fresh, 23, address)) actual.handleVerifiedMessagePacket(packet);
    assert.equal(output.length, 1); assert.deepEqual(output[0], fresh, 'no old fragment can be prefixed to a later message');
});
