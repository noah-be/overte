// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { currentCompressedColorCapabilities } from './compressed-color-capabilities';

for (const supported of [false, true]) test(`current renderer capability values preserve supported=${supported}`, () => {
  const names: string[] = [];
  const renderer = { capabilities: { maxTextureSize: 8192 }, extensions: { has(name: string) { names.push(name); return supported; } } };
  assert.deepEqual(currentCompressedColorCapabilities(renderer), { s3tc: supported, s3tcSRGB: supported, maximumTextureSize: 8192 });
  assert.deepEqual(names, ['WEBGL_compressed_texture_s3tc', 'WEBGL_compressed_texture_s3tc_srgb']);
});
test('capabilities are independent and read from replacement context caches, without a stale snapshot', () => {
  const renderer = { capabilities: { maxTextureSize: 4096 }, extensions: { has: (name: string): boolean => name === 'WEBGL_compressed_texture_s3tc' } };
  const previous = currentCompressedColorCapabilities(renderer);
  assert.deepEqual(previous, { s3tc: true, s3tcSRGB: false, maximumTextureSize: 4096 });
  renderer.capabilities = { maxTextureSize: 16384 };
  renderer.extensions = { has: () => false };
  assert.deepEqual(currentCompressedColorCapabilities(renderer), { s3tc: false, s3tcSRGB: false, maximumTextureSize: 16384 });
  assert.deepEqual(previous, { s3tc: true, s3tcSRGB: false, maximumTextureSize: 4096 });
});
test('every lookup still consults current renderer cache; no extension support is invented', () => {
  let reads = 0;
  const renderer = { capabilities: { maxTextureSize: 4096 }, extensions: { has() { reads++; return false; } } };
  for (let i=0;i<232;i++) assert.deepEqual(currentCompressedColorCapabilities(renderer), { s3tc: false, s3tcSRGB: false, maximumTextureSize: 4096 });
  assert.equal(reads, 464);
});
