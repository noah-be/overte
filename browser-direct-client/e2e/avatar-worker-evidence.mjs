// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Optional test-only composition. Originals keep their arguments, transfer
 * lists, return values and exceptions. No packet forwarding or auth changes. */
export function observeAvatarWorker(expectedNativeID) {
    const scope = globalThis, channels = [], tracked = new WeakSet();
    const events = scope.overteTestOnlyAvatarEventFactory(expectedNativeID);
    let observerErrors = 0, evictedChannels = 0;
    const originalPost = scope.postMessage;
    scope.postMessage = function (...argumentsList) {
        try { if (argumentsList[0]?.type === 'event') events.accept(argumentsList[0].event); }
        catch { observerErrors++; }
        return originalPost.apply(this, argumentsList);
    };
    Object.defineProperty(scope, 'overteAvatarWorkerEvidence', { value: () => ({ observerErrors,
        observationBeforeSDKReceive: true, outgoingEventBoundary: 'Worker global postMessage immediately before actual dispatch',
        channelLimits: { retainedChannels: 4, evictedChannels }, sourceEvents: events.snapshot(),
        channels: channels.map(({ channel, observer }) => ({ nodeType: 'W', readyState: channel.readyState, received: observer.snapshot() })) }) });
    return (channel, nodeType) => {
        if (nodeType !== 'W' || tracked.has(channel)) return;
        tracked.add(channel);
        if (channels.length >= 4) { const old = channels.shift(); old.channel.removeEventListener('message', old.receive); evictedChannels++; }
        const observer = scope.overteTestOnlyAvatarReceiveFactory(expectedNativeID);
        const receive = event => { try { observer.accept(event.data); } catch { observerErrors++; } };
        channel.addEventListener('message', receive); channels.push({ channel, receive, observer });
    };
}
