// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Color, DataTexture, MeshStandardMaterial } from 'three';
import { loadNativeMaterialMaps, NativeMaterialMapFailures } from './native-material-maps';

test('the real declared native material survives a missing PSD while retaining exact colors and successful map pixels', async () => {
  const material = new MeshStandardMaterial({ color: new Color(0.8000028729438782, 0.8000028729438782, 0.8000028729438782),
    metalness: 1, roughness: 0.9039215445518494 });
  const pixels = new Uint8Array([127, 128, 255, 255]), normal = new DataTexture(pixels, 1, 1), memo = new NativeMaterialMapFailures();
  let failedRequests = 0;
  const data = { albedoMap: 'https://asset.example/original/bridges_d.psd', normalMap: 'atp:/native/normal.png' };
  const load = async (url: string) => {
    if (url.endsWith('.psd')) { failedRequests++; throw new Error('A session texture image could not be loaded.'); }
    return normal;
  };
  const failure = await loadNativeMaterialMaps(material, data, value => value, load, () => {}, memo);
  assert.deepEqual(failure, [{ property: 'albedoMap', sourceURL: data.albedoMap, error: 'A session texture image could not be loaded.' }]);
  assert.equal(material.map, null); assert.equal(material.normalMap, normal); assert.equal(material.normalMap.image.data, pixels);
  assert.deepEqual(material.color.toArray(), [0.8000028729438782, 0.8000028729438782, 0.8000028729438782]);
  assert.equal(material.metalness, 1); assert.equal(material.roughness, 0.9039215445518494);
  await loadNativeMaterialMaps(new MeshStandardMaterial(), data, value => value, load, () => {}, memo);
  assert.equal(failedRequests, 1, 'One ordered FST load does not repeatedly request the same unavailable original');
  material.dispose(); normal.dispose();
});

test('session revocation and explicit abort remain fatal even when another declared map succeeds', async () => {
  const material = new MeshStandardMaterial(), image = new DataTexture(new Uint8Array([1, 2, 3, 255]), 1, 1);
  let current = true;
  await assert.rejects(loadNativeMaterialMaps(material, { albedoMap: 'atp:/a.png', normalMap: 'atp:/b.png' }, value => value,
    async url => { if (url.endsWith('b.png')) { current = false; throw new Error('Image unavailable'); } return image; },
    () => { if (!current) throw new DOMException('The authorized owner was retired', 'AbortError'); }), { name: 'AbortError' });
  await assert.rejects(loadNativeMaterialMaps(new MeshStandardMaterial(), { albedoMap: 'atp:/a.png' }, value => value,
    async () => { throw new DOMException('Reader ended', 'AbortError'); }, () => {}, new NativeMaterialMapFailures()), { name: 'AbortError' });
  material.dispose(); image.dispose();
});
