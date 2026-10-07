// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {SimulationClock} from './simulation-clock';

test('held movement covers the same distance at 60, 30, 10 and 4 rendered frames per second', () => {
  for (const fps of [60, 30, 10, 4]) {
    const clock = new SimulationClock(); let distance = 0;
    clock.advance(0);
    for (let frame = 1; frame <= fps * 4; frame++) {
      for (let step = clock.advance(frame * 1000 / fps); step > 0; step--) distance += 2.8 * clock.stepSeconds;
    }
    assert(Math.abs(distance - 11.2) < 1e-9, `actual ${fps} FPS movement time must not be lost`);
  }
});

test('collision steps remain small and a long pause cannot accumulate a catch-up backlog', () => {
  const clock = new SimulationClock(); clock.advance(0);
  assert.equal(clock.advance(10000), 15);
  assert.equal(clock.advance(10000), 0);
  assert.equal(clock.advance(10000 + 1000 / 60), 1);
  assert(5 * clock.stepSeconds < .12, 'running movement still fits the existing collision subdivision bound');
});

test('fractional frames retain their movement time; invalid or stale timestamps cannot rewind it', () => {
  const clock = new SimulationClock(); clock.advance(100);
  assert.equal(clock.advance(105), 0); assert.equal(clock.advance(NaN), 0);
  assert.equal(clock.advance(104), 0); assert.equal(clock.advance(Infinity), 0);
  assert.equal(clock.advance(117), 1); assert.equal(clock.advance(133.4), 1);
});

test('join and input resets discard time from the previous control interval', () => {
  const clock = new SimulationClock(); clock.advance(0); clock.advance(10);
  clock.reset(); assert.equal(clock.advance(10000), 0);
  assert.equal(clock.advance(10000 + 1000 / 60), 1);
});
