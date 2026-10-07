// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Short real Chrome component diagnosis, not native-world input acceptance.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createChrome } from './runtime.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'input-probe'); assert.equal(options.browsers, 'chromium');
assert.equal(process.env.DISPLAY, ':104'); assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0'), false);
const root = resolve(options.result), directory = resolve(root, 'chromium'); await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', passed: false, steps: [], pageErrors: [], softwareOnly: true,
    scope: 'Actual product tablet/keyboard/pointer-lock component only. Test-only trusted-click capture setup; no native join, entities, avatars, microphone or input-interoperability claim.' };
const report = { mode: options.mode, started: new Date().toISOString(), browsers: [evidence], passed: false };
let browser;
try {
    browser = await createChrome(directory, { transportEvidence: false }); evidence.version = browser.version;
    const page = browser.page; page.setDefaultTimeout(10000);
    page.on('pageerror', error => { if (evidence.pageErrors.length < 10) evidence.pageErrors.push(error.message.slice(0, 2000)); });
    await page.goto('http://127.0.0.1:46106/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.overteDirectDiagnostics?.().tablet.visible === true);
    await page.locator('button[aria-label="Close tablet"]').click();
    await page.evaluate(() => {
        const canvas = document.querySelector('#world canvas');
        // The disconnected world intentionally ignores capture. This one-shot
        // fixture enables only real stock pointer lock, preserving all APIs and
        // the product's actual T handler/input-disable cleanup unchanged.
        canvas.addEventListener('click', () => canvas.requestPointerLock(), { once: true });
        window.inputProbeTrustedT = false;
        window.addEventListener('keydown', event => { if (event.code === 'KeyT' && event.isTrusted) window.inputProbeTrustedT = true; });
    });
    await page.locator('#world canvas').click();
    await page.waitForFunction(() => document.pointerLockElement === document.querySelector('#world canvas'));
    await page.keyboard.press('Escape');
    const escape = await page.evaluate(() => ({ pointerLocked: Boolean(document.pointerLockElement),
        tabletVisible: window.overteDirectDiagnostics().tablet.visible }));
    await page.keyboard.press('t');
    await page.waitForFunction(() => window.overteDirectDiagnostics().tablet.visible && document.pointerLockElement === null);
    const restored = await page.evaluate(() => ({ pointerLocked: Boolean(document.pointerLockElement),
        tabletVisible: window.overteDirectDiagnostics().tablet.visible, trustedT: window.inputProbeTrustedT,
        state: window.overteDirectDiagnostics().state }));
    assert.equal(restored.trustedT, true); assert.equal(restored.tabletVisible, true);
    assert.equal(restored.pointerLocked, false); assert.equal(restored.state, 'disconnected');
    await page.locator('#tablet-toggle').click();
    assert.equal(await page.evaluate(() => window.overteDirectDiagnostics().tablet.visible), false);
    await page.locator('#tablet-toggle').click();
    assert.equal(await page.evaluate(() => window.overteDirectDiagnostics().tablet.visible), true);
    assert.deepEqual(evidence.pageErrors, []);
    evidence.steps.push({ name: 'Trusted product T restores pointer-locked tablet and ordinary clicks work afterwards',
        passed: true, details: { escape, restored, actualProductHandler: true, captureSetupTestOnly: true, nativeJoin: false } });
    evidence.passed = true;
} catch (error) { evidence.steps.push({ name: 'Actual Chrome input component', passed: false, error: String(error.stack || error).slice(0, 3000) }); }
finally {
    if (browser) await browser.close().catch(() => undefined);
    report.passed = evidence.passed; report.finished = new Date().toISOString();
    await writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
}
process.exitCode = report.passed ? 0 : 1;
