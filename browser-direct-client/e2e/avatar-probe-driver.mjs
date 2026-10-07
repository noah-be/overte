// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Stationary or guarded native-motion pipeline diagnosis; no model loading or microphone.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile, mkdir, open } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { createChrome, readAvatarWorkerEvidence } from './runtime.mjs';
import { readNativeHostProof, nativeMotionOperation } from './native-host-motion.mjs';
import { withRecordedCleanup } from './operation-cleanup.mjs';
import { avatarPipelineStages, validateAvatarStageMovement, validateAvatarNativeRestore } from './avatar-motion-evidence.mjs';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
assert.ok(['avatar-probe', 'avatar-motion-probe'].includes(options.mode)); assert.equal(options.browsers, 'chromium'); assert.equal(options['native-peer'], 'true');
const motionMode = options.mode === 'avatar-motion-probe';
const root = resolve(options.result), client = dirname(dirname(fileURLToPath(import.meta.url))), directory = resolve(root, 'chromium');
const lab = resolve(client, '../build/browser-direct/lab'), origin = 'http://127.0.0.1:46106', endpoint = 'ws://127.0.0.1:46104/';
const timeout = Math.min(55000, Number(options.timeout || 55) * 1000), pause = milliseconds => new Promise(done => setTimeout(done, milliseconds));
const canonical = value => typeof value === 'string' ? value.replace(/^[{](.*)[}]$/, '$1').toLowerCase() : '';
const sanitize = value => String(value).replace(/\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b/gi, '[identifier]')
    .replace(/\b(?:https?|wss?):\/\/[^\s"'<>]+/gi, '[endpoint]').slice(0, 1000);
const qualificationBytes = await readFile(resolve(lab, 'runtime/native-visitor-qualification.json'));
const qualification = JSON.parse(qualificationBytes);
const expectedNativeID = qualification.explicitNativePlacementObservation.session;
const report = { started: new Date().toISOString(), mode: options.mode,
    scope: motionMode ? 'Quiet actual guarded native one-metre -Z move and strict restore; finite newer wire position, actual worker post and real facade callback only. No rendered-body/full direct acceptance.'
        : '15 seconds stationary actual native AvatarMixer receive, worker outgoing avatars events and real WorkerDirectSession callbacks. Diagnostic collection only: no rendered-world, movement freshness, rig parity or audio acceptance.',
    observationSeconds: 15, nativeMoved: false, browserTestTeleport: false,
    nativeQualificationSHA256: createHash('sha256').update(qualificationBytes).digest('hex'),
    bundleManifestSha256: createHash('sha256').update(await readFile(resolve(root, 'bundle-manifest.json'))).digest('hex'),
    isolation: { display: process.env.DISPLAY, hardwareGPUVisible: existsSync('/dev/dri') || existsSync('/dev/nvidia0'), physicalMicrophoneTested: false },
    browsers: [], passed: false };
assert.equal(report.isolation.display, ':104'); assert.equal(report.isolation.hardwareGPUVisible, false);
assert.ok(process.env.PLAYWRIGHT_BROWSERS_PATH?.includes('/build/browser-direct/browsers'));
await mkdir(directory, { recursive: true });
const evidence = { browser: 'chromium', steps: [], pageErrors: [], nativeSamples: [], pipelineSamples: [], browserSceneAssetRequests: 0, passed: false };
report.browsers.push(evidence); let browser, nativeBrowserPeerID;
async function save() { await writeFile(resolve(directory, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n', { mode: 0o600 }); }
async function step(name, action) {
    const started = Date.now();
    try { evidence.steps.push({ name, passed: true, elapsedMs: 0, details: await action() }); }
    catch (error) { evidence.steps.push({ name, passed: false, error: sanitize(error.message) }); }
    evidence.steps.at(-1).elapsedMs = Date.now() - started; await save();
    console.log(JSON.stringify({ browser: 'chromium', step: name, passed: evidence.steps.at(-1).passed }));
    return evidence.steps.at(-1).passed;
}
async function nativeObservation() {
    const file = await open(resolve(lab, 'logs/native-visitor.log'), 'r'); let text;
    try { const { size } = await file.stat(), bytes = Buffer.alloc(Math.min(size, 262144));
        const result = await file.read(bytes, 0, bytes.length, Math.max(0, size - bytes.length)); text = bytes.subarray(0, result.bytesRead).toString('utf8');
    } finally { await file.close(); }
    for (const line of text.split('\n').reverse()) {
        const marker = line.indexOf('DIRECT_LAB_NATIVE ');
        if (marker >= 0) { try { return JSON.parse(line.slice(marker + 18)); } catch { /* Retry a partial newest line. */ } }
    }
    throw new Error('The actual native observer has no complete report.');
}
async function boundNative() {
    const proof = await readNativeHostProof(resolve(root, 'native-host-actions'));
    assert.deepEqual(proof.processIdentity, Object.fromEntries(['pid', 'startTicks', 'executable', 'cwd'].map(key => [key, qualification.nativeProcessIdentity[key]])));
    assert.equal(canonical(proof.nativeSession), canonical(expectedNativeID));
    const current = await nativeObservation();
    assert.equal(current.connected, true); assert.equal(canonical(current.session), canonical(expectedNativeID));
    assert.equal(current.nativeMotionControlVersion, 2); assert.ok(Date.now() / 1000 - current.observedAtUnixTime <= 6);
    return current;
}
const finite = (value, axes) => value && axes.every(key => typeof value[key] === 'number' && Number.isFinite(value[key]))
    ? Object.fromEntries(axes.map(key => [key, value[key]])) : null;
function nativePose(current) {
    const joints = {};
    for (const name of ['Hips', 'Head', 'LeftArm', 'RightArm']) {
        const raw = current.nativeSkeletonJointEvidence?.joints?.[name];
        joints[name] = { parentRelativeModelRotation: finite(raw?.parentRelativeModelRotation, ['x', 'y', 'z', 'w']),
            parentRelativeModelTranslation: finite(raw?.parentRelativeModelTranslation, ['x', 'y', 'z']),
            absoluteAvatarObjectRotation: finite(raw?.absoluteAvatarObjectRotation, ['x', 'y', 'z', 'w']) };
    }
    return { sequence: current.sequence, observedAtUnixMs: current.observedAtUnixTime * 1000,
        position: finite(current.position, ['x', 'y', 'z']), joints, actualPinnedProcessAndSessionMatched: true };
}
async function pipeline() {
    return { sampledAtUnixMs: Date.now(), page: await browser.page.evaluate(() => window.overteAvatarProbe.state()),
        worker: await readAvatarWorkerEvidence(browser.page) };
}
async function until(action, seconds = timeout) {
    const started = Date.now();
    while (Date.now() - started < seconds) {
        const answer = await action(); if (answer) return answer;
        const state = await browser.page.evaluate(() => window.overteAvatarProbe.state());
        if (state.state === 'error') throw new Error(state.lastError || 'Actual session failed.');
        await pause(200);
    }
    throw new Error('The bounded actual pipeline condition timed out.');
}
try {
    const current = await boundNative(); evidence.nativeSamples.push(nativePose(current));
    browser = await createChrome(directory, { avatarEvidence: { expectedNativeID } }); evidence.version = browser.version;
    browser.page.on('pageerror', error => { if (evidence.pageErrors.length < 8) evidence.pageErrors.push(sanitize(error.message)); });
    browser.page.on('request', request => {
        if (/\.(?:fst|fbx|gltf|glb|obj|png|jpe?g|ktx|exr|texmeta\.json)$/i.test(new URL(request.url()).pathname)) evidence.browserSceneAssetRequests++;
    });
    await browser.page.goto(origin + '/e2e/avatar-probe.html');
    await browser.page.waitForFunction(() => Boolean(window.overteAvatarProbe));
    await browser.prepareTransportEvidence(true);
    await browser.page.evaluate(id => window.overteAvatarProbe.configure(id), expectedNativeID);
    const joined = await step('actual production worker join and uniquely bound native peer', async () => {
        await browser.page.evaluate(value => window.overteAvatarProbe.join(value), endpoint);
        await until(async () => {
            const state = await browser.page.evaluate(() => window.overteAvatarProbe.state());
            if (state.state !== 'connected' || state.entityCount !== Number(options['expected-entities'] || 83) || !state.facadeEvents?.last) return false;
            const native = await boundNative(), peers = native.peers.filter(peer => {
                if (peer.id === 'null') {
                    // Actual AvatarManager MY_AVATAR_KEY -> String(null) alias.
                    // Refuse an unrelated/null-labelled pose instead of hiding it.
                    assert.equal(peer.displayName, 'direct-lab-native');
                    assert.ok(['x', 'y', 'z'].every(axis => Math.abs(peer.position[axis] - native.position[axis]) < .00001));
                    return false;
                }
                return canonical(peer.id) !== '00000000-0000-0000-0000-000000000000';
            });
            if (peers.length !== 1 || peers[0].displayName !== 'avatar-probe-chromium') return false;
            nativeBrowserPeerID = peers[0].id;
            return true;
        });
        const state = await browser.page.evaluate(() => window.overteAvatarProbe.state());
        assert.ok(state.spawn && Math.hypot(state.spawn.x - 155.084, state.spawn.z + 397.328) < .1);
        return { state: state.state, entityCount: state.entityCount, ordinaryDomainSpawn: state.spawn,
            facadeNativeIdentityMatched: true, actualNativeObserverHasOnlyThisBrowserPeer: true,
            liveHostProcessAndSourceBound: true, automaticSceneAssetRequests: state.automaticSceneAssetRequests };
    });
    if (joined && motionMode) await step('guarded actual native move → newer raw position → worker post → facade callback, then strict restore', async () => {
        const baseline = await until(async () => {
            const native = await boundNative(), current = await pipeline(); let stages;
            try { stages = avatarPipelineStages(current); } catch { return false; }
            return Object.values(stages).every(stage => Math.hypot(stage.position.x - native.position.x, stage.position.z - native.position.z) <= .25)
                ? { native, current, stages } : false;
        }, 10000);
        const before = baseline.native; assert.equal(before.nativeMotionTest, null, 'A fresh native one-shot trial is required');
        const proof = await readNativeHostProof(resolve(root, 'native-host-actions'));
        const binding = { processIdentity: proof.processIdentity, nativeSession: proof.nativeSession };
        const beforePipeline = baseline.current, beforeStages = baseline.stages;
        const details = { nativeBefore: nativePose(before), pipelineBefore: beforePipeline, stageBefore: beforeStages, samples: [], primaryFailure: null };
        evidence.motion = details;
        return withRecordedCleanup(async () => {
            details.phase = 'native-move';
            const applied = await nativeMotionOperation('motion-move', binding, resolve(root, 'native-host-actions'));
            report.nativeMoved = true;
            details.move = { nativeSequenceBefore: applied.nativeSequenceBefore, nativeSequenceAfter: applied.nativeSequenceAfter,
                positionBefore: applied.positionBefore, positionAfter: applied.positionAfter,
                appliedAtUnixMs: applied.nativeMotionTest.moveAppliedUnixTime * 1000 };
            const after = await until(async () => {
                const native = await boundNative();
                return native.sequence >= applied.nativeSequenceAfter && native.nativeMotionTest?.phase === 'moved'
                    && native.nativeMotionTest.requestId === applied.requestId ? native : false;
            }, 10000);
            assert.ok(after.sequence > before.sequence); assert.equal(canonical(after.session), canonical(before.session));
            details.nativeAfter = nativePose(after);
            details.phase = 'movement-pipeline';
            const started = Date.now(); let allFresh = false;
            while (Date.now() - started < 15000) {
                await boundNative(); const current = await pipeline(), stages = avatarPipelineStages(current), outcomes = {};
                for (const name of ['rawReceive', 'workerPost', 'facadeCallback']) {
                    try { outcomes[name] = { passed: true, ...validateAvatarStageMovement(beforeStages[name], stages[name], before.position, after.position, details.move.appliedAtUnixMs) }; }
                    catch (error) { outcomes[name] = { passed: false, error: sanitize(error.message), before: beforeStages[name], after: stages[name] }; }
                }
                details.samples.push({ elapsedMs: Date.now() - started, pipeline: current, outcomes }); await save();
                details.finalStages = outcomes;
                if (Object.values(outcomes).every(value => value.passed)) { allFresh = true; break; }
                await pause(1000);
            }
            assert.ok(allFresh, 'Actual native displacement did not reach every observed pipeline stage within15 seconds');
            assert.equal(evidence.browserSceneAssetRequests, 0);
            evidence.finding = { actualGuardedNativePoseReachedThreeStages: true, renderedBodyAcceptancePassed: false,
                fullDirectAcceptancePassed: false, interpretation: 'Wire → worker post → actual facade pose pipeline only; no renderer/model/body acceptance.' };
            return details;
        }, async () => {
            details.phase = 'native-restore';
            const current = await boundNative();
            if (current.nativeMotionTest?.phase === 'moved') {
                report.nativeMoved = true;
                const restored = await nativeMotionOperation('motion-restore', binding, resolve(root, 'native-host-actions'));
                details.restore = validateAvatarNativeRestore(restored, before, binding.nativeSession);
            } else details.restore = { notRequired: true, phase: current.nativeMotionTest?.phase || 'not-moved' };
        }, details, error => ({ phase: details.phase, message: sanitize(error.message) }));
    });
    if (joined && !motionMode) await step('15 second stationary raw receive → worker post → real facade callback window', async () => {
        const before = await pipeline(), windowNative = await boundNative(), nativeWindowIndex = evidence.nativeSamples.length;
        evidence.nativeSamples.push(nativePose(windowNative)); evidence.pipelineSamples.push(before);
        const started = Date.now(); let lastSequence = evidence.nativeSamples.at(-1).sequence;
        while (Date.now() - started < 15000) {
            const current = await boundNative();
            assert.ok(current.peers.some(peer => peer.id === nativeBrowserPeerID), 'The exact native-observed browser participant changed.');
            if (current.sequence > lastSequence) { evidence.nativeSamples.push(nativePose(current)); lastSequence = current.sequence; }
            const currentPipeline = await pipeline(); evidence.pipelineSamples.push(currentPipeline);
            assert.equal(currentPipeline.page.state, 'connected'); await save(); await pause(1000);
        }
        const last = await pipeline(); evidence.pipelineSamples.push(last);
        const receive = last.worker.workers.flatMap(worker => worker.channels || []).map(channel => channel.received);
        assert.ok(receive.some(observer => observer.firstRecordNativeMatches > 0 && observer.positions > 0), 'No matched complete native Bulk11:55 record was observed.');
        assert.ok(last.worker.workers.some(worker => worker.sourceEvents?.samples > 0), 'No real outgoing worker avatar event was observed.');
        assert.ok(last.page.facadeEvents.samples > 0, 'No real facade avatar callback was observed.');
        assert.equal(evidence.browserSceneAssetRequests, 0, 'This quiet diagnostic must not start world/model/image requests.');
        const nativePoseChanges = evidence.nativeSamples.slice(nativeWindowIndex).reduce((count, sample, index, samples) => count + (index > 0 && JSON.stringify(sample.joints) !== JSON.stringify(samples[index - 1].joints) ? 1 : 0), 0);
        const beforeReceive = before.worker.workers.flatMap(worker => worker.channels || []).map(channel => channel.received);
        const receiveDelta = key => receive.reduce((sum, value) => sum + value[key], 0) - beforeReceive.reduce((sum, value) => sum + value[key], 0);
        const workerDelta = key => last.worker.workers.reduce((sum, value) => sum + (value.sourceEvents?.[key] || 0), 0)
            - before.worker.workers.reduce((sum, value) => sum + (value.sourceEvents?.[key] || 0), 0);
        const changes = { nativeObserverSelectedJointChanges: nativePoseChanges,
            rawFirstFlagChanges: receiveDelta('flagChanges'), rawFirstBodyChanges: receiveDelta('bodyChecksumChanges'),
            rawFirstJointSectionChanges: receiveDelta('jointChecksumChanges'),
            outgoingWorkerJointChanges: workerDelta('jointPoseChanges'),
            facadeCallbackJointChanges: last.page.facadeEvents.jointPoseChanges - before.page.facadeEvents.jointPoseChanges };
        evidence.finding = { ...changes, freshnessAcceptancePassed: false,
            interpretation: 'Diagnostic stage counters/checksums only. Stationary position agreement does not prove fresh motion; a separate guarded actual movement test remains required.' };
        return { elapsedMs: Date.now() - started, sampleCount: evidence.pipelineSamples.length,
            nativeSampleCount: evidence.nativeSamples.length, ...changes };
    });
    await step('natural leave closes actual main and transferred worker channels', async () => {
        await browser.page.evaluate(() => window.overteAvatarProbe.leave());
        await until(async () => { const state = await browser.readTransportEvidence();
            return state.rtc.every(peer => peer.connectionState === 'closed') && state.workerTransport.channels.every(channel => channel.readyState === 'closed'); }, 8000);
        return { ...await browser.readTransportEvidence(), nativeMoved: report.nativeMoved,
            nativeRestored: evidence.motion?.restore?.passed === true, microphoneRequested: false };
    });
} catch (error) { evidence.fatal = sanitize(error.message); }
finally {
    if (browser) { evidence.final = await pipeline().catch(() => undefined); await browser.close(); }
    evidence.passed = !evidence.fatal && evidence.pageErrors.length === 0 && evidence.steps.length === 3 && evidence.steps.every(value => value.passed);
    report.passed = evidence.passed; report.finished = new Date().toISOString(); await save();
    await writeFile(resolve(root, 'results.json'), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
    console.log(JSON.stringify({ mode: report.mode, diagnosticCollected: report.passed, finding: evidence.finding }));
}
process.exitCode = report.passed ? 0 : 1;
