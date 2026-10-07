// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { BrowserIdentity, DirectSessionClient, SessionCallbacks, SessionEvent } from './session-contract';
import type { Pose } from './world-data';
import { MainThreadPeerBroker } from './protocol/rtc-peer-broker';
import { normalizeEndpoint } from './protocol/endpoint';
import { assetDispatchMode, emptyAssetRoutingStats, validAssetRoutingStats,
    type AssetDispatchMode, type AssetRouteBinding, type AssetRoutingStats } from './protocol/asset-route';
import { PageAssetRoute, prepareAssetWorker, type AssetWorkerBinding, type PageAssetRouteLike } from './protocol/asset-route-registration';

type WorkerLike = Pick<Worker, 'postMessage' | 'addEventListener' | 'removeEventListener' | 'terminate'>;
type BrokerLike = Pick<MainThreadPeerBroker, 'closePeers' | 'close'>;
type Pending = { generation: string; resolve(value: unknown): void; reject(error: Error): void; timer: ReturnType<typeof setTimeout> };
export interface WorkerSessionEnvironment {
    pageURL?: string;
    createWorker?: () => WorkerLike;
    createBroker?: (port: MessagePort) => BrokerLike;
    prepareAssets?: () => Promise<void | AssetWorkerBinding>;
    createAssetRoute?: (mode: AssetDispatchMode, prepare: (binding: AssetRouteBinding, port: MessagePort) => Promise<unknown>,
        getWorker: () => Promise<AssetWorkerBinding>) => PageAssetRouteLike;
    fingerprint?: string;
}
const BASE = import.meta.env?.BASE_URL || '/';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** DOM-facing mirror of a complete native session in a DedicatedWorker.
 * Actual DataChannels and protocol bytes stay in that worker. This broker
 * supplies browser-only PeerConnection control, never datagram forwarding. */
export class WorkerDirectSession implements DirectSessionClient {
    private readonly worker: WorkerLike;
    private readonly broker: BrokerLike;
    private readonly page: URL;
    private readonly assetMode: AssetDispatchMode;
    private readonly assetRoute: PageAssetRouteLike;
    private assetWorker?: AssetWorkerBinding;
    private assetBoundGeneration?: string;
    private routingStats: AssetRoutingStats;
    private generation: string = crypto.randomUUID();
    private endpoint = '';
    private admitted = false;
    private ready = false;
    private disposed = false;
    private requestId = 0;
    private readonly pending = new Map<number, Pending>();
    private prepareAssetsPromise?: Promise<void>;
    private leaveBoundary: Promise<void> = Promise.resolve();
    private resolveWorkerReady!: () => void;
    private rejectWorkerReady!: (error: Error) => void;
    private readonly workerReady = new Promise<void>((resolve, reject) => { this.resolveWorkerReady = resolve; this.rejectWorkerReady = reject; });
    private latestPose?: Pose;
    private poseSequence = 0;
    private outstandingPose?: number;
    private readonly readyTimer: ReturnType<typeof setTimeout>;

    constructor(private readonly callbacks: SessionCallbacks, private readonly environment: WorkerSessionEnvironment = {}) {
        this.page = new URL(environment.pageURL || location.href);
        this.assetMode = assetDispatchMode(this.page); this.routingStats = emptyAssetRoutingStats(this.assetMode);
        this.worker = environment.createWorker?.() || new Worker(new URL('./session-worker.ts', import.meta.url), { type: 'module' });
        const prepareRoute = (binding: AssetRouteBinding, port: MessagePort) => this.request('assetRoutePrepare',
            { registration: binding.registration, sequence: binding.sequence, mode: binding.mode }, binding.generation, [port]);
        const getWorker = async () => {
            await this.prepareAssets();
            if (!this.assetWorker) throw new Error('The tab has no current asset worker controller.');
            return this.assetWorker;
        };
        this.assetRoute = environment.createAssetRoute?.(this.assetMode, prepareRoute, getWorker)
            || new PageAssetRoute(this.page, this.assetMode, getWorker, prepareRoute);
        const control = new MessageChannel();
        this.broker = environment.createBroker?.(control.port1) || new MainThreadPeerBroker(control.port1);
        this.worker.addEventListener('message', this.receive);
        this.worker.addEventListener('error', this.workerError);
        this.worker.addEventListener('messageerror', this.workerError);
        this.readyTimer = setTimeout(() => this.fail('The native browser worker did not start. Reload the page.', true), 10000);
        void this.workerReady.catch(() => {});
        this.worker.postMessage({ type: 'init', pageURL: this.page.href, generation: this.generation,
            fingerprint: environment.fingerprint || this.persistedFingerprint(), aspectRatio: this.aspectRatio() }, [control.port2]);
        if (typeof navigator !== 'undefined') {
            navigator.serviceWorker?.addEventListener('message', this.assetFetch);
            navigator.serviceWorker?.addEventListener('controllerchange', this.assetControllerChanged);
        }
        if (typeof window !== 'undefined') window.addEventListener('resize', this.viewportChanged);
    }

    get connected(): boolean { return this.ready; }
    get assetRouting(): AssetRoutingStats { return { ...this.routingStats }; }

    async connect(endpoint: string): Promise<void> {
        if (this.disposed) throw new Error('The native browser worker has ended. Reload the page to continue.');
        const normalized = normalizeEndpoint(endpoint, this.page.href);
        this.leave();
        this.endpoint = normalized;
        this.generation = crypto.randomUUID();
        const generation = this.generation;
        this.callbacks.event({ type: 'status', state: 'connecting', endpoint: normalized,
            message: 'Joining the domain directly and loading its entities…' });
        try {
            await Promise.all([this.workerReady, this.leaveBoundary, this.prepareAssets()]);
            if (this.disposed || generation !== this.generation) throw new Error('The connection attempt was cancelled.');
            await this.assetRoute.prepare(generation);
            if (this.disposed || generation !== this.generation) throw new Error('The connection attempt was cancelled.');
            this.assetBoundGeneration = generation;
            await this.request('connect', { endpoint: normalized }, generation);
        } catch (error) {
            if (generation === this.generation && !this.disposed) this.fail(error instanceof Error ? error.message : 'The direct connection failed.');
            throw error;
        }
    }

    leave(): void {
        if (this.disposed) return;
        this.generation = crypto.randomUUID(); this.ready = false; this.admitted = false;
        this.assetBoundGeneration = undefined; this.assetRoute.cancel(); this.routingStats = emptyAssetRoutingStats(this.assetMode);
        this.latestPose = undefined; this.outstandingPose = undefined;
        for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('The browser session has ended.')); }
        this.pending.clear();
        const generation = this.generation;
        const reset = this.broker.closePeers();
        const leave = this.request('leave', {}, generation);
        this.leaveBoundary = Promise.all([reset, leave]).then(() => {});
        void this.leaveBoundary.catch(() => {});
        this.callbacks.event({ type: 'entities', entities: [] });
        this.callbacks.event({ type: 'avatars', avatars: [] });
        this.callbacks.event({ type: 'status', state: 'disconnected', message: 'Disconnected', endpoint: this.endpoint });
    }

    reconnect(): Promise<void> {
        return this.endpoint ? this.connect(this.endpoint) : Promise.reject(new Error('Select a domain first.'));
    }
    sendPose(pose: Pose): void { if (!this.disposed) { this.latestPose = pose; this.flushPose(); } }
    sendIdentity(identity: BrowserIdentity): void { this.command('identity', { identity }); }
    sendInteraction(entityId: string): void { this.command('interaction', { entityId }); }
    sendAudio(buffer: ArrayBuffer): void {
        if (buffer.byteLength === 480 && this.admitted) this.command('audio', { buffer }, [buffer]);
    }

    assetURL(asset: string): string {
        if (/^atp:/i.test(asset)) {
            if (!this.admitted || this.disposed) throw new Error('ATP assets require an active domain session.');
            const path = asset.replace(/^atp:(?:\/\/)?/i, '').replace(/^\/+/, '');
            if (!path || path.includes('\0') || path.split('/').includes('..')) throw new Error('Invalid ATP asset path.');
            return `${BASE}_overte-atp/${this.generation}/${path}`;
        }
        const url = new URL(asset, this.page);
        if (!['https:', 'http:', 'blob:'].includes(url.protocol)) throw new Error('Unsupported asset URL.');
        return url.href;
    }

    async resolveAssetSource(asset: string): Promise<string> {
        if (!/^atp:/i.test(asset)) {
            const url = new URL(asset, this.page);
            if (url.origin !== this.page.origin || !url.pathname.startsWith(`${BASE}_overte-atp/`)) return asset;
        }
        if (!this.admitted) throw new Error('ATP assets require an active domain session.');
        const generation = this.generation;
        const result = await this.request('resolveAsset', { asset }, generation);
        if (generation !== this.generation || !this.admitted) throw new Error('The ATP session has ended.');
        if (typeof result !== 'string') throw new Error('The native asset worker returned an invalid mapping.');
        return result;
    }

    captureAssetAuthority(): { generation: string; assertCurrent(): void } {
        const generation = this.generation;
        return { generation, assertCurrent: () => {
            if (generation !== this.generation || !this.admitted || this.disposed) throw new Error('The asset session is no longer active.');
        } };
    }

    /** Transfer this endpoint to the owned AudioWorklet. Permission, tracks
     * and UI controls remain on the page; PCM crosses directly to the core. */
    createAudioPort(): MessagePort {
        if (this.disposed) throw new Error('The native browser worker has ended.');
        const channel = new MessageChannel();
        this.worker.postMessage({ type: 'audioPort' }, [channel.port2]);
        return channel.port1;
    }

    dispose(): void {
        if (this.disposed) return;
        this.leave(); this.disposed = true; clearTimeout(this.readyTimer);
        this.broker.close(); this.worker.terminate();
        this.worker.removeEventListener('message', this.receive);
        this.worker.removeEventListener('error', this.workerError);
        this.worker.removeEventListener('messageerror', this.workerError);
        if (typeof navigator !== 'undefined') {
            navigator.serviceWorker?.removeEventListener('message', this.assetFetch);
            navigator.serviceWorker?.removeEventListener('controllerchange', this.assetControllerChanged);
        }
        if (typeof window !== 'undefined') window.removeEventListener('resize', this.viewportChanged);
        for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('The native browser worker has ended.')); }
        this.pending.clear(); this.rejectWorkerReady(new Error('The native browser worker has ended.'));
    }

    private receive = (event: MessageEvent): void => {
        const message = event.data as Record<string, unknown> | null;
        if (!message || this.disposed) return;
        // Bootstrap failure can carry the initialization generation while a
        // join is already waiting with a newer generation. It ends this owned
        // Worker, so retirement cannot depend on session equality.
        if (message.type === 'fatal' && message.terminal === true && typeof message.message === 'string') {
            this.fail(message.message, true); return;
        }
        if (message.type === 'ready') { clearTimeout(this.readyTimer); this.resolveWorkerReady(); return; }
        if (message.type === 'assetRouting' && Number.isSafeInteger(message.ticket)) {
            if (message.generation === this.generation && validAssetRoutingStats(message.stats, this.assetMode)) {
                this.routingStats = { ...message.stats };
            }
            this.worker.postMessage({ type: 'assetRoutingAck', ticket: message.ticket }); return;
        }
        if (message.type === 'reply' && Number.isSafeInteger(message.id)) {
            const pending = this.pending.get(message.id as number);
            if (!pending || pending.generation !== message.generation) return;
            this.pending.delete(message.id as number); clearTimeout(pending.timer);
            if (message.ok === true) pending.resolve(message.value);
            else pending.reject(new Error(typeof message.error === 'string' ? message.error : 'The native worker request failed.'));
            return;
        }
        if (message.type === 'event' && Number.isSafeInteger(message.ticket)) {
            try {
                if (message.generation !== this.generation) return;
                const authority = message.authority as { admitted?: unknown; connected?: unknown } | undefined;
                this.admitted = authority?.admitted === true; this.ready = authority?.connected === true;
                const sessionEvent = message.event as SessionEvent;
                if (sessionEvent.type === 'navigate') {
                    // Entity links use the same page-owned leave/rejoin boundary
                    // as the domain chooser, including peer reset acknowledgment.
                    try { void this.connect(normalizeEndpoint(sessionEvent.endpoint, this.page.href)).catch(() => {}); }
                    catch (error) { this.callbacks.event({ type: 'error', message: error instanceof Error ? error.message : 'Invalid domain link.' }); }
                } else this.callbacks.event(sessionEvent);
            } finally { this.worker.postMessage({ type: 'eventAck', ticket: message.ticket }); }
        } else if (message.generation === this.generation) {
            if (message.type === 'poseAck' && message.sequence === this.outstandingPose) { this.outstandingPose = undefined; this.flushPose(); }
            else if (message.type === 'fatal' && typeof message.message === 'string') this.fail(message.message);
        }
    };

    private workerError = (): void => { this.fail('The native browser worker stopped. Reload the page to continue.', true); };
    private fail(message: string, terminal = false): void {
        if (this.disposed) return;
        if (terminal) { this.rejectWorkerReady(new Error(message)); clearTimeout(this.readyTimer); }
        if (terminal) this.dispose(); else this.leave();
        this.callbacks.event({ type: 'status', state: 'error', message, endpoint: this.endpoint });
        this.callbacks.event({ type: 'error', message });
    }
    private command(type: string, body: Record<string, unknown>, transfer: Transferable[] = []): void {
        if (!this.disposed) this.worker.postMessage({ type, generation: this.generation, ...body }, transfer);
    }
    private request(type: string, body: Record<string, unknown>, generation: string, transfer: Transferable[] = []): Promise<unknown> {
        if (this.disposed || this.pending.size >= 32) return Promise.reject(new Error('Too many pending native worker requests.'));
        const id = ++this.requestId;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('The native browser worker did not finish its request.')); }, 35000);
            this.pending.set(id, { generation, resolve, reject, timer });
            try { this.worker.postMessage({ type, id, generation, ...body }, transfer); }
            catch (error) { clearTimeout(timer); this.pending.delete(id); reject(error instanceof Error ? error : new Error('The native browser worker is unavailable.')); }
        });
    }
    private flushPose(): void {
        if (this.outstandingPose !== undefined || !this.latestPose || this.disposed) return;
        const pose = this.latestPose; this.latestPose = undefined;
        this.outstandingPose = ++this.poseSequence; this.command('pose', { pose, sequence: this.outstandingPose });
    }
    private aspectRatio(): number { return typeof window === 'undefined' ? 1 : Math.max(.1, window.innerWidth / Math.max(1, window.innerHeight)); }
    private viewportChanged = (): void => { this.command('viewport', { aspectRatio: this.aspectRatio() }); };

    private assetFetch = (event: MessageEvent): void => {
        const request = event.data as { type?: unknown; generation?: unknown } | null;
        if (request?.type !== 'overte-atp-fetch' || !event.ports[0]) return;
        const port = event.ports[0];
        if (this.assetMode !== 'page' || event.source !== this.assetWorker?.controller || event.ports.length !== 1
            || !this.admitted || request.generation !== this.generation || this.disposed) {
            port.postMessage({ error: 'The ATP session has ended.' }); port.close(); return;
        }
        try { this.worker.postMessage({ type: 'assetFetch', request }, [port]); }
        catch { port.postMessage({ error: 'The native asset worker is unavailable.' }); port.close(); }
    };
    private prepareAssets(): Promise<void> {
        if (!this.prepareAssetsPromise) {
            const preparation = Promise.resolve().then(() => this.environment.prepareAssets?.() || prepareAssetWorker(this.page, BASE))
                .then(binding => {
                    if (binding && !this.disposed && this.prepareAssetsPromise === preparation) this.assetWorker = binding;
                }).catch(error => {
                    if (this.prepareAssetsPromise === preparation) this.prepareAssetsPromise = undefined;
                    throw error;
                });
            this.prepareAssetsPromise = preparation;
        }
        return this.prepareAssetsPromise;
    }
    private assetControllerChanged = (): void => {
        if (!this.assetWorker || navigator.serviceWorker.controller === this.assetWorker.controller) return;
        this.assetWorker = undefined; this.prepareAssetsPromise = undefined; this.assetRoute.cancel();
        if (this.assetBoundGeneration === this.generation) this.fail('The asset worker controller changed. Reconnect to continue.');
    };
    private persistedFingerprint(): string {
        let fingerprint = crypto.randomUUID();
        try {
            const saved = localStorage.getItem('mfp');
            if (saved && UUID.test(saved) && saved !== '00000000-0000-0000-0000-000000000000') return saved;
            localStorage.setItem('mfp', fingerprint);
        } catch { /* The page can still use a per-visit anonymous identifier. */ }
        return fingerprint;
    }
}
