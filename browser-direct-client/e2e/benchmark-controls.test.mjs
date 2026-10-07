// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { benchmarkCases, benchmarkCaseURL, requireBenchmarkRouteUsage } from './benchmark-controls.mjs';
const origin = 'http://127.0.0.1:46106', endpoint = 'ws://127.0.0.1:46104/';

test('routing comparison changes only the route; original image-sharing order is retained', () => {
    const routes = benchmarkCases('benchmark-asset-route');
    assert.deepEqual(routes.map(value => value.route), ['direct', 'page', 'page', 'direct']);
    assert.ok(routes.every(value => value.cache === 'on' && Object.isFrozen(value)));
    assert.deepEqual(benchmarkCases('benchmark').map(value => [value.cache, value.route]),
        [['on', 'direct'], ['off', 'direct'], ['off', 'direct'], ['on', 'direct']]);
    assert.throws(() => benchmarkCases('other'));
});
test('actual route URLs contain only the fixed server and the explicit original page baseline', () => {
    const cases = benchmarkCases('benchmark-asset-route');
    for (const control of cases) {
        const url = new URL(benchmarkCaseURL('benchmark-asset-route', origin, endpoint, control));
        assert.equal(url.origin, origin); assert.equal(url.pathname, '/');
        assert.equal(url.searchParams.get('server'), endpoint);
        assert.equal(url.searchParams.has('benchmarkImageCache'), false);
        assert.equal(url.searchParams.get('assetDispatch'), control.route === 'page' ? 'page' : null);
        assert.deepEqual([...url.searchParams.keys()], control.route === 'page' ? ['server', 'assetDispatch'] : ['server']);
    }
    const first = cases[0];
    for (const wrong of [{ ...first, cache: 'off' }, { ...first, quality: 'low' }, { ...first, route: 'page' }, { ...first, index: 8 }]) {
        assert.throws(() => benchmarkCaseURL('benchmark-asset-route', origin, endpoint, wrong));
    }
    const original = benchmarkCases('benchmark');
    assert.equal(new URL(benchmarkCaseURL('benchmark', origin, endpoint, original[1])).searchParams.get('benchmarkImageCache'), 'off');
    assert.equal(new URL(benchmarkCaseURL('benchmark', origin, endpoint, original[1])).searchParams.has('assetDispatch'), false);
});
test('selected route alone cannot qualify actual use or hide errors, pending work or fallback', () => {
    const direct = { mode: 'direct', directReady: true, directRequests: 12, pageRequests: 0,
        rejectedRequests: 0, registrationFailures: 0, revocations: 1, pending: 0 };
    assert.deepEqual(requireBenchmarkRouteUsage(direct, 'direct'), direct);
    const page = { ...direct, mode: 'page', directReady: false, directRequests: 0, pageRequests: 12 };
    assert.deepEqual(requireBenchmarkRouteUsage(page, 'page'), page);
    for (const changes of [{ directRequests: 0 }, { pageRequests: 1 }, { mode: 'page' }, { directReady: false },
        { pending: 1 }, { rejectedRequests: 1 }, { registrationFailures: 1 }, { directRequests: NaN }, { revocations: -1 }]) {
        assert.throws(() => requireBenchmarkRouteUsage({ ...direct, ...changes }, 'direct'));
    }
    assert.throws(() => requireBenchmarkRouteUsage(undefined, 'direct'));
    assert.throws(() => requireBenchmarkRouteUsage({ ...page, directRequests: 1 }, 'page'));
    assert.deepEqual(requireBenchmarkRouteUsage({ ...direct, arbitrarySecret: 'ignored' }, 'direct'), direct);
});
