// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { Quaternion, Vector3 } from 'three';
import { assetDependency, constrainCamera, entityCollider, entityTransform, parseMaterialData, poseRecord, quaternion, resolveCollision, unsupportedEntityEffects, vector } from './world-data';
import type { Entity } from './world-data';

test('world API positions are not transformed twice by entity parents', () => {
  const parent: Entity = { id: 'parent', type: 'Box', position: { x: 100, y: 0, z: 0 } };
  const child: Entity = { id: 'child', type: 'Box', parentID: 'parent', position: { x: 102, y: 1, z: 3 } };
  assert.equal(entityTransform(child, new Map([['parent', parent]])).position.x, 102);
});
test('local-only snapshots compose parent quaternion and translation', () => {
  const parent: Entity = { id: 'parent', type: 'Box', position: { x: 10, y: 0, z: 0 }, rotation: { x: 0, y: Math.SQRT1_2, z: 0, w: Math.SQRT1_2 } };
  const child: Entity = { id: 'child', type: 'Box', parentID: 'parent', localPosition: { x: 0, y: 0, z: -2 } };
  const position = entityTransform(child, new Map([['parent', parent]])).position;
  assert.ok(Math.abs(position.x - 8) < 0.000001);
  assert.ok(Math.abs(position.z) < 0.000001);
});
test('registration point moves collision volume with visual geometry', () => {
  const entity: Entity = { id: 'box', type: 'Box', position: { x: 0, y: 0, z: 0 }, dimensions: { x: 2, y: 2, z: 2 }, registrationPoint: { x: 0, y: 0, z: 0 } };
  assert.deepEqual({ ...entityCollider(entity, new Map())?.center }, { x: 1, y: 1, z: 1 });
});
test('floor collision supports avatar capsule without a fabricated world floor', () => {
  const floor = entityCollider({ id: 'floor', type: 'Box', position: { x: 0, y: -0.5, z: 0 }, dimensions: { x: 20, y: 1, z: 20 } }, new Map())!;
  const collision = resolveCollision({ x: 0, y: 0.8, z: 0 }, floor)!;
  assert.ok(Math.abs(collision.position.y - 0.85001) < 0.000001);
  assert.equal(collision.normal.y, 1);
  assert.equal(resolveCollision({ x: 0, y: 2, z: 0 }, floor), undefined);
});
test('rotated walls resolve collision along their world surface normal', () => {
  const wall = entityCollider({ id: 'wall', type: 'Box', position: { x: 0, y: 1, z: 0 }, dimensions: { x: 0.2, y: 3, z: 6 }, rotation: { x: 0, y: Math.sin(Math.PI / 8), z: 0, w: Math.cos(Math.PI / 8) } }, new Map())!;
  const collision = resolveCollision({ x: 0.1, y: 1, z: 0 }, wall)!;
  assert.ok(Math.abs(collision.normal.x - Math.SQRT1_2) < 0.000001);
  assert.ok(Math.abs(collision.normal.z + Math.SQRT1_2) < 0.000001);
});
test('collisionless visual entities do not trap walking avatars', () => {
  assert.equal(entityCollider({ id: 'box', type: 'Box', collisionless: true }, new Map()), undefined);
});
test('pitched third-person camera stays above real floors and outside rotated walls', () => {
  const floor = entityCollider({ id: 'floor', type: 'Box', position: { x: 0, y: -0.25, z: 0 }, dimensions: { x: 20, y: 0.5, z: 20 } }, new Map())!;
  const anchor = new Vector3(0, 1.5, 0);
  const desired = anchor.clone().add(new Vector3(0, 0.3, 3).applyQuaternion(new Quaternion().setFromAxisAngle(new Vector3(1, 0, 0), 1.4)));
  assert.ok(desired.y < 0, 'unobstructed camera boom would enter the actual floor');
  const camera = constrainCamera(anchor, desired, [floor]);
  assert.ok(Math.abs(camera.y - 0.08) < 0.000001);
  const wall = entityCollider({ id: 'wall', type: 'Box', position: { x: 1, y: 1.5, z: 1 }, dimensions: { x: 3, y: 3, z: 0.2 }, rotation: { x: 0, y: Math.sin(Math.PI / 8), z: 0, w: Math.cos(Math.PI / 8) } }, new Map())!;
  const clipped = constrainCamera(anchor, { x: 3, y: 1.5, z: 3 }, [wall]);
  const local = clipped.clone().sub(vector(wall.center)).applyQuaternion(quaternion(wall.rotation).invert());
  assert.ok(Math.abs(Math.abs(local.z) - 0.18) < 0.000001);
  assert.deepEqual(constrainCamera(anchor, desired, []).toArray(), desired.toArray(), 'empty domains do not invent camera barriers');
});
test('ATP paths and HTTPS dependencies retain source hierarchy', () => {
  assert.equal(assetDependency('atp:/models/room.gltf', '../textures/wall.png'), 'atp:/textures/wall.png');
  assert.equal(assetDependency('https://example.test/models/room.gltf', 'wall.png'), 'https://example.test/models/wall.png');
  assert.equal(assetDependency('atp:/models/room.gltf', 'https://example.test/wall.png'), 'https://example.test/wall.png');
});
test('material definition accepts native single and multi-material JSON', () => {
  assert.deepEqual(parseMaterialData('{"materials":{"albedo":[1,0,0],"roughness":0.3}}')[0].albedo, [1, 0, 0]);
  assert.equal(parseMaterialData('{"materials":[{"name":"wall"}]}')[0].name, 'wall');
  assert.throws(() => parseMaterialData('{}'));
});
test('malformed orientation cannot poison render or collision transforms', () => {
  assert.equal(quaternion({ x: 0, y: 0, z: 0, w: 0 }).w, 1);
  assert.equal(quaternion({ x: NaN, y: 0, z: 0, w: 1 }).w, 1);
});
test('avatar wire pose retains named quaternion components after JSON serialization', () => {
  const position = new Vector3(1, 2, 3), orientation = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), Math.PI / 2);
  const actual = JSON.parse(JSON.stringify(poseRecord(position, orientation, new Vector3(4, 5, 6))));
  assert.deepEqual(actual.position, { x: 1, y: 2, z: 3 });
  assert.deepEqual(Object.keys(actual.orientation), ['x', 'y', 'z', 'w']);
  assert.ok(Math.abs(actual.orientation.y - Math.SQRT1_2) < 0.000001);
  assert.deepEqual(actual.velocity, { x: 4, y: 5, z: 6 });
});
test('unsupported effects describe enabled native zone features and actual procedural shaders', () => {
  assert.deepEqual(unsupportedEntityEffects({ id: 'zone', type: 'Zone', skyboxMode: 'enabled', hazeMode: 'enabled' }), ['zone skybox', 'zone haze']);
  assert.deepEqual(unsupportedEntityEffects({ id: 'zone', type: 'Zone', skyboxMode: 'inherit', hazeMode: 'disabled', skybox: { url: 'atp:/stored-but-unused.jpg' } }), []);
  assert.deepEqual(unsupportedEntityEffects({ id: 'zone', type: 'Zone', userData: '{"ProceduralEntity":{"fragmentShaderURL":"https://example.test/shader.fs"}}' }), ['procedural shader']);
  assert.deepEqual(unsupportedEntityEffects({ id: 'box', type: 'Box', userData: '{"ProceduralEntity":{}}' }), []);
  assert.deepEqual(unsupportedEntityEffects({ id: 'box', type: 'Box', userData: '{"browserInteraction":"toggleColor"}' }), []);
});
