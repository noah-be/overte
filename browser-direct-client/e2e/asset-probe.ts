// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-only entry: real admission/asset code without renderer work or automatic
// scene asset requests. It is excluded from the normal production build.
import { WorkerDirectSession } from '../src/worker-direct-session';
import type { ConnectionState } from '../src/session-contract';

const evidence = { state: 'disconnected' as ConnectionState, entityCount: 0,
    avatarCount: 0, audioFrames: 0, lastError: '', explicitAssetRequests: 0 };
const session = new WorkerDirectSession({
    event(event) {
        if (event.type === 'status') evidence.state = event.state;
        if (event.type === 'entities') evidence.entityCount = event.entities.length;
        if (event.type === 'avatars') evidence.avatarCount = event.avatars.length;
        if (event.type === 'error') evidence.lastError = event.message;
    },
    audio() { evidence.audioFrames++; },
});

const probe = Object.freeze({
    async join(endpoint: string) { await session.connect(endpoint); return { ...evidence }; },
    async fetch(asset: string) {
        if (!asset.startsWith('atp:/')) throw new Error('This diagnostic requires a real native ATP asset.');
        evidence.explicitAssetRequests++;
        const started = performance.now();
        try {
            const response = await fetch(session.assetURL(asset));
            if (!response.ok) return { status: response.status, elapsedMs: performance.now() - started,
                error: (await response.text()).slice(0, 500) };
            const bytes = await response.arrayBuffer();
            const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
            const sha256 = [...digest].map(byte => byte.toString(16).padStart(2, '0')).join('');
            return { status: response.status, bytes: bytes.byteLength, sha256, elapsedMs: performance.now() - started };
        } catch (error) {
            return { status: 0, elapsedMs: performance.now() - started,
                error: error instanceof Error ? error.message : 'The native asset request failed.' };
        }
    },
    leave() { session.leave(); return this.state(); },
    state() { return { ...evidence, assetRouting: session.assetRouting,
        transportOwnership: 'Actual dedicated session worker; no renderer or model loaders' }; },
});
Object.defineProperty(window, 'overteAssetProbe', { value: probe });
window.addEventListener('pagehide', () => session.dispose(), { once: true });
