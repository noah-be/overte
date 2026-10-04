// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fstDependencies} from './fst-dependencies';

test('native FST baseURL and texdir resolve independently of a nested model filename', () => {
    assert.deepEqual(fstDependencies('https://assets.example/avatar/Kim.fst','filename = meshes/Kim.fbx\ntexdir = textures\n'),{
        model:'https://assets.example/avatar/meshes/Kim.fbx',textures:'https://assets.example/avatar/textures/',
    });
    assert.deepEqual(fstDependencies('https://assets.example/avatar/Kim.fst','baseURL = ../shared/\nfilename = Kim.fbx\ntexdir = textures/\n'),{
        model:'https://assets.example/shared/Kim.fbx',textures:'https://assets.example/shared/textures/',
    });
    assert.deepEqual(fstDependencies('atp:/avatars/Kim.fst','filename = Kim.fbx\ntexdir = textures\n'),{
        model:'atp:/avatars/Kim.fbx',textures:'atp:/avatars/textures/',
    });
    assert.deepEqual(fstDependencies('https://assets.example/a.fst','filename = model.fbx\n'),{model:'https://assets.example/model.fbx'});
    assert.throws(()=>fstDependencies('https://assets.example/a.fst','texdir = textures\n'),/filename/);
});
