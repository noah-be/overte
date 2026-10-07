// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Await the real asynchronous permission/component snapshot before testing it.
// Playwright's waitForFunction treats a Promise result as truthy and therefore
// cannot repeatedly poll this entry's asynchronous state() predicate.
export async function waitForPermissionState(readState, predicate, {
    deadline = Infinity, timeoutMs = 10000, pollingMs = 100,
} = {}) {
    const end = Math.min(deadline, Date.now() + timeoutMs);
    while (Date.now() < end) {
        const state = await readState();
        const matched = predicate(state);
        if (typeof matched !== 'boolean') throw new TypeError('Permission state predicates must return a boolean.');
        if (matched) return state;
        const remaining = end - Date.now();
        if (remaining > 0) await new Promise(resolve => setTimeout(resolve, Math.min(pollingMs, remaining)));
    }
    throw new Error('The actual permission/component state did not reach its required condition before the bounded deadline.');
}
