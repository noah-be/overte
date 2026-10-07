// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { ASSET_ROUTE_DEADLINE_MS, type AssetDispatchMode, type AssetRouteBinding } from './asset-route';

export interface AssetWorkerBinding {
    controller: Pick<ServiceWorker, 'postMessage' | 'scriptURL' | 'state'>;
    registration: Pick<ServiceWorkerRegistration, 'active' | 'scope'>;
}
export interface PageAssetRouteLike {
    prepare(generation: string): Promise<void>;
    cancel(): void;
}

/** Readiness means this tab is controlled by this exact active worker, rather
 * than an unrelated ready registration elsewhere on the same origin. */
export async function prepareAssetWorker(page: URL, base: string): Promise<AssetWorkerBinding> {
    if (!navigator.serviceWorker) throw new Error('Use HTTPS or localhost so domain assets can load in the browser.');
    const script = new URL(`${base}asset-worker.js`, page), scope = new URL(base, page);
    const deadline = Date.now() + 10000;
    let registrationTimer!: ReturnType<typeof setTimeout>;
    const registration = await Promise.race([navigator.serviceWorker.register(script.href, { scope: scope.href }),
        new Promise<never>((_, reject) => { registrationTimer = setTimeout(() => reject(new Error('The browser asset worker did not activate. Reload the page.')), 10000); })])
        .finally(() => clearTimeout(registrationTimer));
    const container = navigator.serviceWorker;
    await new Promise<void>((resolve, reject) => {
        const observed = new Set<ServiceWorker>();
        const cleanup = () => {
            clearTimeout(timer); container.removeEventListener('controllerchange', check);
            registration.removeEventListener('updatefound', check);
            for (const worker of observed) worker.removeEventListener('statechange', check);
        };
        const check = () => {
            for (const worker of [registration.installing, registration.waiting, registration.active]) {
                if (worker && !observed.has(worker)) { observed.add(worker); worker.addEventListener('statechange', check); }
            }
            const active = registration.active, controller = container.controller;
            if (active?.state === 'activated' && controller === active && active.scriptURL === script.href
                && registration.scope === scope.href) { cleanup(); resolve(); }
        };
        const timer = setTimeout(() => { cleanup(); reject(new Error('The browser asset worker did not activate. Reload the page.')); }, Math.max(0, deadline - Date.now()));
        container.addEventListener('controllerchange', check); registration.addEventListener('updatefound', check); check();
    });
    return { controller: container.controller!, registration };
}

type WorkerPreparation = (binding: AssetRouteBinding, port: MessagePort) => Promise<unknown>;
type Registration = AssetRouteBinding & { controller: AssetWorkerBinding['controller']; reject(error: Error): void; ack: MessagePort };

/** The registration port is transferred exactly once to the active SW; the
 * page retains only a bounded acknowledgment, never relaying direct requests. */
export class PageAssetRoute implements PageAssetRouteLike {
    private sequence = 0;
    private registration?: Registration;

    constructor(private readonly page: URL, readonly mode: AssetDispatchMode,
        private readonly getWorker: () => Promise<AssetWorkerBinding>, private readonly prepareWorker: WorkerPreparation,
        private readonly deadline = ASSET_ROUTE_DEADLINE_MS) {}

    async prepare(generation: string): Promise<void> {
        this.cancel();
        const sequence = ++this.sequence, owner = await this.getWorker();
        if (sequence !== this.sequence) throw new Error('The asset route registration was cancelled.');
        this.validate(owner);
        const route = new MessageChannel(), acknowledgement = new MessageChannel();
        const binding: AssetRouteBinding = { generation, registration: crypto.randomUUID(), sequence, mode: this.mode };
        let reject!: (error: Error) => void;
        const acknowledged = new Promise<void>((resolve, fail) => {
            reject = fail;
            const timer = setTimeout(() => fail(new Error('The asset worker did not acknowledge its session route.')), this.deadline);
            acknowledgement.port1.onmessage = event => {
                const message = event.data as Record<string, unknown> | null;
                if (!message || message.generation !== binding.generation || message.registration !== binding.registration
                    || message.sequence !== binding.sequence) return;
                if (message.type === 'overte-atp-registered' && message.ok === true && message.mode === this.mode) resolve();
                else fail(new Error('The asset worker refused the session route.'));
            };
            acknowledgement.port1.onmessageerror = () => fail(new Error('Invalid asset route acknowledgment.'));
            acknowledgement.port1.start();
            void Promise.resolve().then(() => acknowledged).finally(() => {
                clearTimeout(timer); acknowledgement.port1.close();
            }).catch(() => {});
        });
        const registration: Registration = { ...binding, controller: owner.controller, reject, ack: acknowledgement.port1 };
        this.registration = registration;
        // Attach the worker endpoint before asking the SW to send its handshake.
        // The native worker acknowledges both preparation and exact SW identity.
        let prepared: Promise<unknown>;
        try {
            prepared = this.prepareWorker(binding, route.port2);
            void prepared.catch(() => {});
            owner.controller.postMessage({ type: 'overte-atp-register', ...binding }, [route.port1, acknowledgement.port2]);
        } catch (error) {
            route.port1.close(); route.port2.close(); acknowledgement.port2.close();
            reject(error instanceof Error ? error : new Error('The asset route could not be transferred.'));
            this.cancel(); throw error;
        }
        try {
            await Promise.all([prepared, acknowledged]);
            if (this.registration !== registration || sequence !== this.sequence) throw new Error('The asset route registration was cancelled.');
            this.validate(owner);
        } catch (error) {
            if (this.registration === registration) this.cancel();
            throw error;
        }
    }

    cancel(): void {
        ++this.sequence;
        const registration = this.registration; this.registration = undefined;
        if (!registration) return;
        registration.reject(new Error('The asset route registration was cancelled.')); registration.ack.close();
        try { registration.controller.postMessage({ type: 'overte-atp-revoke', generation: registration.generation,
            registration: registration.registration, sequence: registration.sequence }); }
        catch { /* The owned worker independently closes this exact route on leave. */ }
    }

    private validate(owner: AssetWorkerBinding): void {
        const script = new URL('asset-worker.js', owner.registration.scope);
        const scope = new URL(owner.registration.scope);
        if (scope.origin !== this.page.origin || !this.page.pathname.startsWith(scope.pathname)
            || owner.controller !== owner.registration.active || owner.controller.state !== 'activated'
            || owner.controller.scriptURL !== script.href) throw new Error('The tab has no current owned asset worker controller.');
        if (typeof navigator !== 'undefined' && navigator.serviceWorker
            && navigator.serviceWorker.controller !== owner.controller) throw new Error('The asset worker controller changed. Reconnect to continue.');
    }
}
