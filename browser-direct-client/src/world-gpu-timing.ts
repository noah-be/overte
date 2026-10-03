// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { GpuTimeObserver } from './gpu-time-observer';

interface Options { sampleEveryFrames?: number; onWarning?: (message: string) => void; now?: () => number }
type Token = Readonly<object>;

/** Optional aggregate diagnostics for actual World frame draws only. Call
 * beginFrame before the existing graphicsSubmit CPU clock, and endFrame after
 * recording that clock. No renderer/shader/scene/quality setting is changed.
 * GPU elapsed includes driver scheduling/idle gaps while CPU commands arrive;
 * it is not a measurement of pure fragment work or compositor presentation. */
export class WorldGpuTiming {
  private readonly observer: GpuTimeObserver;
  private readonly every: number;
  private ordinal = 0;
  private active?: Token;
  private disposed = false;
  private readonly stats = { observedFrames: 0, scheduledSamples: 0, begunSamples: 0, endedSamples: 0,
    cpuSamples: 0, totalCpuSubmitMs: 0, maxCpuSubmitMs: 0, renderFailedSamples: 0, invalidCpuSamples: 0, orphanedSamples: 0 };

  constructor(gl: WebGL2RenderingContext | WebGLRenderingContext, options: Options = {}) {
    this.every = options.sampleEveryFrames ?? 8;
    if (!Number.isInteger(this.every) || this.every < 1 || this.every > 120) throw Error('Invalid bounded World GPU sample frequency');
    // Fixed maximum and deadline; counter-wrap gating is owned by the frozen
    // observer. No caller can increase the resource/time bounds through World.
    // Three's declared getContext union includes WebGL1. The observer first
    // requires EXT_disjoint_timer_query_webgl2 plus a valid getQuery counter;
    // absent APIs/extension fail closed before any query allocation. WebGL1's
    // older EXT_disjoint_timer_query must never be substituted here.
    this.observer = new GpuTimeObserver(gl as WebGL2RenderingContext, { maxPending: 8, timeoutMs: 5000, onWarning: options.onWarning, now: options.now });
  }

  /** Normal sampled begin already polls, and other frames use pollFrame. A
   * refused begin adds at most one bounded poll, because foreign ownership may
   * refuse begin before its internal poll. Active tokens are local identity
   * proofs, not WebGL handles. Only one can be outstanding in this wrapper. */
  beginFrame(): Token | undefined {
    if (this.disposed) return;
    this.stats.observedFrames++;
    const scheduled = this.ordinal === 0; this.ordinal = (this.ordinal + 1) % this.every;
    if (!scheduled || this.active) { this.pollFrame(); return; }
    this.stats.scheduledSamples++;
    if (!this.observer.begin()) { this.pollFrame(); return; }
    this.stats.begunSamples++;
    const token = Object.freeze({}); this.active = token; return token;
  }

  /** Poll once on normal RAF tasks even while Tablet pauses presentation. No
   * timer, spin, readPixels, gl.finish or blocking result wait is introduced. */
  pollFrame(): void {
    if (this.disposed) return;
    this.observer.poll();
    if (this.active && !this.observer.getSnapshot().active) {
      this.active = undefined; this.stats.orphanedSamples++;
    }
  }

  endFrame(token: Token | undefined, cpuSubmitMs: number | undefined, rendered: boolean): boolean {
    if (this.disposed || !token || token !== this.active) return false;
    this.active = undefined;
    const ended = this.observer.end();
    if (!ended) return false;
    this.stats.endedSamples++;
    if (!rendered) { this.stats.renderFailedSamples++; return true; }
    if (typeof cpuSubmitMs !== 'number' || !Number.isFinite(cpuSubmitMs) || cpuSubmitMs < 0) { this.stats.invalidCpuSamples++; return true; }
    this.stats.cpuSamples++; this.stats.totalCpuSubmitMs += cpuSubmitMs; this.stats.maxCpuSubmitMs = Math.max(this.stats.maxCpuSubmitMs, cpuSubmitMs);
    return true;
  }

  getSnapshot() {
    const gpu = this.observer.getSnapshot();
    const comparablePopulation = gpu.supported && !gpu.contextLost && !gpu.active && gpu.pending === 0
      && gpu.completed > 0 && gpu.completed === this.stats.cpuSamples && gpu.completed === this.stats.endedSamples
      && gpu.disjointDropped === 0 && gpu.timedOut === 0 && gpu.failed === 0
      && this.stats.renderFailedSamples === 0 && this.stats.invalidCpuSamples === 0 && this.stats.orphanedSamples === 0;
    return {
      enabled: true, status: this.disposed ? 'disposed' : gpu.contextLost ? 'context-lost' : !gpu.supported ? 'unsupported' : gpu.completed ? 'sampling' : 'awaiting-samples',
      sampleEveryFrames: this.every, maxPending: 8, ...this.stats,
      // These populations can differ while pending or after invalid/disjoint
      // intervals. Never subtract them to invent a CPU-vs-GPU frame breakdown.
      meanSampledCpuSubmitMs: this.stats.cpuSamples ? this.stats.totalCpuSubmitMs / this.stats.cpuSamples : null,
      meanValidGpuElapsedMs: gpu.completed ? gpu.totalGpuMs / gpu.completed : null,
      comparablePopulation, gpu,
    };
  }

  dispose(): void { if (this.disposed) return; this.disposed = true; this.active = undefined; this.observer.dispose(); }
}
