// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { BrowserAudio } from './audio';

function environment(t: TestContext, getUserMedia: () => Promise<MediaStream>, acknowledgeAttachment = true) {
    const sent: unknown[] = [], contexts: Context[] = [], processors: Processor[] = [], transfers: Transferable[][] = [];
    let attachmentPosted!: () => void;
    const attached = new Promise<void>(resolve => { attachmentPosted = resolve; });
    class Context {
        state = 'running'; sampleRate = 48000; destination = {};
        audioWorklet = { addModule: async () => {} };
        constructor() { contexts.push(this); }
        createGain() { return { gain: { value: 1 }, connect: (target: unknown) => target }; }
        createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
        async resume() {} async close() { this.state = 'closed'; }
    }
    class Processor {
        constructor() { processors.push(this); }
        port = {
            onmessage: null as ((event: { data: unknown }) => void) | null,
            postMessage: (message: unknown, transfer: Transferable[] = []) => {
                sent.push(message); transfers.push(transfer);
                const control = message as { type?: string; id?: number };
                if (control.type === 'attach-audio-port') {
                    attachmentPosted();
                    if (acknowledgeAttachment) queueMicrotask(() => this.port.onmessage?.({
                        data: { type: 'audio-port-attached', id: control.id, epoch: 0 },
                    }));
                }
            },
        };
        connect(target: unknown) { return target; } disconnect() {}
    }
    for (const [key, value] of Object.entries({
        window: { AudioContext: Context, isSecureContext: true }, AudioContext: Context, AudioWorkletNode: Processor,
        navigator: { mediaDevices: { getUserMedia } },
    })) {
        const before = Object.getOwnPropertyDescriptor(globalThis, key);
        Object.defineProperty(globalThis, key, { configurable: true, value });
        t.after(() => { if (before) Object.defineProperty(globalThis, key, before); else Reflect.deleteProperty(globalThis, key); });
    }
    return { sent, contexts, transfers, attached, dispatch: (data: unknown) => processors[0].port.onmessage?.({ data }) };
}
function stream() {
    const track = { stopped: false, onended: null as null | (() => void), stop() { this.stopped = true; } };
    return { track, value: { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream };
}

test('playback setup never requests microphone permission and concurrent startup uses one context', async t => {
    let requests = 0;
    const env = environment(t, async () => { requests++; return stream().value; });
    const audio = new BrowserAudio(() => {}, () => {});
    await Promise.all([audio.start(), audio.start()]); assert.equal(requests, 0); assert.equal(env.contexts.length, 1);
    assert.equal(audio.muted, true); await audio.dispose(); assert.equal(env.contexts[0].state, 'closed');
});
test('a permission result arriving after leave cannot reconnect a microphone', async t => {
    const captured = stream(); let resolve!: (value: MediaStream) => void, entered!: () => void;
    const enteredCapture = new Promise<void>(done => { entered = done; });
    environment(t, () => { entered(); return new Promise(done => { resolve = done; }); });
    const audio = new BrowserAudio(() => {}, () => {}), enabling = audio.enableMicrophone();
    await enteredCapture; await audio.dispose(); resolve(captured.value);
    assert.equal(await enabling, false); assert.equal(captured.track.stopped, true); assert.equal(audio.muted, true);
});
test('muting stops the actual capture track and malformed downlink frames are discarded', async t => {
    const captured = stream(), env = environment(t, async () => captured.value);
    const audio = new BrowserAudio(() => {}, () => {});
    assert.equal(await audio.enableMicrophone(), true); assert.equal(audio.muted, false);
    audio.receive(new ArrayBuffer(1920)); assert.equal(audio.stats.receivedFrames, 0);
    audio.receive(new ArrayBuffer(960)); assert.equal(audio.stats.receivedFrames, 1);
    audio.stopMicrophone(); assert.equal(captured.track.stopped, true); assert.equal(audio.muted, true);
    assert.ok(env.sent.some(message => (message as { type?: string }).type === 'mute'));
    await audio.dispose();
});

test('attaching a worker audio port transfers its endpoint without microphone permission or duplicate main PCM', async t => {
    let requests = 0;
    const env = environment(t, async () => { requests++; return stream().value; });
    const channel = new MessageChannel(); t.after(() => { channel.port1.close(); channel.port2.close(); });
    const audio = new BrowserAudio(() => { throw new Error('PCM must bypass the UI after attachment'); }, () => {});
    await audio.attachAudioPort(channel.port1);
    assert.equal(requests, 0); assert.equal(audio.stats.transport, 'worker');
    assert.ok(env.transfers.some(transfer => transfer.length === 1 && transfer[0] === channel.port1));
    audio.receive(new ArrayBuffer(960)); assert.equal(audio.stats.receivedFrames, 0);
    env.dispatch({ type: 'microphone', buffer: new ArrayBuffer(480) });
    env.dispatch({ type: 'playback', frames: 4800, peak: .25, droppedFrames: 2, capturedFrames: 10, receivedFrames: 12 });
    assert.equal(audio.stats.sentFrames, 10); assert.equal(audio.stats.receivedFrames, 12);
    await audio.dispose(); assert.equal(audio.stats.transport, 'main');
    assert.ok(env.sent.some(message => (message as { type?: string }).type === 'detach-audio-port'));
});

test('worker mute immediately stops the device and the next explicit UI unmute uses the acknowledged epoch', async t => {
    const captures = [stream(), stream()]; let requests = 0;
    const env = environment(t, async () => captures[requests++].value);
    const channel = new MessageChannel(); t.after(() => { channel.port1.close(); channel.port2.close(); });
    const audio = new BrowserAudio(() => {}, () => {});
    await audio.attachAudioPort(channel.port1);
    env.dispatch({ type: 'transport-state', epoch: 3, muted: true });
    assert.equal(await audio.enableMicrophone(), true);
    env.dispatch({ type: 'transport-state', epoch: 4, muted: true });
    assert.equal(captures[0].track.stopped, true); assert.equal(audio.muted, true);
    env.dispatch({ type: 'transport-state', epoch: 3, muted: true });
    assert.equal(audio.stats.audioEpoch, 4, 'a delayed old reset cannot roll back the UI epoch');
    assert.equal(await audio.enableMicrophone(), true);
    const unmutes = env.sent.filter(message => {
        const control = message as { type?: string; muted?: boolean }; return control.type === 'mute' && control.muted === false;
    }) as { epoch: number }[];
    assert.deepEqual(unmutes.map(control => control.epoch), [3, 4]);
    await audio.dispose(); assert.equal(captures[1].track.stopped, true);
});

test('a mixer mute arriving during browser permission cannot activate the eventual capture track', async t => {
    const captured = stream(); let resolve!: (value: MediaStream) => void, entered!: () => void;
    const permissionStarted = new Promise<void>(done => { entered = done; });
    const env = environment(t, () => { entered(); return new Promise(done => { resolve = done; }); });
    const channel = new MessageChannel(); t.after(() => { channel.port1.close(); channel.port2.close(); });
    const audio = new BrowserAudio(() => {}, () => {});
    await audio.attachAudioPort(channel.port1); env.dispatch({ type: 'transport-state', epoch: 2, muted: true });
    const enabling = audio.enableMicrophone(); await permissionStarted;
    env.dispatch({ type: 'transport-state', epoch: 3, muted: true }); resolve(captured.value);
    assert.equal(await enabling, false); assert.equal(captured.track.stopped, true); assert.equal(audio.muted, true);
    assert.equal(env.sent.filter(message => (message as { muted?: boolean }).muted === false).length, 0);
    await audio.dispose();
});

test('disposing during port attachment rejects the pending operation and ignores a late worklet acknowledgement', async t => {
    const env = environment(t, async () => stream().value, false), channel = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); });
    const audio = new BrowserAudio(() => {}, () => {});
    const attaching = audio.attachAudioPort(channel.port1);
    const rejected = assert.rejects(attaching, /context closed/i);
    await env.attached; await audio.dispose(); await rejected;
    env.dispatch({ type: 'audio-port-attached', id: 1, epoch: 5 });
    assert.equal(audio.stats.transport, 'main'); assert.equal(env.contexts[0].state, 'closed');
});
