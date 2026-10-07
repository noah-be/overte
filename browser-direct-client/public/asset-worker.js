// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Browser-local ATP transport. Bind one actual WindowClient and generation to
// its owned native worker. Each asset retains its original direct reply port.
self.addEventListener('install', (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
const MIME = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
    gltf: 'model/gltf+json', glb: 'model/gltf-binary', json: 'application/json', js: 'text/javascript',
    fst: 'text/plain', fbx: 'application/octet-stream', ktx: 'image/ktx', ktx2: 'image/ktx2',
    wav: 'audio/wav', mp3: 'audio/mpeg', ogg: 'audio/ogg' };
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const CLIENT_LIMIT = 64, REQUEST_LIMIT = 128, TOTAL_REQUEST_LIMIT = 512, REGISTRATION_DEADLINE = 5000;
const bindings = new Map();
let totalRequests = 0;
const identity = route => ({ generation: route.generation, registration: route.registration, sequence: route.sequence });
const exact = (route, value) => value && route.generation === value.generation
    && route.registration === value.registration && route.sequence === value.sequence;
const closePorts = ports => { for (const port of ports) port.close(); };
const validRegistration = value => value && typeof value.generation === 'string' && UUID.test(value.generation)
    && typeof value.registration === 'string' && UUID.test(value.registration)
    && Number.isSafeInteger(value.sequence) && value.sequence > 0 && ['direct', 'page'].includes(value.mode);
const pageSource = source => {
    if (!source || source.type !== 'window' || typeof source.id !== 'string' || !source.id
        || typeof source.url !== 'string') return null;
    try {
        const url = new URL(source.url), scope = new URL(self.registration.scope);
        return url.origin === scope.origin && url.pathname.startsWith(scope.pathname) ? url : null;
    } catch { return null; }
};
const sendAck = (port, value, ok) => {
    try { port?.postMessage({ type: 'overte-atp-registered', ...identity(value), mode: value.mode, ok }); }
    catch { /* A retired page has no registration authority. */ }
    port?.close();
};
const publishStats = route => {
    if (route.closed || !route.ready) return;
    if (route.statsOutstanding !== undefined) { route.statsDirty = true; return; }
    const ticket = ++route.statsTicket; route.statsOutstanding = ticket; route.statsDirty = false;
    try { route.port.postMessage({ type: 'overte-atp-route-stats', ...identity(route), ticket, stats: { ...route.stats } }); }
    catch { retire(route); }
};
const retire = route => {
    if (!route || route.closed) return;
    route.closed = true; route.ready = false; clearTimeout(route.timer);
    for (const request of [...route.pending]) request.cancel();
    if (route.ack) { sendAck(route.ack, route, false); route.ack = undefined; }
    try { route.port.postMessage({ type: 'overte-atp-route-revoked', ...identity(route) }); }
    catch { /* Worker authority is independently revoked on leave. */ }
    route.port.onmessage = null; route.port.onmessageerror = null; route.port.close();
    const owner = bindings.get(route.clientId);
    if (owner?.current === route) owner.current = undefined;
};
const reapEndedClients = async () => {
    for (const [id, owner] of bindings) {
        if (!await self.clients.get(id) && bindings.get(id) === owner) {
            owner.pending?.cancel(); retire(owner.current); bindings.delete(id);
        }
    }
};
self.addEventListener('message', event => {
    const value = event.data, source = event.source, sourceURL = pageSource(source);
    if (!sourceURL || !value || !['overte-atp-register', 'overte-atp-revoke'].includes(value.type)) {
        closePorts(event.ports); return;
    }
    if (value.type === 'overte-atp-revoke') {
        closePorts(event.ports);
        const owner = bindings.get(source.id), pending = owner?.pending;
        if (!owner || owner.revoking || (!exact(pending || {}, value) && !exact(owner.current || {}, value))) return;
        owner.revoking = true;
        event.waitUntil((async () => {
            let timer;
            try {
                const actual = await Promise.race([self.clients.get(source.id), new Promise((_, reject) => {
                    timer = setTimeout(() => reject(new Error('Expired asset retirement.')), REGISTRATION_DEADLINE);
                })]);
                if (actual && (!pageSource(actual) || actual.url !== source.url || actual.id !== source.id)) return;
                if (owner.pending === pending && pending && exact(pending, value)) pending.cancel();
                if (exact(owner.current || {}, value)) retire(owner.current);
            } catch { /* Worker-side retirement independently closes authority. */ }
            finally { clearTimeout(timer); owner.revoking = false; }
        })());
        return;
    }
    if (!validRegistration(value) || event.ports.length !== 2
        || value.mode !== (sourceURL.searchParams.get('assetDispatch') === 'page' ? 'page' : 'direct')) {
        if (event.ports[1]) sendAck(event.ports[1], value, false);
        closePorts(event.ports); return;
    }
    let owner = bindings.get(source.id);
    if (!owner) {
        if (bindings.size >= CLIENT_LIMIT) { sendAck(event.ports[1], value, false); closePorts(event.ports); event.waitUntil(reapEndedClients()); return; }
        owner = { highestSequence: 0, current: undefined, pending: undefined }; bindings.set(source.id, owner);
    }
    if (value.sequence <= owner.highestSequence) { sendAck(event.ports[1], value, false); closePorts(event.ports); return; }
    owner.highestSequence = value.sequence;
    owner.pending?.cancel();
    let cancellation, registrationTimer;
    const cancelled = new Promise((_, reject) => { cancellation = reject; });
    const token = { ...identity(value), mode: value.mode, cancelled: false, deadline: Date.now() + REGISTRATION_DEADLINE,
        cancel: () => {
            if (token.cancelled) return; token.cancelled = true; clearTimeout(registrationTimer);
            if (owner.pending === token) owner.pending = undefined;
            sendAck(event.ports[1], value, false); closePorts(event.ports); cancellation(new Error('Expired asset registration.'));
        } };
    owner.pending = token;
    registrationTimer = setTimeout(token.cancel, REGISTRATION_DEADLINE);
    event.waitUntil((async () => {
        let route;
        try {
            const actual = await Promise.race([self.clients.get(source.id), cancelled]);
            if (!pageSource(actual) || actual.url !== source.url || actual.id !== source.id
                || bindings.get(source.id) !== owner || owner.pending !== token || token.cancelled) {
                sendAck(event.ports[1], value, false); closePorts(event.ports); return;
            }
            retire(owner.current);
            clearTimeout(registrationTimer);
            route = { ...identity(token), mode: token.mode, clientId: source.id, port: event.ports[0], ack: event.ports[1], ready: false, closed: false,
                pending: new Set(), statsOutstanding: undefined, statsDirty: false, statsTicket: 0,
                stats: { mode: value.mode, directReady: false, directRequests: 0, pageRequests: 0,
                    rejectedRequests: 0, registrationFailures: 0, revocations: 0, pending: 0 } };
            owner.pending = undefined; owner.current = route;
            route.port.onmessage = message => {
                const control = message.data;
                if (!exact(route, control) || route.closed || bindings.get(route.clientId)?.current !== route) { closePorts(message.ports); return; }
                if (control.type === 'overte-atp-route-revoke' && !message.ports.length) { retire(route); return; }
                if (control.type === 'overte-atp-route-ready-ack' && !route.ready && !message.ports.length) {
                    clearTimeout(route.timer); route.ready = true; route.stats.directReady = route.mode === 'direct';
                    sendAck(route.ack, route, true); route.ack = undefined; publishStats(route);
                } else if (control.type === 'overte-atp-route-stats-ack' && control.ticket === route.statsOutstanding && !message.ports.length) {
                    route.statsOutstanding = undefined; if (route.statsDirty) publishStats(route);
                } else closePorts(message.ports);
            };
            route.port.onmessageerror = () => retire(route);
            route.port.start(); route.timer = setTimeout(() => retire(route), Math.max(0, token.deadline - Date.now()));
            route.port.postMessage({ type: 'overte-atp-route-ready', ...identity(route), mode: route.mode });
        } catch {
            if (owner.pending === token) owner.pending = undefined;
            retire(route);
            sendAck(event.ports[1], value, false); closePorts(event.ports);
        } finally { clearTimeout(registrationTimer); if (owner.pending === token) owner.pending = undefined; }
    })());
});
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const scope = new URL(self.registration.scope);
    const prefix = `${scope.pathname}_overte-atp/`;
    if (url.origin !== scope.origin || !url.pathname.startsWith(prefix)) return;
    event.respondWith((async () => {
        const remaining = url.pathname.slice(prefix.length);
        const separator = remaining.indexOf('/');
        const generation = remaining.slice(0, separator);
        const path = remaining.slice(separator + 1) + url.search;
        if (event.request.method !== 'GET' || separator < 1 || !UUID.test(generation)
            || !path || path.length > 4096) return new Response('Invalid ATP asset request.', { status: 400 });
        const client = await self.clients.get(event.clientId);
        if (!pageSource(client) || client.id !== event.clientId) return new Response('The ATP tab session ended.', { status: 410 });
        const route = bindings.get(event.clientId)?.current;
        if (!route || route.closed || !route.ready || route.generation !== generation) {
            return new Response('The ATP session route has ended.', { status: 502 });
        }
        if (route.pending.size >= REQUEST_LIMIT || totalRequests >= TOTAL_REQUEST_LIMIT) {
            ++route.stats.rejectedRequests; publishStats(route);
            return new Response('Too many pending ATP asset requests.', { status: 503 });
        }
        try {
            const data = await new Promise((resolve, reject) => {
                const channel = new MessageChannel();
                let settled = false;
                const finish = (error, data) => {
                    if (settled) return; settled = true;
                    clearTimeout(timeout); channel.port1.close(); route.pending.delete(pending); --totalRequests;
                    route.stats.pending = route.pending.size; publishStats(route);
                    if (error) reject(error); else resolve(data);
                };
                const pending = { cancel: () => finish(new Error('The ATP session has ended.')) };
                const timeout = setTimeout(() => finish(new Error('The ATP session did not answer.')), 25000);
                route.pending.add(pending); ++totalRequests; route.stats.pending = route.pending.size;
                channel.port1.onmessage = ({ data }) => {
                    if (route.closed || bindings.get(event.clientId)?.current !== route || route.generation !== generation) {
                        finish(new Error('The ATP session has ended.')); return;
                    }
                    if (typeof data?.error === 'string' && data.error) finish(new Error(data.error));
                    else if (data?.data instanceof ArrayBuffer) finish(null, data.data);
                    else finish(new Error('Invalid ATP asset reply.'));
                };
                channel.port1.onmessageerror = () => finish(new Error('Invalid ATP asset reply.'));
                const request = { type: 'overte-atp-fetch', generation, path };
                try {
                    if (route.mode === 'direct') {
                        route.port.postMessage({ type: 'assetFetch', ...identity(route), request }, [channel.port2]); ++route.stats.directRequests;
                    } else { client.postMessage(request, [channel.port2]); ++route.stats.pageRequests; }
                    publishStats(route);
                } catch {
                    channel.port2.close(); ++route.stats.rejectedRequests; finish(new Error('The native asset worker is unavailable.'));
                }
            });
            const extension = url.pathname.split('.').pop().toLowerCase();
            return new Response(data, { headers: { 'Content-Type': MIME[extension] || 'application/octet-stream',
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
        } catch (error) {
            return new Response(error.message || 'The ATP asset is unavailable.', { status: 502 });
        }
    })());
});
