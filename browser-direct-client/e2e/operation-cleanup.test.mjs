// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { withRecordedCleanup } from './operation-cleanup.mjs';

test('failed native body observation remains the primary error after failed restore', async () => {
    const primary = new Error('Actual received body did not move'), cleanup = new Error('Native restore was rejected');
    const evidence = {}, calls = [];
    await assert.rejects(withRecordedCleanup(async () => { calls.push('body'); throw primary; },
        async () => { calls.push('restore'); throw cleanup; }, evidence, error => error.message), error => error === primary);
    assert.deepEqual(calls, ['body', 'restore']);
    assert.deepEqual(evidence, { primaryFailure: primary.message, cleanupFailure: cleanup.message });
});
test('cleanup-only failure cannot turn a completed native observation into a pass', async () => {
    const error = new Error('Restore failed'), evidence = {};
    await assert.rejects(withRecordedCleanup(async () => 'real body proof', async () => { throw error; },
        evidence, failure => failure.message), failure => failure === error);
    assert.deepEqual(evidence, { cleanupFailure: error.message });
});

test('native restore and tablet recovery failures remain separate and both cleanup actions run', async () => {
    for (const bodyFailed of [true, false]) {
        const body = new Error('Actual body comparison failed'), restore = new Error('Native restore rejected'),
            tablet = new Error('Tablet recovery failed'), evidence = {}, cleanupEvidence = {}, calls = [];
        const cleanup = () => withRecordedCleanup(async () => { calls.push('restore'); throw restore; },
            async () => { calls.push('tablet'); throw tablet; }, cleanupEvidence, error => error.message);
        await assert.rejects(withRecordedCleanup(async () => { if (bodyFailed) throw body; return 'real proof'; },
            cleanup, evidence, error => error.message), error => error === (bodyFailed ? body : restore));
        assert.deepEqual(calls, ['restore', 'tablet']);
        assert.deepEqual(cleanupEvidence, { primaryFailure: restore.message, cleanupFailure: tablet.message });
        assert.equal(evidence.cleanupFailure, restore.message);
        assert.equal(evidence.primaryFailure, bodyFailed ? body.message : undefined);
    }
});
