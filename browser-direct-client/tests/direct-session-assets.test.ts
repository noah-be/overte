// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DirectSession } from '../src/direct-session';

function deferred<T>() {
    let resolve!: (value: T) => void, reject!: (reason: Error) => void;
    const promise = new Promise<T>((accept, refuse) => { resolve = accept; reject = refuse; });
    return { promise, resolve, reject };
}
type AssetSessionHarness = {
    admitted: boolean;
    generation: string;
    assetRequests: Map<string, Promise<ArrayBuffer>>;
    assetMappings: Map<string, Promise<unknown>>;
    pendingAssets: Map<number, unknown>;
    entities: Map<string, unknown>;
    levels: { clear(): void };
    domain: { disconnect(): void };
    callbacks: { event(value: unknown): void };
    fetchATP(path: string, generation: string): Promise<ArrayBuffer>;
    getATP(path: string, generation: string): Promise<ArrayBuffer>;
    leave(): void;
};
function assetSession(): AssetSessionHarness {
    // Run the actual production methods without creating domain, RTC, browser or
    // microphone resources. Native reply/digest completion is deliberately controlled.
    const session = Object.create(DirectSession.prototype) as AssetSessionHarness;
    Object.assign(session, {
        admitted: true, generation: 'first-session', assetRequests: new Map(), assetMappings: new Map(),
        pendingAssets: new Map(), entities: new Map(), levels: { clear() {} }, domain: { disconnect() {} },
        callbacks: { event() {} },
    });
    return session;
}

test('old asset completion after actual leave cannot delete the newer same-path request or break deduplication', async () => {
    const session = assetSession(), first = deferred<ArrayBuffer>(), second = deferred<ArrayBuffer>();
    const calls: Array<{ path: string; generation: string }> = [];
    session.fetchATP = (path, generation) => {
        calls.push({ path, generation }); return calls.length === 1 ? first.promise : second.promise;
    };
    const oldRead = session.getATP('same/model.fbx', session.generation);
    const oldFailure = assert.rejects(oldRead, /revoked session/);
    session.leave();
    assert.equal(session.admitted, false); assert.equal(session.assetRequests.size, 0);
    session.admitted = true;
    const nextGeneration = session.generation;
    const nextRead = session.getATP('same/model.fbx', nextGeneration);
    const concurrentRead = session.getATP('same/model.fbx', nextGeneration);
    assert.equal(calls.length, 2); assert.equal(calls[1].generation, nextGeneration);
    assert.equal(session.assetRequests.get('same/model.fbx'), second.promise);
    first.reject(new Error('The revoked session ended while its digest was pending.'));
    await oldFailure;
    await Promise.resolve();
    assert.equal(session.assetRequests.get('same/model.fbx'), second.promise,
        'old finally must retain the newer session promise');
    const laterRead = session.getATP('same/model.fbx', nextGeneration);
    assert.equal(calls.length, 2, 'later same-path fetch still shares the new native request');
    const bytes = new Uint8Array([10, 20, 30]).buffer;
    second.resolve(bytes);
    const results = await Promise.all([nextRead, concurrentRead, laterRead]);
    for (const result of results) assert.equal(result, bytes);
    assert.equal(session.assetRequests.size, 0, 'the current completed request releases its own cache entry');
    session.leave();
});

test('revoked asset generation is rejected before looking up a newer session cache entry', async () => {
    const session = assetSession(); let fetched = false;
    session.fetchATP = () => { fetched = true; return Promise.resolve(new ArrayBuffer(1)); };
    const revoked = session.generation;
    session.leave(); session.admitted = true;
    session.assetRequests.set('same/model.fbx', Promise.resolve(new ArrayBuffer(1)));
    await assert.rejects(session.getATP('same/model.fbx', revoked), /session has ended/);
    assert.equal(fetched, false);
    assert.equal(session.assetRequests.size, 1, 'the stale request does not consume or erase new authority');
    session.leave();
});
