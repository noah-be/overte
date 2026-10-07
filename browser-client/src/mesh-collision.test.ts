// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, Group, Mesh, MeshBasicMaterial, PlaneGeometry, Vector3 } from 'three';
import { MeshCollision } from './mesh-collision';

test('mesh collision supports actual floors under translation, rotation and nonuniform scale', () => {
  const root = new Group(); root.position.set(154, -98, -398);
  const floor = new Mesh(new PlaneGeometry(1, 1), new MeshBasicMaterial());
  floor.rotation.x = -Math.PI / 2; floor.scale.set(8, 4, 1); root.add(floor);
  const collision = new MeshCollision(root);
  const position = new Vector3(154, -97.2, -398);
  const normal = collision.resolve(position);
  assert.ok(normal && normal.y > 0.99);
  assert.ok(Math.abs(position.y - (-98 + 0.85)) < 0.0001);
  const embeddedSpawn = new Vector3(154, -97.8, -398);
  assert.ok(collision.resolve(embeddedSpawn)?.y && Math.abs(embeddedSpawn.y - (-98 + 0.85)) < 0.0001);
  assert.equal(collision.resolve(new Vector3(170, -97.2, -398)), undefined);
  collision.dispose(); floor.geometry.dispose(); floor.material.dispose();
});

test('a hollow building does not collide with its empty bounding volume', () => {
  const root = new Group();
  const wall = new Mesh(new BoxGeometry(0.1, 4, 5), new MeshBasicMaterial());
  wall.position.x = -3; root.add(wall);
  const other = wall.clone(); other.position.x = 3; root.add(other);
  const collision = new MeshCollision(root);
  const position = new Vector3(0, 1, 0);
  assert.equal(collision.resolve(position), undefined);
  assert.deepEqual(position.toArray(), [0, 1, 0]);
  const nearWall = new Vector3(2.8, 1, 0);
  assert.ok(collision.resolve(nearWall));
  assert.ok(nearWall.x < 2.7);
  collision.dispose(); wall.geometry.dispose(); wall.material.dispose();
});

test('generated renderer batches never add extra collision triangles during a transform rebuild', () => {
  const root = new Group();
  const original = new Mesh(new PlaneGeometry(8,8),new MeshBasicMaterial());
  original.rotation.x = -Math.PI / 2; original.visible = false; root.add(original);
  const generated = new Mesh(new BoxGeometry(2,2,2),new MeshBasicMaterial());
  generated.position.y = 3; generated.userData.browserStaticBatch = true; root.add(generated);
  root.position.set(10,20,30);
  const collision = new MeshCollision(root), floor = new Vector3(10,20.8,30);
  assert.ok(collision.resolve(floor)?.y);
  assert.equal(collision.resolve(new Vector3(10,23,30)),undefined);
  collision.dispose(); original.geometry.dispose(); original.material.dispose(); generated.geometry.dispose(); generated.material.dispose();
});
