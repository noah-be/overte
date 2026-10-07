// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { MessageChannel, MessagePort as NodeMessagePort } from 'node:worker_threads';
import { MainThreadPeerBroker } from '../src/protocol/rtc-peer-broker';
import { createWorkerPeerFactory } from '../src/protocol/worker-peer-factory';
import { PEER_LIMITS, type PeerResponse } from '../src/protocol/browser-peer';

const tick = () => new Promise<void>(resolve => setTimeout(resolve, 5));
async function eventually(predicate: () => boolean) {
    for (let count = 0; count < 100 && !predicate(); ++count) await tick();
    assert.ok(predicate(), 'the bounded control event was delivered');
}
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>(done => { resolve = done; });
    return { promise, resolve };
}

/** Node has real transferable MessagePorts but no RTC implementation. Only the
 * native RTC API is mocked: its channel is a real transferred port whose
 * prototype supplies the DataChannel interface in both receiving realms. */
class NativePeer {
    static instances: NativePeer[] = [];
    static untransferable = false;
    static events: string[] = [];
    readonly pair = new MessageChannel();
    connectionState = 'new';
    onicecandidate: ((event: { candidate: unknown }) => void) | null = null;
    onconnectionstatechange: (() => void) | null = null;
    offerFuture: Promise<RTCSessionDescriptionInit> = Promise.resolve({ type: 'offer', sdp: 'native offer' });
    remoteFuture: Promise<void> = Promise.resolve();
    offers = 0;
    local: RTCSessionDescriptionInit[] = [];
    remote: RTCSessionDescriptionInit[] = [];
    candidates: RTCIceCandidateInit[] = [];
    constructor(readonly configuration: RTCConfiguration) {
        NativePeer.instances.push(this); NativePeer.events.push('peer');
    }
    createDataChannel(label: string, options: RTCDataChannelInit) {
        assert.equal(label, 'label');
        assert.deepEqual(options, { protocol: 'protocol', negotiated: false, ordered: false, maxRetransmits: 0 });
        NativePeer.events.push('channel');
        if (NativePeer.untransferable) return { send() {}, close() {}, readyState: 'connecting' };
        return this.pair.port1;
    }
    createOffer(options: RTCOfferOptions) {
        assert.deepEqual(options, { offerToReceiveAudio: false, offerToReceiveVideo: false });
        NativePeer.events.push('offer'); ++this.offers; return this.offerFuture;
    }
    setLocalDescription(value: RTCSessionDescriptionInit) { this.local.push(value); return Promise.resolve(); }
    setRemoteDescription(value: RTCSessionDescriptionInit) { this.remote.push(value); return this.remoteFuture; }
    addIceCandidate(value: RTCIceCandidateInit) { this.candidates.push(value); return Promise.resolve(); }
    close() {
        this.connectionState = 'closed';
        this.pair.port1.close(); this.pair.port2.close();
    }
}

function fixture(t: TestContext) {
    NativePeer.instances = []; NativePeer.events = []; NativePeer.untransferable = false;
    const native = Object.getOwnPropertyDescriptor(globalThis, 'RTCPeerConnection');
    Object.defineProperty(globalThis, 'RTCPeerConnection', { configurable: true, value: NativePeer });
    const prototype = NodeMessagePort.prototype;
    const names = ['send', 'readyState', 'bufferedAmount'];
    const originals = new Map(names.map(name => [name, Object.getOwnPropertyDescriptor(prototype, name)]));
    Object.defineProperties(prototype, {
        send: { configurable: true, value(this: NodeMessagePort, bytes: ArrayBuffer) { this.postMessage(bytes); } },
        readyState: { configurable: true, get() { return 'open'; } },
        bufferedAmount: { configurable: true, get() { return 0; } },
    });
    const control = new MessageChannel();
    const transfers: PeerResponse[] = [];
    const realPost = control.port1.postMessage.bind(control.port1);
    control.port1.postMessage = ((value: PeerResponse, transfer: readonly NodeMessagePort[] = []) => {
        if (value.type === 'created') {
            NativePeer.events.push('transfer'); transfers.push(value);
            assert.equal(transfer.length, 1);
            assert.equal(transfer[0], value.channel);
        }
        realPost(value, [...transfer]);
    }) as typeof control.port1.postMessage;
    const broker = new MainThreadPeerBroker(control.port1 as unknown as MessagePort);
    const factory = createWorkerPeerFactory(control.port2 as unknown as MessagePort);
    t.after(() => {
        factory.close(); broker.close(); control.port1.close(); control.port2.close();
        for (const peer of NativePeer.instances) {
            assert.equal(peer.connectionState, 'closed', 'all owned native peers are closed');
            peer.close();
        }
        if (native) Object.defineProperty(globalThis, 'RTCPeerConnection', native);
        else Reflect.deleteProperty(globalThis, 'RTCPeerConnection');
        for (const [name, descriptor] of originals) {
            if (descriptor) Object.defineProperty(prototype, name, descriptor);
            else Reflect.deleteProperty(prototype, name);
        }
    });
    return { broker, factory, control, transfers };
}

test('real channel transfer precedes offer, controls are RPC, and datagrams bypass the broker', async t => {
    const { broker, factory, transfers } = fixture(t);
    const value = await factory('D', [], 'all');
    assert.deepEqual(NativePeer.events, ['peer', 'channel', 'transfer']);
    assert.notEqual(value.channel, NativePeer.instances[0].pair.port1, 'receiver owns the transferred object');
    assert.equal(value.channel.readyState, 'open');
    assert.deepEqual(await value.peer.createOffer(), { type: 'offer', sdp: 'native offer' });
    assert.deepEqual(NativePeer.events, ['peer', 'channel', 'transfer', 'offer']);
    const bytes = new Uint8Array([9, 8, 7, 6]).buffer;
    const delivered = new Promise<ArrayBuffer>(resolve => NativePeer.instances[0].pair.port2.once('message', resolve));
    value.channel.send(bytes);
    assert.deepEqual(new Uint8Array(await delivered), new Uint8Array(bytes));
    assert.equal(transfers.length, 1, 'no datagram is posted on the control port');
    await value.peer.setLocalDescription({ type: 'offer', sdp: 'local' });
    await value.peer.setRemoteDescription({ type: 'answer', sdp: 'remote' });
    await value.peer.addIceCandidate({ candidate: 'candidate:remote' });
    assert.equal(NativePeer.instances[0].local.length, 1); assert.equal(NativePeer.instances[0].remote.length, 1);
    const received: RTCIceCandidateInit[] = [];
    value.peer.onicecandidate = candidate => { if (candidate) received.push(candidate); };
    NativePeer.instances[0].onicecandidate?.({ candidate: { candidate: 'candidate:local', sdpMid: '0' } });
    await eventually(() => received.length === 1);
    assert.equal(received[0].candidate, 'candidate:local');
    value.peer.close(); await eventually(() => broker.peerCount === 0);
});

test('reset synchronously closes peers and fences queued old creation and delayed offer/answer', async t => {
    const { broker, factory } = fixture(t);
    const first = await factory('D', [], 'all');
    const offer = deferred<RTCSessionDescriptionInit>(), answer = deferred<void>();
    const oldNative = NativePeer.instances[0];
    oldNative.offerFuture = offer.promise; oldNative.remoteFuture = answer.promise;
    const pendingOffer = first.peer.createOffer(), pendingAnswer = first.peer.setRemoteDescription({ type: 'answer', sdp: 'old answer' });
    const rejectedOffer = assert.rejects(pendingOffer, /has ended/), rejectedAnswer = assert.rejects(pendingAnswer, /has ended/);
    await eventually(() => oldNative.offers === 1 && oldNative.remote.length === 1);
    const staleIce = oldNative.onicecandidate!, staleState = oldNative.onconnectionstatechange!;
    const queuedCreation = factory('A', [], 'all');
    const rejectedCreation = assert.rejects(queuedCreation, /generation has ended|peer has ended/);
    const reset = broker.closePeers();
    assert.equal(broker.peerCount, 0); assert.equal(oldNative.connectionState, 'closed');
    assert.equal(broker.closePeers(), reset, 'pending reset requests coalesce');
    await reset; await Promise.all([rejectedOffer, rejectedAnswer, rejectedCreation]);
    assert.equal(NativePeer.instances.length, 1, 'old queued creation cannot allocate a peer after reset');
    const current = await factory('D', [], 'all');
    const candidates: RTCIceCandidateInit[] = [];
    current.peer.onicecandidate = candidate => { if (candidate) candidates.push(candidate); };
    offer.resolve({ type: 'offer', sdp: 'stale offer' }); answer.resolve();
    staleIce({ candidate: { candidate: 'candidate:stale' } }); staleState();
    await tick(); assert.deepEqual(candidates, []);
    assert.equal(current.peer.connectionState, 'new'); assert.equal(broker.peerCount, 1);
    assert.deepEqual(await current.peer.createOffer(), { type: 'offer', sdp: 'native offer' });
});

test('cancelling a posted creation closes the stale transferred channel and its native peer', async t => {
    const { broker, factory } = fixture(t);
    const abort = new AbortController();
    const creation = factory('D', [], 'all', abort.signal);
    const rejected = assert.rejects(creation, /has ended/);
    abort.abort(); await rejected;
    await eventually(() => NativePeer.instances.length === 1 && broker.peerCount === 0);
    assert.equal(NativePeer.instances[0].connectionState, 'closed');
    const next = await factory('D', [], 'all');
    assert.equal(next.peer.connectionState, 'new');
});

test('pending RPC, peers, SDP and candidates have explicit bounds', async t => {
    const { broker, factory } = fixture(t);
    const value = await factory('D', [], 'all');
    const offer = deferred<RTCSessionDescriptionInit>(); NativePeer.instances[0].offerFuture = offer.promise;
    const pending = Array.from({ length: PEER_LIMITS.pendingPerPeer }, () => value.peer.createOffer());
    await assert.rejects(value.peer.createOffer(), /control queue is full/);
    await eventually(() => broker.pendingCount === PEER_LIMITS.pendingPerPeer);
    offer.resolve({ type: 'offer', sdp: 'bounded offer' }); await Promise.all(pending);
    assert.equal(broker.pendingCount, 0);
    await assert.rejects(value.peer.setRemoteDescription({ type: 'answer', sdp: 'x'.repeat(PEER_LIMITS.sdpBytes + 1) }), /invalid/);
    await assert.rejects(value.peer.addIceCandidate({ candidate: 'x'.repeat(PEER_LIMITS.candidateBytes + 1) }), /invalid/);
    for (let index = 0; index < PEER_LIMITS.candidates; ++index) await value.peer.addIceCandidate({ candidate: `candidate:${index}` });
    await assert.rejects(value.peer.addIceCandidate({ candidate: 'candidate:overflow' }), /candidate limit/);
    await eventually(() => broker.peerCount === 0);
    for (let index = 0; index < PEER_LIMITS.peers; ++index) await factory('D', [], 'all');
    await assert.rejects(factory('D', [], 'all'), /peer limit/);
    assert.equal(broker.peerCount, PEER_LIMITS.peers);
});

test('unsupported native transfer fails visibly and closes the peer without fallback', async t => {
    const { broker, factory } = fixture(t); NativePeer.untransferable = true;
    await assert.rejects(factory('D', [], 'all'), /cannot transfer native RTC data channels/);
    assert.equal(broker.peerCount, 0); assert.equal(NativePeer.instances.length, 1);
    assert.equal(NativePeer.instances[0].connectionState, 'closed');
});

test('a worker which does not acknowledge cleanup fails the bounded reset and closes its port', async t => {
    const control = new MessageChannel();
    const broker = new MainThreadPeerBroker(control.port1 as unknown as MessagePort, 20);
    t.after(() => { broker.close(); control.port1.close(); control.port2.close(); });
    await assert.rejects(broker.closePeers(), /did not acknowledge peer cleanup/);
    assert.equal(broker.peerCount, 0); await broker.closePeers();
});
