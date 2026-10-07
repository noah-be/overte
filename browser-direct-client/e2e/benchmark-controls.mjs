// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// One experimental variable per paired production-scene comparison.
import assert from 'node:assert/strict';

export function benchmarkCases(mode) {
    assert.ok(['benchmark', 'benchmark-asset-route'].includes(mode), 'Unknown paired benchmark mode.');
    const labels = mode === 'benchmark' ? ['on', 'off', 'off', 'on'] : ['direct', 'page', 'page', 'direct'];
    return Object.freeze(labels.map((label, offset) => Object.freeze({ index: offset + 1, label,
        cache: mode === 'benchmark' ? label : 'on', route: mode === 'benchmark' ? 'direct' : label })));
}

export function benchmarkCaseURL(mode, origin, endpoint, control) {
    const planned = benchmarkCases(mode)[control?.index - 1];
    assert.ok(planned, 'The case must belong to the fixed four-case plan.');
    assert.deepEqual(control, planned, 'Do not add unrelated settings or combine cache and routing changes.');
    const url = new URL('/', origin);
    url.searchParams.set('server', endpoint);
    if (control.cache === 'off') url.searchParams.set('benchmarkImageCache', 'off');
    if (control.route === 'page') url.searchParams.set('assetDispatch', 'page');
    return url.href;
}

/** Require production counters from actual dispatch, rather than a query
 * string or selected-mode label alone. Return only the documented safe fields. */
export function requireBenchmarkRouteUsage(snapshot, route) {
    assert.ok(['direct', 'page'].includes(route));
    assert.ok(snapshot && typeof snapshot === 'object', 'Actual production asset-routing counters are required.');
    assert.equal(snapshot.mode, route, 'The production route must match this case.');
    assert.equal(typeof snapshot.directReady, 'boolean');
    const result = { mode: snapshot.mode, directReady: snapshot.directReady };
    for (const name of ['directRequests', 'pageRequests', 'rejectedRequests', 'registrationFailures', 'revocations', 'pending']) {
        assert.ok(Number.isSafeInteger(snapshot[name]) && snapshot[name] >= 0, `Actual ${name} must be a finite nonnegative counter.`);
        result[name] = snapshot[name];
    }
    assert.ok(result[route === 'direct' ? 'directRequests' : 'pageRequests'] > 0, 'The selected route must actually carry native asset requests.');
    assert.equal(result[route === 'direct' ? 'pageRequests' : 'directRequests'], 0, 'No alternate route or silent fallback may be hidden.');
    assert.equal(result.rejectedRequests, 0); assert.equal(result.registrationFailures, 0); assert.equal(result.pending, 0);
    if (route === 'direct') assert.equal(result.directReady, true, 'The direct worker asset port must be ready.');
    return result;
}
