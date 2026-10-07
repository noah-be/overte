// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BackSide, DoubleSide, FrontSide, MeshBasicMaterial, ShaderMaterial } from 'three';
import { applyNativeDefaultCull, type NativeCullSource } from './native-default-cull';

test('native default material, solid primitive and FBX paths select BACK once', () => {
  for (const source of ['native-material', 'solid-primitive', 'fbx-import'] as const) {
    const material = new MeshBasicMaterial({ side: DoubleSide });
    applyNativeDefaultCull(material, source);
    assert.equal(material.side, FrontSide);
    assert.equal(material.forceSinglePass, false);
    const version = material.version;
    applyNativeDefaultCull(material, source);
    assert.equal(material.version, version);
    material.dispose();
  }
});

test('Image and Text background are explicitly double-sided, flat approximations and GLTF retain prior state', () => {
  for (const source of ['image', 'text-background'] as const) {
    const material = new MeshBasicMaterial({ transparent: true, side: FrontSide });
    applyNativeDefaultCull(material, source);
    assert.equal(material.side, DoubleSide); assert.equal(material.forceSinglePass, true); assert.equal(material.depthWrite, false);
  }
  for (const source of ['gltf-import', 'unsupported-flat-shape'] as const) {
    const material = new MeshBasicMaterial({ transparent: true, side: BackSide });
    const version = material.version;
    applyNativeDefaultCull(material, source);
    assert.equal(material.side, BackSide); assert.equal(material.depthWrite, true); assert.equal(material.version, version);
  }
});

test('recognized explicit culling wins over each default; unknown modes preserve every prior state', () => {
  const sources: NativeCullSource[] = ['native-material', 'solid-primitive', 'fbx-import', 'gltf-import', 'image', 'text-background', 'unsupported-flat-shape'];
  for (const source of sources) for (const [mode, side] of [['CULL_NONE', DoubleSide], ['CULL_FRONT', BackSide], ['CULL_BACK', FrontSide]] as const) {
    const material = new MeshBasicMaterial(); applyNativeDefaultCull(material, source, mode); assert.equal(material.side, side);
  }
  for (const value of [null, 0, false, 'cull_back', 'CULL_FUTURE', { cullFaceMode: 'CULL_BACK' }]) {
    const material = new MeshBasicMaterial({ side: DoubleSide, transparent: true });
    const version = material.version;
    applyNativeDefaultCull(material, 'native-material', value);
    assert.equal(material.side, DoubleSide); assert.equal(material.depthWrite, true); assert.equal(material.forceSinglePass, false); assert.equal(material.version, version);
  }
});

test('native default culling cannot authorize foreign/custom shader callbacks', () => {
  const custom = new MeshBasicMaterial(); custom.onBeforeCompile = () => {};
  assert.throws(() => applyNativeDefaultCull(custom, 'fbx-import'), /unsupported custom/);
  assert.throws(() => applyNativeDefaultCull(new ShaderMaterial(), 'native-material'), /unsupported custom/);
});
