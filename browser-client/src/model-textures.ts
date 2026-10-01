// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { LoadingManager, Object3D } from 'three';

/** A synchronous FBX parse may still start asynchronous image dependencies. */
export async function parseTexturedModel<T extends Object3D>(manager: LoadingManager, signal: AbortSignal,
  parse: () => T, dispose: (model: T) => void): Promise<T> {
  let settle!: () => void;
  let fail!: (error: Error) => void;
  const ready = new Promise<void>((resolve, reject) => { settle = resolve; fail = reject; });
  const abort = () => { fail(new DOMException('Session ended while loading model textures', 'AbortError')); manager.abort(); };
  const timer = setTimeout(() => {
    // Loader abort handlers may synchronously itemEnd and invoke onLoad.
    // Establish the failure first so a deadline cannot become successful.
    fail(Error('Model textures did not finish loading within 30 seconds')); manager.abort();
  }, 30000);
  manager.onLoad = settle;
  signal.addEventListener('abort', abort, { once: true });
  const sentinel = 'browser-internal-model-parse';
  let model: T | undefined;
  try {
    if (signal.aborted) throw new DOMException('Session ended before model parsing', 'AbortError');
    manager.itemStart(sentinel);
    try { model = parse(); } finally { manager.itemEnd(sentinel); }
    if (signal.aborted) abort();
    await ready;
    if (signal.aborted) throw new DOMException('Session ended while loading model textures', 'AbortError');
    return model;
  } catch (error) {
    // Consume the dependency promise even when parsing itself failed first.
    fail(error instanceof Error ? error : Error('Model parsing failed'));
    await ready.catch(() => {});
    manager.abort();
    if (model) dispose(model);
    throw error;
  } finally {
    clearTimeout(timer); signal.removeEventListener('abort', abort);
    manager.onLoad = () => {};
  }
}
