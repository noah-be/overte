// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Material, MeshBasicMaterial, Texture } from 'three';
import { applyNativeMaterialAlpha, cloneNativeMaterial, getNativeAlphaOptions, nativeOpacityMapMode } from '../src/native-alpha-material';

test('explicit native opacity modes take precedence over automatic inspection and preserve scalar opacity', async () => {
  const material = new MeshBasicMaterial({ map: new Texture(), opacity: 0.4 });
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_OPAQUE' });
  assert.equal(material.opacity, 0.4);
  assert.equal(material.transparent, true);
  assert.equal(material.alphaTest, 0);
  assert.equal(material.userData.nativeAlpha.classification, 'opaque');
  // Pinned native TextureMap retains RGBA; scalar translucency uses map alpha.
  assert.equal(material.onBeforeCompile, Material.prototype.onBeforeCompile);
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: 0.75 });
  assert.equal(material.opacity, 0.4);
  assert.ok(Math.abs(material.alphaTest - 0.3) < 1e-12);
  assert.equal(material.userData.nativeAlpha.classification, 'mask');
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' });
  assert.equal(material.alphaTest, 0);
  assert.equal(material.transparent, true);
  material.dispose();
});

test('ineligible albedo alpha remains opaque without requesting an image or treating RGB black as transparency', async () => {
  const material = new MeshBasicMaterial({ map: new Texture(), alphaMap: new Texture(), transparent: true });
  await applyNativeMaterialAlpha(material, { useAlpha: false });
  assert.equal(material.transparent, false);
  assert.equal(material.alphaTest, 0);
  assert.equal(material.alphaMap, null);
  assert.equal(material.onBeforeCompile, Material.prototype.onBeforeCompile);
  for (const invalid of ['mask', 'blend', 'opacity_map_mask', 'fallthrough', null]) assert.equal(nativeOpacityMapMode(invalid), undefined);
  assert.equal(nativeOpacityMapMode('OPACITY_MAP_MASK'), 'OPACITY_MAP_MASK');
  material.dispose();
});

test('cloning a native mask retains shader behavior and changing its mode removes an obsolete mask hook', async () => {
  const material = new MeshBasicMaterial({ map: new Texture() });
  await applyNativeMaterialAlpha(material, { useAlpha: false, mode: 'OPACITY_MAP_MASK', cutoff: 2 });
  const clone = cloneNativeMaterial(material);
  assert.equal(clone.userData.nativeAlpha.cutoff, 1);
  assert.equal(clone.onBeforeCompile, material.onBeforeCompile);
  assert.equal(clone.customProgramCacheKey(), 'native-material-alpha-mask');
  await applyNativeMaterialAlpha(clone, { useAlpha: false, mode: 'OPACITY_MAP_BLEND' });
  assert.equal(clone.onBeforeCompile, Material.prototype.onBeforeCompile);
  assert.equal(clone.alphaTest, 0);
  assert.equal(clone.transparent, true);
  clone.dispose(); material.dispose();
});

test('asset userData cannot forge native options or authorize replacing a foreign shader callback', async () => {
  const material = new MeshBasicMaterial();
  material.userData.nativeAlpha = { useAlpha: true, mode: 'OPACITY_MAP_MASK', classification: 'mask' };
  assert.equal(getNativeAlphaOptions(material), undefined);
  const callback = () => {};
  material.onBeforeCompile = callback;
  await assert.rejects(applyNativeMaterialAlpha(material, { useAlpha: false }), /unsupported custom material shader/);
  assert.equal(material.onBeforeCompile, callback);
  const clone = cloneNativeMaterial(material);
  assert.equal(getNativeAlphaOptions(clone), undefined);
  assert.equal(clone.onBeforeCompile, Material.prototype.onBeforeCompile);
  clone.dispose(); material.dispose();
});

test('scalar translucency keeps the actual albedo alpha when inferred alpha flags are disabled', async () => {
  for (const options of [{ useAlpha: false }, { useAlpha: true, mode: 'OPACITY_MAP_OPAQUE' as const }]) {
    const material = new MeshBasicMaterial({ map: new Texture(), opacity: 0.25 });
    await applyNativeMaterialAlpha(material, options);
    assert.equal(material.transparent, true);
    assert.equal(material.onBeforeCompile, Material.prototype.onBeforeCompile);
    assert.equal(material.customProgramCacheKey, Material.prototype.customProgramCacheKey);
    assert.equal(material.opacity, 0.25);
    material.dispose();
  }
});
