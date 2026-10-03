// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DirectSession } from '../src/direct-session';
import type Node from '../src/protocol/vircadia/domain/networking/Node';
import NodeType from '../src/protocol/vircadia/domain/networking/NodeType';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import ReceivedMessage from '../src/protocol/vircadia/domain/networking/ReceivedMessage';
import PacketType, { type PacketTypeValue } from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';

const fixtures = JSON.parse(readFileSync(new URL('./fixtures/native-avatar-audio.json', import.meta.url), 'utf8'));
const fixture = fixtures.silentMixer;
type Harness = {
    admitted: boolean;
    codec: string;
    receiveMixerControl(message: ReceivedMessage, node: Node | null): void;
    receiveMixedAudio(message: ReceivedMessage, node: Node | null): void;
    receiveSelectedAudioFormat(message: ReceivedMessage, node: Node | null): void;
};
function harness() {
    const frames: ArrayBuffer[] = [], events: unknown[] = [];
    const session = Object.create(DirectSession.prototype) as Harness;
    Object.assign(session, { admitted: true, callbacks: {
        audio(frame: ArrayBuffer) { frames.push(frame); }, event(event: unknown) { events.push(event); },
    } });
    const mixer = { getType: () => NodeType.AudioMixer } as Node;
    return { session, frames, events, mixer };
}
function message(type: PacketTypeValue, body: Uint8Array): ReceivedMessage {
    const packet = NLPacket.create(type), data = packet.getMessageData();
    data.buffer.set(body, data.dataPosition); data.packetSize = data.dataPosition + body.byteLength;
    return new ReceivedMessage(packet);
}

test('actual native mixer silence reaches playback as one stereo zero frame, respecting current mixer/session', () => {
    const { session, frames, events, mixer } = harness();
    const native = Buffer.from(fixture.hex, 'hex');
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, native), mixer);
    assert.equal(frames.length, 1); assert.equal(frames[0].byteLength, 960);
    assert.ok(new Uint8Array(frames[0]).every(sample => sample === 0));
    // Native PCM fallback names an empty codec while preserving the same count.
    const emptyCodec = Buffer.from('020200000000e0010000', 'hex');
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, emptyCodec), mixer);
    assert.equal(frames.length, 2);
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, native), null);
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, native), { getType: () => NodeType.AssetServer } as Node);
    session.admitted = false;
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, native), mixer);
    assert.equal(frames.length, 2); assert.equal(events.length, 0);
});

test('truncated native mixer silence and unsupported sample counts produce bounded errors without playback/page exceptions', () => {
    const { session, frames, events, mixer } = harness(), native = Buffer.from(fixture.hex, 'hex');
    for (let length = 0; length < native.length; length++) {
        assert.doesNotThrow(() => session.receiveMixerControl(message(PacketType.SilentAudioFrame, native.subarray(0, length)), mixer));
    }
    const unsupported = Buffer.from(native); unsupported.writeUInt32LE(240, unsupported.length - 4);
    session.receiveMixerControl(message(PacketType.SilentAudioFrame, unsupported), mixer);
    assert.equal(frames.length, 0); assert.equal(events.length, native.length + 1);
});

test('optional native environment and statistics controls are consumed without synthesizing voice or effect parity', () => {
    const { session, frames, events, mixer } = harness();
    session.receiveMixerControl(message(PacketType.AudioEnvironment, new Uint8Array([0])), mixer);
    const environment = new Uint8Array(9); environment[0] = 1;
    session.receiveMixerControl(message(PacketType.AudioEnvironment, environment), mixer);
    const stats = new Uint8Array(3 + 152); stats[0] = 3; stats[1] = 1;
    session.receiveMixerControl(message(PacketType.AudioStreamStats, stats), mixer);
    assert.equal(events.length, 0); assert.equal(frames.length, 0);
    session.receiveMixerControl(message(PacketType.AudioEnvironment, environment.subarray(0, 8)), mixer);
    session.receiveMixerControl(message(PacketType.AudioStreamStats, stats.subarray(0, stats.length - 1)), mixer);
    assert.equal(events.length, 2); assert.equal(frames.length, 0);
});

test('actual native mixed PCM preserves exact stereo bytes and rejects every truncated frame without page exceptions', () => {
    const { session, frames, events, mixer } = harness();
    const native = Buffer.from(fixtures.mixedAudio.hex, 'hex');
    session.receiveMixedAudio(message(PacketType.MixedAudio, native), mixer);
    assert.equal(frames.length, 1);
    assert.deepEqual(Buffer.from(frames[0]), Buffer.from(fixtures.mixedAudio.pcmHex, 'hex'));
    for (let length = 0; length < native.length; length++) {
        assert.doesNotThrow(() => session.receiveMixedAudio(message(PacketType.MixedAudio, native.subarray(0, length)), mixer));
    }
    assert.equal(frames.length, 1); assert.equal(events.length, native.length);
    session.receiveMixedAudio(message(PacketType.MixedAudio, native), null);
    session.receiveMixedAudio(message(PacketType.MixedAudio, native), { getType: () => NodeType.AssetServer } as Node);
    session.admitted = false;
    session.receiveMixedAudio(message(PacketType.MixedAudio, native), mixer);
    assert.equal(frames.length, 1);
});

test('native codec negotiation accepts exact PCM/empty records and rejects truncation, excess bytes and unsupported codecs', () => {
    const { session, frames, events, mixer } = harness();
    const record = (name: string) => {
        const bytes = Buffer.from(name, 'utf8'), body = Buffer.alloc(4 + bytes.length);
        body.writeUInt32LE(bytes.length); bytes.copy(body, 4); return body;
    };
    for (const body of [record('pcm'), record('')]) {
        session.codec = 'unsupported';
        session.receiveSelectedAudioFormat(message(PacketType.SelectedAudioFormat, body), mixer);
        assert.equal(session.codec, 'pcm');
    }
    const pcm = record('pcm');
    for (let length = 0; length < pcm.length; length++) {
        assert.doesNotThrow(() => session.receiveSelectedAudioFormat(message(PacketType.SelectedAudioFormat, pcm.subarray(0, length)), mixer));
    }
    for (const body of [Buffer.concat([pcm, Buffer.from([0])]), record('opus')]) {
        assert.doesNotThrow(() => session.receiveSelectedAudioFormat(message(PacketType.SelectedAudioFormat, body), mixer));
    }
    assert.equal(events.length, pcm.length + 2); assert.equal(frames.length, 0);
    assert.equal(session.codec, 'pcm', 'A rejected record must not mutate negotiated audio state');
});
