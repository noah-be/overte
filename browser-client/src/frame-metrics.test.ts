// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FrameMetrics } from './frame-metrics';

test('frame measurements retain genuine stalls and bound memory over long operation', () => {
  const metrics = new FrameMetrics();
  metrics.sample(0);
  for (let i = 1; i <= 20; i++) metrics.sample(i * 20);
  metrics.sample(2400);
  assert.equal(metrics.snapshot().maximumFrameMs, 2000, 'Loading stalls cannot disappear behind simulation delta clamping');
  assert(metrics.snapshot().fps < 10);
  for (let i = 1; i <= 1000; i++) metrics.sample(2400 + i * 20);
  assert.equal(metrics.snapshot().samples, 240);
  assert.equal(metrics.snapshot().frames, 1021);
  assert.equal(metrics.snapshot().fps, 50);
  assert.equal(metrics.snapshot().p95FrameMs, 20);
});

test('invalid timestamps and a fresh world cannot fabricate measured frames', () => {
  const metrics = new FrameMetrics();
  metrics.sample(Number.NaN); metrics.sample(Infinity);
  assert.equal(metrics.snapshot().samples, 0);
  metrics.sample(100); metrics.sample(100);
  assert.equal(metrics.snapshot().frames, 0);
  metrics.sample(120);
  assert.equal(metrics.snapshot().fps, 50);
  assert.equal(new FrameMetrics().snapshot().frames, 0);
});
