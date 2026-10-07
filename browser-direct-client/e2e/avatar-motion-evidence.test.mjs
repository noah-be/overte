// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { validateAvatarStageMovement, validateAvatarNativeRestore } from './avatar-motion-evidence.mjs';

test('stage freshness requires newer actual native displacement, not newer timestamps/static callback repetition', () => {
    const position = { x: 155, y: -97, z: -400 }, moved = { ...position, z: -401 };
    const before = { count: 5, observedAtUnixMs: 1000, position }, after = { count: 6, observedAtUnixMs: 1200, position: moved };
    assert.equal(validateAvatarStageMovement(before, after, position, moved, 1100).horizontalDisplacementError, 0);
    for (const invalid of [{ ...after, position }, { ...after, count: 5 }, { ...after, observedAtUnixMs: 1000 },
        { ...after, observedAtUnixMs: 1099 }, { ...after, position: { ...moved, z: -400.5 } }]) {
        assert.throws(() => validateAvatarStageMovement(before, invalid, position, moved, 1100));
    }
    assert.throws(() => validateAvatarStageMovement(before, after, position, { ...moved, x: 156 }, 1100), /native/);
    const offset = { ...before, position: { ...position, x: 156 } }, offsetMoved = { ...after, position: { ...moved, x: 156 } };
    assert.throws(() => validateAvatarStageMovement(offset, offsetMoved, position, moved, 1100), /actual native position/);
});

test('native cleanup proof requires the same session, a newer restore and actual original position', () => {
    const before = { sequence: 10, position: { x: 155, y: -97, z: -400 } };
    const restored = { session: 'unit-native', nativeSequenceBefore: 12, nativeSequenceAfter: 14,
        positionBefore: { ...before.position, z: -401 }, positionAfter: before.position, nativeMotionTest: { phase: 'restored' } };
    assert.equal(validateAvatarNativeRestore(restored, before, 'unit-native').horizontalError, 0);
    for (const invalid of [{ ...restored, session: 'other-native' }, { ...restored, nativeSequenceAfter: 12 },
        { ...restored, positionAfter: { ...before.position, z: -401 } }, { ...restored, nativeMotionTest: { phase: 'moved' } }]) {
        assert.throws(() => validateAvatarNativeRestore(invalid, before, 'unit-native'));
    }
});
