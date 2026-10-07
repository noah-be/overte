// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { requireAssetWorkerBinding, requireAssetObserverReadiness, waitForActivatedAssetWorker, requireAssetProbeSessionState } from './asset-dispatch-context.mjs';
const origin = 'http://127.0.0.1:46106';
const binding = { registrationScope: `${origin}/`, activeScriptURL: `${origin}/asset-worker.js`,
    controllerScriptURL: `${origin}/asset-worker.js`, activeState: 'activated', controllerState: 'activated' };
test('initial disconnected during actual asynchronous Join setup is distinct from post-admission loss', async () => {
    let state = 'disconnected', resolvePlayback;
    const playback = new Promise(resolve => { resolvePlayback = resolve; });
    const join = (async () => { await playback; state = 'connecting'; })();
    // The real main.connect handler awaits startAudio before session.connect.
    await Promise.resolve(); requireAssetProbeSessionState(state, false);
    resolvePlayback(); await join; requireAssetProbeSessionState(state, false);
    assert.throws(() => requireAssetProbeSessionState('error', false), /native session stopped/);
    assert.throws(() => requireAssetProbeSessionState('disconnected', true), /native session stopped/);
    assert.throws(() => requireAssetProbeSessionState('error', true), /native session stopped/);
    requireAssetProbeSessionState('connected', true);
});
test('the actual activated production asset worker must also control this exact application page', () => {
    requireAssetWorkerBinding(binding, origin);
    for (const wrong of [{ registrationScope: `${origin}/other/` }, { activeScriptURL: `${origin}/other-worker.js` },
        { controllerScriptURL: 'https://foreign.invalid/asset-worker.js' }, { activeState: 'installing' }, { controllerState: 'redundant' }]) {
        assert.throws(() => requireAssetWorkerBinding({ ...binding, ...wrong }, origin));
    }
});

class ActualStateEvents extends EventTarget {
    state = 'activating'; added = 0; removed = 0;
    addEventListener(...values) { this.added++; super.addEventListener(...values); }
    removeEventListener(...values) { this.removed++; super.removeEventListener(...values); }
    activate(state = 'activated') { this.state = state; this.dispatchEvent(new Event('statechange')); }
}
test('native ready/claim while activating cannot qualify before the same worker statechange', async () => {
    const worker = new ActualStateEvents(); let qualified = false;
    const result = waitForActivatedAssetWorker(worker, Date.now() + 200).then(() => { qualified = true; });
    await new Promise(resolve => setTimeout(resolve, 3)); assert.equal(qualified, false);
    worker.activate(); await result; assert.equal(qualified, true);
    assert.equal(worker.added, 1); assert.equal(worker.removed, 1);
});
test('pending/redundant/late activation cannot renew or pass the original preparation deadline', async () => {
    const pending = new ActualStateEvents();
    await assert.rejects(waitForActivatedAssetWorker(pending, Date.now() + 10), /original.*deadline/);
    assert.equal(pending.removed, 1); pending.activate();
    const redundant = new ActualStateEvents();
    const result = waitForActivatedAssetWorker(redundant, Date.now() + 200); redundant.activate('redundant');
    await assert.rejects(result, /became redundant/);
    const expired = new ActualStateEvents(); expired.activate();
    await assert.rejects(waitForActivatedAssetWorker(expired, Date.now() - 1), /original.*deadline/);
});
test('all three empty pre-Join observers require matching run bindings and real qualified clocks', () => {
    const snapshots = ['service-worker', 'page', 'session-worker'].map(role => ({ role, available: true,
        runBinding: 'a'.repeat(64), clock: { status: 'valid' }, counters: { observedEvents: 0, droppedEvents: 0,
            hashErrors: 0, hashCapacityDrops: 0, observerErrors: 0, unmatchedReplyPorts: 0, portCapacityDrops: 0, workerCapacityDrops: 0 } }));
    requireAssetObserverReadiness(snapshots);
    for (const wrong of [{ available: false }, { clock: { status: 'unavailable' } }, { runBinding: 'b'.repeat(64) },
        { counters: { ...snapshots[2].counters, observedEvents: 1 } },
        { counters: { ...snapshots[2].counters, hashErrors: 1 } }, { role: 'page' }]) {
        assert.throws(() => requireAssetObserverReadiness([snapshots[0], snapshots[1], { ...snapshots[2], ...wrong }]));
    }
    assert.throws(() => requireAssetObserverReadiness(snapshots.slice(0, 2)));
});
