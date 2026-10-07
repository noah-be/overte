// SPDX-License-Identifier: Apache-2.0
// Actual World animation/physics methods with presentation disabled. No GPU claim.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Group, PerspectiveCamera, Vector2, Vector3 } from 'three';
import { BrowserWorld } from '../src/world';
import { SimulationClock } from '../src/simulation-clock';
import { InitialSurfaceWait } from '../src/initial-surface-wait';
import { entityCollider } from '../src/world-data';

function world() {
  const context = Object.create(BrowserWorld.prototype);
  Object.assign(context, {
    disposed: false, enabled: true, simulationClock: new SimulationClock(), initialSurfaceWait: new InitialSurfaceWait(),
    metrics: { sample() {} }, pendingModelColliders: [], objects: new Map(),
    keys: new Set(['KeyW']), touchMove: new Vector2(), yaw: 0, pitch: 0,
    position: new Vector3(0, .85, 0), spawn: new Vector3(0, .85, 0),
    velocity: new Vector3(), grounded: false, meshCollisions: new Map(),
    colliders: [entityCollider({ id: 'floor', type: 'Box',
      position: { x: 0, y: -.1, z: 0 }, dimensions: { x: 100, y: .2, z: 100 } }, new Map())!],
    lastPose: 0, lastLightSelection: 0, options: { onStatus() {}, onPose() {} },
    camera: new PerspectiveCamera(), thirdPerson: false, self: new Group(),
    avatars: new Map(), localLights: new Set(), pointSlots: [], spotSlots: [],
    presentationEnabled: false,
  });
  return context;
}

test('actual World animation moves the same distance and maintains floor collision at 60, 30, 10 and 4 FPS', t => {
  const previous = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  t.after(() => { if (previous) globalThis.requestAnimationFrame = previous; else delete (globalThis as Partial<typeof globalThis>).requestAnimationFrame; });
  for (const fps of [60, 30, 10, 4]) {
    const context = world();
    for (let frame = 0; frame <= fps * 4; frame++) context.animate(1000 + frame * 1000 / fps);
    assert.ok(Math.abs(context.position.z + 11.2) < 1e-8, `${fps} FPS preserves 2.8 m/s`);
    assert.ok(Math.abs(context.position.y - .85001) < 1e-8, `${fps} FPS preserves actual floor support`);
    assert.equal(context.grounded, true);
  }
});

test('low-cadence actual World collision does not tunnel through a thin wall', t => {
  const previous = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  t.after(() => { if (previous) globalThis.requestAnimationFrame = previous; else delete (globalThis as Partial<typeof globalThis>).requestAnimationFrame; });
  const context = world();
  context.colliders.push(entityCollider({ id: 'wall', type: 'Box',
    position: { x: 0, y: 2, z: -2 }, dimensions: { x: 10, y: 4, z: .02 } }, new Map())!);
  for (let frame = 0; frame <= 16; frame++) context.animate(1000 + frame * 250);
  assert.ok(context.position.z > -1.71001 && context.position.z < -1.7099);
  assert.ok(Math.abs(context.position.y - .85001) < 1e-8);
});

test('actual World jump is independent of render cadence and lands on real collision', t => {
  const previous = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  t.after(() => { if (previous) globalThis.requestAnimationFrame = previous; else delete (globalThis as Partial<typeof globalThis>).requestAnimationFrame; });
  const results: number[] = [];
  for (const fps of [60, 4]) {
    const context = world(); context.keys.clear(); context.keys.add('Space'); context.grounded = true;
    context.animate(1000); context.animate(1250); context.keys.clear();
    for (let time = 1250 + 1000 / fps; time < 2000 - .01; time += 1000 / fps) context.animate(time);
    context.animate(2000); results.push(context.position.y);
    for (let time = 2000 + 1000 / fps; time < 3000 - .01; time += 1000 / fps) context.animate(time);
    context.animate(3000); assert.ok(Math.abs(context.position.y - .85001) < 1e-8);
  }
  assert.ok(Math.abs(results[0] - results[1]) < 1e-8);
});

test('authoritative spawn resets accumulated elapsed time before the next animation', t => {
  const previous = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  t.after(() => { if (previous) globalThis.requestAnimationFrame = previous; else delete (globalThis as Partial<typeof globalThis>).requestAnimationFrame; });
  const context = world(); context.animate(1000); context.animate(1100);
  context.setSpawn({ x: 0, y: .85, z: 0 }); context.animate(10000);
  assert.equal(context.position.z, 0);
  context.animate(10250); assert.ok(Math.abs(context.position.z + .7) < 1e-8);
});
