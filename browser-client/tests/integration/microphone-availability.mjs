// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Diagnose the host capture boundary without recording audio or storing device labels/identifiers.
import { chromium } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);
const evidenceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../build/browser-lab/evidence');
const env = { ...process.env, PULSE_SERVER: process.env.OVERTE_LAB_HOST_PULSE_SERVER || `unix:/run/user/${process.getuid()}/pulse/native` };
if (process.env.OVERTE_LAB_DISPLAY) env.DISPLAY = process.env.OVERTE_LAB_DISPLAY;
const report = {
    startedAt: new Date().toISOString(), syntheticMicrophone: false, recordings: false,
    hostCaptureSourceCount: 0, defaultSourceIsPhysicalAlsa: false, defaultSourcePortCount: 0,
    defaultSourcePortAvailability: { available: 0, unavailable: 0, unknown: 0 }, probes: [],
    primarySource: 'https://chromium.googlesource.com/chromium/src/+/main/media/audio/pulse/audio_manager_pulse.cc',
    chromiumReason: 'AudioManagerPulse::InputDevicesInfoCallback excludes output monitors and excludes a source with ports when all report PA_PORT_AVAILABLE_NO. Firefox opening an ALSA capture device does not prove a connected microphone or human speech.',
};
const availability = value => value === 'available' ? 'available' : value === 'not available' ? 'unavailable' : 'unknown';
const monitor = source => String(source.name || '').endsWith('.monitor') ||
    (typeof source.monitor_of_sink === 'number' && source.monitor_of_sink !== 4294967295);
const { stdout: defaultSource } = await run('pactl', ['get-default-source'], { env });
const { stdout: sourceData } = await run('pactl', ['-f', 'json', 'list', 'sources'], { env });
const sources = JSON.parse(sourceData);
report.hostCaptureSourceCount = sources.filter(source => !monitor(source)).length;
const selected = sources.find(source => source.name === defaultSource.trim());
report.defaultSourceIsPhysicalAlsa = !!selected && String(selected.name).startsWith('alsa_input.');
for (const port of Object.values(selected?.ports || {})) {
    report.defaultSourcePortCount++;
    report.defaultSourcePortAvailability[availability(port.availability)]++;
}
const server = http.createServer((_request, response) => {
    response.setHeader('content-type', 'text/html');
    response.end('<!doctype html><title>Isolated microphone availability probe</title>');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const variants = [
    { name: 'playwright-headless-shell', headless: true },
    { name: 'playwright-full-chrome-headless', headless: true, executablePath: chromium.executablePath() },
];
if (process.env.OVERTE_LAB_DISPLAY) variants.push({ name: 'playwright-full-chrome-headful', headless: false, executablePath: chromium.executablePath() });
if (process.env.OVERTE_LAB_CHROMIUM) variants.push({ name: 'system-chromium-headless', headless: true, executablePath: process.env.OVERTE_LAB_CHROMIUM });
try {
    for (const variant of variants) {
        const probe = { browserMode: variant.name, startedAt: new Date().toISOString() };
        let browser;
        try {
            const { name, ...options } = variant;
            const browserEnv = name === 'system-chromium-headless' && process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH
                ? { ...env, LD_LIBRARY_PATH: process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH } : env;
            browser = await chromium.launch({ ...options, env: browserEnv, ignoreDefaultArgs: ['--mute-audio'], args: ['--use-angle=swiftshader'], timeout: 30000 });
            probe.browserVersion = browser.version();
            const context = await browser.newContext({ permissions: ['microphone'] });
            const page = await context.newPage();
            await page.goto(`http://127.0.0.1:${server.address().port}`);
            Object.assign(probe, await page.evaluate(async () => {
                const audioInputs = (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'audioinput').length;
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    const liveTracks = stream.getAudioTracks().filter(track => track.readyState === 'live').length;
                    stream.getTracks().forEach(track => track.stop());
                    return { audioInputs, liveTracks };
                } catch (error) { return { audioInputs, captureError: error.name }; }
            }));
        } catch (error) { probe.probeError = error.name; }
        finally { await browser?.close(); probe.finishedAt = new Date().toISOString(); report.probes.push(probe); }
    }
} finally { await new Promise(resolve => server.close(resolve)); }
report.finishedAt = new Date().toISOString();
await mkdir(evidenceDirectory, { recursive: true });
await writeFile(path.join(evidenceDirectory, 'microphone-availability.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report));
