// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BufferGeometry, Group, Line, Mesh, MeshBasicMaterial, Texture } from 'three';
import { ModelResources } from '../src/model-resources';

function disposals(resource: BufferGeometry | MeshBasicMaterial | Texture): () => number {
  let count = 0; resource.addEventListener('dispose', () => count++); return () => count;
}

test('replaced FST materials release once while actual Three clones retain their shared textures and geometry', () => {
  const model = new Group(), geometry = new BufferGeometry(), texture = new Texture(), obsoleteTexture = new Texture();
  const old = new MeshBasicMaterial({ map: texture, alphaMap: obsoleteTexture });
  const mesh = new Mesh(geometry, old); model.add(mesh, new Line(geometry, old));
  const ledger = new ModelResources(); ledger.capture(model);
  const replacement = old.clone(); replacement.alphaMap = null;
  model.traverse(object => { if (object instanceof Mesh || object instanceof Line) object.material = replacement; });
  ledger.capture(model);
  const oldCount = disposals(old), newCount = disposals(replacement), geometryCount = disposals(geometry);
  const textureCount = disposals(texture), obsoleteCount = disposals(obsoleteTexture);
  ledger.releaseKeeping(model); ledger.releaseKeeping(model);
  assert.equal(oldCount(), 1); assert.equal(obsoleteCount(), 1);
  assert.equal(newCount(), 0); assert.equal(geometryCount(), 0); assert.equal(textureCount(), 0);
  ledger.releaseKeeping(); ledger.releaseKeeping();
  assert.equal(oldCount(), 1); assert.equal(newCount(), 1); assert.equal(geometryCount(), 1); assert.equal(textureCount(), 1); assert.equal(obsoleteCount(), 1);
});

test('mapping failure releases removed and newly attached resources and preserves the exact original thrown error', () => {
  const model = new Group(), originalGeometry = new BufferGeometry(), original = new MeshBasicMaterial({ map: new Texture() });
  const mesh = new Mesh(originalGeometry, original); model.add(mesh);
  const ledger = new ModelResources(); ledger.capture(model);
  const replacement = new MeshBasicMaterial({ map: new Texture() }), clone = replacement.clone(), newGeometry = new BufferGeometry();
  ledger.captureMaterial(replacement); mesh.material = clone; mesh.geometry = newGeometry;
  const all = [originalGeometry, original, original.map!, replacement, clone, replacement.map!, newGeometry];
  const counts = all.map(disposals);
  originalGeometry.addEventListener('dispose', () => { throw Error('A cleanup listener failed'); });
  const failure = new Error('Actual FST material-map response failed');
  assert.throws(() => {
    try { throw failure; } finally { ledger.capture(model); ledger.releaseKeeping(); }
  }, error => error === failure);
  ledger.releaseKeeping(); assert.deepEqual(counts.map(count => count()), all.map(() => 1));
});

test('late textures on a captured material are owned even when loading fails before the material reaches a model', () => {
  const ledger = new ModelResources(), material = new MeshBasicMaterial(); ledger.captureMaterial(material);
  const texture = new Texture(); material.map = texture;
  const materialCount = disposals(material), textureCount = disposals(texture);
  ledger.releaseKeeping(); ledger.releaseKeeping();
  assert.equal(materialCount(), 1); assert.equal(textureCount(), 1);
});

test('retained materials in arrays and line resources are discovered without trusting asset userData', () => {
  const ledger = new ModelResources(), model = new Group(), texture = new Texture();
  const first = new MeshBasicMaterial({ map: texture }), second = new MeshBasicMaterial({ alphaMap: texture });
  const geometry = new BufferGeometry(), mesh = new Mesh(geometry, [first, second]), line = new Line(geometry, second);
  model.add(mesh, line); model.userData.material = new MeshBasicMaterial({ map: new Texture() });
  const unrelatedCount = disposals(model.userData.material);
  ledger.capture(model); mesh.material = [second];
  const firstCount = disposals(first), secondCount = disposals(second), textureCount = disposals(texture);
  ledger.releaseKeeping(model);
  assert.equal(firstCount(), 1); assert.equal(secondCount(), 0); assert.equal(textureCount(), 0); assert.equal(unrelatedCount(), 0);
  ledger.releaseKeeping(); assert.equal(secondCount(), 1); assert.equal(textureCount(), 1); assert.equal(unrelatedCount(), 0);
});

test('an ImageBitmap shared by distinct actual Three textures closes only after every retained texture releases it', () => {
  const previous = globalThis.ImageBitmap;
  class TestBitmap { closed = 0; close() { this.closed++; } }
  Object.defineProperty(globalThis, 'ImageBitmap', { configurable: true, value: TestBitmap });
  try {
    const bitmap = new TestBitmap(), cubeBitmap = new TestBitmap();
    const oldTexture = new Texture(bitmap as unknown as ImageBitmap), retainedTexture = oldTexture.clone();
    const cubeTexture = new Texture(); cubeTexture.image = [cubeBitmap, bitmap, bitmap];
    const old = new MeshBasicMaterial({ map: oldTexture, alphaMap: cubeTexture }), replacement = new MeshBasicMaterial({ map: retainedTexture });
    const model = new Group(), mesh = new Mesh(new BufferGeometry(), old); model.add(mesh);
    const ledger = new ModelResources(); ledger.capture(model); ledger.captureMaterial(replacement); mesh.material = replacement; ledger.capture(model);
    ledger.releaseKeeping(model); ledger.releaseKeeping(model);
    assert.equal(cubeBitmap.closed, 1); assert.equal(bitmap.closed, 0);
    ledger.releaseKeeping(); ledger.releaseKeeping(); assert.equal(bitmap.closed, 1); assert.equal(cubeBitmap.closed, 1);
  } finally {
    if (previous) Object.defineProperty(globalThis, 'ImageBitmap', { configurable: true, value: previous });
    else delete (globalThis as { ImageBitmap?: unknown }).ImageBitmap;
  }
});
