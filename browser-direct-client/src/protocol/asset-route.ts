// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export type AssetDispatchMode = 'direct' | 'page';
export const ASSET_ROUTE_DEADLINE_MS = 5000;
export const ASSET_REVOKE_DEADLINE_MS = 2000;
export const ASSET_REQUEST_LIMIT = 128;
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export class AssetRouteRetirementTimeout extends Error {
    constructor() { super('The asset worker did not acknowledge session retirement.'); }
}

export interface AssetRouteBinding {
    generation: string;
    registration: string;
    sequence: number;
    mode: AssetDispatchMode;
}
export interface AssetRoutingStats {
    mode: AssetDispatchMode;
    directReady: boolean;
    directRequests: number;
    pageRequests: number;
    rejectedRequests: number;
    registrationFailures: number;
    revocations: number;
    pending: number;
}
export const assetDispatchMode = (page: URL): AssetDispatchMode => page.searchParams.get('assetDispatch') === 'page' ? 'page' : 'direct';
export const emptyAssetRoutingStats = (mode: AssetDispatchMode): AssetRoutingStats => ({ mode, directReady: false,
    directRequests: 0, pageRequests: 0, rejectedRequests: 0, registrationFailures: 0, revocations: 0, pending: 0 });
export function validAssetRouteBinding(value: unknown): value is AssetRouteBinding {
    const binding = value as Partial<AssetRouteBinding> | null;
    return !!binding && typeof binding.generation === 'string' && UUID.test(binding.generation)
        && typeof binding.registration === 'string' && UUID.test(binding.registration)
        && Number.isSafeInteger(binding.sequence) && binding.sequence! > 0
        && ['direct', 'page'].includes(binding.mode || '');
}
export function validAssetRoutingStats(value: unknown, mode: AssetDispatchMode): value is AssetRoutingStats {
    const stats = value as Partial<AssetRoutingStats> | null;
    return !!stats && stats.mode === mode && typeof stats.directReady === 'boolean'
        && ['directRequests', 'pageRequests', 'rejectedRequests', 'registrationFailures', 'revocations', 'pending']
            .every(key => Number.isSafeInteger(stats[key as keyof AssetRoutingStats]) && (stats[key as keyof AssetRoutingStats] as number) >= 0)
        && stats.pending! <= ASSET_REQUEST_LIMIT;
}
type AssetEvent = { data: unknown; ports: readonly MessagePort[] };
type Route = AssetRouteBinding & { port: MessagePort; ready: boolean; finishRevoke?: (error?: Error) => void };

/** This control port belongs to one page-created native worker and one exact
 * ServiceWorker registration. Asset bytes still use each fetch's reply port. */
export class WorkerAssetRoute {
    private current?: Route;
    private retirement?: Promise<void>;
    private highestSequence = 0;
    private stats: AssetRoutingStats;
    private localRejections = 0;

    constructor(readonly mode: AssetDispatchMode,
        private readonly fetch: (event: AssetEvent) => void,
        private readonly changed: (generation: string, stats: AssetRoutingStats) => void,
        private readonly failed: (generation: string) => void,
        private readonly revokeDeadline = ASSET_REVOKE_DEADLINE_MS) {
        this.stats = emptyAssetRoutingStats(mode);
    }

    prepare(binding: AssetRouteBinding, port: MessagePort): void {
        if (!validAssetRouteBinding(binding) || binding.mode !== this.mode || binding.sequence <= this.highestSequence
            || this.current || this.retirement) { port.close(); throw new Error('The previous asset route has not retired.'); }
        this.highestSequence = binding.sequence;
        const route: Route = { ...binding, port, ready: false };
        this.current = route; this.localRejections = 0; this.stats = emptyAssetRoutingStats(this.mode);
        port.onmessage = event => this.receive(route, event);
        port.onmessageerror = () => this.closeUnexpected(route);
        port.start(); this.publish(route);
    }

    isReady(generation: string): boolean { return this.current?.generation === generation && this.current.ready; }
    rejected(): void { if (this.current) { ++this.localRejections; this.publish(this.current); } }
    pendingChanged(pending: number): void {
        this.stats.pending = pending;
        if (this.current) this.publish(this.current);
    }

    revoke(): Promise<void> {
        const route = this.current;
        if (!route) return this.retirement || Promise.resolve();
        this.current = undefined; route.ready = false;
        this.stats.directReady = false; ++this.stats.revocations; this.publish(route);
        const retirement = new Promise<void>((resolve, reject) => {
            const timer = setTimeout(() => finish(new AssetRouteRetirementTimeout()), this.revokeDeadline);
            const finish = (error?: Error) => {
                if (route.finishRevoke !== finish) return;
                route.finishRevoke = undefined; clearTimeout(timer);
                route.port.onmessage = null; route.port.onmessageerror = null; route.port.close();
                if (error) reject(error); else resolve();
            };
            route.finishRevoke = finish;
            try { route.port.postMessage({ type: 'overte-atp-route-revoke', ...this.identity(route) }); }
            catch { finish(new Error('The asset request channel ended before retirement.')); }
        });
        this.retirement = retirement;
        void retirement.finally(() => { if (this.retirement === retirement) this.retirement = undefined; }).catch(() => {});
        return retirement;
    }

    dispose(): void {
        const route = this.current;
        if (route) {
            this.current = undefined; route.ready = false;
            try { route.port.postMessage({ type: 'overte-atp-route-revoke', ...this.identity(route) }); } catch { /* Local authority is already revoked. */ }
            route.port.onmessage = null; route.port.onmessageerror = null; route.port.close();
        }
    }

    private receive(route: Route, event: MessageEvent): void {
        const message = event.data as Record<string, unknown> | null;
        const exact = !!message && message.generation === route.generation && message.registration === route.registration
            && message.sequence === route.sequence;
        if (exact && message.type === 'overte-atp-route-revoked') {
            for (const port of event.ports) port.close();
            if (route.finishRevoke) route.finishRevoke();
            else if (this.current === route) {
                this.current = undefined; route.ready = false; this.stats.directReady = false; ++this.stats.revocations;
                route.port.onmessage = null; route.port.onmessageerror = null; route.port.close(); this.publish(route);
            }
            return;
        }
        if (this.current !== route || !exact) { this.rejectPorts(event.ports, route); return; }
        if (message.type === 'overte-atp-route-ready' && !event.ports.length && message.mode === this.mode) {
            route.ready = true; this.stats.directReady = this.mode === 'direct';
            route.port.postMessage({ type: 'overte-atp-route-ready-ack', ...this.identity(route) }); this.publish(route);
        } else if (message.type === 'overte-atp-route-stats' && !event.ports.length
            && Number.isSafeInteger(message.ticket) && validAssetRoutingStats(message.stats, this.mode)) {
            const pending = this.stats.pending;
            this.stats = { ...message.stats, pending }; this.publish(route);
            route.port.postMessage({ type: 'overte-atp-route-stats-ack', ticket: message.ticket, ...this.identity(route) });
        } else if (message.type === 'assetFetch' && this.mode === 'direct' && route.ready && event.ports.length === 1) {
            const request = message.request as { generation?: unknown } | null;
            if (request?.generation !== route.generation) this.rejectPorts(event.ports, route);
            else this.fetch({ data: request, ports: event.ports });
        } else if (message.type === 'overte-atp-route-closed') {
            this.rejectPorts(event.ports, route); this.closeUnexpected(route);
        } else this.rejectPorts(event.ports, route);
    }

    private closeUnexpected(route: Route): void {
        if (this.current !== route) return;
        this.current = undefined; route.ready = false; this.stats.directReady = false; ++this.stats.registrationFailures;
        route.port.onmessage = null; route.port.onmessageerror = null; route.port.close();
        this.publish(route); this.failed(route.generation);
    }
    private rejectPorts(ports: readonly MessagePort[], route: Route): void {
        if (ports.length && this.current === route) this.rejected();
        for (const port of ports) {
            try { port.postMessage({ error: 'The ATP session has ended.' }); } catch { /* A closed requester has no authority. */ }
            port.close();
        }
    }
    private publish(route: Route): void {
        this.changed(route.generation, { ...this.stats, rejectedRequests: this.stats.rejectedRequests + this.localRejections });
    }
    private identity(route: AssetRouteBinding) {
        return { generation: route.generation, registration: route.registration, sequence: route.sequence };
    }
}
