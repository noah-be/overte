// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Test-only observer injected into the actual DedicatedWorker before Join.
 * The entry's passive hook supplies the transferred channel before SDK receive
 * callbacks can deobfuscate it. Payloads, source IDs, HMACs and SDP are omitted.
 * This function is self-contained for Playwright's Worker.evaluate(). */
export function observeWorkerTransport(watchAdditional) {
    const scope = globalThis, records = [], tracked = new WeakSet();
    let evictedChannels = 0;
    const validNodeTypes = new Set(['D', 'o', 'I', 'M', 'W', 'A', 'm', 'S', 'B', 'C', 'a', 'w']);
    const size = value => typeof value === 'string' ? new TextEncoder().encode(value).length
        : typeof Blob === 'function' && value instanceof Blob ? value.size : value?.byteLength || 0;
    Object.defineProperty(scope, 'overteTestOnlyWatchWorkerChannel', {
        value: (channel, nodeType) => {
            if (tracked.has(channel)) return;
            tracked.add(channel);
            if (records.length >= 32) {
                const old = records.shift(); evictedChannels++;
                old.channel.removeEventListener('message', old.receive);
                if (old.channel.send === old.sendWrapper) old.channel.send = old.originalSend;
            }
            const sent = scope.overteTestOnlyHeaderObserverFactory(), received = scope.overteTestOnlyHeaderObserverFactory();
            const record = { channel, nodeType: validNodeTypes.has(nodeType) ? nodeType : null,
                sent, received, sentBytes: 0, receivedBytes: 0, sentMessages: 0, receivedMessages: 0 };
            const originalSend = channel.send;
            const sendWrapper = function (...values) {
                const answer = originalSend.apply(this, values);
                record.sentBytes += size(values[0]); record.sentMessages++; sent.accept(values[0]);
                return answer;
            };
            const receive = event => {
                record.receivedBytes += size(event.data); record.receivedMessages++; received.accept(event.data);
            };
            Object.assign(record, { originalSend, sendWrapper, receive });
            channel.send = sendWrapper;
            channel.addEventListener('message', receive);
            records.push(record);
            if (typeof watchAdditional === 'function') watchAdditional(channel, nodeType);
        },
    });
    Object.defineProperty(scope, 'overteWorkerTransportEvidence', {
        value: () => ({ observerLimits: { retainedChannels: 32, evictedChannels },
            channels: records.map(({ channel, nodeType, sent, received, sentBytes, receivedBytes, sentMessages, receivedMessages }) => ({
                owner: 'session-worker', nodeType, readyState: channel.readyState,
                label: ['label', 'dataChannel'].includes(channel.label) ? channel.label : '[omitted]',
                ordered: channel.ordered, maxRetransmits: channel.maxRetransmits,
                sentBytes, receivedBytes, sentMessages, receivedMessages,
                headers: { sent: sent.snapshot(), received: received.snapshot() },
            })) }),
    });
}
