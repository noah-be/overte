// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import { CASE_BUDGET_MS, commonSceneDeadline, remainingSceneBudget } from './time-budgets.mjs';
test('all actual scene phases share one deadline without renewing a fresh wait', () => {
    const deadline = commonSceneDeadline(1000, 240, CASE_BUDGET_MS);
    assert.equal(deadline, 241000);
    assert.equal(remainingSceneBudget(11000, deadline), 230000);
    assert.equal(remainingSceneBudget(181000, deadline), 60000);
    assert.equal(remainingSceneBudget(181000, deadline, 10000), 10000);
    assert.throws(() => remainingSceneBudget(241000, deadline), /expired/);
    assert.equal(commonSceneDeadline(100000, 999, CASE_BUDGET_MS), CASE_BUDGET_MS);
    assert.ok(CASE_BUDGET_MS * 4 < 20 * 60 * 1000);
});
