// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import ReceivedMessage from '../src/protocol/vircadia/domain/networking/ReceivedMessage';
import SockAddr from '../src/protocol/vircadia/domain/networking/SockAddr';
import AvatarIdentity from '../src/protocol/vircadia/domain/networking/packets/AvatarIdentity';
import DomainList from '../src/protocol/vircadia/domain/networking/packets/DomainList';
import DomainServerAddedNode from '../src/protocol/vircadia/domain/networking/packets/DomainServerAddedNode';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';
import SequenceNumber from '../src/protocol/vircadia/domain/networking/udt/SequenceNumber';
import Uuid from '../src/protocol/vircadia/domain/shared/Uuid';
import { ASSET_REPLY_HEADER_BYTES, MAX_ASSET_BYTES, nativeAssetGetBody, nativeAssetMapping, nativeAssetReply } from '../src/protocol/native-assets';
import { MAX_RELIABLE_MESSAGE_BYTES, MessageAssembler } from '../src/protocol/message-assembler';
import UDT from '../src/protocol/vircadia/domain/networking/udt/UDT';
import '../src/protocol/vircadia/domain/shared/DataViewExtensions';

const fixtures = JSON.parse(readFileSync(new URL('./fixtures/native-wire.json', import.meta.url), 'utf8'));
function payload(list: NLPacketList): Buffer {
    list.closeCurrentPacket();
    list.preparePackets(1);
    return Buffer.concat(list.getPackets().map(packet => {
        const data = packet.getMessageData();
        const start = NLPacket.totalNLHeaderSize(packet.getType(), true);
        return Buffer.from(data.buffer.subarray(start, data.packetSize));
    }));
}

function nativeView(hex: string): DataView {
    const bytes = Buffer.from(hex, 'hex');
    const backing = Buffer.concat([Buffer.from([99, 98]), bytes, Buffer.from([97])]);
    return new DataView(backing.buffer, backing.byteOffset + 2, bytes.byteLength);
}
test('native Qt socket records retain null/Any/IPv4 boundaries and UUID byte order', () => {
    for (const fixture of fixtures.nodeRecords) {
        if (fixture.name === 'ipv6-public') {
            assert.throws(() => DomainServerAddedNode.read(nativeView(fixture.hex)), /IPv6/);
            continue;
        }
        const node = DomainServerAddedNode.read(nativeView(fixture.hex));
        const ipv4 = (value: string) => ['null', 'any'].includes(value) ? 0
            : value.split('.').reduce((address, octet) => address * 256 + Number(octet), 0);
        assert.equal(node.type, fixture.type);
        assert.equal(node.uuid.stringify(), fixture.uuid);
        assert.equal(node.connectionSecretUUID.stringify(), fixture.secret);
        assert.equal(node.publicSocket.getAddress(), ipv4(fixture.public));
        assert.equal(node.localSocket.getAddress(), ipv4(fixture.local));
        assert.equal(node.publicSocket.getPort(), fixture.port);
        assert.equal(node.localSocket.getPort(), fixture.port);
        assert.equal(node.permissions.permissions, fixture.permissions);
        assert.equal(node.sessionLocalID, fixture.localID);
        assert.equal(node.isReplicated, false);
        for (let length = 0; length < fixture.hex.length / 2; length++) {
            assert.throws(() => DomainServerAddedNode.read(nativeView(fixture.hex.slice(0, length * 2))), /truncated/);
        }
    }
    const fixture = fixtures.domainList;
    const bytes = fixture.headerHex + fixtures.nodeRecords.filter((node: { name: string }) => node.name !== 'ipv6-public')
        .map((node: { hex: string }) => node.hex).join('');
    const domain = DomainList.read(nativeView(bytes));
    assert.equal(domain.domainUUID.stringify(), fixture.domainUUID);
    assert.equal(domain.domainLocalID, fixture.domainLocalID);
    assert.equal(domain.newUUID.stringify(), fixture.newUUID);
    assert.equal(domain.newLocalID, fixture.newLocalID);
    assert.equal(domain.nodes.length, 4);
    assert.equal(domain.connectRequestTimestamp, 0x0102030405060708n);
    assert.equal(domain.domainServerPingSendTime, 0x1112131415161718n);
    assert.equal(domain.domainServerCheckinProcessingTime, 0x2122232425262728n);
    assert.equal(domain.newConnection, true);
    for (let length = 0; length < 66; length++) {
        assert.throws(() => DomainList.read(nativeView(bytes.slice(0, length * 2))), /truncated/);
    }
});
test('native node address readers reject unsupported discriminators and trailing data', () => {
    const record = Buffer.from(fixtures.nodeRecords[0].hex, 'hex');
    const changed = Buffer.from(record); changed[17] = 255;
    assert.throws(() => DomainServerAddedNode.read(nativeView(changed.toString('hex'))), /socket type/);
    changed.set(record); changed[18] = 3;
    assert.throws(() => DomainServerAddedNode.read(nativeView(changed.toString('hex'))), /address protocol/);
    assert.throws(() => DomainServerAddedNode.read(nativeView(record.toString('hex') + '00')), /Length mismatch/);
});

test('ATP PacketList strings match the fixture also executed by native C++', () => {
    const list = NLPacketList.create(PacketType.AssetMappingOperation, null, true, true);
    list.writeString(fixtures.packetString.text);
    assert.equal(payload(list).toString('hex'), fixtures.packetString.hex);
});
test('native complete-file AssetGet has both range boundaries zero', () => {
    assert.equal(Buffer.from(nativeAssetGetBody(fixtures.assetGet.id, fixtures.assetGet.hash)).toString('hex'), fixtures.assetGet.hex);
});
test('avatar identity retains QDataStream UTF-16 and has no deprecated attachment block', () => {
    const fixture = fixtures.avatarIdentity;
    const bytes = payload(AvatarIdentity.write({ sessionUUID: new Uuid(fixture.uuid),
        identitySequenceNumber: new SequenceNumber(fixture.sequence), displayName: fixture.displayName,
        sessionDisplayName: fixture.sessionDisplayName, isReplicated: false, lookAtSnapping: false, verificationFailed: false }));
    assert.equal(bytes.toString('hex'), fixture.hex);
    const backing = Buffer.concat([Buffer.from([99, 98]), bytes, bytes, Buffer.from([97])]);
    const decoded = AvatarIdentity.read(new DataView(backing.buffer, backing.byteOffset + 2, bytes.byteLength * 2));
    assert.equal(decoded.length, 2); assert.equal(decoded[1].displayName, fixture.displayName);
    assert.equal(decoded[1].sessionUUID.stringify(), fixture.uuid);
});
test('native asset replies validate identity, bounds, and redirected UTF-8 path', () => {
    const hash = fixtures.assetGet.hash, id = fixtures.assetGet.id;
    const path = new TextEncoder().encode('/.baked/scene/Visitor Ω.fbx');
    const mapping = new Uint8Array(42 + path.byteLength), view = new DataView(mapping.buffer);
    view.setUint32(0, id, true); mapping.set(Buffer.from(hash, 'hex'), 5); view.setUint8(37, 1);
    view.setUint32(38, path.byteLength, true); mapping.set(path, 42);
    assert.deepEqual(nativeAssetMapping(view, id), { hash, redirectedPath: '/.baked/scene/Visitor Ω.fbx' });
    assert.throws(() => nativeAssetMapping(view, id + 1), /Invalid/);
    assert.throws(() => nativeAssetMapping(new DataView(mapping.buffer, 0, mapping.byteLength - 1), id), /Invalid/);
    const reply = new Uint8Array(48), replyView = new DataView(reply.buffer);
    reply.set(Buffer.from(hash, 'hex')); replyView.setUint32(32, id, true); replyView.setBigInt64(37, 3n, true);
    reply.set([10, 20, 30], 45);
    assert.deepEqual([...new Uint8Array(nativeAssetReply(replyView, id, hash))], [10, 20, 30]);
    assert.throws(() => nativeAssetReply(replyView, id, 'f'.repeat(64)), /Invalid/);
    replyView.setBigInt64(37, -1n, true); assert.throws(() => nativeAssetReply(replyView, id, hash), /size/);
});
test('fragmented real NLPacket messages assemble exact payload once and retain metadata', () => {
    const source = new Uint8Array(32 * 1024).map((_, index) => index & 255);
    const list = NLPacketList.create(PacketType.BrowserEntityData, null, true, true);
    list.write(source); list.closeCurrentPacket(); list.preparePackets(7);
    const packets = list.getPackets().map(packet => {
        const data = packet.getMessageData();
        return NLPacket.fromReceivedPacket(data.data, data.packetSize, new SockAddr());
    });
    assert.ok(packets.length > 2);
    const message = new ReceivedMessage(packets[0]);
    assert.throws(() => message.getMessage(), /before/);
    for (const packet of packets.slice(1)) message.appendPacket(packet);
    assert.equal(message.getMessageData().numPackets, packets.length);
    const assembled = message.getMessage();
    assert.deepEqual(new Uint8Array(assembled.buffer, assembled.byteOffset, assembled.byteLength), source);
    assert.equal(message.getMessage().buffer, assembled.buffer);
});
test('reliable message assembly rejects oversized messages before allocation', () => {
    const assembler = new MessageAssembler(4);
    assembler.append(new Uint8Array([1, 2, 3]));
    assert.throws(() => assembler.append(new Uint8Array([4, 5])), /limit/);
    assert.deepEqual([...assembler.finish()], [1, 2, 3]);
});
test('maximum native asset body and reply header fit reliable assembly without allocating asset-sized storage', () => {
    // Native AssetGetReply body: hash32 + requestID4 + error1 + dataSize8.
    assert.equal(ASSET_REPLY_HEADER_BYTES, 32 + 4 + 1 + 8);
    assert.equal(MAX_RELIABLE_MESSAGE_BYTES, MAX_ASSET_BYTES + ASSET_REPLY_HEADER_BYTES);
    const assembler = new MessageAssembler();
    assembler.append(new Uint8Array(ASSET_REPLY_HEADER_BYTES));
    // Reuse one datagram-sized backing allocation; append only records views.
    // Do not finish(), which would intentionally allocate the complete 64 MiB body.
    const payloadBytes = UDT.MAX_PACKET_SIZE - NLPacket.totalNLHeaderSize(PacketType.AssetGetReply, true);
    const sharedPacket = new Uint8Array(payloadBytes);
    let remaining = MAX_ASSET_BYTES;
    while (remaining >= sharedPacket.byteLength) {
        assembler.append(sharedPacket); remaining -= sharedPacket.byteLength;
    }
    if (remaining) assembler.append(sharedPacket.subarray(0, remaining));
    assert.throws(() => assembler.append(new Uint8Array(1)), /limit/,
        'one byte beyond the full native asset plus header remains bounded');
});
