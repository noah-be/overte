// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual Chrome browser-UI permission decisions. No permission override API.
import assert from 'node:assert/strict';
import { constants, existsSync } from 'node:fs';
import { mkdir, open, readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { createChrome } from './runtime.mjs';
import { waitForPermissionState } from './permission-state.mjs';

const execute = promisify(execFile), helper = resolve(dirname(fileURLToPath(import.meta.url)), 'chrome-permission-ui.py');
const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'permission-probe'); assert.equal(options.browsers, 'chromium');
assert.equal(process.env.DISPLAY, ':104'); assert.equal(process.env.PULSE_SOURCE, 'browser_microphone');
assert.ok(process.env.PULSE_SERVER?.endsWith('/lab/runtime/b.sock'));
assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0') || existsSync('/dev/snd'), false);
const root = resolve(options.result), deadline = Date.now() + 165000;
const evidence = { browser: 'chromium', passed: false, steps: [], pageErrors: [], softwareOnly: true,
    syntheticOnly: true, physicalMicrophoneTested: false, permissionAPIOverrides: false, fakeMediaDeviceFlags: false,
    scope: 'Actual stock Chrome microphone permission popup, trusted XTest browser-UI decisions, and unchanged BrowserAudio capture against only the private Pulse remap; no domain, World or native voice acceptance.' };
const report = { mode: options.mode, started: new Date().toISOString(), browsers: [evidence], passed: false };
const save = () => writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
const wait = delay => new Promise(resolve => setTimeout(resolve, delay));
const hash = data => createHash('sha256').update(data).digest('hex');
const waitForState = (page, predicate) => waitForPermissionState(
    () => page.evaluate(() => window.overtePermissionProbe.state()), predicate, { deadline });

async function reviewedAction(path, expected, caseDeadline) {
    while (Date.now() < Math.min(deadline, caseDeadline)) {
        if (existsSync(path)) {
            const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
            try {
                const info = await file.stat();
                assert.ok(info.isFile() && info.size <= 4096 && (info.mode & 0o777) === 0o600, 'UI request must be a private bounded regular file');
                const data = Buffer.alloc(4097), { bytesRead } = await file.read(data, 0, data.length, 0);
                assert.ok(bytesRead <= 4096);
                const request = JSON.parse(data.subarray(0, bytesRead).toString());
                assert.deepEqual(Object.keys(request).sort(), ['bindingSHA256', 'decision', 'nonce', 'x', 'y']);
                assert.equal(request.nonce, expected.nonce); assert.equal(request.decision, expected.decision);
                assert.equal(request.bindingSHA256, expected.bindingSHA256);
                assert.ok(Number.isSafeInteger(request.x) && Number.isSafeInteger(request.y));
                return request;
            } finally { await file.close(); }
        }
        await wait(150);
    }
    throw new Error('Actual Chrome popup inspection/input exceeded the bounded permission-only UI feasibility window.');
}

async function testDecision(decision, details) {
    const directory = resolve(root, decision), profile = resolve(directory, 'profile');
    await mkdir(directory, { recursive: true }); assert.equal(existsSync(profile), false, 'Each decision needs a fresh profile');
    let browser;
    try {
        // syntheticAudio:false intentionally leaves Chrome's permission at its
        // fresh-profile default. The private Pulse source is still synthetic.
        browser = await createChrome(directory, { syntheticAudio: false, transportEvidence: false,
            viewport: { width: 900, height: 600 } });
        evidence.version ||= browser.version;
        const page = browser.page; page.setDefaultTimeout(10000);
        page.on('pageerror', error => evidence.pageErrors.push(String(error).slice(0, 1000)));
        await page.goto('http://127.0.0.1:46106/e2e/permission-probe.html', { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => Boolean(window.overtePermissionProbe));
        details.before = await page.evaluate(() => window.overtePermissionProbe.state());
        assert.equal(details.before.permission, 'prompt'); assert.equal(details.before.nativeRequests, 0);
        await page.locator('#enable').click();
        await waitForState(page, state => state.nativeRequests === 1);
        await wait(600);
        details.pending = await page.evaluate(() => window.overtePermissionProbe.state());
        assert.equal(details.pending.phase, 'requesting'); assert.equal(details.pending.permission, 'prompt');
        assert.equal(details.pending.enableTrusted, true);
        const screenshot = resolve(directory, 'chrome-permission-prompt.png'), binding = resolve(directory, 'chrome-window-binding.json');
        const capture = await execute('python3', [helper, '--operation', 'capture', '--profile', profile,
            '--binding', binding, '--screenshot', screenshot], { timeout: 8000, maxBuffer: 16384 });
        details.windowCapture = JSON.parse(capture.stdout);
        details.screenshot = `${decision}/chrome-permission-prompt.png`;
        details.screenshotSHA256 = hash(await readFile(screenshot));
        const ready = { decision, nonce: randomUUID(), bindingSHA256: hash(await readFile(binding)),
            screenshot: details.screenshot, instructions: 'Inspect this actual bound Chrome popup screenshot, then supply only the reviewed button coordinates.' };
        await writeFile(resolve(directory, 'prompt-ready.json'), `${JSON.stringify(ready, null, 2)}\n`, { mode: 0o600 });
        await save();
        const request = await reviewedAction(resolve(directory, 'reviewed-ui-action.json'), ready, Date.now() + 65000);
        const input = await execute('python3', [helper, '--operation', 'click', '--profile', profile, '--binding', binding,
            '--x', String(request.x), '--y', String(request.y)], { timeout: 8000, maxBuffer: 16384 });
        details.browserUIInput = JSON.parse(input.stdout);
        details.reviewedCoordinates = { x: request.x, y: request.y };
        details.answered = await waitForState(page, state => state.phase === 'answered');
        assert.equal(details.answered.permissionBefore, 'prompt'); assert.equal(details.answered.nativeRequests, 1);
        if (decision === 'deny') {
            assert.equal(details.answered.permission, 'denied'); assert.equal(details.answered.enabled, false);
            assert.equal(details.answered.nativeErrorName, 'NotAllowedError'); assert.equal(details.answered.returnedStreams, 0);
            assert.equal(details.answered.audio.microphoneMuted, true);
            assert.ok(details.answered.notices.some(notice => notice.message.startsWith('Microphone permission denied.')));
        } else {
            assert.equal(details.answered.permission, 'granted'); assert.equal(details.answered.enabled, true);
            assert.equal(details.answered.returnedAudioTracks, 1); assert.equal(details.answered.liveAudioTracks, 1);
            assert.equal(details.answered.audio.microphoneMuted, false);
            details.capturing = await waitForState(page, state => state.capturedCallbacks > 0);
        }
        await page.locator('#stop').click();
        details.stopped = await waitForState(page, state => state.disposed);
        assert.equal(details.stopped.stopTrusted, true); assert.equal(details.stopped.allReturnedTracksStopped, true);
        assert.equal(details.stopped.liveAudioTracks, 0); assert.equal(details.stopped.audio.microphoneMuted, true);
        assert.equal(details.stopped.audio.sampleRate, undefined);
        const callbacks = details.stopped.capturedCallbacks; await wait(250);
        assert.equal((await page.evaluate(() => window.overtePermissionProbe.state())).capturedCallbacks, callbacks);
        return details;
    } finally {
        if (browser) {
            details.finalCleanup = await browser.page.evaluate(() => window.overtePermissionProbe?.dispose()).catch(error => ({ error: String(error).slice(0, 1000) }));
            await browser.close().catch(error => { details.closeError = String(error).slice(0, 1000); });
        }
    }
}

try {
    for (const decision of ['deny', 'allow']) {
        const step = { name: `Actual Chrome browser-UI microphone ${decision}`, passed: false,
            details: { decision, freshProfile: true, permissionAPIOverrides: false, nativeDomainJoined: false } };
        evidence.steps.push(step); await save();
        try { await testDecision(decision, step.details); step.passed = true; }
        catch (error) { step.error = String(error.stack || error).slice(0, 3000); throw error; }
        await save();
    }
    assert.equal(evidence.pageErrors.length, 0); evidence.passed = true;
} catch { /* Preserve an unsupported UI or failed decision, never grant by API. */ }
finally {
    report.passed = evidence.passed; report.finished = new Date().toISOString(); await save();
}
process.exitCode = report.passed ? 0 : 1;
