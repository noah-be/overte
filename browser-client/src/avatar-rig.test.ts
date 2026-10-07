// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Bone,Group,Quaternion,Vector3} from 'three';
import {AvatarRig} from './avatar-rig.ts';

test('native joint names drive every body/face bone regardless of stale FST indices', () => {
    const model = new Group(), hips = new Bone(), head = new Bone(), duplicate = new Bone();
    hips.name = 'Hips'; hips.position.y = 100;
    head.name = 'Head'; head.position.y = 60;
    duplicate.name = 'Head'; duplicate.position.y = 60;
    hips.add(head,duplicate); model.add(hips); model.userData.unitScaleFactor = 1;
    const rig = new AvatarRig(model,'fbx');
    const turn = new Quaternion().setFromAxisAngle(new Vector3(0,1,0),.8);
    rig.apply({id:'native',position:{x:0,y:0,z:0},jointNames:['body','Head','Hips'],
        jointRotations:[{x:0,y:0,z:0,w:1},{x:turn.x,y:turn.y,z:turn.z,w:turn.w},{x:0,y:0,z:0,w:1}],
        jointTranslations:[{x:0,y:0,z:0},{x:0,y:61,z:0},{x:0,y:100,z:0}]});
    assert.ok(head.quaternion.equals(duplicate.quaternion));
    assert.ok(head.quaternion.angleTo(turn) < 1e-7);
    assert.equal(head.position.y,61);
    rig.root.updateMatrixWorld(true);
    assert.ok(hips.getWorldPosition(new Vector3()).length() < 1e-10);
    assert.ok(Math.abs(head.getWorldPosition(new Vector3()).y - .61) < 1e-10);
    assert.equal(rig.boneCount,3);
});
test('avatar units and authoring lights preserve native geometry conventions', () => {
    const model = new Group(); model.userData.unitScaleFactor = NaN;
    assert.throws(() => new AvatarRig(model,'fbx'), /units/);
    assert.equal(new AvatarRig(new Group(),'gltf').root.children[0].scale.x,1);
});
test('shared FBX cluster identity children inherit their canonical joint only once', () => {
    const model = new Group(), head = new Bone() as Bone & {ID:number}, binding = new Bone() as Bone & {ID:number};
    head.name = binding.name = 'Head'; head.ID = binding.ID = 42;
    head.userData.transformData = {translation:[0,60,0]}; head.position.y = 60;
    head.add(binding); model.add(head);
    const rig = new AvatarRig(model,'fbx');
    rig.apply({id:'native',position:{x:0,y:0,z:0},jointNames:['Head'],jointTranslations:[{x:0,y:61,z:0}],jointRotations:[{x:0,y:0,z:0,w:1}]});
    rig.root.updateMatrixWorld(true);
    assert.equal(binding.position.length(),0);
    assert.equal(head.position.y,61);
    assert.equal(rig.boneCount,1);
    assert.ok(Math.abs(binding.getWorldPosition(new Vector3()).y - .61) < 1e-10);
});
