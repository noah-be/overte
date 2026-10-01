// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyNativeAlpha, nativeTextureAlpha } from '../src/texture-alpha';

test('native alpha classifies opacity and the exact five-percent intermediate boundary', () => {
  assert.equal(classifyNativeAlpha(100, 100, 0), 'opaque');
  assert.equal(classifyNativeAlpha(100, 50, 0), 'mask');
  assert.equal(classifyNativeAlpha(100, 50, 5), 'mask');
  assert.equal(classifyNativeAlpha(100, 50, 6), 'blend');
  assert.equal(classifyNativeAlpha(19, 18, 1), 'blend');
  assert.equal(classifyNativeAlpha(20, 19, 1), 'mask');
  assert.equal(classifyNativeAlpha(262144, 175920, 0), 'mask'); // Exact actual Hub Leaf-Cards PNG.
});
test('invalid counts, unloaded, over-budget and cancelled images fail honestly', async () => {
  for (const counts of [[0,0,0],[10,11,0],[10,5,6],[10,-1,0],[1.5,1,0]]) assert.throws(() => classifyNativeAlpha(...counts as [number,number,number]));
  await assert.rejects(nativeTextureAlpha({image:null}), /loaded image/);
  await assert.rejects(nativeTextureAlpha({image:{width:8193,height:8192}}), /64 megapixels/);
  await assert.rejects(nativeTextureAlpha({image:{width:1,height:1,naturalWidth:8193,naturalHeight:8192}}), /64 megapixels/);
  const abort = new AbortController(); abort.abort();
  await assert.rejects(nativeTextureAlpha({image:{width:1,height:1}},abort.signal), {name:'AbortError'});
});
