// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bakedIndexMap } from '../src/baked-deformation';

test('skin weights and morph deltas expand to every Draco vertex split preserving original membership', () => {
    const map = bakedIndexMap(6, [2, 0, 1, 0, 2, 1]);
    const skin = map.expand([0, 2], [.75, .25], 1);
    assert.deepEqual([...skin.indices], [1, 3, 0, 4]);
    assert.deepEqual([...skin.values], [.75, .75, .25, .25]);
    const morph = map.expand([0, 2], [0, 1, 0, 0, 0, 2], 3);
    assert.deepEqual([...morph.indices], [1, 3, 0, 4]);
    assert.deepEqual([...morph.values], [0, 1, 0, 0, 1, 0, 0, 0, 2, 0, 0, 2]);
    assert.deepEqual([...map.expand([10], [1], 1).indices], [], 'Removed native original vertices contribute to no decoded point');
});
test('version-one deformation retains the native identity mapping when original-index semantic is absent', () => {
    assert.deepEqual([...bakedIndexMap(3).expand([0, 2], [1, 2], 1).indices], [0, 2]);
});
test('deformation rejects fractional/negative/oversized indexes, array mismatch, nonfinite values, and aggregate expansion bombs', () => {
    for (const original of [[0, NaN], [0, -1], [0, .5], [0, 2_000_000]]) assert.throws(() => bakedIndexMap(2, original), /original vertex index/);
    assert.throws(() => bakedIndexMap(2, [0]), /vertex count/);
    const map = bakedIndexMap(3);
    for (const index of [-1, .5, Infinity, 2_000_000]) assert.throws(() => map.expand([index], [1], 1), /source index/);
    assert.throws(() => map.expand([0], [NaN], 1), /Non-finite/);
    assert.throws(() => map.expand([0], [], 1), /array shape/);
    assert.throws(() => map.expand([0], [1], 0), /array shape/);
    assert.throws(() => bakedIndexMap(1, [0], { generatedBytes: 128 * 1024 * 1024 }).expand([0], [1], 1), /output limits/);
});
