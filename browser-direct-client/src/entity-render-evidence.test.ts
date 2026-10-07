// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { observeEntityRendering } from './entity-render-evidence';

test('actual participant body bounds and draw counts exclude a large avatar label', async () => {
  const root = new THREE.Group(), camera = new THREE.PerspectiveCamera();
  const body = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 1), new THREE.MeshBasicMaterial());
  const label = new THREE.Mesh(new THREE.BoxGeometry(100, 100, 1), new THREE.MeshBasicMaterial());
  label.position.x = 20; root.add(body, label); root.userData.avatarLabel = label;
  const original = body.onAfterRender;
  const observing = observeEntityRendering(new Map([['peer', { id: 'peer', type: 'Avatar' }]]),
    new Map([['peer', root]]), camera, ['peer'], new AbortController().signal, () => {}, 100);
  const invoke = (mesh: THREE.Mesh) => mesh.onAfterRender(
    {} as THREE.WebGLRenderer, new THREE.Scene(), camera, mesh.geometry, mesh.material as THREE.Material, new THREE.Group());
  invoke(body); invoke(label);
  const { entities: [value] } = await observing;
  assert.deepEqual(value.bounds, { min: { x: -0.5, y: -1, z: -0.5 }, max: { x: 0.5, y: 1, z: 0.5 } });
  assert.equal(value.meshes, 1); assert.equal(value.submittedDraws, 1); assert.equal(value.submittedTriangles, 12);
  assert.equal(body.onAfterRender, original);
  body.geometry.dispose(); label.geometry.dispose();
});

test('new real owner transforms and body bounds are sampled together after participant movement', async () => {
  const root = new THREE.Group(), camera = new THREE.PerspectiveCamera();
  const body = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 1), new THREE.MeshBasicMaterial());
  root.add(body); root.position.set(155, -97, -400);
  const observe = () => observeEntityRendering(new Map([['peer', { id: 'peer', type: 'Avatar' }]]),
    new Map([['peer', root]]), camera, ['peer'], new AbortController().signal, () => {}, 100);
  const before = (await observe()).entities[0];
  root.position.z -= 1;
  const after = (await observe()).entities[0];
  assert.deepEqual(before.ownerPosition, { x: 155, y: -97, z: -400 });
  assert.deepEqual(after.ownerPosition, { x: 155, y: -97, z: -401 });
  assert.equal(after.bounds!.min.z - before.bounds!.min.z, -1);
  assert.equal(after.bounds!.max.z - before.bounds!.max.z, -1);
  body.geometry.dispose(); (body.material as THREE.Material).dispose();
});
