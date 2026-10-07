// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact participant/session/freshness guards for independently observed motion.
import assert from 'node:assert/strict';

export const horizontalDistance = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const delta = (a, b) => ({ x: b.x - a.x, z: b.z - a.z });
const deltaDistance = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
function point(value) {
    assert.ok(value && ['x', 'y', 'z'].every(axis => Number.isFinite(value[axis])), 'Require finite actual positions');
    return value;
}
export function requireNativeBinding(binding, state, processIdentity, newerThan) {
    assert.deepEqual(processIdentity, binding.processIdentity, 'The owned native process must remain the same');
    assert.equal(state.connected, true); assert.equal(state.session, binding.nativeSession, 'Native session changed');
    assert.ok(Number.isSafeInteger(state.sequence) && state.sequence > newerThan, 'Require a strictly newer native observer sequence');
}
export function validateBrowserMovement(binding, before, after, processIdentity, browserBefore, browserAfter) {
    requireNativeBinding(binding, after, processIdentity, before.sequence);
    assert.equal(before.session, binding.nativeSession); assert.equal(before.connected, true);
    const previous = before.peers.find(peer => peer.id === binding.browserPeerID);
    const current = after.peers.find(peer => peer.id === binding.browserPeerID);
    assert.ok(previous && current, 'Require the exact browser peer UUID in both native samples');
    point(previous.position); point(current.position); point(browserBefore); point(browserAfter);
    assert.ok(horizontalDistance(previous.position, browserBefore) <= 0.25, 'Before sample must agree with the pre-move browser pose');
    assert.ok(horizontalDistance(current.position, browserAfter) <= 0.25, 'New native sample must receive the actual moved browser pose');
    const browserDisplacement = delta(browserBefore, browserAfter), nativeDisplacement = delta(previous.position, current.position);
    assert.ok(horizontalDistance(previous.position, current.position) > 0.02, 'Native must observe nonzero actual keyboard movement');
    assert.ok(deltaDistance(browserDisplacement, nativeDisplacement) <= 0.25, 'Measured native and browser movement must agree');
    return { peerID: binding.browserPeerID, nativeSession: binding.nativeSession,
        nativeSequenceBefore: before.sequence, nativeSequenceAfter: after.sequence,
        nativePositionBefore: previous.position, nativePositionAfter: current.position,
        browserPositionBefore: browserBefore, browserPositionAfter: browserAfter,
        browserDisplacement, nativeDisplacement, horizontalTolerance: 0.25, testTeleport: false };
}
export function bodyCenter(rendered, id) {
    const body = rendered.entities.find(entity => entity.id === id);
    assert.ok(body?.rigLoaded && body.bounds && body.excludesAvatarLabel && !body.partial,
        'Require the complete actually loaded native participant body, excluding its label');
    const center = Object.fromEntries(['x', 'y', 'z'].map(axis => [axis, (body.bounds.min[axis] + body.bounds.max[axis]) / 2]));
    return point(center);
}
export function validateNativeMovement(binding, before, after, processIdentity, renderedBefore, renderedAfter) {
    requireNativeBinding(binding, after, processIdentity, before.sequence);
    assert.equal(before.session, binding.nativeSession);
    assert.equal(before.nativeMotionControlVersion,2,'Require the reviewed fixed -Z native motion observer');
    assert.equal(after.nativeMotionControlVersion,2,'Reject a stale native motion observer after the operation');
    const setup = after.nativeMotionTest;
    assert.equal(setup?.session, binding.nativeSession); assert.equal(setup?.phase, 'moved'); assert.equal(setup?.browserMoved, false);
    point(before.position); point(after.position);
    const nativeDisplacement = delta(before.position, after.position);
    assert.ok(deltaDistance(nativeDisplacement, { x: 0, z: -1 }) <= 0.25, 'Require the bounded real native-only one-metre motion along the actual bridge');
    const centerBefore = bodyCenter(renderedBefore, binding.nativeSession), centerAfter = bodyCenter(renderedAfter, binding.nativeSession);
    const bodyDisplacement = delta(centerBefore, centerAfter);
    assert.ok(deltaDistance(nativeDisplacement, bodyDisplacement) <= 0.25, 'Real received rig body must follow the newer native pose');
    const rendered = renderedAfter.entities.find(entity => entity.id === binding.nativeSession);
    assert.ok(rendered.submittedDraws > 0 && rendered.submittedTriangles > 0, 'New actual body must submit fresh main-camera draws');
    return { nativeSequenceBefore: before.sequence, nativeSequenceAfter: after.sequence, nativeDisplacement,
        bodyCenterBefore: centerBefore, bodyCenterAfter: centerAfter, bodyDisplacement,
        horizontalTolerance: 0.25, setup, browserTeleported: false, realRigDraws: rendered.submittedDraws };
}
