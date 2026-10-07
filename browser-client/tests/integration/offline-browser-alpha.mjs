// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real Firefox Worker/ImageBitmap/OffscreenCanvas proof without a TCP server.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { firefox } from '@playwright/test';

const directory = path.resolve(process.env.OVERTE_OFFLINE_FIXTURE_DIR || '/tmp/overte-browser-offline-fixture');
const entry = process.env.OVERTE_OFFLINE_FIXTURE_ENTRY || 'fixture.js';
assert.equal(path.basename(entry), entry, 'The fixture entry must be a trusted local filename');
const output = path.resolve(process.env.OVERTE_OFFLINE_ALPHA_REPORT || 'build/offline-browser-alpha/result.json');
const origin = 'https://overte-offline.invalid';
const fixtureURL = `${origin}/${entry}`;
const files = new Map(), requests = [], pageErrors = [];
const started = new Date().toISOString();
let browser, context, result, failure;
async function bounded(promise, milliseconds, message) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error(message)), milliseconds); })]); }
  finally { clearTimeout(timer); }
}
try {
  const entryBytes = await readFile(path.join(directory, entry));
  files.set(entry, createHash('sha256').update(entryBytes).digest('hex'));
  browser = await firefox.launch({ headless: true, timeout: 45000 });
  context = await browser.newContext();
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { await route.abort('blockedbyclient'); return; }
    if (url.pathname === '/') {
      await route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><head><title>Offline native alpha proof</title></head><body></body></html>' });
      return;
    }
    let relative;
    try { relative = decodeURIComponent(url.pathname).slice(1); } catch { await route.abort(); return; }
    const filename = path.resolve(directory, relative);
    if (!filename.startsWith(directory + path.sep) || !/\.(?:js|mjs)$/.test(filename)) { await route.abort(); return; }
    try {
      const bytes = await readFile(filename);
      requests.push(relative); files.set(relative, createHash('sha256').update(bytes).digest('hex'));
      await route.fulfill({ contentType: 'text/javascript', body: bytes });
    } catch { await route.abort(); }
  });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto(origin + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  result = await bounded(page.evaluate(async fixtureURL => {
    const module = await import(fixtureURL);
    if (typeof module.nativeTextureAlpha !== 'function') throw Error('The fixture must export nativeTextureAlpha');
    const { nativeTextureAlpha } = module;
    const make = (width, height, intermediate = 0, transparent = 0) => {
      const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
      const context = canvas.getContext('2d'); if (!context) throw Error('The test needs actual canvas image bytes');
      const bytes = new Uint8ClampedArray(width * height * 4);
      for (let pixel = 0; pixel < width * height; pixel++) bytes[pixel * 4 + 3] = pixel < intermediate ? 128 : pixel < intermediate + transparent ? 0 : 255;
      context.putImageData(new ImageData(bytes, width, height), 0, 0); return canvas;
    };
    const classify = async (name, image, expected) => {
      const started = performance.now(), actual = await nativeTextureAlpha({ image });
      if (actual !== expected) throw Error(`${name}: expected ${expected}, received ${actual}`);
      return { name, actual, milliseconds: performance.now() - started };
    };
    const capabilities = {
      worker: typeof Worker === 'function', imageBitmap: typeof ImageBitmap === 'function',
      createImageBitmap: typeof createImageBitmap === 'function', offscreenCanvas: typeof OffscreenCanvas === 'function',
      webgl2: Boolean(document.createElement('canvas').getContext('webgl2')), userAgent: navigator.userAgent,
    };
    const cases = [];
    cases.push(await classify('opaque-black', make(10, 10), 'opaque'));
    cases.push(await classify('transparent-black', make(10, 10, 0, 2), 'mask'));
    cases.push(await classify('native-five-percent-boundary', make(10, 10, 5), 'mask'));
    cases.push(await classify('above-native-five-percent-boundary', make(10, 10, 6), 'blend'));
    const tiled = make(300, 270); tiled.getContext('2d').clearRect(299, 269, 1, 1);
    cases.push(await classify('last-pixel-in-nonfull-worker-tile', tiled, 'mask'));

    const bitmap = await createImageBitmap(make(64, 64, 0, 10));
    const first = await nativeTextureAlpha({ image: bitmap }); bitmap.close();
    const cached = await nativeTextureAlpha({ image: bitmap });
    const freshModule = await import(fixtureURL + '?fresh-cache=1');
    const uncachedClosedBitmap = await freshModule.nativeTextureAlpha({ image: bitmap }).then(() => 'unexpected-success', error => error.message);
    if (first !== 'mask' || cached !== 'mask' || !uncachedClosedBitmap.includes('loaded image')) throw Error('The real decoded-bitmap cache control failed');

    const sharedImage = make(2048, 2048), one = new AbortController();
    const cancelledConsumer = nativeTextureAlpha({ image: sharedImage }, one.signal).then(() => 'unexpected-success', error => error.name);
    const retainedConsumer = nativeTextureAlpha({ image: sharedImage }); one.abort();
    const shared = { cancelled: await cancelledConsumer, retained: await retainedConsumer };
    if (shared.cancelled !== 'AbortError' || shared.retained !== 'opaque') throw Error('One cancelled reader invalidated a live real-image reader');

    const abandonedImage = make(4096, 4096), last = new AbortController();
    let completed = false;
    const abandoned = nativeTextureAlpha({ image: abandonedImage }, last.signal).then(() => { completed = true; return 'unexpected-success'; }, error => error.name);
    // Keep the real large worker job active; no API replacement or fake clock.
    await new Promise(resolve => setTimeout(resolve, 200));
    const pendingAtCancellation = !completed; last.abort();
    const cancellation = { pendingAtCancellation, result: await abandoned, recovery: await nativeTextureAlpha({ image: make(16, 16, 0, 1) }) };
    if (!pendingAtCancellation || cancellation.result !== 'AbortError' || cancellation.recovery !== 'mask') throw Error('The last-reader cancellation/recovery proof failed');

    // Synchronously fill the actual 1 active + 32 queued + 128 backpressure slots.
    // Each call uses distinct real canvas bytes, so the cache cannot evade the cap.
    const admitted = [];
    for (let i = 0; i < 161; i++) admitted.push(nativeTextureAlpha({ image: make(16, 16) }).then(value => ({ value }), error => ({ error: error.message })));
    const overflow = await nativeTextureAlpha({ image: make(16, 16) }).then(() => 'unexpected-success', error => error.message);
    const completedAdmissions = await Promise.all(admitted);
    const backpressure = { admitted: completedAdmissions.length, opaque: completedAdmissions.filter(value => value.value === 'opaque').length,
      failures: completedAdmissions.filter(value => value.error).map(value => value.error), overflow,
      recovery: await nativeTextureAlpha({ image: make(16, 16, 8) }) };
    if (backpressure.opaque !== 161 || backpressure.failures.length || overflow !== 'Too many pending texture alpha inspections' || backpressure.recovery !== 'mask') throw Error('Bounded actual-worker backpressure/recovery failed');
    return { capabilities, cases, cache: { first, cachedAfterClose: cached, closedWidth: bitmap.width, uncachedClosedBitmap }, shared, cancellation, backpressure };
  }, fixtureURL), 60000, 'Offline alpha proof did not finish within 60 seconds; the production per-job deadline remains 30 seconds');
  assert.equal(result.capabilities.worker, true); assert.equal(result.capabilities.imageBitmap, true);
  assert.equal(result.capabilities.offscreenCanvas, true); assert.equal(result.capabilities.createImageBitmap, true);
  assert.deepEqual(pageErrors, []);
} catch (error) { failure = error; }
finally {
  if (context) await context.close().catch(error => { failure ||= error; });
  if (browser) await browser.close().catch(error => { failure ||= error; });
}
const report = {
  schema: 1, started, completed: new Date().toISOString(), status: failure ? 'failed' : 'passed',
  scope: 'Actual Firefox Worker/ImageBitmap/OffscreenCanvas alpha inspection; no network server, native domain, GPU rendering or world-visual proof.',
  browser: browser?.version(), sourceFiles: [...files].map(([file, sha256]) => ({ file, sha256 })).sort((a, b) => a.file.localeCompare(b.file)),
  workerRequests: requests.filter(file => /worker/i.test(file)), pageErrors, result,
  error: failure instanceof Error ? failure.message : failure ? String(failure) : undefined,
};
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify({ status: report.status, browser: report.browser, classifications: result?.cases.map(value => value.actual), workerRequests: report.workerRequests.length, error: report.error }));
if (failure) throw failure;
