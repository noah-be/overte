// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { encodePCM, decodePCM } from './pcm.ts';

test('PCM uses signed little-endian samples and clips invalid/oversized input', () => {
    const buffer = encodePCM([-2, -1, -0.5, 0, 0.5, 1, 2, NaN]);
    assert.deepEqual(Array.from(new Uint8Array(buffer)), [0,128,0,128,0,192,0,0,0,64,255,127,255,127,0,0]);
    const values = decodePCM(buffer);
    assert.equal(values[0], -1);
    assert.equal(values[7], 0);
    assert.ok(Math.abs(values[5] - 1) < 0.00004);
});
test('partial audio frames fail explicitly', () => {
    assert.throws(() => decodePCM(new ArrayBuffer(3)), /Incomplete PCM sample/);
});
