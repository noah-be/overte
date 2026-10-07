// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Observe real RTC states and native headers without retaining payloads/SDP/credentials. */
export function observeTransport() {
    const peers = [];
    let evictedPeers = 0;
    // Offer contents are hashed only transiently to associate the real signaling
    // node type with its peer. Neither SDP nor the internal hash is emitted.
    const offers = new Map();
    const fingerprint = value => { let hash = 2166136261; for (let index = 0; index < value.length; index++) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619); return hash >>> 0; };
    const validNodeTypes = new Set(['D', 'o', 'I', 'M', 'W', 'A', 'm', 'S', 'B', 'C', 'a', 'w']);
    const websocket = window.WebSocket;
    if (websocket) window.WebSocket = new Proxy(websocket, {
        construct(target, argumentsList, newTarget) {
            const socket = Reflect.construct(target, argumentsList, newTarget), send = socket.send;
            socket.send = function (...values) {
                const answer = send.apply(this, values);
                if (typeof values[0] === 'string' && values[0].length <= 65536) {
                    try {
                        const message = JSON.parse(values[0]), description = message.data?.description;
                        if (validNodeTypes.has(message.to) && description?.type === 'offer' && typeof description.sdp === 'string') {
                            const hash = fingerprint(description.sdp), record = offers.get(hash);
                            if (record) { record.nodeType = message.to; offers.delete(hash); }
                        }
                    } catch { /* Other WebSocket protocols do not belong to this observer. */ }
                }
                return answer;
            };
            return socket;
        },
    });
    const original = window.RTCPeerConnection;
    if (!original) return;
    const size = value => typeof value === 'string' ? new TextEncoder().encode(value).length
        : value instanceof Blob ? value.size : value?.byteLength || 0;
    window.RTCPeerConnection = new Proxy(original, {
        construct(target, argumentsList, newTarget) {
            const peer = Reflect.construct(target, argumentsList, newTarget);
            const channels = [];
            const record = { peer, channels, nodeType: null };
            const createOffer = peer.createOffer;
            peer.createOffer = async function (...values) {
                const offer = await createOffer.apply(this, values);
                if (typeof offer.sdp === 'string') {
                    if (offers.size >= 32) offers.delete(offers.keys().next().value);
                    offers.set(fingerprint(offer.sdp), record);
                }
                return offer;
            };
            const tracked = new WeakSet();
            const watch = channel => {
                if (tracked.has(channel)) return;
                tracked.add(channel);
                if (channels.length >= 4) { record.unobservedChannels = (record.unobservedChannels || 0) + 1; return; }
                const sent = window.overteTestOnlyHeaderObserverFactory?.(), received = window.overteTestOnlyHeaderObserverFactory?.();
                const counters = { channel, sent, received, sentBytes: 0, receivedBytes: 0, sentMessages: 0, receivedMessages: 0 };
                channels.push(counters);
                const send = channel.send;
                channel.send = function (...argumentsList) {
                    const answer = send.apply(this, argumentsList);
                    counters.sentBytes += size(argumentsList[0]); counters.sentMessages++;
                    sent?.accept(argumentsList[0]);
                    return answer;
                };
                channel.addEventListener('message', event => { counters.receivedBytes += size(event.data); counters.receivedMessages++; received?.accept(event.data); });
            };
            const create = peer.createDataChannel;
            peer.createDataChannel = function (...argumentsList) { const channel = create.apply(this, argumentsList); watch(channel); return channel; };
            peer.addEventListener('datachannel', event => watch(event.channel));
            if (peers.length >= 32) { peers.shift(); evictedPeers++; }
            peers.push(record);
            return peer;
        },
    });
    Object.defineProperty(window, 'overteDirectTransportEvidence', {
        value: () => peers.map(({ peer, channels, nodeType, unobservedChannels = 0 }) => ({ nodeType,
            observerLimits: { retainedPeers: 32, evictedPeers, channelsPerPeer: 4, unobservedChannels }, connectionState: peer.connectionState,
            iceConnectionState: peer.iceConnectionState, signalingState: peer.signalingState,
            channels: channels.map(({ channel, sent, received, ...counts }) => ({ ...counts, label: channel.label,
                readyState: channel.readyState, ordered: channel.ordered, maxRetransmits: channel.maxRetransmits,
                ...(sent && received ? { headers: { sent: sent.snapshot(), received: received.snapshot() } } : {}) })) })),
    });
}
