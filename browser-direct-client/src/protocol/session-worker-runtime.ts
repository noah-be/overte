// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { DirectSessionClient, SessionCallbacks, SessionEvent } from '../session-contract';
import type { Pose } from '../world-data';
import { SessionEventOutbox } from './session-events';
import { ASSET_REQUEST_LIMIT, AssetRouteRetirementTimeout, WorkerAssetRoute, validAssetRouteBinding,
    type AssetDispatchMode, type AssetRoutingStats } from './asset-route';
import type { AssetFetchLifecycle } from './asset-worker-bridge';

export interface WorkerSessionCore extends DirectSessionClient {
    connect(endpoint: string, generation?: string): Promise<void>;
    assetSessionState(): { admitted: boolean; connected: boolean };
    acceptAssetFetch(event: { data: unknown; ports: readonly MessagePort[] }, lifecycle?: AssetFetchLifecycle): boolean;
}
type WorkerOutput = (data: unknown, transfer?: Transferable[]) => void;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const validGeneration = (value: unknown): value is string => typeof value === 'string' && UUID.test(value);
const reason = (error: unknown) => (error instanceof Error ? error.message : 'The native browser worker failed.').slice(0, 2048);

/** Owns one complete native session. DataChannels, HMAC, ACKs and reassembly
 * belong to the core; only validated results and UI control cross to the page. */
export class SessionWorkerRuntime {
    private readonly outbox: SessionEventOutbox;
    private generation: string;
    private audioPort?: MessagePort;
    private audioEpoch = 0;
    private microphoneMuted = true;
    private readonly playbackPending = new Set<number>();
    private playbackTicket = 0;
    static readonly AUDIO_FRAME_LIMIT = 10;
    private operations = 0;
    private closed = false;
    private retiring = false;
    private overflowing = false;
    private readonly assetRoute?: WorkerAssetRoute;
    private assetRetirement: Promise<void> = Promise.resolve();
    private readonly assetRequests = new Set<{ port: MessagePort; generation: string; current: boolean }>();
    private assetStatsTicket = 0;
    private assetStatsOutstanding?: number;
    private assetStatsLatest?: { generation: string; stats: AssetRoutingStats };
    readonly core: WorkerSessionCore;

    constructor(createCore: (callbacks: SessionCallbacks) => WorkerSessionCore,
        private readonly output: WorkerOutput, generation: string, assetMode?: AssetDispatchMode) {
        if (!validGeneration(generation)) throw new Error('Invalid browser worker generation.');
        this.generation = generation;
        this.outbox = new SessionEventOutbox(message => output(message));
        this.core = createCore({ event: event => this.publish(event), audio: frame => this.playAudio(frame) });
        if (assetMode) this.assetRoute = new WorkerAssetRoute(assetMode, event => this.fetchAsset(event),
            (generation, stats) => { this.assetStatsLatest = { generation, stats }; this.flushAssetStats(); },
            generation => {
                if (this.closed || generation !== this.generation) return;
                this.retireCore(); this.outbox.retire();
                this.output({ type: 'fatal', generation, message: 'The asset request channel ended. Reconnect to continue.' });
            });
    }

    handle(event: { data: unknown; ports: readonly MessagePort[] }): void {
        const message = event.data as Record<string, unknown> | null;
        if (!message || this.closed) { this.closePorts(event.ports); return; }
        if (message.type === 'eventAck' && Number.isSafeInteger(message.ticket)) {
            this.outbox.acknowledge(message.ticket as number); return;
        }
        if (message.type === 'assetRoutingAck' && Number.isSafeInteger(message.ticket)) {
            this.closePorts(event.ports);
            if (message.ticket === this.assetStatsOutstanding) { this.assetStatsOutstanding = undefined; this.flushAssetStats(); }
            return;
        }
        if (message.type === 'assetRoutePrepare') {
            if (!this.assetRoute || !validAssetRouteBinding(message) || event.ports.length !== 1
                || this.core.assetSessionState().admitted) {
                this.closePorts(event.ports); this.reply(message, false, 'Invalid asset route preparation.'); return;
            }
            try { this.assetRoute.prepare(message, event.ports[0]); this.reply(message, true); }
            catch { this.reply(message, false, 'The previous asset route has not retired.'); }
            return;
        }
        if (message.type === 'audioPort') {
            if (event.ports.length !== 1) { this.closePorts(event.ports); return; }
            if (this.audioPort) { this.audioPort.onmessage = null; this.audioPort.onmessageerror = null; this.audioPort.close(); }
            const port = this.audioPort = event.ports[0];
            port.onmessage = event => { if (this.audioPort === port) this.captureAudio(event.data); };
            port.onmessageerror = () => { if (this.audioPort === port) this.resetAudio(); };
            port.start(); this.resetAudio(); return;
        }
        if (message.type === 'assetFetch') {
            if (this.assetRoute?.mode === 'direct') this.rejectAsset(event.ports);
            else this.fetchAsset({ data: message.request, ports: event.ports });
            return;
        }
        if (event.ports.length) this.closePorts(event.ports);
        if (!validGeneration(message.generation)) return;
        if (message.type === 'leave') {
            this.generation = message.generation; this.outbox.retire(); this.resetAudio(); this.retireCore();
            void this.assetRetirement.then(() => this.reply(message, true, { assetRouteAcknowledged: true }), error => {
                // An idle SW context may have disappeared. Local native and
                // reply-port authority is already revoked and the old channel
                // is closed. A subsequent connect still requires a positively
                // acknowledged fresh registration; it cannot use that old port.
                if (error instanceof AssetRouteRetirementTimeout) this.reply(message, true, { assetRouteAcknowledged: false });
                else this.reply(message, false, 'The asset request channel could not retire safely.');
            }).catch(() => {}); return;
        }
        if (message.type === 'connect') {
            if (typeof message.endpoint !== 'string' || message.endpoint.length > 4096) { this.reply(message, false, 'Invalid domain endpoint.'); return; }
            if (this.assetRoute && !this.assetRoute.isReady(message.generation)) { this.reply(message, false, 'The native asset route is not ready.'); return; }
            this.generation = message.generation; this.overflowing = false; this.outbox.retire(); this.resetAudio();
            this.operation(message, () => {
                // Core connect synchronously calls its normal leave before its
                // first await. The page already retired that session; keep the
                // freshly acknowledged route while those cleanup callbacks run.
                this.retiring = true;
                try { return this.core.connect(message.endpoint as string, message.generation as string); }
                finally { this.retiring = false; }
            }); return;
        }
        if (message.generation !== this.generation) { this.reply(message, false, 'The browser session has ended.'); return; }
        if (message.type === 'pose') {
            const pose = message.pose as Pose | undefined;
            if (pose?.position && pose.orientation && pose.velocity) this.core.sendPose(pose);
            this.output({ type: 'poseAck', generation: this.generation, sequence: message.sequence });
        } else if (message.type === 'identity') {
            const identity = message.identity as Parameters<DirectSessionClient['sendIdentity']>[0] | undefined;
            if (identity && typeof identity.displayName === 'string' && typeof identity.skeletonModelURL === 'string') this.core.sendIdentity(identity);
        } else if (message.type === 'interaction' && typeof message.entityId === 'string' && message.entityId.length <= 128) {
            this.core.sendInteraction(message.entityId);
        } else if (message.type === 'audio' && !this.microphoneMuted && this.core.assetSessionState().admitted
            && message.buffer instanceof ArrayBuffer && message.buffer.byteLength === 480) {
            this.core.sendAudio(message.buffer);
        } else if (message.type === 'resolveAsset' && typeof message.asset === 'string' && message.asset.length <= 8192) {
            this.operation(message, () => this.core.resolveAssetSource(message.asset as string));
        }
    }

    dispose(): void {
        if (this.closed) return;
        this.resetAudio(); this.retireCore(); this.audioPort?.close(); this.audioPort = undefined;
        this.assetRoute?.dispose(); this.assetStatsLatest = undefined;
        this.outbox.retire(); this.closed = true;
    }

    private publish(event: SessionEvent): void {
        if (this.closed || this.retiring) return;
        if (event.type === 'microphoneMuted') {
            this.microphoneMuted = true; this.playbackPending.clear();
            this.audioPort?.postMessage({ type: 'mute', muted: true, epoch: ++this.audioEpoch });
        } else if (event.type === 'status' && ['disconnected', 'error'].includes(event.state)) {
            this.resetAudio(); this.cancelAssets(); this.revokeAssetRoute();
        }
        if (!this.outbox.enqueue(this.generation, this.core?.assetSessionState() ?? { admitted: false, connected: false }, event)
            && !this.overflowing) {
            this.overflowing = true; this.resetAudio(); this.retireCore(); this.outbox.retire();
            this.output({ type: 'fatal', generation: this.generation, message: 'The renderer stopped accepting bounded session updates. Reconnect to continue.' });
        }
    }

    private playAudio(buffer: ArrayBuffer): void {
        if (this.closed || buffer.byteLength !== 960 || !this.core.assetSessionState().admitted) return;
        // Playback only uses the directly attached AudioWorklet. Until it is
        // ready, discard live frames rather than queuing PCM on a busy page.
        if (!this.audioPort || this.playbackPending.size >= SessionWorkerRuntime.AUDIO_FRAME_LIMIT) return;
        const ticket = ++this.playbackTicket; this.playbackPending.add(ticket);
        this.audioPort.postMessage({ type: 'pcm', buffer, epoch: this.audioEpoch, ticket }, [buffer]);
    }

    private captureAudio(data: unknown): void {
        const message = data as { type?: unknown; buffer?: unknown; muted?: unknown; epoch?: unknown; ticket?: unknown } | null;
        if (!message || message.epoch !== this.audioEpoch) return;
        if (message.type === 'playbackAck' && Number.isSafeInteger(message.ticket)) {
            this.playbackPending.delete(message.ticket as number); return;
        }
        if (message.type === 'microphoneState' && typeof message.muted === 'boolean') {
            this.microphoneMuted = message.muted; return;
        }
        if (message.type === 'microphone' && Number.isSafeInteger(message.ticket)) {
            this.audioPort?.postMessage({ type: 'microphoneAck', ticket: message.ticket, epoch: this.audioEpoch });
            if (!this.microphoneMuted && this.core.assetSessionState().admitted
                && message.buffer instanceof ArrayBuffer && message.buffer.byteLength === 480) this.core.sendAudio(message.buffer);
        }
    }

    private resetAudio(): void {
        this.microphoneMuted = true;
        this.playbackPending.clear();
        const epoch = ++this.audioEpoch;
        this.audioPort?.postMessage({ type: 'reset', epoch });
    }

    private operation(message: Record<string, unknown>, action: () => Promise<unknown>): void {
        if (!Number.isSafeInteger(message.id) || this.operations >= 32) { this.reply(message, false, 'Too many pending native worker requests.'); return; }
        this.operations++;
        void Promise.resolve().then(async () => {
            if (this.closed || message.generation !== this.generation) throw new Error('The browser session has ended.');
            const value = await action();
            if (this.closed || message.generation !== this.generation) throw new Error('The browser session has ended.');
            return value;
        }).then(value => this.reply(message, true, value), error => this.reply(message, false, reason(error)))
            .finally(() => { this.operations--; }).catch(() => {});
    }

    private reply(message: Record<string, unknown>, ok: boolean, value?: unknown): void {
        if (!Number.isSafeInteger(message.id) || this.closed) return;
        this.output({ type: 'reply', id: message.id, generation: message.generation, ok, ...(ok ? { value } : { error: value }) });
    }
    private retireCore(): void {
        // The page has synchronously cleared its state before sending leave.
        // Reposting these core cleanup callbacks could later replace its error
        // notice with "Disconnected". Native spontaneous errors remain visible.
        this.retiring = true;
        this.cancelAssets(); this.revokeAssetRoute();
        try { this.core.leave(); } finally { this.retiring = false; }
    }
    private fetchAsset(event: { data: unknown; ports: readonly MessagePort[] }): void {
        const request = event.data as { generation?: unknown } | null;
        if (this.closed || event.ports.length !== 1 || request?.generation !== this.generation
            || !this.core.assetSessionState().admitted || this.assetRequests.size >= ASSET_REQUEST_LIMIT) {
            this.rejectAsset(event.ports); return;
        }
        const token = { port: event.ports[0], generation: this.generation, current: true };
        this.assetRequests.add(token); this.assetRoute?.pendingChanged(this.assetRequests.size);
        const settle = () => {
            if (!token.current) return; token.current = false; this.assetRequests.delete(token);
            this.assetRoute?.pendingChanged(this.assetRequests.size);
        };
        try {
            if (!this.core.acceptAssetFetch(event, { isCurrent: () => token.current && !this.closed
                && token.generation === this.generation && this.core.assetSessionState().admitted, onSettled: settle })) {
                token.port.close(); settle();
            }
        } catch { token.port.close(); settle(); }
    }
    private cancelAssets(): void {
        for (const token of this.assetRequests) { token.current = false; token.port.close(); }
        this.assetRequests.clear(); this.assetRoute?.pendingChanged(0);
    }
    private rejectAsset(ports: readonly MessagePort[]): void {
        this.assetRoute?.rejected();
        for (const port of ports) {
            try { port.postMessage({ error: 'The ATP session has ended or its bounded request limit was reached.' }); } catch { /* Requester closed. */ }
            port.close();
        }
    }
    private revokeAssetRoute(): void {
        this.assetRetirement = this.assetRoute?.revoke() || Promise.resolve();
        void this.assetRetirement.catch(() => {});
    }
    private flushAssetStats(): void {
        if (this.closed || this.assetStatsOutstanding !== undefined || !this.assetStatsLatest) return;
        const next = this.assetStatsLatest; this.assetStatsLatest = undefined;
        const ticket = ++this.assetStatsTicket; this.assetStatsOutstanding = ticket;
        this.output({ type: 'assetRouting', ticket, ...next });
    }
    private closePorts(ports: readonly MessagePort[]): void { for (const port of ports) port.close(); }
}
