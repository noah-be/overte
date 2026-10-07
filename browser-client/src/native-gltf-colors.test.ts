// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BufferAttribute, BufferGeometry, Float32BufferAttribute, Group, InterleavedBuffer, InterleavedBufferAttribute, Mesh, MeshBasicMaterial, Uint8BufferAttribute } from 'three';
import { normalizeNativeGltfColors, normalizeNativeGltfVertexColor } from './native-gltf-colors';

test('native COLOR_0 VEC4 discards only alpha and preserves geometry/material ownership', () => {
  const geometry = new BufferGeometry(), rgba = new Float32BufferAttribute([1, 0, 0, 0, 0, .5, 1, .25], 4);
  const position = new Float32BufferAttribute([0, 0, 0, 1, 1, 1], 3), index = new BufferAttribute(new Uint16Array([0, 1, 0]), 1);
  geometry.setAttribute('position', position); geometry.setAttribute('color', rgba); geometry.setIndex(index); geometry.addGroup(0, 3, 0);
  const material = new MeshBasicMaterial({ opacity: .5, transparent: true, vertexColors: true }), mesh = new Mesh(geometry, material);
  const original = Array.from(rgba.array);
  assert.equal(normalizeNativeGltfColors(mesh), 1);
  assert.equal(geometry.getAttribute('color').itemSize, 3);
  assert.deepEqual(Array.from(geometry.getAttribute('color').array), [1, 0, 0, 0, .5, 1]);
  assert.deepEqual(Array.from(rgba.array), original, 'original source data must remain unchanged');
  assert.equal(geometry.getAttribute('position'), position); assert.equal(geometry.index, index);
  assert.deepEqual(geometry.groups, [{ start: 0, count: 3, materialIndex: 0 }]);
  assert.equal(mesh.material, material); assert.equal(material.opacity, .5); assert.equal(material.transparent, true);
  assert.equal(normalizeNativeGltfColors(mesh), 0);
});

test('normalized unsigned-byte RGB matches native accessor float unpacking', () => {
  const geometry = new BufferGeometry(), color = new Uint8BufferAttribute([255, 128, 0, 0, 0, 64, 255, 255], 4, true);
  geometry.setAttribute('color', color); normalizeNativeGltfVertexColor(geometry);
  const rgb = geometry.getAttribute('color'); assert.equal(rgb.normalized, false);
  assert.deepEqual(Array.from(rgb.array), [1, Math.fround(128 / 255), 0, 0, Math.fround(64 / 255), 1]);
  assert.deepEqual(Array.from(color.array), [255, 128, 0, 0, 0, 64, 255, 255]);
});

test('interleaved color ignores unrelated stride components and preserves source', () => {
  const source = new InterleavedBuffer(new Float32Array([100, .1, .2, .3, 0, 200, .4, .5, .6, 1]), 5);
  const color = new InterleavedBufferAttribute(source, 4, 1);
  const geometry = new BufferGeometry(); geometry.setAttribute('color', color);
  assert.equal(normalizeNativeGltfVertexColor(geometry), true);
  assert.deepEqual(Array.from(geometry.getAttribute('color').array), [.1, .2, .3, .4, .5, .6].map(Math.fround));
  assert.equal(source.array.length, 10); assert.equal(source.array[0], 100); assert.equal(source.array[5], 200);
});

test('absent/RGB attributes are unchanged and shared RGBA geometry is converted once', () => {
  const absent = new BufferGeometry(), rgb = new BufferGeometry(), original = new Float32BufferAttribute([.2, .3, .4], 3);
  rgb.setAttribute('color', original);
  assert.equal(normalizeNativeGltfVertexColor(absent), false); assert.equal(normalizeNativeGltfVertexColor(rgb), false); assert.equal(rgb.getAttribute('color'), original);
  const shared = new BufferGeometry(); shared.setAttribute('color', new Float32BufferAttribute([1, 0, 0, 0], 4));
  const root = new Group(); root.add(new Mesh(shared), new Mesh(shared));
  assert.equal(normalizeNativeGltfColors(root), 1); assert.equal(normalizeNativeGltfColors(root), 0);
});
