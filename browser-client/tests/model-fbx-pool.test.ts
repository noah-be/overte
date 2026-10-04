// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BakedFbxPreparePool, type FbxPreparationWorker } from '../src/model-fbx-pool';
import { boundDecoderHeap } from '../src/model-fbx-decoder-memory';
class OwnedWorker implements FbxPreparationWorker {
  onmessage: FbxPreparationWorker['onmessage'] = null;
  onerror: FbxPreparationWorker['onerror'] = null;
  onmessageerror: FbxPreparationWorker['onmessageerror'] = null;
  terminated = false;
  requests: { type: string; id: number; buffer?: ArrayBuffer }[] = [];
  postMessage(value: unknown, transfers: Transferable[] = []) {
    this.requests.push(structuredClone(value, { transfer: transfers as ArrayBuffer[] }) as OwnedWorker['requests'][number]);
  }
  terminate() { this.terminated = true; }
  reply() {
    const request = this.requests.filter(value => value.type === 'prepare').at(-1)!;
    this.onmessage?.({ data: { id: request.id, buffer: request.buffer!, phases: { materialBindingsMs: 4, decodeMs: 9 } } } as MessageEvent);
  }
}
function fixture(options: ConstructorParameters<typeof BakedFbxPreparePool>[0] = {}) {
  const workers: OwnedWorker[] = [];
  const pool = new BakedFbxPreparePool({ ...options, workerFactory: () => { const worker = new OwnedWorker(); workers.push(worker); return worker; } });
  return { pool, workers };
}
const handled = <T>(value: Promise<T>): Promise<{result?: T; error?: Error}> => value.then(result => ({ result }), error => ({ error }));

test('two owned workers transfer buffers, preserve FIFO and reuse each decoder thread', async () => {
  const { pool, workers } = fixture();
  try {
    const first = new Uint8Array([1, 2, 3]).buffer, second = new Uint8Array([4]).buffer;
    const a = pool.prepare(first), b = pool.prepare(second), c = pool.prepare(new Uint8Array([5]).buffer);
    assert.equal(first.byteLength, 0); assert.equal(second.byteLength, 0);
    assert.equal(workers.length, 2); assert.equal(pool.counters.active, 2); assert.equal(pool.counters.queued, 1);
    assert.equal(pool.counters.inputBytes, 5);
    workers[0].reply(); assert.deepEqual([...new Uint8Array((await a).buffer)], [1, 2, 3]);
    assert.equal(workers[0].requests.at(-1)?.id, 3);
    workers[1].reply(); assert.deepEqual([...new Uint8Array((await b).buffer)], [4]);
    workers[0].reply(); assert.deepEqual([...new Uint8Array((await c).buffer)], [5]);
    assert.equal(pool.counters.completed, 3); assert.equal(pool.counters.inputBytes, 0); assert.equal(pool.counters.outstanding, 0);
  } finally { pool.dispose(); }
});

test('active cancellation terminates only its owned thread and ignores saved late callbacks', async () => {
  const { pool, workers } = fixture({ limit: 1 });
  try {
    const abort = new AbortController(); const a = handled(pool.prepare(new ArrayBuffer(4), abort.signal));
    const late = workers[0].onmessage!;
    const b = pool.prepare(new Uint8Array([9]).buffer);
    abort.abort();
    assert.equal((await a).error!.name, 'AbortError'); assert.equal(workers[0].terminated, true);
    assert.equal(workers[0].requests.at(-1)?.type, 'cancel'); assert.equal(workers.length, 2);
    late({ data: { id: 1, buffer: new ArrayBuffer(1), phases: { materialBindingsMs: 0, decodeMs: 0 } } } as MessageEvent);
    assert.equal(pool.counters.active, 1); assert.equal(pool.counters.completed, 0);
    workers[1].reply(); assert.equal(new Uint8Array((await b).buffer)[0], 9);
    assert.equal(pool.counters.cancelled, 1); assert.equal(pool.counters.failed, 0);
  } finally { pool.dispose(); }
});

test('queued cancellation releases its byte weight without affecting the live worker', async () => {
  const { pool, workers } = fixture({ limit: 1 });
  try {
    const a = pool.prepare(new ArrayBuffer(3)), abort = new AbortController();
    const b = handled(pool.prepare(new ArrayBuffer(7), abort.signal));
    assert.equal(pool.counters.inputBytes, 10); abort.abort();
    assert.equal((await b).error!.name, 'AbortError'); assert.equal(pool.counters.inputBytes, 3);
    assert.equal(workers[0].terminated, false); assert.equal(pool.counters.queued, 0);
    workers[0].reply(); await a;
  } finally { pool.dispose(); }
});

test('real bounded deadline terminates stalled work and admits the next request without fake clocks', async () => {
  const { pool, workers } = fixture({ limit: 1, deadlineMs: 25 });
  try {
    const start = performance.now(), a = handled(pool.prepare(new ArrayBuffer(2)));
    const b = pool.prepare(new ArrayBuffer(3));
    assert.match((await a).error!.message, /bounded deadline/);
    assert(performance.now() - start >= 20);
    assert.equal(workers[0].terminated, true); assert.equal(workers.length, 2);
    workers[1].reply(); assert.equal((await b).buffer.byteLength, 3);
    assert.equal(pool.counters.failed, 1); assert.equal(pool.counters.inputBytes, 0);
  } finally { pool.dispose(); }
});

test('whole-world revocation rejects active and queued work, clears weights and cannot be resumed', async () => {
  const signal = new AbortController(), { pool, workers } = fixture({ signal: signal.signal });
  const requests = [handled(pool.prepare(new ArrayBuffer(2))), handled(pool.prepare(new ArrayBuffer(2))), handled(pool.prepare(new ArrayBuffer(2)))];
  signal.abort(); pool.dispose();
  for (const request of requests) assert.equal((await request).error!.name, 'AbortError');
  assert.equal(workers.every(worker => worker.terminated), true);
  assert.equal(pool.counters.inputBytes, 0); assert.equal(pool.counters.outstanding, 0);
  await assert.rejects(pool.prepare(new ArrayBuffer(1)), { name: 'AbortError' });
});

test('the job-count and byte-weight bounds reject excess memory before transfer', async () => {
  const { pool } = fixture();
  const requests = Array.from({ length: 16 }, () => handled(pool.prepare(new ArrayBuffer(1))));
  const overflow = new ArrayBuffer(1);
  await assert.rejects(pool.prepare(overflow), /16-job or 96 MiB/); assert.equal(overflow.byteLength, 1);
  pool.dispose(); await Promise.all(requests);
  const second = fixture();
  const weighted = Array.from({ length: 3 }, () => handled(second.pool.prepare(new ArrayBuffer(32 * 1024 * 1024))));
  await assert.rejects(second.pool.prepare(new ArrayBuffer(1)), /16-job or 96 MiB/);
  await assert.rejects(second.pool.prepare(new ArrayBuffer(32 * 1024 * 1024 + 1)), /1 byte–32 MiB/);
  second.pool.dispose(); await Promise.all(weighted);
});

test('unreadable, oversized or non-finite worker results retire the decoder and recover cleanly', async () => {
  const { pool, workers } = fixture({ limit: 1 });
  try {
    const a = handled(pool.prepare(new ArrayBuffer(1))), b = pool.prepare(new ArrayBuffer(2));
    workers[0].onmessage!({ data: { id: 1, buffer: new ArrayBuffer(1), phases: { materialBindingsMs: NaN, decodeMs: 0 } } } as MessageEvent);
    assert.match((await a).error!.message, /invalid geometry/); assert.equal(workers[0].terminated, true);
    workers[1].reply(); await b;
    const c = handled(pool.prepare(new ArrayBuffer(1)));
    workers[1].onmessageerror!({ data: null } as MessageEvent);
    assert.match((await c).error!.message, /unreadable data/);
  } finally { pool.dispose(); }
});

test('exact decoder errors reach the caller and detached inputs are rejected', async () => {
  const { pool, workers } = fixture();
  try {
    const buffer = new ArrayBuffer(1), pending = handled(pool.prepare(buffer));
    await assert.rejects(pool.prepare(buffer), /1 byte–32 MiB/);
    workers[0].onmessage!({ data: { id: 1, error: 'Invalid native Draco original-index width' } } as MessageEvent);
    assert.equal((await pending).error!.message, 'Invalid native Draco original-index width');
  } finally { pool.dispose(); }
  assert.throws(() => fixture({ limit: 3 as 2 }), /one or two/);
  assert.throws(() => fixture({ deadlineMs: 60001 }), /60000/);
});

test('the actual Emscripten-exported memory grow path cannot exceed its byte budget', () => {
  const memory = new WebAssembly.Memory({ initial: 1, maximum: 32 });
  boundDecoderHeap(memory, 2 * 65536);
  assert.equal(memory.grow(1), 1); assert.equal(memory.buffer.byteLength, 2 * 65536);
  assert.throws(() => memory.grow(1), /bounded limit/);
  assert.equal(memory.buffer.byteLength, 2 * 65536);
  assert.throws(() => memory.grow(-1), /bounded limit/);
  assert.throws(() => boundDecoderHeap(new WebAssembly.Memory({ initial: 3 }), 65536), /heap limit/);
});


test('repeated decode-stage reports cannot extend the original real deadline',async()=>{
  const {pool,workers}=fixture({limit:1,deadlineMs:35});
  try {
    const started=performance.now(),pending=handled(pool.prepare(new ArrayBuffer(1)));
    const repeat=setInterval(()=>workers[0].onmessage?.({data:{id:1,type:'decodeStarted'}} as MessageEvent),5);
    try {assert.match((await pending).error!.message,/bounded deadline/);}
    finally {clearInterval(repeat);}
    const elapsed=performance.now()-started;assert(elapsed>=25&&elapsed<250);
    assert.equal(workers[0].terminated,true);assert.equal(pool.counters.outstanding,0);
  }finally{pool.dispose();}
});
