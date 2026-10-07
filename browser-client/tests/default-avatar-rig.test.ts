// SPDX-License-Identifier: Apache-2.0
// Compare the real packaged mannequin against independently captured native world joints.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { Bone, Group, Quaternion, SkinnedMesh, Texture, TextureLoader, Vector3 } from 'three';
import { AvatarRig } from '../src/avatar-rig';
import type { Avatar } from '../src/world-data';

test('actual default mannequin skin and joint transforms agree with native 2026.04.1', async () => {
    const pose = JSON.parse(await readFile(new URL('./fixtures/default-avatar-native-pose.json', import.meta.url), 'utf8'));
    const bytes = await readFile(new URL('../../interface/resources/meshes/mannequin/mannequin.fbx', import.meta.url));
    // Texture decoding is covered by the real browser fixture. The Node audit only
    // compares actual mesh deformation and native skeletal transforms.
    const original = TextureLoader.prototype.load;
    TextureLoader.prototype.load = function () { return new Texture(); };
    let model: Group;
    try { model = new FBXLoader().parse(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), ''); }
    finally { TextureLoader.prototype.load = original; }
    const skins: SkinnedMesh[] = [];
    model.traverse(object => { if (object instanceof SkinnedMesh) skins.push(object); });
    assert.equal(skins.length, 2);
    assert.equal(skins.reduce((total, skin) => total + skin.geometry.getAttribute('position').count / 3, 0), 14748);
    const rig = new AvatarRig(model, 'fbx');
    assert.equal(rig.boneCount, 67, 'Shared identity cluster children cannot receive a second native transform');
    const parent = new Group();
    parent.position.set(pose.position.x, pose.position.y, pose.position.z);
    parent.quaternion.copy(new Quaternion(pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w));
    parent.add(rig.root);
    parent.updateMatrixWorld(true);
    for (const skin of skins) skin.skeleton.update();
    const rest = skins.map(skin => skin.applyBoneTransform(0, new Vector3().fromBufferAttribute(skin.geometry.getAttribute('position'), 0)).clone());
    rig.apply({ id: 'offline-native-audit', position: pose.position, jointNames: pose.jointNames,
        jointRotations: pose.rotations, jointTranslations: pose.translations } as Avatar);
    parent.updateMatrixWorld(true);
    let compared = 0;
    model.traverse(object => {
        if (!(object instanceof Bone)) return;
        const bone = object as Bone & { ID?: number };
        const parent = bone.parent as (Bone & { ID?: number }) | null;
        if (parent?.isBone && bone.ID === parent.ID && !bone.userData.transformData) return;
        const index = pose.jointNames.indexOf(bone.userData.originalName || bone.name);
        if (index < 0) return;
        const expected = pose.worldJointPositions[index];
        assert.ok(bone.getWorldPosition(new Vector3()).distanceTo(new Vector3(expected.x, expected.y, expected.z)) < .001,
            `Actual native ${bone.name} world transform must agree within 1mm`);
        compared++;
    });
    assert.equal(compared, 67);
    let changed = 0;
    for (const [index, skin] of skins.entries()) {
        skin.skeleton.update();
        const vertex = skin.applyBoneTransform(0, new Vector3().fromBufferAttribute(skin.geometry.getAttribute('position'), 0));
        assert.ok(vertex.toArray().every(Number.isFinite));
        if (vertex.distanceTo(rest[index]) > .01) changed++;
    }
    assert.equal(changed, 2, 'Both actual face and body skin respond to independently captured native idle animation');
});
