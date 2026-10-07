// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted implementation; reviewed changes and validation are recorded in REUSE.md.
import { BrowserPeerError, PEER_LIMITS, validCandidate, validDescription, validIceServers,
    validPeerId, validPeerState, validRequestId, type BrowserPeer, type BrowserPeerControl,
    type BrowserPeerFactory, type PeerOperation, type PeerRequest, type PeerResponse } from './browser-peer';

export type WorkerPeerFactory = BrowserPeerFactory & { close(): void };
type Pending = { peer: string; operation: 'create' | PeerOperation;
    resolve(response: PeerResponse): void; reject(error: BrowserPeerError): void };

class RemotePeer implements BrowserPeerControl {
    private state: RTCPeerConnectionState = 'new';
    private candidateCallback: BrowserPeerControl['onicecandidate'] = null;
    private stateCallback: BrowserPeerControl['onconnectionstatechange'] = null;
    private savedCandidates: Array<RTCIceCandidateInit | null> = [];
    private receivedCandidates = 0;
    channel?: RTCDataChannel;
    removeAbort?: () => void;
    constructor(readonly id: string, private readonly owner: WorkerPeerControls) {}
    get connectionState(): RTCPeerConnectionState { return this.state; }
    get onicecandidate() { return this.candidateCallback; }
    set onicecandidate(value: BrowserPeerControl['onicecandidate']) {
        this.candidateCallback = value;
        if (value) {
            const pending = this.savedCandidates; this.savedCandidates = [];
            for (const candidate of pending) if (this.state !== 'closed') value(candidate);
        }
    }
    get onconnectionstatechange() { return this.stateCallback; }
    set onconnectionstatechange(value: BrowserPeerControl['onconnectionstatechange']) {
        this.stateCallback = value;
        if (value && ['closed', 'failed', 'disconnected'].includes(this.state)) value(this.state);
    }
    async createOffer(): Promise<RTCSessionDescriptionInit> {
        const response = await this.owner.call(this, 'offer');
        if (response.type !== 'result' || !validDescription(response.description, 'offer')) {
            throw new BrowserPeerError('The native RTC broker returned an invalid offer.');
        }
        return response.description;
    }
    async setLocalDescription(description: RTCSessionDescriptionInit): Promise<void> {
        if (!validDescription(description, 'offer')) throw new BrowserPeerError('The native RTC local description is invalid.');
        await this.owner.call(this, 'local', { description });
    }
    async setRemoteDescription(description: RTCSessionDescriptionInit): Promise<void> {
        if (!validDescription(description, 'answer')) throw new BrowserPeerError('The native RTC remote description is invalid.');
        await this.owner.call(this, 'remote', { description });
    }
    async addIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
        if (!validCandidate(candidate)) throw new BrowserPeerError('The native RTC candidate is invalid.');
        await this.owner.call(this, 'ice', { candidate });
    }
    close(): void { this.owner.retire(this, true); }
    updateState(state: RTCPeerConnectionState): void {
        if (this.state === 'closed') return;
        this.state = state;
        this.stateCallback?.(state);
    }
    candidate(candidate: RTCIceCandidateInit | null): void {
        if (this.state === 'closed') return;
        if (candidate && ++this.receivedCandidates > PEER_LIMITS.candidates) { this.close(); return; }
        if (this.candidateCallback) this.candidateCallback(candidate);
        else if (this.savedCandidates.length < PEER_LIMITS.candidates) this.savedCandidates.push(candidate);
        else this.close();
    }
    dispose(): void {
        const callback = this.stateCallback;
        this.state = 'closed';
        this.candidateCallback = null; this.stateCallback = null; this.savedCandidates = [];
        this.removeAbort?.(); this.removeAbort = undefined;
        try { this.channel?.close(); } catch { /* Already closed or detached. */ }
        callback?.('closed');
    }
}

class WorkerPeerControls {
    private readonly peers = new Map<string, RemotePeer>();
    private readonly pending = new Map<number, Pending>();
    private nextRequest = 0;
    private disposed = false;
    private epoch = 1;
    constructor(private readonly port: MessagePort) {
        port.addEventListener('message', this.receive);
        port.addEventListener('messageerror', this.messageError);
        port.start();
    }
    async create(nodeType: string, iceServers: RTCIceServer[], policy: RTCIceTransportPolicy,
        signal?: AbortSignal): Promise<BrowserPeer> {
        if (signal?.aborted || this.disposed) throw new BrowserPeerError('The native peer creation was cancelled.');
        if (this.peers.size >= PEER_LIMITS.peers) throw new BrowserPeerError('The browser RTC peer limit was exceeded.');
        if (!validIceServers(iceServers) || !['all', 'relay'].includes(policy)) {
            throw new BrowserPeerError('The browser RTC configuration is invalid.');
        }
        const peer = new RemotePeer(crypto.randomUUID(), this);
        this.peers.set(peer.id, peer);
        const abort = () => this.retire(peer, true);
        signal?.addEventListener('abort', abort, { once: true });
        peer.removeAbort = () => signal?.removeEventListener('abort', abort);
        try {
            const response = await this.request(peer, 'create', request => ({ type: 'create', epoch: this.epoch, request,
                peer: peer.id, nodeType, iceServers, policy }));
            if (response.type !== 'created' || !peer.channel || this.peers.get(peer.id) !== peer) {
                throw new BrowserPeerError('The native RTC peer has ended.');
            }
            return { peer, channel: peer.channel };
        } catch (error) {
            this.retire(peer, true);
            throw error;
        }
    }
    call(peer: RemotePeer, operation: PeerOperation, values: { description?: RTCSessionDescriptionInit;
        candidate?: RTCIceCandidateInit } = {}): Promise<PeerResponse> {
        return this.request(peer, operation, request => ({ type: 'call', epoch: this.epoch, request, peer: peer.id, operation, ...values }));
    }
    private request(peer: RemotePeer, operation: Pending['operation'], make: (request: number) => PeerRequest): Promise<PeerResponse> {
        if (this.disposed || this.peers.get(peer.id) !== peer) return Promise.reject(new BrowserPeerError('The native RTC peer has ended.'));
        let ownedPending = 0;
        for (const item of this.pending.values()) if (item.peer === peer.id) ++ownedPending;
        if (this.pending.size >= PEER_LIMITS.pending || ownedPending >= PEER_LIMITS.pendingPerPeer
            || this.nextRequest === Number.MAX_SAFE_INTEGER) {
            return Promise.reject(new BrowserPeerError('The browser RTC control queue is full.'));
        }
        const request = ++this.nextRequest;
        return new Promise((resolve, reject) => {
            this.pending.set(request, { peer: peer.id, operation, resolve, reject });
            if (!this.send(make(request))) {
                this.pending.delete(request);
                reject(new BrowserPeerError('The native RTC control port failed.'));
                this.close();
            }
        });
    }
    private send(message: PeerRequest): boolean {
        if (this.disposed) return false;
        try { this.port.postMessage(message); return true; } catch { return false; }
    }
    retire(peer: RemotePeer, notify: boolean): void {
        if (this.peers.get(peer.id) !== peer) return;
        this.peers.delete(peer.id);
        for (const [request, pending] of this.pending) if (pending.peer === peer.id) {
            this.pending.delete(request);
            pending.reject(new BrowserPeerError('The native RTC peer has ended.'));
        }
        if (notify) this.send({ type: 'close', epoch: this.epoch, peer: peer.id });
        peer.dispose();
    }
    close(): void {
        if (this.disposed) return;
        this.send({ type: 'shutdown' });
        this.disposed = true;
        for (const peer of [...this.peers.values()]) this.retire(peer, false);
        this.port.removeEventListener('message', this.receive);
        this.port.removeEventListener('messageerror', this.messageError);
        this.port.close();
    }
    private messageError = (): void => { this.close(); };
    private receive = ({ data }: MessageEvent<unknown>): void => {
        if (this.disposed || !data || typeof data !== 'object') return;
        const message = data as PeerResponse;
        if (message.type === 'shutdown') { this.close(); return; }
        if (message.type === 'reset') {
            if (!validRequestId(message.epoch) || message.epoch < this.epoch) return;
            if (message.epoch > this.epoch) {
                this.epoch = message.epoch;
                for (const old of [...this.peers.values()]) this.retire(old, false);
            }
            if (!this.send({ type: 'reset-ack', epoch: this.epoch })) this.close();
            return;
        }
        if (!('peer' in message) || !validPeerId(message.peer)) return;
        const peer = this.peers.get(message.peer);
        if (!peer) {
            if (message.type === 'created') {
                try { message.channel?.close(); } catch { /* Stale transfer. */ }
            }
            return;
        }
        if (message.type === 'closed') { this.retire(peer, false); return; }
        if (message.type === 'state') {
            if (!validPeerState(message.state)) { this.retire(peer, true); return; }
            peer.updateState(message.state); return;
        }
        if (message.type === 'candidate') {
            if (message.candidate !== null && !validCandidate(message.candidate)) { this.retire(peer, true); return; }
            peer.candidate(message.candidate); return;
        }
        if (!('request' in message) || !validRequestId(message.request)) return;
        const pending = this.pending.get(message.request);
        if (!pending || pending.peer !== peer.id) {
            if (message.type === 'created') {
                try { message.channel?.close(); } catch { /* Stale transfer. */ }
            }
            return;
        }
        this.pending.delete(message.request);
        if (message.type === 'error') {
            pending.reject(new BrowserPeerError(typeof message.message === 'string' && message.message.length <= 256
                ? message.message : 'The native RTC control operation failed.')); return;
        }
        if (message.type === 'created' && pending.operation === 'create' && message.channel
            && typeof message.channel.send === 'function' && typeof message.channel.close === 'function'
            && validPeerState(message.state)) {
            peer.channel = message.channel;
            peer.updateState(message.state);
            pending.resolve(message); return;
        }
        if (message.type === 'result' && pending.operation !== 'create') { pending.resolve(message); return; }
        pending.reject(new BrowserPeerError('The native RTC broker returned an invalid response.'));
        this.retire(peer, true);
    };
}

export function createWorkerPeerFactory(controlPort: MessagePort): WorkerPeerFactory {
    const owner = new WorkerPeerControls(controlPort);
    const factory = ((...args: Parameters<BrowserPeerFactory>) => owner.create(...args)) as WorkerPeerFactory;
    factory.close = () => owner.close();
    return factory;
}
