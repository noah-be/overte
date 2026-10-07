// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted implementation; reviewed changes and validation are recorded in REUSE.md.
import { BrowserPeerError, PEER_LIMITS, createNativePeerNow, validCandidate, validDescription,
    validIceServers, validPeerId, validRequestId, type BrowserPeer, type PeerRequest,
    type PeerResponse } from './browser-peer';

type OwnedPeer = { value: BrowserPeer; candidates: number; remoteCandidates: number; pending: Set<number> };
type ResetBoundary = { promise: Promise<void>; resolve(): void; reject(error: BrowserPeerError): void;
    timer: ReturnType<typeof setTimeout> };

/** Owns only Window RTC controls. Native datagrams never pass through this
 * broker: the real channel is transferred once to the network worker. */
export class MainThreadPeerBroker {
    private readonly peers = new Map<string, OwnedPeer>();
    private readonly requests = new Set<number>();
    private disposed = false;
    private epoch = 1;
    private reset?: ResetBoundary;
    constructor(private readonly port: MessagePort, private readonly resetTimeoutMS = 10000) {
        port.addEventListener('message', this.receive);
        port.addEventListener('messageerror', this.messageError);
        port.start();
    }
    get peerCount(): number { return this.peers.size; }
    get pendingCount(): number { return this.requests.size; }

    /** Leave retires all current peers synchronously; the port survives for reconnect. */
    closePeers(): Promise<void> {
        if (this.disposed) return Promise.resolve();
        for (const [id, peer] of [...this.peers]) this.retire(id, peer);
        if (this.reset) return this.reset.promise;
        ++this.epoch;
        let resolve!: () => void;
        let reject!: (error: BrowserPeerError) => void;
        const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
        const timer = setTimeout(() => {
            if (!this.reset || this.reset.promise !== promise) return;
            this.reset = undefined;
            reject(new BrowserPeerError('The native RTC worker did not acknowledge peer cleanup.'));
            this.close();
        }, this.resetTimeoutMS);
        this.reset = { promise, resolve, reject, timer };
        if (!this.send({ type: 'reset', epoch: this.epoch })) {
            clearTimeout(timer); this.reset = undefined;
            reject(new BrowserPeerError('The native RTC control port failed.'));
            this.close();
        }
        return promise;
    }
    close(): void {
        if (this.disposed) return;
        for (const [id, peer] of [...this.peers]) this.retire(id, peer);
        if (this.reset) {
            clearTimeout(this.reset.timer);
            this.reset.resolve(); this.reset = undefined;
        }
        this.send({ type: 'shutdown' });
        this.disposed = true;
        this.port.removeEventListener('message', this.receive);
        this.port.removeEventListener('messageerror', this.messageError);
        this.port.close();
    }

    private send(message: PeerResponse, transfer: Transferable[] = []): boolean {
        if (this.disposed) return false;
        try { this.port.postMessage(message, transfer); return true; }
        catch { return false; }
    }
    private fail(request: number, peer: string, message: string): void {
        this.send({ type: 'error', request, peer, message });
    }
    private current(id: string, record: OwnedPeer): boolean {
        return !this.disposed && this.peers.get(id) === record;
    }
    private retire(id: string, record: OwnedPeer): void {
        if (this.peers.get(id) !== record) return;
        this.peers.delete(id);
        for (const request of record.pending) this.requests.delete(request);
        record.pending.clear();
        record.value.peer.onicecandidate = null;
        record.value.peer.onconnectionstatechange = null;
        try { record.value.peer.close(); } catch { /* Already disposed. */ }
        this.send({ type: 'closed', peer: id });
    }
    private messageError = (): void => { this.close(); };
    private receive = ({ data }: MessageEvent<unknown>): void => {
        if (this.disposed || !data || typeof data !== 'object') return;
        const message = data as PeerRequest;
        if (message.type === 'shutdown') { this.close(); return; }
        if (message.type === 'reset-ack') {
            if (message.epoch === this.epoch && this.reset) {
                clearTimeout(this.reset.timer);
                this.reset.resolve(); this.reset = undefined;
            }
            return;
        }
        if (!('peer' in message) || !validPeerId(message.peer)) return;
        if (message.type === 'close') {
            if (message.epoch !== this.epoch) return;
            const peer = this.peers.get(message.peer);
            if (peer) this.retire(message.peer, peer);
            return;
        }
        if ((message.type !== 'create' && message.type !== 'call') || !validRequestId(message.request)) return;
        if (message.epoch !== this.epoch) {
            this.fail(message.request, message.peer, 'The native RTC generation has ended.'); return;
        }
        if (this.requests.has(message.request)) { this.close(); return; }
        if (message.type === 'create') { this.create(message); return; }
        this.call(message);
    };

    private create(message: Extract<PeerRequest, { type: 'create' }>): void {
        const { peer: id, request } = message;
        if (this.peers.has(id) || this.peers.size >= PEER_LIMITS.peers || this.requests.size >= PEER_LIMITS.pending) {
            this.fail(request, id, 'The browser RTC peer limit was exceeded.'); return;
        }
        if (typeof message.nodeType !== 'string' || !/^[DoIMWAmSBCaw]$/.test(message.nodeType)
            || !validIceServers(message.iceServers) || !['all', 'relay'].includes(message.policy)) {
            this.fail(request, id, 'The browser RTC configuration is invalid.'); return;
        }
        let value: BrowserPeer;
        try { value = createNativePeerNow(message.iceServers, message.policy); }
        catch {
            this.fail(request, id, 'The native WebRTC peer could not start.'); return;
        }
        const record: OwnedPeer = { value, candidates: 0, remoteCandidates: 0, pending: new Set() };
        this.peers.set(id, record);
        value.peer.onicecandidate = candidate => {
            if (!this.current(id, record)) return;
            if (candidate && (!validCandidate(candidate) || ++record.candidates > PEER_LIMITS.candidates)) {
                this.retire(id, record); return;
            }
            if (!this.send({ type: 'candidate', peer: id, candidate })) this.close();
        };
        value.peer.onconnectionstatechange = state => {
            if (!this.current(id, record)) return;
            if (!this.send({ type: 'state', peer: id, state })) { this.close(); return; }
            if (state === 'closed' || state === 'failed') this.retire(id, record);
        };
        // Transfer in createDataChannel's task, before any await or send. A
        // native DataChannel transfer failure is explicit; never mediate bytes.
        const transferred = this.send({ type: 'created', request, peer: id, channel: value.channel,
            state: value.peer.connectionState }, [value.channel as unknown as Transferable]);
        if (!transferred) {
            this.fail(request, id, 'This browser cannot transfer native RTC data channels to a DedicatedWorker.');
            try { value.channel.close(); } catch { /* Transfer may have failed after detachment. */ }
            this.retire(id, record);
        }
    }

    private call(message: Extract<PeerRequest, { type: 'call' }>): void {
        const record = this.peers.get(message.peer);
        if (!record) { this.fail(message.request, message.peer, 'The native RTC peer has ended.'); return; }
        if (this.requests.size >= PEER_LIMITS.pending || record.pending.size >= PEER_LIMITS.pendingPerPeer) {
            this.fail(message.request, message.peer, 'The browser RTC control queue is full.'); return;
        }
        const valid = message.operation === 'offer'
            || message.operation === 'local' && validDescription(message.description, 'offer')
            || message.operation === 'remote' && validDescription(message.description, 'answer')
            || message.operation === 'ice' && validCandidate(message.candidate);
        if (!valid) { this.fail(message.request, message.peer, 'The native RTC control request is invalid.'); return; }
        if (message.operation === 'ice' && ++record.remoteCandidates > PEER_LIMITS.candidates) {
            this.fail(message.request, message.peer, 'The native RTC candidate limit was exceeded.');
            this.retire(message.peer, record); return;
        }
        this.requests.add(message.request);
        record.pending.add(message.request);
        void this.execute(message, record);
    }
    private async execute(message: Extract<PeerRequest, { type: 'call' }>, record: OwnedPeer): Promise<void> {
        try {
            let description: RTCSessionDescriptionInit | undefined;
            const peer = record.value.peer;
            switch (message.operation) {
                case 'offer': description = await peer.createOffer(); break;
                case 'local': await peer.setLocalDescription(message.description!); break;
                case 'remote': await peer.setRemoteDescription(message.description!); break;
                case 'ice': await peer.addIceCandidate(message.candidate!); break;
                default: throw new BrowserPeerError('Invalid RTC control operation.');
            }
            if (!this.current(message.peer, record)) return;
            if (description && !validDescription(description, 'offer')) throw new BrowserPeerError('Invalid RTC offer.');
            if (!this.send({ type: 'result', request: message.request, peer: message.peer, description })) this.close();
        } catch {
            if (this.current(message.peer, record)) this.fail(message.request, message.peer, 'The native RTC control operation failed.');
        } finally {
            // A closed generation may have the same request number as a
            // malformed later message; only retire this record's request.
            if (record.pending.delete(message.request)) this.requests.delete(message.request);
        }
    }
}
