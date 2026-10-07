// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { MessageChannel, MessagePort } from 'node:worker_threads';
import { installAssetDispatchEvidence, correlateAssetDispatchEvidence } from './asset-dispatch-evidence.mjs';

const BASE = 1_700_000_000_000;
const SALT = 'PRIVATE-RUN-SALT-0123456789';
const GENERATION = '12345678-1234-4123-8123-123456789abc';
const REQUEST = { type: 'overte-atp-fetch', generation: GENERATION, path: 'PRIVATE/source.json?PRIVATE-QUERY' };
const nativePortPost = MessagePort.prototype.postMessage;
const flush = () => new Promise(resolve => setImmediate(resolve));

function environment(role, options = {}) {
    const target = new EventTarget(), clock = { epoch: BASE, origin: BASE - 10000, wallSkew: 0 };
    class ClockDate extends Date { static now() { return clock.epoch + clock.wallSkew; } }
    const scope = { ArrayBuffer, Uint8Array, TextEncoder, URL, crypto: webcrypto,
        Date: ClockDate, performance: { get timeOrigin() { return clock.origin; }, now: () => clock.epoch - clock.origin },
        addEventListener: target.addEventListener.bind(target), removeEventListener: target.removeEventListener.bind(target),
        dispatchEvent: target.dispatchEvent.bind(target), MessagePort, MessageChannel, location: { href: 'http://127.0.0.1/app/' } };
    let rejectPost = false;
    class Worker extends EventTarget {
        calls = [];
        postMessage(...values) {
            if (rejectPost) throw Error('Original Worker.postMessage failure');
            this.calls.push(values); return 42;
        }
        terminate() { return 'terminated'; }
    }
    class Client {
        calls = [];
        postMessage(...values) {
            if (rejectPost) throw Error('Original Client.postMessage failure');
            this.calls.push(values); return 73;
        }
    }
    class FetchEvent extends Event {
        constructor(url = `http://127.0.0.1/app/_overte-atp/${GENERATION}/${REQUEST.path}`, method = 'GET') {
            super('fetch'); this.request = { url, method }; this.clientId = 'PRIVATE-CLIENT';
        }
        respondWith(value) { this.responsePromise = value; return 91; }
    }
    Object.assign(scope, { Worker, Client, FetchEvent,
        navigator: { serviceWorker: new EventTarget() }, registration: { scope: 'http://127.0.0.1/app/' } });
    scope.options = options; scope.privateSalt = SALT;
    runInNewContext(`globalThis.observer=(${installAssetDispatchEvidence.toString()})(${JSON.stringify(role)},privateSalt,options);`, scope);
    return { scope, clock, observer: scope.observer, rejectPost: () => { rejectPost = true; } };
}

function fixture() {
    const key = createHash('sha256').update('fixture-key').digest('hex');
    const runBinding = createHash('sha256').update('fixture-run').digest('hex');
    const roles = {
        'service-worker': [['swFetch', 0], ['swClientPost', 100], ['swReplyReceive', 910], ['swResponseReady', 915]],
        page: [['pageReceive', 400], ['pageWorkerPost', 450]],
        'session-worker': [['workerReceive', 460], ['workerReplyPost', 900]],
    };
    return Object.entries(roles).map(([role, entries]) => ({ schema: 1, role, available: true, runBinding,
        limits: { maximumEvents: 2048, maximumPendingHashes: 64, maximumPorts: 512, maximumWorkers: 4, maximumWallSkewMs: 10 },
        counters: {}, clock: { status: 'valid' }, records: entries.map(([boundary, elapsed]) => ({
            key, kind: 'json', boundary, epochMs: BASE + elapsed, outcome: boundary === 'swResponseReady' ? 'ok' : null })) }));
}

test('actual transferable ports preserve the production route, native arguments, results and original response promise', async t => {
    const sw = environment('service-worker'), page = environment('page'), worker = environment('session-worker');
    t.after(() => { worker.observer.dispose(); page.observer.dispose(); sw.observer.dispose(); });
    page.clock.origin = BASE - 17000; worker.clock.origin = BASE - 42000;
    let resolveAsset, originalResponse, nativeClientResult, nativeWorkerResult;
    const bytes = Uint8Array.from([17, 29, 43]).buffer;
    const asset = new Promise(resolve => { resolveAsset = resolve; });
    const client = new sw.scope.Client(), ownedWorker = new page.scope.Worker('/assets/session-worker-owned.js');
    const originalClientPost = Object.getPrototypeOf(client).postMessage;
    // Use the real structured-clone/transfer operation that native postMessage
    // performs. The observer's wrappers must pass the same objects/transfer list.
    const clientNativeCalls = [], workerNativeCalls = [];
    const clientBase = Object.getPrototypeOf(client);
    const clientWrapped = clientBase.postMessage;
    // The original methods were captured at installation; adapt their behavior
    // through the captured class instance, rather than replacing test wrappers.
    const clientCalls = client.calls;
    clientCalls.push = function (values) {
        clientNativeCalls.push(values);
        const clone = structuredClone({ data: values[0], port: values[1][0] }, { transfer: values[1] });
        queueMicrotask(() => {
            page.clock.epoch = BASE + 400;
            page.scope.navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: clone.data, ports: [clone.port] }));
        });
        return Array.prototype.push.call(this, values);
    };
    ownedWorker.calls.push = function (values) {
        workerNativeCalls.push(values);
        const clone = structuredClone({ data: values[0], port: values[1][0] }, { transfer: values[1] });
        queueMicrotask(() => {
            worker.clock.epoch = BASE + 460;
            worker.scope.dispatchEvent(new MessageEvent('message', { data: clone.data, ports: [clone.port] }));
        });
        return Array.prototype.push.call(this, values);
    };
    let receivedRequest;
    page.scope.navigator.serviceWorker.addEventListener('message', event => {
        receivedRequest = event.data; page.clock.epoch = BASE + 450;
        nativeWorkerResult = ownedWorker.postMessage({ type: 'assetFetch', request: event.data }, [event.ports[0]]);
    });
    worker.scope.addEventListener('message', event => {
        const port = event.ports[0];
        void Promise.resolve().then(() => asset).then(data => port.postMessage({ data })).finally(() => port.close());
    });
    const event = new sw.scope.FetchEvent();
    sw.scope.addEventListener('fetch', current => {
        originalResponse = (async () => {
            await Promise.resolve(); sw.clock.epoch = BASE + 100;
            const channel = new sw.scope.MessageChannel();
            const data = await new Promise(resolve => {
                channel.port1.onmessage = message => { channel.port1.close(); resolve(message.data.data); };
                nativeClientResult = client.postMessage(REQUEST, [channel.port2]);
            });
            sw.clock.epoch = BASE + 915;
            return new Response(data);
        })();
        assert.equal(current.respondWith(originalResponse), 91);
    });
    sw.scope.dispatchEvent(event);
    await flush();
    assert.equal(nativeClientResult, 73); assert.equal(nativeWorkerResult, 42);
    assert.equal(event.responsePromise, originalResponse);
    assert.equal(clientNativeCalls[0][0], REQUEST); assert.deepEqual(receivedRequest, REQUEST);
    assert.equal(workerNativeCalls[0][0].request, receivedRequest);
    assert.equal(clientWrapped, originalClientPost);
    worker.clock.epoch = BASE + 900; sw.clock.epoch = BASE + 910;
    resolveAsset(bytes);
    const response = await event.responsePromise;
    assert.deepEqual(new Uint8Array(await response.arrayBuffer()), new Uint8Array(bytes));
    await flush();
    const snapshots = await Promise.all([sw.observer.snapshot(), page.observer.snapshot(), worker.observer.snapshot()]);
    const result = correlateAssetDispatchEvidence(snapshots);
    assert.equal(result.status, 'complete'); assert.equal(result.counters.completeRequests, 1);
    assert.equal(result.phases.mainThreadDispatch.meanMs, 300);
    assert.equal(result.phases.pageForward.meanMs, 50);
    assert.equal(result.phases.sessionWorkerDispatch.meanMs, 10);
    assert.equal(result.phases.nativeAssetResolution.meanMs, 440);
    assert.equal(result.phases.directReplyDispatch.meanMs, 10);
    assert.equal(result.phases.responseBuild.meanMs, 5);
    assert.equal(result.phases.totalObserved.meanMs, 915);
    assert.equal(result.phases.mainThreadDispatch.byKind.json.count, 1);
    assert.equal(result.phases.mainThreadDispatch.byKind.image.totalMs, null);
    const output = JSON.stringify({ snapshots, result });
    for (const secret of [SALT, GENERATION, REQUEST.path, 'PRIVATE-CLIENT']) assert.ok(!output.includes(secret));
    assert.ok(!JSON.stringify(result).includes(snapshots[0].records[0].key));
});

test('epoch clocks compare across different time origins; relative-clock subtraction would give the wrong result', () => {
    const result = correlateAssetDispatchEvidence(fixture());
    assert.equal(result.status, 'complete'); assert.equal(result.phases.mainThreadDispatch.totalMs, 300);
    assert.equal(result.crossRealmWallClockCheckBoundMs, 20);
});

test('missing observers, salt bindings and invalid clocks remain unavailable rather than zero', () => {
    for (const mutate of [
        values => values.pop(), values => { values[2].available = false; },
        values => { values[2].runBinding = 'f'.repeat(64); },
        values => { values[2].clock.status = 'invalid'; },
        values => { values[2] = values[1]; },
    ]) {
        const values = fixture(); mutate(values); const result = correlateAssetDispatchEvidence(values);
        assert.equal(result.status, 'unavailable'); assert.equal(result.phases.mainThreadDispatch.available, false);
        assert.equal(result.phases.mainThreadDispatch.totalMs, null); assert.equal(result.phases.mainThreadDispatch.meanMs, null);
    }
});

test('missing and reversed stages are explicit partial evidence and cannot become fast zero-duration samples', () => {
    const missing = fixture(); missing[1].records.shift();
    const partial = correlateAssetDispatchEvidence(missing);
    assert.equal(partial.status, 'partial'); assert.equal(partial.counters.completeRequests, 0);
    assert.equal(partial.phases.mainThreadDispatch.count, 0); assert.equal(partial.phases.mainThreadDispatch.totalMs, null);
    const reversed = fixture(); reversed[1].records[0].epochMs = BASE + 99;
    const invalid = correlateAssetDispatchEvidence(reversed);
    assert.equal(invalid.status, 'partial'); assert.equal(invalid.counters.invalidIntervals, 1);
    assert.equal(invalid.phases.mainThreadDispatch.totalMs, null);
});

test('duplicate same-key requests are excluded instead of order-correlated after rejection or asynchronous replies', () => {
    const values = fixture(); values[0].records.push({ ...values[0].records[0], epochMs: BASE + 1000 });
    const result = correlateAssetDispatchEvidence(values);
    assert.equal(result.status, 'unavailable'); assert.equal(result.counters.ambiguousKeys, 1);
    assert.equal(result.counters.completeRequests, 0); assert.equal(result.phases.mainThreadDispatch.totalMs, null);
});

test('an error response is measured as failure without retaining its text or claiming success', async t => {
    const sw = environment('service-worker'); t.after(() => sw.observer.dispose());
    const event = new sw.scope.FetchEvent(); sw.scope.dispatchEvent(event);
    const original = Promise.resolve(new Response('PRIVATE-ERROR-BODY', { status: 502 }));
    assert.equal(event.respondWith(original), 91); assert.equal(event.responsePromise, original);
    await flush(); const snapshot = await sw.observer.snapshot();
    assert.equal(snapshot.records.find(value => value.boundary === 'swResponseReady').outcome, 'http-error');
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-ERROR-BODY'));
    const values = fixture(); values[0].records.at(-1).outcome = 'http-error';
    assert.equal(correlateAssetDispatchEvidence(values).counters.failedResponses, 1);
});

test('native postMessage exceptions are preserved and explicitly counted without a successful dispatch sample', async t => {
    const page = environment('page'), sw = environment('service-worker');
    t.after(() => { sw.observer.dispose(); page.observer.dispose(); });
    const worker = new page.scope.Worker('/assets/session-worker-real.js'); page.rejectPost();
    assert.throws(() => worker.postMessage({ type: 'assetFetch', request: REQUEST }, []), /Original Worker.postMessage failure/);
    const client = new sw.scope.Client(); sw.rejectPost();
    assert.throws(() => client.postMessage(REQUEST, []), /Original Client.postMessage failure/);
    const [p, s] = await Promise.all([page.observer.snapshot(), sw.observer.snapshot()]);
    assert.equal(p.counters.pagePostFailures, 1); assert.equal(p.records.length, 0);
    assert.equal(s.counters.swPostFailures, 1); assert.equal(s.records.length, 0);
});

test('native transferable-port clone errors retain the original exception and reply data is never modified', async t => {
    const worker = environment('session-worker'); t.after(() => worker.observer.dispose());
    const channel = new MessageChannel(), baseline = new MessageChannel();
    t.after(() => { channel.port1.close(); channel.port2.close(); baseline.port1.close(); baseline.port2.close(); });
    worker.scope.dispatchEvent(new MessageEvent('message', { data: { type: 'assetFetch', request: REQUEST }, ports: [channel.port2] }));
    assert.throws(() => channel.port2.postMessage({ data: () => {} }), error => error.name === 'DataCloneError');
    const data = { error: 'PRIVATE-NATIVE-ERROR' }, received = new Promise(resolve => { channel.port1.onmessage = event => resolve(event.data); });
    const expectedNativeResult = Reflect.apply(nativePortPost, baseline.port2, [data]);
    assert.equal(channel.port2.postMessage(data), expectedNativeResult);
    assert.deepEqual(await received, data);
    const snapshot = await worker.observer.snapshot();
    assert.equal(snapshot.counters.workerReplyFailures, 1); assert.equal(snapshot.counters.replyErrorMarkers, 1);
    assert.equal(snapshot.records.filter(value => value.boundary === 'workerReplyPost').length, 1);
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-NATIVE-ERROR'));
});

test('missing and drifting epoch clocks are explicit while native methods still run', async t => {
    const page = environment('page'); t.after(() => page.observer.dispose());
    const worker = new page.scope.Worker('/assets/session-worker-real.js');
    page.clock.wallSkew = 50;
    assert.equal(worker.postMessage({ type: 'assetFetch', request: REQUEST }), 42);
    let snapshot = await page.observer.snapshot();
    assert.equal(snapshot.clock.status, 'invalid'); assert.equal(snapshot.records[0].epochMs, null);
    page.clock.wallSkew = 0; page.clock.origin = undefined;
    assert.equal(worker.postMessage({ type: 'assetFetch', request: { ...REQUEST, path: 'second.json' } }), 42);
    snapshot = await page.observer.snapshot(); assert.ok(snapshot.clock.unavailableSamples > 0);
    assert.equal(snapshot.records[1].epochMs, null);
});

test('a throwing clock accessor cannot replace an original native postMessage result or exception', async t => {
    const page = environment('page'); t.after(() => page.observer.dispose());
    const worker = new page.scope.Worker('/assets/session-worker-real.js');
    Object.defineProperty(page.scope.performance, 'timeOrigin', { get() { throw Error('PRIVATE-CLOCK-ERROR'); } });
    assert.equal(worker.postMessage({ type: 'assetFetch', request: REQUEST }), 42);
    page.rejectPost();
    assert.throws(() => worker.postMessage({ type: 'assetFetch', request: REQUEST }), /Original Worker.postMessage failure/);
    const snapshot = await page.observer.snapshot();
    assert.equal(snapshot.clock.status, 'unavailable'); assert.equal(snapshot.records[0].epochMs, null);
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-CLOCK-ERROR'));
});

test('event and worker bounds do not change dispatch results; observer losses prevent complete evidence', async t => {
    const page = environment('page', { maximumEvents: 2, maximumWorkers: 1 }); t.after(() => page.observer.dispose());
    const first = new page.scope.Worker('/assets/session-worker-first.js'), second = new page.scope.Worker('/assets/session-worker-second.js');
    for (let index = 0; index < 6; index++) assert.equal(first.postMessage({ type: 'assetFetch', request: { ...REQUEST, path: `${index}.json` } }), 42);
    assert.equal(second.postMessage({ type: 'assetFetch', request: REQUEST }), 42);
    const snapshot = await page.observer.snapshot();
    assert.equal(snapshot.records.length, 2); assert.equal(snapshot.counters.droppedEvents, 4);
    assert.equal(snapshot.counters.workerCapacityDrops, 1);
    const values = fixture(); values[1].counters.droppedEvents = 1;
    assert.equal(correlateAssetDispatchEvidence(values).status, 'partial');
});

test('pending digest limits are explicit and invalid installer capabilities cannot masquerade as a zero-cost route', async t => {
    const page = environment('page', { maximumPendingHashes: 1 }); t.after(() => page.observer.dispose());
    const worker = new page.scope.Worker('/assets/session-worker-real.js');
    for (let index = 0; index < 4; index++) assert.equal(worker.postMessage({ type: 'assetFetch', request: { ...REQUEST, path: `${index}.json` } }), 42);
    const snapshot = await page.observer.snapshot();
    assert.ok(snapshot.counters.hashCapacityDrops > 0); assert.equal(snapshot.counters.peakPendingHashes, 1);
    assert.equal(snapshot.records.length, 4); assert.ok(snapshot.records.some(value => value.key === null));
    const target = { performance, Date, ArrayBuffer, Uint8Array, TextEncoder, crypto: {} };
    runInNewContext(`globalThis.observer=(${installAssetDispatchEvidence.toString()})('session-worker',${JSON.stringify(SALT)});`, target);
    const absent = await target.observer.snapshot();
    assert.equal(absent.available, false); assert.equal(absent.unavailableReason, 'digest-unavailable');
    assert.equal(absent.clock.status, 'unavailable');
});

test('reply-port bounds record observation loss without closing, consuming or changing either real port', async t => {
    const sw = environment('service-worker', { maximumPorts: 1 }); t.after(() => sw.observer.dispose());
    const first = new sw.scope.MessageChannel(), second = new sw.scope.MessageChannel();
    t.after(() => { for (const channel of [first, second]) { channel.port1.close(); channel.port2.close(); } });
    const received = [first, second].map(channel => new Promise(resolve => { channel.port1.onmessage = event => resolve(event.data); }));
    const client = new sw.scope.Client();
    assert.equal(client.postMessage(REQUEST, [first.port2]), 73);
    assert.equal(client.postMessage({ ...REQUEST, path: 'second.json' }, [second.port2]), 73);
    first.port2.postMessage({ data: 'PRIVATE-FIRST' }); second.port2.postMessage({ data: 'PRIVATE-SECOND' });
    assert.deepEqual(await Promise.all(received), [{ data: 'PRIVATE-FIRST' }, { data: 'PRIVATE-SECOND' }]);
    const snapshot = await sw.observer.snapshot();
    assert.equal(snapshot.counters.portCapacityDrops, 1);
    assert.equal(snapshot.records.filter(record => record.boundary === 'swReplyReceive').length, 1);
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-FIRST')); assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-SECOND'));
});

test('page rejection replies are distinguished from a worker response and leave native port semantics intact', async t => {
    const page = environment('page'); t.after(() => page.observer.dispose());
    const channel = new MessageChannel(); t.after(() => { channel.port1.close(); channel.port2.close(); });
    const received = new Promise(resolve => { channel.port1.onmessage = event => resolve(event.data); });
    page.scope.navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: REQUEST, ports: [channel.port2] }));
    channel.port2.postMessage({ error: 'PRIVATE-REVOKED-SESSION' });
    assert.deepEqual(await received, { error: 'PRIVATE-REVOKED-SESSION' });
    const snapshot = await page.observer.snapshot();
    assert.equal(snapshot.counters.pageRejectReplies, 1); assert.equal(snapshot.counters.replyErrorMarkers, 1);
    assert.deepEqual(Array.from(snapshot.records, record => record.boundary), ['pageReceive', 'pageRejectReply']);
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-REVOKED-SESSION'));
});

test('unrelated workers/messages and malformed requests remain unchanged, and dispose restores only owned wrappers', async t => {
    const page = environment('page'); t.after(() => page.observer.dispose());
    const unrelated = new page.scope.Worker('/assets/model-fbx-worker.js');
    const worker = new page.scope.Worker('/assets/session-worker-real.js'), original = Object.getPrototypeOf(worker).postMessage;
    assert.equal(unrelated.postMessage({ type: 'assetFetch', request: REQUEST }), 42);
    const values = [{ type: 'pose', data: 'PRIVATE-POSE' }, { type: 'assetFetch', request: { ...REQUEST, generation: 'malformed' } },
        { type: 'assetFetch', request: { ...REQUEST, path: 'x'.repeat(4097) } }];
    for (const value of values) assert.equal(worker.postMessage(value), 42);
    assert.equal((await page.observer.snapshot()).records.length, 0);
    page.observer.dispose(); assert.equal(worker.postMessage, original);
    assert.equal(worker.postMessage({ type: 'assetFetch', request: REQUEST }), 42);
    const closed = await page.observer.snapshot(); assert.equal(closed.available, false); assert.equal(closed.unavailableReason, 'disposed');
});

test('aggregate output whitelists safe fields and does not publish private correlation keys or arbitrary metadata', () => {
    const values = fixture(); values[0].limits.PRIVATE = 'PRIVATE-LIMIT'; values[0].counters.PRIVATE = 'PRIVATE-COUNT';
    values[0].records[0].PRIVATE = 'PRIVATE-PAYLOAD';
    const result = correlateAssetDispatchEvidence(values), serialized = JSON.stringify(result);
    assert.equal(result.status, 'complete'); assert.ok(!serialized.includes('PRIVATE'));
    assert.ok(!serialized.includes(values[0].records[0].key)); assert.ok(!serialized.includes(values[0].runBinding));
});

test('passive observation does not invoke payload or request accessors beyond native postMessage cloning', async t => {
    const worker = environment('session-worker'); t.after(() => worker.observer.dispose());
    const channel = new MessageChannel(); t.after(() => { channel.port1.close(); channel.port2.close(); });
    worker.scope.dispatchEvent(new MessageEvent('message', { data: { type: 'assetFetch', request: REQUEST }, ports: [channel.port2] }));
    let reads = 0;
    const reply = { get error() { reads++; return 'PRIVATE-GETTER'; } };
    const received = new Promise(resolve => { channel.port1.onmessage = event => resolve(event.data); });
    channel.port2.postMessage(reply); assert.deepEqual(await received, { error: 'PRIVATE-GETTER' });
    assert.equal(reads, 1, 'Only the actual native structured clone reads the accessor');
    const snapshot = await worker.observer.snapshot();
    assert.equal(snapshot.records.find(value => value.boundary === 'workerReplyPost').outcome, 'unavailable');
    assert.ok(!JSON.stringify(snapshot).includes('PRIVATE-GETTER'));
});
