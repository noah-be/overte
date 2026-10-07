// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import { Bone, Group } from 'three';
import { AvatarRig } from './avatar-rig';
import { captureAvatarPoseEvidence } from './avatar-pose-evidence';
import type { Avatar } from './world-data';

test('source joint data and actual local body transforms are copied without changing the rig', () => {
    const owner = new Group(), model = new Group(), hips = new Bone(); hips.name = 'Hips'; model.add(hips);
    const rig = new AvatarRig(model, 'gltf'); owner.add(rig.root); owner.position.set(155, -97, -400);
    const avatar = { id: 'native', position: { x: 155, y: -97, z: -400 }, jointNames: ['Hips'],
        jointRotations: [{ x: 1, y: 0, z: 0, w: 0 }], jointTranslations: [{ x: 0, y: 2, z: 0 }] };
    rig.apply(avatar); const original = hips.quaternion.clone();
    const proof = captureAvatarPoseEvidence(owner, rig, avatar);
    assert.deepEqual(proof.network!.jointRotations![0], { x: 1, y: 0, z: 0, w: 0 });
    assert.deepEqual(proof.joints[0].orientation, proof.network!.jointRotations![0]);
    assert.deepEqual(proof.joints[0].position, { x: 0, y: 2, z: 0 });
    assert.deepEqual(proof.ownerPosition, avatar.position); assert.equal(proof.partial, false);
    avatar.jointRotations[0].x = 0;
    assert.equal(proof.network!.jointRotations![0]!.x, 1); assert.equal(hips.quaternion.equals(original), true);
});

test('read-only pose evidence preserves raw null flags and independently copied native defaults',()=>{
    const owner=new Group(),model=new Group(),head=new Bone();head.name='Head';head.position.y=61;model.add(head);
    const rig=new AvatarRig(model,'gltf');owner.add(rig.root);
    const avatar:Avatar={id:'native',position:{x:0,y:0,z:0},jointNames:['Head'],jointParents:[-1],
        jointRotations:[null],jointTranslations:[null],jointDefaultRotations:[{x:0,y:0,z:0,w:1}],
        jointDefaultTranslations:[{x:0,y:61,z:0}],jointDefaultScales:[100]};
    rig.apply(avatar);const proof=captureAvatarPoseEvidence(owner,rig,avatar);
    assert.deepEqual(proof.network!.jointRotations,[null]);assert.deepEqual(proof.network!.jointTranslations,[null]);
    assert.deepEqual(proof.network!.jointParents,[-1]);assert.deepEqual(proof.network!.jointDefaultScales,[100]);
    avatar.jointDefaultTranslations![0].y=999;avatar.jointDefaultScales![0]=0;
    assert.equal(proof.network!.jointDefaultTranslations![0]!.y,61);assert.equal(proof.network!.jointDefaultScales![0],100);
    assert.equal(proof.joints[0].position.y,61);assert.equal(proof.authoredDefaults!.joints[0].position.y,61);
});
