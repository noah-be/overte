// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LoadingManager, Group } from 'three';
import { parseTexturedModel } from '../src/model-textures';

test('actual Three LoadingManager waits for every image, including synchronous cached completion', async () => {
  const manager = new LoadingManager(), model = new Group(); let settled = false;
  const pending = parseTexturedModel(manager, new AbortController().signal, () => {
    manager.itemStart('first.png'); manager.itemStart('cached.png'); manager.itemEnd('cached.png'); manager.itemStart('last.png'); return model;
  }, () => assert.fail('A successfully loaded model must not be disposed')).then(value => { settled = true; return value; });
  await Promise.resolve(); assert.equal(settled, false);
  manager.itemEnd('first.png'); await Promise.resolve(); assert.equal(settled, false);
  manager.itemEnd('last.png'); assert.equal(await pending, model);
  assert.equal(await parseTexturedModel(new LoadingManager(), new AbortController().signal, () => model, () => {}), model);
});

test('native dependency failure can finish loading while its real manager error remains observable', async () => {
  const errors: string[] = [], manager = new LoadingManager(undefined, undefined, url => errors.push(url)), model = new Group();
  const pending = parseTexturedModel(manager, new AbortController().signal, () => { manager.itemStart('missing.png'); return model; }, () => {});
  manager.itemError('missing.png'); manager.itemEnd('missing.png');
  assert.equal(await pending, model); assert.deepEqual(errors, ['missing.png']);
});

test('stalled model image loading expires at its unchanged deadline and late completion cannot revive it', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const manager = new LoadingManager(), model = new Group(); let disposed = 0;
  const pending = parseTexturedModel(manager, new AbortController().signal, () => { manager.itemStart('stalled.png'); return model; }, value => { assert.equal(value, model); disposed++; });
  const rejected = assert.rejects(pending, /within 30 seconds/);
  t.mock.timers.tick(30000); await rejected;
  assert.equal(disposed, 1); manager.itemEnd('stalled.png'); await Promise.resolve(); assert.equal(disposed, 1);
});

test('session cancellation disposes a parsed model once, and an already-cancelled session never parses', async () => {
  const manager = new LoadingManager(), abort = new AbortController(); let disposed = 0, parsed = 0;
  const pending = parseTexturedModel(manager, abort.signal, () => { parsed++; manager.itemStart('image.png'); return new Group(); }, () => disposed++);
  const rejected = assert.rejects(pending, {name:'AbortError'}); abort.abort(); await rejected;
  manager.itemEnd('image.png'); assert.equal(disposed, 1);
  await assert.rejects(parseTexturedModel(manager, abort.signal, () => { parsed++; return new Group(); }, () => disposed++), {name:'AbortError'});
  assert.equal(parsed, 1); assert.equal(disposed, 1);
});

test('a parser exception is retained without unhandled dependency rejection or a false timeout', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const manager = new LoadingManager(), original = new Error('Actual parser failure');
  await assert.rejects(parseTexturedModel(manager, new AbortController().signal, () => { manager.itemStart('late.png'); throw original; }, () => assert.fail()), error => error === original);
  t.mock.timers.tick(30000); manager.itemEnd('late.png');
});

test('deadline stays failed when actual LoadingManager abort synchronously completes an image', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const manager = new LoadingManager(), model = new Group(); let disposed = 0;
  const pending = parseTexturedModel(manager, new AbortController().signal, () => {
    manager.itemStart('dependency');
    manager.abortController.signal.addEventListener('abort', () => manager.itemEnd('dependency'), {once:true});
    return model;
  }, () => disposed++);
  const rejected = assert.rejects(pending, /within 30 seconds/);
  t.mock.timers.tick(30000); await rejected; assert.equal(disposed, 1);
});

test('a cached completed parse is revoked by cancellation before its promise publishes', async () => {
  const manager = new LoadingManager(), abort = new AbortController(); let disposed = 0;
  const pending = parseTexturedModel(manager, abort.signal, () => new Group(), () => disposed++);
  const rejected = assert.rejects(pending, {name:'AbortError'}); abort.abort(); await rejected;
  assert.equal(disposed, 1);
});
