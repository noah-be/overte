// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';

const point = value => {
    assert.ok(value && ['x', 'y', 'z'].every(axis => Number.isFinite(value[axis])), 'Require finite actual native/event positions');
    return value;
};
export function avatarPipelineStages(pipeline) {
    const workers = pipeline.worker.workers.filter(worker => !worker.unavailable);
    assert.equal(workers.length, 1, 'Require the actual single production session worker');
    const channels = workers[0].channels.filter(channel => channel.readyState === 'open');
    assert.equal(channels.length, 1, 'Require the actual single current AvatarMixer channel');
    const stage = (observer, count) => { assert.ok(observer.last, 'Require an actual privately matched native position');
        return { count: observer[count], observedAtUnixMs: observer.last.observedAtUnixMs, position: point(observer.last.position) }; };
    return { rawReceive: stage(channels[0].received, 'positions'), workerPost: stage(workers[0].sourceEvents, 'samples'),
        facadeCallback: stage(pipeline.page.facadeEvents, 'samples') };
}

export function validateAvatarStageMovement(before, after, nativeBefore, nativeAfter, appliedAtUnixMs) {
    point(before.position); point(after.position); point(nativeBefore); point(nativeAfter);
    assert.ok(Math.hypot(before.position.x - nativeBefore.x, before.position.z - nativeBefore.z) <= .25,
        'Require pre-move stage position to agree with actual native position');
    assert.ok(Math.hypot(after.position.x - nativeAfter.x, after.position.z - nativeAfter.z) <= .25,
        'Require newer stage position to agree with actual moved native position');
    assert.ok(after.count > before.count, 'Require a strictly newer observed stage sample');
    assert.ok(after.observedAtUnixMs > before.observedAtUnixMs && after.observedAtUnixMs >= appliedAtUnixMs,
        'Require a stage sample after actual native application time');
    const displacement = Object.fromEntries(['x', 'y', 'z'].map(axis => [axis, after.position[axis] - before.position[axis]]));
    const nativeDisplacement = Object.fromEntries(['x', 'y', 'z'].map(axis => [axis, nativeAfter[axis] - nativeBefore[axis]]));
    assert.ok(Math.hypot(nativeDisplacement.x, nativeDisplacement.z + 1) <= .25,
        'Require the original measured actual native one-metre -Z operation');
    const horizontalDisplacementError = Math.hypot(displacement.x - nativeDisplacement.x, displacement.z - nativeDisplacement.z);
    assert.ok(horizontalDisplacementError <= .25, 'Require received stage displacement to match actual native movement');
    assert.ok(Math.hypot(displacement.x, displacement.z) > .02, 'Static republishing cannot prove movement');
    return { displacement, nativeDisplacement, horizontalDisplacementError, horizontalTolerance: .25,
        before, after, appliedAtUnixMs, renderedBodyAcceptance: false };
}

export function validateAvatarNativeRestore(restored, before, expectedSession) {
    assert.equal(restored.session, expectedSession, 'Restore must bind the exact native session');
    assert.equal(restored.nativeMotionTest?.phase, 'restored');
    assert.ok(Number.isSafeInteger(restored.nativeSequenceAfter) && restored.nativeSequenceAfter > restored.nativeSequenceBefore
        && restored.nativeSequenceAfter > before.sequence, 'Require a newer actual native restore observation');
    point(restored.positionAfter); point(before.position);
    const horizontalError = Math.hypot(restored.positionAfter.x - before.position.x, restored.positionAfter.z - before.position.z);
    assert.ok(horizontalError <= .25, 'Restore the actual native-only setup within the original strict horizontal bound');
    return { nativeSessionMatched: true, nativeSequenceBefore: restored.nativeSequenceBefore, nativeSequenceAfter: restored.nativeSequenceAfter,
        positionBefore: restored.positionBefore, positionAfter: restored.positionAfter, phase: 'restored', horizontalError, horizontalTolerance: .25, passed: true };
}
