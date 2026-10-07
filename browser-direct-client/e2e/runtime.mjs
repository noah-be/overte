// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { mkdir, readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, X509Certificate } from 'node:crypto';
import { chromium } from '@playwright/test';
import { observeTransport } from './instrumentation.mjs';
import { createHeaderObserver } from './header-evidence.mjs';
import { observeWorkerTransport } from './worker-instrumentation.mjs';
import { observeSessionMessages } from './session-message-evidence.mjs';
import { observeLocalNotices } from './local-notice-evidence.mjs';
import { createAvatarReceiveObserver } from './avatar-receive-evidence.mjs';
import { createAvatarEventObserver } from './avatar-event-evidence.mjs';
import { observeAvatarWorker } from './avatar-worker-evidence.mjs';
import { observeAvatarPageMessages } from './avatar-page-message-evidence.mjs';

const workerObservers = new WeakMap();
function watchSessionWorkers(page, avatarEvidence) {
    if (workerObservers.has(page)) return;
    const records = new Map(); let evictedWorkers = 0;
    const install = worker => {
        let path;
        try { path = new URL(worker.url()).pathname; } catch { return; }
        if (!/(?:^|\/)session-worker(?:[.-]|$)/.test(path) || records.has(worker)) return;
        if (records.size >= 8) { records.delete(records.keys().next().value); evictedWorkers++; }
        const record = { worker, script: path.split('/').at(-1), unavailable: false };
        records.set(worker, record);
        const avatarSetup = avatarEvidence ? `globalThis.overteTestOnlyAvatarReceiveFactory = (${createAvatarReceiveObserver.toString()});
            globalThis.overteTestOnlyAvatarEventFactory = (${createAvatarEventObserver.toString()});` : '';
        const additional = avatarEvidence ? `(${observeAvatarWorker.toString()})(${JSON.stringify(avatarEvidence.expectedNativeID)})` : '';
        record.ready = worker.evaluate(`${avatarSetup}
            globalThis.overteTestOnlyHeaderObserverFactory = (${createHeaderObserver.toString()}); (${observeWorkerTransport.toString()})(${additional});`)
            .catch(() => { record.unavailable = true; });
        worker.on('close', () => { record.unavailable = true; });
    };
    workerObservers.set(page, { records, install, limits: () => ({ retainedWorkers: 8, evictedWorkers }) });
    page.on('worker', install); for (const worker of page.workers()) install(worker);
}

/** Separate, opt-in AvatarMixer/body-event diagnostics. The normal header
 * observer still emits only its original header counters. */
export async function readAvatarWorkerEvidence(page) {
    const observer = workerObservers.get(page), records = observer ? [...observer.records.values()] : [];
    const workers = await Promise.all(records.map(async record => {
        await record.ready;
        if (record.unavailable) return { unavailable: true };
        try { return await record.worker.evaluate(() => globalThis.overteAvatarWorkerEvidence?.() || { unavailable: true }); }
        catch { return { unavailable: true }; }
    }));
    return { workersObserved: records.length, unavailableWorkers: workers.filter(value => value.unavailable).length, workers };
}

/** Await injection before any real Join. No polling or diagnostic work runs
 * during a benchmark except its explicit before/after snapshots. */
export async function prepareWorkerTransportEvidence(page, required = false) {
    const observer = workerObservers.get(page);
    if (!observer) {
        if (required) throw new Error('Actual session-worker transport observation is not installed.');
        return { workersObserved: 0 };
    }
    const started = Date.now();
    while (true) {
        for (const worker of page.workers()) observer.install(worker);
        const records = [...observer.records.values()];
        if (records.length || !required) {
            await Promise.all(records.map(record => record.ready));
            if (required && records.some(record => record.unavailable)) throw new Error('Actual session-worker observer could not initialize.');
            return { workersObserved: records.length, observerLimits: observer.limits() };
        }
        if (Date.now() - started >= 10000) throw new Error('No actual native session worker started.');
        await new Promise(resolve => setTimeout(resolve, 100));
    }
}

/** Main PeerConnection states and actual transferred worker channels are
 * separate: a detached main channel handle cannot prove worker closure. */
export async function readTransportEvidence(page, mainPeers) {
    const observer = workerObservers.get(page);
    const records = observer ? [...observer.records.values()] : [];
    const [rtc, snapshots] = await Promise.all([
        mainPeers === undefined ? page.evaluate(() => window.overteDirectTransportEvidence?.() || []) : Promise.resolve(mainPeers),
        Promise.all(records.map(async record => {
            await record.ready;
            if (record.unavailable) return { script: record.script, unavailable: true };
            try { return { script: record.script, ...await record.worker.evaluate(() => globalThis.overteWorkerTransportEvidence()) }; }
            catch { return { script: record.script, unavailable: true }; }
        })),
    ]);
    return { rtc, workerTransport: { workersObserved: records.length,
        unavailableWorkers: snapshots.filter(snapshot => snapshot.unavailable).length,
        observerLimits: observer?.limits() || { retainedWorkers: 8, evictedWorkers: 0 },
        workers: snapshots.map(({ channels, ...metadata }) => metadata),
        channels: snapshots.flatMap(snapshot => snapshot.channels || []) } };
}

/** Identical software settings for functional/benchmark arms. The isolated
 * permission-only diagnostic may select a smaller viewport inside display104. */
export async function createChrome(directory, { origin = 'http://127.0.0.1:46106', syntheticAudio = false, longTasks = false, transportEvidence = true, avatarEvidence, viewport = { width: 1280, height: 800 } } = {}) {
    process.env.TMPDIR = '/tmp'; // Bound to this laboratory's private temporary directory.
    const profile = resolve(directory, 'profile'); await mkdir(profile, { recursive: true });
    const args = ['--ozone-platform=x11', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
        '--disable-gpu-compositing', '--disable-dev-shm-usage'];
    const client = dirname(dirname(fileURLToPath(import.meta.url)));
    const certificatePath = resolve(client, '../build/browser-direct/lab/runtime/fixture-tls/cert.pem');
    let fixtureCertificateSPKI;
    if (existsSync(certificatePath)) {
        const certificate = new X509Certificate(await readFile(certificatePath));
        fixtureCertificateSPKI = createHash('sha256').update(certificate.publicKey.export({ type: 'spki', format: 'der' })).digest('base64');
        // Trust only the own test fixture's certificate key, never all HTTPS errors.
        args.push(`--ignore-certificate-errors-spki-list=${fixtureCertificateSPKI}`);
    }
    const context = await chromium.launchPersistentContext(profile, {
        headless: false, viewport, timeout: 40000, args, acceptDownloads: true,
    });
    if (transportEvidence) {
        await context.addInitScript({ content: `window.overteTestOnlyHeaderObserverFactory = (${createHeaderObserver.toString()});` });
        await context.addInitScript(observeTransport);
        await context.addInitScript(observeSessionMessages);
        await context.addInitScript(observeLocalNotices);
        context.on('page', page => watchSessionWorkers(page, avatarEvidence));
        for (const current of context.pages()) watchSessionWorkers(current, avatarEvidence);
    }
    if (avatarEvidence?.pageMessages) await context.addInitScript({ content:
        `window.overteTestOnlyAvatarEventFactory=(${createAvatarEventObserver.toString()});
        (${observeAvatarPageMessages.toString()})(${JSON.stringify(avatarEvidence.expectedNativeID)});` });
    if (longTasks) await context.addInitScript(observeLongTasks);
    await context.addInitScript(() => performance.setResourceTimingBufferSize(4096));
    await context.addInitScript(() => {
        const stats = { lockedTrustedEvents: 0, movementX: 0, movementY: 0 };
        document.addEventListener('mousemove', event => {
            if (event.isTrusted && document.pointerLockElement) { stats.lockedTrustedEvents++; stats.movementX += event.movementX; stats.movementY += event.movementY; }
        });
        Object.defineProperty(window, 'overteMouseEvidence', { value: () => ({ ...stats, pointerLocked: Boolean(document.pointerLockElement) }) });
    });
    if (syntheticAudio) await context.grantPermissions(['microphone'], { origin });
    const page = context.pages()[0] || await context.newPage();
    return { page, context, version: context.browser()?.version(), fixtureCertificateSPKI,
        automation: 'Playwright; own downloaded Chrome', close: () => context.close(),
        prepareTransportEvidence: required => prepareWorkerTransportEvidence(page, required),
        readTransportEvidence: () => readTransportEvidence(page),
        fill: (selector, value) => page.locator(selector).fill(value), click: selector => page.locator(selector).click(),
        screenshot: path => page.screenshot({ path, fullPage: false }), download: async path => {
            const pending = page.waitForEvent('download'); await page.locator('#tablet-snapshot button').click();
            const download = await pending; await download.saveAs(path);
        } };
}

/** Bounded real browser long-task measurements; durations describe main-thread work. */
export function observeLongTasks() {
    const durations = []; let count = 0, totalMs = 0, maxMs = 0;
    const supported = PerformanceObserver.supportedEntryTypes.includes('longtask');
    if (supported) new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
            count++; totalMs += entry.duration; maxMs = Math.max(maxMs, entry.duration);
            if (durations.length < 2048) durations.push(entry.duration);
        }
    }).observe({ type: 'longtask', buffered: true });
    Object.defineProperty(window, 'overteLongTaskEvidence', { value: () => {
        const sorted = [...durations].sort((left, right) => left - right);
        return { supported, count, totalMs, maxMs, retained: sorted.length,
            p95Ms: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] || 0 };
    } });
}

/** Observe both loader arms without replacing browser image loading/decoding. */
export function observeImageLoads() {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
    const originalDecode = HTMLImageElement.prototype.decode, pending = new WeakMap();
    const stats = { assigned: 0, completed: 0, failed: 0, canceled: 0, completedPixels: 0,
        totalLoadEventMs: 0, maximumLoadEventMs: 0, explicitDecodeCalls: 0, explicitDecodeMs: 0,
        explicitDecodeErrors: 0, kinds: { atp: 0, blob: 0, data: 0, https: 0, http: 0, other: 0 } };
    const durations = [];
    if (descriptor?.get && descriptor.set) Object.defineProperty(HTMLImageElement.prototype, 'src', {
        ...descriptor, set(value) {
            const previous = pending.get(this);
            if (previous) { this.removeEventListener('load', previous.load); this.removeEventListener('error', previous.error); pending.delete(this); stats.canceled++; }
            if (String(value)) {
                const source = String(value), started = performance.now(); stats.assigned++;
                const kind = source.includes('/_overte-atp/') ? 'atp' : source.startsWith('blob:') ? 'blob'
                    : source.startsWith('data:') ? 'data' : source.startsWith('https:') ? 'https' : source.startsWith('http:') ? 'http' : 'other';
                stats.kinds[kind]++;
                const finish = success => {
                    this.removeEventListener('load', load); this.removeEventListener('error', error); pending.delete(this);
                    const elapsed = performance.now() - started;
                    if (success) { stats.completed++; stats.completedPixels += this.naturalWidth * this.naturalHeight; }
                    else stats.failed++;
                    stats.totalLoadEventMs += elapsed; stats.maximumLoadEventMs = Math.max(stats.maximumLoadEventMs, elapsed);
                    if (durations.length < 2048) durations.push(elapsed);
                };
                const load = () => finish(true), error = () => finish(false);
                this.addEventListener('load', load); this.addEventListener('error', error); pending.set(this, { load, error });
            }
            return descriptor.set.call(this, value);
        },
    });
    if (originalDecode) HTMLImageElement.prototype.decode = function (...argumentsList) {
        const started = performance.now(); stats.explicitDecodeCalls++;
        return originalDecode.apply(this, argumentsList).then(result => {
            stats.explicitDecodeMs += performance.now() - started; return result;
        }, error => { stats.explicitDecodeMs += performance.now() - started; stats.explicitDecodeErrors++; throw error; });
    };
    Object.defineProperty(window, 'overteImageLoadingEvidence', { value: () => {
        const sorted = [...durations].sort((left, right) => left - right);
        return { ...stats, kinds: { ...stats.kinds }, retainedLoadEvents: sorted.length,
            p95LoadEventMs: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] || 0,
            scope: 'Image src assignment through browser load/error event; includes transport, implicit decode and main-thread dispatch. Explicit decode measures only calls to Image.decode.' };
    } });
}
