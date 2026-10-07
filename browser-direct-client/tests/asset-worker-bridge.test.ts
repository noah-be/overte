// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MessageChannel } from 'node:worker_threads';
import { once } from 'node:events';
import { answerAssetFetch } from '../src/protocol/asset-worker-bridge';

const generation = '0bba0d0c-3c0a-441a-9d52-b464589e048a';
function request(channel: MessageChannel) {
    return { data: { type: 'overte-atp-fetch', path: 'hub/material.png', generation },
        ports: [channel.port2] as unknown as MessagePort[] };
}

test('concurrent worker asset replies clone an in-flight native buffer without detaching it', async () => {
    const first = new MessageChannel(), second = new MessageChannel();
    const bytes = Uint8Array.from([0, 10, 20, 255]).buffer;
    const sharedNativeResult = Promise.resolve(bytes);
    const replies = [once(first.port1, 'message'), once(second.port1, 'message')];
    try {
        for (const channel of [first, second]) {
            assert.equal(answerAssetFetch(request(channel), (path, current) => {
                assert.equal(path, 'hub/material.png'); assert.equal(current, generation);
                return sharedNativeResult;
            }), true);
        }
        const [[a], [b]] = await Promise.all(replies);
        assert.deepEqual([...new Uint8Array(a.data)], [0, 10, 20, 255]);
        assert.deepEqual([...new Uint8Array(b.data)], [0, 10, 20, 255]);
        assert.equal(bytes.byteLength, 4);
        new Uint8Array(a.data)[0] = 99;
        assert.equal(new Uint8Array(b.data)[0], 0);
        assert.equal(new Uint8Array(bytes)[0], 0);
    } finally { first.port1.close(); first.port2.close(); second.port1.close(); second.port2.close(); }
});

test('a revoked native session returns its error to the worker port', async () => {
    const channel = new MessageChannel();
    const reply = once(channel.port1, 'message');
    try {
        answerAssetFetch(request(channel), async () => { throw new Error('The ATP session has ended.'); });
        const [message] = await reply;
        assert.deepEqual(message, { error: 'The ATP session has ended.' });
    } finally { channel.port1.close(); channel.port2.close(); }
});

test('late native resolution cannot post revoked bytes and releases its tracked port exactly once', async () => {
    const channel = new MessageChannel(); let current = true, settled = 0, fetched = 0;
    let resolve!: (data: ArrayBuffer) => void;
    const native = new Promise<ArrayBuffer>(done => { resolve = done; });
    const received: unknown[] = []; channel.port1.on('message', value => received.push(value));
    try {
        assert.equal(answerAssetFetch(request(channel), async () => { ++fetched; return native; }, {
            isCurrent: () => current, onSettled: () => { ++settled; },
        }), true);
        await new Promise<void>(done => setImmediate(done)); assert.equal(fetched, 1);
        current = false; channel.port2.close();
        const bytes = Uint8Array.of(99).buffer; resolve(bytes);
        await new Promise<void>(done => setImmediate(done));
        assert.deepEqual(received, []); assert.equal(settled, 1); assert.equal(bytes.byteLength, 1);
    } finally { channel.port1.close(); channel.port2.close(); }
});

test('revocation before native dispatch does not spend a native request and still returns its credit', async () => {
    const channel = new MessageChannel(); let fetched = 0, settled = 0;
    try {
        answerAssetFetch(request(channel), async () => { ++fetched; return new ArrayBuffer(0); }, {
            isCurrent: () => false, onSettled: () => { ++settled; },
        });
        await new Promise<void>(done => setImmediate(done));
        assert.equal(fetched, 0); assert.equal(settled, 1);
    } finally { channel.port1.close(); channel.port2.close(); }
});
