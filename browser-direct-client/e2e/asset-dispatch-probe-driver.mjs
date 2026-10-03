// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// One actual frozen full-scene observation; no product transport optimization.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomBytes } from 'node:crypto';
import { createChrome, observeLongTasks } from './runtime.mjs';
import { readSceneAssetAudit } from './asset-evidence.mjs';
import { addPageAssetDispatchObserver, prepareAssetDispatchContexts, requireAssetProbeSessionState } from './asset-dispatch-context.mjs';
import { correlateAssetDispatchEvidence } from './asset-dispatch-evidence.mjs';
import { CASE_BUDGET_MS, commonSceneDeadline } from './time-budgets.mjs';
import { requireBenchmarkRouteUsage } from './benchmark-controls.mjs';
import { requireValidatedBundleManifest } from './validated-bundle.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.equal(options.mode, 'asset-dispatch-probe'); assert.equal(options.browsers, 'chromium');
assert.equal(Number(options.timeout), 240, 'This standalone observation uses one fixed 240-second scene bound.');
assert.equal(options['synthetic-audio'], 'false'); assert.equal(process.env.DISPLAY, ':104');
assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0') || existsSync('/dev/snd'), false);
const root = resolve(options.result), client = dirname(dirname(fileURLToPath(import.meta.url)));
const lab = resolve(client, '../build/browser-direct/lab'), origin = 'http://127.0.0.1:46106';
const endpoint = 'ws://127.0.0.1:46104/', salt = randomBytes(24).toString('base64url');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const safeReason = value => String(value?.message || value).replace(/(?:https?|wss?|blob|atp|data):[^\s"']+/g, '[url]')
    .replace(/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/gi, '[identifier]').slice(0, 1000);
const evidence = { browser: 'chromium', passed: false, errors: [], shaderErrors: [], networkFailedRequests: 0,
    softwareOnly: true, physicalMicrophoneTested: false, permissionAPIOverrides: false, nativeMotionRequested: false };
const report = { mode: options.mode, started: new Date().toISOString(), passed: false, browsers: [evidence],
    scope: 'One fresh actual Chrome full-Hub PAGE-baseline load with passive ATP dispatch clocks. Requests route SW→page→session worker; replies already go directly from session worker to SW. The direct route is outside these page-edge observers. No decoder CPU, GPU bottleneck or critical-path improvement claim.',
    budgets: { commonJoinToSceneMs: 240000, caseMs: CASE_BUDGET_MS, launcherMs: 315000 },
    settings: { viewport: { width: 1280, height: 800 }, imageSharing: 'Unmodified default ON',
        assetDispatch: 'Explicit page baseline only; actual production counters must prove its use',
        graphics: 'Unmodified production defaults', microphone: 'Off; no permission grant or voice measurement',
        navigation: 'Actual domain path, no browser/native repositioning' } };
const save = () => writeFile(resolve(root, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
const caseDeadline = Date.now() + CASE_BUDGET_MS;
let sceneDeadline = caseDeadline, admitted = false, browser, observers, rawSnapshots, timedOutClosing;
const caseTimer = setTimeout(() => {
    evidence.caseExpired = true;
    if (browser) timedOutClosing = browser.close().catch(error => { evidence.closeError = safeReason(error); });
}, CASE_BUDGET_MS);

async function frozenScene() {
    const manifest = await readFile(resolve(lab, 'scene/asset-provenance.json'));
    const audit = await readSceneAssetAudit(lab);
    return { sourceAndServedAssetManifestSHA256: hash(manifest), sourceSceneSHA256: audit.sourceSHA256,
        servedSceneSHA256: audit.servedSHA256, entityCount: audit.entityCount, atpModels: audit.atpModelCount,
        httpsModels: audit.httpsModels.length };
}
async function waitForScene(predicate) {
    while (Date.now() < sceneDeadline && Date.now() < caseDeadline) {
        if (await browser.page.evaluate(predicate)) return;
        const state = await browser.page.evaluate(() => window.overteDirectDiagnostics?.().state);
        evidence.lastObservedSessionState = state;
        requireAssetProbeSessionState(state, admitted);
        await pause(250);
    }
    throw Error('The actual scene did not complete before its common fixed deadline.');
}
async function collectDispatch() {
    if (!observers) return;
    rawSnapshots = await observers.read();
    // This bounded hash/timestamp record is private evidence. Only the following
    // aggregate phases/kinds are included in results or published descriptions.
    await writeFile(resolve(root, 'asset-dispatch-private.json'), `${JSON.stringify(rawSnapshots, null, 2)}\n`, { mode: 0o600 });
    evidence.assetDispatch = correlateAssetDispatchEvidence(rawSnapshots);
}
async function naturalLeave() {
    if (!browser) return;
    const state = await browser.page.evaluate(() => window.overteDirectDiagnostics?.());
    if (!state || state.state === 'disconnected') return;
    if (!state.tablet.visible) await browser.click('#tablet-toggle');
    await browser.click('button[aria-controls="tablet-domain"]');
    await browser.click('#tablet-domain .button-row button:first-child');
    const deadline = Math.min(Date.now() + 10000, caseDeadline);
    while (Date.now() < deadline) {
        const current = await browser.page.evaluate(() => ({ state: window.overteDirectDiagnostics().state,
            microphoneMuted: window.overteDirectDiagnostics().audio.microphoneMuted,
            peersClosed: window.overteDirectTransportEvidence().every(peer => peer.connectionState === 'closed') }));
        if (current.state === 'disconnected' && current.peersClosed && current.microphoneMuted) {
            evidence.naturalLeave = current; return;
        }
        await pause(100);
    }
    throw Error('Actual native leave did not close the owned peers before bounded cleanup.');
}

try {
    report.frozenSceneBefore = await frozenScene();
    assert.equal(report.frozenSceneBefore.entityCount, 83);
    assert.equal(report.frozenSceneBefore.atpModels + report.frozenSceneBefore.httpsModels, 55);
    const bundleManifest = await readFile(resolve(root, 'bundle-manifest.json'));
    const qualified = requireValidatedBundleManifest(bundleManifest, options['validated-bundle-sha256']);
    report.bundleManifestSHA256 = qualified.manifestSHA256;
    report.validatedBundleManifestSHA256 = options['validated-bundle-sha256'];
    report.productionFreeze = qualified.productionFiles; report.sourceMapProvenance = qualified.sourceMaps;
    const nativeReadiness = JSON.parse(await readFile(resolve(root, 'native-readiness.json'), 'utf8'));
    report.nativeRuntimeSHA256 = nativeReadiness.runtimeSHA256;
    browser = await createChrome(root); evidence.version = browser.version;
    await addPageAssetDispatchObserver(browser.context, salt);
    await browser.context.addInitScript(observeLongTasks);
    browser.page.on('pageerror', error => { if (evidence.errors.length < 30) evidence.errors.push(safeReason(error)); });
    browser.page.on('requestfailed', () => { evidence.networkFailedRequests++; });
    browser.page.on('console', message => {
        const value = message.text();
        if (evidence.shaderErrors.length < 30 && /(?:Shader Error|WebGLProgram.*(?:Error|failed)|program.*not linked|linking failed|invalid program)/i.test(value)) evidence.shaderErrors.push(safeReason(value));
    });
    await browser.page.goto(`${origin}/?server=${encodeURIComponent(endpoint)}&assetDispatch=page`, { waitUntil: 'domcontentloaded' });
    await browser.page.waitForFunction(() => typeof window.overteDirectDiagnostics === 'function');
    await browser.prepareTransportEvidence(true);
    observers = await prepareAssetDispatchContexts(browser, salt, origin);
    assert.equal(await browser.page.evaluate(() => window.overteDirectDiagnostics().assetRouting?.mode), 'page',
        'The qualified production bundle must implement the explicit page-baseline route.');
    evidence.observersBeforeJoin = observers.before.map(({ role, available, limits, counters, clock }) => ({ role, available, limits, counters, clock }));
    evidence.actualAssetWorker = { sameRegisteredAndControllerScript: true, activated: true, registeredRootScope: true };
    evidence.renderer = await browser.page.evaluate(() => {
        const gl = document.querySelector('#world canvas').getContext('webgl2'), extension = gl.getExtension('WEBGL_debug_renderer_info');
        return extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    }); assert.match(evidence.renderer, /swiftshader|llvmpipe|software/i);
    await browser.page.evaluate(() => performance.mark('assetDispatchJoin'));
    sceneDeadline = commonSceneDeadline(Date.now(), 240, caseDeadline);
    await browser.click('#tablet-domain button[type="submit"]');
    await waitForScene(() => window.overteDirectDiagnostics().state === 'connected');
    admitted = true; evidence.actualNativeAdmission = true;
    assert.equal(await browser.page.evaluate(() => window.overteDirectDiagnostics().entities), 83);
    await browser.click('button[aria-label="Close tablet"]');
    console.log(JSON.stringify({ phase: 'actual-native-admitted', observerRolesReady: 3 }));
    await waitForScene(() => {
        const p = window.overteDirectDiagnostics().performance;
        return p.loadedModels === 55 && p.loadingModels === 0 && p.queuedModels === 0 && p.compilingGraphics === 0
            && p.imageLoading.active === 0 && p.imageLoading.pending === 0 && p.fbxPreparation.active === 0
            && p.fbxPreparation.queued === 0 && (p.sourceTextLoading?.active || 0) === 0
            && p.zoneSkybox.state === 'ready' && p.zoneSkybox.renderedDraws > 0;
    });
    evidence.scene = await browser.page.evaluate(() => {
        performance.mark('assetDispatchAllModels'); performance.measure('assetDispatchAllModels', 'assetDispatchJoin', 'assetDispatchAllModels');
        const p = window.overteDirectDiagnostics().performance, m = window.overteModelLoadEvidence();
        const known = m.rows.filter(model => model.incompleteTextures);
        return { loadedModels: p.loadedModels, modelEvidence: { total: m.total, loaded: m.loaded, failed: m.failed,
            incompleteModels: m.incompleteModels, unavailableTextures: m.unavailableTextures, omitted: m.omitted },
            exactlyKnownOriginalPSD: known.length === 1 && known[0].id === '{963f3392-c904-417e-a31e-ca9ad5407120}'
                && known[0].shadersReady && known[0].unavailableTextures.length === 1
                && known[0].unavailableTextures[0].property === 'albedoMap'
                && known[0].unavailableTextures[0].sourceURL === 'https://cdn.highfidelity.com/DomainContent/production/HQ-v4-15-person-Baked_2019-05-09_04-45-00/dock-pieces/original/bridges_d.psd',
            fullOriginalTextureParity: false, substitutedPixels: false,
            imageLoading: p.imageLoading, loadPhases: p.loadPhases,
            skybox: { state: p.zoneSkybox.state, dimensions: p.zoneSkybox.dimensions, renderedDraws: p.zoneSkybox.renderedDraws },
            drawingBuffer: [p.drawingBufferWidth, p.drawingBufferHeight], textures: p.textures,
            triangles: p.triangles, fps: p.fps, p95FrameMs: p.p95FrameMs,
            cpuFrameTiming: p.cpuFrameTiming, renderCpuTiming: p.renderCpuTiming, gpuTiming: p.gpuTiming,
            longTasks: window.overteLongTaskEvidence(), allModelsMs: performance.getEntriesByName('assetDispatchAllModels', 'measure').at(-1).duration };
    });
    assert.deepEqual(evidence.scene.modelEvidence, { total: 55, loaded: 55, failed: 0, incompleteModels: 1, unavailableTextures: 1, omitted: 0 });
    assert.equal(evidence.scene.exactlyKnownOriginalPSD, true);
    assert.equal(await browser.page.locator('#asset-warning').isVisible(), true);
    assert.equal(evidence.scene.imageLoading.enabled, true); assert.deepEqual(evidence.scene.drawingBuffer, [1280, 800]);
    evidence.assetRouting = requireBenchmarkRouteUsage(await browser.page.evaluate(() => window.overteDirectDiagnostics().assetRouting), 'page');
    await collectDispatch(); assert.ok(['complete', 'partial'].includes(evidence.assetDispatch.status), 'Real three-realm causal dispatch intervals must be available.');
    assert.ok(evidence.assetDispatch.counters.completeRequests > 0);
    assert.equal(evidence.assetDispatch.counters.observerLosses, 0, 'No bounded observer loss may be hidden as successful dispatch coverage.');
    assert.ok(Object.values(evidence.assetDispatch.phases).every(phase => phase.available), 'Every causal phase must contain actual correlated intervals.');
    assert.deepEqual(evidence.errors, []); assert.deepEqual(evidence.shaderErrors, []);
    report.frozenSceneAfter = await frozenScene(); assert.deepEqual(report.frozenSceneAfter, report.frozenSceneBefore);
    assert.notEqual(evidence.caseExpired, true);
    evidence.passed = true;
} catch (error) { evidence.error = safeReason(error); }
finally {
    try { if (!rawSnapshots) await collectDispatch(); } catch (error) { evidence.observerCollectionError = safeReason(error); evidence.passed = false; }
    try { await naturalLeave(); } catch (error) { evidence.cleanupError = safeReason(error); evidence.passed = false; }
    if (observers) evidence.observerCleanup = await observers.dispose();
    try { if (timedOutClosing) await timedOutClosing; else if (browser) await browser.close(); }
    catch (error) { evidence.closeError = safeReason(error); evidence.passed = false; }
    clearTimeout(caseTimer);
    report.passed = evidence.passed; report.finished = new Date().toISOString(); await save();
}
process.exitCode = report.passed ? 0 : 1;
