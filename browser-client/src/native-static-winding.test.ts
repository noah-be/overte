// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BufferAttribute, BufferGeometry, Group, InstancedMesh, Mesh, MeshBasicMaterial, SkinnedMesh } from 'three';
import { ModelResources } from './model-resources';
import { prepareNativeStaticWinding } from './native-static-winding';

function triangle(indexed = true): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([-1,-1,0, 1,-1,0, 0,1,0]), 3));
  geometry.setAttribute('normal', new BufferAttribute(new Float32Array([0,0,1, 0,0,1, 0,0,1]), 3));
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array([255,0,0, 0,255,0, 0,0,255]), 3, true));
  if (indexed) geometry.setIndex(new BufferAttribute(new Uint16Array([0,1,2]), 1));
  geometry.addGroup(0,3,0); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

test('full mirrored parent transform reverses owned indices without altering authored attributes or material', async () => {
  const parent = new Group(), root = new Group(), source = triangle(), material = new MeshBasicMaterial();
  const mesh = new Mesh(source, material); root.add(mesh); parent.add(root); parent.scale.set(-1,2,.5);
  const scope = await prepareNativeStaticWinding(root);
  assert.equal(scope.convertedMeshes, 1); assert.equal(scope.createdGeometries, 1);
  assert.notEqual(mesh.geometry, source); assert.deepEqual(Array.from(mesh.geometry.index!.array), [1,0,2]);
  assert.deepEqual(Array.from(source.index!.array), [0,1,2]); assert.equal(mesh.material, material);
  for (const name of ['position','normal','color']) assert.equal(mesh.geometry.getAttribute(name), source.getAttribute(name));
  assert.deepEqual(mesh.geometry.groups, source.groups); assert.notEqual(mesh.geometry.groups, source.groups);
  assert.deepEqual(mesh.geometry.boundingBox, source.boundingBox); assert.notEqual(mesh.geometry.boundingBox, source.boundingBox);
  assert.equal(await prepareNativeStaticWinding(root), scope); scope.assertStatic();
  parent.scale.x = 1; assert.throws(() => scope.assertStatic(), /parity or geometry changed/);
});

test('shared positive and two negative meshes preserve original resource and deduplicate reversed clone', async () => {
  const root = new Group(), source = triangle(), positive = new Mesh(source), negative = new Mesh(source), another = new Mesh(source);
  negative.scale.x = -1; another.scale.z = -2; root.add(positive,negative,another);
  const resources = new ModelResources(); resources.capture(root);
  let originalDisposals = 0, cloneDisposals = 0; source.addEventListener('dispose', () => originalDisposals++);
  const scope = await prepareNativeStaticWinding(root);
  negative.geometry.addEventListener('dispose', () => cloneDisposals++);
  assert.equal(scope.convertedMeshes, 2); assert.equal(scope.createdGeometries, 1);
  assert.equal(negative.geometry, another.geometry); assert.equal(positive.geometry, source);
  resources.capture(root); resources.releaseKeeping(root); assert.equal(originalDisposals, 0); assert.equal(cloneDisposals, 0);
  root.remove(positive); resources.releaseKeeping(root); assert.equal(originalDisposals, 1);
  resources.releaseKeeping(); resources.releaseKeeping(); assert.equal(originalDisposals, 1); assert.equal(cloneDisposals, 1);
});

test('nonindexed static triangle gets reversed owned index, retaining attribute order', async () => {
  const source = triangle(false), mesh = new Mesh(source); mesh.scale.y = -1;
  await prepareNativeStaticWinding(mesh);
  assert.equal(source.index, null); assert.deepEqual(Array.from(mesh.geometry.index!.array), [1,0,2]);
  assert.equal(mesh.geometry.getAttribute('position'), source.getAttribute('position'));
});

test('positive and doubly mirrored objects retain original winding', async () => {
  const root = new Group(), positive = new Mesh(triangle()), double = new Mesh(triangle()); double.scale.set(-1,-2,1); root.add(positive,double);
  const sources = [positive.geometry,double.geometry]; const scope = await prepareNativeStaticWinding(root);
  assert.equal(scope.convertedMeshes, 0); assert.equal(positive.geometry, sources[0]); assert.equal(double.geometry, sources[1]);
});

test('mirrored skinned/instanced and unaligned shapes are explicitly unsupported', async () => {
  const root = new Group(), skin = new SkinnedMesh(triangle()), instances = new InstancedMesh(triangle(),new MeshBasicMaterial(),1), unaligned = new Mesh(triangle());
  for (const mesh of [skin,instances,unaligned]) mesh.scale.x = -1;
  unaligned.geometry.setDrawRange(1,2); root.add(skin,instances,unaligned);
  const original = [skin.geometry,instances.geometry,unaligned.geometry]; const warnings: string[] = [];
  const scope = await prepareNativeStaticWinding(root, {onUnsupported: warning => warnings.push(warning)});
  assert.equal(scope.convertedMeshes, 0); assert.equal(scope.unsupportedMeshes, 3); assert.equal(warnings.length, 1);
  assert.deepEqual([skin.geometry,instances.geometry,unaligned.geometry], original);
});

test('invalid budgets, transform and index references fail before mutation', async () => {
  for (const budget of [NaN,Infinity,0,-1,1.5,5]) {
    const source = triangle(), mesh = new Mesh(source); mesh.scale.x = -1;
    await assert.rejects(prepareNativeStaticWinding(mesh,{maxIndexBytes:budget}), /budget/); assert.equal(mesh.geometry, source);
  }
  const source = triangle(), invalid = new Mesh(source); invalid.scale.x = -1; source.setIndex([0,1,9]);
  await assert.rejects(prepareNativeStaticWinding(invalid), /invalid vertex/); assert.equal(invalid.geometry,source);
  invalid.scale.x = NaN; await assert.rejects(prepareNativeStaticWinding(invalid), /finite world transform/);
});

test('pre-abort and mid-read abort preserve all source geometries transactionally', async () => {
  const controller = new AbortController(); controller.abort(); const first = new Mesh(triangle()); first.scale.x = -1;
  await assert.rejects(prepareNativeStaticWinding(first,{signal:controller.signal}), {name:'AbortError'});
  const active = new AbortController(), root = new Group(), a = new Mesh(triangle()), b = new Mesh(triangle());
  a.scale.x = b.scale.x = -1; root.add(a,b); const originals = [a.geometry,b.geometry];
  const index = b.geometry.index!, read = index.getX.bind(index); index.getX = i => {active.abort(); return read(i);};
  await assert.rejects(prepareNativeStaticWinding(root,{signal:active.signal}), {name:'AbortError'});
  assert.equal(a.geometry,originals[0]); assert.equal(b.geometry,originals[1]);
});

test('source mutation during preparation and graph mutation after preparation fail closed', async () => {
  const root = new Group(), mesh = new Mesh(triangle()), replacement = triangle(); mesh.scale.x = -1; root.add(mesh);
  const original = mesh.geometry, index = original.index!, read = index.getX.bind(index); index.getX = i => {mesh.geometry = replacement; return read(i);};
  await assert.rejects(prepareNativeStaticWinding(root), /geometry changed during/); assert.equal(mesh.geometry,replacement);
  const stable = new Group(), a = new Mesh(triangle()); stable.add(a); const scope = await prepareNativeStaticWinding(stable);
  stable.add(new Mesh(triangle())); assert.throws(() => scope.assertStatic(), /graph changed/);
});
