// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { MessageChannel, MessagePort as NodeMessagePort, type Transferable as NodeTransferable } from 'node:worker_threads';
import { WorkerDirectSession, type WorkerSessionEnvironment } from '../src/worker-direct-session';
import type { SessionEvent } from '../src/session-contract';
import type { Pose } from '../src/world-data';

type Message = { type: string; id?: number; generation?: string; [key: string]: unknown };
type Envelope = { data: Message; ports: NodeMessagePort[] };
const endpoint = 'wss://owned-domain.invalid:46105/';
const fingerprint = '55555555-5555-4555-8555-555555555555';
const tick = () => new Promise<void>(resolve => setTimeout(resolve, 3));
async function eventually(predicate: () => boolean): Promise<void> {
    for (let count = 0; count < 200 && !predicate(); ++count) await tick();
    assert.ok(predicate(), 'the bounded worker message was delivered');
}
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>(done => { resolve = done; });
    return { promise, resolve };
}

/** The Worker API is controlled, but its messages and transferred control/audio
 * endpoints use actual MessageChannels rather than shared object references. */
class FakeWorker extends EventTarget {
    readonly pair = new MessageChannel();
    readonly received: Envelope[] = [];
    readonly transferredPorts = new Set<NodeMessagePort>();
    terminated = 0;
    constructor() {
        super();
        this.pair.port2.on('message', (envelope: Envelope) => {
            this.received.push(envelope);
            for (const port of envelope.ports) this.transferredPorts.add(port);
        });
        this.pair.port1.on('message', (envelope: Envelope) => {
            this.dispatchEvent(new MessageEvent('message', {
                data: envelope.data, ports: envelope.ports as unknown as MessagePort[],
            }));
        });
    }
    postMessage(data: Message, transfer: Transferable[] = []): void {
        assert.equal(this.terminated, 0, 'no work may be posted after worker termination');
        const ports = transfer.filter(value => value instanceof NodeMessagePort) as unknown as NodeMessagePort[];
        this.pair.port1.postMessage({ data, ports }, transfer as unknown as NodeTransferable[]);
    }
    send(data: Message): void { this.pair.port2.postMessage({ data, ports: [] }); }
    reply(request: Message, value?: unknown): void {
        this.send({ type: 'reply', id: request.id, generation: request.generation, ok: true, value });
    }
    event(generation: string, ticket: number, event: SessionEvent, admitted = true, connected = true): void {
        this.send({ type: 'event', generation, ticket, authority: { admitted, connected }, event });
    }
    messages(type: string): Message[] { return this.received.filter(value => value.data.type === type).map(value => value.data); }
    async message(type: string, index = 0): Promise<Message> {
        await eventually(() => this.messages(type).length > index);
        return this.messages(type)[index];
    }
    terminate(): void {
        if (this.terminated) return;
        this.terminated = 1;
        for (const port of this.transferredPorts) port.close();
        this.pair.port1.close(); this.pair.port2.close();
    }
}

class DeferredBroker {
    readonly resets: ReturnType<typeof deferred<void>>[] = [];
    closed = 0;
    constructor(readonly port: MessagePort) {}
    closePeers(): Promise<void> {
        const reset = deferred<void>(); this.resets.push(reset); return reset.promise;
    }
    close(): void { ++this.closed; this.port.close(); this.resolveAll(); }
    resolveAll(): void { for (const reset of this.resets) reset.resolve(); }
}

function fixture(t: TestContext, overrides: WorkerSessionEnvironment = {}) {
    const worker = new FakeWorker(), events: SessionEvent[] = [], audio: ArrayBuffer[] = [];
    let broker!: DeferredBroker, preparations = 0;
    const session = new WorkerDirectSession({ event: event => events.push(event), audio: frame => audio.push(frame) }, {
        pageURL: 'https://owned-client.invalid/app/', fingerprint,
        // These facade tests control the native worker, so its routing RPC is
        // controlled too. Actual SW/port routing is exercised separately.
        createAssetRoute: () => ({ prepare: async () => {}, cancel() {} }),
        prepareAssets: () => { ++preparations; return Promise.resolve(); }, ...overrides,
        createWorker: () => worker as unknown as Worker,
        createBroker: port => { broker = new DeferredBroker(port); return broker; },
    });
    t.after(() => { session.dispose(); broker.resolveAll(); worker.terminate(); });
    return { session, worker, broker, events, audio, preparations: () => preparations };
}

type Fixture = ReturnType<typeof fixture>;
async function join(value: Fixture) {
    const { session, worker, broker } = value;
    const init = await worker.message('init');
    assert.equal(worker.received.find(value => value.data === init)?.ports.length, 1,
        'the broker control endpoint is transferred during initialization');
    worker.send({ type: 'ready' });
    const connected = session.connect(endpoint);
    const leave = await worker.message('leave');
    broker.resets[0].resolve(); worker.reply(leave);
    const request = await worker.message('connect');
    worker.reply(request); await connected;
    worker.event(request.generation!, 1, { type: 'status', state: 'connected', endpoint });
    await eventually(() => session.connected);
    return { generation: request.generation!, request };
}
function pose(value: number): Pose {
    return { position: { x: value, y: 2, z: 3 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, velocity: { x: 0, y: 0, z: 0 } };
}

test('leave synchronously revokes ATP authority and stale replies/events cannot restore it', async t => {
    const value = fixture(t), { session, worker, events } = value;
    const { generation } = await join(value);
    const authority = session.captureAssetAuthority();
    authority.assertCurrent(); assert.match(session.assetURL('atp:models/owned.fbx'), new RegExp(generation));
    const mapping = session.resolveAssetSource('atp:models/owned.fbx');
    const rejected = assert.rejects(mapping, /session has ended/);
    const oldRequest = await worker.message('resolveAsset');
    session.leave();
    assert.equal(session.connected, false);
    assert.throws(authority.assertCurrent, /no longer active/);
    assert.throws(() => session.assetURL('atp:models/owned.fbx'), /active domain session/);
    await rejected;
    const visibleEvents = events.length;
    worker.reply(oldRequest, 'https://stale.invalid/owned.fbx');
    worker.event(generation, 41, { type: 'status', state: 'connected', endpoint });
    await eventually(() => worker.messages('eventAck').some(message => message.ticket === 41));
    assert.equal(events.length, visibleEvents, 'the stale event releases its worker outbox ticket without reaching the renderer');
    assert.equal(session.connected, false);
    assert.throws(authority.assertCurrent, /no longer active/);
    assert.throws(() => session.assetURL('atp:models/owned.fbx'), /active domain session/);
});

test('reconnect waits for the real reset and core leave acknowledgments; old-generation replies do not unblock it', async t => {
    const value = fixture(t), { session, worker, broker } = value;
    const { generation } = await join(value);
    const reconnect = session.reconnect();
    const leave = await worker.message('leave', 1);
    assert.equal(session.connected, false);
    broker.resets[1].resolve(); await tick();
    assert.equal(worker.messages('connect').length, 1, 'peer reset alone cannot begin the next native session');
    worker.send({ type: 'reply', id: leave.id, generation, ok: true }); await tick();
    assert.equal(worker.messages('connect').length, 1, 'the previous generation cannot acknowledge the current leave');
    worker.reply(leave);
    const next = await worker.message('connect', 1);
    assert.equal(next.endpoint, endpoint); assert.notEqual(next.generation, generation);
    worker.reply(next); await reconnect;
    assert.equal(value.preparations(), 1, 'asset bootstrap is shared rather than repeated on reconnect');
    const authority = session.captureAssetAuthority();
    assert.throws(authority.assertCurrent, /no longer active/, 'a connect RPC result alone does not grant ATP access');
    worker.event(next.generation!, 42, { type: 'status', state: 'connected', endpoint });
    await eventually(() => session.connected); authority.assertCurrent();
});

test('pose commands coalesce to one outstanding frame and ignore stale sequence or generation acknowledgments', async t => {
    const value = fixture(t), { session, worker } = value;
    const { generation } = await join(value);
    session.sendPose(pose(0));
    for (let index = 1; index <= 1000; ++index) session.sendPose(pose(index));
    const first = await worker.message('pose'); await tick();
    assert.equal(worker.messages('pose').length, 1);
    assert.deepEqual(first.pose, pose(0));
    worker.send({ type: 'poseAck', generation, sequence: Number(first.sequence) + 1 });
    worker.send({ type: 'poseAck', generation: 'old-generation', sequence: first.sequence });
    await tick(); assert.equal(worker.messages('pose').length, 1);
    worker.send({ type: 'poseAck', generation, sequence: first.sequence });
    const latest = await worker.message('pose', 1);
    assert.deepEqual(latest.pose, pose(1000)); assert.notEqual(latest.sequence, first.sequence);
    session.sendPose(pose(1001));
    worker.send({ type: 'poseAck', generation, sequence: first.sequence });
    await tick(); assert.equal(worker.messages('pose').length, 2);
    session.leave(); session.sendPose(pose(2000));
    const fresh = await worker.message('pose', 2);
    assert.deepEqual(fresh.pose, pose(2000)); assert.notEqual(fresh.generation, generation);
    worker.send({ type: 'poseAck', generation, sequence: latest.sequence });
    await tick(); assert.equal(worker.messages('pose').length, 3, 'the previous queued pose was cleared by leave');
});

test('dispose cancels pending RPC and closes owned worker/control/audio endpoints', async t => {
    const value = fixture(t), { session, worker, broker } = value;
    await join(value);
    const mapping = session.resolveAssetSource('atp:models/owned.fbx');
    const rejected = assert.rejects(mapping, /session has ended|worker has ended/);
    await worker.message('resolveAsset');
    const audio = session.createAudioPort() as unknown as NodeMessagePort;
    t.after(() => audio.close());
    await worker.message('audioPort');
    let audioClosed = false, controlClosed = false;
    audio.once('close', () => { audioClosed = true; });
    (broker.port as unknown as NodeMessagePort).once('close', () => { controlClosed = true; });
    session.dispose(); await rejected;
    await eventually(() => audioClosed && controlClosed);
    assert.equal(broker.closed, 1); assert.equal(worker.terminated, 1);
    assert.equal(session.connected, false);
    assert.throws(() => session.createAudioPort(), /worker has ended/);
    assert.throws(() => session.assetURL('atp:models/owned.fbx'), /active domain session/);
    session.sendPose(pose(4)); session.sendInteraction('owned-entity');
    session.sendIdentity({ displayName: 'Owned visitor', skeletonModelURL: '', scale: 1 });
    session.sendAudio(new ArrayBuffer(480)); session.leave(); session.dispose();
    assert.equal(broker.closed, 1, 'final disposal is idempotent');
});

test('persisted main-realm fingerprint and actual transferred control port reach worker initialization', async t => {
    const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    const saved = '77777777-7777-4777-8777-777777777777';
    let writes = 0;
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
        getItem(key: string) { assert.equal(key, 'mfp'); return saved; },
        setItem() { ++writes; },
    } });
    t.after(() => {
        if (original) Object.defineProperty(globalThis, 'localStorage', original);
        else Reflect.deleteProperty(globalThis, 'localStorage');
    });
    const { worker, broker } = fixture(t, { fingerprint: undefined });
    const init = await worker.message('init');
    assert.equal(init.fingerprint, saved); assert.equal(writes, 0);
    assert.equal(init.pageURL, 'https://owned-client.invalid/app/');
    const control = worker.received.find(value => value.data === init)!.ports[0];
    const delivered = new Promise<string>(resolve => control.once('message', resolve));
    broker.port.postMessage('owned control endpoint');
    assert.equal(await delivered, 'owned control endpoint', 'initialization transferred a working native MessagePort');
});

test('entity navigation uses the public page-owned leave/reset boundary and stale navigation is only acknowledged', async t => {
    const value = fixture(t), { session, worker, broker, events } = value;
    const { generation } = await join(value);
    const destination = 'wss://owned-next-domain.invalid:46105/';
    const authority = session.captureAssetAuthority();
    worker.event(generation, 81, { type: 'navigate', endpoint: destination });
    const leave = await worker.message('leave', 1);
    assert.equal(session.connected, false); assert.throws(authority.assertCurrent, /no longer active/);
    await eventually(() => worker.messages('eventAck').some(message => message.ticket === 81));
    assert.equal(worker.messages('connect').length, 1);
    worker.reply(leave); await tick();
    assert.equal(worker.messages('connect').length, 1, 'the navigation waits for peer reset as well as core leave');
    broker.resets[1].resolve();
    const next = await worker.message('connect', 1);
    assert.equal(next.endpoint, destination); assert.notEqual(next.generation, generation);
    worker.reply(next); worker.event(next.generation!, 82, { type: 'status', state: 'connected', endpoint: destination });
    await eventually(() => session.connected);
    const resets = broker.resets.length;
    worker.event(generation, 83, { type: 'navigate', endpoint: 'wss://stale.invalid/' });
    await eventually(() => worker.messages('eventAck').some(message => message.ticket === 83));
    assert.equal(broker.resets.length, resets); assert.equal(worker.messages('connect').length, 2);
    assert.equal(events.some(event => event.type === 'navigate'), false, 'domain links are handled by the facade rather than passed to rendering');
});

test('terminal core failure after admission cancels ATP work and ends the owned worker instead of awaiting a dead leave RPC', async t => {
    const value = fixture(t), { session, worker, broker, events } = value;
    const { generation } = await join(value);
    const authority = session.captureAssetAuthority();
    const mapping = session.resolveAssetSource('atp:models/owned.fbx');
    const rejected = assert.rejects(mapping, /session has ended|worker has ended/);
    await worker.message('resolveAsset');
    worker.send({ type: 'fatal', terminal: true, generation,
        message: 'The native browser worker failed. Reload the page.' });
    await eventually(() => worker.terminated === 1); await rejected;
    assert.equal(broker.closed, 1); assert.equal(session.connected, false);
    assert.throws(authority.assertCurrent, /no longer active/);
    assert.throws(() => session.assetURL('atp:models/owned.fbx'), /active domain session/);
    await assert.rejects(session.connect(endpoint), /reload the page/i);
    await assert.rejects(session.reconnect(), /reload the page/i);
    assert.ok(events.some(event => event.type === 'error' && /reload the page/i.test(event.message)));
});

test('a true Worker error revokes current authority, cancels pending RPC and requires reload', async t => {
    const value = fixture(t), { session, worker, broker } = value;
    await join(value);
    const authority = session.captureAssetAuthority();
    const mapping = session.resolveAssetSource('atp:models/owned.fbx');
    const rejected = assert.rejects(mapping, /session has ended|worker has ended/);
    await worker.message('resolveAsset');
    worker.dispatchEvent(new Event('error'));
    assert.equal(worker.terminated, 1); assert.equal(broker.closed, 1);
    assert.equal(session.connected, false); assert.throws(authority.assertCurrent, /no longer active/);
    await rejected;
    await assert.rejects(session.connect(endpoint), /reload the page/i);
});

test('terminal bootstrap failure is owned by the Worker even after connect advances the session generation', async t => {
    const { session, worker, broker, events } = fixture(t);
    const init = await worker.message('init');
    const connection = session.connect(endpoint);
    const rejected = assert.rejects(connection, /worker|reload|session has ended/i);
    const leave = await worker.message('leave');
    assert.notEqual(leave.generation, init.generation);
    worker.send({ type: 'fatal', terminal: true, generation: init.generation,
        message: 'The native browser worker failed during bootstrap. Reload the page.' });
    await eventually(() => worker.terminated === 1); await rejected;
    assert.equal(broker.closed, 1); assert.equal(session.connected, false);
    await assert.rejects(session.connect(endpoint), /reload the page/i);
    assert.ok(events.some(event => event.type === 'error' && /bootstrap/.test(event.message)),
        'the initialization error remains visible instead of becoming a later readiness timeout');
});

test('recoverable renderer overflow retires its session but keeps a functioning worker for an acknowledged reconnect', async t => {
    const value = fixture(t), { session, worker, broker } = value;
    const { generation } = await join(value);
    const authority = session.captureAssetAuthority();
    worker.send({ type: 'fatal', generation,
        message: 'The renderer stopped accepting bounded session updates. Reconnect to continue.' });
    const failedLeave = await worker.message('leave', 1);
    assert.equal(session.connected, false); assert.throws(authority.assertCurrent, /no longer active/);
    assert.equal(worker.terminated, 0); assert.equal(broker.closed, 0);
    broker.resets[1].resolve(); worker.reply(failedLeave); await tick();
    const reconnect = session.reconnect();
    const leave = await worker.message('leave', 2);
    worker.reply(leave); await tick();
    assert.equal(worker.messages('connect').length, 1, 'core leave alone does not bypass peer reset on recovery');
    broker.resets[2].resolve();
    const next = await worker.message('connect', 1);
    assert.notEqual(next.generation, generation);
    worker.reply(next); await reconnect;
    worker.event(next.generation!, 91, { type: 'status', state: 'connected', endpoint });
    await eventually(() => session.connected);
    session.captureAssetAuthority().assertCurrent();
    assert.equal(worker.terminated, 0); assert.equal(broker.closed, 0);
});

test('a failed asset worker preparation is retried freshly on reconnect', async t => {
    let preparations = 0;
    const value = fixture(t, { prepareAssets: async () => {
        if (++preparations === 1) throw new Error('The owned SW activation timed out.');
    } });
    const { session, worker, broker } = value;
    await worker.message('init'); worker.send({ type: 'ready' });
    await assert.rejects(session.connect(endpoint), /activation timed out/);
    await eventually(() => worker.messages('leave').length >= 2);
    broker.resolveAll(); for (const leave of worker.messages('leave')) worker.reply(leave);
    const retry = session.reconnect();
    const leave = await worker.message('leave', 2); broker.resolveAll(); worker.reply(leave);
    const connect = await worker.message('connect'); worker.reply(connect); await retry;
    assert.equal(preparations, 2); assert.equal(worker.messages('connect').length, 1);
});

test('leave and dispose revoke a join waiting for SW readiness before any route or native connect can be posted', async t => {
    for (const dispose of [false, true]) {
        const preparation = deferred<void>(); let routePreparations = 0;
        const value = fixture(t, { prepareAssets: () => preparation.promise,
            createAssetRoute: () => ({ prepare: async () => { ++routePreparations; }, cancel() {} }) });
        const { session, worker, broker } = value;
        await worker.message('init'); worker.send({ type: 'ready' });
        const joining = session.connect(endpoint), cancelled = assert.rejects(joining, /cancelled|ended/);
        const firstLeave = await worker.message('leave'); broker.resolveAll(); worker.reply(firstLeave);
        if (dispose) session.dispose(); else session.leave();
        preparation.resolve(); await cancelled;
        assert.equal(routePreparations, 0); assert.equal(worker.messages('connect').length, 0);
        assert.equal(session.connected, false); assert.equal(session.assetRouting.directReady, false);
    }
});
