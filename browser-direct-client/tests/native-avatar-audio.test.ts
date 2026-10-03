// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import AvatarData from '../src/protocol/vircadia/domain/networking/packets/AvatarData';
import BulkAvatarData from '../src/protocol/vircadia/domain/networking/packets/BulkAvatarData';
import SetAvatarTraits from '../src/protocol/vircadia/domain/networking/packets/SetAvatarTraits';
import BulkAvatarTraits from '../src/protocol/vircadia/domain/networking/packets/BulkAvatarTraits';
import MicrophoneAudioNoEcho from '../src/protocol/vircadia/domain/networking/packets/MicrophoneAudioNoEcho';
import MixedAudio from '../src/protocol/vircadia/domain/networking/packets/MixedAudio';
import SilentAudioFrame from '../src/protocol/vircadia/domain/networking/packets/SilentAudioFrame';
import { AvatarDataDetail } from '../src/protocol/vircadia/domain/avatars/AvatarData';
import AvatarTraits, { TraitType } from '../src/protocol/vircadia/domain/avatars/AvatarTraits';
import { ClientTraitStatus } from '../src/protocol/vircadia/domain/avatars/ClientTraitsHandler';
import GLMHelpers from '../src/protocol/vircadia/domain/shared/GLMHelpers';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import '../src/protocol/vircadia/domain/shared/DataViewExtensions';

// NativeAvatarAudioWireTests executes the production native avatar/skeleton
// serializers and native packet writer against this same fixture file.
const fixture = JSON.parse(readFileSync(new URL('./fixtures/native-avatar-audio.json', import.meta.url), 'utf8'));
function payload(packet: NLPacket): Buffer {
    const data = packet.getMessageData();
    const start = NLPacket.totalNLHeaderSize(packet.getType(), false);
    return Buffer.from(data.buffer.subarray(start, data.packetSize));
}
function listPayload(list: NLPacketList): Buffer {
    list.closeCurrentPacket(); list.preparePackets(1);
    return Buffer.concat(list.getPackets().map(packet => {
        const data = packet.getMessageData();
        const start = NLPacket.totalNLHeaderSize(packet.getType(), true);
        return Buffer.from(data.buffer.subarray(start, data.packetSize));
    }));
}
function paddedView(bytes: Buffer): DataView {
    const padded = Buffer.concat([Buffer.from([99, 98, 97]), bytes, Buffer.alloc(137, 123)]);
    return new DataView(padded.buffer, padded.byteOffset + 3, bytes.byteLength);
}

test('native avatar pose bytes include sequence, compressed orientation, negative joints, and default flags', () => {
    const input = fixture.avatar;
    const packet = AvatarData.write({ sequenceNumber: input.sequence, dataDetail: AvatarDataDetail.SendAllData,
        lastSentTime: 0, globalPosition: input.position, localOrientation: input.orientation,
        avatarScale: input.scale, audioLoudness: input.loudness, jointRotations: [input.orientation],
        jointTranslations: [input.jointTranslation], lastSentJointRotations: [null], lastSentJointTranslations: [null] });
    assert.equal(payload(packet).toString('hex'), input.hex);
    const body = Buffer.from(input.hex, 'hex').subarray(2);
    const uuid = Buffer.from(input.uuid.replaceAll('-', ''), 'hex');
    const bytes = Buffer.concat([uuid, body, uuid, Buffer.from([0, 0])]);
    const avatars = BulkAvatarData.read(paddedView(bytes));
    assert.equal(avatars.length, 2);
    assert.deepEqual(avatars[0].globalPosition, input.position);
    assert.deepEqual(avatars[0].jointTranslations, [input.jointTranslation]);
    assert.deepEqual(avatars[0].jointRotationsUseDefault, [false]);
    assert.equal(avatars[1].globalPosition, undefined);
});

test('native skeleton traits use UTF-8 byte indexes and consume only their declared body', () => {
    const input = fixture.skeleton;
    const list = SetAvatarTraits.write({ currentTraitVersion: input.version, skeletonModelURL: '',
        skeletonData: input.joints, traitStatuses: [ClientTraitStatus.Unchanged, ClientTraitStatus.Updated], initialSend: false });
    assert.equal(listPayload(list).toString('hex'), input.setTraitsHex);
    const body = Buffer.from(input.bodyHex, 'hex');
    const joints = AvatarTraits.processTrait(TraitType.SkeletonData, paddedView(body), 0, body.byteLength);
    assert.ok(Array.isArray(joints));
    assert.deepEqual(joints.map(joint => joint.jointName), ['Ω', 'Arm']);
    assert.deepEqual(joints[0].defaultTranslation, input.joints[0].defaultTranslation);
    assert.equal(joints[0].parentIndex, -1);
    assert.throws(() => AvatarTraits.processTrait(TraitType.SkeletonData, paddedView(body), 0, body.byteLength - 1), /Invalid/);
    const invalid = Buffer.from(body); invalid.writeUInt16LE(65535, 11);
    assert.throws(() => AvatarTraits.processTrait(TraitType.SkeletonData, paddedView(invalid), 0, invalid.byteLength), /Invalid/);
});

test('native zero skeleton translations/scales remain finite and long UTF-8 names obey byte limits', () => {
    const joint = { ...fixture.skeleton.joints[0], jointName: 'Ω'.repeat(128),
        defaultTranslation: { x: 0, y: 0, z: 0 }, defaultScale: 0 };
    const bytes = listPayload(SetAvatarTraits.write({ currentTraitVersion: 1, skeletonModelURL: '', skeletonData: [joint],
        traitStatuses: [ClientTraitStatus.Unchanged, ClientTraitStatus.Updated], initialSend: false }));
    const body = bytes.subarray(7);
    const joints = AvatarTraits.processTrait(TraitType.SkeletonData, paddedView(body), 0, body.byteLength);
    assert.ok(Array.isArray(joints));
    assert.equal(joints[0].jointName, '');
    assert.deepEqual(joints[0].defaultTranslation, { x: 0, y: 0, z: 0 });
    assert.ok(Number.isFinite(joints[0].defaultScale) && joints[0].defaultScale > 0);
});

test('native instanced trait deletion preserves the next simple trait and rejects negative sizes', () => {
    const skeleton = Buffer.from(fixture.skeleton.bodyHex, 'hex');
    const uuid = Buffer.from(fixture.avatar.uuid.replaceAll('-', ''), 'hex');
    const deleted = Buffer.alloc(23); deleted.writeInt8(TraitType.AvatarEntity, 0); deleted.writeInt32LE(1, 1);
    uuid.copy(deleted, 5); deleted.writeInt16LE(-1, 21);
    const simple = Buffer.alloc(7); simple.writeInt8(TraitType.SkeletonData, 0);
    simple.writeInt32LE(17, 1); simple.writeInt16LE(skeleton.byteLength, 5);
    const header = Buffer.alloc(8); header.writeBigInt64LE(23n);
    const bytes = Buffer.concat([header, uuid, deleted, simple, skeleton, Buffer.from([255])]);
    const traits = BulkAvatarTraits.read(paddedView(bytes));
    assert.equal(traits.traitsSequenceNumber, 23n);
    assert.equal(traits.avatarTraitsList[0].avatarTraits[0].type, TraitType.SkeletonData);
    const invalid = Buffer.from(bytes); invalid.writeInt16LE(-2, 8 + 16 + 21);
    assert.throws(() => BulkAvatarTraits.read(paddedView(invalid)), /Invalid/);
});

test('native microphone frames use PCM240 mono samples and native transform ordering', () => {
    const input = fixture.microphone;
    const packet = MicrophoneAudioNoEcho.write({ sequenceNumber: input.sequence, codecName: input.codec,
        isStereo: input.isStereo, audioPosition: input.audioPosition, audioOrientation: input.audioOrientation,
        avatarBoundingBoxCorner: input.avatarBoundingBoxCorner, avatarBoundingBoxScale: input.avatarBoundingBoxScale,
        audioBuffer: Buffer.from(input.pcmHex, 'hex') });
    assert.equal(payload(packet).toString('hex'), input.hex);
    assert.equal(payload(packet).byteLength, 542);
});

test('native mixed stereo audio excludes backing-buffer padding and validates codec bounds', () => {
    const input = fixture.mixedAudio;
    const bytes = Buffer.from(input.hex, 'hex');
    const mixed = MixedAudio.read(paddedView(bytes));
    assert.equal(mixed.sequenceNumber, input.sequence); assert.equal(mixed.codecName, 'pcm');
    assert.equal(mixed.numAudioSamples, 240); assert.equal(mixed.audioBuffer.byteLength, 960);
    assert.equal(Buffer.from(mixed.audioBuffer.buffer, mixed.audioBuffer.byteOffset, mixed.audioBuffer.byteLength).toString('hex'), input.pcmHex);
    const invalid = Buffer.from(bytes); invalid.writeUInt32LE(65535, 2);
    assert.throws(() => MixedAudio.read(paddedView(invalid)), /Truncated/);
    const silent = SilentAudioFrame.read(paddedView(Buffer.from(fixture.silentMixer.hex, 'hex')));
    assert.equal(silent.numSilentSamples, 480); // Mixer currently writes its int32 constant, not client uint16.
});

test('native six-byte quaternion normalization and damaged-sphere projection stay finite', () => {
    for (const entry of fixture.quaternions) {
        const bytes = new Uint8Array(6), data = new DataView(bytes.buffer);
        GLMHelpers.packOrientationQuatToSixBytes(data, 0, entry.input);
        assert.equal(Buffer.from(bytes).toString('hex'), entry.hex);
    }
    const malformed = GLMHelpers.unpackOrientationQuatFromSixBytes(new DataView(new Uint8Array(6).buffer), 0);
    assert.ok(Object.values(malformed).every(Number.isFinite));
    assert.ok(Math.abs(Object.values(malformed).reduce((sum, value) => sum + value * value, 0) - 1) < .000001);
});
