// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual stock Chrome private synthetic input capability, never physical audio.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createChrome } from './runtime.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'media-probe'); assert.equal(options.browsers, 'chromium');
assert.equal(process.env.DISPLAY, ':104'); assert.equal(process.env.PULSE_SOURCE, 'browser_microphone');
assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0') || existsSync('/dev/snd'), false);
const root = resolve(options.result), directory = resolve(root, 'chromium'); await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', passed: false, steps: [], pageErrors: [], softwareOnly: true,
    syntheticOnly: true, physicalMicrophoneTested: false, fakeMediaDeviceFlags: false,
    scope: 'Actual Chrome enumerateDevices/getUserMedia against only the private Pulse remap of browser_input.monitor; no domain join or native uplink acceptance.' };
const report = { mode: options.mode, started: new Date().toISOString(), browsers: [evidence], passed: false };
let browser;
try {
    browser = await createChrome(directory, { syntheticAudio: true, transportEvidence: false }); evidence.version = browser.version;
    const page = browser.page; page.setDefaultTimeout(10000);
    await page.route('http://127.0.0.1:46106/__media-probe', route => route.fulfill({ contentType: 'text/html',
        body: '<!doctype html><title>Private synthetic media capability</title><button id="capture">Capture laboratory input</button>' }));
    await page.goto('http://127.0.0.1:46106/__media-probe', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
        document.querySelector('#capture').addEventListener('click', async () => {
            let stream;
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false,
                });
                const tracks = stream.getAudioTracks(), settings = tracks[0].getSettings();
                window.mediaProbeResult = { audioInputCount: devices.filter(device => device.kind === 'audioinput').length,
                    trackCount: tracks.length, liveTrack: tracks[0].readyState === 'live', enabled: tracks[0].enabled,
                    settings: { sampleRate: settings.sampleRate, channelCount: settings.channelCount,
                        echoCancellation: settings.echoCancellation, noiseSuppression: settings.noiseSuppression,
                        autoGainControl: settings.autoGainControl }, deviceIdentifiersRetained: false, labelsRetained: false };
            } catch (error) { window.mediaProbeResult = { errorName: error.name, error: error.message }; }
            finally {
                if (stream) { stream.getTracks().forEach(track => track.stop());
                    window.mediaProbeResult.allTracksStopped = stream.getTracks().every(track => track.readyState === 'ended'); }
            }
        });
    });
    await page.locator('#capture').click();
    await page.waitForFunction(() => Boolean(window.mediaProbeResult));
    const result = await page.evaluate(() => window.mediaProbeResult);
    assert.ok(!result.error, result.error); assert.ok(result.audioInputCount > 0);
    assert.equal(result.trackCount, 1); assert.equal(result.liveTrack, true); assert.equal(result.enabled, true);
    assert.equal(result.allTracksStopped, true);
    evidence.steps.push({ name: 'Actual private synthetic input enumerates and trusted stock getUserMedia succeeds', passed: true, details: result });
    evidence.passed = true;
} catch (error) { evidence.steps.push({ name: 'Actual private Chrome media capability', passed: false, error: String(error.stack || error).slice(0, 3000) }); }
finally {
    if (browser) await browser.close().catch(() => undefined);
    report.passed = evidence.passed; report.finished = new Date().toISOString();
    await writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
}
process.exitCode = report.passed ? 0 : 1;
