// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// These exercise real worklet code with synthetic PCM; they are not microphone evidence.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { MessageChannel } from 'node:worker_threads';

function processor(rate = 48000) {
    const sent: { type: string; buffer?: ArrayBuffer; frames?: number }[] = [];
    let instance: any;
    class Worklet { port = { onmessage: undefined as any, postMessage: (message: any) => sent.push(message) }; }
    runInNewContext(readFileSync(new URL('./audio-worklet.js', import.meta.url), 'utf8'), {
        AudioWorkletProcessor: Worklet, sampleRate: rate, ArrayBuffer, DataView, Float32Array,
        registerProcessor: (_name: string, constructor: new () => unknown) => { instance = new constructor(); },
    });
    const receive = (data: unknown) => instance.port.onmessage({ data });
    const render = (input = new Float32Array(128)) => {
        const outputs = [new Float32Array(128), new Float32Array(128)];
        instance.process([[input]], [outputs]); return outputs;
    };
    return { instance, sent, receive, render };
}
function stereo(value: number, right = value): ArrayBuffer {
    const buffer = new ArrayBuffer(960), view = new DataView(buffer);
    for (let sample = 0; sample < 240; sample++) { view.setInt16(sample * 4, value, true); view.setInt16(sample * 4 + 2, right, true); }
    return buffer;
}

test('48 kHz browser capture produces native 24 kHz 240-sample frames with explicit little-endian PCM', () => {
    const audio = processor(); audio.receive({ type: 'mute', muted: false });
    for (let block = 0; block < 15; block++) audio.render(new Float32Array(128).fill(-.5));
    const frames = audio.sent.filter(frame => frame.type === 'microphone');
    assert.equal(frames.length, 4, '40 ms input produces four native 10 ms network frames');
    for (const frame of frames) {
        assert.equal(frame.buffer?.byteLength, 480);
        const view = new DataView(frame.buffer!);
        assert.equal(view.getInt16(0, true), -16384); assert.equal(view.getInt16(478, true), -16384);
    }
});
test('44.1 kHz devices also produce the exact native sample count', () => {
    const audio = processor(44100); audio.receive({ type: 'mute', muted: false });
    audio.render(new Float32Array(4410).fill(.25));
    assert.equal(audio.sent.filter(frame => frame.type === 'microphone').length, 10);
});
test('muting discards partial capture and prevents retained samples crossing permission boundaries', () => {
    const audio = processor(); audio.receive({ type: 'mute', muted: false });
    audio.render(new Float32Array(128).fill(1)); audio.receive({ type: 'mute', muted: true });
    for (let block = 0; block < 10; block++) audio.render(new Float32Array(128).fill(1));
    assert.equal(audio.sent.length, 0);
    audio.receive({ type: 'mute', muted: false }); audio.render(new Float32Array(480).fill(.25));
    assert.equal(audio.sent.length, 1);
    const view = new DataView(audio.sent[0].buffer!); assert.equal(view.getInt16(0, true), 8192);
});
test('received native mixer PCM reaches both browser channels without channel reversal', () => {
    const audio = processor(); audio.receive({ type: 'pcm', buffer: stereo(8192, -16384) });
    assert.equal(audio.render()[0][0], 0, 'playback waits for a 20 ms jitter cushion');
    audio.receive({ type: 'pcm', buffer: stereo(8192, -16384) });
    const [left, right] = audio.render(); assert.equal(left[0], .25); assert.equal(right[0], -.5);
    assert.equal(left[127], .25); assert.equal(right[127], -.5);
});
test('stalled playback retains at most 100 ms and rejects malformed mixer frames', () => {
    const audio = processor();
    audio.receive({ type: 'pcm', buffer: new ArrayBuffer(1920) }); assert.equal(audio.instance.queue.length, 0);
    for (let frame = 0; frame < 24; frame++) audio.receive({ type: 'pcm', buffer: stereo(8192) });
    assert.equal(audio.instance.queue.length, 10); assert.equal(audio.instance.droppedFrames, 14);
    audio.receive({ type: 'reset' }); assert.equal(audio.instance.queue.length, 0);
    assert.equal(audio.render()[0][0], 0, 'leave/reconnect does not play old domain audio');
});
test('underrun yields silence and reestablishes the jitter cushion', () => {
    const audio = processor(24000);
    audio.receive({ type: 'pcm', buffer: stereo(4096) }); audio.receive({ type: 'pcm', buffer: stereo(4096) });
    for (let block = 0; block < 4; block++) audio.render();
    assert.equal(audio.instance.playing, false); assert.equal(audio.render()[0][0], 0);
    audio.receive({ type: 'pcm', buffer: stereo(4096) }); assert.equal(audio.render()[0][0], 0);
});

async function settlePorts(): Promise<void> {
    await new Promise<void>(resolve => setImmediate(resolve));
    await new Promise<void>(resolve => setImmediate(resolve));
}

test('a real duplex MessagePort transfers exact native capture and mixer frames without main-thread PCM', async t => {
    const audio = processor(), channel = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); });
    const messages: { type: string; buffer?: ArrayBuffer; epoch?: number; muted?: boolean; ticket?: number }[] = [];
    channel.port2.on('message', message => messages.push(message));
    audio.receive({ type: 'attach-audio-port', id: 1, port: channel.port1 });
    channel.port2.postMessage({ type: 'reset', epoch: 7 });
    await settlePorts();
    audio.receive({ type: 'mute', muted: false, epoch: 7 });
    for (let block = 0; block < 15; block++) audio.render(new Float32Array(128).fill(-.5));
    await settlePorts();
    const frames = messages.filter(message => message.type === 'microphone');
    assert.equal(frames.length, 4);
    for (const frame of frames) {
        assert.equal(frame.epoch, 7); assert.equal(frame.buffer?.byteLength, 480);
        const view = new DataView(frame.buffer!);
        assert.equal(view.getInt16(0, true), -16384); assert.equal(view.getInt16(478, true), -16384);
    }
    assert.deepEqual(frames.map(frame => frame.ticket), [1, 2, 3, 4]);
    assert.equal(audio.sent.filter(message => message.type === 'microphone').length, 0);
    audio.receive({ type: 'mute', muted: true, epoch: 7 });
    const first = stereo(8192, -16384), second = stereo(8192, -16384);
    channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket: 1, buffer: first }, [first]);
    channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket: 2, buffer: second }, [second]);
    assert.equal(first.byteLength, 0, 'the actual MessagePort transfers owned PCM');
    await settlePorts();
    const [left, right] = audio.render(); assert.equal(left[0], .25); assert.equal(right[0], -.5);
    for (let block = 0; block < 40; block++) audio.render();
    const summary = audio.sent.find(message => message.type === 'playback') as unknown as {
        capturedFrames: number; receivedFrames: number; buffer?: ArrayBuffer;
    };
    assert.equal(summary.capturedFrames, 4); assert.equal(summary.receivedFrames, 2);
    assert.equal(summary.buffer, undefined, 'only numeric telemetry is delivered to the UI');
});

test('leave and NoisyMute epochs reject queued old unmute, speech and mixer data', async t => {
    const audio = processor(), channel = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); });
    const messages: { type: string; buffer?: ArrayBuffer; epoch?: number }[] = [];
    channel.port2.on('message', message => messages.push(message));
    audio.receive({ type: 'attach-audio-port', id: 1, port: channel.port1 });
    channel.port2.postMessage({ type: 'reset', epoch: 4 }); await settlePorts();
    audio.receive({ type: 'mute', muted: false, epoch: 4 });
    audio.render(new Float32Array(128).fill(1));
    channel.port2.postMessage({ type: 'pcm', epoch: 4, ticket: 1, buffer: stereo(16384) });
    channel.port2.postMessage({ type: 'reset', epoch: 5 }); await settlePorts();
    assert.equal(audio.instance.queue.length, 0); assert.equal(audio.instance.captureOffset, 0);
    // This explicit-unmute message was queued by the old UI/permission epoch.
    audio.receive({ type: 'mute', muted: false, epoch: 4 });
    channel.port2.postMessage({ type: 'pcm', epoch: 4, ticket: 2, buffer: stereo(16384) });
    channel.port2.postMessage({ type: 'reset', epoch: 4 }); await settlePorts();
    audio.render(new Float32Array(480).fill(1)); await settlePorts();
    assert.equal(audio.instance.muted, true); assert.equal(audio.instance.audioEpoch, 5);
    assert.equal(audio.instance.queue.length, 0);
    assert.equal(messages.filter(message => message.type === 'microphone').length, 0);
    audio.receive({ type: 'mute', muted: false, epoch: 5 });
    audio.render(new Float32Array(128).fill(1));
    channel.port2.postMessage({ type: 'mute', muted: true, epoch: 6 }); await settlePorts();
    audio.receive({ type: 'mute', muted: false, epoch: 5 });
    audio.render(new Float32Array(480).fill(1)); await settlePorts();
    assert.equal(messages.filter(message => message.type === 'microphone').length, 0);
    audio.receive({ type: 'mute', muted: false, epoch: 6 });
    audio.render(new Float32Array(480).fill(.25)); await settlePorts();
    const frames = messages.filter(message => message.type === 'microphone');
    assert.equal(frames.length, 1); assert.equal(frames[0].epoch, 6);
    assert.equal(new DataView(frames[0].buffer!).getInt16(0, true), 8192, 'old partial speech was discarded');
});

test('direct transport preserves the 100 ms playout bound and ignores stale replaced ports', async t => {
    const audio = processor(), old = new MessageChannel(), current = new MessageChannel();
    t.after(() => { for (const port of [old.port1, old.port2, current.port1, current.port2]) port.close(); });
    audio.receive({ type: 'attach-audio-port', id: 1, port: old.port1 });
    const staleHandler = old.port1.onmessage!;
    old.port2.postMessage({ type: 'reset', epoch: 90 }); await settlePorts();
    audio.receive({ type: 'attach-audio-port', id: 2, port: current.port1 });
    current.port2.postMessage({ type: 'reset', epoch: 1 }); await settlePorts();
    staleHandler.call(old.port1, { data: { type: 'reset', epoch: 100 } } as Parameters<typeof staleHandler>[0]);
    assert.equal(audio.instance.audioEpoch, 1);
    current.port2.postMessage({ type: 'pcm', epoch: 1, ticket: 1, buffer: new ArrayBuffer(1920) });
    audio.receive({ type: 'pcm', buffer: stereo(8192) });
    for (let index = 0; index < 24; index++) current.port2.postMessage({ type: 'pcm', epoch: 1, ticket: index + 2, buffer: stereo(8192) });
    await settlePorts();
    assert.equal(audio.instance.queue.length, 10); assert.equal(audio.instance.droppedFrames, 14);
    audio.receive({ type: 'detach-audio-port', id: 1 }); assert.equal(audio.instance.transportPort, current.port1);
    audio.receive({ type: 'detach-audio-port', id: 2 });
    assert.equal(audio.instance.transportPort, null); assert.equal(audio.instance.queue.length, 0);
    assert.equal(audio.instance.muted, true);
});

test('a stalled session peer receives at most ten microphone frames and stale ACKs cannot reopen credit', async t => {
    const audio = processor(24000), channel = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); });
    const messages: { type: string; buffer?: ArrayBuffer; epoch?: number; ticket?: number }[] = [];
    channel.port2.on('message', message => messages.push(message));
    audio.receive({ type: 'attach-audio-port', id: 1, port: channel.port1 });
    channel.port2.postMessage({ type: 'reset', epoch: 3 }); await settlePorts();
    audio.receive({ type: 'mute', muted: false, epoch: 3 });
    audio.render(new Float32Array(24000).fill(.5)); await settlePorts();
    assert.equal(messages.filter(message => message.type === 'microphone').length, 10);
    assert.equal(audio.instance.pendingMicrophone.size, 10);
    assert.equal(audio.instance.droppedMicrophoneFrames, 90);
    // UI toggles cannot reopen the same stalled port's finite budget.
    audio.receive({ type: 'mute', muted: true }); audio.receive({ type: 'mute', muted: false, epoch: 3 });
    audio.render(new Float32Array(2400).fill(.5)); await settlePorts();
    assert.equal(messages.filter(message => message.type === 'microphone').length, 10);
    channel.port2.postMessage({ type: 'microphoneAck', epoch: 2, ticket: 1 });
    channel.port2.postMessage({ type: 'microphoneAck', epoch: 3, ticket: 999 }); await settlePorts();
    assert.equal(audio.instance.pendingMicrophone.size, 10);
    channel.port2.postMessage({ type: 'microphoneAck', epoch: 3, ticket: 1 }); await settlePorts();
    audio.render(new Float32Array(240).fill(.25)); await settlePorts();
    const frames = messages.filter(message => message.type === 'microphone');
    assert.equal(frames.length, 11); assert.equal(frames[10].ticket, 11);
    assert.equal(new DataView(frames[10].buffer!).getInt16(0, true), 8192, 'credit resumes with fresh live samples');
    channel.port2.postMessage({ type: 'reset', epoch: 4 }); await settlePorts();
    audio.receive({ type: 'mute', muted: false, epoch: 4 });
    audio.render(new Float32Array(2400).fill(.25)); await settlePorts();
    assert.equal(audio.instance.pendingMicrophone.size, 10);
    channel.port2.postMessage({ type: 'microphoneAck', epoch: 3, ticket: 12 }); await settlePorts();
    assert.equal(audio.instance.pendingMicrophone.size, 10, 'an old-epoch ACK cannot release a new-epoch ticket');
});

test('playback returns exact-epoch ticket credit even when bounded ring drops or malformed PCM is rejected', async t => {
    const audio = processor(), channel = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); });
    const messages: { type: string; epoch?: number; ticket?: number }[] = [];
    channel.port2.on('message', message => messages.push(message));
    audio.receive({ type: 'attach-audio-port', id: 1, port: channel.port1 });
    channel.port2.postMessage({ type: 'reset', epoch: 7 }); await settlePorts();
    for (let ticket = 1; ticket <= 24; ticket++) channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket, buffer: stereo(8192) });
    channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket: 25, buffer: new ArrayBuffer(480) });
    channel.port2.postMessage({ type: 'pcm', epoch: 6, ticket: 26, buffer: stereo(16384) });
    channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket: -1, buffer: stereo(16384) });
    await settlePorts();
    const acknowledgements = messages.filter(message => message.type === 'playbackAck');
    assert.deepEqual(acknowledgements.map(message => message.ticket), Array.from({ length: 25 }, (_, index) => index + 1));
    assert.ok(acknowledgements.every(message => message.epoch === 7));
    assert.equal(audio.instance.queue.length, 10); assert.equal(audio.instance.droppedFrames, 14);
    assert.equal(audio.instance.receivedFrames, 24);
    channel.port2.postMessage({ type: 'pcm', epoch: 7, ticket: 24, buffer: stereo(16384) }); await settlePorts();
    assert.equal(audio.instance.receivedFrames, 24, 'repeated ticket is acknowledged without replaying audio');
});
