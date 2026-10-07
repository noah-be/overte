// SPDX-License-Identifier: Apache-2.0
export type NativeTextureAlpha = 'opaque' | 'mask' | 'blend';
/** Native processTextureAlpha uses actual alpha, never the RGB background. */
export function classifyNativeAlpha(total: number, opaque: number, intermediate: number): NativeTextureAlpha {
  if (![total, opaque, intermediate].every(Number.isSafeInteger) || total <= 0 || opaque < 0 || intermediate < 0 || opaque + intermediate > total) throw Error('Invalid texture alpha counts');
  if (opaque === total) return 'opaque';
  // Match the native float multiplication and integer truncation precisely.
  const threshold = Math.trunc(Math.fround(Math.fround(0.05) * Math.fround(total)));
  return intermediate <= threshold ? 'mask' : 'blend';
}
interface Job { image: ImageBitmapSource; resolve(value: NativeTextureAlpha): void; reject(reason: unknown): void; signal: AbortSignal; id: number; stop(): void; timer?: ReturnType<typeof setTimeout> }
interface Inspection { promise: Promise<NativeTextureAlpha>; controller: AbortController; consumers: number; settled: boolean }
const cache = new WeakMap<object, Inspection>();
const queue: Job[] = [];
const backpressure: Job[] = [];
let worker: Worker | undefined, active: Job | undefined, nextID = 0;
function abortError() { return new DOMException('Texture alpha inspection cancelled', 'AbortError'); }
function finish(error?: unknown, result?: NativeTextureAlpha) {
  const job = active; active = undefined;
  if (job) { job.stop(); if (error) job.reject(error); else job.resolve(result!); }
  pump();
}
function reset(error: unknown) { worker?.terminate(); worker = undefined; finish(error); }
function getWorker() {
  if (!worker) {
    worker = new Worker(new URL('./texture-alpha-worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = ({ data }: MessageEvent<{ id: number; error?: string; total: number; opaque: number; intermediate: number }>) => {
      if (data.id !== active?.id) return;
      try { if (data.error) throw Error(data.error); finish(undefined, classifyNativeAlpha(data.total, data.opaque, data.intermediate)); }
      catch (error) { finish(error); }
    };
    const owned = worker;
    worker.onerror = () => { if (worker === owned) reset(Error('Texture alpha worker failed')); };
  }
  return worker;
}
function pump() {
  while (queue.length < 32 && backpressure.length) queue.push(backpressure.shift()!);
  if (active) return;
  const job = queue.shift(); if (!job) return;
  active = job;
  if (job.signal.aborted) { finish(abortError()); return; }
  job.timer = setTimeout(() => { if (active === job) reset(Error('Texture alpha inspection exceeded 30 seconds')); }, 30000);
  let bitmapPromise: Promise<ImageBitmap>;
  try { bitmapPromise = createImageBitmap(job.image); }
  catch (error) { finish(error); return; }
  bitmapPromise.then(bitmap => {
    if (active !== job || job.signal.aborted) { bitmap.close(); if (active === job) finish(abortError()); return; }
    if (bitmap.width * bitmap.height > 64 * 1024 * 1024) { bitmap.close(); finish(Error('Decoded texture alpha image exceeds 64 megapixels')); return; }
    try { getWorker().postMessage({ id: job.id, bitmap }, [bitmap]); }
    catch (error) { bitmap.close(); finish(error); }
  }, error => { if (active === job) finish(error); });
}
function inspect(image: object, signal: AbortSignal): Promise<NativeTextureAlpha> {
  const dimensions = image as { width?: number; height?: number; naturalWidth?: number; naturalHeight?: number };
  const width = dimensions.naturalWidth ?? dimensions.width, height = dimensions.naturalHeight ?? dimensions.height;
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width! <= 0 || height! <= 0 || width! * height! > 64 * 1024 * 1024) return Promise.reject(Error('Texture alpha inspection requires a loaded image within 64 megapixels'));
  if (backpressure.length >= 128) return Promise.reject(Error('Too many pending texture alpha inspections'));
  return new Promise((resolve, reject) => {
    const id = ++nextID;
    const onAbort = () => {
      for (const waiting of [queue, backpressure]) {
        const at = waiting.findIndex(job => job.id === id);
        if (at >= 0) { const [job] = waiting.splice(at, 1); job.stop(); reject(abortError()); pump(); return; }
      }
      if (active?.id === id) reset(abortError());
    };
    const job: Job = { image: image as ImageBitmapSource, id, signal, resolve, reject, stop: () => { signal.removeEventListener('abort', onAbort); if (job.timer) clearTimeout(job.timer); } };
    signal.addEventListener('abort', onAbort, { once: true });
    if (queue.length >= 32 || backpressure.length) backpressure.push(job); else queue.push(job);
    pump();
  });
}
/** Shared per-image inspection; cancellation frees an unneeded worker job.
 * Unreadable/tainted images reject so the caller can show an honest warning. */
export function nativeTextureAlpha(texture: { image: unknown }, signal?: AbortSignal): Promise<NativeTextureAlpha> {
  if (signal?.aborted) return Promise.reject(abortError());
  const image = texture.image;
  if (!image || typeof image !== 'object') return Promise.reject(Error('Texture alpha inspection requires a loaded image'));
  let record = cache.get(image);
  if (!record) {
    const controller = new AbortController();
    record = { controller, consumers: 0, settled: false, promise: Promise.resolve('opaque') };
    const current = record;
    current.promise = inspect(image, controller.signal).then(value => { current.settled = true; return value; }, error => { current.settled = true; if (cache.get(image) === current) cache.delete(image); throw error; });
    cache.set(image, current);
  }
  record.consumers++;
  const current = record;
  let onAbort: (() => void) | undefined;
  return new Promise<NativeTextureAlpha>((resolve, reject) => {
    onAbort = () => reject(abortError());
    signal?.addEventListener('abort', onAbort, { once: true });
    current.promise.then(resolve, reject);
  }).finally(() => {
    if (onAbort) signal?.removeEventListener('abort', onAbort);
    current.consumers--;
    if (!current.consumers && !current.settled) {
      if (cache.get(image) === current) cache.delete(image);
      current.controller.abort();
    }
  });
}
