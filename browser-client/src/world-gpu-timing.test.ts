// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { WorldGpuTiming } from './world-gpu-timing';

function fixture(options: { supported?: boolean; bits?: number; every?: number } = {}) {
  let now = 0, current: WebGLQuery | null = null, disjoint = false, lost = false, reads = 0, ends = 0, disjointReads = 0;
  const created: WebGLQuery[] = [], deleted = new Set<WebGLQuery>(), ready = new Map<WebGLQuery, number>();
  const extension = { TIME_ELAPSED_EXT: 10, GPU_DISJOINT_EXT: 11, QUERY_COUNTER_BITS_EXT: 12 };
  const gl = { CURRENT_QUERY: 1, QUERY_RESULT_AVAILABLE: 2, QUERY_RESULT: 3,
    getExtension: () => options.supported === false ? null : extension,
    getQuery: (_target: number, key: number) => key === 12 ? options.bits ?? 64 : current,
    createQuery: () => { const query = {} as WebGLQuery; created.push(query); return query; },
    beginQuery: (_target: number, query: WebGLQuery) => { assert.equal(current, null); current = query; },
    endQuery: () => { ends++; current = null; }, isContextLost: () => lost,
    getParameter: () => { disjointReads++; return disjoint; },
    getQueryParameter: (query: WebGLQuery, key: number) => { if (key === 2) return ready.has(query); assert.ok(ready.has(query), 'No result read before actual availability'); reads++; return ready.get(query); },
    deleteQuery: (query: WebGLQuery) => { assert.ok(created.includes(query), 'No foreign query deletion'); assert.equal(deleted.has(query), false, 'No duplicate release'); deleted.add(query); },
  };
  const timer = new WorldGpuTiming(gl as unknown as WebGL2RenderingContext, { sampleEveryFrames: options.every, now: () => now });
  return { timer, gl, created, deleted, ready, get current() { return current; }, get reads() { return reads; }, get ends() { return ends; }, get disjointReads() { return disjointReads; },
    advance: (ms: number) => { now += ms; }, foreign: (query: WebGLQuery | null) => { current = query; }, disjoint: () => { disjoint = true; }, lost: () => { lost = true; } };
}

test('actual-draw sampler creates one query every eight frames and reports asynchronous GPU/CPU populations separately', () => {
  const f = fixture();
  for (let frame = 0; frame < 24; frame++) {
    const token = f.timer.beginFrame();
    if (frame % 8 === 0) { assert.ok(token); const query = f.current!; assert.equal(f.timer.endFrame(token, 20, true), true); f.ready.set(query, 5_000_000); }
    else assert.equal(token, undefined);
  }
  f.timer.pollFrame(); const snapshot = f.timer.getSnapshot();
  assert.equal(f.created.length, 3); assert.equal(f.reads, 3); assert.equal(snapshot.observedFrames, 24); assert.equal(snapshot.cpuSamples, 3); assert.equal(snapshot.gpu.completed, 3);
  assert.equal(snapshot.meanSampledCpuSubmitMs, 20); assert.equal(snapshot.meanValidGpuElapsedMs, 5); assert.equal(snapshot.comparablePopulation, true);
  assert.equal(snapshot.maxPending, 8); assert.equal(snapshot.gpu.timeoutMs, 5000); f.timer.dispose();
});

test('unsupported timer extension and unsafe counters have null means and allocate no queries', () => {
  for (const options of [{ supported: false }, { bits: 0 }, { bits: 16 }]) {
    const f = fixture(options); for (let frame = 0; frame < 20; frame++) assert.equal(f.timer.beginFrame(), undefined);
    assert.equal(f.created.length, 0); const snapshot = f.timer.getSnapshot(); assert.equal(snapshot.status, 'unsupported'); assert.equal(snapshot.meanValidGpuElapsedMs, null); assert.equal(snapshot.meanSampledCpuSubmitMs, null); assert.equal(snapshot.comparablePopulation, false); f.timer.dispose();
  }
  const f = fixture({ bits: 32 }); assert.equal(f.timer.getSnapshot().gpu.timeoutMs, 2147); f.timer.dispose();
});

test('legacy WebGL1 timer extension cannot substitute for WebGL2 query ownership', () => {
  let allocated = 0;
  const gl = { getExtension: (name: string) => { assert.equal(name, 'EXT_disjoint_timer_query_webgl2'); return { TIME_ELAPSED_EXT: 10, QUERY_COUNTER_BITS_EXT: 12 }; },
    createQuery: () => { allocated++; return {}; } } as unknown as WebGLRenderingContext;
  // A lying/partial extension cannot authorize absent WebGL2 getQuery methods.
  const timer = new WorldGpuTiming(gl);
  assert.equal(timer.beginFrame(), undefined); timer.pollFrame();
  assert.equal(timer.getSnapshot().status, 'unsupported'); assert.equal(allocated, 0); timer.dispose();
});

test('pending lag and invalidated samples cannot claim matched CPU/GPU frame populations', () => {
  const f = fixture({ every: 1 }); const token = f.timer.beginFrame()!, query = f.current!; f.timer.endFrame(token, 30, true);
  let snapshot = f.timer.getSnapshot(); assert.equal(snapshot.meanSampledCpuSubmitMs, 30); assert.equal(snapshot.meanValidGpuElapsedMs, null); assert.equal(snapshot.comparablePopulation, false);
  f.ready.set(query, 4_000_000); f.timer.pollFrame(); assert.equal(f.timer.getSnapshot().comparablePopulation, true);
  const other = f.timer.beginFrame()!; f.timer.endFrame(other, 60, true); f.disjoint(); f.timer.pollFrame();
  snapshot = f.timer.getSnapshot(); assert.equal(snapshot.gpu.completed, 1); assert.equal(snapshot.cpuSamples, 2); assert.equal(snapshot.gpu.disjointDropped, 1); assert.equal(snapshot.comparablePopulation, false); f.timer.dispose();
});

test('hard eight-query cap, five-second deadline and 32-bit wrap bound preserve finite resources', () => {
  for (const bits of [64, 32]) {
    const f = fixture({ every: 1, bits });
    for (let frame = 0; frame < 24; frame++) { const token = f.timer.beginFrame(); if (token) f.timer.endFrame(token, 20, true); }
    assert.equal(f.created.length, 8); assert.equal(f.timer.getSnapshot().gpu.pending, 8); assert.ok(f.timer.getSnapshot().gpu.skippedCapacity > 0);
    f.advance(bits === 32 ? 2147 : 5000); f.timer.pollFrame();
    assert.equal(f.deleted.size, 8); assert.equal(f.reads, 0); assert.equal(f.timer.getSnapshot().gpu.timedOut, 8); assert.equal(f.timer.getSnapshot().comparablePopulation, false);
    const token = f.timer.beginFrame()!; assert.ok(token); f.timer.endFrame(token, 20, true); f.timer.dispose(); assert.equal(f.deleted.size, 9);
  }
});

test('foreign timer is never ended/deleted and refused per-frame sampling still expires owned pending work', () => {
  const f = fixture({ every: 1 }); const own = f.timer.beginFrame()!; f.timer.endFrame(own, 20, true);
  const foreign = {} as WebGLQuery; f.foreign(foreign); const disjointReads = f.disjointReads; f.advance(5000);
  assert.equal(f.timer.beginFrame(), undefined); assert.equal(f.current, foreign); assert.equal(f.disjointReads, disjointReads);
  assert.equal(f.timer.getSnapshot().gpu.timedOut, 1); assert.equal(f.ends, 1); assert.equal(f.deleted.size, 1); f.timer.dispose(); assert.equal(f.current, foreign);
});

test('identity-bound sample tokens prevent foreign/copy/repeated end from touching the active query', () => {
  const f = fixture(), token = f.timer.beginFrame()!, query = f.current!;
  assert.equal(f.timer.endFrame({}, 20, true), false); assert.equal(f.timer.endFrame(undefined, 20, true), false); assert.equal(f.current, query); assert.equal(f.ends, 0);
  assert.equal(f.timer.endFrame(token, 20, true), true); assert.equal(f.timer.endFrame(token, 20, true), false); assert.equal(f.ends, 1); assert.equal(f.timer.getSnapshot().endedSamples, 1); f.timer.dispose();
});

test('paused presentation polling drains existing samples without inventing rendered frames', () => {
  const f = fixture(), token = f.timer.beginFrame()!, query = f.current!; f.timer.endFrame(token, 20, true); f.ready.set(query, 3_000_000);
  for (let frame = 0; frame < 20; frame++) f.timer.pollFrame();
  assert.equal(f.created.length, 1); assert.equal(f.timer.getSnapshot().observedFrames, 1); assert.equal(f.timer.getSnapshot().gpu.completed, 1); f.timer.dispose();
});

test('renderer failure/invalid CPU values preserve cleanup and refuse comparable populations', () => {
  for (const input of [{ cpu: 10, rendered: false }, { cpu: undefined, rendered: true }, { cpu: NaN, rendered: true }, { cpu: -1, rendered: true }]) {
    const f = fixture(), token = f.timer.beginFrame()!, query = f.current!;
    assert.equal(f.timer.endFrame(token, input.cpu, input.rendered), true); f.ready.set(query, 3_000_000); f.timer.pollFrame();
    const snapshot = f.timer.getSnapshot(); assert.equal(snapshot.cpuSamples, 0); assert.equal(snapshot.gpu.completed, 1); assert.equal(snapshot.comparablePopulation, false); assert.equal(snapshot.renderFailedSamples + snapshot.invalidCpuSamples, 1); f.timer.dispose();
  }
});

test('context loss/disposal closes owned queries before later frame work and leaves no recurring scheduler', () => {
  const f = fixture(), token = f.timer.beginFrame()!; f.lost(); f.timer.endFrame(token, 20, true);
  assert.equal(f.timer.getSnapshot().status, 'context-lost'); assert.equal(f.timer.getSnapshot().gpu.pending, 0); assert.equal(f.timer.beginFrame(), undefined);
  f.timer.dispose(); f.timer.dispose(); assert.equal(f.deleted.size, 1); assert.equal(f.timer.getSnapshot().status, 'disposed'); assert.equal(f.timer.beginFrame(), undefined);
  const active = fixture(), pending = active.timer.beginFrame()!; active.timer.dispose();
  assert.equal(active.ends, 1); assert.equal(active.deleted.size, 1); assert.equal(active.timer.endFrame(pending, 20, true), false);
});

test('forgotten end expires the owned active handle and the bounded sampler can resume safely', () => {
  const f = fixture({ every: 1 }), token = f.timer.beginFrame()!; f.advance(5000); assert.equal(f.timer.beginFrame(), undefined);
  assert.equal(f.timer.getSnapshot().orphanedSamples, 1); assert.equal(f.deleted.size, 1); assert.equal(f.timer.endFrame(token, 20, true), false);
  assert.ok(f.timer.beginFrame()); f.timer.dispose(); assert.equal(f.deleted.size, 2);
});

test('unsupported or unbounded sampling options are refused without allocating a timer query', () => {
  for (const every of [0, 121, 1.5, Infinity, NaN]) assert.throws(() => fixture({ every }), /bounded/);
});
