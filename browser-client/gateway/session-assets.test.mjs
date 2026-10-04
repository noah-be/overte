// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SessionAssets } from './session-assets.mjs';

const bytes = text => ({ data: Buffer.from(text), type: 'image/png' });
const turn = () => new Promise(resolve => setImmediate(resolve));
function fixture(options = {}) {
    let authority = 'guest-domain|1', calls = [];
    const assets = new SessionAssets({ authority: () => authority,
        load: (url, signal) => new Promise((resolve, reject) => {
            calls.push({ url, signal, resolve, reject });
        }), ...options });
    return { assets, calls, setAuthority: value => { authority = value; } };
}

test('concurrent readers and completed hits share exact bytes only inside one visitor', async () => {
    const a = fixture(), b = fixture();
    const first = a.assets.request('texture'), second = a.assets.request('texture');
    await turn(); assert.equal(a.calls.length, 1); a.calls[0].resolve(bytes('RGBA'));
    const firstValue = await first, secondValue = await second;
    assert.deepEqual(firstValue.data, secondValue.data); assert.equal(firstValue.source, 'download'); assert.equal(secondValue.source, 'shared'); const memoryValue = await a.assets.request('texture'); assert.equal(memoryValue.data.toString(), 'RGBA'); assert.equal(memoryValue.source, 'memory');
    const foreign = b.assets.request('texture'); await turn(); assert.equal(b.calls.length, 1);
    b.calls[0].resolve(bytes('OTHER')); assert.equal((await foreign).data.toString(), 'OTHER');
    assert.deepEqual(a.assets.metrics, { loads: 1, hits: 1, shared: 1, downloadedBytes: 4 });
});
test('cancelling one shared reader preserves another; last-reader cancellation cannot release an active native slot early', async () => {
    const f = fixture({ maximumActive: 1 }); const one = new AbortController(), two = new AbortController();
    const a = f.assets.request('atp:/one', one.signal), b = f.assets.request('atp:/one', two.signal);
    const rejectedA = assert.rejects(a, /cancelled/); await turn(); one.abort(); await rejectedA;
    assert.equal(f.calls[0].signal.aborted, false);
    const rejectedB = assert.rejects(b, /cancelled/); two.abort(); await rejectedB;
    assert.equal(f.calls[0].signal.aborted, true);
    const next = f.assets.request('atp:/two'); await turn(); assert.equal(f.calls.length, 1);
    f.calls[0].resolve(bytes('late native callback')); await turn(); assert.equal(f.calls.length, 2);
    f.calls[1].resolve(bytes('next')); assert.equal((await next).data.toString(), 'next');
    assert.equal(f.assets.metrics.hits, 0); assert.equal(f.assets.entries.size, 1);
});
test('queued work and readers retain fixed caps; cancellation frees only actual queued work', async () => {
    const f = fixture({ maximumActive: 1, maximumQueued: 1, maximumReaders: 2 });
    const first = f.assets.request('one'); const cancellation = new AbortController();
    const second = f.assets.request('two', cancellation.signal); const rejected = assert.rejects(second, /cancelled/);
    await assert.rejects(f.assets.request('one'), /readers/);
    cancellation.abort(); await rejected;
    const third = f.assets.request('three'); await assert.rejects(f.assets.request('four'), /readers/);
    await turn(); assert.equal(f.calls.length, 1);
    f.calls[0].resolve(bytes('one')); await first; await turn(); f.calls[1].resolve(bytes('three')); await third;
    assert.equal(f.assets.readers, 0); assert.equal(f.assets.active, 0);
    const queue = fixture({ maximumActive: 1, maximumQueued: 0 }); const pending = queue.assets.request('one');
    await assert.rejects(queue.assets.request('two'), /queued/); await turn(); queue.calls[0].resolve(bytes('one')); await pending;
});
test('permission revocation rejects all readers, discards late native bytes and resets cache on reapproval', async () => {
    const f = fixture(); const promise = f.assets.request('atp:/private'); const rejection = assert.rejects(promise, /session changed/);
    await turn(); f.setAuthority(null); f.assets.reset(); await rejection;
    f.calls[0].resolve(bytes('private')); await turn(); assert.equal(f.assets.entries.size, 0);
    await assert.rejects(f.assets.request('atp:/private'), /not connected/);
    f.setAuthority('guest-domain|2'); const fresh = f.assets.request('atp:/private'); await turn();
    f.calls[1].resolve(bytes('new revision')); assert.equal((await fresh).data.toString(), 'new revision');
    f.assets.close(); await assert.rejects(f.assets.request('atp:/private'), /not connected/);
    assert.equal(f.assets.bytes, 0);
});
test('authority change between loader completion and release rejects bytes without caching', async () => {
    const f = fixture(); const pending = f.assets.request('texture'); const rejection = assert.rejects(pending, /session changed/);
    await turn(); f.setAuthority('different-world|2'); f.calls[0].resolve(bytes('old')); await rejection;
    assert.equal(f.assets.entries.size, 0);
});
test('LRU byte and entry bounds and short TTL do not retain oversized or expired assets', async () => {
    let now = 0;
    const assets = new SessionAssets({ authority: () => 'one', load: async value => bytes(value), maximumBytes: 6, maximumEntries: 2, ttl: 5, now: () => now });
    await assets.request('aaa'); await assets.request('bbb'); await assets.request('aaa'); await assets.request('ccc');
    assert.equal(assets.bytes, 6); assert.equal(assets.entries.size, 2);
    await assets.request('bbb'); assert.equal(assets.metrics.loads, 4, 'Least recently used entry is downloaded again');
    now = 5; await assets.request('bbb'); assert.equal(assets.metrics.loads, 5, 'Mutable URL is not cached past TTL');
    await assets.request('1234567'); assert.equal(assets.bytes, 6, 'Large legal asset can be served without retention');
    const huge = new SessionAssets({ authority: () => 'one', load: async () => ({data:Buffer.alloc(32*1024*1024+1),type:'image/png'}) });
    await assert.rejects(huge.request('huge'), /oversized/); assert.equal(huge.entries.size, 0);
});
test('synchronous revoke before loader microtask cannot start obsolete native work', async () => {
    const f = fixture(); const pending = f.assets.request('old'); const rejection = assert.rejects(pending, /session changed/);
    f.assets.close(); await rejection; await turn(); assert.equal(f.calls.length, 0); assert.equal(f.assets.active, 0);
});

test('queued readers have their own deadline and cannot start native work after expiry', async () => {
    const f = fixture({ maximumActive: 1, readerTimeout: 20 });
    const first = f.assets.request('uncancellable ATP'); const firstRejected = assert.rejects(first, /timed out/);
    const second = f.assets.request('queued ATP'); const secondRejected = assert.rejects(second, /timed out/);
    await turn(); await Promise.all([firstRejected, secondRejected]);
    assert.equal(f.calls.length, 1); assert.equal(f.assets.queue.length, 0);
    assert.equal(f.assets.active, 1, 'Expired readers do not release a still-running native callback slot');
    f.calls[0].resolve(bytes('late')); await turn(); assert.equal(f.assets.active, 0);
    assert.equal(f.assets.entries.size, 0);
    assert.equal(new SessionAssets({ authority: () => 'guest', load: async () => bytes('') }).readerTimeout, 30000);
});
