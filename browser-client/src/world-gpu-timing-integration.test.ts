// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld methods with a diagnostic boundary double. The observer's
// query ownership/deadline mathematics are exercised separately; no GPU claim.
import test, { type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { Group, PerspectiveCamera, Vector3 } from 'three';
import { BrowserWorld } from './world';
import { FstGraphCache } from './fst-graph-cache';
import { SimulationClock } from './simulation-clock';

function fixture(t: TestContext) {
  const events: string[] = [], token = Object.freeze({});
  const context = Object.create(BrowserWorld.prototype);
  let calls = 0;
  Object.assign(context, {
    disposed: false, enabled: false, simulationClock: new SimulationClock(), metrics: { sample() {}, snapshot: () => ({ fps: 60 }) },
    options: {}, camera: new PerspectiveCamera(), thirdPerson: false, yaw: 0, pitch: 0,
    position: new Vector3(0, .85, 0), self: new Group(), avatars: new Map(), localLights: new Set(),
    pointSlots: [], spotSlots: [], lastLightSelection: 0, presentationEnabled: true, renderedFrames: 0,
    renderer: { render() { events.push('render'); calls++; }, dispose() { events.push('renderer-dispose'); },
      getContext: () => ({ drawingBufferWidth: 1280, drawingBufferHeight: 800 }),
      info: { render: { calls: 10, triangles: 20 }, memory: { geometries: 3, textures: 2 } }, extensions: { has: () => false } },
    recordLoadPhase(name: string, started: number) { assert.equal(name, 'graphicsSubmit'); assert.ok(Number.isFinite(started)); events.push('cpu-record'); },
    entities: new Map(), objects: new Map(), avatarModels: new Map(), meshCollisions: new Map(),
    modelScheduler: { stats: { active: 0, queued: 0 } }, compilingGraphics: 0, imageCache: { stats: () => ({}) },
    embeddedFbxImages: { statistics: {} }, embeddedFbxCounts: {}, fbxPreparePool: { counters: {} },
    preparedFbx: { stats: {} }, initialSurfaceWait: { state: 'supported' }, loadPhases: new Map(),
    abort: new AbortController(), resizeObserver: { disconnect() {} }, loadManagers: new Set(),
    modelBatches: new Map(), modelGeometry: new WeakMap(), canvas: { remove() { events.push('canvas-remove'); },
      toBlob(callback: (blob: Blob) => void) { callback(new Blob(['owned visitor capture'], { type: 'image/png' })); } },
  });
  context.fstGraphCache = new FstGraphCache(context.abort.signal);
  const previousRaf = globalThis.requestAnimationFrame, previousCancel = globalThis.cancelAnimationFrame, previousDocument = globalThis.document;
  globalThis.requestAnimationFrame = () => { events.push('raf'); return 1; };
  globalThis.cancelAnimationFrame = () => {};
  Object.assign(globalThis, { document: { pointerLockElement: null } });
  t.after(() => {
    for (const [key, previous] of [['requestAnimationFrame', previousRaf], ['cancelAnimationFrame', previousCancel], ['document', previousDocument]] as const) {
      if (previous === undefined) delete (globalThis as unknown as Record<string, unknown>)[key];
      else (globalThis as unknown as Record<string, unknown>)[key] = previous;
    }
  });
  const diagnostic = {
    beginFrame() { events.push('gpu-begin'); return token; },
    endFrame(own: object, elapsed: number | undefined, rendered: boolean) {
      assert.equal(own, token); assert.equal(rendered, true); assert.ok(typeof elapsed === 'number' && elapsed >= 0); events.push('gpu-end');
    },
    pollFrame() { events.push('gpu-poll'); }, getSnapshot: () => ({ enabled: true, status: 'unsupported', meanValidGpuElapsedMs: null }),
    dispose() { events.push('gpu-dispose'); },
  };
  return { context, events, diagnostic, token, get calls() { return calls; } };
}

test('default-off actual World rendering keeps normal CPU records and allocates no diagnostic work', t => {
  const f = fixture(t); f.context.animate(1000);
  assert.deepEqual(f.events, ['render', 'cpu-record', 'raf']); assert.equal(f.context.renderedFrames, 1);
  assert.deepEqual(f.context.getPerformance().gpuTiming, { enabled: false });
});

test('opt-in actual frame brackets render only and retains independent CPU measurement order', t => {
  const f = fixture(t); f.context.gpuTiming = f.diagnostic; f.context.animate(1000);
  assert.deepEqual(f.events, ['gpu-begin', 'render', 'cpu-record', 'gpu-end', 'raf']);
  assert.equal(f.context.renderedFrames, 1); assert.equal(f.context.getPerformance().gpuTiming.meanValidGpuElapsedMs, null);
  assert.equal(f.context.getPerformance().drawingBufferWidth, 1280);
});

test('Tablet presentation pause polls pending work without draws, CPU samples or invented frames', t => {
  const f = fixture(t); f.context.gpuTiming = f.diagnostic; f.context.presentationEnabled = false;
  for (let index = 0; index < 20; index++) f.context.animate(1000 + index * 16);
  assert.equal(f.calls, 0); assert.equal(f.context.renderedFrames, 0);
  assert.equal(f.events.filter(event => event === 'gpu-poll').length, 20);
  assert.equal(f.events.filter(event => event === 'gpu-begin' || event === 'cpu-record').length, 0);
});

test('renderer error remains observable and finally closes only the diagnostic token', t => {
  const f = fixture(t); const failure = Error('original renderer failure');
  f.context.gpuTiming = { ...f.diagnostic, endFrame(token: object, elapsed: number | undefined, rendered: boolean) {
    assert.equal(token, f.token); assert.equal(elapsed, undefined); assert.equal(rendered, false); f.events.push('gpu-end-failed');
  } };
  f.context.renderer.render = () => { f.events.push('render-failed'); throw failure; };
  assert.throws(() => f.context.animate(1000), error => error === failure);
  assert.deepEqual(f.events, ['gpu-begin', 'render-failed', 'gpu-end-failed']); assert.equal(f.context.renderedFrames, 0);
});

test('actual visitor snapshot remains independent of sampled normal-frame diagnostics', async t => {
  const f = fixture(t); f.context.gpuTiming = f.diagnostic; f.context.enabled = true; f.context.presentationEnabled = false;
  assert.equal((await f.context.captureScene()).type, 'image/png');
  assert.deepEqual(f.events, ['render']); assert.equal(f.context.renderedFrames, 0);
});

test('actual World teardown releases diagnostic ownership before the renderer and blocks future frames', t => {
  const f = fixture(t); f.context.gpuTiming = f.diagnostic; f.context.dispose();
  assert.deepEqual(f.events, ['gpu-dispose', 'renderer-dispose', 'canvas-remove']); assert.equal(f.context.abort.signal.aborted, true);
  f.context.animate(2000); assert.deepEqual(f.events, ['gpu-dispose', 'renderer-dispose', 'canvas-remove']);
});
