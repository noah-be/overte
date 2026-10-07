// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Group, LoadingManager } from 'three';
import { ModelParseTurn, ModelParseCapacityError } from '../src/model-parse-turn';
import { parseTexturedModel } from '../src/model-textures';

test('prepared parses leave the current microtask turn and deliver the exact original result', async () => {
  const owner = new ModelParseTurn(); const order: string[] = [];
  const graph = new Group(); const pending = owner.run(() => { order.push('parse'); return graph; }, { weight: 10 });
  await Promise.resolve(); order.push('microtask');
  assert.equal(await pending, graph); assert.deepEqual(order, ['microtask', 'parse']);
  assert.deepEqual(owner.stats, { queued: 0, queuedBytes: 0, parsed: 1, closed: false, taskChannelOpen: false }); owner.dispose();
});
test('successive parses are distinct tasks, allowing the first result continuation before the next parse', async () => {
  const owner = new ModelParseTurn(); const order: string[] = [];
  const a = owner.run(() => { order.push('a'); return 1; }, { weight: 1 }).then(() => order.push('a delivered'));
  const b = owner.run(() => { order.push('b'); return 2; }, { weight: 1 });
  await Promise.all([a, b]); assert.deepEqual(order, ['a', 'a delivered', 'b']); owner.dispose();
});
test('reader cancellation never starts its queued parser and releases its byte budget', async () => {
  const owner = new ModelParseTurn(); const reader = new AbortController(); let calls = 0;
  const pending = owner.run(() => ++calls, { signal: reader.signal, weight: 99 }); reader.abort();
  await assert.rejects(pending, { name: 'AbortError' }); assert.equal(calls, 0); assert.equal(owner.stats.queuedBytes, 0);
  assert.equal(owner.stats.taskChannelOpen, false); assert.equal(await owner.run(() => 42, { weight: 1 }), 42); owner.dispose();
});
test('whole owner abort closes ports and cancels every pending parse without publishing', async () => {
  const controller = new AbortController(); const owner = new ModelParseTurn(controller.signal); let calls = 0;
  const pending = Array.from({ length: 6 }, () => owner.run(() => ++calls, { weight: 1024 })); controller.abort();
  assert.ok((await Promise.allSettled(pending)).every(result => result.status === 'rejected' && result.reason.name === 'AbortError'));
  assert.equal(calls, 0); assert.equal(owner.stats.queuedBytes, 0); assert.equal(owner.stats.taskChannelOpen, false);
  await assert.rejects(owner.run(() => 1, { weight: 0 }), { name: 'AbortError' }); owner.dispose();
});
test('a parser that synchronously invalidates its reader discards exactly once', async () => {
  const owner = new ModelParseTurn(); const reader = new AbortController(); const graph = new Group(); let discarded = 0;
  await assert.rejects(owner.run(() => { reader.abort(); return graph; }, { signal: reader.signal, weight: 8, discard: value => { assert.equal(value, graph); discarded++; } }), { name: 'AbortError' });
  assert.equal(discarded, 1); assert.equal(owner.stats.queuedBytes, 0); owner.dispose();
});
test('parser failures retain their cause and do not strand subsequent jobs', async () => {
  const owner = new ModelParseTurn(); const error = Error('actual parse failure');
  const failed = owner.run(() => { throw error; }, { weight: 1 }); const next = owner.run(() => 2, { weight: 1 });
  await assert.rejects(failed, candidate => candidate === error); assert.equal(await next, 2); owner.dispose();
});
test('byte and count budgets refuse excess work before starting it', async () => {
  const owner = new ModelParseTurn(); const max = 256 * 1024 * 1024;
  const pending = owner.run(() => 1, { weight: max }); await assert.rejects(owner.run(() => 2, { weight: 1 }), /capacity/);
  assert.equal(await pending, 1); const jobs = Array.from({ length: 32 }, () => owner.run(() => 3, { weight: 0 }));
  await assert.rejects(owner.run(() => 4, { weight: 0 }), /capacity/); owner.dispose();
  assert.ok((await Promise.allSettled(jobs)).every(result => result.status === 'rejected'));
});
test('only dedicated capacity refusals authorize an optional caller fallback', async () => {
  const owner = new ModelParseTurn(); const pending = owner.run(() => 1, { weight: 256 * 1024 * 1024 });
  await assert.rejects(owner.run(() => assert.fail('Capacity-refused parser cannot start'), { weight: 1 }), error => error instanceof ModelParseCapacityError);
  assert.equal(await pending, 1);
  const sameText = Error('Model parse queue capacity exceeded');
  await assert.rejects(owner.run(() => { throw sameText; }, { weight: 1 }), error => error === sameText && !(error instanceof ModelParseCapacityError));
  owner.dispose();
});
test('revocation and malformed admission weights never become capacity fallback errors', async () => {
  const owner = new ModelParseTurn();
  await assert.rejects(owner.run(() => 1, { weight: Number.NaN }), error => error instanceof Error && !(error instanceof ModelParseCapacityError));
  owner.dispose(); await assert.rejects(owner.run(() => 1, { weight: 0 }), error => error instanceof Error && error.name === 'AbortError' && !(error instanceof ModelParseCapacityError));
});
test('the actual manager sentinel stays open across scheduling and asynchronous texture loading', async () => {
  const owner = new ModelParseTurn(); const reader = new AbortController(); const manager = new LoadingManager();
  const graph = new Group(); let disposed = 0; let ended = false;
  const result = parseTexturedModel(manager, reader.signal, () => { manager.itemStart('owned-image'); return graph; }, () => disposed++,
    (parse, signal) => owner.run(parse, { signal, weight: 1, discard: () => disposed++ }));
  void result.then(() => { ended = true; }); await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(owner.stats.parsed, 1); assert.equal(ended, false); manager.itemEnd('owned-image');
  assert.equal(await result, graph); assert.equal(disposed, 0); owner.dispose();
});
test('manager cancellation while the scheduled parser is queued rejects promptly and never runs it', async () => {
  const owner = new ModelParseTurn(); const reader = new AbortController(); const manager = new LoadingManager(); let calls = 0;
  const pending = parseTexturedModel(manager, reader.signal, () => { calls++; return new Group(); }, () => {},
    (parse, signal) => owner.run(parse, { signal, weight: 1 })); reader.abort();
  await assert.rejects(pending, { name: 'AbortError' }); assert.equal(calls, 0); assert.equal(owner.stats.taskChannelOpen, false); owner.dispose();
});
test('the original unscheduled parser remains synchronous with unchanged dependency accounting', async () => {
  const reader = new AbortController(); const manager = new LoadingManager(); let called = false; const graph = new Group();
  const pending = parseTexturedModel(manager, reader.signal, () => { called = true; return graph; }, () => {});
  assert.equal(called, true); assert.equal(await pending, graph);
});
test('an undelivered scheduled parse expires at the original deadline and closes owned ports', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const controller = new AbortController(); const owner = new ModelParseTurn(controller.signal); let calls = 0;
  const pending = parseTexturedModel(new LoadingManager(), controller.signal, () => { calls++; return new Group(); }, () => assert.fail('No parsed graph exists'),
    (parse, signal) => owner.run(parse, { signal, weight: 1 }));
  const rejected = assert.rejects(pending, /within 30 seconds/); t.mock.timers.tick(30000); await rejected;
  assert.equal(calls, 0); assert.equal(owner.stats.queuedBytes, 0); assert.equal(owner.stats.taskChannelOpen, false); owner.dispose();
});
test('a whole owner revoked from inside its parser cannot publish a graph', async () => {
  const controller = new AbortController(); const owner = new ModelParseTurn(controller.signal); let discarded = 0;
  await assert.rejects(owner.run(() => { controller.abort(); return new Group(); }, { weight: 5, discard: () => discarded++ }), { name: 'AbortError' });
  assert.equal(discarded, 1); assert.equal(owner.stats.queuedBytes, 0); assert.equal(owner.stats.taskChannelOpen, false);
});
