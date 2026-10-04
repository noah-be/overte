// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual input listeners, fixed-step animation and collision. No GPU/domain claim.
import test, {type TestContext} from 'node:test';
import assert from 'node:assert/strict';
import {Group, PerspectiveCamera, Vector2, Vector3} from 'three';
import {BrowserWorld} from './world';
import {SimulationClock} from './simulation-clock';
import {InitialSurfaceWait} from './initial-surface-wait';
import {entityCollider} from './world-data';

function fixture(t: TestContext) {
  const listeners = new Map<string, Function>();
  const canvas = {addEventListener() {}};
  const document = {hidden: false, pointerLockElement: null, addEventListener(name: string, listener: Function) {listeners.set(name, listener);}};
  const replacements = {
    window: {addEventListener(name: string, listener: Function) {listeners.set(name, listener);}},
    document, requestAnimationFrame: () => 1,
    HTMLButtonElement: class {}, HTMLInputElement: class {}, HTMLTextAreaElement: class {}, HTMLSelectElement: class {},
  };
  for (const [name, value] of Object.entries(replacements)) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
    t.after(() => previous ? Object.defineProperty(globalThis, name, previous) : Reflect.deleteProperty(globalThis, name));
  }
  const world: any = Object.create(BrowserWorld.prototype);
  Object.assign(world, {
    abort: new AbortController(), canvas, disposed: false, enabled: true, inputEnabled: true,
    simulationClock: new SimulationClock(), initialSurfaceWait: new InitialSurfaceWait(),
    metrics: {sample() {}}, pendingModelColliders: [], objects: new Map(),
    keys: new Set(), touchMove: new Vector2(), yaw: 0, pitch: 0,
    position: new Vector3(0, .85, 0), spawn: new Vector3(0, .85, 0), velocity: new Vector3(),
    grounded: false, meshCollisions: new Map(), colliders: [entityCollider({id: 'floor', type: 'Box',
      position: {x: 0, y: -.1, z: 0}, dimensions: {x: 100, y: .2, z: 100}}, new Map())!],
    lastPose: 0, lastLightSelection: 0, options: {onStatus() {}, onPose() {}},
    camera: new PerspectiveCamera(), thirdPerson: false, self: new Group(),
    avatars: new Map(), localLights: new Set(), pointSlots: [], spotSlots: [], presentationEnabled: false,
  });
  world.installControls(); world.animate(0);
  t.after(() => world.abort.abort());
  const key = (kind: 'keydown' | 'keyup', code: string, timeStamp: number, extra = {}) =>
    listeners.get(kind)!({code, timeStamp, target: canvas, preventDefault() {}, ...extra});
  return {world, key, listeners, document};
}

test('actual key release retains bounded movement when the whole press falls between render frames', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 100); key('keyup', 'KeyW', 1300); world.animate(1400);
  assert(-world.position.z > .5, 'The actual 1200 ms WASD press must move the avatar');
  assert(-world.position.z <= .700001, 'The existing 250 ms stall clamp must remain');
  assert(Math.abs(world.position.y - .85001) < 1e-8, 'Actual floor collision remains active');
  const stopped = world.position.z; world.animate(2000); assert.equal(world.position.z, stopped);
});

test('actual keydown cannot assign idle elapsed time to a newly pressed direction', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 10000); assert.equal(world.position.z, 0);
  world.animate(10001); assert.equal(world.position.z, 0);
  key('keyup', 'KeyW', 10020);
  assert(Math.abs(world.position.z + 2.8 / 60) < 1e-8);
});

test('actual direction transition advances the previous key state before installing the next one', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 100); key('keydown', 'KeyD', 200);
  assert(Math.abs(world.position.z + .28) < 1e-8); assert.equal(world.position.x, 0);
  key('keyup', 'KeyW', 300);
  assert(Math.abs(world.position.x - .28 / Math.SQRT2) < 1e-8);
  assert(Math.abs(world.position.z + .28 + .28 / Math.SQRT2) < 1e-8);
});

test('event-driven bounded steps use the actual thin-wall collision resolver', t => {
  const {world, key} = fixture(t);
  world.colliders.push(entityCollider({id: 'wall', type: 'Box', position: {x: 0, y: 2, z: -.6},
    dimensions: {x: 10, y: 4, z: .02}}, new Map())!);
  key('keydown', 'KeyW', 100); key('keyup', 'KeyW', 1300);
  assert(world.position.z > -.31001 && world.position.z < -.3099);
});

test('actual focus and visibility revocations discard held movement without replaying it', t => {
  for (const kind of ['blur', 'visibilitychange']) {
    const {world, key, listeners, document} = fixture(t);
    key('keydown', 'KeyW', 100);
    if (kind === 'visibilitychange') document.hidden = true;
    listeners.get(kind)!(); key('keyup', 'KeyW', 1300); world.animate(10000);
    assert.equal(world.position.z, 0); assert.equal(world.keys.size, 0);
  }
});

test('actual input disable and disposal cannot flush old keys into movement', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 100); world.setInputEnabled(false); key('keyup', 'KeyW', 1300);
  assert.equal(world.position.z, 0);
  world.setInputEnabled(true); key('keydown', 'KeyW', 1400); world.disposed = true;
  key('keyup', 'KeyW', 2600); assert.equal(world.position.z, 0);
});

test('actual pending support guard still prevents movement and cannot be bypassed by release', t => {
  const {world, key} = fixture(t);
  world.pendingModelColliders.push(entityCollider({id: 'pending', type: 'Model', dimensions: {x: 100, y: 100, z: 100}}, new Map())!);
  key('keydown', 'KeyW', 100); key('keyup', 'KeyW', 1300);
  assert.equal(world.position.z, 0); assert.equal(world.initialSurfaceWait.state.waiting, true);
});

test('render and input timestamps share one clock and cannot count an interval twice', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 100);
  for (let frame = 1; frame <= 6; frame++) world.animate(100 + frame * 1000 / 60);
  key('keyup', 'KeyW', 200); world.animate(200);
  assert(Math.abs(world.position.z + .28) < 1e-8);
});

test('unaccepted controls and invalid event clocks do not cause movement or exceptions', t => {
  const {world, key} = fixture(t);
  key('keydown', 'KeyW', 100, {ctrlKey: true}); key('keyup', 'KeyW', 1300);
  assert.equal(world.position.z, 0);
  key('keydown', 'KeyW', 1400); assert.doesNotThrow(() => key('keyup', 'KeyW', NaN));
  assert.equal(world.keys.size, 0);
});
