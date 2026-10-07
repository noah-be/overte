// SPDX-License-Identifier: Apache-2.0
// Optional real hardware capture check. No microphone recordings or device labels are saved.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { launchSystemFirefox } from './system-firefox.mjs';

const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../build/browser-lab/evidence');
const browserKind = process.env.OVERTE_LAB_BROWSER || 'chromium';
const report = {startedAt:new Date().toISOString(), browser:browserKind, syntheticMicrophone:false, speechTest:false, completed:false};
let browser;
let page;
try {
    const {stdout} = await promisify(execFile)('pactl', ['get-default-source']);
    report.hardwareDefaultSource = stdout.trim().startsWith('alsa_input.');
    assert(report.hardwareDefaultSource, 'Host default source must be a physical ALSA microphone, not a virtual monitor');
    // Deliberately omit fake-device/fake-capture switches and use the host audio server.
    browser = browserKind === 'system-firefox'
        ? await launchSystemFirefox({syntheticMicrophone:false, executablePath:process.env.OVERTE_LAB_FIREFOX || '/usr/bin/firefox'})
        : await chromium.launch({headless:true, ignoreDefaultArgs:['--mute-audio'], args:['--use-angle=swiftshader']});
    report.browserVersion = browser.version();
    const context = await browser.newContext({permissions:browserKind === 'system-firefox' ? [] : ['microphone']});
    page = await context.newPage();
    await page.addInitScript(() => {
        const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async constraints => {
            const stream = await capture(constraints);
            window.__physicalTracks = stream.getAudioTracks();
            return stream;
        };
    });
    await page.goto(process.env.OVERTE_LAB_URL || 'http://127.0.0.1:8090');
    report.availableAudioInputs = await page.evaluate(async () =>
        (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'audioinput').length);
    assert(report.availableAudioInputs > 0, 'The browser must expose an actual audio input before a hardware capture can be tested');
    await page.locator('#domain').fill('overte://127.0.0.2:45102');
    await page.locator('#name').fill('Browser hardware microphone check');
    await page.locator('#join').click();
    await page.waitForFunction(() => window.__overte?.connected && window.__overte.entityCount >= 7, undefined, {timeout:90000});
    await page.locator('#microphone').click();
    await page.waitForFunction(() => window.__physicalTracks?.some(track => track.readyState === 'live') && window.__overte.audio.sentFrames > 50, undefined, {timeout:15000});
    report.liveAudioTracks = await page.evaluate(() => window.__physicalTracks.filter(track => track.readyState === 'live').length);
    report.captureFrames = await page.evaluate(() => window.__overte.audio.sentFrames);
    report.sampleRate = await page.evaluate(() => window.__overte.audio.sampleRate);
    await page.locator('#microphone').click();
    assert(await page.evaluate(() => window.__physicalTracks.every(track => track.readyState === 'ended')), 'Mute releases the real microphone tracks');
    report.muteReleasedHardware = true;
    await page.locator('#leave').click();
    report.completed = true;
} catch (error) {
    report.error = error.message;
    if (page) report.diagnostics = await page.evaluate(() => ({
        connected:window.__overte?.connected,
        audio:window.__overte?.audio,
        microphonePending:document.querySelector('#microphone')?.disabled,
        microphoneEnabled:document.querySelector('#microphone')?.getAttribute('aria-pressed'),
        notice:document.querySelector('#notice')?.textContent,
        trackStates:window.__physicalTracks?.map(track => track.readyState),
    })).catch(() => undefined);
    process.exitCode = 1;
} finally {
    await browser?.close();
    report.finishedAt = new Date().toISOString();
    await mkdir(directory, {recursive:true});
    await writeFile(path.join(directory, `physical-microphone-${browserKind}.json`), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
}
