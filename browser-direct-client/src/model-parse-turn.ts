// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
interface ParseJob {
  parse: () => unknown; discard?: (value: unknown) => void; signal?: AbortSignal;
  weight: number; resolve: (value: unknown) => void; reject: (error: unknown) => void;
  onAbort: () => void;
}
const aborted = (signal?: AbortSignal) => signal?.reason instanceof Error ? signal.reason : new DOMException('Model parse owner ended', 'AbortError');
/** Only this optional scheduling-capacity refusal may use the original parse
 * path, after the caller rechecks its current owner and authority. */
export class ModelParseCapacityError extends Error {
  constructor() { super('Model parse queue capacity exceeded'); this.name = 'ModelParseCapacityError'; }
}
/** An optional scheduling boundary, not a parser cache. Each synchronous parse
 * runs in a separate owned task; parsed resources never survive in this queue. */
export class ModelParseTurn {
  private readonly jobs: ParseJob[] = [];
  private channel?: MessageChannel;
  private closed = false;
  private bytes = 0;
  private parsed = 0;
  private readonly onAbort = () => this.dispose();
  constructor(private readonly owner?: AbortSignal) {
    if (owner?.aborted) this.closed = true;
    else owner?.addEventListener('abort', this.onAbort, { once: true });
  }
  get stats() { return { queued: this.jobs.length, queuedBytes: this.bytes, parsed: this.parsed, closed: this.closed, taskChannelOpen: Boolean(this.channel) }; }
  run<T>(parse: () => T, options: { signal?: AbortSignal; weight: number; discard?: (value: T) => void }): Promise<T> {
    if (this.closed || options.signal?.aborted) return Promise.reject(aborted(options.signal));
    if (!Number.isSafeInteger(options.weight) || options.weight < 0 || options.weight > 256 * 1024 * 1024) return Promise.reject(Error('Invalid model parse byte weight'));
    if (this.jobs.length >= 32 || this.bytes + options.weight > 256 * 1024 * 1024) return Promise.reject(new ModelParseCapacityError());
    return new Promise<T>((resolve, reject) => {
      const job: ParseJob = { parse, signal: options.signal, weight: options.weight,
        discard: options.discard as ParseJob['discard'], resolve: resolve as ParseJob['resolve'], reject,
        onAbort: () => {
          const index = this.jobs.indexOf(job);
          if (index < 0) return;
          this.jobs.splice(index, 1); this.release(job); reject(aborted(job.signal));
          if (!this.jobs.length) this.closeChannel();
        } };
      job.signal?.addEventListener('abort', job.onAbort, { once: true });
      this.jobs.push(job); this.bytes += job.weight;
      if (!this.channel) {
        try {
          const channel = new MessageChannel(); this.channel = channel;
          channel.port1.onmessage = () => { if (this.channel === channel) this.drain(); };
          channel.port2.postMessage(null);
        } catch (error) {
          this.jobs.splice(this.jobs.indexOf(job), 1); this.release(job); this.closeChannel(); reject(error);
        }
      }
    });
  }
  private release(job: ParseJob): void { this.bytes -= job.weight; job.signal?.removeEventListener('abort', job.onAbort); }
  private closeChannel(): void {
    const channel = this.channel; this.channel = undefined;
    if (channel) { channel.port1.onmessage = null; channel.port1.close(); channel.port2.close(); }
  }
  private drain(): void {
    const job = this.jobs.shift();
    if (!job) { this.closeChannel(); return; }
    try {
      if (this.closed || job.signal?.aborted) throw aborted(job.signal);
      const value = job.parse(); this.parsed++;
      if (this.closed || job.signal?.aborted) { job.discard?.(value); throw aborted(job.signal); }
      job.resolve(value);
    } catch (error) { job.reject(error); }
    finally { this.release(job); }
    if (this.jobs.length && !this.closed) this.channel?.port2.postMessage(null);
    else this.closeChannel();
  }
  dispose(): void {
    if (this.closed) return;
    this.closed = true; this.owner?.removeEventListener('abort', this.onAbort); this.closeChannel();
    for (const job of this.jobs.splice(0)) { this.release(job); job.reject(aborted()); }
  }
}
