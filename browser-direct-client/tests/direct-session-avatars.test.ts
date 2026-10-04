// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DirectSession } from '../src/direct-session';
import AvatarData from '../src/protocol/vircadia/domain/avatars/AvatarData';
import ScriptAvatar from '../src/protocol/vircadia/domain/avatar-renderer/ScriptAvatar';
import ContextManager from '../src/protocol/vircadia/domain/shared/ContextManager';
import NodeList from '../src/protocol/vircadia/domain/networking/NodeList';
import Uuid from '../src/protocol/vircadia/domain/shared/Uuid';
import type { SkeletonJoint } from '../src/protocol/vircadia/domain/avatars/AvatarTraits';
import type { SessionEvent } from '../src/session-contract';

// Retain the actual SDK avatar/default state and ScriptAvatar getters. Only
// network discovery/delivery is absent: no browser or live domain is opened.
class QuietNodeList { static contextItemType = NodeList.contextItemType; }
const nativeID = new Uuid('00112233-4455-6677-8899-aabbccddeeff');
const defaults: SkeletonJoint[] = [
    { jointName: 'Hips', jointIndex: 0, parentIndex: -1, boneType: 0,
        defaultRotation: { x: 1, y: 0, z: 0, w: 0 },
        defaultTranslation: { x: 0, y: 101, z: 0 }, defaultScale: 1 },
    { jointName: 'Head', jointIndex: 1, parentIndex: 0, boneType: 1,
        defaultRotation: { x: Math.SQRT1_2, y: 0, z: 0, w: Math.SQRT1_2 },
        defaultTranslation: { x: 0, y: 60, z: 0 }, defaultScale: 2 },
];

function nativeAvatar() {
    const context = ContextManager.createContext();
    ContextManager.set(context, QuietNodeList);
    const data = new AvatarData(context);
    data.setSkeletonData(structuredClone(defaults));
    const view = new ScriptAvatar(data);
    const events: SessionEvent[] = [];
    const session = Object.create(DirectSession.prototype) as DirectSession;
    Object.assign(session, {
        avatars: { avatarList: {
            getAvatarIDs: () => [new Uuid(), nativeID],
            getAvatar: (id: Uuid) => { assert.equal(id, nativeID); return view; },
        } },
        callbacks: { event: (event: SessionEvent) => events.push(event) },
    });
    const publish = () => {
        events.length = 0;
        (session as unknown as { publishAvatars(): void }).publishAvatars();
        assert.equal(events.length, 1);
        const event = events[0]; assert.equal(event.type, 'avatars');
        if (event.type !== 'avatars') throw new Error('Expected avatar event');
        assert.equal(event.avatars.length, 1); // The local null sentinel is omitted.
        return event.avatars[0];
    };
    return { data, publish };
}

test('native default flags retain null and the actual absolute defaults/parent table in the worker snapshot', () => {
    const { data, publish } = nativeAvatar();
    const snapshot = publish();
    assert.deepEqual(snapshot.jointRotations, [null, null]);
    assert.deepEqual(snapshot.jointTranslations, [null, null]);
    assert.deepEqual(snapshot.jointNames, ['Hips', 'Head']);
    assert.deepEqual(snapshot.jointParents, [-1, 0]);
    assert.deepEqual(snapshot.jointDefaultRotations, defaults.map(joint => joint.defaultRotation));
    assert.deepEqual(snapshot.jointDefaultTranslations, defaults.map(joint => joint.defaultTranslation));
    assert.deepEqual(snapshot.jointDefaultScales, [1, 2]);
    assert.deepEqual(data.getJointRotations(), [null, null]);
});

test('an animated native joint can return to its actual default without becoming identity or zero', () => {
    const { data, publish } = nativeAvatar();
    const turn = { x: 0, y: Math.SQRT1_2, z: 0, w: Math.SQRT1_2 };
    const translation = { x: -2, y: 61, z: 3 };
    data.setJointRotations([null, turn]); data.setJointTranslations([null, translation]);
    const animated = publish();
    assert.deepEqual(animated.jointRotations, [null, turn]);
    assert.deepEqual(animated.jointTranslations, [null, translation]);
    // Exercise the actual SDK receiver's native default-bit transition.
    data.parseDataFromBuffer({ sessionUUID: nativeID, globalPosition: undefined,
        localOrientation: undefined, avatarScale: undefined, audioLoudness: undefined,
        jointRotationsValid: undefined, jointRotations: undefined,
        jointTranslationsValid: undefined, jointTranslations: undefined,
        jointRotationsUseDefault: [true, true], jointTranslationsUseDefault: [true, true] });
    const restored = publish();
    assert.deepEqual(restored.jointRotations, [null, null]);
    assert.deepEqual(restored.jointTranslations, [null, null]);
    assert.deepEqual(restored.jointDefaultRotations, defaults.map(joint => joint.defaultRotation));
    assert.deepEqual(restored.jointDefaultTranslations, defaults.map(joint => joint.defaultTranslation));
    assert.deepEqual(animated.jointRotations, [null, turn]);
});

test('a queued native joint snapshot is independent of subsequent mutable SDK pose and trait objects', () => {
    const { data, publish } = nativeAvatar();
    const turn = { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 };
    const translation = { x: 4, y: 62, z: -2 };
    data.setJointRotations([null, turn]); data.setJointTranslations([null, translation]);
    const snapshot = publish();
    turn.z = 0; translation.y = 999;
    data.getSkeletonData()[0].defaultRotation.x = 0;
    data.getSkeletonData()[0].defaultTranslation.y = 999;
    assert.equal(snapshot.jointRotations?.[1]?.z, Math.SQRT1_2);
    assert.equal(snapshot.jointTranslations?.[1]?.y, 62);
    assert.equal(snapshot.jointDefaultRotations?.[0]?.x, 1);
    assert.equal(snapshot.jointDefaultTranslations?.[0]?.y, 101);
});
