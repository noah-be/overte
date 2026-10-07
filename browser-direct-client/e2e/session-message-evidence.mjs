// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Test-only passive observation before façade callbacks. A later disconnected
 * notice cannot erase the first worker failure. Never retains event payloads,
 * generations, source IDs, credentials, SDP or transferred message ports. */
export function observeSessionMessages() {
    const records = []; let evictedWorkers = 0;
    const original = window.Worker;
    const sanitize = value => {
        if (typeof value !== 'string') return undefined;
        if (/\b(password|authorization|secret|sdp|candidate|token)\b/i.test(value)) return '[Sensitive protocol reason omitted]';
        return value.replace(/\b(?:https?|wss?):\/\/[^\s"'<>]+/gi, '[endpoint]')
            .replace(/\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b/gi, '[identifier]').slice(0, 2048);
    };
    if (original) window.Worker = new Proxy(original, {
        construct(target, values, newTarget) {
            const worker = Reflect.construct(target, values, newTarget);
            let path;
            try { path = new URL(values[0], location.href).pathname; } catch { return worker; }
            if (!/(?:^|\/)session-worker(?:[.-]|$)/.test(path)) return worker;
            if (records.length >= 8) { records.shift(); evictedWorkers++; }
            const record = { script: path.split('/').at(-1), events: [], eventCount: 0, evictedEvents: 0, firstFailure: null, terminated: false };
            records.push(record);
            const retain = value => {
                const event = { atMs: performance.now(), ...value }; record.eventCount++;
                if (!record.firstFailure && (event.kind === 'fatal' || event.kind === 'worker-error'
                        || event.kind === 'error' || event.kind === 'status' && event.state === 'error')) record.firstFailure = event;
                if (record.events.length >= 64) { record.events.shift(); record.evictedEvents++; }
                record.events.push(event);
            };
            worker.addEventListener('message', event => {
                const message = event.data;
                if (!message || typeof message !== 'object') return;
                if (message.type === 'fatal') retain({ kind: 'fatal', reason: sanitize(message.message), terminal: message.terminal === true });
                else if (message.type === 'event') {
                    const value = message.event;
                    if (value?.type === 'status' && ['connecting', 'connected', 'disconnected', 'error'].includes(value.state)) {
                        retain({ kind: 'status', state: value.state, reason: sanitize(value.message) });
                    } else if (value?.type === 'error') retain({ kind: 'error', reason: sanitize(value.message) });
                    else if (value?.type === 'microphoneMuted') retain({ kind: 'microphone-muted' });
                }
            });
            worker.addEventListener('error', event => retain({ kind: 'worker-error', reason: sanitize(event.message) }));
            const terminate = worker.terminate;
            worker.terminate = function (...argumentsList) {
                const result = terminate.apply(this, argumentsList); record.terminated = true;
                retain({ kind: 'worker-terminated' }); return result;
            };
            return worker;
        },
    });
    Object.defineProperty(window, 'overteSessionMessageEvidence', { value: () => ({
        observerLimits: { retainedWorkers: 8, retainedEventsPerWorker: 64, evictedWorkers },
        workers: records.map(record => ({ ...record, events: record.events.map(event => ({ ...event })),
            firstFailure: record.firstFailure ? { ...record.firstFailure } : null })),
    }) });
}
