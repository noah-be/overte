// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Bounded fixed-step movement time, independent of the render frame rate.
 * Up to 250 ms of an active frame is recovered, in 60 Hz collision steps.
 * Longer stalls discard excess time rather than teleporting on tab restoration.
 */
export class SimulationClock {
  private previous?: number;
  private remainder = 0;
  readonly stepSeconds = 1 / 60;
  readonly maximumElapsedSeconds = .25;

  advance(timeMs: number): number {
    if (!Number.isFinite(timeMs)) return 0;
    if (this.previous === undefined) { this.previous = timeMs; return 0; }
    if (timeMs <= this.previous) return 0;
    const elapsed = Math.min((timeMs - this.previous) / 1000, this.maximumElapsedSeconds);
    this.previous = timeMs;
    this.remainder += elapsed;
    // The small relative tolerance prevents a mathematically exact 60 Hz tick
    // from being dropped because its floating-point remainder is slightly short.
    const steps = Math.min(15, Math.floor((this.remainder + this.stepSeconds * 1e-9) / this.stepSeconds));
    this.remainder = Math.max(0, this.remainder - steps * this.stepSeconds);
    return steps;
  }

  reset(): void { this.previous = undefined; this.remainder = 0; }
}
