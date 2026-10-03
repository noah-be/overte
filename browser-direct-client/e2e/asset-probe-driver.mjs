// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Isolated real native asset diagnosis; never scene/render/interoperability acceptance.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { createChrome, readTransportEvidence } from './runtime.mjs';
import { requireNoAutomaticAssetRequests, actualWorkerAssetChannel } from './asset-probe-controls.mjs';
import { requireBenchmarkRouteUsage } from './benchmark-controls.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'asset-probe'); assert.equal(options.browsers, 'chromium');
const root = resolve(options.result), client = dirname(dirname(fileURLToPath(import.meta.url))), directory = resolve(root, 'chromium');
const lab = resolve(client, '../build/browser-direct/lab'), origin = 'http://127.0.0.1:46106', endpoint = 'ws://127.0.0.1:46104/';
const timeout = Number(options.timeout || 55) * 1000, pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
const report = { started: new Date().toISOString(), mode: 'asset-probe', origin, endpoint,
    scope: 'Actual production WorkerDirectSession, transferred worker channels, registered ServiceWorker and native AssetServer with no renderer, no model loaders and no automatic scene asset requests. Earlier main-owned core artifacts remain historical. Diagnostic only; no rendered world, native participant or voice acceptance.',
    bundleManifestSha256: createHash('sha256').update(await readFile(resolve(root, 'bundle-manifest.json'))).digest('hex'),
    isolation: { display: process.env.DISPLAY, gpuDevicesMounted: existsSync('/dev/dri') || existsSync('/dev/nvidia0'), softwareRenderingOnly: true, physicalMicrophoneTested: false },
    browsers: [], passed: false };
assert.equal(report.isolation.display, ':104'); assert.equal(report.isolation.gpuDevicesMounted, false);
assert.ok(process.env.PLAYWRIGHT_BROWSERS_PATH?.includes('/build/browser-direct/browsers'));
await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', steps: [], pageErrors: [], requestFailures: [], warningsAndErrors: [], assetTimeline: [], passed: false };
report.browsers.push(evidence);
let browser, observedNativeAssetRequests = 0;
const snapshot = async page => {
    const result = await page.evaluate(() => ({ state: window.overteAssetProbe?.state(), rtc: window.overteDirectTransportEvidence?.(),
        longTasks: window.overteLongTaskEvidence?.(), observedAtMs: performance.now() }));
    Object.assign(result, await readTransportEvidence(page, result.rtc));
    result.observedNativeAssetRequests = observedNativeAssetRequests;
    if (result.state) result.state.automaticSceneAssetRequests = Math.max(0, observedNativeAssetRequests - result.state.explicitAssetRequests);
    return result;
};
async function save() { await writeFile(resolve(directory, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 }); }
async function step(name, operation) {
    const started = Date.now();
    try { const details = await operation(); evidence.steps.push({ name, passed: true, elapsedMs: Date.now() - started, details }); }
    catch (error) { evidence.steps.push({ name, passed: false, elapsedMs: Date.now() - started,
        error: String(error.stack || error).slice(0, 3000), ...(browser ? { failureDiagnostics: await snapshot(browser.page).catch(() => undefined) } : {}) }); }
    await save(); console.log(JSON.stringify({ browser: 'chromium', step: name, passed: evidence.steps.at(-1).passed }));
    return evidence.steps.at(-1).passed;
}
async function waitFor(page, predicate, limit = timeout) {
    const started = Date.now();
    while (Date.now() - started < limit) {
        if (await page.evaluate(predicate)) return;
        const state = (await snapshot(page)).state;
        if (state?.state === 'error') throw new Error(state.lastError || 'Real native session error');
        await pause(250);
    }
    throw new Error(`Actual browser condition timed out after ${limit}ms`);
}
async function fetchWithTimeline(page, record) {
    let settled = false, response, failure;
    const started = Date.now();
    const request = page.evaluate(asset => window.overteAssetProbe.fetch(asset), record.atpURL)
        .then(value => { response = value; settled = true; }, error => { failure = error; settled = true; });
    while (!settled && Date.now() - started < 35000) {
        const current = { asset: record.relativePath, observedAt: new Date().toISOString(), ...await snapshot(page) };
        evidence.assetTimeline.push(current);
        await writeFile(resolve(directory, 'live-diagnostics.pending'), `${JSON.stringify(current, null, 2)}\n`, { mode: 0o600 });
        await rename(resolve(directory, 'live-diagnostics.pending'), resolve(directory, 'live-diagnostics.json'));
        await pause(2000);
    }
    if (!settled) throw new Error('Native asset diagnostic exceeded 35 seconds; production request timeout remains unchanged');
    await request; if (failure) throw failure;
    const details = { source: { atpURL: record.atpURL, relativePath: record.relativePath, sourceSHA256: record.sourceSHA256,
        servedSHA256: record.servedSHA256, sourceBytes: record.sourceBytes, servedBytes: record.servedBytes },
        result: response, finalTransport: await snapshot(page), automaticSceneAssetRequests: (await snapshot(page)).state.automaticSceneAssetRequests };
    assert.equal(details.automaticSceneAssetRequests, 0);
    // Preserve response/body diagnostics before assertions so native HTTP 502 is visible.
    evidence.assetResults ||= []; evidence.assetResults.push(details); await save();
    assert.equal(response.status, 200, response.error || 'Actual native asset failed');
    assert.equal(response.bytes, record.servedBytes); assert.equal(response.sha256, record.servedSHA256);
    assert.equal(record.sourceSHA256, record.servedSHA256, 'Select unchanged original binary bytes');
    // Worker diagnostics are bounded/coalesced separately from the response.
    // Their delivery uses the same original request observation deadline.
    let counted, routingError;
    do {
        counted = await snapshot(page);
        try { details.assetRouting = requireBenchmarkRouteUsage(counted.state.assetRouting, 'direct'); routingError = undefined; }
        catch (error) { routingError = error; }
        if (!routingError) break;
        await pause(100);
    } while (Date.now() - started < 35000);
    details.observedRequests = requireNoAutomaticAssetRequests(counted.observedNativeAssetRequests, counted.state.explicitAssetRequests);
    if (routingError) throw routingError;
    await save();
    return details;
}
try {
    browser = await createChrome(directory, { origin, longTasks: true }); evidence.version = browser.version; evidence.automation = browser.automation;
    const page = browser.page;
    page.on('request', request => {
        const url = new URL(request.url());
        if (url.origin === origin && url.pathname.startsWith('/_overte-atp/')) observedNativeAssetRequests++;
    });
    page.on('pageerror', error => { if (evidence.pageErrors.length < 20) evidence.pageErrors.push(String(error.message).slice(0, 2000)); });
    page.on('requestfailed', request => { if (evidence.requestFailures.length < 20) evidence.requestFailures.push({ url: request.url().replace(/\?.*/, ''), error: request.failure()?.errorText }); });
    page.on('console', message => { if (['warning', 'error'].includes(message.type()) && evidence.warningsAndErrors.length < 40) {
        const text = message.text(); evidence.warningsAndErrors.push({ type: message.type(), text: /\b(sdp|candidate|secret|password|token|authorization)\b/i.test(text) ? '[sensitive protocol log omitted]' : text.slice(0, 2000) }); } });
    const loaded = await step('Test-only entry has no renderer or automatic asset loads', async () => {
        await page.goto(`${origin}/e2e/asset-probe.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await waitFor(page, () => Boolean(window.overteAssetProbe), 12000);
        evidence.nativeSessionWorker = await browser.prepareTransportEvidence(true);
        const result = await page.evaluate(() => ({ ...window.overteAssetProbe.state(), canvases: document.querySelectorAll('canvas').length,
            media: document.querySelectorAll('video,iframe,audio').length }));
        assert.equal(result.state, 'disconnected'); requireNoAutomaticAssetRequests(observedNativeAssetRequests, result.explicitAssetRequests);
        assert.equal(result.canvases, 0); assert.equal(result.media, 0);
        return result;
    });
    const joined = loaded && await step('Actual WebRTC native admission with no renderer', async () => {
        await page.evaluate(value => window.overteAssetProbe.join(value), endpoint);
        await waitFor(page, () => window.overteAssetProbe.state().state === 'connected');
        const deadline = Date.now() + 12000;
        let current;
        while (Date.now() < deadline) {
            current = await snapshot(page);
            if (actualWorkerAssetChannel(current)) break;
            await pause(100);
        }
        assert.ok(current && actualWorkerAssetChannel(current), 'Header observer must bind the actual transferred AssetServer channel.');
        assert.equal(current.state.automaticSceneAssetRequests, 0);
        requireNoAutomaticAssetRequests(current.observedNativeAssetRequests, current.state.explicitAssetRequests);
        return current;
    });
    if (joined) {
        const provenanceBytes = await readFile(resolve(lab, 'scene/asset-provenance.json'));
        evidence.assetManifestSHA256 = createHash('sha256').update(provenanceBytes).digest('hex');
        const files = JSON.parse(provenanceBytes).records;
        const exr = files.find(file => file.relativePath.endsWith('/SKY-brush-clouds.exr'));
        const fbx = files.filter(file => file.relativePath.endsWith('.fbx') && file.sourceSHA256 === file.servedSHA256)
            .sort((left, right) => Math.abs(left.servedBytes - 1820000) - Math.abs(right.servedBytes - 1820000))[0];
        assert.ok(exr && fbx, 'Actual unchanged Hub EXR and medium FBX must exist');
        await step('Serial native unchanged daytime EXR transfer with bounded header evidence', () => fetchWithTimeline(page, exr));
        await step('Serial native unchanged medium FBX transfer with bounded header evidence', () => fetchWithTimeline(page, fbx));
        await step('Native session leave closes all actual DataChannels', async () => {
            await page.evaluate(() => window.overteAssetProbe.leave());
            const deadline = Date.now() + 10000; let current;
            while (Date.now() < deadline) {
                current = await snapshot(page);
                if (current.state.state === 'disconnected' && current.rtc.every(peer => peer.connectionState === 'closed')
                    && current.workerTransport.unavailableWorkers === 0 && current.workerTransport.channels.length > 0
                    && current.workerTransport.channels.every(channel => channel.readyState === 'closed')) break;
                await pause(100);
            }
            assert.equal(current.state.state, 'disconnected');
            assert.ok(current.rtc.every(peer => peer.connectionState === 'closed'));
            assert.equal(current.workerTransport.unavailableWorkers, 0); assert.ok(current.workerTransport.channels.length > 0);
            assert.ok(current.workerTransport.channels.every(channel => channel.readyState === 'closed'));
            return current;
        });
    }
    await step('No uncaught browser exception', async () => { assert.deepEqual(evidence.pageErrors, []); return { pageErrors: evidence.pageErrors }; });
} catch (error) { evidence.fatal = String(error.stack || error).slice(0, 3000); }
finally {
    if (browser) await browser.close().catch(() => undefined);
    evidence.passed = !evidence.fatal && evidence.steps.length > 0 && evidence.steps.every(item => item.passed);
    await save(); report.finished = new Date().toISOString(); report.passed = evidence.passed;
    await writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
}
process.exitCode = report.passed ? 0 : 1;
