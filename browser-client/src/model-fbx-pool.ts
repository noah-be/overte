// SPDX-License-Identifier: Apache-2.0
export interface PreparedBakedFbx { buffer: ArrayBuffer; phases: { materialBindingsMs: number; decodeMs: number } }
export interface FbxPreparationWorker {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  onmessageerror: ((event: MessageEvent<unknown>) => void) | null;
  postMessage(message: unknown, transfer?: Transferable[]): void;
  terminate(): void;
}
interface Options {
  signal?: AbortSignal; limit?: 1 | 2;
  /** May shorten the fixed maximum for real-timer tests; never extend it. */
  deadlineMs?: number;
  /** Dependency injection for Node fault tests, not a browser/gateway setting. */
  workerFactory?: () => FbxPreparationWorker;
}
interface Job {
  id: number; bytes: number; buffer?: ArrayBuffer; signal?: AbortSignal; onAbort?: () => void;
  resolve(result: PreparedBakedFbx): void; reject(error: unknown): void; timer?: ReturnType<typeof setTimeout>;
  settled: boolean; expiresAt?: number; decodeExpiresAt?: number;
}
interface Slot { worker: FbxPreparationWorker; job?: Job }
const MIB = 1024 * 1024;
const MAX_JOBS = 16, MAX_INPUT_TOTAL = 96 * MIB, MAX_INPUT = 32 * MIB, MAX_OUTPUT = 256 * MIB;
function aborted(): DOMException { return new DOMException('FBX preparation cancelled', 'AbortError'); }

/** Owned per-world two-worker pipeline, with bounded transfer and immediate revocation. */
export class BakedFbxPreparePool {
  private readonly limit: 1 | 2;
  private readonly deadlineMs: number;
  private readonly factory: () => FbxPreparationWorker;
  private readonly slots: Slot[] = [];
  private readonly queue: Job[] = [];
  private readonly jobs = new Set<Job>();
  private inputBytes = 0;
  private nextID = 0;
  private disposed = false;
  private readonly signal?: AbortSignal;
  private readonly onDispose: () => void;
  private completed = 0; private cancelled = 0; private failed = 0;

  constructor(options: Options = {}) {
    this.limit = options.limit ?? 2;
    if (this.limit !== 1 && this.limit !== 2) throw Error('FBX preparation supports one or two workers');
    this.deadlineMs = options.deadlineMs ?? 60000;
    if (!Number.isSafeInteger(this.deadlineMs) || this.deadlineMs < 1 || this.deadlineMs > 60000) throw Error('FBX preparation deadline must be within 1–60000 milliseconds');
    this.factory = options.workerFactory ?? (() => new Worker(new URL('./model-fbx-worker.ts', import.meta.url), { type: 'module' }));
    this.signal = options.signal;
    this.onDispose = () => this.dispose();
    if (this.signal?.aborted) this.disposed = true;
    else this.signal?.addEventListener('abort', this.onDispose, { once: true });
  }

  prepare(buffer: ArrayBuffer, signal?: AbortSignal): Promise<PreparedBakedFbx> {
    if (this.disposed || signal?.aborted) return Promise.reject(aborted());
    if (!(buffer instanceof ArrayBuffer) || buffer.byteLength <= 0 || buffer.byteLength > MAX_INPUT) return Promise.reject(Error('FBX preparation input must be within 1 byte–32 MiB'));
    if (this.jobs.size >= MAX_JOBS || this.inputBytes + buffer.byteLength > MAX_INPUT_TOTAL) return Promise.reject(Error('FBX preparation queue exceeds its 16-job or 96 MiB input limit'));
    return new Promise((resolve, reject) => {
      const job: Job = { id: ++this.nextID, bytes: buffer.byteLength, buffer, signal, resolve, reject, settled: false };
      job.onAbort = () => this.cancel(job);
      signal?.addEventListener('abort', job.onAbort, { once: true });
      this.jobs.add(job); this.inputBytes += job.bytes; this.queue.push(job);
      this.pump();
    });
  }

  get counters() { return { active: this.slots.filter(slot => slot.job).length, queued: this.queue.length,
    outstanding: this.jobs.size, inputBytes: this.inputBytes, workers: this.slots.length,
    completed: this.completed, cancelled: this.cancelled, failed: this.failed, disposed: this.disposed }; }

  private finish(job: Job, error?: unknown, result?: PreparedBakedFbx): void {
    if (job.settled) return;
    job.settled = true; clearTimeout(job.timer);
    if (job.onAbort) job.signal?.removeEventListener('abort', job.onAbort);
    job.buffer = undefined; this.jobs.delete(job); this.inputBytes -= job.bytes;
    if (result === undefined) { if (!(error instanceof DOMException && error.name === 'AbortError')) this.failed++; job.reject(error ?? Error('FBX preparation failed')); }
    else { this.completed++; job.resolve(result!); }
  }

  private retire(slot: Slot): void {
    slot.worker.onmessage = null; slot.worker.onerror = null; slot.worker.onmessageerror = null;
    slot.worker.terminate();
    const index = this.slots.indexOf(slot); if (index !== -1) this.slots.splice(index, 1);
    // Draco executes on this same owned thread: termination leaves no nested
    // decoder worker requiring an unproved recursive cleanup guarantee.
  }

  private cancel(job: Job): void {
    if (job.settled) return;
    const queued = this.queue.indexOf(job); if (queued !== -1) this.queue.splice(queued, 1);
    const slot = this.slots.find(value => value.job === job);
    if (slot) {
      try { slot.worker.postMessage({ type: 'cancel', id: job.id }); } catch { /* Termination remains authoritative. */ }
      slot.job = undefined; this.retire(slot);
    }
    this.cancelled++; this.finish(job, aborted()); this.pump();
  }

  private createSlot(): Slot {
    const slot: Slot = { worker: this.factory() }; this.slots.push(slot);
    const failed = (error: Error) => {
      if (!this.slots.includes(slot)) return;
      const job = slot.job; slot.job = undefined; this.retire(slot);
      if (job) this.finish(job, error); this.pump();
    };
    slot.worker.onerror = event => failed(Error(event.message || 'FBX preparation worker failed'));
    slot.worker.onmessageerror = () => failed(Error('FBX preparation worker returned unreadable data'));
    slot.worker.onmessage = event => {
      if (!this.slots.includes(slot) || !slot.job) return;
      const data = event.data as Partial<PreparedBakedFbx> & { id?: unknown; error?: unknown; type?: unknown };
      if (!data || typeof data !== 'object' || data.id !== slot.job.id) return;
      if (data.type === 'decodeStarted') {
        const job=slot.job;
        // First stage report may tighten the full deadline, never restart it.
        if (job.decodeExpiresAt === undefined) { job.decodeExpiresAt=performance.now()+30000; this.armDeadline(slot,job); }
        return;
      }
      if (typeof data.error === 'string') { failed(Error(data.error.slice(0, 8192))); return; }
      if (!(data.buffer instanceof ArrayBuffer) || data.buffer.byteLength <= 0 || data.buffer.byteLength > MAX_OUTPUT ||
          !data.phases || ![data.phases.materialBindingsMs, data.phases.decodeMs].every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 60000)) {
        failed(Error('FBX preparation worker returned invalid geometry data')); return;
      }
      const job = slot.job; slot.job = undefined;
      this.finish(job, undefined, data as PreparedBakedFbx); this.pump();
    };
    return slot;
  }

  private armDeadline(slot: Slot, job: Job): void {
    clearTimeout(job.timer);
    const expiry=Math.min(job.expiresAt!,job.decodeExpiresAt??Infinity);
    job.timer=setTimeout(()=>{
      if(slot.job!==job||!this.slots.includes(slot))return;
      slot.job=undefined;this.retire(slot);
      this.finish(job,Error(job.decodeExpiresAt!==undefined&&job.decodeExpiresAt<=job.expiresAt!
        ?'The baked model Draco decoder exceeded its 30-second limit':'FBX preparation exceeded its bounded deadline'));
      this.pump();
    },Math.max(0,expiry-performance.now()));
  }

  private pump(): void {
    if (this.disposed) return;
    while (this.queue.length) {
      let slot = this.slots.find(value => !value.job);
      if (!slot && this.slots.length >= this.limit) return;
      if (!slot) {
        try { slot = this.createSlot(); }
        catch (error) { const job = this.queue.shift()!; this.finish(job, error); continue; }
      }
      const job = this.queue.shift()!;
      if (job.signal?.aborted) { this.cancelled++; this.finish(job, aborted()); continue; }
      slot.job = job;
      const owned = slot;
      job.expiresAt=performance.now()+this.deadlineMs;
      this.armDeadline(owned,job);
      try {
        const buffer = job.buffer!;
        slot.worker.postMessage({ type: 'prepare', id: job.id, buffer }, [buffer]);
        job.buffer = undefined;
      } catch (error) {
        slot.job = undefined; this.retire(slot); this.finish(job, error);
      }
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true; this.signal?.removeEventListener('abort', this.onDispose);
    this.queue.length = 0;
    for (const slot of [...this.slots]) {
      if (slot.job) { try { slot.worker.postMessage({ type: 'cancel', id: slot.job.id }); } catch { /* Terminate below. */ } }
      slot.job = undefined; this.retire(slot);
    }
    for (const job of [...this.jobs]) { this.cancelled++; this.finish(job, aborted()); }
  }
}
