// Modified for Overte direct browser compatibility; see docs/browser-direct-client/SDK_PORT.md.
//
//  WebRTCSocket.ts
//
//  Created by David Rowe on 28 Jun 2021.
//  Copyright 2021 Vircadia contributors.
//  Copyright 2021 DigiSomni LLC.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import WebRTCDataChannel, { IceServerList } from "./WebRTCDataChannel";
import WebRTCSignalingChannel from "./WebRTCSignalingChannel";
import { NodeTypeValue } from "../NodeType";
import SockAddr from "../SockAddr";
import SignalEmitter, { Signal } from "../../shared/SignalEmitter";
import UDT from "../udt/UDT";
import type { BrowserPeerFactory } from "../../../../browser-peer";


type WebRTCSocketDatagram = { buffer: ArrayBuffer | undefined, sender: SockAddr | undefined };

/** A current native service channel or the shared signaling connection has failed. */
type TransportDisconnection = Readonly<{
    nodeType: NodeTypeValue | null;
    channelID: number | null;
    reason: "signaling-closed" | "signaling-error" | "channel-closed" | "channel-error";
    message?: string;
}>;
type TransportDisconnectedSlot = (event: TransportDisconnection) => void;
type TransportDisconnectedSignal = {
    connect(slot: TransportDisconnectedSlot): void;
    disconnect(slot: TransportDisconnectedSlot): void;
};
type ChannelConnection = {
    channelID: number;
    nodeType: NodeTypeValue;
    webrtcDataChannel: WebRTCDataChannel;
    callbacks: Set<(socketID: number) => void>;
};

/** One native datagram connection per service, through a domain-owned signaling connection. */
class WebRTCSocket {
    static readonly UNCONNECTED = 0;
    static readonly SIGNALING = 1;
    static readonly CONNECTING = 2;
    static readonly CONNECTED = 3;
    static readonly MAX_QUEUED_DATAGRAMS = 4096;
    static readonly MAX_QUEUED_BYTES = 1024 * 1024;
    static readonly MAX_CHANNEL_DATAGRAMS = 256;
    static readonly MAX_CHANNELS = 16;
    static readonly MAX_CONNECTION_CALLBACKS = 16;

    #_webrtcSignalingChannel: WebRTCSignalingChannel | null = null;
    #_webrtcSignalingChannelAddress = "";
    #_webrtcDataChannelsByNodeType = new Map<NodeTypeValue, ChannelConnection>();
    #_webrtcDataChannelsByChannelID = new Map<number, ChannelConnection>();
    #_pendingConnections = new Map<NodeTypeValue, Set<(socketID: number) => void>>();
    // Never reset pseudo ports on leave: an old UDT destination cannot address a later join.
    #_lastDataChannelID = 0;
    #_generation = 0;
    #_receivedQueue: Array<{ channelID: number, message: ArrayBuffer }> = [];
    #_queuedBytes = 0;
    #_queuedByChannel = new Map<number, number>();
    #_readyRead = new SignalEmitter();
    #_disconnectedSlots = new Set<TransportDisconnectedSlot>();
    #_transportDisconnected: TransportDisconnectedSignal = {
        connect: (slot) => { this.#_disconnectedSlots.add(slot); },
        disconnect: (slot) => { this.#_disconnectedSlots.delete(slot); }
    };

    constructor(private readonly iceServers: IceServerList = [],
        private readonly iceTransportPolicy: RTCIceTransportPolicy = "all", private readonly peerFactory?: BrowserPeerFactory) {}

    state(url: string, nodeType: NodeTypeValue): number {
        if (url.trim() !== this.#_webrtcSignalingChannelAddress) return WebRTCSocket.UNCONNECTED;
        const channel = this.#_webrtcDataChannelsByNodeType.get(nodeType)?.webrtcDataChannel;
        if (channel?.readyState === WebRTCDataChannel.OPEN) return WebRTCSocket.CONNECTED;
        if (channel?.readyState === WebRTCDataChannel.CONNECTING) return WebRTCSocket.CONNECTING;
        if (nodeType === NodeTypeValue.DomainServer && this.#_webrtcSignalingChannel
            && [WebRTCSignalingChannel.OPEN, WebRTCSignalingChannel.CONNECTING].includes(this.#_webrtcSignalingChannel.readyState)) {
            return WebRTCSocket.SIGNALING;
        }
        return WebRTCSocket.UNCONNECTED;
    }

    connectToHost(url: string, nodeType: NodeTypeValue, callback: (socketID: number) => void): void {
        const address = url.trim();
        if (address !== this.#_webrtcSignalingChannelAddress) this.abort();
        this.#_webrtcSignalingChannelAddress = address;
        if (!address) return;
        const signaling = this.#_webrtcSignalingChannel;
        if (signaling?.readyState === WebRTCSignalingChannel.OPEN) {
            this.#openWebRTCDataChannel(nodeType, new Set([callback]));
            return;
        }
        if (signaling && signaling.readyState !== WebRTCSignalingChannel.CONNECTING) {
            this.abort();
            this.#_webrtcSignalingChannelAddress = address;
        }
        const callbacks = this.#_pendingConnections.get(nodeType) ?? new Set<(socketID: number) => void>();
        if (callbacks.size >= WebRTCSocket.MAX_CONNECTION_CALLBACKS
            || (!this.#_pendingConnections.has(nodeType) && this.#_pendingConnections.size >= WebRTCSocket.MAX_CHANNELS)) return;
        callbacks.add(callback);
        this.#_pendingConnections.set(nodeType, callbacks);
        if (!this.#_webrtcSignalingChannel) this.#openWebRTCSignalingChannel();
    }

    disconnectFromHost(socketID: number): void {
        const connection = this.#_webrtcDataChannelsByChannelID.get(socketID);
        if (connection) this.#closeWebRTCDataChannel(connection);
        this.#purgeDatagrams(socketID);
    }

    abort(): void {
        ++this.#_generation;
        this.#_pendingConnections.clear();
        for (const channel of [...this.#_webrtcDataChannelsByChannelID.values()]) this.#closeWebRTCDataChannel(channel);
        this.#closeWebRTCSignalingChannel();
        this.#_receivedQueue = [];
        this.#_queuedBytes = 0;
        this.#_queuedByChannel.clear();
        this.#_webrtcSignalingChannelAddress = "";
    }

    hasPendingDatagrams(): boolean { return this.#_receivedQueue.length > 0; }

    readDatagram(datagram: WebRTCSocketDatagram, maxSize = -1): number {
        if (!Number.isSafeInteger(maxSize) || maxSize < -1) return -1;
        const data = this.#_receivedQueue.shift();
        if (!data) return -1;
        this.#_queuedBytes -= data.message.byteLength;
        this.#decrementQueuedChannel(data.channelID);
        const length = maxSize >= 0 ? Math.min(data.message.byteLength, maxSize) : data.message.byteLength;
        datagram.buffer = length === data.message.byteLength ? data.message : data.message.slice(0, length);
        datagram.sender = new SockAddr();
        datagram.sender.setPort(data.channelID);
        return length;
    }

    writeDatagram(datagram: ArrayBuffer | Uint8Array, port: number): number {
        if (datagram.byteLength < 4 || datagram.byteLength > UDT.MAX_PACKET_SIZE) return -1;
        const channel = this.#_webrtcDataChannelsByChannelID.get(port)?.webrtcDataChannel;
        return channel?.send(datagram) ? datagram.byteLength : -1;
    }

    get readyRead(): Signal { return this.#_readyRead.signal(); }
    /** Synchronous: a previous session's close cannot be queued into a later join. */
    get transportDisconnected(): TransportDisconnectedSignal { return this.#_transportDisconnected; }

    #emitDisconnected(event: TransportDisconnection): void {
        const generation = this.#_generation;
        for (const slot of [...this.#_disconnectedSlots]) {
            // A handler may leave and start another session. Do not deliver the old event to it.
            if (generation !== this.#_generation) break;
            slot(Object.freeze(event));
        }
    }

    #openWebRTCSignalingChannel(): void {
        const signaling = new WebRTCSignalingChannel(this.#_webrtcSignalingChannelAddress);
        this.#_webrtcSignalingChannel = signaling;
        const generation = this.#_generation;
        const isCurrent = () => generation === this.#_generation && this.#_webrtcSignalingChannel === signaling;
        signaling.onopen = () => {
            if (!isCurrent()) return;
            const pending = this.#_pendingConnections;
            this.#_pendingConnections = new Map();
            for (const [nodeType, callbacks] of pending) {
                if (!isCurrent()) break;
                this.#openWebRTCDataChannel(nodeType, callbacks);
            }
        };
        const disconnected = (reason: TransportDisconnection["reason"]) => {
            if (!isCurrent()) return;
            this.abort();
            this.#emitDisconnected({ nodeType: null, channelID: null, reason });
        };
        signaling.onclose = () => disconnected("signaling-closed");
        signaling.onerror = () => disconnected("signaling-error");
        if (signaling.readyState === WebRTCSignalingChannel.CLOSED) disconnected("signaling-error");
    }

    #closeWebRTCSignalingChannel(): void {
        const signaling = this.#_webrtcSignalingChannel;
        this.#_webrtcSignalingChannel = null;
        if (!signaling) return;
        signaling.onopen = () => {}; signaling.onclose = () => {}; signaling.onerror = () => {};
        signaling.close();
    }

    #openWebRTCDataChannel(nodeType: NodeTypeValue, callbacks: Set<(socketID: number) => void>): void {
        const signaling = this.#_webrtcSignalingChannel;
        if (!signaling || signaling.readyState !== WebRTCSignalingChannel.OPEN) return;
        const existing = this.#_webrtcDataChannelsByNodeType.get(nodeType);
        if (existing) {
            if (existing.webrtcDataChannel.readyState === WebRTCDataChannel.OPEN) {
                for (const callback of callbacks) callback(existing.channelID);
            } else {
                for (const callback of callbacks) {
                    if (existing.callbacks.size < WebRTCSocket.MAX_CONNECTION_CALLBACKS) existing.callbacks.add(callback);
                }
            }
            return;
        }
        if (this.#_webrtcDataChannelsByChannelID.size >= WebRTCSocket.MAX_CHANNELS || this.#_lastDataChannelID >= 65535) return;
        const webrtcDataChannel = new WebRTCDataChannel(nodeType, signaling, this.iceServers, this.iceTransportPolicy, this.peerFactory);
        const connection: ChannelConnection = { channelID: ++this.#_lastDataChannelID, nodeType, webrtcDataChannel, callbacks };
        webrtcDataChannel.id = connection.channelID;
        this.#_webrtcDataChannelsByNodeType.set(nodeType, connection);
        this.#_webrtcDataChannelsByChannelID.set(connection.channelID, connection);
        const generation = this.#_generation;
        const isCurrent = () => generation === this.#_generation
            && this.#_webrtcDataChannelsByChannelID.get(connection.channelID) === connection
            && this.#_webrtcDataChannelsByNodeType.get(nodeType) === connection;
        webrtcDataChannel.onopen = () => {
            if (!isCurrent()) return;
            const openedCallbacks = [...connection.callbacks];
            connection.callbacks.clear();
            for (const callback of openedCallbacks) {
                if (!isCurrent()) break;
                callback(connection.channelID);
            }
        };
        webrtcDataChannel.onmessage = (message) => {
            if (!isCurrent() || webrtcDataChannel.readyState !== WebRTCDataChannel.OPEN
                || message.byteLength < 4 || message.byteLength > UDT.MAX_PACKET_SIZE
                || this.#_receivedQueue.length >= WebRTCSocket.MAX_QUEUED_DATAGRAMS
                || this.#_queuedBytes + message.byteLength > WebRTCSocket.MAX_QUEUED_BYTES
                || (this.#_queuedByChannel.get(connection.channelID) ?? 0) >= WebRTCSocket.MAX_CHANNEL_DATAGRAMS) return;
            const wasEmpty = this.#_receivedQueue.length === 0;
            this.#_receivedQueue.push({ channelID: connection.channelID, message });
            this.#_queuedBytes += message.byteLength;
            this.#_queuedByChannel.set(connection.channelID, (this.#_queuedByChannel.get(connection.channelID) ?? 0) + 1);
            if (wasEmpty) this.#_readyRead.emit();
        };
        const disconnected = (reason: TransportDisconnection["reason"], message?: string) => {
            if (!isCurrent()) return;
            this.#closeWebRTCDataChannel(connection);
            this.#emitDisconnected({ nodeType, channelID: connection.channelID, reason, message });
        };
        webrtcDataChannel.onclose = () => disconnected("channel-closed");
        webrtcDataChannel.onerror = (message) => disconnected("channel-error", message);
    }

    #closeWebRTCDataChannel(connection: ChannelConnection): void {
        if (this.#_webrtcDataChannelsByChannelID.get(connection.channelID) !== connection) return;
        this.#_webrtcDataChannelsByChannelID.delete(connection.channelID);
        if (this.#_webrtcDataChannelsByNodeType.get(connection.nodeType) === connection) {
            this.#_webrtcDataChannelsByNodeType.delete(connection.nodeType);
        }
        connection.callbacks.clear();
        this.#purgeDatagrams(connection.channelID);
        const channel = connection.webrtcDataChannel;
        channel.onopen = null; channel.onmessage = null; channel.onclose = null; channel.onerror = null;
        channel.close();
    }

    #decrementQueuedChannel(channelID: number): void {
        const count = (this.#_queuedByChannel.get(channelID) ?? 1) - 1;
        if (count > 0) this.#_queuedByChannel.set(channelID, count);
        else this.#_queuedByChannel.delete(channelID);
    }

    #purgeDatagrams(channelID: number): void {
        this.#_receivedQueue = this.#_receivedQueue.filter((datagram) => {
            if (datagram.channelID !== channelID) return true;
            this.#_queuedBytes -= datagram.message.byteLength;
            return false;
        });
        this.#_queuedByChannel.delete(channelID);
    }
}

export default WebRTCSocket;
export type { WebRTCSocketDatagram, TransportDisconnection, TransportDisconnectedSignal };
