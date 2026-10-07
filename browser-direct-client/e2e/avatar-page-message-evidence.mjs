// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Test-only actual page Worker message observation. This does not instrument
 * or claim the private WorkerDirectSession callback. It sends no ACK/messages. */
export function observeAvatarPageMessages(expectedNativeID) {
    const scope = window, original = scope.Worker, records = [];
    let evictedWorkers = 0, observerErrors = 0;
    scope.Worker = new Proxy(original, {
        construct(target, values, newTarget) {
            const worker = Reflect.construct(target, values, newTarget);
            let path;
            try { path = new URL(values[0], location.href).pathname; } catch { return worker; }
            if (!/(?:^|\/)session-worker(?:[.-]|$)/.test(path)) return worker;
            if (records.length >= 8) { const old = records.shift(); old.worker.removeEventListener('message', old.receive); evictedWorkers++; }
            const observer = scope.overteTestOnlyAvatarEventFactory(expectedNativeID);
            const receive = event => {
                try { if (event.data?.type === 'event') observer.accept(event.data.event); }
                catch { observerErrors++; }
            };
            worker.addEventListener('message', receive); records.push({ worker, observer, receive });
            return worker;
        },
    });
    Object.defineProperty(scope, 'overteAvatarPageMessageEvidence', { value: () => ({
        boundary: 'Actual page Worker message event observed; not a facade callback assertion',
        observerErrors, limits: { retainedWorkers: 8, evictedWorkers }, workers: records.map(record => record.observer.snapshot()) }) });
}
