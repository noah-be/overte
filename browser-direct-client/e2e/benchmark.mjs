// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Paired real-scene software measurements. No synthetic renderer or quality reduction.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, mkdir, open } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { createChrome, observeLongTasks, observeImageLoads, readTransportEvidence } from './runtime.mjs';
import { readSceneAssetAudit } from './asset-evidence.mjs';
import { CASE_BUDGET_MS, commonSceneDeadline, remainingSceneBudget } from './time-budgets.mjs';
import { benchmarkCases, benchmarkCaseURL, requireBenchmarkRouteUsage } from './benchmark-controls.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
const resultRoot = resolve(options.result), client = dirname(dirname(fileURLToPath(import.meta.url)));
const lab = resolve(client, '../build/browser-direct/lab'), origin = 'http://127.0.0.1:46106';
const endpoint = 'ws://127.0.0.1:46104/', timeout = Number(options.timeout || 240) * 1000;
const mode = options.mode || 'benchmark', routeComparison = mode === 'benchmark-asset-route';
const order = benchmarkCases(mode);
if (routeComparison) {
    assert.equal(timeout, 240000, 'Routing cases use the original fixed 240-second shared scene deadline.');
    assert.equal(options['synthetic-audio'], 'false');
}
let sceneDeadline = Infinity;
const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
assert.equal(process.env.DISPLAY, ':104'); assert.equal(existsSync('/dev/dri') || existsSync('/dev/nvidia0'), false);
const scene = JSON.parse(await readFile(resolve(lab, 'scene/hub-subset.json'), 'utf8'));
const modelCount = scene.Entities.filter(entity => entity.type === 'Model' && entity.modelURL).length;
const provenanceBytes = await readFile(resolve(lab, 'scene/asset-provenance.json'));
const bundleBytes = await readFile(resolve(resultRoot, 'bundle-manifest.json'));
const sceneAssetAudit = await readSceneAssetAudit(lab);
const report = { started: new Date().toISOString(), mode, passed: false, browsers: [],
    softwareOnly: true, hardwareFluidityClaim: false, origin, endpoint,
    entityCount: Number(options['expected-entities'] || 83), modelCount,
    sourceAndServedAssetManifestSHA256: createHash('sha256').update(provenanceBytes).digest('hex'),
    sceneAssetAudit,
    bundleManifestSHA256: createHash('sha256').update(bundleBytes).digest('hex'),
    budgets: { sharedSceneWaitMs: timeout, freshCaseTotalMs: CASE_BUDGET_MS, overallBatchMs: 1200000,
        note: 'All actual admission/ready/full-scene phases share one absolute deadline; both arms have identical bounds.' },
    liveSourceMotion: scene.Entities.filter(entity => entity.angularVelocity
        && Object.values(entity.angularVelocity).some(value => typeof value === 'number' && value !== 0))
        .map(entity => ({ id: entity.id, type: entity.type, angularVelocity: entity.angularVelocity })),
    settings: { viewport: { width: 1280, height: 800 }, graphics: 'Unmodified application defaults',
        spawn: 'Actual domain path; no teleport, movement or third-person override', microphone: 'Off',
        changedSetting: routeComparison ? 'Only asset dispatch: default direct versus assetDispatch=page; decoded-image sharing remains default ON in every arm'
            : 'Only decoded-image sharing via benchmarkImageCache=off',
        controls: order },
    measures: { joinToReady: 'Trusted Join click through actual native admission/entities, first completed model, texture allocation and render-loop progress',
        joinToAllModels: 'Trusted Join click through all native model geometry, available textures and shader preparation; the original unavailable PSD remains explicit',
        frameCadence: 'Actual rendered-frame intervals after full scene loading; includes software-renderer stalls',
        longTasks: 'Browser main-thread Long Tasks API; includes JavaScript, decode and other task work; not GPU elapsed time',
        imageLoading: 'Both arms observe Image src-to-load/error and explicit Image.decode calls. Zero explicit baseline decode calls does not imply zero browser decode work.' },
    cases: [], pairs: [] };
if (routeComparison) {
    assert.equal(report.entityCount, 83); assert.equal(modelCount, 55);
    report.nativeRuntimeSHA256 = JSON.parse(await readFile(resolve(resultRoot, 'native-readiness.json'), 'utf8')).runtimeSHA256;
    report.nativePositionToleranceMetres = 0.05;
}

async function verifyFrozenScene() {
    const manifestSHA256 = createHash('sha256').update(await readFile(resolve(lab, 'scene/asset-provenance.json'))).digest('hex');
    assert.equal(manifestSHA256, report.sourceAndServedAssetManifestSHA256, 'Do not change native asset bytes during a paired run');
    const current = await readSceneAssetAudit(lab);
    assert.equal(current.sourceSHA256, sceneAssetAudit.sourceSHA256);
    assert.equal(current.servedSHA256, sceneAssetAudit.servedSHA256, 'Do not change native scene URLs or transforms during a paired run');
    return { manifestSHA256, sourceSceneSHA256: current.sourceSHA256, servedSceneSHA256: current.servedSHA256 };
}

async function nativeSceneState() {
    const path = resolve(lab, 'logs/native-visitor.log');
    if (!existsSync(path)) return { notObserved: 'No packaged native observer log exists' };
    const file = await open(path, 'r');
    let source, modified;
    try {
        const info = await file.stat(); modified = info.mtimeMs;
        const bytes = Buffer.alloc(Math.min(info.size, 262144));
        const { bytesRead } = await file.read(bytes, 0, bytes.length, Math.max(0, info.size - bytes.length));
        source = bytes.subarray(0, bytesRead).toString('utf8');
    } finally { await file.close(); }
    for (const line of source.split('\n').reverse()) {
        const marker = line.indexOf('DIRECT_LAB_NATIVE ');
        if (marker < 0) continue;
        try {
            const state = JSON.parse(line.slice(marker + 'DIRECT_LAB_NATIVE '.length));
            return { observedAt: new Date().toISOString(), logModifiedUnixMs: modified, sequence: state.sequence,
                connected: state.connected, session: state.session, position: state.position, orientation: state.orientation,
                skeletonModelURL: state.skeletonModelURL, avatarJointCount: state.avatarJointCount,
                avatarGraphics: state.avatarGraphics, nativeTestSetup: state.nativeTestSetup,
                note: 'Actual observer frame near screenshot time; native animation and browser simulation remain live, not frozen' };
        } catch { /* A partial last line is retried from the preceding full frame. */ }
    }
    return { notObserved: 'No complete actual packaged native observer frame was available' };
}

function requireSameNativePosition(state, reference) {
    assert.equal(state.connected, true, 'The same actual native participant must remain connected.');
    assert.ok(typeof state.session === 'string' && state.session.length > 0);
    assert.ok(Number.isSafeInteger(state.sequence) && state.sequence > 0);
    assert.ok(state.position && ['x', 'y', 'z'].every(axis => Number.isFinite(state.position[axis])));
    assert.equal(state.session, reference.session, 'Do not restart or replace the native participant between paired arms.');
    const distance = Math.hypot(...['x', 'y', 'z'].map(axis => state.position[axis] - reference.position[axis]));
    assert.ok(distance <= report.nativePositionToleranceMetres, 'Native position must remain within the recorded fixed-viewpoint tolerance.');
    return distance;
}

async function waitFor(page, predicate, maximum = timeout) {
    const started = Date.now(), budget = remainingSceneBudget(started, sceneDeadline, maximum);
    while (Date.now() - started < budget && Date.now() < sceneDeadline) {
        if (await page.evaluate(predicate)) return;
        const state = await page.evaluate(() => ({ state: window.overteDirectDiagnostics?.().state, message: document.querySelector('#notice')?.textContent }));
        if (state.state === 'error') throw new Error(state.message || 'Native connection error');
        await pause(250);
    }
    throw new Error(`Actual scene condition did not complete before its common deadline (${budget}ms remaining at this phase)`);
}

async function mark(page, name) {
    await page.evaluate(name => { performance.mark(name); performance.measure(name, 'overteBenchJoinStart', name); }, name);
}

async function snapshotEvidence(page, png) {
    return page.evaluate(async base64 => {
        const bytes = Uint8Array.from(atob(base64), character => character.charCodeAt(0));
        const image = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = new OffscreenCanvas(image.width, image.height), context = canvas.getContext('2d');
        context.drawImage(image, 0, 0); image.close();
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        const digest = await crypto.subtle.digest('SHA-256', pixels);
        const sampleGrid = [];
        for (let row = 0; row < 20; row++) for (let column = 0; column < 32; column++) {
            const index = ((Math.floor((row + 0.5) * canvas.height / 20) * canvas.width) + Math.floor((column + 0.5) * canvas.width / 32)) * 4;
            sampleGrid.push(...pixels.subarray(index, index + 3));
        }
        return { width: canvas.width, height: canvas.height,
            rgbaSHA256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join(''), sampleGrid };
    }, png.toString('base64'));
}

for (let index = 0; index < order.length; index++) {
    const control = order[index], { cache, route } = control;
    const directory = resolve(resultRoot, `case-${index + 1}-${control.label}`);
    await mkdir(directory, { recursive: true });
    const evidence = { index: index + 1, cache, route, passed: false, directory, errors: [], shaderErrors: [], failures: [] };
    report.cases.push(evidence); let browser, timedOutClosing;
    const caseDeadline = Date.now() + CASE_BUDGET_MS;
    sceneDeadline = caseDeadline;
    const caseTimer = setTimeout(() => {
        evidence.caseBudgetExpired = true;
        if (browser) timedOutClosing = browser.close().catch(error => { evidence.closeError = String(error.message).slice(0, 512); });
    }, CASE_BUDGET_MS);
    try {
        evidence.frozenSceneBefore = await verifyFrozenScene();
        evidence.nativeBefore = await nativeSceneState();
        if (routeComparison) evidence.nativeBeforePositionDistance = requireSameNativePosition(evidence.nativeBefore, report.cases[0].nativeBefore);
        browser = await createChrome(directory); evidence.version = browser.version;
        const page = browser.page; await browser.context.addInitScript(observeLongTasks);
        await browser.context.addInitScript(observeImageLoads);
        page.on('pageerror', error => { if (evidence.errors.length < 30) evidence.errors.push(error.message.slice(0, 2000)); });
        page.on('console', message => {
            const value = message.text();
            if (evidence.shaderErrors.length < 30 && /(?:Shader Error|WebGLProgram.*(?:Error|failed)|program.*not linked|linking failed|invalid program)/i.test(value)) {
                evidence.shaderErrors.push(value.slice(0, 3000));
            }
        });
        page.on('requestfailed', request => { if (evidence.failures.length < 50) evidence.failures.push({ url: request.url().replace(/\?.*/, ''), failure: request.failure() }); });
        await page.goto(benchmarkCaseURL(mode, origin, endpoint, control), { waitUntil: 'domcontentloaded' });
        await waitFor(page, () => typeof window.overteDirectDiagnostics === 'function', 30000);
        evidence.nativeSessionWorker = await browser.prepareTransportEvidence(true);
        evidence.renderer = await page.evaluate(() => {
            const gl = document.querySelector('#world canvas').getContext('webgl2'), extension = gl.getExtension('WEBGL_debug_renderer_info');
            return extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
        }); assert.match(evidence.renderer, /swiftshader|llvmpipe|software/i);
        await page.evaluate(() => performance.mark('overteBenchJoinStart'));
        sceneDeadline = commonSceneDeadline(Date.now(), timeout / 1000, caseDeadline);
        await browser.click('#tablet-domain button[type="submit"]');
        await waitFor(page, () => window.overteDirectDiagnostics().state === 'connected');
        await mark(page, 'overteBenchAdmitted');
        assert.equal(await page.evaluate(() => window.overteDirectDiagnostics().entities), report.entityCount);
        await browser.click('button[aria-label="Close tablet"]');
        await waitFor(page, () => { const value = window.overteDirectDiagnostics().performance; return value.loadedModels > 0 && value.textures > 0 && value.renderedFrames > 0; });
        await mark(page, 'overteBenchRenderReady');
        console.log(JSON.stringify({ benchmark: index + 1, cache, route, phase: 'first-render-ready' }));
        await page.evaluate(modelCount => { window.overteExpectedModelCount = modelCount; }, modelCount);
        await waitFor(page, () => {
            const p = window.overteDirectDiagnostics().performance;
            return p.loadedModels === window.overteExpectedModelCount && p.loadingModels === 0 && p.queuedModels === 0
                && p.compilingGraphics === 0 && p.imageLoading.active === 0 && p.imageLoading.pending === 0
                && p.fbxPreparation.active === 0 && p.fbxPreparation.queued === 0 && (p.sourceTextLoading?.active || 0) === 0
                && p.zoneSkybox.state === 'ready' && p.zoneSkybox.renderedDraws > 0;
        });
        await mark(page, 'overteBenchAllModels');
        evidence.afterLoading = await page.evaluate(() => window.overteDirectDiagnostics());
        assert.equal(evidence.afterLoading.performance.imageLoading.enabled, cache === 'on');
        const modelLoads = await page.evaluate(() => window.overteModelLoadEvidence());
        assert.equal(modelLoads.total, modelCount); assert.equal(modelLoads.loaded, modelCount); assert.equal(modelLoads.failed, 0);
        assert.equal(modelLoads.incompleteModels, 1); assert.equal(modelLoads.unavailableTextures, 1); assert.equal(modelLoads.omitted, 0);
        const affected = modelLoads.rows.filter(model => model.incompleteTextures);
        assert.equal(affected[0].id, '{963f3392-c904-417e-a31e-ca9ad5407120}');
        assert.equal(affected[0].shadersReady, true); assert.equal(affected[0].unavailableTextures.length, 1);
        assert.equal(affected[0].unavailableTextures[0].property, 'albedoMap');
        assert.equal(affected[0].unavailableTextures[0].sourceURL,
            'https://cdn.highfidelity.com/DomainContent/production/HQ-v4-15-person-Baked_2019-05-09_04-45-00/dock-pieces/original/bridges_d.psd');
        assert.equal(await page.locator('#asset-warning').isVisible(), true);
        evidence.incompleteOriginalTexture = { fullOriginalTextureParity: false, substitutedPixels: false,
            affected, persistentWarning: await page.locator('#asset-warning').textContent() };
        console.log(JSON.stringify({ benchmark: index + 1, cache, route, phase: 'all-models-complete', models: modelCount }));
        await pause(10000);
        evidence.settled = await page.evaluate(() => ({ app: window.overteDirectDiagnostics(), longTasks: window.overteLongTaskEvidence(),
            browserImageLoads: window.overteImageLoadingEvidence(),
            measures: performance.getEntriesByType('measure').map(entry => ({ name: entry.name, durationMs: entry.duration })),
            resources: performance.getEntriesByType('resource').filter(entry => entry.name.includes('/_overte-atp/') || entry.name.startsWith('https://127.0.0.1:46119/')).map(entry => ({
                transport: entry.name.includes('/_overte-atp/') ? 'native-atp' : 'https', path: new URL(entry.name).pathname.replace(/^\/_overte-atp\/[^/]+/, ''), durationMs: entry.duration,
                encodedBodySize: entry.encodedBodySize, decodedBodySize: entry.decodedBodySize, transferSize: entry.transferSize })),
            rtc: window.overteDirectTransportEvidence() }));
        if (routeComparison || evidence.settled.app.assetRouting) {
            evidence.assetRouting = requireBenchmarkRouteUsage(evidence.settled.app.assetRouting, route);
        }
        Object.assign(evidence.settled, await readTransportEvidence(page, evidence.settled.rtc));
        assert.equal(evidence.settled.workerTransport.unavailableWorkers, 0);
        assert.ok(evidence.settled.workerTransport.channels.some(channel => channel.nodeType === 'A'
            && channel.readyState === 'open' && channel.receivedBytes > 0), 'Actual asset packets must be received in the dedicated session worker');
        assert.ok(Math.abs(evidence.settled.app.pose.position.x - 155.084) < 3 && Math.abs(evidence.settled.app.pose.position.z + 397.328) < 3);
        await browser.click('#tablet-toggle'); await browser.click('button[aria-controls="tablet-snapshot"]');
        evidence.nativeBeforeSnapshot = await nativeSceneState();
        if (routeComparison) evidence.nativeScreenshotPositionDistance = requireSameNativePosition(evidence.nativeBeforeSnapshot, report.cases[0].nativeBefore);
        const path = resolve(directory, 'world.png'); await browser.download(path);
        const png = await readFile(path); evidence.pngSHA256 = createHash('sha256').update(png).digest('hex');
        evidence.pixels = await snapshotEvidence(page, png); assert.equal(evidence.pixels.width, 1280); assert.equal(evidence.pixels.height, 800);
        evidence.nativeAfterSnapshot = await nativeSceneState();
        if (routeComparison) {
            requireSameNativePosition(evidence.nativeAfterSnapshot, report.cases[0].nativeBefore);
            assert.ok(evidence.nativeAfterSnapshot.sequence > evidence.nativeBefore.sequence, 'The actual native observer must advance during this case.');
        }
        evidence.frozenSceneAfter = await verifyFrozenScene();
        await browser.click('button[aria-controls="tablet-domain"]'); await browser.click('#tablet-domain .button-row button:first-child');
        assert.deepEqual(evidence.errors, []); assert.deepEqual(evidence.shaderErrors, []);
        assert.notEqual(evidence.caseBudgetExpired, true, 'The complete fresh-profile case must fit its common budget'); evidence.passed = true;
    } catch (error) { evidence.error = String(error?.stack || error).slice(0, 4000); }
    finally {
        try {
            if (browser) {
                try { if (!evidence.settled) evidence.lastState = await browser.page.evaluate(() => window.overteDirectDiagnostics?.()); } catch { /* Closed/crashed browser is recorded above. */ }
                if (timedOutClosing) await timedOutClosing; else await browser.close();
            }
        } catch (error) {
            evidence.closeError = String(error.message || error).slice(0, 512); evidence.passed = false;
        } finally {
            clearTimeout(caseTimer);
            if (evidence.caseBudgetExpired || Date.now() >= caseDeadline) {
                evidence.caseBudgetExpired = true; evidence.passed = false;
                evidence.error ||= 'The complete fresh-profile case, including cleanup, exceeded its original budget.';
            }
        }
        await writeFile(resolve(directory, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`, { mode: 0o600 });
        await writeFile(resolve(resultRoot, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
        console.log(JSON.stringify({ benchmark: index + 1, cache, route, passed: evidence.passed, error: evidence.error }));
    }
}
for (const [first, second] of [[0, 1], [2, 3]]) {
    const cases = [report.cases[first], report.cases[second]];
    if (!cases.every(value => value.passed)) { report.pairs.push({ cases: [first + 1, second + 1], passed: false }); continue; }
    const difference = cases[0].pixels.sampleGrid.map((value, index) => Math.abs(value - cases[1].pixels.sampleGrid[index]));
    const positions = cases.map(value => value.settled.app.pose.position);
    const poseDistance = Math.hypot(...['x', 'y', 'z'].map(axis => positions[0][axis] - positions[1][axis]));
    const nativeStates = cases.map(value => value.nativeBeforeSnapshot);
    const nativePositionDistance = nativeStates.every(value => value?.connected && value.position)
        ? Math.hypot(...['x', 'y', 'z'].map(axis => nativeStates[0].position[axis] - nativeStates[1].position[axis])) : undefined;
    report.pairs.push({ cases: [first + 1, second + 1], passed: true,
        comparedSetting: report.settings.changedSetting,
        sameDecodedImageSharing: cases[0].cache === cases[1].cache,
        actualRouteUse: routeComparison ? cases.map(value => value.assetRouting) : undefined,
        sameSourceAndServedHashes: cases.every(value => value.frozenSceneBefore.manifestSHA256 === report.sourceAndServedAssetManifestSHA256
            && value.frozenSceneAfter.manifestSHA256 === report.sourceAndServedAssetManifestSHA256),
        exactWorldPixelsEqual: cases[0].pixels.rgbaSHA256 === cases[1].pixels.rgbaSHA256,
        sampledMeanAbsoluteRGBDifference: difference.reduce((sum, value) => sum + value, 0) / difference.length,
        poseDistance, nativeParticipants: cases.map(value => value.settled.app.participants),
        sameNativeSession: nativeStates.every(value => value?.connected) && nativeStates[0].session === nativeStates[1].session,
        nativePositionDistance, nativeStates,
        pairPassedMeans: 'Both cases met their individual functional/loading/budget criteria; not a pixel-equivalence claim',
        note: 'World pixels include actual native avatar pose/time, authored live angular velocities and loading-dependent simulation. Pixel differences are reported, not hidden or treated as visual equivalence.' });
}
report.finished = new Date().toISOString(); report.passed = report.cases.every(value => value.passed);
report.browsers = [{ browser: 'chromium', version: report.cases[0]?.version, passed: report.passed }];
await writeFile(resolve(resultRoot, 'results.json'), `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
process.exitCode = report.passed ? 0 : 1;
