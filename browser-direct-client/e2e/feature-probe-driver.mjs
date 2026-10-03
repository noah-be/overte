// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Isolated stock Chrome capability observation; no domain, SDP, ICE or data sends.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createChrome } from './runtime.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'feature-probe'); assert.equal(options.browsers, 'chromium');
assert.equal(process.env.DISPLAY, ':104'); assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0'), false);
assert.ok(process.env.PLAYWRIGHT_BROWSERS_PATH?.includes('/build/browser-direct/browsers'));
const root = resolve(options.result), directory = resolve(root, 'chromium'); await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', passed: false, steps: [], pageErrors: [], softwareOnly: true,
    scope: 'Stock current Chrome RTCDataChannel transfer to DedicatedWorker only. No RTCPeerConnection offer/SDP, ICE gathering, native join, send or microphone. No production worker architecture change.' };
const report = { mode: 'feature-probe', started: new Date().toISOString(), browsers: [evidence], passed: false };
let browser;
try {
    browser = await createChrome(directory, { transportEvidence: false }); evidence.version = browser.version;
    browser.page.on('pageerror', error => { if (evidence.pageErrors.length < 10) evidence.pageErrors.push(error.message.slice(0, 2000)); });
    // Minimal browser-local localhost document: no application modules and no
    // native signaling. Real RTC/Worker APIs remain completely unmodified.
    await browser.page.route('http://127.0.0.1:46106/__rtc-worker-feature', route => route.fulfill({
        status: 200, contentType: 'text/html', body: '<!doctype html><title>Stock RTC worker feature probe</title>' }));
    await browser.page.goto('http://127.0.0.1:46106/__rtc-worker-feature', { waitUntil: 'domcontentloaded' });
    const result = await browser.page.evaluate(async () => {
        async function transfer(sameTask) {
            const code = `self.onmessage = event => {
                const channel = event.data.channel;
                const evidence = { workerSecureContext: self.isSecureContext, workerRTCDataChannelType: typeof RTCDataChannel,
                    workerRTCPeerConnectionType: typeof RTCPeerConnection,
                    constructor: channel.constructor.name, instanceOfRTCDataChannel: typeof RTCDataChannel === 'function' && channel instanceof RTCDataChannel,
                    state: channel.readyState, ordered: channel.ordered, maxRetransmits: channel.maxRetransmits,
                    sendAttempted: false, actualNativeDataReceived: false };
                channel.close(); self.postMessage(evidence);
            };`;
            const workerURL = URL.createObjectURL(new Blob([code], { type: 'text/javascript' })), worker = new Worker(workerURL);
            const peer = new RTCPeerConnection({ iceServers: [] });
            let timer;
            const pending = new Promise(resolveMessage => {
                worker.onmessage = event => resolveMessage({ supported: true, worker: event.data });
                worker.onerror = event => { event.preventDefault(); resolveMessage({ supported: false, workerError: event.message }); };
                timer = setTimeout(() => resolveMessage({ supported: false, workerTimeout: true }), 5000);
            });
            // Same-task case performs no await between the actual channel's
            // creation and postMessage transfer; the control crosses a task.
            const channel = peer.createDataChannel('direct-worker-feature-probe', { ordered: false, maxRetransmits: 0 });
            if (!sameTask) await new Promise(resolveTask => setTimeout(resolveTask, 0));
            let result;
            try { worker.postMessage({ channel }, [channel]); result = await pending; }
            catch (error) { result = { supported: false, errorName: error.name, error: error.message }; }
            finally { clearTimeout(timer); peer.close(); worker.terminate(); URL.revokeObjectURL(workerURL); }
            return { sameTask, ...result, peerClosed: peer.connectionState === 'closed', workerTerminated: true, blobURLRevoked: true,
                peerOfferCreated: false, nativeDataSent: false };
        }
        return { secureContext: window.isSecureContext, stockAPIs: !window.overteDirectTransportEvidence,
            browserLocalMinimalDocument: true, applicationModulesLoaded: false,
            sameTask: await transfer(true), laterTask: await transfer(false) };
    });
    assert.equal(result.secureContext, true); assert.equal(result.stockAPIs, true);
    assert.equal(result.sameTask.peerClosed, true); assert.equal(result.laterTask.peerClosed, true);
    if (result.sameTask.supported) {
        assert.equal(result.sameTask.worker.constructor, 'RTCDataChannel'); assert.equal(result.sameTask.worker.instanceOfRTCDataChannel, true);
        assert.equal(result.sameTask.worker.sendAttempted, false); assert.equal(result.sameTask.worker.actualNativeDataReceived, false);
        assert.equal(result.sameTask.worker.workerSecureContext, true);
        assert.equal(result.laterTask.errorName, 'DataCloneError', 'Actual late transfer must fail the structured clone guard');
    }
    assert.equal(result.laterTask.supported, false, 'A channel must not remain transferable after its creation task');
    assert.deepEqual(evidence.pageErrors, []);
    evidence.steps.push({ name: 'Stock RTCDataChannel same-task transfer and later-task negative control', passed: true, details: result });
    evidence.capabilitySupported = result.sameTask.supported; evidence.passed = true;
} catch (error) { evidence.steps.push({ name: 'Stock Chrome capability probe', passed: false, error: String(error.stack || error).slice(0, 3000) }); }
finally {
    if (browser) await browser.close().catch(() => undefined);
    report.passed = evidence.passed; report.finished = new Date().toISOString();
    await writeFile(resolve(directory, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
    await writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
}
process.exitCode = report.passed ? 0 : 1;
