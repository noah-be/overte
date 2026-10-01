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

function completionFixture(actualSource = source) {
    let clock = 0, reads = 0, delay = 268, names = ['Hips', 'Head'];
    const start = actualSource.indexOf('    function avatarData(');
    const finish = actualSource.indexOf('    function state()', start);
    const sample = vm.runInNewContext('var rigCache={};' + actualSource.slice(start, finish) + '\navatarData;', {
        Date: { now: () => clock },
    });
    const q = { x: 0, y: 0, z: 0, w: 1 }, t = { x: 1, y: 2, z: 3 };
    const avatar = {
        skeletonModelURL: 'same-url.fst', position: t, orientation: q, scale: 1, displayName: 'Visitor',
        getJointNames() { return names; },
        getJointRotations() { reads++; clock += delay; return [q, q]; },
        getJointTranslations() { return [t, t]; },
    };
    return {
        sample: () => JSON.parse(JSON.stringify(sample('self', avatar))), avatar,
        reads: () => reads, time: value => { clock = value; }, delay: value => { delay = value; },
        names: value => { names = value; },
    };
}

test('blocked complete native rig reads retain the original100ms reuse period from delivery', () => {
    // Counterfactual negative control changes only the previously defective
    // timestamp expression in the actual fixed production function.
    const expression = 'time: valid ? Date.now() : now, names:';
    assert.equal(source.split(expression).length, 2, 'The actual completion-stamp expression must be present exactly once');
    const negative = completionFixture(source.replace(expression, 'time: now, names:'));
    negative.sample(); negative.delay(0); negative.sample();
    assert.equal(negative.reads(), 2, 'The old attempt timestamp immediately repeats a completed268ms read');
    const actual = completionFixture();
    const first = actual.sample(); actual.delay(0);
    assert.deepEqual(actual.sample(), first); assert.equal(actual.reads(), 1);
    actual.time(367); actual.sample(); assert.equal(actual.reads(), 1);
    actual.time(368); actual.sample(); assert.equal(actual.reads(), 2, 'A new complete sample is due at the unchanged100ms boundary');
});

test('cached rig arrays never delay current pose or equal-size name and URL replacements', () => {
    const actual = completionFixture(); actual.delay(0);
    const first = actual.sample(); actual.avatar.position = { x: 8, y: 9, z: 10 };
    actual.time(50); const next = actual.sample();
    assert.deepEqual(next.position, { x: 8, y: 9, z: 10 });
    assert.deepEqual(next.jointRotations, first.jointRotations);
    assert.deepEqual(next.jointTranslations, first.jointTranslations);
    actual.names(['NewHips', 'NewHead']); actual.time(99);
    assert.deepEqual(actual.sample().jointNames, ['Hips', 'Head']);
    actual.time(100); assert.deepEqual(actual.sample().jointNames, ['NewHips', 'NewHead']);
    actual.avatar.skeletonModelURL = 'replacement.fst'; actual.names(['OtherHips', 'OtherHead']); actual.time(101);
    assert.deepEqual(actual.sample().jointNames, ['OtherHips', 'OtherHead'], 'URL replacement bypasses the old sample immediately');
});

test('blocked invalid and thrown native rig reads cannot receive fresh completion timestamps', () => {
    const invalid = completionFixture(); invalid.names(['', 'Head']);
    const first = invalid.sample();
    assert.deepEqual([first.jointNames, first.jointRotations, first.jointTranslations], [[], [], []]);
    invalid.delay(0); invalid.sample();
    assert.equal(invalid.reads(), 2, 'Invalid blocked samples retain the original attempt timestamp');
    const actual = completionFixture(); actual.delay(0); actual.sample(); actual.time(100);
    const original = actual.avatar.getJointRotations, expected = Error('native getter failure');
    actual.avatar.getJointRotations = () => { throw expected; };
    assert.throws(() => actual.sample(), error => error === expected, 'Native error identity is preserved');
    actual.avatar.getJointRotations = original; actual.sample();
    assert.equal(actual.reads(), 2, 'Throwing left the previous cache entry expired');
});

function emptyRigFixture(actualSource = source) {
    let clock = 0, names = [], namesReads = 0, rotationReads = 0, translationReads = 0;
    const start = actualSource.indexOf('    function avatarData(');
    const finish = actualSource.indexOf('    function state()', start);
    const sample = vm.runInNewContext('var rigCache={};' + actualSource.slice(start, finish) + '\navatarData;', {
        Date: { now: () => clock },
    });
    const q = {x:0,y:0,z:0,w:1}, t = {x:1,y:2,z:3};
    const avatar = {skeletonModelURL:'loading.fst',position:t,orientation:q,displayName:'Visitor',scale:1,
        getJointNames(){namesReads++;return names;},
        getJointRotations(){rotationReads++;return [q];},
        getJointTranslations(){translationReads++;return [t];}};
    return {sample:()=>JSON.parse(JSON.stringify(sample('self',avatar))),avatar,
        time:value=>{clock=value;},names:value=>{names=value;},
        reads:()=>({names:namesReads,rotations:rotationReads,translations:translationReads})};
}

test('only a genuine empty native names array avoids unusable bulk transforms, unlike the original single-expression control',()=>{
    const guard='var emptyRig = Array.isArray(names) && names.length === 0;';
    assert.equal(source.split(guard).length,2,'The exact narrow guard exists once');
    const old=emptyRigFixture(source.replace(guard,'var emptyRig = false;'));
    const expected=Error('Blocked unusable getter');old.avatar.getJointRotations=()=>{throw expected;};
    assert.throws(()=>old.sample(),error=>error===expected,'The old function still invokes an unusable blocking getter');
    const actual=emptyRigFixture();actual.avatar.getJointRotations=()=>{throw expected;};actual.avatar.getJointTranslations=()=>{throw expected;};
    const result=actual.sample();assert.deepEqual([result.jointNames,result.jointRotations,result.jointTranslations],[[],[],[]]);
    assert.deepEqual(result.position,{x:1,y:2,z:3});assert.deepEqual(actual.reads(),{names:1,rotations:0,translations:0});
});

test('empty native rigs retain current pose, the original100ms retry and immediate model/name readiness',()=>{
    const actual=emptyRigFixture();actual.sample();actual.names(['Hips']);
    actual.avatar.position={x:8,y:9,z:10};actual.time(50);const during=actual.sample();
    assert.deepEqual(during.position,{x:8,y:9,z:10});assert.deepEqual(during.jointNames,[]);
    actual.time(99);actual.sample();assert.deepEqual(actual.reads(),{names:1,rotations:0,translations:0});
    actual.time(100);const ready=actual.sample();assert.deepEqual(ready.jointNames,['Hips']);
    assert.deepEqual(ready.jointRotations,[{x:0,y:0,z:0,w:1}]);assert.deepEqual(ready.jointTranslations,[{x:1,y:2,z:3}]);
    actual.names([]);actual.avatar.skeletonModelURL='replacement.fst';actual.time(101);
    const replacing=actual.sample();assert.deepEqual([replacing.jointNames,replacing.jointRotations,replacing.jointTranslations],[[],[],[]]);
    assert.deepEqual(actual.reads(),{names:3,rotations:1,translations:1});
    actual.names(['NewHips']);actual.time(200);assert.deepEqual(actual.sample().jointNames,[]);
    actual.time(201);assert.deepEqual(actual.sample().jointNames,['NewHips']);
});

test('untyped/null/nonempty-invalid names retain bulk getter ordering and original thrown-error identity',()=>{
    for(const names of [null,undefined,{length:0},new Uint8Array(0),[''],Array(1001).fill('Hips')]){
        const actual=emptyRigFixture();actual.names(names);const calls=[],expected=Error('Native bulk error');
        actual.avatar.getJointRotations=()=>{calls.push('rotations');return [{x:0,y:0,z:0,w:1}];};
        actual.avatar.getJointTranslations=()=>{calls.push('translations');throw expected;};
        assert.throws(()=>actual.sample(),error=>error===expected);assert.deepEqual(calls,['rotations','translations']);
    }
    const actual=emptyRigFixture();actual.sample();actual.time(100);const original=actual.avatar.getJointNames,expected=Error('Native names error');
    actual.avatar.getJointNames=()=>{throw expected;};assert.throws(()=>actual.sample(),error=>error===expected);
    actual.avatar.getJointNames=original;actual.names(['Hips']);assert.deepEqual(actual.sample().jointNames,['Hips'],'A throwing name getter never renews the expired empty cache');
});

test('an empty array obtained after a delayed names read retains its original attempt timestamp',()=>{
    const actual=emptyRigFixture(),original=actual.avatar.getJointNames;
    actual.avatar.getJointNames=()=>{const names=original();actual.time(268);return names;};
    actual.sample();actual.avatar.getJointNames=original;actual.names(['Hips']);
    assert.deepEqual(actual.sample().jointNames,['Hips']);assert.deepEqual(actual.reads(),{names:2,rotations:1,translations:1});
});
