// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import WebRTCSocket, { type TransportDisconnection } from '../src/protocol/vircadia/domain/networking/webrtc/WebRTCSocket';
import WebRTCDataChannel from '../src/protocol/vircadia/domain/networking/webrtc/WebRTCDataChannel';
// Enter the historical NodeList/PacketReceiver import cycle through its concrete class.
import '../src/protocol/vircadia/domain/networking/NodeList';
import LimitedNodeList from '../src/protocol/vircadia/domain/networking/LimitedNodeList';
import Node from '../src/protocol/vircadia/domain/networking/Node';
import SockAddr from '../src/protocol/vircadia/domain/networking/SockAddr';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import NodePermissions from '../src/protocol/vircadia/domain/networking/NodePermissions';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';
import { NodeTypeValue } from '../src/protocol/vircadia/domain/networking/NodeType';
import UDT from '../src/protocol/vircadia/domain/networking/udt/UDT';
import Uuid from '../src/protocol/vircadia/domain/shared/Uuid';
import Url from '../src/protocol/vircadia/domain/shared/Url';
import '../src/protocol/vircadia/domain/shared/DataViewExtensions';
import { createNativeBrowserPeer, type BrowserPeerFactory } from '../src/protocol/browser-peer';

const URL_A = 'ws://transport-a.invalid/', URL_B = 'ws://transport-b.invalid/';
const tick = () => new Promise<void>(resolve => setTimeout(resolve, 0));
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>(done => { resolve = done; });
    return { promise, resolve };
}
class ControlledWebSocket {
    static instances: ControlledWebSocket[] = [];
    readyState = 0;
    onopen: ((event: unknown) => void) | null = null;
    onmessage: ((event: unknown) => void) | null = null;
    onclose: ((event: unknown) => void) | null = null;
    onerror: ((event: unknown) => void) | null = null;
    sent: Record<string, unknown>[] = [];
    listeners = new Map<string, Set<(event: unknown) => void>>();
    constructor(readonly url: string) { ControlledWebSocket.instances.push(this); }
    addEventListener(name: string, callback: (event: unknown) => void) {
        const listeners = this.listeners.get(name) ?? new Set(); listeners.add(callback); this.listeners.set(name, listeners);
    }
    removeEventListener(name: string, callback: (event: unknown) => void) { this.listeners.get(name)?.delete(callback); }
    send(value: string) { this.sent.push(JSON.parse(value)); }
    close() { this.readyState = 3; }
    open() { this.readyState = 1; this.onopen?.({}); }
    receive(value: object) {
        const event = { type: 'message', data: JSON.stringify(value) };
        this.onmessage?.(event);
        for (const listener of [...(this.listeners.get('message') ?? [])]) listener(event);
    }
    fail() { this.onerror?.({}); }
    closed() { this.readyState = 3; this.onclose?.({ code: 1006 }); }
}
class ControlledDataChannel {
    readyState = 'connecting'; bufferedAmount = 0; binaryType = 'arraybuffer';
    onopen: (() => void) | null = null;
    onmessage: ((event: { data: unknown }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onSend: ((bytes: ArrayBuffer) => void) | null = null;
    sent: ArrayBuffer[] = [];
    send(bytes: ArrayBuffer) { this.sent.push(bytes.slice(0)); this.onSend?.(bytes.slice(0)); }
    close() { this.readyState = 'closed'; }
    open() { this.readyState = 'open'; this.onopen?.(); }
    receive(data: unknown) { this.onmessage?.({ data }); }
    closed() { this.readyState = 'closed'; this.onclose?.(); }
    fail() { this.onerror?.(); }
}
class ControlledPeer {
    static instances: ControlledPeer[] = [];
    static nextOffer: Promise<RTCSessionDescriptionInit> | null = null;
    connectionState = 'new';
    onicecandidate: ((event: { candidate: unknown }) => void) | null = null;
    onconnectionstatechange: (() => void) | null = null;
    channel = new ControlledDataChannel();
    offer = ControlledPeer.nextOffer ?? Promise.resolve({ type: 'offer' as const, sdp: 'controlled offer' });
    localFuture: Promise<void> = Promise.resolve(); remoteFuture: Promise<void> = Promise.resolve();
    localCalls = 0; remoteCalls = 0; candidates: RTCIceCandidateInit[] = [];
    constructor(readonly configuration: RTCConfiguration) {
        ControlledPeer.instances.push(this); ControlledPeer.nextOffer = null;
    }
    createDataChannel(_label: string, configuration: RTCDataChannelInit) {
        assert.equal(configuration.ordered, false); assert.equal(configuration.maxRetransmits, 0); return this.channel;
    }
    createOffer() { return this.offer; }
    setLocalDescription() { ++this.localCalls; return this.localFuture; }
    setRemoteDescription() { ++this.remoteCalls; return this.remoteFuture; }
    addIceCandidate(candidate: RTCIceCandidateInit) { this.candidates.push(candidate); return Promise.resolve(); }
    close() { this.connectionState = 'closed'; }
}
const cleanups = new WeakMap<TestContext, Array<() => void>>();
function cleanup(t: TestContext, callback: () => void) { cleanups.get(t)!.push(callback); }
function controlledRTC(t: TestContext) {
    cleanups.set(t, []);
    ControlledWebSocket.instances = []; ControlledPeer.instances = []; ControlledPeer.nextOffer = null;
    const originals = new Map(['WebSocket', 'RTCPeerConnection'].map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
    Object.defineProperty(globalThis, 'WebSocket', { configurable: true, writable: true, value: ControlledWebSocket });
    Object.defineProperty(globalThis, 'RTCPeerConnection', { configurable: true, writable: true, value: ControlledPeer });
    t.after(() => {
        for (const callback of cleanups.get(t)!) callback();
        for (const peer of ControlledPeer.instances) assert.equal(peer.connectionState, 'closed', 'every created RTC peer is disposed');
        for (const [name, original] of originals) {
            if (original) Object.defineProperty(globalThis, name, original);
            else Reflect.deleteProperty(globalThis, name);
        }
    });
}
async function open(t: TestContext, nodeType = NodeTypeValue.DomainServer) {
    controlledRTC(t);
    const socket = new WebRTCSocket(); cleanup(t, () => socket.abort());
    let port = 0;
    socket.connectToHost(URL_A, nodeType, id => { port = id; });
    const signaling = ControlledWebSocket.instances[0]; signaling.open(); await tick();
    const peer = ControlledPeer.instances[0]; peer.channel.open(); assert.ok(port > 0);
    return { socket, signaling, peer, port };
}
class ExposedNodeList extends LimitedNodeList { get socket() { return this._nodeSocket; } }

test('aborting before deferred startup does not create or leak a peer', async t => {
    controlledRTC(t);
    const socket = new WebRTCSocket();
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, () => assert.fail('closed socket opened'));
    ControlledWebSocket.instances[0].open(); socket.abort();
    await tick(); assert.equal(ControlledPeer.instances.length, 0);
});

test('a transferred channel already open at factory acquisition activates its native socket once', async t => {
    controlledRTC(t);
    let factoryCalls = 0;
    const factory: BrowserPeerFactory = async (nodeType, ice, policy, signal) => {
        ++factoryCalls;
        assert.equal(nodeType, NodeTypeValue.DomainServer); assert.deepEqual(ice, []); assert.equal(policy, 'relay');
        const result = await createNativeBrowserPeer(nodeType, ice, policy, signal);
        ControlledPeer.instances.at(-1)!.channel.open();
        return result;
    };
    const socket = new WebRTCSocket([], 'relay', factory); cleanup(t, () => socket.abort());
    const ports: number[] = [];
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, id => ports.push(id));
    ControlledWebSocket.instances[0].open(); await tick();
    assert.deepEqual(ports, [1]); assert.equal(factoryCalls, 1);
    assert.equal(socket.state(URL_A, NodeTypeValue.DomainServer), WebRTCSocket.CONNECTED);
    assert.equal(ControlledWebSocket.instances[0].sent.length, 1, 'the native SDP offer still uses the original signaling path');
});

test('closing during factory acquisition aborts and disposes its late peer without modifying a later join', async t => {
    controlledRTC(t);
    const acquired = deferred<void>();
    const signals: AbortSignal[] = [];
    let first = true;
    const factory: BrowserPeerFactory = async (nodeType, ice, policy, signal) => {
        signals.push(signal!);
        const result = await createNativeBrowserPeer(nodeType, ice, policy, signal);
        if (first) { first = false; await acquired.promise; }
        return result;
    };
    const socket = new WebRTCSocket([], 'all', factory); cleanup(t, () => socket.abort());
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, () => assert.fail('stale acquired channel opened'));
    const oldSignaling = ControlledWebSocket.instances[0]; oldSignaling.open(); await tick();
    const oldPeer = ControlledPeer.instances[0];
    socket.abort(); assert.equal(signals[0].aborted, true); assert.equal(oldPeer.connectionState, 'closed');
    let port = 0;
    socket.connectToHost(URL_B, NodeTypeValue.DomainServer, id => { port = id; });
    const nextSignaling = ControlledWebSocket.instances[1]; nextSignaling.open(); await tick();
    ControlledPeer.instances[1].channel.open();
    acquired.resolve(); await tick();
    assert.equal(oldSignaling.sent.length, 0); assert.equal(nextSignaling.sent.length, 1);
    assert.equal(port, 2); assert.equal(signals[1].aborted, false);
    assert.equal(socket.state(URL_B, NodeTypeValue.DomainServer), WebRTCSocket.CONNECTED);
});

test('late offer, RTC events and old signaling close cannot modify a later join or its ports', async t => {
    controlledRTC(t);
    const offer = deferred<RTCSessionDescriptionInit>(); ControlledPeer.nextOffer = offer.promise;
    const socket = new WebRTCSocket(); cleanup(t, () => socket.abort());
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, () => assert.fail('old join opened'));
    const oldSignaling = ControlledWebSocket.instances[0]; oldSignaling.open(); await tick();
    const oldPeer = ControlledPeer.instances[0], oldOpened = oldPeer.channel.onopen!, oldIce = oldPeer.onicecandidate!;
    const oldClosed = oldSignaling.onclose!; socket.abort();
    let port = 0;
    socket.connectToHost(URL_B, NodeTypeValue.DomainServer, id => { port = id; });
    const nextSignaling = ControlledWebSocket.instances[1]; nextSignaling.open(); await tick();
    const nextPeer = ControlledPeer.instances[1]; nextPeer.channel.open();
    offer.resolve({ type: 'offer', sdp: 'late old offer' }); await tick();
    oldOpened(); oldIce({ candidate: { candidate: 'stale candidate' } }); oldClosed({});
    assert.equal(oldSignaling.sent.length, 0); assert.equal(nextSignaling.sent.length, 1);
    assert.equal(nextPeer.connectionState, 'new');
    assert.equal(socket.state(URL_B, NodeTypeValue.DomainServer), WebRTCSocket.CONNECTED);
    assert.equal(port, 2, 'pseudo ports are not reset or assigned by stale callbacks');
    assert.equal(ControlledPeer.instances.length, 2, 'exactly one peer was created per join');
    assert.equal(socket.writeDatagram(new ArrayBuffer(4), 1), -1);
});

test('closing during local SDP application prevents remote SDP from running', async t => {
    const { socket, signaling, peer, port } = await open(t);
    const local = deferred<void>(); peer.localFuture = local.promise;
    signaling.receive({ from: NodeTypeValue.DomainServer, data: { description: { type: 'answer', sdp: 'answer' } } });
    assert.equal(peer.localCalls, 1);
    socket.disconnectFromHost(port); local.resolve(); await tick(); assert.equal(peer.remoteCalls, 0);
});

test('closing during remote SDP application discards saved ICE and late continuations', async t => {
    const { socket, signaling, peer, port } = await open(t);
    signaling.receive({ from: NodeTypeValue.DomainServer, data: { candidate: { candidate: 'candidate:1' } } });
    const remote = deferred<void>(); peer.remoteFuture = remote.promise;
    signaling.receive({ from: NodeTypeValue.DomainServer, data: { description: { type: 'answer', sdp: 'answer' } } });
    await tick(); assert.equal(peer.remoteCalls, 1);
    socket.disconnectFromHost(port); remote.resolve(); await tick(); assert.deepEqual(peer.candidates, []);
});

test('ICE accumulation is bounded and closes the current service immediately once exceeded', async t => {
    const { socket, signaling, peer } = await open(t);
    const events: TransportDisconnection[] = []; socket.transportDisconnected.connect(event => events.push(event));
    for (let index = 0; index <= WebRTCDataChannel.MAX_ICE_CANDIDATES; ++index) {
        signaling.receive({ from: NodeTypeValue.DomainServer, data: { candidate: { candidate: `candidate:${index}` } } });
    }
    assert.equal(peer.connectionState, 'closed'); assert.equal(events.length, 1);
    assert.equal(events[0].reason, 'channel-error'); assert.equal(socket.hasPendingDatagrams(), false);
});

test('connecting services while signaling opens coalesces peers and retains callbacks', async t => {
    controlledRTC(t);
    const socket = new WebRTCSocket(); cleanup(t, () => socket.abort()); const ports: number[] = [];
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, id => ports.push(id));
    socket.connectToHost(URL_A, NodeTypeValue.AssetServer, id => ports.push(id));
    socket.connectToHost(URL_A, NodeTypeValue.DomainServer, id => ports.push(id));
    assert.equal(ControlledWebSocket.instances.length, 1);
    ControlledWebSocket.instances[0].open(); await tick(); assert.equal(ControlledPeer.instances.length, 2);
    for (const peer of ControlledPeer.instances) peer.channel.open(); assert.deepEqual(ports, [1, 1, 2]);
    socket.connectToHost(URL_A, NodeTypeValue.AssetServer, id => ports.push(id));
    assert.deepEqual(ports, [1, 1, 2, 2]); assert.equal(ControlledPeer.instances.length, 2);
});

test('receive MTU, per-channel counts, total bytes and send buffering stay bounded', async t => {
    const { socket, signaling, peer, port } = await open(t);
    peer.channel.receive(new ArrayBuffer(3)); peer.channel.receive(new ArrayBuffer(UDT.MAX_PACKET_SIZE + 1));
    peer.channel.receive('nonbinary'); assert.equal(socket.hasPendingDatagrams(), false);
    for (let index = 0; index < 1000; ++index) peer.channel.receive(new ArrayBuffer(4));
    let count = 0;
    while (socket.hasPendingDatagrams()) { assert.equal(socket.readDatagram({ buffer: undefined, sender: undefined }), 4); ++count; }
    assert.equal(count, WebRTCSocket.MAX_CHANNEL_DATAGRAMS);
    for (const type of [NodeTypeValue.AudioMixer, NodeTypeValue.AvatarMixer, NodeTypeValue.AssetServer]) {
        socket.connectToHost(URL_A, type, () => {});
    }
    await tick();
    for (const current of ControlledPeer.instances) {
        current.channel.open();
        for (let index = 0; index < 1000; ++index) current.channel.receive(new ArrayBuffer(UDT.MAX_PACKET_SIZE));
    }
    let bytes = 0; count = 0;
    while (socket.hasPendingDatagrams()) { bytes += socket.readDatagram({ buffer: undefined, sender: undefined }); ++count; }
    assert.equal(count, Math.floor(WebRTCSocket.MAX_QUEUED_BYTES / UDT.MAX_PACKET_SIZE));
    assert.ok(bytes <= WebRTCSocket.MAX_QUEUED_BYTES);
    assert.equal(socket.writeDatagram(new ArrayBuffer(UDT.MAX_PACKET_SIZE + 1), port), -1);
    peer.channel.bufferedAmount = WebRTCDataChannel.MAX_BUFFERED_BYTES;
    assert.equal(socket.writeDatagram(new ArrayBuffer(4), port), -1);
    peer.channel.bufferedAmount = 0; assert.equal(socket.writeDatagram(new ArrayBuffer(4), port), 4);
    const staleReceive = peer.channel.onmessage!;
    peer.channel.receive(new ArrayBuffer(4)); socket.disconnectFromHost(port); staleReceive({ data: new ArrayBuffer(4) });
    assert.equal(socket.hasPendingDatagrams(), false);
    assert.equal(signaling.readyState, 1, 'closing one service retains signaling for other services');
});

test('service and signaling failures relay synchronously through LimitedNodeList once, excluding stale sessions', async t => {
    controlledRTC(t);
    const nodes = new ExposedNodeList(0); cleanup(t, () => nodes.reset('test complete'));
    const events: TransportDisconnection[] = []; nodes.transportDisconnected.connect(event => events.push(event));
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AssetServer, () => {});
    const signaling = ControlledWebSocket.instances[0]; signaling.open(); await tick();
    const peer = ControlledPeer.instances[0]; peer.channel.open(); const oldClosed = peer.channel.onclose!;
    peer.channel.closed();
    assert.deepEqual(events[0], { nodeType: NodeTypeValue.AssetServer, channelID: 1, reason: 'channel-closed', message: undefined });
    oldClosed(); assert.equal(events.length, 1);
    signaling.closed(); assert.equal(events.length, 2); assert.equal(events[1].reason, 'signaling-closed');
    nodes.socket.openSocket(new Url(URL_B), NodeTypeValue.DomainServer, () => {});
    const nextSignaling = ControlledWebSocket.instances[1]; nextSignaling.open(); await tick();
    ControlledPeer.instances[1].channel.open(); oldClosed(); assert.equal(events.length, 2);
    nextSignaling.fail(); assert.equal(events.length, 3);
    nextSignaling.closed(); assert.equal(events.length, 3, 'later close after WebSocket error is ignored');
});

test('actual reliable PacketList emission carries native source ID and payload HMAC on queued originals', async t => {
    controlledRTC(t);
    const nodes = new ExposedNodeList(0); cleanup(t, () => nodes.reset('test complete'));
    nodes.setSessionLocalID(4097);
    let port = 0; nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AssetServer, id => { port = id; });
    ControlledWebSocket.instances[0].open(); await tick(); const peer = ControlledPeer.instances[0]; peer.channel.open();
    const address = new SockAddr(); address.setPort(port);
    const destination = new Node(new Uuid('00112233-4455-6677-8899-aabbccddeeff'), NodeTypeValue.AssetServer, address, new SockAddr());
    const secret = '0102030405060708090a0b0c0d0e0f10';
    destination.setConnectionSecret(new Uuid('01020304-0506-0708-090a-0b0c0d0e0f10')); destination.activatePublicSocket();
    const received: Uint8Array[] = [];
    peer.channel.onSend = bytes => {
        const data = new DataView(bytes), bits = data.getUint32(0, true);
        // Fixture endpoint uses current C++ control layout, independent of SDK encoders.
        if (bits & 0x80000000) {
            if ((bits >>> 16 & 0x7fff) !== 1) return;
            const ack = new ArrayBuffer(8), view = new DataView(ack);
            view.setUint32(0, 0x80020000, true); view.setUint32(4, data.getUint32(4, true), true); peer.channel.receive(ack);
        } else {
            received.push(new Uint8Array(bytes));
            const ack = new ArrayBuffer(8), view = new DataView(ack);
            view.setUint32(0, 0x80000000, true); view.setUint32(4, bits & 0x07ffffff, true); peer.channel.receive(ack);
        }
    };
    const payload = new Uint8Array([4, 3, 2, 1, 0, 5, 0, 0, 0, 47, 97, 46, 102, 115]);
    for (const type of [PacketType.AssetMappingOperation, PacketType.AvatarIdentity]) {
        const list = NLPacketList.create(type, null, true, true); list.write(payload); assert.equal(nodes.sendPacketList(list, destination), 0);
    }
    for (let tries = 0; tries < 100 && received.length < 2; ++tries) await tick();
    assert.equal(received.length, 2, 'native-format handshake ACK permits both reliable messages to leave');
    assert.deepEqual(received.map(bytes => bytes[12]), [PacketType.AssetMappingOperation, PacketType.AvatarIdentity]);
    for (const bytes of received) {
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        assert.equal(view.getUint16(14, true), 4097, 'emitted original carries current session local ID');
        assert.deepEqual(bytes.subarray(32), payload);
        const expected = createHmac('md5', Buffer.from(secret, 'hex')).update(payload).digest();
        assert.deepEqual(Buffer.from(bytes.subarray(16, 32)), expected, 'emitted original carries native HMAC-MD5 over exact payload');
    }
});


function sourcedWire(type: number, localID: number, payload = new Uint8Array([10, 20, 30, 40]), validHash = true): ArrayBuffer {
    const packet = NLPacket.create(type, payload.byteLength, false);
    packet.writeSourceID(localID);
    const data = packet.getMessageData(), start = data.dataPosition;
    data.buffer.set(payload, start); data.packetSize = start + payload.byteLength;
    if (!PacketType.getNonVerifiedPackets().has(type)) {
        const hashOffset = 8;
        const hash = createHmac('md5', Buffer.from('0102030405060708090a0b0c0d0e0f10', 'hex')).update(payload).digest();
        data.buffer.set(validHash ? hash : new Uint8Array(16), hashOffset);
    }
    return data.buffer.slice(0, data.packetSize).buffer;
}
function serviceNode(nodes: ExposedNodeList, type: NodeTypeValue, port: number, localID: number, secret = true) {
    const address = new SockAddr(); address.setPort(port); address.setAddress(0x01020304);
    const node = nodes.addOrUpdateNode(new Uuid(type === NodeTypeValue.AvatarMixer
        ? '00112233-4455-6677-8899-aabbccddeeff' : '10112233-4455-6677-8899-aabbccddeeff'), type,
        address, new SockAddr(), localID, false, false,
        new Uuid(secret ? '01020304-0506-0708-090a-0b0c0d0e0f10' : Uuid.NULL), new NodePermissions());
    node.activatePublicSocket(); return node;
}
class ClientNodeList extends ExposedNodeList {
    domainSocket = new SockAddr();
    override isDomainServer() { return false; }
    override getDomainLocalID() { return 17; }
    override getDomainSockAddr() { return this.domainSocket; }
}

test('browser receive verifies native payload HMAC and current service channel, even when authentication is disabled', async t => {
    controlledRTC(t);
    const nodes = new ClientNodeList(0); cleanup(t, () => nodes.reset('test complete'));
    const received: number[] = [];
    nodes.socket.setPacketHandler(packet => received.push(NLPacket.typeInHeader(packet)));
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AvatarMixer, port => serviceNode(nodes, NodeTypeValue.AvatarMixer, port, 201));
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AudioMixer, port => serviceNode(nodes, NodeTypeValue.AudioMixer, port, 202));
    ControlledWebSocket.instances[0].open(); await tick();
    const [avatar, audio] = ControlledPeer.instances; avatar.channel.open(); audio.channel.open();
    const valid = sourcedWire(PacketType.AvatarData, 201);
    avatar.channel.receive(valid); await tick(); assert.deepEqual(received, [PacketType.AvatarData]);
    avatar.channel.receive(sourcedWire(PacketType.AvatarData, 201, undefined, false));
    audio.channel.receive(valid); // Valid payload MAC, wrong actual RTC service.
    avatar.channel.receive(sourcedWire(PacketType.AvatarData, 999));
    const corrupted = valid.slice(0); new Uint8Array(corrupted)[corrupted.byteLength - 1] ^= 1;
    avatar.channel.receive(corrupted); await tick(); assert.equal(received.length, 1);
    // The native non-verified exception still requires the source's actual channel.
    avatar.channel.receive(sourcedWire(PacketType.EntityQuery, 201));
    audio.channel.receive(sourcedWire(PacketType.EntityQuery, 201));
    await tick(); assert.deepEqual(received, [PacketType.AvatarData, PacketType.EntityQuery]);
    nodes.setAuthenticatePackets(false);
    avatar.channel.receive(sourcedWire(PacketType.AvatarData, 201, undefined, false));
    audio.channel.receive(sourcedWire(PacketType.AvatarData, 201, undefined, false));
    await tick(); assert.equal(received.length, 3);
});

test('asset-reply ignored verification is restricted to the native domain-server exception', async t => {
    controlledRTC(t);
    const nodes = new ExposedNodeList(0); cleanup(t, () => nodes.reset('test complete'));
    let delivered = 0; nodes.socket.setPacketHandler(() => { ++delivered; });
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AssetServer, port => serviceNode(nodes, NodeTypeValue.AssetServer, port, 201, false));
    ControlledWebSocket.instances[0].open(); await tick();
    const peer = ControlledPeer.instances[0]; peer.channel.open();
    peer.channel.receive(sourcedWire(PacketType.AssetGetReply, 201, undefined, false)); await tick();
    assert.equal(delivered, 1, 'native domain-server asset exception permits an unsigned asset reply');
    peer.channel.receive(sourcedWire(PacketType.Ping, 201, undefined, false)); await tick();
    assert.equal(delivered, 1, 'a sourced verified packet without its connection secret is rejected');
    // Client NodeList does not inherit the domain-server asset exception.
    t.mock.method(nodes, 'isDomainServer', () => false);
    peer.channel.receive(sourcedWire(PacketType.AssetGetReply, 201, undefined, false)); await tick();
    assert.equal(delivered, 1);
});

test('native domain-sourced packets require their declared domain ID and the current domain channel', async t => {
    controlledRTC(t);
    const nodes = new ClientNodeList(0); cleanup(t, () => nodes.reset('test complete'));
    let delivered = 0; nodes.socket.setPacketHandler(() => { ++delivered; });
    nodes.socket.setConnectionCreationFilterOperator(() => true);
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.DomainServer, port => nodes.domainSocket.setPort(port));
    nodes.socket.openSocket(new Url(URL_A), NodeTypeValue.AssetServer, () => {});
    ControlledWebSocket.instances[0].open(); await tick();
    const [domain, asset] = ControlledPeer.instances; domain.channel.open(); asset.channel.open();
    domain.channel.receive(sourcedWire(PacketType.AssetGet, 17, undefined, false)); await tick();
    assert.equal(delivered, 1);
    asset.channel.receive(sourcedWire(PacketType.AssetGet, 17, undefined, false));
    domain.channel.receive(sourcedWire(PacketType.AssetGet, 18, undefined, false));
    domain.channel.receive(sourcedWire(PacketType.Ping, 17, undefined, false));
    await tick(); assert.equal(delivered, 1);
});
