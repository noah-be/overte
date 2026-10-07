// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { DirectSession } from './direct-session';
import FingerprintUtils from './protocol/vircadia/domain/networking/FingerprintUtils';
import Uuid from './protocol/vircadia/domain/shared/Uuid';
import { createWorkerPeerFactory } from './protocol/worker-peer-factory';
import { SessionWorkerRuntime } from './protocol/session-worker-runtime';
import { assetDispatchMode } from './protocol/asset-route';

const scope = globalThis as unknown as {
    onmessage: ((event: MessageEvent) => void) | null;
    postMessage(data: unknown, transfer?: Transferable[]): void;
};
let runtime: SessionWorkerRuntime | undefined;
let aspectRatio = 1;
scope.onmessage = event => {
    const message = event.data as { type?: string; pageURL?: string; generation?: string; fingerprint?: string; aspectRatio?: number } | null;
    try {
        if (!runtime && message?.type === 'init') {
            if (!message.pageURL || !message.generation || !message.fingerprint || event.ports.length !== 1) throw new Error('Invalid native worker initialization.');
            const page = new URL(message.pageURL);
            if (!['http:', 'https:'].includes(page.protocol)) throw new Error('Use an HTTP(S) page for the native browser worker.');
            if (!FingerprintUtils.setMachineFingerprint(new Uuid(message.fingerprint))) throw new Error('Invalid anonymous browser fingerprint.');
            aspectRatio = Number.isFinite(message.aspectRatio) ? Math.max(.1, message.aspectRatio!) : 1;
            const nativePeerFactory = createWorkerPeerFactory(event.ports[0]);
            const peerFactory: typeof nativePeerFactory = Object.assign(async (...args: Parameters<typeof nativePeerFactory>) => {
                const connection = await nativePeerFactory(...args);
                // A private Chrome qualification harness may install a passive,
                // bounded header observer. Production exposes no packet data.
                const watch = (globalThis as unknown as {
                    overteTestOnlyWatchWorkerChannel?: (channel: RTCDataChannel, nodeType: string) => void;
                }).overteTestOnlyWatchWorkerChannel;
                if (typeof watch === 'function') watch(connection.channel, args[0]);
                return connection;
            }, { close: () => nativePeerFactory.close() });
            runtime = new SessionWorkerRuntime(callbacks => new DirectSession(callbacks, {
                worker: true, pageURL: page.href, peerFactory, aspectRatio: () => aspectRatio,
                prepareAssetWorker: () => Promise.resolve(),
                navigate: endpoint => callbacks.event({ type: 'navigate', endpoint }),
            }), (data, transfer) => scope.postMessage(data, transfer || []), message.generation, assetDispatchMode(page));
            scope.postMessage({ type: 'ready' });
        } else if (message?.type === 'viewport' && Number.isFinite(message.aspectRatio)) {
            aspectRatio = Math.max(.1, message.aspectRatio!);
        } else runtime?.handle(event);
    } catch (error) {
        for (const port of event.ports) port.close();
        runtime?.dispose();
        scope.postMessage({ type: 'fatal', terminal: true, generation: message?.generation,
            message: `${error instanceof Error ? error.message.slice(0, 2000) : 'The native browser worker failed.'} Reload the page to continue.` });
    }
};
