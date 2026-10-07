// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// One shared absolute deadline; a later loading phase never renews the budget.
export const CASE_BUDGET_MS = 285000;
export function commonSceneDeadline(now, requestedSeconds, caseDeadline) {
    if (!Number.isFinite(now) || !Number.isFinite(caseDeadline) || !Number.isFinite(requestedSeconds) || requestedSeconds <= 0) {
        throw Error('Invalid software test budget');
    }
    return Math.min(now + requestedSeconds * 1000, caseDeadline);
}
export function remainingSceneBudget(now, deadline, requestedMaximum = Infinity) {
    const remaining = Math.min(requestedMaximum, deadline - now);
    if (!(remaining > 0)) throw Error('The common software scene deadline expired');
    return remaining;
}
