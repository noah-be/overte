// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Passive, test-only asset dispatch clocks. This installer is self-contained
 * for page init scripts and actual ServiceWorker/DedicatedWorker.evaluate().
 * Native arguments, promises, ports, return values and exceptions are retained.
 * Request strings are used transiently for salted SHA-256 correlation only.
 * Snapshot records belong to the private test collector; publish only the
 * aggregate returned by correlateAssetDispatchEvidence(). No payload is read.
 */
export function installAssetDispatchEvidence(role, privateRunSalt, options = {}) {
    const scope = globalThis;
    const validRoles = ['service-worker', 'page', 'session-worker'];
    const maximumEvents = options.maximumEvents ?? 2048;
    const maximumPendingHashes = options.maximumPendingHashes ?? 64;
    const maximumPorts = options.maximumPorts ?? 512;
    const maximumWorkers = options.maximumWorkers ?? 4;
    const maximumWallSkewMs = 10;
    const limits = { maximumEvents, maximumPendingHashes, maximumPorts, maximumWorkers, maximumWallSkewMs };
    const counters = { observedEvents: 0, retainedEvents: 0, droppedEvents: 0,
        hashErrors: 0, pendingHashes: 0, peakPendingHashes: 0, hashCapacityDrops: 0,
        observerErrors: 0, unmatchedReplyPorts: 0, portCapacityDrops: 0,
        workersObserved: 0, workerCapacityDrops: 0, swPostFailures: 0,
        pagePostFailures: 0, workerReplyFailures: 0, pageRejectReplies: 0,
        replyErrorMarkers: 0, fetchStartFallbacks: 0 };
    const clock = { method: 'performance.timeOrigin + performance.now()', maximumWallSkewMs,
        validSamples: 0, unavailableSamples: 0, invalidSamples: 0, maximumObservedWallSkewMs: null };
    const records = [], cleanups = [], pending = new Set(), ports = new Set();
    const fetches = new WeakMap(), channelPeers = new WeakMap(), workerReplies = new WeakMap(), pageReplies = new WeakMap();
    const workers = new Set();
    let disposed = false, available = true, unavailableReason = null, runBinding = null;
    const kinds = new Set(['fst', 'fbx', 'json', 'image', 'skybox', 'audio', 'other']);
    const unavailable = reason => { available = false; unavailableReason ??= reason; };
    if (!validRoles.includes(role) || typeof privateRunSalt !== 'string'
        || !/^[A-Za-z0-9_-]{16,128}$/.test(privateRunSalt)) unavailable('invalid-installation');
    if ([maximumEvents, maximumPendingHashes, maximumPorts, maximumWorkers].some(value => !Number.isSafeInteger(value) || value < 1)
        || maximumEvents > 8192 || maximumPendingHashes > 256 || maximumPorts > 2048 || maximumWorkers > 8) unavailable('invalid-limits');
    if (typeof scope.crypto?.subtle?.digest !== 'function' || typeof scope.TextEncoder !== 'function') unavailable('digest-unavailable');

    const stamp = () => {
        let origin, relative, wall;
        try { origin = scope.performance?.timeOrigin; relative = scope.performance?.now?.(); wall = scope.Date?.now?.(); }
        catch { clock.unavailableSamples++; return null; }
        if (typeof origin !== 'number' || typeof relative !== 'number' || typeof wall !== 'number') {
            clock.unavailableSamples++; return null;
        }
        const epoch = origin + relative, skew = Math.abs(epoch - wall);
        if (![origin, relative, wall, epoch].every(Number.isFinite) || origin <= 0 || relative < 0 || epoch <= 0 || skew > maximumWallSkewMs) {
            clock.invalidSamples++; return null;
        }
        clock.validSamples++; clock.maximumObservedWallSkewMs = Math.max(clock.maximumObservedWallSkewMs ?? 0, skew);
        return epoch;
    };
    const digest = text => {
        if (disposed || !available || pending.size >= maximumPendingHashes) { counters.hashCapacityDrops++; return Promise.resolve(null); }
        let operation;
        try { operation = scope.crypto.subtle.digest('SHA-256', new scope.TextEncoder().encode(text)); }
        catch { counters.hashErrors++; return Promise.resolve(null); }
        const promise = Promise.resolve(operation).then(buffer => {
            if (!(buffer instanceof scope.ArrayBuffer) || buffer.byteLength !== 32) throw Error('Invalid observer digest');
            return [...new scope.Uint8Array(buffer)].map(value => value.toString(16).padStart(2, '0')).join('');
        }).catch(() => { counters.hashErrors++; return null; }).finally(() => {
            pending.delete(promise); counters.pendingHashes = pending.size;
        });
        pending.add(promise); counters.pendingHashes = pending.size;
        counters.peakPendingHashes = Math.max(counters.peakPendingHashes, pending.size);
        return promise;
    };
    const request = value => {
        try {
            if (!value || typeof value !== 'object') return null;
            // Do not invoke application getters in addition to native cloning.
            const type = Object.getOwnPropertyDescriptor(value, 'type')?.value;
            const generation = Object.getOwnPropertyDescriptor(value, 'generation')?.value;
            const path = Object.getOwnPropertyDescriptor(value, 'path')?.value;
            if (type !== 'overte-atp-fetch' || typeof generation !== 'string'
                || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(generation)
                || typeof path !== 'string' || !path || path.length > 4096) return null;
            const extension = path.split(/[?#]/, 1)[0].split('.').at(-1).toLowerCase();
            const kind = ['fst', 'fbx', 'json'].includes(extension) ? extension
                : ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif', 'svg'].includes(extension) ? 'image'
                : ['exr', 'ktx', 'ktx2'].includes(extension) ? 'skybox'
                : ['wav', 'mp3', 'ogg'].includes(extension) ? 'audio' : 'other';
            return { kind, key: records.length >= maximumEvents ? Promise.resolve(null)
                : digest(`overte-asset-dispatch-request-v1\0${privateRunSalt}\0${generation}\0${path}`) };
        } catch { counters.observerErrors++; return null; }
    };
    const mark = (memo, boundary, epochMs = stamp(), outcome = null) => {
        if (disposed || !memo) return;
        counters.observedEvents++;
        if (records.length >= maximumEvents) { counters.droppedEvents++; return; }
        const record = { key: null, kind: kinds.has(memo.kind) ? memo.kind : 'other', boundary, epochMs, outcome };
        records.push(record); counters.retainedEvents = records.length;
        void memo.key.then(key => { if (!disposed) record.key = key; }).catch(() => { counters.observerErrors++; });
    };
    const replyOutcome = value => {
        try {
            const field = value && typeof value === 'object' ? Object.getOwnPropertyDescriptor(value, 'error') : null;
            return field?.get || field?.set ? 'unavailable' : typeof field?.value === 'string' && field.value.length ? 'error' : 'reply';
        }
        catch { counters.observerErrors++; return 'unavailable'; }
    };
    const envelopeRequest = value => {
        if (!value || typeof value !== 'object') return null;
        return Object.getOwnPropertyDescriptor(value, 'type')?.value === 'assetFetch'
            ? request(Object.getOwnPropertyDescriptor(value, 'request')?.value) : null;
    };
    const replace = (owner, name, wrapper) => {
        const previous = owner[name], descriptor = Object.getOwnPropertyDescriptor(owner, name);
        try {
            Object.defineProperty(owner, name, { configurable: true, enumerable: descriptor?.enumerable ?? false,
                writable: true, value: wrapper });
            if (owner[name] !== wrapper) throw Error('Observer hook unavailable');
            cleanups.push(() => {
                if (owner[name] !== wrapper) return;
                if (descriptor) Object.defineProperty(owner, name, descriptor); else delete owner[name];
            });
            return previous;
        } catch { unavailable('hook-unavailable'); return null; }
    };
    const listen = (target, name, listener) => {
        target.addEventListener(name, listener, { capture: true });
        cleanups.push(() => target.removeEventListener(name, listener, { capture: true }));
    };
    const observeSafely = run => { try { return run(); } catch { counters.observerErrors++; return null; } };
    const transferred = values => {
        if (Array.isArray(values[1])) return values[1];
        const transfer = values[1] && typeof values[1] === 'object' ? Object.getOwnPropertyDescriptor(values[1], 'transfer')?.value : null;
        return Array.isArray(transfer) ? transfer : [];
    };

    const installReplyPosts = mapping => {
        const prototype = scope.MessagePort?.prototype;
        if (!prototype || typeof prototype.postMessage !== 'function') { unavailable('reply-port-hook-unavailable'); return; }
        const original = prototype.postMessage;
        replace(prototype, 'postMessage', function (...values) {
            const memo = mapping.get(this), before = memo ? stamp() : null;
            let result;
            try { result = Reflect.apply(original, this, values); }
            catch (error) {
                if (memo && !disposed) counters[role === 'page' ? 'pagePostFailures' : 'workerReplyFailures']++;
                throw error;
            }
            if (memo) observeSafely(() => {
                const outcome = replyOutcome(values[0]);
                if (outcome === 'error') counters.replyErrorMarkers++;
                mark(memo, role === 'page' ? 'pageRejectReply' : 'workerReplyPost', before, outcome);
                if (role === 'page') counters.pageRejectReplies++;
                mapping.delete(this);
            });
            return result;
        });
    };

    if (available) {
        const binding = digest(`overte-asset-dispatch-run-v1\0${privateRunSalt}`);
        void binding.then(value => { runBinding = value; });
        stamp();
        try {
            if (role === 'page') {
                const serviceWorker = scope.navigator?.serviceWorker, NativeWorker = scope.Worker;
                if (!serviceWorker?.addEventListener || typeof NativeWorker !== 'function') unavailable('page-hook-unavailable');
                else {
                    listen(serviceWorker, 'message', event => observeSafely(() => {
                        const memo = request(event.data); if (!memo) return;
                        mark(memo, 'pageReceive');
                        if (event.ports?.[0]) pageReplies.set(event.ports[0], memo);
                    }));
                    const WorkerObserver = new Proxy(NativeWorker, {
                        construct(target, values, newTarget) {
                            const worker = Reflect.construct(target, values, newTarget);
                            if (disposed) return worker;
                            let path;
                            try { path = new scope.URL(values[0], scope.location.href).pathname; } catch { return worker; }
                            if (!/(?:^|\/)session-worker(?:[.-]|$)/.test(path)) return worker;
                            if (workers.size >= maximumWorkers) { counters.workerCapacityDrops++; return worker; }
                            workers.add(worker); counters.workersObserved++;
                            const original = worker.postMessage;
                            if (typeof original !== 'function') { unavailable('worker-post-hook-unavailable'); return worker; }
                            replace(worker, 'postMessage', function (...argumentsList) {
                                const memo = observeSafely(() => envelopeRequest(argumentsList[0]));
                                const before = memo ? stamp() : null;
                                let result;
                                try { result = Reflect.apply(original, this, argumentsList); }
                                catch (error) { if (memo && !disposed) counters.pagePostFailures++; throw error; }
                                if (memo) mark(memo, 'pageWorkerPost', before);
                                return result;
                            });
                            return worker;
                        },
                    });
                    replace(scope, 'Worker', WorkerObserver); installReplyPosts(pageReplies);
                }
            } else if (role === 'session-worker') {
                if (typeof scope.addEventListener !== 'function') unavailable('worker-receive-hook-unavailable');
                else {
                    listen(scope, 'message', event => observeSafely(() => {
                        const memo = envelopeRequest(event.data); if (!memo) return;
                        mark(memo, 'workerReceive');
                        if (event.ports?.length === 1) workerReplies.set(event.ports[0], memo);
                    }));
                    installReplyPosts(workerReplies);
                }
            } else {
                const NativeChannel = scope.MessageChannel, clientPrototype = scope.Client?.prototype;
                const fetchPrototype = scope.FetchEvent?.prototype;
                if (typeof NativeChannel !== 'function' || typeof clientPrototype?.postMessage !== 'function'
                    || typeof fetchPrototype?.respondWith !== 'function' || typeof scope.addEventListener !== 'function'
                    || !scope.registration?.scope) unavailable('service-worker-hook-unavailable');
                else {
                    const fetchMemo = event => {
                        let memo = fetches.get(event); if (memo) return memo;
                        const url = new scope.URL(event.request.url), registration = new scope.URL(scope.registration.scope);
                        const prefix = `${registration.pathname}_overte-atp/`;
                        if (event.request.method !== 'GET' || url.origin !== registration.origin || !url.pathname.startsWith(prefix)) return null;
                        const rest = url.pathname.slice(prefix.length), separator = rest.indexOf('/');
                        memo = request({ type: 'overte-atp-fetch', generation: rest.slice(0, separator), path: rest.slice(separator + 1) + url.search });
                        if (memo) fetches.set(event, memo); return memo;
                    };
                    listen(scope, 'fetch', event => observeSafely(() => {
                        const memo = fetchMemo(event); if (memo) mark(memo, 'swFetch');
                    }));
                    replace(scope, 'MessageChannel', new Proxy(NativeChannel, {
                        construct(target, values, newTarget) {
                            const channel = Reflect.construct(target, values, newTarget);
                            if (!disposed) channelPeers.set(channel.port2, channel.port1);
                            return channel;
                        },
                    }));
                    const originalPost = clientPrototype.postMessage;
                    replace(clientPrototype, 'postMessage', function (...values) {
                        const memo = observeSafely(() => request(values[0])), before = memo ? stamp() : null;
                        let stop;
                        if (memo) observeSafely(() => {
                            const transfer = transferred(values);
                            const port = transfer.length === 1 ? channelPeers.get(transfer[0]) : undefined;
                            if (!port) { counters.unmatchedReplyPorts++; return; }
                            if (ports.size >= maximumPorts) { counters.portCapacityDrops++; return; }
                            const receive = event => {
                                stop();
                                observeSafely(() => {
                                    const outcome = replyOutcome(event.data);
                                    if (outcome === 'error') counters.replyErrorMarkers++;
                                    mark(memo, 'swReplyReceive', stamp(), outcome);
                                });
                            };
                            stop = () => { port.removeEventListener('message', receive, { capture: true }); ports.delete(stop); };
                            ports.add(stop); port.addEventListener('message', receive, { capture: true, once: true });
                        });
                        let result;
                        try { result = Reflect.apply(originalPost, this, values); }
                        catch (error) { stop?.(); if (memo && !disposed) counters.swPostFailures++; throw error; }
                        if (memo) mark(memo, 'swClientPost', before);
                        return result;
                    });
                    const originalRespond = fetchPrototype.respondWith;
                    replace(fetchPrototype, 'respondWith', function (...values) {
                        const memo = observeSafely(() => {
                            const existing = fetches.has(this), found = fetchMemo(this);
                            if (found && !existing) { counters.fetchStartFallbacks++; mark(found, 'swFetch'); }
                            return found;
                        });
                        const result = Reflect.apply(originalRespond, this, values);
                        if (memo) observeSafely(() => {
                            void Promise.resolve(values[0]).then(response => {
                                const status = typeof response?.status === 'number' ? response.status : null;
                                mark(memo, 'swResponseReady', stamp(), status !== null ? status >= 200 && status < 300 ? 'ok' : 'http-error' : 'unavailable');
                            }, () => mark(memo, 'swResponseReady', stamp(), 'rejected')).catch(() => { counters.observerErrors++; });
                        });
                        return result;
                    });
                }
            }
        } catch { unavailable('hook-installation-failed'); counters.observerErrors++; }
    }

    const snapshot = async () => {
        // There is no request/asset wait here, only already-started bounded hashes.
        await Promise.allSettled([...pending]);
        return { schema: 1, role, available: available && !disposed, unavailableReason: disposed ? 'disposed' : unavailableReason,
            runBinding, limits: { ...limits }, counters: { ...counters },
            clock: { ...clock, status: clock.invalidSamples ? 'invalid' : clock.unavailableSamples ? 'unavailable' : clock.validSamples ? 'valid' : 'unavailable' },
            records: records.map(record => ({ ...record })) };
    };
    const dispose = () => {
        if (disposed) return; disposed = true;
        for (const stop of [...ports]) observeSafely(stop);
        for (const cleanup of cleanups.reverse()) observeSafely(cleanup);
        cleanups.length = 0; workers.clear(); records.length = 0;
    };
    return { snapshot, dispose };
}

/** Correlate private salted request hashes, then discard them from the result.
 * Repeated keys are deliberately ambiguous: observers never add a wire ID and
 * must not assume that rejected/missing requests preserve cross-realm order.
 * Missing observers, clocks and intervals remain unavailable rather than zero.
 */
export function correlateAssetDispatchEvidence(snapshots) {
    const roles = ['service-worker', 'page', 'session-worker'];
    const kinds = ['fst', 'fbx', 'json', 'image', 'skybox', 'audio', 'other'];
    const allowed = {
        'service-worker': ['swFetch', 'swClientPost', 'swReplyReceive', 'swResponseReady'],
        page: ['pageReceive', 'pageWorkerPost', 'pageRejectReply'],
        'session-worker': ['workerReceive', 'workerReplyPost'],
    };
    const edges = {
        serviceWorkerSetup: ['swFetch', 'swClientPost'],
        mainThreadDispatch: ['swClientPost', 'pageReceive'],
        pageForward: ['pageReceive', 'pageWorkerPost'],
        sessionWorkerDispatch: ['pageWorkerPost', 'workerReceive'],
        nativeAssetResolution: ['workerReceive', 'workerReplyPost'],
        directReplyDispatch: ['workerReplyPost', 'swReplyReceive'],
        responseBuild: ['swReplyReceive', 'swResponseReady'],
        totalObserved: ['swFetch', 'swResponseReady'],
    };
    const result = { schema: 1, status: 'unavailable',
        scope: 'Observed dispatch and promise boundaries only; nativeAssetResolution includes native mapping/get/hash waits. No decoder CPU, GPU elapsed time or individual critical path is asserted.',
        replyRoute: 'session-worker directly to service-worker over the transferred reply port',
        crossRealmWallClockCheckBoundMs: 20,
        observers: [], counters: { correlatedRequests: 0, completeRequests: 0, ambiguousKeys: 0,
            invalidRecords: 0, missingStages: 0, invalidIntervals: 0, failedResponses: 0, unavailableResponses: 0,
            incompleteCorrelationKeys: 0, observerLosses: 0 }, phases: {} };
    const empty = reason => ({ available: false, unavailableReason: reason, count: 0, totalMs: null,
        minimumMs: null, maximumMs: null, meanMs: null, p50Ms: null, p95Ms: null, byKind: {} });
    const fail = reason => { for (const name of Object.keys(edges)) result.phases[name] = empty(reason); return result; };
    if (!Array.isArray(snapshots) || snapshots.length !== roles.length) return fail('observer-set-unavailable');
    const selected = new Map();
    const safeNumbers = (source, names) => Object.fromEntries(names.map(name => [name,
        Number.isSafeInteger(source?.[name]) && source[name] >= 0 ? source[name] : null]));
    const counterNames = ['observedEvents', 'retainedEvents', 'droppedEvents', 'hashErrors', 'pendingHashes',
        'peakPendingHashes', 'hashCapacityDrops', 'observerErrors', 'unmatchedReplyPorts', 'portCapacityDrops',
        'workersObserved', 'workerCapacityDrops', 'swPostFailures', 'pagePostFailures', 'workerReplyFailures',
        'pageRejectReplies', 'replyErrorMarkers', 'fetchStartFallbacks'];
    for (const value of snapshots) {
        if (!value || value.schema !== 1 || !roles.includes(value.role) || selected.has(value.role)) return fail('observer-set-unavailable');
        selected.set(value.role, value);
        result.observers.push({ role: value.role, available: value.available === true,
            clockStatus: ['valid', 'invalid', 'unavailable'].includes(value.clock?.status) ? value.clock.status : 'unavailable',
            limits: safeNumbers(value.limits, ['maximumEvents', 'maximumPendingHashes', 'maximumPorts', 'maximumWorkers', 'maximumWallSkewMs']),
            counters: safeNumbers(value.counters, counterNames) });
    }
    if (roles.some(role => !selected.has(role) || selected.get(role).available !== true)) return fail('observer-unavailable');
    const binding = selected.get(roles[0]).runBinding;
    if (typeof binding !== 'string' || !/^[a-f0-9]{64}$/.test(binding)
        || roles.some(role => selected.get(role).runBinding !== binding)) return fail('run-correlation-unavailable');
    if (roles.some(role => selected.get(role).clock?.status !== 'valid')) return fail('clock-unavailable');
    const groups = new Map();
    for (const role of roles) {
        const observer = selected.get(role), records = observer.records;
        if (!Array.isArray(records) || records.length > 8192) return fail('record-set-unavailable');
        for (const name of ['droppedEvents', 'hashCapacityDrops', 'hashErrors', 'observerErrors', 'unmatchedReplyPorts', 'portCapacityDrops', 'workerCapacityDrops']) {
            const count = observer.counters?.[name];
            if (typeof count === 'number' && Number.isSafeInteger(count) && count > 0) result.counters.observerLosses += count;
        }
        for (const record of records) {
            if (!record || typeof record.key !== 'string' || !/^[a-f0-9]{64}$/.test(record.key)) { result.counters.incompleteCorrelationKeys++; continue; }
            if (!kinds.includes(record.kind) || !allowed[role].includes(record.boundary)
                || typeof record.epochMs !== 'number' || !Number.isFinite(record.epochMs) || record.epochMs <= 0) {
                result.counters.invalidRecords++; continue;
            }
            let group = groups.get(record.key);
            if (!group) { group = { kind: record.kind, stages: new Map(), ambiguous: false }; groups.set(record.key, group); }
            if (group.kind !== record.kind || group.stages.has(record.boundary)) group.ambiguous = true;
            else group.stages.set(record.boundary, record);
        }
    }
    const samples = Object.fromEntries(Object.keys(edges).map(name => [name, []]));
    for (const group of groups.values()) {
        if (group.ambiguous) { result.counters.ambiguousKeys++; continue; }
        result.counters.correlatedRequests++;
        const outcome = group.stages.get('swResponseReady')?.outcome;
        if (outcome === 'http-error' || outcome === 'rejected') result.counters.failedResponses++;
        else if (outcome !== 'ok') result.counters.unavailableResponses++;
        let complete = true;
        for (const [name, [before, after]] of Object.entries(edges)) {
            const start = group.stages.get(before), end = group.stages.get(after);
            if (!start || !end) { complete = false; result.counters.missingStages++; continue; }
            const duration = end.epochMs - start.epochMs;
            if (!Number.isFinite(duration) || duration < 0 || duration > 60000) {
                complete = false; result.counters.invalidIntervals++; continue;
            }
            samples[name].push({ duration, kind: group.kind });
        }
        if (complete) result.counters.completeRequests++;
    }
    const summarize = values => {
        if (!values.length) return empty('no-valid-intervals');
        const sorted = values.map(value => value.duration).sort((a, b) => a - b), totalMs = sorted.reduce((a, b) => a + b, 0);
        return { available: true, unavailableReason: null, count: sorted.length, totalMs,
            minimumMs: sorted[0], maximumMs: sorted.at(-1), meanMs: totalMs / sorted.length,
            p50Ms: sorted[Math.max(0, Math.ceil(sorted.length * .5) - 1)], p95Ms: sorted[Math.max(0, Math.ceil(sorted.length * .95) - 1)] };
    };
    for (const [name, values] of Object.entries(samples)) {
        result.phases[name] = { ...summarize(values), byKind: Object.fromEntries(kinds.map(kind => [kind, summarize(values.filter(value => value.kind === kind))])) };
    }
    result.status = result.counters.completeRequests && !result.counters.ambiguousKeys && !result.counters.invalidRecords
        && !result.counters.missingStages && !result.counters.invalidIntervals && !result.counters.incompleteCorrelationKeys && !result.counters.observerLosses ? 'complete'
        : result.counters.correlatedRequests ? 'partial' : 'unavailable';
    return result;
}
