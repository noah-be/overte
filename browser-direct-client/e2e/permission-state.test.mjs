// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { waitForPermissionState } from './permission-state.mjs';

test('a resolved false async snapshot keeps polling until the actual microphone answer arrives', async () => {
    let reads = 0;
    const answered = { phase: 'answered', enabled: true, liveAudioTracks: 1 };
    const result = await waitForPermissionState(async () => {
        await new Promise(resolve => setTimeout(resolve, 3));
        return ++reads < 3 ? { phase: 'requesting' } : answered;
    }, state => state.phase === 'answered', { pollingMs: 1, timeoutMs: 200 });
    assert.equal(reads, 3);
    assert.equal(result, answered, 'the successful native state is returned atomically');
});

test('an unanswered real-state reader fails at its common deadline rather than qualifying its Promise', async () => {
    let reads = 0;
    await assert.rejects(waitForPermissionState(async () => {
        reads++; return { phase: 'requesting' };
    }, state => state.phase === 'answered', { pollingMs: 1, timeoutMs: 1000, deadline: Date.now() + 15 }), /bounded deadline/);
    assert.ok(reads > 1);
});

test('async predicates and real reader errors cannot become successful permission evidence', async () => {
    await assert.rejects(waitForPermissionState(async () => ({ phase: 'requesting' }), async () => false), /return a boolean/);
    const failure = new Error('Actual page context closed');
    await assert.rejects(waitForPermissionState(async () => { throw failure; }, () => true), failure);
});
