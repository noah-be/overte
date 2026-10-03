// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { MessageChannel as NativeChannel, type MessagePort as NativePort } from 'node:worker_threads';
import { assetDispatchMode, ASSET_REQUEST_LIMIT, WorkerAssetRoute, type AssetRouteBinding,
    type AssetRoutingStats } from '../src/protocol/asset-route';
import { PageAssetRoute, prepareAssetWorker, type AssetWorkerBinding } from '../src/protocol/asset-route-registration';
import { answerAssetFetch } from '../src/protocol/asset-worker-bridge';
import { SessionWorkerRuntime, type WorkerSessionCore } from '../src/protocol/session-worker-runtime';
import type { SessionCallbacks } from '../src/session-contract';
import { WorkerDirectSession } from '../src/worker-direct-session';

const FIRST = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const SECOND = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const THIRD = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const SCOPE = 'https://owned-client.invalid/app/';
const tick = () => new Promise<void>(resolve => setTimeout(resolve, 2));
async function eventually(predicate: () => boolean) {
    for (let n = 0; n < 250 && !predicate(); ++n) await tick();
    assert.ok(predicate(), 'the actual transferable port delivered its message');
}
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>(done => { resolve = done; });
    return { promise, resolve };
}

/** Node supplies actual structured cloning and transferred MessagePorts. The
 * small envelope exposes transferred ports through the browser's event.ports
 * field, rather than sharing the original wrapper across simulated realms. */
class BrowserPort extends EventTarget {
    static all = new Set<BrowserPort>();
    private callback: ((event: MessageEvent) => void) | null = null;
    private errorCallback: ((event: MessageEvent) => void) | null = null;
    private started = false;
    private queue: Array<{ data: unknown; ports: NativePort[] }> = [];
    closed = false;
    constructor(readonly raw: NativePort) {
        super(); BrowserPort.all.add(this);
        raw.on('message', value => {
            if (this.closed) return;
            if (this.started) this.deliver(value); else this.queue.push(value);
        });
    }
    get onmessage() { return this.callback; }
    set onmessage(value: ((event: MessageEvent) => void) | null) {
        if (this.callback) this.removeEventListener('message', this.callback as EventListener);
        this.callback = value;
        if (value) { this.addEventListener('message', value as EventListener); this.start(); }
    }
    get onmessageerror() { return this.errorCallback; }
    set onmessageerror(value: ((event: MessageEvent) => void) | null) {
        if (this.errorCallback) this.removeEventListener('messageerror', this.errorCallback as EventListener);
        this.errorCallback = value;
        if (value) this.addEventListener('messageerror', value as EventListener);
    }
    postMessage(data: unknown, transfer: BrowserPort[] = []) {
        this.raw.postMessage({ data, ports: transfer.map(port => port.raw) }, transfer.map(port => port.raw));
    }
    start() {
        this.started = true;
        for (const value of this.queue.splice(0)) queueMicrotask(() => this.deliver(value));
    }
    close() { this.closed = true; this.queue.length = 0; this.raw.close(); BrowserPort.all.delete(this); }
    private deliver(value: { data: unknown; ports: NativePort[] }) {
        if (this.closed) return;
        const event = new MessageEvent('message', { data: value.data });
        // Node's WebIDL constructor accepts only raw Node ports. Expose the
        // already-transferred real endpoints through this browser adapter.
        Object.defineProperty(event, 'ports', { value: value.ports.map(port => new BrowserPort(port)) });
        this.dispatchEvent(event);
    }
}
class BrowserChannel {
    port1: BrowserPort; port2: BrowserPort;
    constructor() { const pair = new NativeChannel(); this.port1 = new BrowserPort(pair.port1); this.port2 = new BrowserPort(pair.port2); }
}
const asPort = (port: BrowserPort) => port as unknown as MessagePort;
function message(port: BrowserPort, type: string, deadline = 500): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
        const listen = (event: Event) => {
            const value = (event as MessageEvent).data;
            if (value?.type !== type) return;
            clearTimeout(timer); port.removeEventListener('message', listen); resolve(value);
        };
        const timer = setTimeout(() => { port.removeEventListener('message', listen); reject(new Error('No bounded routing message.')); }, deadline);
        port.addEventListener('message', listen); port.start();
    });
}
function useChannels(t: TestContext) {
    const original = globalThis.MessageChannel;
    globalThis.MessageChannel = BrowserChannel as unknown as typeof MessageChannel;
    t.after(() => { globalThis.MessageChannel = original; for (const port of [...BrowserPort.all]) port.close(); });
}

type Client = { id: string; type: string; url: string; pageCalls: number; receive?: (data: unknown, port: BrowserPort) => void;
    postMessage(data: unknown, ports: BrowserPort[]): void };
function swFixture(t: TestContext, shortDeadlines = false) {
    useChannels(t);
    const listeners = new Map<string, (event: any) => void>(), clients = new Map<string, Client>();
    const ownedPorts = new Set<BrowserPort>();
    const lifetimes = new Set<Promise<unknown>>();
    let lookup = async (id: string) => clients.get(id);
    const worker = { registration: { scope: SCOPE }, clients: { get: (id: string) => lookup(id), claim: async () => {} },
        skipWaiting: async () => {}, addEventListener: (type: string, listener: (event: any) => void) => listeners.set(type, listener) };
    const timeout = (callback: (...args: any[]) => void, delay: number, ...args: any[]) => {
        const timer = setTimeout(callback, shortDeadlines && delay >= 1000 ? 35 : delay, ...args);
        timers.add(timer); return timer;
    };
    const timers = new Set<ReturnType<typeof setTimeout>>();
    t.after(() => { for (const timer of timers) clearTimeout(timer); });
    class SWChannel extends BrowserChannel {
        constructor() { super(); ownedPorts.add(this.port1); ownedPorts.add(this.port2); }
    }
    const load = () => runInNewContext(readFileSync(new URL('../public/asset-worker.js', import.meta.url), 'utf8'), {
        self: worker, URL, Response, MessageChannel: SWChannel, ArrayBuffer, setTimeout: timeout, clearTimeout, Date,
    });
    load();
    const clone = (data: unknown, ports: BrowserPort[]) => {
        const raw = ports.map(port => port.raw);
        const copy = structuredClone({ data, ports: raw }, { transfer: raw });
        return { data: copy.data, ports: copy.ports.map(port => new BrowserPort(port)) };
    };
    const waitUntil = (operation: Promise<unknown>) => {
        lifetimes.add(operation); void operation.finally(() => lifetimes.delete(operation)).catch(() => {});
    };
    const post = (source: Client | null, data: unknown, ports: BrowserPort[] = []) => {
        const copy = clone(data, ports);
        for (const port of copy.ports) ownedPorts.add(port);
        queueMicrotask(() => listeners.get('message')!({ ...copy, source, waitUntil }));
    };
    const client = (id: string, mode: 'direct' | 'page' = 'direct') => {
        const value: Client = { id, type: 'window', url: `${SCOPE}${mode === 'page' ? '?assetDispatch=page' : ''}`, pageCalls: 0,
            postMessage(data, ports) { ++value.pageCalls; const copy = clone(data, ports); value.receive?.(copy.data, copy.ports[0]); } };
        clients.set(id, value); return value;
    };
    const binding = (source: Client): AssetWorkerBinding => {
        const controller = { state: 'activated', scriptURL: `${SCOPE}asset-worker.js`,
            postMessage: (data: unknown, ports: readonly MessagePort[] = []) => post(source, data, ports as unknown as BrowserPort[]) };
        return { controller: controller as unknown as ServiceWorker, registration: { active: controller, scope: SCOPE } as unknown as ServiceWorkerRegistration };
    };
    const fetch = (id: string, generation = FIRST, path = 'hub/model.fbx') => {
        let response!: Promise<Response>;
        listeners.get('fetch')!({ clientId: id, request: { method: 'GET', url: `${SCOPE}_overte-atp/${generation}/${path}` },
            respondWith(value: Promise<Response>) { response = value; } });
        return response;
    };
    return { clients, client, binding, post, fetch, setLookup: (value: typeof lookup) => { lookup = value; }, restart: () => {
        for (const port of ownedPorts) port.close(); ownedPorts.clear();
        for (const timer of timers) clearTimeout(timer); timers.clear(); listeners.clear(); load();
    } };
}

function nativeFixture(t: TestContext, mode: 'direct' | 'page', getAsset = async (_path: string) => Uint8Array.from([7, 11, 19]).buffer,
    autoStatsAck = true) {
    let callbacks!: SessionCallbacks, admitted = false, generation = FIRST, nextId = 0;
    const requests: string[] = [], output: Array<Record<string, any>> = [];
    let observer: ((message: Record<string, any>) => void) | undefined;
    const core: WorkerSessionCore = {
        get connected() { return admitted; },
        async connect(_endpoint, current) {
            core.leave(); generation = current!; await Promise.resolve(); admitted = true;
            callbacks.event({ type: 'status', state: 'connected' });
        },
        leave() { admitted = false; callbacks.event({ type: 'status', state: 'disconnected' }); },
        async reconnect() {}, sendPose() {}, sendIdentity() {}, sendInteraction() {}, sendAudio() {},
        assetURL(asset) { return asset; }, async resolveAssetSource(asset) { return asset; },
        captureAssetAuthority() { return { generation, assertCurrent() { assert.ok(admitted); } }; },
        assetSessionState() { return { admitted, connected: admitted }; },
        acceptAssetFetch(event, lifecycle) {
            return answerAssetFetch(event, async (path, current) => {
                assert.equal(current, generation); assert.ok(admitted); requests.push(path); return getAsset(path);
            }, lifecycle);
        },
    };
    const runtime = new SessionWorkerRuntime(value => { callbacks = value; return core; }, value => {
        const message = value as Record<string, any>; output.push(message); observer?.(message);
        if (autoStatsAck && message.type === 'assetRouting') queueMicrotask(() => runtime.handle({
            data: { type: 'assetRoutingAck', ticket: message.ticket }, ports: [] }));
        if (message.type === 'event') queueMicrotask(() => runtime.handle({ data: { type: 'eventAck', ticket: message.ticket }, ports: [] }));
    }, THIRD, mode);
    t.after(() => runtime.dispose());
    const rpc = (type: string, binding: Record<string, unknown>, ports: readonly MessagePort[] = []) => {
        const id = ++nextId; runtime.handle({ data: { type, id, ...binding }, ports });
        return new Promise<unknown>((resolve, reject) => {
            void eventually(() => output.some(message => message.type === 'reply' && message.id === id)).then(() => {
                const reply = output.find(message => message.type === 'reply' && message.id === id)!;
                if (reply.ok) resolve(reply.value); else reject(new Error(reply.error));
            }, reject);
        });
    };
    return { runtime, output, requests, core, rpc, observe: (callback: typeof observer) => { observer = callback; },
        prepare: (binding: AssetRouteBinding, port: MessagePort) => rpc('assetRoutePrepare', { ...binding }, [port]),
        connect: (generation: string) => rpc('connect', { generation, endpoint: 'wss://owned-domain.invalid/' }),
        leave: (generation = THIRD) => rpc('leave', { generation }),
        stats: () => output.filter(message => message.type === 'assetRouting').at(-1)?.stats as AssetRoutingStats | undefined };
}

test('direct route bypasses the page and retains original native bytes and shared-buffer ownership', async t => {
    const sw = swFixture(t), tab = sw.client('owned-tab');
    const bytes = Uint8Array.from([0, 10, 255]).buffer, native = nativeFixture(t, 'direct', async () => bytes);
    const page = new PageAssetRoute(new URL(tab.url), 'direct', async () => sw.binding(tab), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    const replies = await Promise.all([sw.fetch(tab.id), sw.fetch(tab.id)]);
    for (const reply of replies) { assert.equal(reply.status, 200); assert.deepEqual([...new Uint8Array(await reply.arrayBuffer())], [0, 10, 255]); }
    assert.equal(bytes.byteLength, 3); assert.equal(tab.pageCalls, 0); assert.equal(native.requests.length, 2);
    await eventually(() => native.stats()?.directRequests === 2 && native.stats()?.pending === 0);
    assert.deepEqual(native.stats(), { mode: 'direct', directReady: true, directRequests: 2, pageRequests: 0,
        rejectedRequests: 0, registrationFailures: 0, revocations: 0, pending: 0 });
    page.cancel(); await native.leave();
    assert.equal((await sw.fetch(tab.id)).status, 502);
});

test('explicit page baseline forwards the same request and uses only its selected route', async t => {
    const sw = swFixture(t), tab = sw.client('owned-page', 'page'), native = nativeFixture(t, 'page');
    tab.receive = (request, port) => native.runtime.handle({ data: { type: 'assetFetch', request }, ports: [asPort(port)] });
    const page = new PageAssetRoute(new URL(tab.url), 'page', async () => sw.binding(tab), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    const reply = await sw.fetch(tab.id); assert.equal(reply.status, 200);
    assert.deepEqual([...new Uint8Array(await reply.arrayBuffer())], [7, 11, 19]); assert.equal(tab.pageCalls, 1);
    await eventually(() => native.stats()?.pageRequests === 1 && native.stats()?.pending === 0);
    assert.equal(native.stats()?.directRequests, 0); assert.equal(native.stats()?.directReady, false);
    assert.equal(assetDispatchMode(new URL(`${SCOPE}?assetDispatch=page`)), 'page');
    assert.equal(assetDispatchMode(new URL(`${SCOPE}?assetDispatch=arbitrary`)), 'direct');
    page.cancel(); await native.leave();
});

test('retirement cancels actual in-flight ports and old completion cannot publish into a fresh same-path session', async t => {
    const sw = swFixture(t), tab = sw.client('owned-retirement'), old = deferred<ArrayBuffer>();
    let number = 0;
    const native = nativeFixture(t, 'direct', async () => ++number === 1 ? old.promise : Uint8Array.of(42).buffer);
    const page = new PageAssetRoute(new URL(tab.url), 'direct', async () => sw.binding(tab), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    const pending = sw.fetch(tab.id); await eventually(() => native.requests.length === 1);
    page.cancel(); await native.leave(SECOND);
    assert.equal((await pending).status, 502);
    await page.prepare(SECOND); await native.connect(SECOND);
    const fresh = await sw.fetch(tab.id, SECOND); assert.deepEqual([...new Uint8Array(await fresh.arrayBuffer())], [42]);
    old.resolve(Uint8Array.of(99).buffer); await tick();
    await eventually(() => native.stats()?.directRequests === 1 && native.stats()?.pending === 0);
    assert.equal((await sw.fetch(tab.id, FIRST)).status, 502); assert.equal(tab.pageCalls, 0);
    page.cancel(); await native.leave();
});

test('an exact generation in another tab cannot borrow the registered native session', async t => {
    const sw = swFixture(t), owner = sw.client('registered-tab'), other = sw.client('other-tab'), native = nativeFixture(t, 'direct');
    const page = new PageAssetRoute(new URL(owner.url), 'direct', async () => sw.binding(owner), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    assert.equal((await sw.fetch(other.id)).status, 502); assert.equal(native.requests.length, 0); assert.equal(other.pageCalls, 0);
    const response = await sw.fetch(owner.id); assert.equal(response.status, 200);
    page.cancel(); await native.leave();
});

test('wrong source kind, origin, actual-client URL, mode and malformed registration cannot replace an active route', async t => {
    const sw = swFixture(t), owner = sw.client('validated-owner'), native = nativeFixture(t, 'direct');
    const page = new PageAssetRoute(new URL(owner.url), 'direct', async () => sw.binding(owner), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    for (const change of [{ type: 'worker' }, { url: 'https://foreign.invalid/app/' }, { url: `${SCOPE}different` }]) {
        const pair = new BrowserChannel(), ack = new BrowserChannel();
        sw.post({ ...owner, ...change }, { type: 'overte-atp-register', generation: SECOND, registration: SECOND, sequence: 100, mode: 'direct' }, [pair.port1, ack.port2]);
        await tick(); assert.equal((await sw.fetch(owner.id)).status, 200);
    }
    for (const change of [{ generation: 'invalid' }, { sequence: -1 }, { mode: 'page' }]) {
        const pair = new BrowserChannel(), ack = new BrowserChannel(), denied = message(ack.port1, 'overte-atp-registered');
        sw.post(owner, { type: 'overte-atp-register', generation: SECOND, registration: SECOND, sequence: 200, mode: 'direct', ...change }, [pair.port1, ack.port2]);
        assert.equal((await denied).ok, false); assert.equal((await sw.fetch(owner.id)).status, 200);
    }
    page.cancel(); await native.leave();
});

test('worker rejects wrong direct identities and an attempted silent page fallback before native getters', async t => {
    const sw = swFixture(t), owner = sw.client('strict-worker'), native = nativeFixture(t, 'direct');
    const page = new PageAssetRoute(new URL(owner.url), 'direct', async () => sw.binding(owner), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    const reply = new BrowserChannel(), denied = new Promise<unknown>(resolve => {
        reply.port1.onmessage = event => resolve(event.data);
    });
    native.runtime.handle({ data: { type: 'assetFetch', request: { type: 'overte-atp-fetch', generation: FIRST, path: 'hub/forged.fbx' } }, ports: [asPort(reply.port2)] });
    assert.match(String((await denied as { error: string }).error), /session has ended|bounded/);
    assert.equal(native.requests.length, 0);
    page.cancel(); await native.leave();
});

test('pending native requests have a real port bound and retirement releases every credit', async t => {
    const sw = swFixture(t), owner = sw.client('bounded-owner'), held = deferred<ArrayBuffer>();
    const native = nativeFixture(t, 'direct', async () => held.promise);
    const page = new PageAssetRoute(new URL(owner.url), 'direct', async () => sw.binding(owner), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    const requests = Array.from({ length: ASSET_REQUEST_LIMIT }, (_, n) => sw.fetch(owner.id, FIRST, `hub/asset-${n}.fbx`));
    await eventually(() => native.requests.length === ASSET_REQUEST_LIMIT);
    assert.equal((await sw.fetch(owner.id, FIRST, 'hub/overflow.fbx')).status, 503);
    assert.equal(native.requests.length, ASSET_REQUEST_LIMIT);
    page.cancel(); await native.leave(SECOND);
    assert.ok((await Promise.all(requests)).every(reply => reply.status === 502));
    held.resolve(Uint8Array.of(1).buffer);
    await page.prepare(SECOND); await native.connect(SECOND);
    assert.equal((await sw.fetch(owner.id, SECOND)).status, 200);
    await eventually(() => native.stats()?.pending === 0 && native.stats()?.directRequests === 1);
    page.cancel(); await native.leave();
});

test('safe diagnostics keep one outstanding update and coalesce until its actual acknowledgment', async t => {
    const sw = swFixture(t), owner = sw.client('slow-diagnostics'), native = nativeFixture(t, 'direct', undefined, false);
    const page = new PageAssetRoute(new URL(owner.url), 'direct', async () => sw.binding(owner), native.prepare);
    await page.prepare(FIRST); await native.connect(FIRST);
    await Promise.all(Array.from({ length: 8 }, () => sw.fetch(owner.id)));
    const messages = native.output.filter(value => value.type === 'assetRouting'); assert.equal(messages.length, 1);
    native.runtime.handle({ data: { type: 'assetRoutingAck', ticket: messages[0].ticket + 1 }, ports: [] });
    assert.equal(native.output.filter(value => value.type === 'assetRouting').length, 1);
    native.runtime.handle({ data: { type: 'assetRoutingAck', ticket: messages[0].ticket }, ports: [] });
    assert.equal(native.output.filter(value => value.type === 'assetRouting').length, 2);
    // The last SW completion may still be in transit when that ACK is handled.
    // A later update needs its own credit, never a second unacknowledged post.
    for (let n = 0; n < 20; ++n) {
        await tick();
        const latest = native.output.filter(value => value.type === 'assetRouting').at(-1)!;
        if (latest.stats.directRequests === 8 && latest.stats.pending === 0) break;
        const before = native.output.filter(value => value.type === 'assetRouting').length;
        native.runtime.handle({ data: { type: 'assetRoutingAck', ticket: latest.ticket }, ports: [] });
        assert.ok(native.output.filter(value => value.type === 'assetRouting').length <= before + 1);
    }
    const stats = native.output.filter(value => value.type === 'assetRouting').at(-1)!.stats;
    assert.equal(stats.directRequests, 8); assert.equal(stats.pending, 0);
    assert.deepEqual(Object.keys(stats).sort(), ['directReady', 'directRequests', 'mode', 'pageRequests', 'pending', 'registrationFailures', 'rejectedRequests', 'revocations']);
    page.cancel(); await native.leave();
});

test('worker retirement without an SW acknowledgment fails within its bounded deadline', async t => {
    useChannels(t);
    const pair = new BrowserChannel(), updates: AssetRoutingStats[] = [];
    const route = new WorkerAssetRoute('direct', () => assert.fail('no asset may arrive'), (_generation, stats) => updates.push(stats), () => {}, 20);
    route.prepare({ generation: FIRST, registration: FIRST, sequence: 1, mode: 'direct' }, asPort(pair.port2));
    await assert.rejects(route.revoke(), /acknowledge/); assert.equal(updates.at(-1)?.directReady, false);
    route.prepare({ generation: SECOND, registration: SECOND, sequence: 2, mode: 'direct' }, asPort(new BrowserChannel().port2));
    route.dispose();
});

test('production preparation awaits the same activating controller and refuses a replacement controller', async t => {
    const saved = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
    const controller = Object.assign(new EventTarget(), { state: 'activating', scriptURL: `${SCOPE}asset-worker.js` });
    const registration = Object.assign(new EventTarget(), { scope: SCOPE, active: controller, installing: null, waiting: null });
    const container = Object.assign(new EventTarget(), { controller, register: async () => registration });
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { serviceWorker: container } });
    t.after(() => { if (saved) Object.defineProperty(globalThis, 'navigator', saved); else Reflect.deleteProperty(globalThis, 'navigator'); });
    let prepared = false;
    const result = prepareAssetWorker(new URL(SCOPE), '/app/').then(value => { prepared = true; return value; });
    await tick(); assert.equal(prepared, false);
    controller.state = 'activated'; controller.dispatchEvent(new Event('statechange'));
    assert.equal((await result).controller, controller);
    const page = new PageAssetRoute(new URL(SCOPE), 'direct', async () => ({ controller: controller as unknown as ServiceWorker,
        registration: registration as unknown as ServiceWorkerRegistration }), async () => assert.fail('wrong current controller'));
    container.controller = Object.assign(new EventTarget(), { state: 'activated', scriptURL: `${SCOPE}asset-worker.js` });
    await assert.rejects(page.prepare(FIRST), /controller changed/);
});

function rawRegistration(t: TestContext, sw: ReturnType<typeof swFixture>, tab: Client,
    generation: string, sequence: number, ready = true, getAsset = async () => Uint8Array.of(23).buffer) {
    const pair = new BrowserChannel(), ack = new BrowserChannel();
    const binding: AssetRouteBinding = { generation, registration: generation, sequence, mode: 'direct' };
    const receiver = new WorkerAssetRoute('direct', event => { answerAssetFetch(event, getAsset); }, () => {}, () => {}, 50);
    if (ready) receiver.prepare(binding, asPort(pair.port2));
    else { pair.port2.onmessage = () => {}; }
    t.after(() => receiver.dispose());
    const result = message(ack.port1, 'overte-atp-registered');
    sw.post(tab, { type: 'overte-atp-register', ...binding }, [pair.port1, ack.port2]);
    return { binding, pair, result, receiver };
}

test('a delayed older registration and stale revoke cannot replace or close the newer actual tab binding', async t => {
    const sw = swFixture(t), tab = sw.client('replacement-owner'), delayed = deferred<Client | undefined>();
    let lookups = 0;
    sw.setLookup(async id => ++lookups === 1 ? delayed.promise : sw.clients.get(id));
    const first = rawRegistration(t, sw, tab, FIRST, 1);
    await tick();
    const fresh = rawRegistration(t, sw, tab, SECOND, 2);
    assert.equal((await fresh.result).ok, true); assert.equal((await first.result).ok, false);
    delayed.resolve(tab); await tick();
    sw.post(tab, { type: 'overte-atp-revoke', ...first.binding }); await tick();
    assert.equal((await sw.fetch(tab.id, FIRST)).status, 502);
    const reply = await sw.fetch(tab.id, SECOND); assert.equal(reply.status, 200);
    assert.deepEqual([...new Uint8Array(await reply.arrayBuffer())], [23]); assert.equal(tab.pageCalls, 0);
    await fresh.receiver.revoke();
});

test('failed replacement has a finite handshake deadline and never falls back to its retired predecessor', async t => {
    const sw = swFixture(t, true), tab = sw.client('failed-replacement');
    const first = rawRegistration(t, sw, tab, FIRST, 1); assert.equal((await first.result).ok, true);
    const failed = rawRegistration(t, sw, tab, SECOND, 2, false);
    assert.equal((await failed.result).ok, false);
    assert.equal((await sw.fetch(tab.id, FIRST)).status, 502); assert.equal((await sw.fetch(tab.id, SECOND)).status, 502);
    const fresh = rawRegistration(t, sw, tab, THIRD, 3); assert.equal((await fresh.result).ok, true);
    failed.pair.port2.postMessage({ type: 'overte-atp-route-ready-ack', ...failed.binding });
    sw.post(tab, { type: 'overte-atp-revoke', ...failed.binding }); await tick();
    assert.equal((await sw.fetch(tab.id, THIRD)).status, 200); assert.equal(tab.pageCalls, 0);
    await fresh.receiver.revoke();
});

test('late page preparation cannot publish an old controller result or revoke a newer registration', async t => {
    const sw = swFixture(t), tab = sw.client('late-page-preparation'), old = deferred<AssetWorkerBinding>();
    const native = nativeFixture(t, 'direct'); let calls = 0;
    const page = new PageAssetRoute(new URL(tab.url), 'direct', async () => ++calls === 1 ? old.promise : sw.binding(tab), native.prepare);
    const stale = page.prepare(FIRST), rejected = assert.rejects(stale, /cancelled/);
    page.cancel(); await page.prepare(SECOND); await native.connect(SECOND);
    old.resolve(sw.binding(tab)); await rejected;
    assert.equal((await sw.fetch(tab.id, SECOND)).status, 200); assert.equal((await sw.fetch(tab.id, FIRST)).status, 502);
    page.cancel(); await native.leave();
});

test('source registration table is bounded and only an actually ended client releases its row', async t => {
    const sw = swFixture(t); const registered = [];
    for (let n = 0; n < 64; ++n) {
        const tab = sw.client(`bounded-tab-${n}`), route = rawRegistration(t, sw, tab, FIRST, 1);
        assert.equal((await route.result).ok, true); registered.push({ tab, route });
    }
    const extra = sw.client('bounded-tab-overflow'), denied = rawRegistration(t, sw, extra, FIRST, 1);
    assert.equal((await denied.result).ok, false);
    assert.equal((await sw.fetch(extra.id)).status, 502);
    sw.clients.delete(registered[0].tab.id);
    const reap = rawRegistration(t, sw, extra, FIRST, 2); assert.equal((await reap.result).ok, false);
    await tick();
    const accepted = rawRegistration(t, sw, extra, FIRST, 3); assert.equal((await accepted.result).ok, true);
    assert.equal((await sw.fetch(extra.id)).status, 200);
    await accepted.receiver.revoke();
    for (const { route } of registered.slice(1)) await route.receiver.revoke();
});

test('total SW reply ports are bounded across owned tabs and release on exact per-tab retirement', async t => {
    const sw = swFixture(t), held = deferred<ArrayBuffer>(), routes = [], pending: Promise<Response>[] = [];
    for (let n = 0; n < 4; ++n) {
        const tab = sw.client(`global-bound-tab-${n}`), route = rawRegistration(t, sw, tab, FIRST, 1, true, async () => held.promise);
        assert.equal((await route.result).ok, true); routes.push({ tab, route });
        for (let m = 0; m < ASSET_REQUEST_LIMIT; ++m) pending.push(sw.fetch(tab.id, FIRST, `hub/held-${m}.fbx`));
    }
    const extra = sw.client('global-bound-overflow'), route = rawRegistration(t, sw, extra, FIRST, 1);
    assert.equal((await route.result).ok, true);
    assert.equal((await sw.fetch(extra.id)).status, 503); assert.equal(extra.pageCalls, 0);
    for (const { route } of routes) await route.receiver.revoke();
    assert.ok((await Promise.all(pending)).every(value => value.status === 502));
    held.resolve(Uint8Array.of(13).buffer);
    assert.equal((await sw.fetch(extra.id)).status, 200); await route.receiver.revoke();
});

test('the first public reconnect after an idle SW context restart closes old authority and awaits a fresh exact route', async t => {
    const sw = swFixture(t), tab = sw.client('idle-context-owner'), native = nativeFixture(t, 'direct', undefined, false);
    class OwnedWorker extends EventTarget {
        terminated = false;
        constructor() {
            super();
            native.observe(data => queueMicrotask(() => {
                if (!this.terminated) this.dispatchEvent(new MessageEvent('message', { data: structuredClone(data) }));
            }));
        }
        postMessage(data: Record<string, unknown>, ports: MessagePort[] = []) {
            const raw = (ports as unknown as BrowserPort[]).map(port => port.raw);
            const clone = structuredClone({ data, ports: raw }, { transfer: raw });
            queueMicrotask(() => {
                if (data.type === 'init') {
                    for (const port of clone.ports) port.close();
                    this.dispatchEvent(new MessageEvent('message', { data: { type: 'ready' } }));
                } else native.runtime.handle({ data: clone.data, ports: clone.ports.map(port => asPort(new BrowserPort(port))) });
            });
        }
        terminate() { this.terminated = true; native.runtime.dispose(); }
    }
    const worker = new OwnedWorker();
    const session = new WorkerDirectSession({ event() {}, audio() {} }, {
        pageURL: tab.url, fingerprint: FIRST, createWorker: () => worker as unknown as Worker,
        createBroker: port => ({ closePeers: async () => {}, close() { port.close(); } }),
        prepareAssets: async () => sw.binding(tab),
    });
    t.after(() => session.dispose());
    await session.connect('wss://owned-domain.invalid/');
    const oldAuthority = session.captureAssetAuthority(); oldAuthority.assertCurrent();
    const initialGeneration = new URL(session.assetURL('atp:hub/model.fbx'), SCOPE).pathname.match(/\/_overte-atp\/([^/]+)/)![1];
    assert.equal((await sw.fetch(tab.id, initialGeneration)).status, 200);
    sw.restart();
    const reconnect = session.reconnect();
    assert.throws(oldAuthority.assertCurrent, /no longer active/); assert.equal(session.connected, false);
    await reconnect;
    assert.ok(native.output.some(message => message.type === 'reply' && message.value?.assetRouteAcknowledged === false));
    session.captureAssetAuthority().assertCurrent();
    const freshGeneration = new URL(session.assetURL('atp:hub/model.fbx'), SCOPE).pathname.match(/\/_overte-atp\/([^/]+)/)![1];
    assert.notEqual(freshGeneration, initialGeneration);
    assert.equal((await sw.fetch(tab.id, freshGeneration)).status, 200);
    await eventually(() => session.assetRouting.directReady && session.assetRouting.directRequests === 1 && session.assetRouting.pending === 0);
    assert.equal(session.assetRouting.pageRequests, 0); assert.equal(tab.pageCalls, 0);
    assert.equal((await sw.fetch(tab.id, initialGeneration)).status, 502);
});
