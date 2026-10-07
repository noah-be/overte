// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted real-browser acceptance driver. It does not replace native peers.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, appendFile, mkdir, open, rename } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createChrome, readTransportEvidence, readAvatarWorkerEvidence } from './runtime.mjs';
import { readSceneAssetAudit, probeSourceEffectCORS } from './asset-evidence.mjs';
import { captureCPUProfile } from './cpu-profile.mjs';
import { horizontalDistance, bodyCenter, requireNativeBinding, validateBrowserMovement, validateNativeMovement } from './native-motion-evidence.mjs';
import { withRecordedCleanup } from './operation-cleanup.mjs';
import { readNativeHostProof, nativeMotionOperation as requestNativeMotion } from './native-host-motion.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
const resultRoot = resolve(options.result);
const client = dirname(dirname(fileURLToPath(import.meta.url)));
const timeout = Number(options.timeout || 55) * 1000;
const browsers = (options.browsers || 'chromium').split(',');
assert.deepEqual(browsers, ['chromium'], 'Current acceptance scope is Chrome only');
const endpoint = 'ws://127.0.0.1:46104/';
const expectedEntities = Number(options['expected-entities'] || 83);
const labRoot = resolve(client, '../build/browser-direct/lab');
const origin = 'http://127.0.0.1:46106';
const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
const executeFile = promisify(execFile);
const bounded = value => String(value).slice(0, 3000).replace(/(?:token|password|secret|authorization)[=: ]+[^\s]+/gi, '[redacted]');
const failureReaders = new WeakMap();
const report = {
    started: new Date().toISOString(), mode: options.mode, origin, endpoint, expectedEntities,
    isolation: { display: process.env.DISPLAY, gpuDevicesMounted: existsSync('/dev/dri') || existsSync('/dev/nvidia0'),
        softwareRenderingOnly: true, syntheticAudioOnly: true, physicalMicrophoneTested: false },
    automation: { playwright: JSON.parse(await readFile(resolve(client, 'node_modules/@playwright/test/package.json'), 'utf8')).version },
    bundleManifestSha256: createHash('sha256').update(await readFile(resolve(resultRoot, 'bundle-manifest.json'))).digest('hex'),
    browsers: [], passed: false,
};
assert.equal(process.env.DISPLAY, ':104', 'Use the private software-run.py browser display');
assert.equal(report.isolation.gpuDevicesMounted, false, 'The browser must not see hardware GPU devices');
assert.ok(process.env.PLAYWRIGHT_BROWSERS_PATH?.includes('/build/browser-direct/browsers'), 'Use own downloaded browser cache');
if (options.mode === 'direct' || options.mode === 'scene-probe') report.sceneAssetAudit = await readSceneAssetAudit(labRoot);
if (options.mode === 'scene-probe') report.scope = 'Bounded real native join, assets and rendering diagnosis only; not native avatar, input or audio interoperability acceptance';
// software-run.py binds this worktree's private temporary directory onto /tmp.
// Chromium's Unix singleton socket must fit sockaddr_un's short path limit.
process.env.TMPDIR = '/tmp';



async function until(page, predicate, limit = timeout, failOnSessionError = false, requireConnection = false) {
    const started = Date.now();
    while (Date.now() - started < limit) {
        if (await page.evaluate(predicate)) return;
        if (failOnSessionError || requireConnection) {
            const current = await diagnostics(page);
            if (current.app?.state === 'error') throw new Error(current.notice || 'The native connection failed');
            if (requireConnection && current.app?.state === 'disconnected') {
                const failure = current.sessionMessages?.workers.find(worker => worker.firstFailure)?.firstFailure;
                throw new Error(failure?.reason || 'The native session disconnected while the real scene was loading.');
            }
        }
        await pause(200);
    }
    throw new Error(`Browser condition did not become true within ${limit}ms`);
}

function recordLive(page, evidence, path) {
    let inFlight = Promise.resolve(), writing = false;
    evidence.liveDiagnosticSamples = { count: 0, retained: 0, limit: 96, intervalMs: 5000 };
    const timer = setInterval(() => {
        if (writing) return; writing = true;
        inFlight = (async () => {
            const current = { observedAt: new Date().toISOString(), ...await diagnostics(page) };
            await writeFile(`${path}.pending`, `${JSON.stringify(current, null, 2)}\n`, { mode: 0o600 });
            await rename(`${path}.pending`, path); evidence.liveDiagnosticSamples.count++;
            if (evidence.liveDiagnosticSamples.retained < evidence.liveDiagnosticSamples.limit) {
                await appendFile(path.replace(/\.json$/, '-timeline.ndjson'), `${JSON.stringify(current)}\n`, { mode: 0o600 });
                evidence.liveDiagnosticSamples.retained++;
            }
        })().catch(error => {
            evidence.liveDiagnosticErrors ||= [];
            if (evidence.liveDiagnosticErrors.length < 10) evidence.liveDiagnosticErrors.push(bounded(error.message));
        }).finally(() => { writing = false; });
    }, 5000);
    return async () => { clearInterval(timer); await inFlight; };
}

async function diagnostics(page) {
    const main = await page.evaluate(() => ({ app: window.overteDirectDiagnostics?.(), rtc: window.overteDirectTransportEvidence?.(),
        longTasks: window.overteLongTaskEvidence?.(), sessionMessages: window.overteSessionMessageEvidence?.(),
        modelLoads: window.overteModelLoadEvidence?.(),
        localNotices: window.overteLocalNoticeEvidence?.(),
        input: { pointerLocked: Boolean(document.pointerLockElement),
            canvasFocused: document.activeElement === document.querySelector('#world canvas') },
        notice: document.querySelector('#notice')?.textContent, connection: document.querySelector('#connection')?.textContent }));
    return { ...main, ...await readTransportEvidence(page, main.rtc) };
}

async function requireActiveSession(page) {
    const current = await page.evaluate(() => ({ state: window.overteDirectDiagnostics().state,
        notice: document.querySelector('#notice')?.textContent,
        failure: window.overteSessionMessageEvidence?.().workers.find(worker => worker.firstFailure)?.firstFailure }));
    if (current.state !== 'connected') throw new Error(current.failure?.reason || current.notice
        || 'The actual native session is no longer connected.');
}

async function untilTransportClosed(page) {
    const started = Date.now();
    while (Date.now() - started < 8000) {
        const current = await readTransportEvidence(page);
        if (current.rtc.every(peer => peer.connectionState === 'closed')
                && current.workerTransport.unavailableWorkers === 0
                && current.workerTransport.channels.every(channel => channel.readyState === 'closed')) return;
        await pause(100);
    }
    throw new Error('Main RTC peers or actual transferred worker channels did not close after leave.');
}

async function showTablet(browser, visible) {
    const current = await browser.page.evaluate(() => ({ shown: window.overteDirectDiagnostics().tablet.visible,
        locked: Boolean(document.pointerLockElement) }));
    if (current.shown !== visible) {
        // Chrome's browser-level Escape shortcut is not guaranteed to run for
        // CDP keyboard input. Use the app's real trusted T shortcut when locked:
        // opening the tablet disables world input and calls exitPointerLock().
        if (current.locked) await browser.page.keyboard.press('t');
        else await browser.click(visible ? '#tablet-toggle' : 'button[aria-label="Close tablet"]');
    }
    const shown = await browser.page.waitForFunction(wanted => window.overteDirectDiagnostics().tablet.visible === wanted
        && (!wanted || document.pointerLockElement === null), visible, { timeout: 8000, polling: 100 });
    await shown.dispose();
}

async function captureMouse(browser) {
    await showTablet(browser, false);
    await browser.page.mouse.move(640, 400); await browser.click('#world canvas');
    await until(browser.page, () => document.pointerLockElement === document.querySelector('#world canvas'), 8000);
    assert.equal(await browser.page.evaluate(() => document.activeElement === document.querySelector('#world canvas')), true,
        'Trusted world input must focus the actual canvas rather than a tablet button');
}

async function restoreTabletAfter(browser, operation) {
    let failure;
    try { return await operation(); }
    catch (error) { failure = error; throw error; }
    finally {
        try {
            await browser.page.keyboard.up('w'); await browser.page.keyboard.up('Space');
            await browser.page.keyboard.press('Escape'); await showTablet(browser, true);
        } catch (error) { if (!failure) throw error; }
    }
}

async function firstPerson(browser) {
    await showTablet(browser, true);
    await browser.click('button[aria-controls="tablet-avatar"]');
    const before = await browser.page.evaluate(() => window.overteDirectDiagnostics().selfAvatar);
    const checkbox = browser.page.locator('#tablet-avatar input[type="checkbox"]');
    if (await checkbox.isChecked()) await checkbox.uncheck();
    await until(browser.page, () => window.overteDirectDiagnostics().selfAvatar.thirdPerson === false, 10000, true, true);
    return { before, after: await browser.page.evaluate(() => window.overteDirectDiagnostics().selfAvatar),
        action: 'Trusted actual Avatar-app checkbox', browserTeleported: false };
}

async function untilValue(page, predicate, argument, limit = timeout) {
    const started = Date.now();
    while (Date.now() - started < limit) {
        const value = await page.evaluate(predicate, argument);
        if (value) return value;
        await requireActiveSession(page); await pause(200);
    }
    throw Error(`Actual browser evidence did not complete within ${limit}ms`);
}

async function aimAtActualPoint(browser, point) {
    await captureMouse(browser);
    const frameBefore = await browser.page.evaluate(() => window.overteDirectDiagnostics().performance.renderedFrames);
    const before = await browser.page.evaluate(() => window.overteInspectView());
    const dx = point.x - before.cameraPosition.x, dy = point.y - before.cameraPosition.y, dz = point.z - before.cameraPosition.z;
    const yaw = Math.atan2(-dx, -dz), pitch = Math.atan2(dy, Math.hypot(dx, dz));
    const deltaYaw = Math.atan2(Math.sin(yaw - before.yaw), Math.cos(yaw - before.yaw));
    const movement = { x: -deltaYaw / 0.0025, y: -(pitch - before.pitch) / 0.0025 };
    await browser.page.mouse.move(640 + movement.x, 400 + movement.y, { steps: 8 });
    await untilValue(browser.page, frame => window.overteDirectDiagnostics().performance.renderedFrames > frame, frameBefore, 10000);
    const after = await browser.page.evaluate(() => ({ view: window.overteInspectView(), mouse: window.overteMouseEvidence() }));
    assert.ok(after.mouse.lockedTrustedEvents > 0, 'Use actual trusted mouse events while pointer locked');
    assert.ok(Math.abs(after.view.yaw - yaw) < 0.03 && Math.abs(after.view.pitch - pitch) < 0.03, 'Trusted mouse input must aim the actual camera at the source-owned point');
    return { before, desiredPoint: point, movement, frameBefore, ...after,
        actualCameraTargetDistance: Math.hypot(point.x - after.view.cameraPosition.x,
            point.y - after.view.cameraPosition.y, point.z - after.view.cameraPosition.z), testTeleport: false };
}

async function nativeObservation() {
    const path = resolve(labRoot, 'logs/native-visitor.log');
    if (!existsSync(path)) return undefined;
    const file = await open(path, 'r');
    let source;
    try {
        const { size } = await file.stat(); const bytes = Buffer.alloc(Math.min(size, 262144));
        const { bytesRead } = await file.read(bytes, 0, bytes.length, Math.max(0, size - bytes.length));
        source = bytes.subarray(0, bytesRead).toString('utf8');
    } finally { await file.close(); }
    for (const line of source.split('\n').reverse()) {
        const marker = line.indexOf('DIRECT_LAB_NATIVE ');
        if (marker >= 0) {
            try { return JSON.parse(line.slice(marker + 'DIRECT_LAB_NATIVE '.length)); } catch { /* Partial writes are retried. */ }
        }
    }
}

async function nativeProcessIdentity() {
    const proof = await readNativeHostProof(resolve(resultRoot, 'native-host-actions'));
    return proof.processIdentity;
}

async function waitNative(predicate, limit = timeout) {
    const started = Date.now();
    while (Date.now() - started < limit) {
        const observation = await nativeObservation();
        if (observation && predicate(observation)) return observation;
        await pause(250);
    }
    throw new Error('The actual packaged native observer did not report the expected peer state');
}

async function nativePeerProof(browser, directory, name) {
    if (options['native-peer'] !== 'true') return { notRun: 'Pinned packaged native visitor is not running in this scenario' };
    await requireActiveSession(browser.page);
    const processIdentity = await nativeProcessIdentity();
    const page = browser.page, expectedPose = (await diagnostics(page)).app.pose.position;
    const observation = await waitNative(state => state.connected && state.peers.some(peer => peer.displayName === `direct-${name}`
        && Math.hypot(peer.position.x - expectedPose.x, peer.position.z - expectedPose.z) < 3));
    await until(page, () => { const geometry = window.overteDirectDiagnostics().participantGeometry;
        return geometry.remoteRoots > 0 && geometry.rigRoots > 0 && !geometry.censored; });
    const nativeID = observation.session;
    const initial = await page.evaluate(id => window.overteObserveAvatarRendering([id], 100), nativeID);
    const native = initial.entities[0]; assert.equal(native.rigLoaded, true, 'The actual network participant must load its real rig');
    assert.ok(native.bounds, 'Use actual loaded participant geometry for the view target');
    const point = Object.fromEntries(['x', 'y', 'z'].map(axis => [axis, (native.bounds.min[axis] + native.bounds.max[axis]) / 2]));
    const cameraInput = await aimAtActualPoint(browser, point);
    const rendered = await page.evaluate(id => window.overteObserveAvatarRendering([id], 4000), nativeID);
    assert.equal(rendered.entities[0].rigLoaded, true); assert.equal(rendered.entities[0].excludesAvatarLabel, true);
    assert.ok(rendered.entities[0].submittedDraws > 0 && rendered.entities[0].submittedTriangles > 0, 'Actual native rig/body meshes must submit main-camera draws');
    await browser.screenshot(resolve(directory, 'native-avatar-visible.png'));
    const current = await diagnostics(page), remote = observation.peers.find(peer => peer.displayName === `direct-${name}`);
    assert.ok(Math.hypot(remote.position.x - current.app.pose.position.x, remote.position.z - current.app.pose.position.z) < 3);
    assert.deepEqual(await nativeProcessIdentity(), processIdentity);
    const binding = { processIdentity, nativeSession: observation.session, browserPeerID: remote.id };
    return { nativeRelease: '2026.04.1', nativeObservation: observation, browserParticipants: current.app.participants,
        peerGeometry: current.app.participantGeometry, rendered, cameraInput, binding,
        nativePlacement: 'Owned native visitor may use separately recorded scripted native placement after proving ordinary domain spawn; browser position is never overridden' };
}

async function nativeMotionOperation(operation, binding) {
    return requestNativeMotion(operation, binding, resolve(resultRoot, 'native-host-actions'));
}

async function nativeMotionProof(browser, directory, binding, evidence) {
    if (options['native-peer'] !== 'true') return { notRun: 'Pinned packaged native visitor is absent' };
    assert.ok(binding, 'Initial actual native rig proof is required before native motion');
    await requireActiveSession(browser.page);
    const pipeline = async () => ({ observedAtUnixMs: Date.now(), worker: await readAvatarWorkerEvidence(browser.page),
        pageWorkerMessage: await browser.page.evaluate(() => window.overteAvatarPageMessageEvidence?.()),
        scope: 'Raw first record and actual worker post plus page Worker message event; no private facade callback claim' });
    const details = { setup: 'Explicit native-only one-metre -Z move along the actual bridge and restore after ordinary native spawn and actual rig proof',
        browserTeleported: false, pipelineBefore: await pipeline(), pipelineSamples: [] };
    evidence.nativeMotionControl = details;
    const before = await nativeObservation();
    assert.equal(before.nativeMotionControlVersion, 2); assert.equal(before.nativeMotionTest, null);
    requireNativeBinding(binding, before, await nativeProcessIdentity(), -1);
    const renderedBefore = await browser.page.evaluate(id => window.overteObserveAvatarRendering([id], 100), binding.nativeSession);
    const originalCenter = bodyCenter(renderedBefore, binding.nativeSession);
    details.nativeBefore = before; details.renderedBefore = renderedBefore;
    return withRecordedCleanup(async () => {
        details.phase = 'native-move';
        details.move = await nativeMotionOperation('motion-move', binding);
        assert.equal(details.move.session, binding.nativeSession);
        details.phase = 'native-confirmation';
        const after = await waitNative(state => state.sequence >= details.move.nativeSequenceAfter
            && state.nativeMotionTest?.requestId === details.move.requestId && state.nativeMotionTest.phase === 'moved', 10000);
        details.nativeAfter = after; details.phase = 'received-body';
        details.bodySamples = []; details.bodySamplesEvicted = 0;
        let latest, measured;
        const started = Date.now();
        while (Date.now() - started < 15000) {
            latest = await browser.page.evaluate(id => window.overteObserveAvatarRendering([id], 100), binding.nativeSession);
            const center = bodyCenter(latest, binding.nativeSession);
            if (details.pipelineSamples.length < 16) details.pipelineSamples.push({ elapsedMs: Date.now() - started, ...await pipeline() });
            details.lastBody = latest;
            const difference = Math.hypot(center.x - originalCenter.x - (after.position.x - before.position.x),
                center.z - originalCenter.z - (after.position.z - before.position.z));
            if (details.bodySamples.length === 16) { details.bodySamples.shift(); details.bodySamplesEvicted++; }
            details.bodySamples.push({ elapsedMs: Date.now() - started, ownerPosition: latest.entities[0].ownerPosition,
                bodyCenter: center, displacementError: difference });
            if (difference <= 0.25) { measured = latest; break; }
        }
        assert.ok(measured, 'A newer actual native position must reach the loaded remote body');
        details.phase = 'camera-and-draws';
        details.cameraInput = await aimAtActualPoint(browser, bodyCenter(measured, binding.nativeSession));
        details.renderedAfter = await browser.page.evaluate(id => window.overteObserveAvatarRendering([id], 4000), binding.nativeSession);
        details.motion = validateNativeMovement(binding, before, after, await nativeProcessIdentity(), renderedBefore, details.renderedAfter);
        await browser.screenshot(resolve(directory, 'native-avatar-moved.png'));
        return details;
    }, async () => {
        details.cleanup = { primaryKind: 'native-restore', cleanupKind: 'tablet-recovery' };
        await withRecordedCleanup(async () => {
            details.phase = 'native-restore';
            const current = await nativeObservation();
            if (current?.session === binding.nativeSession && current.nativeMotionTest?.phase === 'moved') {
                details.restore = await nativeMotionOperation('motion-restore', binding);
                details.pipelineAfterRestore = await pipeline();
                assert.equal(details.restore.session, binding.nativeSession); assert.equal(details.restore.nativeMotionTest.phase, 'restored');
                assert.ok(details.restore.nativeSequenceAfter > details.restore.nativeSequenceBefore);
                assert.ok(horizontalDistance(details.restore.positionAfter, before.position) <= 0.25, 'Restore the actual native-only setup');
            }
        }, async () => {
            details.phase = 'tablet-recovery';
            await showTablet(browser, true);
        }, details.cleanup, error => bounded(error?.stack || error));
    }, details, error => ({ phase: details.phase, error: bounded(error?.stack || error) }));
}

async function audioTool(operation, participant, frequency, seconds) {
    const { stdout } = await executeFile('python3', [resolve(client, 'lab/synthetic-audio.py'), operation,
        '--participant', participant, '--frequency', String(frequency), '--seconds', String(seconds)],
    { cwd: client, timeout: (seconds + 12) * 1000, maxBuffer: 32768 });
    const result = JSON.parse(stdout.trim()); assert.equal(result.syntheticOnly, true);
    assert.equal(result.physicalMicrophoneTested, false); return result;
}

async function step(evidence, name, operation) {
    const started = Date.now();
    try {
        const details = await operation();
        if (details?.notRun) {
            evidence.steps.push({ name, passed: null, elapsedMs: Date.now() - started, notRun: details.notRun });
            await writeFile(resolve(evidence.directory, 'progress.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
            console.log(JSON.stringify({ browser: evidence.browser, step: name, passed: null, notRun: details.notRun }));
            return false;
        }
        evidence.steps.push({ name, passed: true, elapsedMs: Date.now() - started, ...(details === undefined ? {} : { details }) });
        await writeFile(resolve(evidence.directory, 'progress.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
        console.log(JSON.stringify({ browser: evidence.browser, step: name, passed: true }));
        return true;
    } catch (error) {
        let current;
        try { current = await failureReaders.get(evidence)?.(); } catch { /* Preserve the original failure if the browser is already gone. */ }
        evidence.steps.push({ name, passed: false, elapsedMs: Date.now() - started, error: bounded(error?.stack || error),
            ...(current ? { failureDiagnostics: current } : {}) });
        await writeFile(resolve(evidence.directory, 'progress.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
        console.log(JSON.stringify({ browser: evidence.browser, step: name, passed: false, error: bounded(error?.message || error) }));
        return false;
    }
}

for (const name of browsers) {
    const directory = resolve(resultRoot, name); await mkdir(directory, { recursive: true });
    const evidence = { browser: name, directory, steps: [], console: [], warningsAndErrors: [], shaderErrors: [], requestFailures: [], responses: [],
        pageErrors: [], pageErrorDetails: [], expectedNetworkDiagnostics: [], passed: false };
    report.browsers.push(evidence);
    let browser, stopLiveRecording, cpuProfileTask, nativeBinding;
    try {
        const nativeQualification = options.mode === 'direct' && options['native-peer'] === 'true'
            ? JSON.parse(await readFile(resolve(labRoot, 'runtime/native-visitor-qualification.json'), 'utf8')) : undefined;
        const avatarEvidence = nativeQualification ? { expectedNativeID: nativeQualification.explicitNativePlacementObservation.session, pageMessages: true } : undefined;
        browser = await createChrome(directory, { origin, syntheticAudio: options['synthetic-audio'] === 'true', longTasks: true, avatarEvidence });
        evidence.version = browser.version; evidence.automation = browser.automation;
        evidence.fixtureCertificateSPKI = browser.fixtureCertificateSPKI;
        const page = browser.page;
        failureReaders.set(evidence, () => diagnostics(page));
        stopLiveRecording = recordLive(page, evidence, resolve(directory, 'live-diagnostics.json'));
        page.on('pageerror', error => {
            // Stock Firefox BiDi reports these browser network diagnostics as
            // pageerror events; keep them visible and separate from exceptions.
            const value = bounded(error.message);
            if (value === 'Firefox can’t establish a connection to the server at ws://127.0.0.1:46118/.'
                || value === "Firefox can't establish a connection to the server at ws://127.0.0.1:46118/."
                || value === 'The connection to ws://127.0.0.1:46118/ was interrupted while the page was loading.') {
                if (evidence.expectedNetworkDiagnostics.length < 30) evidence.expectedNetworkDiagnostics.push(value);
            } else if (evidence.pageErrors.length < 30) {
                evidence.pageErrors.push(value);
                evidence.pageErrorDetails.push({ name: error.name, message: value, stack: bounded(error.stack || error.message) });
            }
        });
        page.on('console', message => {
            const value = message.text();
            if (evidence.shaderErrors.length < 30 && /(?:Shader Error|WebGLProgram.*(?:Error|failed)|program.*not linked|linking failed|invalid program)/i.test(value)) {
                evidence.shaderErrors.push(bounded(value));
            }
            if (evidence.warningsAndErrors.length < 60 && ['warning', 'error'].includes(message.type())) {
                evidence.warningsAndErrors.push({ type: message.type(), text: /\b(sdp|candidate|secret|password|token|authorization)\b/i.test(value) ? '[sensitive protocol log omitted]' : bounded(value) });
            }
            if (evidence.console.length >= 120) return;
            evidence.console.push({ type: message.type(), text: /\b(sdp|candidate|secret|password|token|authorization)\b/i.test(value) ? '[sensitive protocol log omitted]' : bounded(value) });
        });
        page.on('requestfailed', request => {
            if (evidence.requestFailures.length < 60) evidence.requestFailures.push({ url: bounded(request.url()).replace(/\?.*/, ''), failure: request.failure() });
        });
        page.on('response', response => {
            if (evidence.responses.length < 120) evidence.responses.push({ url: bounded(response.url()).replace(/\?.*/, ''), status: response.status() });
        });
        const booted = await step(evidence, 'Production app and software WebGL', async () => {
            await page.goto(`${origin}/?server=${encodeURIComponent(endpoint)}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
            await until(page, () => typeof window.overteDirectDiagnostics === 'function', 30000);
            const nativeSessionWorker = await browser.prepareTransportEvidence(true);
            const result = await page.evaluate(() => {
                const canvas = document.querySelector('#world canvas'); const gl = canvas?.getContext('webgl2');
                const extension = gl?.getExtension('WEBGL_debug_renderer_info');
                return { userAgent: navigator.userAgent, secureContext: isSecureContext, serviceWorker: Boolean(navigator.serviceWorker),
                    webgl2: Boolean(gl), renderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER),
                    vendor: extension ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL) : gl?.getParameter(gl.VENDOR),
                    canvas: canvas ? { width: canvas.width, height: canvas.height } : null,
                    videoElements: document.querySelectorAll('video').length, mediaElements: document.querySelectorAll('video,audio,iframe').length };
            });
            assert.equal(result.webgl2, true, 'The real renderer must create WebGL2');
            assert.match(result.renderer || '', /swiftshader|llvmpipe|swrast|software/i, 'Record an actual software GL renderer');
            assert.equal(result.secureContext, true); assert.equal(result.serviceWorker, true);
            assert.equal(result.mediaElements, 0, 'The tablet must execute locally without streamed UI');
            return { ...result, nativeSessionWorker };
        });
        if (!booted) {
            evidence.failedBoot = await page.evaluate(() => ({ url: location.href, title: document.title,
                body: document.body?.textContent?.slice(0, 1500), scripts: [...document.scripts].map(script => script.src),
                resources: performance.getEntriesByType('resource').map(entry => ({ name: entry.name, duration: entry.duration })) }));
            await browser.screenshot(resolve(directory, 'boot-error.png')); continue;
        }
        await step(evidence, 'Six local tablet applications and graphics callback', async () => {
            for (const app of ['Domain', 'People', 'Avatar', 'Audio', 'Graphics', 'Snapshot']) {
                await browser.click(`button[aria-controls="tablet-${app.toLowerCase()}"]`);
                const active = await page.evaluate(() => window.overteDirectDiagnostics().tablet.app);
                assert.equal(active, app);
            }
            await browser.click('button[aria-controls="tablet-audio"]');
            const disabled = await page.evaluate(() => document.querySelector('#tablet-audio button').disabled);
            assert.equal(disabled, true, 'No microphone can be enabled while disconnected');
            await browser.click('button[aria-controls="tablet-graphics"]');
            const slider = page.locator('#tablet-graphics label:first-of-type input[type="range"]');
            const initialValue = await slider.inputValue();
            await slider.focus(); await page.keyboard.press('ArrowLeft');
            await until(page, () => document.querySelector('#notice').textContent.includes('Graphics setting applied'), 5000);
            assert.notEqual(await slider.inputValue(), initialValue);
            await page.keyboard.press('ArrowRight');
            assert.equal(await slider.inputValue(), initialValue, 'Restore the original graphics setting after the callback check');
            await browser.click('button[aria-controls="tablet-domain"]');
            return { applications: 6, microphoneInitiallyDisabled: disabled, renderedTablet: 'browser DOM', graphicsRestoredToInitialValue: initialValue };
        });
        if (options.mode === 'direct' || options.mode === 'scene-probe') {
            const joined = await step(evidence, 'Actual native WebRTC join and entities', async () => {
                await browser.fill('#tablet-domain input[name="endpoint"]', endpoint);
                await browser.click('#tablet-domain button[type="submit"]');
                await until(page, () => window.overteDirectDiagnostics().state === 'connected', timeout, true);
                const current = await diagnostics(page);
                assert.equal(current.app.receivedEntities, expectedEntities, 'Prepared native lab scene entity count');
                assert.equal(current.app.entities, expectedEntities);
                assert.ok(current.rtc.some(peer => peer.connectionState === 'connected'), 'An actual main-owned RTCPeerConnection must connect');
                assert.ok(current.workerTransport.workersObserved > 0 && current.workerTransport.unavailableWorkers === 0);
                assert.ok(current.workerTransport.channels.some(channel => channel.readyState === 'open' && channel.receivedBytes > 0 && channel.sentBytes > 0),
                    'Native packets must flow through the actual transferred DataChannel in the dedicated worker');
                return current;
            });
            if (joined) {
                await step(evidence, 'Native default path supplies historical Hub spawn', async () => {
                    await until(page, () => { const point = window.overteDirectDiagnostics().pose?.position; return point && Math.abs(point.x - 155.084) < 3 && Math.abs(point.z + 397.328) < 3; }, 12000);
                    const current = await diagnostics(page);
                    assert.ok(Math.abs(current.app.pose.position.y + 98.5) < 6, 'Native spawn height must be close to actual domain path');
                    return { actualPose: current.app.pose, expectedPath: '/155.084,-98.5,-397.328/0,0,0,1', testTeleport: false };
                });
                await step(evidence, 'Local Avatar app applies actual identity and view', async () => {
                    await browser.click('button[aria-controls="tablet-avatar"]');
                    await browser.fill('#tablet-avatar form label:first-child input', `direct-${name}`);
                    await browser.click('#tablet-avatar button[type="submit"]');
                    await browser.click('#tablet-avatar > label input[type="checkbox"]');
                    await page.evaluate(value => { window.overteExpectedLocalDisplayName = value; }, `direct-${name}`);
                    await until(page, () => {
                        const identity = JSON.parse(localStorage.getItem('overte.direct.identity.v1') || 'null');
                        return identity?.displayName === window.overteExpectedLocalDisplayName
                            && window.overteDirectDiagnostics().selfAvatar?.thirdPerson === true;
                    }, 5000, true, true);
                    return { displayName: `direct-${name}`, defaultModel: 'qrc:/meshes/defaultAvatar_full.fst' };
                });
                if (options.mode === 'scene-probe') cpuProfileTask = captureCPUProfile(page, directory, resolve(resultRoot, 'bundle'), () => diagnostics(page))
                    .then(value => { evidence.cpuProfile = value; }, error => { evidence.cpuProfileError = bounded(error.stack || error); });
                await step(evidence, 'Native ATP files retain actual FST, FBX and image bytes', async () => {
                    const provenancePath = resolve(labRoot, 'scene/asset-provenance.json');
                    assert.ok(existsSync(provenancePath), 'Prepare actual native AssetServer files and mappings first');
                    const provenance = JSON.parse(await readFile(provenancePath, 'utf8'));
                    const representatives = [/\.fst$/i, /\.fbx$/i, /\.(png|jpe?g)$/i].map(extension => {
                        const matching = provenance.records.filter(record => extension.test(record.relativePath) && record.servedSHA256 === record.sourceSHA256)
                            .sort((left, right) => left.servedBytes - right.servedBytes);
                        assert.ok(matching.length > 0, `Missing original-byte asset for ${extension}`); return matching[0];
                    });
                    await until(page, () => performance.getEntriesByType('resource').some(entry => /\/_overte-atp\/[^/]+\//.test(entry.name)), 12000);
                    const prefix = await page.evaluate(() => performance.getEntriesByType('resource').map(entry => entry.name.match(/^(.*\/_overte-atp\/[^/]+\/)/)?.[1]).find(Boolean));
                    const result = [];
                    for (const record of representatives) {
                        const asset = await page.evaluate(async ({ prefix, record }) => {
                            const response = await fetch(prefix + record.relativePath, { cache: 'no-store' });
                            const bytes = await response.arrayBuffer(); const digest = await crypto.subtle.digest('SHA-256', bytes);
                            return { path: record.relativePath, status: response.status, bytes: bytes.byteLength,
                                sha256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') };
                        }, { prefix, record });
                        assert.equal(asset.status, 200); assert.equal(asset.bytes, record.servedBytes);
                        assert.equal(asset.sha256, record.sourceSHA256); result.push(asset);
                    }
                    return { files: result, serviceWorkerOrigin: new URL(prefix).origin, transport: 'native AssetServer DataChannel; same connected DirectSession' };
                });
                await step(evidence, 'HTTPS fixture retains original asset bytes with browser CORS', async () => {
                    const provenance = JSON.parse(await readFile(resolve(labRoot, 'scene/asset-provenance.json'), 'utf8'));
                    const samples = [/\.fst$/i, /\.fbx$/i, /\.(png|jpe?g)$/i].map(extension => provenance.records
                        .filter(record => extension.test(record.relativePath) && record.servedSHA256 === record.sourceSHA256)
                        .sort((left, right) => left.servedBytes - right.servedBytes)[0]);
                    assert.ok(browser.fixtureCertificateSPKI, 'Trust only the owned fixture certificate public key');
                    const result = [];
                    for (const record of samples) {
                        const file = await page.evaluate(async record => {
                            const response = await fetch(`https://127.0.0.1:46119/${record.relativePath}`, { mode: 'cors', cache: 'no-store' });
                            const bytes = await response.arrayBuffer(); const digest = await crypto.subtle.digest('SHA-256', bytes);
                            return { path: record.relativePath, status: response.status, responseType: response.type, bytes: bytes.byteLength,
                                sha256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') };
                        }, record);
                        assert.equal(file.status, 200); assert.equal(file.responseType, 'cors');
                        assert.equal(file.bytes, record.servedBytes); assert.equal(file.sha256, record.sourceSHA256); result.push(file);
                    }
                    return { files: result, fixtureCertificateSPKI: browser.fixtureCertificateSPKI,
                        origin: 'https://127.0.0.1:46119', note: 'Own CORS-enabled static asset fixture; original public CDN CORS remains separate' };
                });
                await step(evidence, 'All real model geometry, available textures and default avatar render', async () => {
                    await until(page, () => { const p = window.overteDirectDiagnostics().performance; return p.loadedModels === 55
                        && p.loadingModels === 0 && p.queuedModels === 0 && p.compilingGraphics === 0
                        && p.imageLoading.active === 0 && p.imageLoading.pending === 0
                        && p.fbxPreparation.active === 0 && p.fbxPreparation.queued === 0 && (p.sourceTextLoading?.active || 0) === 0
                        && p.textures > 0 && p.loadedAvatars > 0 && p.renderedFrames > 0; }, timeout, true, true);
                    await until(page, () => window.overteDirectDiagnostics().selfAvatar.selfVisible === true, 15000, true, true);
                    const current = await diagnostics(page); await browser.screenshot(resolve(directory, 'render-tablet.png'));
                    return current;
                });
                await step(evidence, 'Known unavailable original PSD remains explicit without substituted pixels', async () => {
                    await requireActiveSession(page);
                    const modelLoads = await page.evaluate(() => window.overteModelLoadEvidence());
                    assert.equal(modelLoads.total, 55); assert.equal(modelLoads.loaded, 55); assert.equal(modelLoads.failed, 0);
                    assert.equal(modelLoads.incompleteModels, 1); assert.equal(modelLoads.unavailableTextures, 1); assert.equal(modelLoads.omitted, 0);
                    const affected = modelLoads.rows.filter(model => model.incompleteTextures);
                    assert.equal(affected[0].id, '{963f3392-c904-417e-a31e-ca9ad5407120}');
                    assert.equal(affected[0].shadersReady, true); assert.equal(affected[0].unavailableTextures.length, 1);
                    assert.equal(affected[0].unavailableTextures[0].sourceURL, 'https://cdn.highfidelity.com/DomainContent/production/HQ-v4-15-person-Baked_2019-05-09_04-45-00/dock-pieces/original/bridges_d.psd');
                    assert.equal(affected[0].unavailableTextures[0].property, 'albedoMap');
                    assert.ok(affected[0].unavailableTextures[0].error);
                    assert.equal(await page.locator('#asset-warning').isVisible(), true, 'Missing textures must remain visible after later loaded notices');
                    return { fullOriginalTextureParity: false, substitutedPixels: false, affected,
                        persistentWarning: await page.locator('#asset-warning').textContent(),
                        nativeBehavior: 'NetworkMaterial considers a failed image finished so the original geometry fades in with its declared material values.' };
                });
                await step(evidence, 'Actual HTTPS Hub model and textures submit main-view shader draws', async () => {
                    await requireActiveSession(page);
                    assert.ok(report.sceneAssetAudit.httpsModels.length > 0, 'The real native scene must contain the HTTPS Hub model variant');
                    assert.ok(report.sceneAssetAudit.atpModelCount > 0, 'The same scene must retain native ATP models');
                    const ids = report.sceneAssetAudit.httpsModels.map(entity => entity.id).slice(0, 8);
                    const result = await page.evaluate(ids => window.overteObserveEntityRendering(ids, 4000), ids);
                    for (const entity of result.entities) {
                        assert.equal(entity.partial, false); assert.equal(entity.loaded, true); assert.equal(entity.shadersReady, true);
                        assert.ok(entity.submittedDraws > 0 && entity.submittedTriangles > 0, 'The actual HTTPS model must submit shader-backed geometry in the unchanged scene');
                        assert.ok(entity.textures.some(texture => texture.source.startsWith('https://127.0.0.1:46119/') && texture.width > 0 && texture.height > 0), 'At least one actual assigned model texture must load through HTTPS');
                    }
                    await browser.screenshot(resolve(directory, 'https-rendered.png'));
                    return { ...result, sceneSHA256: report.sceneAssetAudit.servedSHA256, unchangedHistoricalTransforms: report.sceneAssetAudit.httpsModels };
                });
                await step(evidence, 'Actual contained native Zone skybox loads and renders', async () => {
                    await until(page, () => { const zone = window.overteDirectDiagnostics().zoneSkybox;
                        if (zone?.state === 'error') throw new Error(zone.error || 'The actual native Zone skybox failed');
                        return zone?.state === 'ready' && zone.renderedDraws > 0; }, timeout, true, true);
                    const zone = await page.evaluate(() => window.overteDirectDiagnostics().zoneSkybox);
                    assert.equal(zone.selectedZone, '{184edf9f-43c5-4db8-8b15-6b6ca88d044d}');
                    assert.ok(zone.source.endsWith('/SKY-brush-clouds.exr')); assert.ok(zone.dimensions.width === zone.dimensions.height * 2);
                    return { ...zone, sourceEffectAudit: report.sceneAssetAudit.sourceEffects, servedEffectAudit: report.sceneAssetAudit.servedEffects,
                        rawSourceBrowserCORS: await probeSourceEffectCORS(page, report.sceneAssetAudit) };
                });
                if (options.mode === 'direct') {
                await step(evidence, 'Actual Avatar checkbox selects first-person native peer and nearby interaction view', () => firstPerson(browser));
                await step(evidence, 'Actual native peer identity, pose and loaded rig submit main-view draws', () => restoreTabletAfter(browser, async () => {
                    const proof = await nativePeerProof(browser, directory, name);
                    evidence.nativePeerProof = proof; nativeBinding = proof.binding; return proof;
                }));
                await step(evidence, 'New actual native motion reaches the loaded remote body and fresh main-view draws',
                    () => restoreTabletAfter(browser, () => nativeMotionProof(browser, directory, nativeBinding, evidence)));
                await step(evidence, 'Trusted pointer-locked mouse changes the real yaw', () => restoreTabletAfter(browser, async () => {
                    await requireActiveSession(page);
                    await captureMouse(browser);
                    const before = await page.evaluate(() => ({ pose: window.overteDirectDiagnostics().pose, mouse: window.overteMouseEvidence() }));
                    await page.mouse.move(720, 400, { steps: 8 });
                    const after = await page.evaluate(() => ({ pose: window.overteDirectDiagnostics().pose, mouse: window.overteMouseEvidence() }));
                    assert.ok(after.mouse.lockedTrustedEvents > before.mouse.lockedTrustedEvents);
                    assert.ok(Math.abs(after.pose.orientation.y - before.pose.orientation.y) > 0.01, 'Actual trusted mouse movement must rotate the avatar yaw');
                    await page.mouse.move(640, 400, { steps: 8 }); await page.keyboard.press('Escape');
                    return { before, after, testTeleport: false };
                }));
                await step(evidence, 'Trusted source-entity pick opens the local selection inspector', () => restoreTabletAfter(browser, async () => {
                    await requireActiveSession(page);
                    const entity = report.sceneAssetAudit.httpsModels[0]; assert.ok(entity.position, 'Use an actual source entity position');
                    const input = await aimAtActualPoint(browser, entity.position);
                    assert.ok(input.actualCameraTargetDistance <= 5, 'Use a real nearby source object within the unchanged interaction reach');
                    await page.keyboard.press('e');
                    await until(page, () => Boolean(window.overteDirectDiagnostics().tablet.selectedEntityID), 8000);
                    await page.keyboard.press('Escape');
                    const current = await diagnostics(page), selected = current.app.tablet.selectedEntityID;
                    const nativeScene = JSON.parse(await readFile(resolve(labRoot, 'scene/mixed-scene-provenance.json'), 'utf8'));
                    assert.ok(selected, 'Real raycast input selects a native source entity');
                    const scene = JSON.parse(await readFile(resolve(labRoot, 'scene', nativeScene.runtimeScene), 'utf8'));
                    assert.ok(scene.Entities.some(item => item.id.replace(/[{}]/g, '').toLowerCase() === selected.replace(/[{}]/g, '').toLowerCase()), 'The actual selected entity belongs to the served historical scene');
                    const selectionText = await page.locator('.selection-info').textContent();
                    assert.ok(selectionText && !selectionText.startsWith('Aim at'));
                    assert.equal(current.app.tablet.visible, true); assert.equal(current.app.tablet.app, 'Domain');
                    return { selectedEntityID: selected, selectionText, aimedSourceEntity: entity.id, input,
                        sceneSHA256: nativeScene.sceneSHA256, canEdit: await page.locator('#tablet').getAttribute('data-can-edit'), destructiveEditingTested: false };
                }));
                await step(evidence, 'Trusted keyboard movement reaches a strictly newer actual native peer pose', () => restoreTabletAfter(browser, async () => {
                    await requireActiveSession(page);
                    await captureMouse(browser);
                    const before = (await diagnostics(page)).app.pose;
                    let nativeBefore;
                    if (options['native-peer'] === 'true') {
                        assert.ok(nativeBinding, 'Actual initial native peer proof is required');
                        const observation = await nativeObservation();
                        nativeBefore = await waitNative(state => state.sequence >= observation.sequence
                            && state.session === nativeBinding.nativeSession && state.peers.some(peer => peer.id === nativeBinding.browserPeerID
                            && horizontalDistance(peer.position, before.position) <= 0.25), 12000);
                        requireNativeBinding(nativeBinding, nativeBefore, await nativeProcessIdentity(), -1);
                    }
                    await page.keyboard.down('w');
                    try { await pause(900); } finally { await page.keyboard.up('w'); }
                    await until(page, () => { const velocity = window.overteDirectDiagnostics().pose.velocity;
                        return Math.hypot(velocity.x, velocity.z) < 0.05; }, 10000, true, true);
                    const after = (await diagnostics(page)).app.pose;
                    assert.ok(Object.values(after.position).every(Number.isFinite));
                    assert.ok(Math.hypot(after.position.x - before.position.x, after.position.z - before.position.z) > 0.02, 'Actual keyboard movement must change the pose');
                    let nativeReceipt;
                    if (nativeBefore) {
                        const newer = await waitNative(state => state.sequence > nativeBefore.sequence && state.session === nativeBinding.nativeSession
                            && state.peers.some(peer => peer.id === nativeBinding.browserPeerID
                                && horizontalDistance(peer.position, after.position) <= 0.25
                                && horizontalDistance(peer.position, nativeBefore.peers.find(old => old.id === nativeBinding.browserPeerID).position) > 0.02), 15000);
                        nativeReceipt = validateBrowserMovement(nativeBinding, nativeBefore, newer, await nativeProcessIdentity(), before.position, after.position);
                    }
                    await showTablet(browser, true);
                    return { before, after, nativeReceipt, testTeleport: false };
                }));
                await step(evidence, 'Actual Hub model triangles support a trusted jump and landing', () => restoreTabletAfter(browser, async () => {
                    await requireActiveSession(page);
                    await captureMouse(browser);
                    await until(page, () => { const collision = window.overteInspectCollision(); return collision.grounded && collision.supportingModels.length > 0; }, 20000);
                    const before = await page.evaluate(() => window.overteInspectCollision()); assert.equal(before.censored, false);
                    await page.keyboard.down('Space');
                    let airborne;
                    try { airborne = await untilValue(page, height => { const collision = window.overteInspectCollision();
                        return collision.pose.velocity.y > 0.1 && collision.pose.position.y > height + 0.02 ? collision : undefined; }, before.pose.position.y, 8000); }
                    finally { await page.keyboard.up('Space'); }
                    assert.ok(airborne.pose.position.y > before.pose.position.y + 0.02 && airborne.pose.velocity.y > 0);
                    const landed = await untilValue(page, () => { const collision = window.overteInspectCollision();
                        return collision.grounded && collision.supportingModels.length > 0 && Math.abs(collision.pose.velocity.y) < 0.05 ? collision : undefined; }, undefined, 20000);
                    assert.ok(Math.abs(landed.pose.position.y - before.pose.position.y) < 0.2, 'The actual loaded model floor arrests gravity after the jump');
                    await showTablet(browser, true);
                    return { before, airborne, landed, sceneSHA256: report.sceneAssetAudit.servedSHA256, fabricatedObstacle: false, testTeleport: false };
                }));
                if (options['synthetic-audio'] === 'true') {
                    await step(evidence, 'Native synthetic microphone reaches actual browser output', async () => {
                        await requireActiveSession(page);
                        const native = await nativeObservation(), before = (await diagnostics(page)).app;
                        assert.ok(native?.connected, 'The actual pinned native visitor must be connected');
                        assert.ok(Math.hypot(native.position.x - before.pose.position.x, native.position.z - before.pose.position.z) < 10,
                            'Spatial audio peers must meet using the real domain path');
                        assert.equal(before.audio.microphoneMuted, true, 'Native downlink test starts with browser capture off');
                        const capture = audioTool('capture', 'browser', 523.25, 8);
                        await pause(800); const input = await audioTool('tone', 'native', 523.25, 6);
                        const output = await capture, after = (await diagnostics(page)).app;
                        assert.ok(output.capturedFrames > 48000 && output.rms > 0.002);
                        assert.ok(output.frequencyAmplitudes['523.25'] > 0.002, 'Browser output must contain the native-only test frequency');
                        assert.ok(after.audio.receivedFrames > before.audio.receivedFrames);
                        assert.ok(after.audio.playedFrames > before.audio.playedFrames);
                        return { input, output, before: before.audio, after: after.audio, physicalMicrophoneTested: false };
                    });
                    await step(evidence, 'Explicit browser capture reaches actual native output', async () => {
                        await requireActiveSession(page);
                        await browser.click('button[aria-controls="tablet-audio"]');
                        await browser.click('#tablet-audio button');
                        await until(page, () => window.overteDirectDiagnostics().audio.microphoneMuted === false, 15000);
                        const before = (await diagnostics(page)).app.audio;
                        const capture = audioTool('capture', 'native', 659.25, 8);
                        await pause(800); const input = await audioTool('tone', 'browser', 659.25, 6);
                        const output = await capture, after = (await diagnostics(page)).app.audio;
                        await browser.click('#tablet-audio button');
                        await until(page, () => window.overteDirectDiagnostics().audio.microphoneMuted === true, 5000);
                        assert.ok(after.sentFrames > before.sentFrames, 'Native240-sample PCM frames must leave real browser capture');
                        assert.ok(output.capturedFrames > 48000 && output.rms > 0.002);
                        assert.ok(output.frequencyAmplitudes['659.25'] > 0.002, 'Native output must contain the browser-only test frequency');
                        return { input, output, before, after, permission: 'Automation grant in own test profile, followed by explicit Audio-app microphone action',
                            physicalMicrophoneTested: false };
                    });
                }
                }
                await step(evidence, 'Snapshot saves actual rendered PNG', async () => {
                    await requireActiveSession(page);
                    await browser.click('button[aria-controls="tablet-snapshot"]');
                    const path = resolve(directory, 'snapshot.png'); await browser.download(path);
                    const png = await readFile(path); assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
                    const width = png.readUInt32BE(16), height = png.readUInt32BE(20); assert.ok(width > 100 && height > 100);
                    return { width, height, bytes: png.length, sha256: createHash('sha256').update(png).digest('hex') };
                });
                await step(evidence, 'Leave closes real peer connections and disables capture', async () => {
                    await browser.click('button[aria-controls="tablet-domain"]'); await browser.click('#tablet-domain .button-row button:first-child');
                    await until(page, () => window.overteDirectDiagnostics().state === 'disconnected', 8000);
                    await untilTransportClosed(page);
                    const current = await diagnostics(page);
                    assert.equal(current.app.entities, 0);
                    assert.equal(current.app.audio.microphoneMuted, true, 'Leaving stops the actual browser capture track');
                    assert.ok(current.rtc.every(peer => peer.connectionState === 'closed'), 'All actual RTCPeerConnections must close on leave');
                    assert.ok(current.workerTransport.channels.every(channel => channel.readyState === 'closed'), 'Every actual transferred worker DataChannel must close on leave');
                    return current;
                });
                await step(evidence, 'Reconnect receives entities over fresh native channels', async () => {
                    await browser.click('#tablet-domain .button-row button:last-child');
                    await until(page, () => window.overteDirectDiagnostics().state === 'connected', timeout, true);
                    const current = await diagnostics(page); assert.equal(current.app.entities, expectedEntities);
                    assert.ok(current.rtc.some(peer => peer.connectionState === 'closed') && current.rtc.some(peer => peer.connectionState === 'connected'));
                    assert.ok(current.workerTransport.channels.some(channel => channel.readyState === 'closed')
                        && current.workerTransport.channels.some(channel => channel.readyState === 'open'), 'Reconnect must use fresh actual worker channels');
                    return current;
                });
                await browser.click('#tablet-domain .button-row button:first-child');
            }
        }
        await step(evidence, 'Unavailable loopback domain reports error and closes channels', async () => {
            await browser.click('button[aria-controls="tablet-domain"]');
            await browser.fill('#tablet-domain input[name="endpoint"]', 'ws://127.0.0.1:46118/');
            await browser.click('#tablet-domain button[type="submit"]');
            await until(page, () => window.overteDirectDiagnostics().state === 'error', 35000);
            await untilTransportClosed(page);
            const current = await diagnostics(page); assert.ok(current.notice?.length > 10);
            assert.ok(current.rtc.every(peer => peer.connectionState === 'closed'), 'Failed connection must dispose all created RTC peers');
            await browser.screenshot(resolve(directory, 'connection-error.png'));
            return current;
        });
        await step(evidence, 'No uncaught application exceptions or shader errors', async () => {
            assert.deepEqual(evidence.pageErrors, []); assert.deepEqual(evidence.shaderErrors, []);
        });
        if (cpuProfileTask) {
            await cpuProfileTask;
            await step(evidence, 'Bounded diagnostic CPU profile and transport timeline captured', async () => {
                assert.ok(evidence.cpuProfile, evidence.cpuProfileError || 'No actual CPU profile was captured');
                assert.equal(evidence.cpuProfile.truncatedNodes, false); assert.equal(evidence.cpuProfile.truncatedSamples, false);
                assert.ok(evidence.liveDiagnosticSamples.retained > 0); assert.deepEqual(evidence.liveDiagnosticErrors || [], []);
                return { cpuProfile: evidence.cpuProfile, liveDiagnosticSamples: evidence.liveDiagnosticSamples };
            });
        }
        evidence.final = await diagnostics(page);
    } catch (error) {
        evidence.steps.push({ name: 'Browser automation runtime', passed: false, error: bounded(error?.stack || error) });
    } finally {
        if (cpuProfileTask) await cpuProfileTask;
        if (stopLiveRecording) await stopLiveRecording();
        if (browser) {
            try { await browser.close(); } catch (error) { evidence.steps.push({ name: 'Browser closes', passed: false, error: bounded(error?.message || error) }); }
        }
        evidence.passed = evidence.steps.some(item => item.passed === true) && evidence.steps.every(item => item.passed !== false);
        await writeFile(resolve(directory, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
        await writeFile(resolve(resultRoot, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
    }
}
report.finished = new Date().toISOString();
report.passed = report.browsers.length === browsers.length && report.browsers.every(evidence => evidence.passed);
await writeFile(resolve(resultRoot, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
console.log(JSON.stringify({ passed: report.passed, result: resolve(resultRoot, 'results.json') }));
process.exitCode = report.passed ? 0 : 1;
