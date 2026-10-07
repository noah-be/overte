// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {defaultAvatarAsset} from './default-avatar.ts';
test('only exact public mannequin resources map to the bundled same-origin assets', () => {
    const base = 'https://visitor.example/';
    assert.equal(defaultAvatarAsset('qrc:////meshes/defaultAvatar_full.fst',base),`${base}default-avatar/defaultAvatar_full.fst`);
    assert.equal(defaultAvatarAsset('resource:/meshes/mannequin/mannequin.fbx',base),`${base}default-avatar/mannequin/mannequin.fbx`);
    assert.equal(defaultAvatarAsset(`${base}default-avatar/mannequin/Eyes.png`,base),`${base}default-avatar/mannequin/Eyes.png`);
    for (const asset of ['file:///etc/passwd','qrc://operator/meshes/defaultAvatar_full.fst','qrc:/meshes/private.json',
        'resource:/scripts/operator.js','https://attacker.example/default-avatar/mannequin/Eyes.png',
        `${base}default-avatar/mannequin/Eyes.png?secret=1`]) assert.equal(defaultAvatarAsset(asset,base),undefined);
});
