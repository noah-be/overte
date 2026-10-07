// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual managed-domain UI check. Requires a host with no Chromium-available microphone.
// No fake media, audio recording, device labels, session identifiers, or user profiles.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const report = {
    startedAt: new Date().toISOString(), syntheticMicrophone: false, recordings: false,
    microphonePermissionGranted: true, hostAudioOutputMuted: true, completed: false,
};
let browser;
try {
    const env = { ...process.env, PULSE_SERVER: process.env.OVERTE_LAB_HOST_PULSE_SERVER || `unix:/run/user/${process.getuid()}/pulse/native` };
    if (process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH) env.LD_LIBRARY_PATH = process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH;
    // Preserve Playwright's default --mute-audio flag so this UI test cannot play into host speakers.
    browser = await chromium.launch({ headless: true, env,
        executablePath: process.env.OVERTE_LAB_CHROMIUM || chromium.executablePath(), args: ['--use-angle=swiftshader'] });
    report.browserVersion = browser.version();
    report.clientHTMLSHA256 = createHash('sha256').update(await readFile(path.join(repo, 'browser-client/dist/index.html'))).digest('hex');
    const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    let pageErrors = 0;
    page.on('pageerror', () => pageErrors++);
    await page.goto(process.env.OVERTE_LAB_URL || 'http://127.0.0.1:8090');
    report.availableAudioInputs = await page.evaluate(async () =>
        (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'audioinput').length);
    assert.equal(report.availableAudioInputs, 0, 'This acceptance check requires actually unavailable Chromium microphone inputs');
    await page.locator('#domain').fill('overte://127.0.0.2:45102');
    await page.locator('#name').fill('Browser microphone availability check');
    await page.locator('#join').click();
    await page.waitForFunction(() => window.__overte?.connected && window.__overte.entityCount >= 7, undefined, { timeout: 90000 });
    report.loadedRealEntities = await page.evaluate(() => window.__overte.entityCount);
    await page.locator('#microphone').click();
    const expected = 'No microphone found. Connect one and try again.';
    await page.waitForFunction(message => {
        const notice = document.querySelector('#notice');
        return !notice.hidden && notice.textContent === message && !document.querySelector('#microphone').disabled;
    }, expected, { timeout: 15000 });
    report.displayedError = await page.locator('#notice').textContent();
    const state = await page.evaluate(() => ({ connected: window.__overte.connected, entities: window.__overte.entityCount,
        microphoneMuted: document.querySelector('#microphone').getAttribute('aria-pressed') === 'false',
        captureFrames: window.__overte.audio.sentFrames, retryEnabled: !document.querySelector('#microphone').disabled }));
    assert(state.connected && state.entities >= 7, 'Missing microphone keeps the actual world connected');
    assert(state.microphoneMuted && state.captureFrames === 0 && state.retryEnabled, 'Missing microphone stays muted without capture and permits retry');
    Object.assign(report, { connectedAfterError: state.connected, realEntitiesAfterError: state.entities,
        microphoneMutedAfterError: state.microphoneMuted, sentCaptureFrames: state.captureFrames, retryEnabled: state.retryEnabled });
    const before = await page.evaluate(() => window.__overte.pose.position);
    await page.locator('#world canvas').focus();
    await page.keyboard.down('KeyD');
    try {
        await page.waitForFunction(start => Math.hypot(window.__overte.pose.position.x - start.x, window.__overte.pose.position.z - start.z) > 0.3,
            before, { timeout: 6000 });
    } finally { await page.keyboard.up('KeyD'); }
    const after = await page.evaluate(() => window.__overte.pose.position);
    report.movementDistanceAfterErrorMetres = Math.hypot(after.x - before.x, after.z - before.z);
    assert(report.movementDistanceAfterErrorMetres > 0.3, 'Walking still works after the actual hardware error');
    await page.locator('#leave').click();
    await page.waitForFunction(() => !window.__overte.connected && window.__overte.entityCount === 0);
    report.cleanLeave = true;
    report.uncaughtPageErrors = pageErrors;
    assert.equal(pageErrors, 0, 'Actual hardware failure produces no uncaught application errors');
    report.completed = true;
} catch (error) {
    // Error types are diagnostic; arbitrary browser error messages could contain local paths.
    report.errorType = error.name;
    process.exitCode = 1;
} finally {
    await browser?.close();
    report.finishedAt = new Date().toISOString();
    const directory = path.join(repo, 'docs/browser-client/evidence');
    await mkdir(directory, { recursive: true });
    await writeFile(path.join(directory, 'microphone-unavailable-ui.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
}
