// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted implementation; reviewed changes and validation are recorded in REUSE.md.

/** RTC controls stay in Window; the actual datagram channel can live in a
 * DedicatedWorker together with native verification, ACKs and reassembly. */
export interface BrowserPeerControl {
    readonly connectionState: RTCPeerConnectionState;
    onicecandidate: ((candidate: RTCIceCandidateInit | null) => void) | null;
    onconnectionstatechange: ((state: RTCPeerConnectionState) => void) | null;
    createOffer(): Promise<RTCSessionDescriptionInit>;
    setLocalDescription(description: RTCSessionDescriptionInit): Promise<void>;
    setRemoteDescription(description: RTCSessionDescriptionInit): Promise<void>;
    addIceCandidate(candidate: RTCIceCandidateInit): Promise<void>;
    close(): void;
}
export type BrowserPeer = { peer: BrowserPeerControl; channel: RTCDataChannel };
export type BrowserPeerFactory = (nodeType: string, iceServers: RTCIceServer[],
    policy: RTCIceTransportPolicy, signal?: AbortSignal) => Promise<BrowserPeer>;

/** Fixed, public errors only: native SDP/ICE exceptions may contain secrets. */
export class BrowserPeerError extends Error {}

export const PEER_LIMITS = Object.freeze({
    peers: 16, pending: 64, pendingPerPeer: 8, candidates: 64,
    sdpBytes: 48 * 1024, candidateBytes: 2048, iceServers: 16, urlsPerServer: 16,
});

export type PeerOperation = 'offer' | 'local' | 'remote' | 'ice';
export type PeerRequest =
    | { type: 'create'; epoch: number; request: number; peer: string; nodeType: string; iceServers: RTCIceServer[]; policy: RTCIceTransportPolicy }
    | { type: 'call'; epoch: number; request: number; peer: string; operation: PeerOperation; description?: RTCSessionDescriptionInit; candidate?: RTCIceCandidateInit }
    | { type: 'close'; epoch: number; peer: string }
    | { type: 'reset-ack'; epoch: number }
    | { type: 'shutdown' };
export type PeerResponse =
    | { type: 'created'; request: number; peer: string; channel: RTCDataChannel; state: RTCPeerConnectionState }
    | { type: 'result'; request: number; peer: string; description?: RTCSessionDescriptionInit }
    | { type: 'error'; request: number; peer: string; message: string }
    | { type: 'candidate'; peer: string; candidate: RTCIceCandidateInit | null }
    | { type: 'state'; peer: string; state: RTCPeerConnectionState }
    | { type: 'closed'; peer: string }
    | { type: 'reset'; epoch: number }
    | { type: 'shutdown' };

const encoder = new TextEncoder();
export function validPeerId(value: unknown): value is string {
    return typeof value === 'string' && /^[a-f0-9-]{36}$/.test(value);
}
export function validRequestId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
export function validPeerState(value: unknown): value is RTCPeerConnectionState {
    return ['new', 'connecting', 'connected', 'disconnected', 'failed', 'closed'].includes(value as string);
}
export function validDescription(value: unknown, type?: RTCSdpType): value is RTCSessionDescriptionInit {
    if (!value || typeof value !== 'object') return false;
    const description = value as RTCSessionDescriptionInit;
    return (!type || description.type === type) && ['offer', 'answer'].includes(description.type)
        && typeof description.sdp === 'string' && description.sdp.length <= PEER_LIMITS.sdpBytes
        && encoder.encode(description.sdp).byteLength <= PEER_LIMITS.sdpBytes;
}
export function validCandidate(value: unknown): value is RTCIceCandidateInit {
    if (!value || typeof value !== 'object') return false;
    const candidate = value as RTCIceCandidateInit;
    return typeof candidate.candidate === 'string' && candidate.candidate.length <= PEER_LIMITS.candidateBytes
        && encoder.encode(candidate.candidate).byteLength <= PEER_LIMITS.candidateBytes
        && (candidate.sdpMid == null || typeof candidate.sdpMid === 'string' && candidate.sdpMid.length <= 64)
        && (candidate.sdpMLineIndex == null || Number.isInteger(candidate.sdpMLineIndex)
            && candidate.sdpMLineIndex >= 0 && candidate.sdpMLineIndex <= 65535)
        && (candidate.usernameFragment == null || typeof candidate.usernameFragment === 'string'
            && candidate.usernameFragment.length <= 256);
}
export function validIceServers(value: unknown): value is RTCIceServer[] {
    if (!Array.isArray(value) || value.length > PEER_LIMITS.iceServers) return false;
    return value.every(server => {
        if (!server || typeof server !== 'object') return false;
        const urls = typeof server.urls === 'string' ? [server.urls] : server.urls;
        return Array.isArray(urls) && urls.length > 0 && urls.length <= PEER_LIMITS.urlsPerServer
            && urls.every((url: unknown) => typeof url === 'string' && url.length > 0 && url.length <= 2048)
            && (server.username === undefined || typeof server.username === 'string' && server.username.length <= 512)
            && (server.credential === undefined || typeof server.credential === 'string' && server.credential.length <= 1024);
    });
}

/** Synchronous construction is required for the broker: transfer the returned
 * channel in this same task, before awaiting SDP or invoking send(). */
export function createNativePeerNow(iceServers: RTCIceServer[], policy: RTCIceTransportPolicy): BrowserPeer {
    const native = new RTCPeerConnection({ iceServers, iceTransportPolicy: policy });
    let channel: RTCDataChannel;
    try {
        channel = native.createDataChannel('label', {
            protocol: 'protocol', negotiated: false, ordered: false, maxRetransmits: 0,
        });
    } catch {
        native.close();
        throw new BrowserPeerError('The native WebRTC data channel could not start.');
    }
    let closed = false;
    const control: BrowserPeerControl = {
        get connectionState() { return native.connectionState; },
        onicecandidate: null, onconnectionstatechange: null,
        async createOffer() {
            const offer = await native.createOffer({ offerToReceiveAudio: false, offerToReceiveVideo: false });
            return { type: offer.type, sdp: offer.sdp };
        },
        async setLocalDescription(description) { await native.setLocalDescription(description); },
        async setRemoteDescription(description) { await native.setRemoteDescription(description); },
        async addIceCandidate(candidate) { await native.addIceCandidate(candidate); },
        close() {
            if (closed) return;
            closed = true;
            native.onicecandidate = null; native.onconnectionstatechange = null;
            native.close();
        },
    };
    native.onicecandidate = ({ candidate }) => {
        if (closed) return;
        const plain = candidate ? (typeof candidate.toJSON === 'function' ? candidate.toJSON() : {
            candidate: candidate.candidate, sdpMid: candidate.sdpMid, sdpMLineIndex: candidate.sdpMLineIndex,
            usernameFragment: candidate.usernameFragment,
        }) : null;
        control.onicecandidate?.(plain);
    };
    native.onconnectionstatechange = () => {
        if (!closed) control.onconnectionstatechange?.(native.connectionState);
    };
    return { peer: control, channel };
}

/** Existing main-thread SDK and the renderer-free diagnostic retain native RTC. */
export const createNativeBrowserPeer: BrowserPeerFactory = async (_nodeType, iceServers, policy, signal) => {
    if (signal?.aborted) throw new BrowserPeerError('The native peer creation was cancelled.');
    const result = createNativePeerNow(iceServers, policy);
    const close = () => { result.channel.close(); result.peer.close(); };
    signal?.addEventListener('abort', close, { once: true });
    const nativeClose = result.peer.close;
    result.peer.close = () => {
        signal?.removeEventListener('abort', close);
        nativeClose();
    };
    return result;
};
