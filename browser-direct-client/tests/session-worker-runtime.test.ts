// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted regression coverage for worker session and audio boundaries.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageChannel, type MessagePort as NodeMessagePort } from 'node:worker_threads';
import { once } from 'node:events';
import type { SessionCallbacks, SessionEvent } from '../src/session-contract';
import { SessionEventOutbox } from '../src/protocol/session-events';
import { SessionWorkerRuntime, type WorkerSessionCore } from '../src/protocol/session-worker-runtime';
import { DirectSession } from '../src/direct-session';
import FingerprintUtils from '../src/protocol/vircadia/domain/networking/FingerprintUtils';
import Uuid from '../src/protocol/vircadia/domain/shared/Uuid';

const first = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const second = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const third = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const tick = () => new Promise<void>(resolve => setTimeout(resolve, 2));
async function eventually(check: () => boolean) {
    for (let n = 0; n < 100 && !check(); n++) await tick();
    assert.ok(check(), 'the real MessagePort delivered the bounded message');
}
function portMessage(port: NodeMessagePort, type: string): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
        const listener = (message: Record<string, unknown>) => {
            if (message.type !== type) return;
            clearTimeout(timer); port.off('message', listener); resolve(message);
        };
        const timer = setTimeout(() => { port.off('message', listener); reject(new Error(`No ${type} received.`)); }, 500);
        port.on('message', listener);
    });
}
function fixture(notifyLeave = false) {
    let callbacks!: SessionCallbacks;
    let admitted = false;
    const calls: Array<{ type: string; generation?: string; bytes?: number[] }> = [];
    const output: Array<Record<string, unknown>> = [];
    const core: WorkerSessionCore = {
        get connected() { return admitted; },
        async connect(_endpoint, generation) { admitted = true; calls.push({ type: 'connect', generation }); },
        leave() {
            admitted = false; calls.push({ type: 'leave' });
            if (notifyLeave) callbacks.event({ type: 'status', state: 'disconnected', message: 'Disconnected' });
        },
        async reconnect() {}, sendPose() {}, sendIdentity() {}, sendInteraction() {},
        sendAudio(buffer) { calls.push({ type: 'audio', bytes: [...new Uint8Array(buffer)] }); },
        assetURL(asset) { return asset; }, async resolveAssetSource(asset) { return asset; },
        captureAssetAuthority() { return { generation: first, assertCurrent() {} }; },
        assetSessionState() { return { admitted, connected: admitted }; },
        acceptAssetFetch(event) {
            calls.push({ type: 'asset' }); event.ports[0].postMessage({ data: new Uint8Array([1, 2, 3]).buffer });
            event.ports[0].close(); return true;
        },
    };
    const runtime = new SessionWorkerRuntime(value => { callbacks = value; return core; },
        value => output.push(value as Record<string, unknown>), first);
    const command = (data: Record<string, unknown>, ports: readonly MessagePort[] = []) => runtime.handle({ data, ports });
    return { runtime, core, calls, output, command, callbacks: () => callbacks };
}

test('a stalled renderer keeps one posted event, coalesces snapshots, and preserves entity edit order', () => {
    const sent: Array<{ ticket: number; generation: string; event: SessionEvent }> = [];
    const outbox = new SessionEventOutbox(message => sent.push(message));
    const authority = { admitted: true, connected: true };
    outbox.enqueue(first, authority, { type: 'status', state: 'connected' });
    outbox.enqueue(first, authority, { type: 'avatars', avatars: [{ id: 'old', position: { x: 0, y: 0, z: 0 } }] });
    outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'entity', type: 'Box' }] });
    outbox.enqueue(first, authority, { type: 'remove', ids: ['entity'] });
    outbox.enqueue(first, authority, { type: 'avatars', avatars: [] });
    assert.equal(sent.length, 1); assert.equal(outbox.queued, 3);
    outbox.acknowledge(sent[0].ticket + 1); assert.equal(sent.length, 1);
    outbox.acknowledge(sent[0].ticket);
    assert.equal(sent[1].event.type, 'upserts');
    outbox.acknowledge(sent[1].ticket); assert.equal(sent[2].event.type, 'remove');
    outbox.acknowledge(sent[2].ticket); assert.deepEqual(sent[3].event, { type: 'avatars', avatars: [] });
    outbox.acknowledge(sent[3].ticket); assert.equal(outbox.queued, 0);
});

test('page-requested retirement cannot overwrite an already delivered session error with asynchronous disconnect events', async () => {
    const { runtime, command, callbacks, output } = fixture(true);
    try {
        callbacks().event({ type: 'status', state: 'error', message: 'A required service ended.' });
        const error = output.find(value => value.type === 'event')!;
        command({ type: 'leave', id: 1, generation: second });
        command({ type: 'eventAck', ticket: error.ticket });
        await tick();
        assert.deepEqual(output.filter(value => value.type === 'event').map(value => (value.event as SessionEvent).type), ['status']);
        assert.equal(output.some(value => value.type === 'event' && (value.event as { state?: string }).state === 'disconnected'), false);
        assert.ok(output.some(value => value.type === 'reply' && value.id === 1 && value.ok === true));
    } finally { runtime.dispose(); }
});

test('event overflow is bounded and retirement discards queued old generations', () => {
    const sent: Array<{ ticket: number; generation: string }> = [];
    const outbox = new SessionEventOutbox(message => sent.push(message));
    const authority = { admitted: true, connected: true };
    outbox.enqueue(first, authority, { type: 'status', state: 'connected' });
    for (let n = 0; n < SessionEventOutbox.LIMIT; n++) assert.equal(outbox.enqueue(first, authority, { type: 'remove', ids: [String(n)] }), true);
    assert.equal(outbox.enqueue(first, authority, { type: 'remove', ids: ['overflow'] }), false);
    assert.equal(outbox.queued, SessionEventOutbox.LIMIT);
    outbox.retire(); outbox.enqueue(second, authority, { type: 'status', state: 'connecting' });
    assert.equal(sent.length, 1);
    outbox.acknowledge(sent[0].ticket); assert.equal(sent[1].generation, second);
    outbox.acknowledge(sent[0].ticket); assert.equal(sent.length, 2, 'an old acknowledgment cannot acknowledge the new event');
});

test('a stalled renderer receives the latest entity state without empty edits exhausting its bounded queue', () => {
    const delivered: Array<{ ticket: number; event: SessionEvent }> = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    const authority = { admitted: true, connected: true };
    outbox.enqueue(first, authority, { type: 'status', state: 'connected' });
    for (let revision = 0; revision < 100; revision++) {
        assert.equal(outbox.enqueue(first, authority, { type: 'remove', ids: [] }), true);
        assert.equal(outbox.enqueue(first, authority, { type: 'upserts', entities: [] }), true);
        const entities = Array.from({ length: 8 }, (_, id) => ({ id: String(id), type: 'Model',
            modelURL: 'https://assets.invalid/unchanged.fbx', rotation: { x: 0, y: revision, z: 0, w: 1 } }));
        assert.equal(outbox.enqueue(first, authority, { type: 'upserts', entities }), true);
        assert.equal(outbox.enqueue(first, authority, { type: 'avatars', avatars: [] }), true);
        assert.equal(outbox.enqueue(first, authority, { type: 'permissions', permissions: { connect: true, rez: false, edit: false } }), true);
    }
    assert.equal(delivered.length, 1); assert.equal(outbox.queued, 3);
    outbox.acknowledge(delivered[0].ticket);
    const change = delivered[1].event; assert.equal(change.type, 'upserts');
    if (change.type !== 'upserts') throw new Error('The authoritative entity update was lost.');
    assert.equal(change.entities.length, 8);
    for (const entity of change.entities) assert.equal(entity.rotation?.y, 99);
    outbox.acknowledge(delivered[1].ticket); outbox.acknowledge(delivered[2].ticket);
    assert.equal(delivered[3].event.type, 'permissions');
    outbox.acknowledge(delivered[3].ticket); assert.equal(outbox.queued, 0);
});

test('coalescing never crosses entity deletion or lifecycle barriers, including recreation under the same ID', () => {
    const delivered: Array<{ ticket: number; event: SessionEvent }> = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    const authority = { admitted: true, connected: true };
    outbox.enqueue(first, authority, { type: 'status', state: 'connected' });
    outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'A', type: 'Box', alpha: .1 }] });
    outbox.enqueue(first, authority, { type: 'avatars', avatars: [] });
    outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'A', type: 'Box', alpha: .2 }] });
    outbox.enqueue(first, authority, { type: 'remove', ids: ['A'] });
    outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'A', type: 'Model', modelURL: 'https://assets.invalid/new.fbx' }] });
    outbox.enqueue(first, authority, { type: 'status', state: 'error', message: 'The native service ended.' });
    outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'A', type: 'Model', alpha: .8 }] });
    const state = new Map<string, string>(); let removed = false;
    for (let n = 0; n < delivered.length; n++) {
        const { event, ticket } = delivered[n];
        if (event.type === 'upserts') {
            if (event.entities[0].type === 'Box') assert.equal(event.entities[0].alpha, .2);
            if (event.entities[0].modelURL) assert.equal(removed, true, 'recreated assets must follow the removal');
            for (const entity of event.entities) state.set(entity.id, entity.type);
        } else if (event.type === 'remove') { for (const id of event.ids) state.delete(id); removed = true; }
        outbox.acknowledge(ticket);
    }
    assert.deepEqual(delivered.map(value => value.event.type), ['status', 'upserts', 'avatars', 'remove', 'upserts', 'status', 'upserts']);
    assert.equal(state.get('A'), 'Model'); assert.equal(outbox.queued, 0);
});

test('merged entity updates retain their resource bound and retirement releases the previous generation', () => {
    const delivered: Array<{ ticket: number; generation: string; event: SessionEvent }> = [];
    const outbox = new SessionEventOutbox(message => delivered.push(message));
    const authority = { admitted: true, connected: true };
    outbox.enqueue(first, authority, { type: 'status', state: 'connected' });
    const entities = Array.from({ length: SessionEventOutbox.ENTITY_LIMIT }, (_, id) => ({ id: String(id), type: 'Box' }));
    assert.equal(outbox.enqueue(first, authority, { type: 'upserts', entities }), true);
    assert.equal(outbox.enqueue(first, authority, { type: 'upserts', entities: [{ id: 'new', type: 'Box' }] }), false);
    outbox.retire();
    assert.equal(outbox.enqueue(second, authority, { type: 'upserts', entities: [{ id: 'new', type: 'Model' }] }), true);
    outbox.acknowledge(delivered[0].ticket);
    assert.equal(delivered[1].generation, second);
    assert.deepEqual(delivered[1].event, { type: 'upserts', entities: [{ id: 'new', type: 'Model' }] });
    outbox.acknowledge(delivered[1].ticket); assert.equal(outbox.queued, 0);
});

test('connect work queued before leave cannot reopen the retired native session', async () => {
    const { runtime, command, calls, output } = fixture();
    try {
        command({ type: 'connect', id: 1, generation: second, endpoint: 'ws://localhost:46104/' });
        command({ type: 'leave', id: 2, generation: third });
        await tick();
        assert.equal(calls.filter(call => call.type === 'connect').length, 0);
        assert.equal(runtime.core.connected, false);
        assert.ok(output.some(value => value.type === 'reply' && value.id === 1 && value.ok === false));
        command({ type: 'connect', id: 3, generation: third, endpoint: 'ws://localhost:46104/' });
        await eventually(() => calls.some(call => call.type === 'connect'));
        assert.equal(calls.find(call => call.type === 'connect')?.generation, third);
    } finally { runtime.dispose(); }
});

test('ATP MessagePort forwarding requires current native admission and exact session authority', async () => {
    const { runtime, command, calls } = fixture();
    const stale = new MessageChannel(), current = new MessageChannel();
    try {
        command({ type: 'connect', id: 1, generation: second, endpoint: 'ws://localhost:46104/' }); await tick();
        const rejected = once(stale.port1, 'message');
        command({ type: 'assetFetch', request: { generation: first } }, [stale.port2 as unknown as MessagePort]);
        assert.match((await rejected)[0].error, /session has ended/); assert.equal(calls.some(call => call.type === 'asset'), false);
        const accepted = once(current.port1, 'message');
        command({ type: 'assetFetch', request: { generation: second } }, [current.port2 as unknown as MessagePort]);
        assert.deepEqual([...new Uint8Array((await accepted)[0].data)], [1, 2, 3]);
        assert.equal(calls.filter(call => call.type === 'asset').length, 1);
    } finally { runtime.dispose(); stale.port1.close(); stale.port2.close(); current.port1.close(); current.port2.close(); }
});

test('real worker audio ports reject stale unmute and PCM after remote mute, replacement and leave', async () => {
    const { runtime, command, calls, callbacks, output } = fixture();
    const audio = new MessageChannel(), replacement = new MessageChannel();
    const mono = (value: number) => new Uint8Array(480).fill(value).buffer;
    try {
        command({ type: 'connect', id: 1, generation: second, endpoint: 'ws://localhost:46104/' }); await tick();
        const initial = portMessage(audio.port1, 'reset');
        command({ type: 'audioPort' }, [audio.port2 as unknown as MessagePort]);
        const epoch = (await initial).epoch as number;
        audio.port1.postMessage({ type: 'microphone', epoch, ticket: 1, buffer: mono(1) });
        audio.port1.postMessage({ type: 'microphoneState', epoch, muted: false });
        audio.port1.postMessage({ type: 'microphone', epoch, ticket: 2, buffer: mono(2) });
        await eventually(() => calls.filter(call => call.type === 'audio').length === 1);
        assert.equal(calls.find(call => call.type === 'audio')?.bytes?.[0], 2);
        const mute = portMessage(audio.port1, 'mute'); callbacks().event({ type: 'microphoneMuted' });
        const mutedEpoch = (await mute).epoch as number; assert.ok(mutedEpoch > epoch);
        audio.port1.postMessage({ type: 'microphoneState', epoch, muted: false });
        audio.port1.postMessage({ type: 'microphone', epoch, ticket: 3, buffer: mono(3) });
        command({ type: 'audio', generation: second, buffer: mono(4) });
        audio.port1.postMessage({ type: 'microphone', epoch: mutedEpoch, ticket: 5, buffer: mono(5) });
        audio.port1.postMessage({ type: 'microphoneState', epoch: mutedEpoch, muted: false });
        audio.port1.postMessage({ type: 'microphone', epoch: mutedEpoch, ticket: 6, buffer: mono(6) });
        await eventually(() => calls.filter(call => call.type === 'audio').length >= 2);
        assert.deepEqual(calls.filter(call => call.type === 'audio').map(call => call.bytes?.[0]), [2, 6]);
        const reset = portMessage(replacement.port1, 'reset');
        command({ type: 'audioPort' }, [replacement.port2 as unknown as MessagePort]);
        const nextEpoch = (await reset).epoch as number; assert.ok(nextEpoch > mutedEpoch);
        const playback = portMessage(replacement.port1, 'pcm');
        const stereo = new Uint8Array(960).fill(7).buffer; callbacks().audio(stereo);
        const played = await playback; assert.equal(played.type, 'pcm'); assert.equal(played.epoch, nextEpoch);
        assert.equal(stereo.byteLength, 0, 'PCM ownership transfers directly to the worklet port');
        assert.equal(new Uint8Array(played.buffer as ArrayBuffer)[0], 7);
        command({ type: 'leave', id: 2, generation: third });
        replacement.port1.postMessage({ type: 'microphoneState', epoch: nextEpoch, muted: false });
        replacement.port1.postMessage({ type: 'microphone', epoch: nextEpoch, ticket: 8, buffer: mono(8) });
        callbacks().audio(new ArrayBuffer(960)); await tick();
        assert.equal(calls.filter(call => call.type === 'audio').length, 2);
        assert.equal(output.some(value => value.type === 'audio'), false, 'PCM never accumulates in the renderer event queue');
    } finally { runtime.dispose(); audio.port1.close(); audio.port2.close(); replacement.port1.close(); replacement.port2.close(); }
});

test('a stalled AudioWorklet receives at most 100 ms of PCM and stale acknowledgments cannot renew credit', async () => {
    const { runtime, command, callbacks } = fixture();
    const audio = new MessageChannel();
    const received: Array<Record<string, unknown>> = [];
    audio.port1.on('message', message => received.push(message));
    try {
        command({ type: 'connect', id: 1, generation: second, endpoint: 'ws://localhost:46104/' }); await tick();
        const initial = portMessage(audio.port1, 'reset');
        command({ type: 'audioPort' }, [audio.port2 as unknown as MessagePort]);
        const epoch = (await initial).epoch as number;
        for (let n = 0; n < 1000; n++) callbacks().audio(new ArrayBuffer(960));
        await eventually(() => received.filter(value => value.type === 'pcm').length === SessionWorkerRuntime.AUDIO_FRAME_LIMIT);
        assert.equal(received.filter(value => value.type === 'pcm').length, 10);
        const ticket = received.find(value => value.type === 'pcm')!.ticket;
        audio.port1.postMessage({ type: 'playbackAck', ticket, epoch: epoch - 1 });
        audio.port1.postMessage({ type: 'microphoneState', epoch, muted: false });
        const barrier = portMessage(audio.port1, 'microphoneAck');
        audio.port1.postMessage({ type: 'microphone', ticket: 2000, epoch, buffer: new ArrayBuffer(480) }); await barrier;
        callbacks().audio(new ArrayBuffer(960)); await tick();
        assert.equal(received.filter(value => value.type === 'pcm').length, 10);
        audio.port1.postMessage({ type: 'playbackAck', ticket, epoch });
        const nextBarrier = portMessage(audio.port1, 'microphoneAck');
        audio.port1.postMessage({ type: 'microphone', ticket: 2001, epoch, buffer: new ArrayBuffer(480) }); await nextBarrier;
        callbacks().audio(new ArrayBuffer(960));
        await eventually(() => received.filter(value => value.type === 'pcm').length === 11);
        audio.port1.postMessage({ type: 'playbackAck', ticket, epoch });
        const duplicateBarrier = portMessage(audio.port1, 'microphoneAck');
        audio.port1.postMessage({ type: 'microphone', ticket: 2002, epoch, buffer: new ArrayBuffer(480) }); await duplicateBarrier;
        callbacks().audio(new ArrayBuffer(960)); await tick();
        assert.equal(received.filter(value => value.type === 'pcm').length, 11, 'duplicate ACK cannot grant additional credit');
    } finally { runtime.dispose(); audio.port1.close(); audio.port2.close(); }
});

test('worker entity domain links request page navigation without silently replacing core asset authority', () => {
    const session = Object.create(DirectSession.prototype) as DirectSession;
    const navigated: string[] = [];
    let hiddenConnections = 0;
    Object.assign(session, { ready: true, entities: new Map([['link', { id: 'link', href: 'wss://example.invalid/' }]]),
        environment: { navigate: (endpoint: string) => navigated.push(endpoint) },
        connect() { hiddenConnections++; return Promise.resolve(); } });
    session.sendInteraction('link');
    assert.deepEqual(navigated, ['wss://example.invalid/']); assert.equal(hiddenConnections, 0);
});

test('worker fingerprint injection retains the page identifier and rejects a null replacement', () => {
    const previous = FingerprintUtils.getMachineFingerprint();
    const input = new Uuid(first);
    try {
        assert.equal(FingerprintUtils.setMachineFingerprint(input), true);
        assert.equal(FingerprintUtils.getMachineFingerprint().stringify(), first);
        assert.notEqual(FingerprintUtils.getMachineFingerprint(), input);
        assert.equal(FingerprintUtils.setMachineFingerprint(new Uuid()), false);
        assert.equal(FingerprintUtils.getMachineFingerprint().stringify(), first);
    } finally { FingerprintUtils.setMachineFingerprint(previous); }
});

test('PCM received before audio attachment is dropped without posting a renderer backlog', async () => {
    const { runtime, command, callbacks, output } = fixture();
    try {
        command({ type: 'connect', id: 1, generation: second, endpoint: 'ws://localhost:46104/' }); await tick();
        for (let n = 0; n < 1000; n++) callbacks().audio(new ArrayBuffer(960));
        assert.equal(output.some(value => value.type === 'audio'), false);
    } finally { runtime.dispose(); }
});
