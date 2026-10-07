// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-only injection into the exact production asset/session workers.
import assert from 'node:assert/strict';
import { installAssetDispatchEvidence } from './asset-dispatch-evidence.mjs';

export function requireAssetProbeSessionState(state, admitted) {
    // The trusted Join handler awaits actual audio playback initialization
    // before session.connect, so initial disconnected is not a lost session.
    // Error is fatal throughout, and loss after admission still fails promptly.
    if (state === 'error' || (admitted && state === 'disconnected')) {
        throw Error('The actual native session stopped before the required scene condition completed.');
    }
}

export function requireAssetWorkerBinding(binding, origin) {
    const script = `${origin}/asset-worker.js`, scope = `${origin}/`;
    assert.equal(binding.registrationScope, scope, 'The registered asset scope must be the actual application root.');
    assert.equal(binding.activeScriptURL, script, 'Use the unchanged production asset worker.');
    assert.equal(binding.controllerScriptURL, script, 'The actual current page must be controlled by that asset worker.');
    assert.equal(binding.activeState, 'activated');
    assert.equal(binding.controllerState, 'activated');
}

export function requireAssetObserverReadiness(snapshots) {
    assert.equal(snapshots.length, 3);
    assert.deepEqual(snapshots.map(value => value.role).sort(), ['page', 'service-worker', 'session-worker']);
    const binding = snapshots[0].runBinding;
    assert.match(binding || '', /^[a-f0-9]{64}$/);
    for (const value of snapshots) {
        assert.equal(value.available, true, `The ${value.role} observer must initialize before Join.`);
        assert.equal(value.clock.status, 'valid', `The ${value.role} clock must be qualified.`);
        assert.equal(value.runBinding, binding, 'All three actual realms must bind this one private observation run.');
        assert.equal(value.counters.observedEvents, 0, 'No native asset request may precede observer readiness.');
        for (const name of ['droppedEvents', 'hashErrors', 'hashCapacityDrops', 'observerErrors',
            'unmatchedReplyPorts', 'portCapacityDrops', 'workerCapacityDrops']) {
            assert.equal(value.counters[name], 0, 'All observers must initialize without hash/hook/capacity losses.');
        }
    }
}

export async function addPageAssetDispatchObserver(context, salt) {
    await context.addInitScript({ content: `globalThis.overteTestOnlyAssetDispatch=(${installAssetDispatchEvidence.toString()})('page',${JSON.stringify(salt)});` });
}

/** Same native worker and one absolute preparation deadline. Self-contained
 * so the real page and the delayed-activation regression execute this code. */
export function waitForActivatedAssetWorker(worker, deadline) {
    return new Promise((resolve, reject) => {
        if (!worker || typeof worker.addEventListener !== 'function') { reject(Error('The actual asset worker is unavailable.')); return; }
        let timer;
        const finish = (error) => {
            clearTimeout(timer); worker.removeEventListener('statechange', changed);
            if (error) reject(error); else resolve();
        };
        const changed = () => {
            if (Date.now() >= deadline) finish(Error('The original asset-worker preparation deadline expired.'));
            else if (worker.state === 'activated') finish();
            else if (worker.state === 'redundant') finish(Error('The same actual asset worker became redundant before activation.'));
        };
        worker.addEventListener('statechange', changed);
        timer = setTimeout(() => finish(Error('The original asset-worker preparation deadline expired.')), Math.max(0, deadline - Date.now()));
        changed();
    });
}

export async function prepareAssetDispatchContexts(browser, salt, origin) {
    const deadline = Date.now() + 10000;
    const binding = await browser.page.evaluate(async ({ deadline, activationSource }) => {
        if (!navigator.serviceWorker) throw Error('The actual application asset ServiceWorker is unavailable.');
        const waitForActivation = globalThis.eval(`(${activationSource})`);
        let timer, changed;
        try {
            return await Promise.race([(async () => {
                const registration = await navigator.serviceWorker.register('/asset-worker.js', { scope: '/' });
                await navigator.serviceWorker.ready;
                if (!navigator.serviceWorker.controller) await new Promise(resolve => {
                    changed = () => resolve();
                    navigator.serviceWorker.addEventListener('controllerchange', changed);
                    if (navigator.serviceWorker.controller) resolve();
                });
                await Promise.all([waitForActivation(registration.active, deadline), waitForActivation(navigator.serviceWorker.controller, deadline)]);
                return { registrationScope: registration.scope, activeScriptURL: registration.active?.scriptURL,
                    activeState: registration.active?.state, controllerScriptURL: navigator.serviceWorker.controller?.scriptURL,
                    controllerState: navigator.serviceWorker.controller?.state };
            })(), new Promise((_, reject) => { timer = setTimeout(() => reject(Error('The actual asset worker did not activate before the bounded preparation deadline.')), Math.max(0, deadline - Date.now())); })]);
        } finally {
            clearTimeout(timer);
            if (changed) navigator.serviceWorker.removeEventListener('controllerchange', changed);
        }
    }, { deadline, activationSource: waitForActivatedAssetWorker.toString() });
    requireAssetWorkerBinding(binding, origin);
    let serviceWorker;
    while (Date.now() < deadline) {
        const actual = browser.context.serviceWorkers().filter(worker => worker.url() === binding.activeScriptURL);
        assert.ok(actual.length <= 1, 'Only one actual activated asset worker may match the controller.');
        if (actual.length === 1) { serviceWorker = actual[0]; break; }
        await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.ok(serviceWorker, 'The exact activated asset ServiceWorker must be observable.');
    const sessions = browser.page.workers().filter(worker => /(?:^|\/)session-worker(?:[.-]|$)/.test(new URL(worker.url()).pathname));
    assert.equal(sessions.length, 1, 'Use the actual unique production session worker before Join.');
    const sessionWorker = sessions[0];
    for (const [role, worker] of [['service-worker', serviceWorker], ['session-worker', sessionWorker]]) {
        await worker.evaluate(`globalThis.overteTestOnlyAssetDispatch=(${installAssetDispatchEvidence.toString()})(${JSON.stringify(role)},${JSON.stringify(salt)});`);
    }
    const read = () => Promise.all([serviceWorker, browser.page, sessionWorker].map(realm =>
        realm.evaluate(() => globalThis.overteTestOnlyAssetDispatch.snapshot())));
    const before = await read(); requireAssetObserverReadiness(before);
    assert.ok(Date.now() < deadline, 'All three actual observers must initialize within the one original preparation deadline.');
    return { read, before, binding, dispose: async () => {
        const outcomes = await Promise.allSettled([serviceWorker, browser.page, sessionWorker].map(realm =>
            realm.evaluate(() => globalThis.overteTestOnlyAssetDispatch?.dispose())));
        return { restoredObservers: outcomes.filter(value => value.status === 'fulfilled').length,
            unavailableClosedObservers: outcomes.filter(value => value.status === 'rejected').length };
    } };
}
