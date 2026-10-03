// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { createAvatarEventObserver } from './avatar-event-evidence.mjs';
import { createAvatarReceiveObserver } from './avatar-receive-evidence.mjs';
import { observeAvatarWorker } from './avatar-worker-evidence.mjs';
import { observeAvatarPageMessages } from './avatar-page-message-evidence.mjs';
const nativeID = '10203040-5060-7080-90a0-b0c0d0e0f010';
const q = { x: 0, y: 0, z: 0, w: 1 }, v = { x: 155, y: -97, z: -400 };
function event() { return { type: 'avatars', avatars: [{ id: '{' + nativeID + '}', displayName: 'PRIVATE-NAME', position: { ...v },
    jointNames: ['Hips', 'Head', 'LeftArm', 'RightArm'], jointParents: [-1, 0, 0, 0],
    jointRotations: [{ ...q }, null, { ...q }, { ...q }], jointTranslations: [null, { ...v }, null, null],
    jointDefaultRotations: [{ ...q }, { ...q }, { ...q }, { ...q }],
    jointDefaultTranslations: [{ ...v }, { ...v }, { ...v }, { ...v }], jointDefaultScales: [100, 100, 100, 100] }] }; }

test('raw null/default poses and snapshots are independent of queued source mutation', () => {
    const observer = createAvatarEventObserver(nativeID), input = event(), before = structuredClone(input);
    observer.accept(input); assert.deepEqual(input, before); input.avatars[0].jointRotations[0].x = .5; input.avatars[0].position.x = 156;
    const first = observer.snapshot().first; assert.equal(first.joints.Hips.rotation.x, 0); assert.equal(first.position.x, 155);
    assert.equal(first.joints.Head.rotation, null); assert.equal(first.joints.Head.rotationDefaultFlag, true);
    assert.equal(first.joints.Hips.translationDefaultFlag, true); assert.equal(first.joints.Hips.defaultScale, 100);
    observer.accept(input); const result = observer.snapshot(); assert.equal(result.jointPoseChanges, 1); assert.equal(result.positionChanges, 1);
    for (const sensitive of [nativeID, 'PRIVATE-NAME', 'displayName', 'id"']) assert.ok(!JSON.stringify(result).includes(sensitive));
});

test('ambiguous/non-native events and unlimited samples cannot produce a falsely qualified pose', () => {
    const observer = createAvatarEventObserver(nativeID); observer.accept({ type: 'avatars', avatars: [] });
    const input = event(); input.avatars.push({ ...input.avatars[0] }); observer.accept(input);
    input.avatars.pop(); input.avatars[0].id = 'ffeeddcc-bbaa-9988-7766-554433221100'; observer.accept(input);
    for (let index = 0; index < 70; index++) observer.accept(event());
    const result = observer.snapshot(); assert.equal(result.emptyEvents, 1); assert.equal(result.ambiguousEvents, 1); assert.equal(result.unmatchedEvents, 1);
    assert.equal(result.retained.length, 64); assert.equal(result.sampleEvictions, 6); assert.equal(result.samples, 70);
    result.last.joints.Head.defaultRotation.w = 8; assert.equal(observer.snapshot().last.joints.Head.defaultRotation.w, 1);
});

test('actual Worker post boundary keeps originals/transfer lists/throws and observes only AvatarMixer channels', () => {
    const writes = [], scope = { ArrayBuffer, Uint8Array, DataView, performance, Date,
        postMessage(...values) { if (values[0]?.reject) throw new Error('Original failed'); writes.push(values); return 9; } };
    runInNewContext(`globalThis.overteTestOnlyAvatarEventFactory=(${createAvatarEventObserver.toString()});
        globalThis.overteTestOnlyAvatarReceiveFactory=(${createAvatarReceiveObserver.toString()});
        globalThis.watch=(${observeAvatarWorker.toString()})(${JSON.stringify(nativeID)});`, scope);
    const input = { type: 'event', event: event() }, transfers = [];
    assert.equal(scope.postMessage(input, transfers), 9); assert.equal(writes[0][0], input); assert.equal(writes[0][1], transfers);
    assert.throws(() => scope.postMessage({ reject: true }), /Original failed/);
    const channel = new EventTarget(); channel.readyState = 'open'; scope.watch(channel, 'M'); scope.watch(channel, 'W'); scope.watch(channel, 'W');
    let delivered; channel.addEventListener('message', event => { delivered = event.data; });
    const bytes = new Uint8Array([0, 0, 0, 0x80]); channel.dispatchEvent(new MessageEvent('message', { data: bytes }));
    assert.equal(delivered, bytes); const result = scope.overteAvatarWorkerEvidence(); assert.equal(result.channels.length, 1);
    assert.equal(result.sourceEvents.samples, 1); assert.equal(result.channels[0].received.control, 1); assert.equal(result.observerErrors, 0);
});

test('page Worker event observation leaves actual delivery and SDK-owned acknowledgements unchanged', () => {
    class Worker extends EventTarget { writes = []; postMessage(value) { this.writes.push(value); } }
    const scope = { Worker, performance, Date, URL, location: { href: 'http://127.0.0.1:46106/' } }; scope.window = scope;
    runInNewContext(`window.overteTestOnlyAvatarEventFactory=(${createAvatarEventObserver.toString()});
        (${observeAvatarPageMessages.toString()})(${JSON.stringify(nativeID)});`, scope);
    const worker = new scope.Worker('/assets/session-worker-example.js'), input = { type: 'event', event: event() }, delivered = [];
    worker.addEventListener('message', value => { delivered.push(value.data); worker.postMessage({ type: 'eventAck' }); });
    worker.dispatchEvent(new MessageEvent('message', { data: input }));
    assert.equal(delivered[0], input); assert.equal(worker.writes.length, 1, 'Only the real consumer sends its normal ACK');
    const result = scope.overteAvatarPageMessageEvidence(); assert.match(result.boundary, /not a facade/);
    assert.equal(result.workers[0].samples, 1); assert.equal(result.observerErrors, 0);
    assert.ok(!JSON.stringify(result).includes(nativeID));
});
