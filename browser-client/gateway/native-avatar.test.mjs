// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('./native-bridge.js', import.meta.url), 'utf8');
const begin = source.indexOf('    function avatarData('), end = source.indexOf('    function state()', begin);
test('asynchronously replaced equal-size native rigs refresh names and preserve complete model-unit transforms', () => {
    let now = 0, names = ['OldHips', 'OldHead'], reads = 0;
    const sample = vm.runInNewContext('var rigCache={};' + source.slice(begin, end) + '\navatarData;', { Date: { now: () => now } });
    const q={x:0,y:0,z:0,w:1,toJSON(){throw Error('Qt wrapper must be copied');}};
    const avatar={skeletonModelURL:'new-model.fst',displayName:'x'.repeat(300),scale:1,
        position:{x:1,y:2,z:3},orientation:q,skeletonOffset:{x:0,y:.125,z:0},
        getJointNames(){reads++;return names;},getJointRotations(){return [q,q];},
        getJointTranslations(){return [{x:1.25,y:2.5,z:-3},{x:4,y:5,z:6}];}};
    const plain=value=>JSON.parse(JSON.stringify(value));
    assert.deepEqual(plain(sample('self',avatar)).jointNames,['OldHips','OldHead']);
    names=['NewHips','NewHead']; now=99;
    assert.deepEqual(plain(sample('self',avatar)).jointNames,['OldHips','OldHead']); assert.equal(reads,1);
    now=100; const updated=plain(sample('self',avatar));
    assert.deepEqual(updated.jointNames,['NewHips','NewHead']); assert.equal(reads,2);
    assert.deepEqual(updated.jointTranslations,[{x:1.25,y:2.5,z:-3},{x:4,y:5,z:6}]);
    assert.deepEqual(updated.skeletonOffset,{x:0,y:.125,z:0});assert.equal(updated.displayName.length,256);
    names=['', 'Head'];now=200;const invalid=plain(sample('self',avatar));
    assert.deepEqual([invalid.jointNames,invalid.jointRotations,invalid.jointTranslations],[[],[],[]]);
    names=['Hips','Head'];avatar.skeletonModelURL='another.fst';now=201;
    assert.deepEqual(plain(sample('self',avatar)).jointNames,['Hips','Head'],'A model change invalidates the 100ms sample immediately');
});
