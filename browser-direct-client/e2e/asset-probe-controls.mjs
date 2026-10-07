// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual HTTP request counts and transferred worker channels are distinct from
// a constant entry flag and detached main-thread DataChannel handles.
import assert from 'node:assert/strict';

export function requireNoAutomaticAssetRequests(observed, explicit) {
    assert.ok(Number.isSafeInteger(observed) && observed >= 0);
    assert.ok(Number.isSafeInteger(explicit) && explicit >= 0);
    assert.equal(observed, explicit, 'Only the explicitly requested native asset fetches may occur.');
    return { observedNativeAssetRequests: observed, explicitAssetRequests: explicit, automaticSceneAssetRequests: 0 };
}

export function actualWorkerAssetChannel(snapshot) {
    assert.ok(snapshot?.workerTransport && snapshot.workerTransport.workersObserved === 1
        && snapshot.workerTransport.unavailableWorkers === 0, 'Require the actual unique observed session worker.');
    return snapshot.workerTransport.channels.find(channel => channel.nodeType === 'A' && channel.readyState === 'open');
}
