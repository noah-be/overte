// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { requireNoAutomaticAssetRequests, actualWorkerAssetChannel } from './asset-probe-controls.mjs';
test('startup and each serial fetch use actual observed counts, not a constant zero flag', () => {
    requireNoAutomaticAssetRequests(0, 0); requireNoAutomaticAssetRequests(1, 1); requireNoAutomaticAssetRequests(2, 2);
    for (const [observed, explicit] of [[1, 0], [3, 2], [1, 2], [-1, 0], [NaN, 0]]) {
        assert.throws(() => requireNoAutomaticAssetRequests(observed, explicit));
    }
});
test('detached main channel handles cannot prove an actual worker-owned AssetServer channel', () => {
    const main = { rtc: [{ nodeType: 'A', channels: [{ readyState: 'open' }] }] };
    assert.throws(() => actualWorkerAssetChannel(main));
    const empty = { ...main, workerTransport: { workersObserved: 1, unavailableWorkers: 0, channels: [] } };
    assert.equal(actualWorkerAssetChannel(empty), undefined);
    const channel = { nodeType: 'A', readyState: 'open' };
    assert.equal(actualWorkerAssetChannel({ workerTransport: { workersObserved: 1, unavailableWorkers: 0,
        channels: [{ nodeType: 'E', readyState: 'open' }, channel] } }), channel);
    assert.throws(() => actualWorkerAssetChannel({ workerTransport: { workersObserved: 1, unavailableWorkers: 1, channels: [channel] } }));
});
