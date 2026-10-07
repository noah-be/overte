// Modified for Overte direct browser compatibility; see docs/browser-direct-client/SDK_PORT.md.
//
//  WebRTCDataChannel.ts
//
//  Created by David Rowe on 21 May 2021.
//  Copyright 2021 Vircadia contributors.
//  Copyright 2021 DigiSomni LLC.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import { NodeTypeValue } from "../NodeType";
import WebRTCSignalingChannel, { SignalingMessage } from "./WebRTCSignalingChannel";
import UDT from "../udt/UDT";
import { BrowserPeerError, createNativeBrowserPeer, type BrowserPeerControl, type BrowserPeerFactory } from "../../../../browser-peer";


type OnOpenCallback = () => void;
type OnMessageCallback = (data: ArrayBuffer) => void;
type OnCloseCallback = () => void;
type OnErrorCallback = (message: string) => void;

type IceServerConfig = {urls: string | Array<string>, username?: string, credential?: string};

/*@sdkdoc
 *  WebRTC ICE server configuration, see https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/RTCPeerConnection#iceservers
 */
type IceServerList = Array<IceServerConfig>;


/*@devdoc
 *  The <code>WebRTCDataChannel</code> class provides an unordered, unreliable WebRTC data channel used for Vircadia protocol
 *  communications with a domain server or assignment client. The Vircadia protocol implements ordering and reliability for
 *  parts of the protocol that require these.
 *  <p>A {@link WebRTCSignalingChannel} is used in the process of establishing the WebRTC connection.</p>
 *  <p>The API is similar to the WebRTCSignalingChannel and WebSocket APIs.</p>
 *  <p>C++: Akin to <code>WebRTCDataChannels</code> though significantly different.
 *
 *  @class WebRTCDataChannel
 *  @param {NodeType} nodeType - The node type to connect to.
 *  @param {WebRTCSignalingChannel} signalingChannel - The WebRTCSignalingChannel to use in establishing the WebRTC connection
 *      and data channel.
 *  @param {IceServerList} iceServers - The list of WebRTC ICE servers used to initiate connections.
 *
 *  @property {WebRTCDataChannel.ReadyState} CONNECTING=0 - The connection is opening.
 *      <em>Static. Read-only.</em>
 *  @property {WebRTCDataChannel.ReadyState} OPEN=1 - The connection is open.
 *      <em>Static. Read-only.</em>
 *  @property {WebRTCDataChannel.ReadyState} CLOSING=2 - The connection is closing.
 *      <em>Static. Read-only.</em>
 *  @property {WebRTCDataChannel.ReadyState} CLOSED=3 - The connection is closed.
 *      <em>Static. Read-only.</em>
 *  @property {WebRTCDataChannel.ReadyState} readyState - The current state of the data channel connection.
 *      <em>Read-only.</em>
 *
 *  @property {number} id -  The data channel ID. The SDK assigns a unique number to each WebRTC data channel, starting at
 *      <code>1</code>.
 *
 *  @property {WebRTCDataChannel~onOpenCallback} onopen - Sets a single function to be called when the data channel opens.
 *      <em>Write-only.</em>
 *  @property {WebRTCDataChannel~onMessageCallback} onmessage - Sets a single function to be called when a message is
 *      received.
 *      <em>Write-only.</em>
 *  @property {WebRTCDataChannel~onErrorCallback} onerror - Sets a single function to be called when an error occurs.
 *      <em>Write-only.</em>
 *  @property {WebRTCDataChannel~onCloseCallback} onclose - Set s a single function to be called when the data channel closes.
 *      <em>Write-only.</em>
 */
class WebRTCDataChannel {
    // C++  Related to WebRTCDataChannels but significantly different.

    /*@devdoc
     *  Called when the data channel opens.
     *  @callback WebRTCDataChannel~onOpenCallback
     */

    /*@devdoc
     *  Called when a message is received.
     *  @callback WebRTCDataChannel~onMessageCallback
     *  @param {ArrayBuffer} message - The message received.
     */

    /*@devdoc
     *  Called when the data channel closes.
     *  @callback WebRTCDataChannel~onCloseCallback
     */

    /*@devdoc
     *  Called when there's an error in the data channel.
     *  @callback WebRTCDataChannel~onErrorCallback
     *  @param {string} message - The error message.
     */


    /*@devdoc
     *  The state of a WebRTCDataChannel connection.
     *  <table>
     *      <thead>
     *          <tr><th>Name</th><th>Value</th><th>Description</th></tr>
     *      </thead>
     *      <tbody>
     *          <tr><td>CONNECTING</td><td>0</td><td>The connection is opening.</td></tr>
     *          <tr><td>OPEN</td><td>1</td><td>The connection is open.</td></tr>
     *          <tr><td>CLOSING</td><td>2</td><td>The connection is closing.</td></tr>
     *          <tr><td>CLOSED</td><td>3</td><td>The connection is closed.</td></tr>
     *      </tbody>
     *  </table>
     *  @typedef {number} WebRTCDataChannel.ReadyState
     */
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;

    static readonly MAX_BUFFERED_BYTES = 1024 * 1024;
    static readonly MAX_ICE_CANDIDATES = 64;
    static readonly MAX_CANDIDATE_BYTES = 2048;
    static readonly MAX_SDP_BYTES = 48 * 1024;

    #_nodeType: NodeTypeValue;
    #_signalingChannel: WebRTCSignalingChannel | null;
    #_peerConnection: BrowserPeerControl | null = null;
    #_peerCreationAbort: AbortController | null = null;
    #_dataChannel: RTCDataChannel | null = null;
    #_offer: RTCSessionDescriptionInit | null = null;
    #_haveSetRemoteDescription = false;
    #_answerStarted = false;
    #_dataChannelID = 0;
    #_readyState = WebRTCDataChannel.CONNECTING;
    #_savedICECandidates: RTCIceCandidateInit[] = [];
    #_candidateCount = 0;
    #_generation = 0;
    #_startTimer: ReturnType<typeof setTimeout> | null = null;
    #_onopenCallback: OnOpenCallback | null = null;
    #_onmessageCallback: OnMessageCallback | null = null;
    #_oncloseCallback: OnCloseCallback | null = null;
    #_onerrorCallback: OnErrorCallback | null = null;

    constructor(nodeType: NodeTypeValue, signalingChannel: WebRTCSignalingChannel, iceServers: IceServerList = [],
        iceTransportPolicy: RTCIceTransportPolicy = "all", private readonly peerFactory: BrowserPeerFactory = createNativeBrowserPeer) {
        this.#_nodeType = nodeType;
        this.#_signalingChannel = signalingChannel;
        // One peer per channel. The historical constructor created an extra peer for logging
        // and then replaced it at startup, leaving that first peer alive on every join.
        const generation = this.#_generation;
        this.#_startTimer = setTimeout(() => {
            this.#_startTimer = null;
            if (generation === this.#_generation && this.#_readyState === WebRTCDataChannel.CONNECTING) {
                void this.#start(iceServers, iceTransportPolicy, generation);
            }
        }, 0);
    }

    get nodeType(): NodeTypeValue { return this.#_nodeType; }
    get readyState(): number { return this.#_readyState; }
    set id(id: number) { this.#_dataChannelID = id; }
    get id(): number { return this.#_dataChannelID; }
    set onopen(callback: OnOpenCallback | null) { this.#_onopenCallback = callback; }
    set onmessage(callback: OnMessageCallback | null) { this.#_onmessageCallback = callback; }
    set onclose(callback: OnCloseCallback | null) { this.#_oncloseCallback = callback; }
    set onerror(callback: OnErrorCallback | null) { this.#_onerrorCallback = callback; }

    addEventListener(_eventName: string, _callback: OnOpenCallback | OnMessageCallback | OnCloseCallback | OnErrorCallback): void {
        this.#_onerrorCallback?.("WebRTCDataChannel.addEventListener() is not implemented.");
    }

    send(message: string | Blob | ArrayBuffer | ArrayBufferView): boolean {
        const channel = this.#_dataChannel;
        if (this.#_readyState !== WebRTCDataChannel.OPEN || !channel || channel.readyState !== "open") return false;
        // This transport carries bounded binary native datagrams only. UDT supplies its own
        // retransmission when a congested DataChannel cannot currently accept another packet.
        if (!(message instanceof ArrayBuffer) && !ArrayBuffer.isView(message)) return false;
        if (message.byteLength < 4 || message.byteLength > UDT.MAX_PACKET_SIZE
            || channel.bufferedAmount + message.byteLength > WebRTCDataChannel.MAX_BUFFERED_BYTES) return false;
        try {
            const bytes = ArrayBuffer.isView(message)
                ? new Uint8Array(message.buffer, message.byteOffset, message.byteLength).slice().buffer : message;
            channel.send(bytes);
            return true;
        } catch {
            this.#terminate("The native data channel could not send a datagram.");
            return false;
        }
    }

    close(): void { this.#terminate(); }

    #isCurrent(peer: BrowserPeerControl, generation: number): boolean {
        return generation === this.#_generation && this.#_peerConnection === peer
            && this.#_readyState !== WebRTCDataChannel.CLOSED;
    }

    #terminate(errorMessage?: string): void {
        if (this.#_readyState === WebRTCDataChannel.CLOSED) return;
        // Invalidate callbacks and async continuations before closing native browser objects.
        ++this.#_generation;
        this.#_readyState = WebRTCDataChannel.CLOSED;
        this.#_peerCreationAbort?.abort(); this.#_peerCreationAbort = null;
        if (this.#_startTimer !== null) clearTimeout(this.#_startTimer);
        this.#_startTimer = null;
        this.#_signalingChannel?.removeEventListener("message", this.#onSignalingChannelMessage);
        this.#_signalingChannel = null;
        const channel = this.#_dataChannel, peer = this.#_peerConnection;
        this.#_dataChannel = null;
        this.#_peerConnection = null;
        this.#_offer = null;
        this.#_savedICECandidates = [];
        if (channel) {
            channel.onopen = null; channel.onmessage = null; channel.onclose = null; channel.onerror = null;
            try { channel.close(); } catch { /* Already closed. */ }
        }
        if (peer) {
            peer.onicecandidate = null; peer.onconnectionstatechange = null;
            try { peer.close(); } catch { /* Already closed. */ }
        }
        if (errorMessage) this.#_onerrorCallback?.(errorMessage);
        else this.#_oncloseCallback?.();
    }

    async #start(iceServers: IceServerList, iceTransportPolicy: RTCIceTransportPolicy, generation: number): Promise<void> {
        const signaling = this.#_signalingChannel;
        if (!signaling || signaling.readyState !== WebRTCSignalingChannel.OPEN) {
            this.#terminate("The native signaling channel is not open.");
            return;
        }
        signaling.addEventListener("message", this.#onSignalingChannelMessage);
        try {
            const creation = new AbortController();
            this.#_peerCreationAbort = creation;
            const { peer, channel } = await this.peerFactory(this.#_nodeType, iceServers, iceTransportPolicy, creation.signal);
            if (generation !== this.#_generation || this.#_signalingChannel !== signaling
                || this.#_readyState === WebRTCDataChannel.CLOSED) {
                channel.close(); peer.close(); return;
            }
            this.#_peerConnection = peer;
            this.#_dataChannel = channel;
            peer.onicecandidate = candidate => {
                if (!this.#isCurrent(peer, generation) || !candidate || signaling.readyState !== WebRTCSignalingChannel.OPEN) return;
                signaling.send({ to: this.#_nodeType, data: { candidate } });
            };
            peer.onconnectionstatechange = () => {
                if (!this.#isCurrent(peer, generation)) return;
                if (["disconnected", "closed"].includes(peer.connectionState)) this.#terminate();
                else if (peer.connectionState === "failed") this.#terminate("The native WebRTC connection failed.");
            };
            channel.binaryType = "arraybuffer";
            const opened = () => {
                if (!this.#isCurrent(peer, generation) || this.#_dataChannel !== channel) return;
                this.#_readyState = WebRTCDataChannel.OPEN;
                this.#_onopenCallback?.();
            };
            channel.onopen = opened;
            channel.onmessage = ({ data }: MessageEvent<unknown>) => {
                if (!this.#isCurrent(peer, generation) || this.#_dataChannel !== channel
                    || this.#_readyState !== WebRTCDataChannel.OPEN || !(data instanceof ArrayBuffer)
                    || data.byteLength < 4 || data.byteLength > UDT.MAX_PACKET_SIZE) return;
                this.#_onmessageCallback?.(data);
            };
            channel.onclose = () => { if (this.#isCurrent(peer, generation)) this.#terminate(); };
            channel.onerror = () => {
                if (this.#isCurrent(peer, generation)) this.#terminate("The native data channel failed.");
            };
            if (!this.#isCurrent(peer, generation)) return;
            if (channel.readyState === "open") opened();
            else if (channel.readyState === "closed") {
                this.#terminate("The native data channel closed before initialization."); return;
            }
            const offer = await peer.createOffer();
            if (!this.#isCurrent(peer, generation) || this.#_signalingChannel !== signaling) return;
            if (!offer.sdp || offer.sdp.length > WebRTCDataChannel.MAX_SDP_BYTES) {
                this.#terminate("The native WebRTC offer exceeds the signaling limit.");
                return;
            }
            this.#_offer = offer;
            // Delay local description until the native answer, so the native peer exists
            // before local ICE gathering begins. Every await retains this exact peer.
            if (!signaling.send({ to: this.#_nodeType, data: { description: offer } })) {
                this.#terminate("The native WebRTC offer could not be signaled.");
            }
        } catch (error) {
            if (generation === this.#_generation) this.#terminate(error instanceof BrowserPeerError
                ? error.message : "The native WebRTC connection could not start.");
        }
    }

    #onSignalingChannelMessage = (message: SignalingMessage): void => {
        const { from, data, echo } = message;
        const peer = this.#_peerConnection, generation = this.#_generation;
        if (from !== this.#_nodeType || !peer || !this.#isCurrent(peer, generation)) return;
        if (data?.["close"] === true) { this.#terminate(); return; }
        if (echo) return;
        void (async () => {
            try {
                const description = data?.["description"] as RTCSessionDescriptionInit | undefined;
                const candidate = data?.["candidate"] as RTCIceCandidateInit | undefined;
                if (description) {
                    if (this.#_answerStarted) return;
                    if (description.type !== "answer" || typeof description.sdp !== "string"
                        || description.sdp.length > WebRTCDataChannel.MAX_SDP_BYTES || !this.#_offer) {
                        this.#terminate("The native signaling answer is invalid.");
                        return;
                    }
                    this.#_answerStarted = true;
                    await peer.setLocalDescription(this.#_offer);
                    if (!this.#isCurrent(peer, generation)) return;
                    await peer.setRemoteDescription(description);
                    if (!this.#isCurrent(peer, generation)) return;
                    this.#_haveSetRemoteDescription = true;
                    const savedCandidates = this.#_savedICECandidates;
                    this.#_savedICECandidates = [];
                    for (const saved of savedCandidates) {
                        if (!this.#isCurrent(peer, generation)) return;
                        await peer.addIceCandidate(saved);
                        if (!this.#isCurrent(peer, generation)) return;
                    }
                } else if (candidate) {
                    if (typeof candidate.candidate !== "string"
                        || candidate.candidate.length > WebRTCDataChannel.MAX_CANDIDATE_BYTES
                        || ++this.#_candidateCount > WebRTCDataChannel.MAX_ICE_CANDIDATES) {
                        this.#terminate("The native ICE signaling limit was exceeded.");
                        return;
                    }
                    if (this.#_haveSetRemoteDescription) {
                        await peer.addIceCandidate(candidate);
                        if (!this.#isCurrent(peer, generation)) return;
                    } else {
                        this.#_savedICECandidates.push(candidate);
                    }
                } else this.#terminate("The native signaling message is invalid.");
            } catch {
                if (this.#isCurrent(peer, generation)) this.#terminate("The native signaling message could not be applied.");
            }
        })();
    };
}

export default WebRTCDataChannel;
export type { IceServerList, IceServerConfig };
