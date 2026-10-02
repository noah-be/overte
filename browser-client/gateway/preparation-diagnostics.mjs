// SPDX-License-Identifier: Apache-2.0
// No retained stderr or caller-supplied strings are returned to callers.
const PHASES = Object.freeze({ OVERTE_NET_OWNER_READY: 'network-owner-ready', OVERTE_NET_NATIVE_STARTED: 'native-started', OVERTE_UDP_RELAY_READY: 'udp-relay-ready' });
const SIGNALS = new Set(['SIGTERM', 'SIGKILL', 'SIGINT', 'SIGABRT', 'SIGSEGV', 'SIGPIPE']);
export function preparationDiagnostics(expected) {
    const phase = PHASES[expected];
    if (!phase) throw Error('Unknown native preparation phase');
    let tail = '', observedBytes = 0, truncated = false;
    return {
        observe(chunk) {
            if (!Buffer.isBuffer(chunk)) return;
            observedBytes = Math.min(Number.MAX_SAFE_INTEGER, observedBytes + chunk.length);
            truncated ||= observedBytes > 16384;
            tail = (tail + chunk.subarray(Math.max(0, chunk.length - 16384)).toString('utf8')).slice(-16384);
        },
        snapshot(exitCode, signal) {
            let category = 'unclassified-child-exit';
            if (/unshare: (?:unshare failed|write failed).*Operation not permitted/.test(tail)) category = 'namespace-refused';
            else if (/bwrap:.*(?:Operation not permitted|Permission denied)/.test(tail)) category = 'inner-sandbox-refused';
            else if (/Private native network failed: Command .*'ip', 'route', 'add', 'prohibit'/.test(tail)) category = 'deny-route-command-failed';
            else if (/Private native network failed: Private native network initialization timed out/.test(tail)) category = 'interface-initialization-timeout';
            else if (/Private native network failed:.*Cannot (?:bind network supervisor lifetime|own native namespace descendants)/.test(tail)) category = 'supervisor-lifetime-refused';
            else if (/slirp4netns:.*(?:Operation not permitted|Permission denied)|setns.*(?:Operation not permitted|Permission denied)/.test(tail)) category = 'network-helper-refused';
            let routeFailure;
            const marker = /(?:^|\n)OVERTE_NET_ROUTE_FAILURE=(\{[^\n]{1,1536}\})(?:\n|$)/.exec(tail);
            if (marker) { try { routeFailure = safeRouteFailure(JSON.parse(marker[1])); } catch {} }
            return Object.freeze({ phase, category, observedBytes, truncated, ...(routeFailure ? { routeFailure } : {}),
                exitCode: Number.isInteger(exitCode) && exitCode >= 0 && exitCode <= 255 ? exitCode : null,
                signal: SIGNALS.has(signal) ? signal : signal ? 'other-signal' : null });
        }
    };
}

/** Safe test/operator projection; refuses unknown categories and strips extras. */
export function safePreparationDiagnostic(value) {
    const categories = ['unclassified-child-exit', 'namespace-refused', 'inner-sandbox-refused',
        'deny-route-command-failed', 'interface-initialization-timeout', 'supervisor-lifetime-refused', 'network-helper-refused', 'helper-spawn-failed', 'helper-exited-during-preparation'];
    if (!value || typeof value !== 'object' || !Object.values(PHASES).includes(value.phase)
        || !categories.includes(value.category) || !Number.isSafeInteger(value.observedBytes) || value.observedBytes < 0
        || typeof value.truncated !== 'boolean' || !(value.exitCode === null || Number.isInteger(value.exitCode) && value.exitCode >= 0 && value.exitCode <= 255)
        || !(value.signal === null || value.signal === 'other-signal' || SIGNALS.has(value.signal))) return null;
    const out = { phase: value.phase, category: value.category, observedBytes: value.observedBytes,
        truncated: value.truncated, exitCode: value.exitCode, signal: value.signal };
    if (value.routeFailure !== undefined) {
        const route = safeRouteFailure(value.routeFailure);
        if (!route) return null;
        out.routeFailure = route;
    }
    if (value.helperEvents !== undefined) {
        if (!Array.isArray(value.helperEvents) || value.helperEvents.length > 4) return null;
        out.helperEvents = [];
        for (const event of value.helperEvents) {
            if (!event || !['slirp', 'managed-udp'].includes(event.role)
                || !['spawn-error', 'exit'].includes(event.kind) || typeof event.beforeOwnerReady !== 'boolean') return null;
            if (event.kind === 'spawn-error') {
                if (!HELPER_ERRNOS.has(event.errno) && event.errno !== 'other-error') return null;
                out.helperEvents.push({ role: event.role, kind: event.kind, beforeOwnerReady: event.beforeOwnerReady, errno: event.errno });
            } else {
                if (!(event.exitCode === null || Number.isInteger(event.exitCode) && event.exitCode >= 0 && event.exitCode <= 255)
                    || !(event.signal === null || event.signal === 'other-signal' || SIGNALS.has(event.signal))) return null;
                out.helperEvents.push({ role: event.role, kind: event.kind, beforeOwnerReady: event.beforeOwnerReady,
                    exitCode: event.exitCode, signal: event.signal });
            }
        }
    }
    return out;
}

// Fixed labels only. Pipe observations identify preparation ordering, not syscall timing.
const HELPER_ERRNOS = new Set(['ENOENT', 'EACCES', 'ENOEXEC', 'E2BIG', 'EMFILE', 'ENFILE']);
export function helperPreparationDiagnostics() {
    let ownerReady = false, observing = true;
    const events = [], listeners = [];
    function add(event) { if (observing && events.length < 4) events.push(Object.freeze(event)); }
    function spawnFailure(role, error) {
        if (!['slirp', 'managed-udp'].includes(role)) throw Error('Unknown native helper role');
        add({ role, kind: 'spawn-error', beforeOwnerReady: !ownerReady,
            errno: HELPER_ERRNOS.has(error?.code) ? error.code : 'other-error' });
    }
    return {
        ownerReady() { ownerReady = true; },
        spawnFailure,
        watch(role, child) {
            if (!['slirp', 'managed-udp'].includes(role)) throw Error('Unknown native helper role');
            const error = value => spawnFailure(role, value);
            const exit = (code, signal) => add({ role, kind: 'exit', beforeOwnerReady: !ownerReady,
                exitCode: Number.isInteger(code) && code >= 0 && code <= 255 ? code : null,
                signal: SIGNALS.has(signal) ? signal : signal ? 'other-signal' : null });
            child.once('error', error); child.once('exit', exit);
            listeners.push({ child, error, exit });
            return child;
        },
        attach(error, phase) {
            const base = safePreparationDiagnostic(error?.networkPreparation)
                || preparationDiagnostics(phase).snapshot(null, null);
            const helperEvents = Object.freeze(events.map(event => Object.freeze({ ...event })));
            const spawnFailed = helperEvents.some(event => event.kind === 'spawn-error');
            const badExit = helperEvents.some(event => event.kind === 'exit' && (event.exitCode !== 0 || event.signal));
            const category = base.category === 'unclassified-child-exit'
                ? spawnFailed ? 'helper-spawn-failed' : badExit ? 'helper-exited-during-preparation' : base.category
                : base.category;
            const diagnostic = Object.freeze({ ...base, category, helperEvents });
            // Preserve the original failure and tolerate immutable cancellation reasons.
            try { Object.defineProperty(error, 'networkPreparation', { value: diagnostic, enumerable: true, configurable: true }); } catch {}
        },
        stop() {
            observing = false;
            for (const { child, error, exit } of listeners) { child.off('error', error); child.off('exit', exit); }
            listeners.length = 0;
        }
    };
}

function safeRouteFailure(value) {
    const categories = ['permission-denied', 'route-exists', 'network-unreachable', 'invalid-request',
        'missing-route', 'kernel-resource-unavailable', 'unclassified-route-error'];
    if (!value || typeof value !== 'object' || !categories.includes(value.category)
        || !Number.isSafeInteger(value.stderrBytes) || value.stderrBytes < 0 || typeof value.truncated !== 'boolean'
        || !(value.exitCode === null || Number.isInteger(value.exitCode) && value.exitCode >= 0 && value.exitCode <= 255)) return null;
    const out = { category: value.category, stderrBytes: value.stderrBytes, truncated: value.truncated, exitCode: value.exitCode };
    if (value.ownerContext !== undefined) {
        const context = safeOwnerContext(value.ownerContext);
        if (!context) return null;
        out.ownerContext = context;
    }
    return Object.freeze(out);
}

function safeOwnerContext(value) {
    if (!value || !['unavailable', 'unrecognized', 'unconfined', 'unshare', 'unshare-unpriv', 'bwrap', 'unpriv-bwrap', 'bwrap-unpriv-stacked'].includes(value.profile)) return null;
    const out = { profile: value.profile, capabilitySets: {}, netAdmin: {}, namespaceRelations: {} };
    for (const key of ['inheritable', 'permitted', 'effective', 'bounding', 'ambient']) {
        const item = value.capabilitySets?.[key];
        if (!['zero', 'nonzero', 'unavailable', 'invalid'].includes(item)) return null;
        out.capabilitySets[key] = item;
    }
    for (const key of ['permitted', 'effective', 'bounding']) {
        const item = value.netAdmin?.[key];
        if (!['present', 'absent', 'unavailable', 'invalid'].includes(item)) return null;
        out.netAdmin[key] = item;
    }
    for (const key of ['user', 'net']) {
        const item = value.namespaceRelations?.[key];
        if (!['same-as-visible-pid1', 'different-from-visible-pid1', 'unavailable', 'invalid'].includes(item)) return null;
        out.namespaceRelations[key] = item;
    }
    return Object.freeze({ ...out, capabilitySets: Object.freeze(out.capabilitySets), netAdmin: Object.freeze(out.netAdmin), namespaceRelations: Object.freeze(out.namespaceRelations) });
}
