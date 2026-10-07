// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BackSide, BoxGeometry, BufferAttribute, DoubleSide, FrontSide, InstancedMesh, Mesh, MeshBasicMaterial, Object3D, ShaderMaterial, Texture } from 'three';
import { applyNativeMaterialAlpha, hasNativeAlphaShader } from './native-alpha-material';
import { applyNativeModelRenderState, applyNativeRenderState, cloneNativeMaterialForGeometry, nativeCullFaceMode } from './native-render-state';
import { inspectStaticModel } from './static-model-batch';

test('native cull enum maps front/back/none without inventing a default on imported materials', () => {
  for (const [mode, side] of [['CULL_NONE', DoubleSide], ['CULL_FRONT', BackSide], ['CULL_BACK', FrontSide]] as const) {
    const material = new MeshBasicMaterial({ transparent: true });
    applyNativeRenderState(material, { cullFaceMode: mode });
    assert.equal(material.side, side); assert.equal(material.forceSinglePass, side === DoubleSide); assert.equal(material.depthWrite, false);
  }
  const imported = new MeshBasicMaterial({ side: BackSide }); applyNativeRenderState(imported); assert.equal(imported.side, BackSide);
  assert.equal(nativeCullFaceMode('CULL_BACK'), 'CULL_BACK'); assert.equal(nativeCullFaceMode('__proto__'), undefined);
});
test('native alpha masking keeps depth writes and exact owned shader hooks; blend disables writes', async () => {
  const material = new MeshBasicMaterial({ map: new Texture(), side: DoubleSide });
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .3 });
  const compile = material.onBeforeCompile, key = material.customProgramCacheKey;
  applyNativeRenderState(material);
  assert.equal(material.transparent, false); assert.equal(material.depthWrite, true); assert.equal(material.alphaTest, .3);
  assert.equal(material.onBeforeCompile, compile); assert.equal(material.customProgramCacheKey, key); assert.equal(hasNativeAlphaShader(material), true);
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' }); applyNativeRenderState(material);
  assert.equal(material.transparent, true); assert.equal(material.depthWrite, false);
});
test('native render-state application is idempotent and rejects foreign hooks without changing state', () => {
  const material = new MeshBasicMaterial({ side: DoubleSide, transparent: true }); applyNativeRenderState(material);
  const version = material.version; for (let i = 0; i < 20; i++) applyNativeRenderState(material); assert.equal(material.version, version);
  material.onBeforeCompile = () => {}; material.userData.nativeAlpha = { classification: 'mask' };
  assert.throws(() => applyNativeRenderState(material, { cullFaceMode: 'CULL_BACK' }), /unsupported custom/);
  assert.equal(material.side, DoubleSide); assert.equal(material.depthWrite, false); assert.equal(material.version, version);
  assert.throws(() => applyNativeRenderState(new ShaderMaterial()), /unsupported custom/);
});
test('native render state preserves opaque mask batching and excludes blends and instances', async () => {
  const geometry = new BoxGeometry(), material = new MeshBasicMaterial({ map: new Texture(), side: DoubleSide });
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK' }); applyNativeRenderState(material);
  const root = new Object3D(); root.add(new Mesh(geometry, material), new Mesh(geometry, material));
  assert.equal(inspectStaticModel(root).savedDrawCalls, 1);
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' }); applyNativeRenderState(material);
  assert.equal(inspectStaticModel(root).sourceDrawCalls, 0);
  const instances = new Object3D(); instances.add(new InstancedMesh(geometry, material, 2));
  assert.equal(inspectStaticModel(instances).sourceDrawCalls, 0);
  material.dispose(); geometry.dispose();
});
test('native material override preserves authored geometry colors without leaking the flag across neighboring meshes', async () => {
  const material = new MeshBasicMaterial({ map: new Texture() }); await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK' });
  const colored = new BoxGeometry(); colored.setAttribute('color', new BufferAttribute(new Float32Array(colored.getAttribute('position').count * 3).fill(.5), 3));
  const plain = new BoxGeometry(), replacement = cloneNativeMaterialForGeometry(material, colored), neighbor = cloneNativeMaterialForGeometry(material, plain);
  assert.equal(replacement.vertexColors, true); assert.equal(neighbor.vertexColors, false); assert.equal(material.vertexColors, false);
  assert.equal(hasNativeAlphaShader(replacement), true); assert.equal(hasNativeAlphaShader(neighbor), true);
  assert.equal(replacement.map, material.map); assert.equal(replacement.alphaTest, material.alphaTest);
  replacement.dispose(); neighbor.dispose(); material.dispose(); colored.dispose(); plain.dispose();
});
test('native imported-model traversal deduplicates shared material state and preserves imported culling', () => {
  const material = new MeshBasicMaterial({ transparent: true, side: DoubleSide }), geometry = new BoxGeometry(), root = new Object3D();
  root.add(new Mesh(geometry, material), new Mesh(geometry, [material, material])); applyNativeModelRenderState(root);
  const version = material.version; applyNativeModelRenderState(root); assert.equal(material.version, version);
  assert.equal(material.side, DoubleSide); assert.equal(material.forceSinglePass, true); assert.equal(material.depthWrite, false);
  material.dispose(); geometry.dispose();
});
