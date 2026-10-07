// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import { validateBrowserMovement, validateNativeMovement } from './native-motion-evidence.mjs';
const processIdentity = { pid: 123, startTicks: '456' };
const binding = { processIdentity, nativeSession: 'native', browserPeerID: 'actual-browser' };
const origin = { x: 155, y: -98, z: -397 }, moved = { ...origin, z: -398 };
const report = (sequence, position) => ({ connected: true, session: 'native', sequence,
    position: origin, nativeMotionControlVersion:2, peers: [{ id: 'actual-browser', position }] });

test('native receipt requires fresh same-process/session exact-peer keyboard displacement', () => {
    const before = report(10, origin), after = report(11, moved);
    assert.equal(validateBrowserMovement(binding, before, after, processIdentity, origin, moved).testTeleport, false);
    for (const stale of [report(10, moved), { ...after, session: 'new-native' }, report(11, origin),
        { ...after, peers: [{ id: 'other-browser', position: moved }] }]) {
        assert.throws(() => validateBrowserMovement(binding, before, stale, processIdentity, origin, moved));
    }
    assert.throws(() => validateBrowserMovement(binding, before, after, { pid: 123, startTicks: '789' }, origin, moved));
});
test('native scripted motion must reach the actual loaded body and fresh label-free draws', () => {
    const before = report(20, origin), after = { ...report(21, origin), position: { ...origin, z: -398 },
        nativeMotionTest: { session: 'native', phase: 'moved', browserMoved: false } };
    const draw = (z, overrides = {}) => ({ entities: [{ id: 'native', rigLoaded: true, excludesAvatarLabel: true,
        partial: false, bounds: { min: { x: 155, y: -98, z }, max: { x: 155, y: -97, z } },
        submittedDraws: 2, submittedTriangles: 200, ...overrides }] });
    assert.equal(validateNativeMovement(binding, before, after, processIdentity, draw(-397), draw(-398)).realRigDraws, 2);
    for (const invalid of [draw(-397), draw(-398, { rigLoaded: false }), draw(-398, { submittedDraws: 0 }),
        draw(-398, { excludesAvatarLabel: false })]) {
        assert.throws(() => validateNativeMovement(binding, before, after, processIdentity, draw(-397), invalid));
    }
    for(const [staleBefore,staleAfter] of [[{...before,nativeMotionControlVersion:1},after],
        [before,{...after,nativeMotionControlVersion:1}]]){
        assert.throws(()=>validateNativeMovement(binding,staleBefore,staleAfter,processIdentity,draw(-397),draw(-398)),/observer/);
    }
});
