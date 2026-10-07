// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real full-scene model-failure diagnosis; never world/interoperability acceptance.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createChrome } from './runtime.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'model-probe'); assert.equal(options.browsers, 'chromium');
const root = resolve(options.result), directory = resolve(root, 'chromium'), timeout = Number(options.timeout || 55) * 1000;
const origin = 'http://127.0.0.1:46106', endpoint = 'ws://127.0.0.1:46104/', pause = ms => new Promise(done => setTimeout(done, ms));
const report = { started: new Date().toISOString(), mode: 'model-probe', origin, endpoint, diagnosticOnly: true, worldQualified: false,
    scope: 'Unchanged full production scene, assets, graphics and ordinary spawn. Identify one current failed model and naturally leave; no full scene, participant, input or audio qualification.',
    bundleManifestSha256: createHash('sha256').update(await readFile(resolve(root, 'bundle-manifest.json'))).digest('hex'),
    isolation: { display: process.env.DISPLAY, gpuDevicesMounted: existsSync('/dev/dri') || existsSync('/dev/nvidia0'), softwareRenderingOnly: true, physicalMicrophoneTested: false },
    browsers: [], passed: false };
assert.equal(report.isolation.display, ':104'); assert.equal(report.isolation.gpuDevicesMounted, false);
assert.ok(process.env.PLAYWRIGHT_BROWSERS_PATH?.includes('/build/browser-direct/browsers'));
await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', steps: [], pageErrors: [], passed: false }; report.browsers.push(evidence);
let browser;
async function snapshot() {
    return browser.page.evaluate(() => ({ observedAt: new Date().toISOString(), app: window.overteDirectDiagnostics?.(),
        modelLoads: window.overteModelLoadEvidence?.(), localNotices: window.overteLocalNoticeEvidence?.(),
        sessionMessages: window.overteSessionMessageEvidence?.() }));
}
async function save() { await writeFile(resolve(directory, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 }); }
async function step(name, operation) {
    const started = Date.now();
    try { evidence.steps.push({ name, passed: true, elapsedMs: Date.now() - started, details: await operation() }); }
    catch (error) { evidence.steps.push({ name, passed: false, elapsedMs: Date.now() - started, error: String(error.stack || error).slice(0, 3000),
        failureDiagnostics: browser ? await snapshot().catch(() => undefined) : undefined }); }
    evidence.steps.at(-1).elapsedMs = Date.now() - started;
    await save(); console.log(JSON.stringify({ browser: 'chromium', step: name, passed: evidence.steps.at(-1).passed }));
    return evidence.steps.at(-1).passed;
}
async function waitFor(predicate, limit = timeout) {
    const started = Date.now();
    while (Date.now() - started < limit) {
        const current = await snapshot();
        await writeFile(resolve(directory, 'live-diagnostics.json'), `${JSON.stringify(current, null, 2)}\n`, { mode: 0o600 });
        if (predicate(current)) return current;
        if (current.app?.state === 'error') throw new Error(current.sessionMessages?.workers.find(worker => worker.firstFailure)?.firstFailure?.reason || 'The actual native session failed');
        await pause(1000);
    }
    throw new Error('No expected real model state was observed within the bounded diagnostic window.');
}
try {
    browser = await createChrome(directory, { origin, longTasks: true }); evidence.version = browser.version;
    browser.page.on('pageerror', error => { if (evidence.pageErrors.length < 16) evidence.pageErrors.push(String(error.message).slice(0, 2048)); });
    await browser.page.goto(origin, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await waitFor(current => Boolean(current.app && current.modelLoads), 30000); await browser.prepareTransportEvidence(true);
    const joined = await step('Actual worker native join and unchanged 83-entity scene', async () => {
        await browser.click('button[aria-controls="tablet-domain"]'); await browser.fill('#tablet-domain input[name="endpoint"]', endpoint);
        await browser.click('#tablet-domain button[type="submit"]');
        const current = await waitFor(value => value.app?.state === 'connected');
        assert.equal(current.app.entities, Number(options['expected-entities'] || 83));
        assert.equal(current.modelLoads.total, 55);
        return { ...current, ...await browser.readTransportEvidence() };
    });
    if (joined) await step('Exact current failed model source and bounded error', async () => {
        const current = await waitFor(value => value.modelLoads?.failed > 0);
        assert.equal(current.modelLoads.omitted, 0); assert.equal(current.app.audio.microphoneMuted, true);
        const failures = current.modelLoads.rows.filter(value => value.failed);
        assert.ok(failures.length > 0 && failures.every(value => value.error));
        return { ...current, failures, ...await browser.readTransportEvidence() };
    });
    await step('Natural leave closes actual worker channels and native peers', async () => {
        await browser.click('button[aria-controls="tablet-domain"]'); await browser.click('#tablet-domain .button-row button:first-child');
        await waitFor(current => current.app.state === 'disconnected', 10000);
        const started = Date.now(); let transport;
        do {
            transport = await browser.readTransportEvidence();
            if (transport.rtc.every(peer => peer.connectionState === 'closed') && transport.workerTransport.channels.every(channel => channel.readyState === 'closed')) break;
            await pause(100);
        } while (Date.now() - started < 8000);
        assert.ok(transport.rtc.every(peer => peer.connectionState === 'closed'));
        assert.ok(transport.workerTransport.channels.every(channel => channel.readyState === 'closed'));
        return { ...await snapshot(), ...transport };
    });
    assert.deepEqual(evidence.pageErrors, []);
} catch (error) { evidence.driverError = String(error.stack || error).slice(0, 3000); }
finally {
    await browser?.close().catch(() => undefined); evidence.passed = !evidence.driverError && evidence.steps.length === 3 && evidence.steps.every(step => step.passed);
    report.passed = evidence.passed; report.finished = new Date().toISOString(); await save();
    await writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
}
process.exitCode = report.passed ? 0 : 1;
