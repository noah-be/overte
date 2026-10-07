// SPDX-License-Identifier: Apache-2.0
/** Bounded measurements of actual animation intervals, including loading stalls. */
export class FrameMetrics {
  private readonly intervals = new Float64Array(240);
  private count = 0;
  private cursor = 0;
  private previous?: number;
  private totalFrames = 0;

  sample(time: number): void {
    if (!Number.isFinite(time)) return;
    if (this.previous !== undefined && time > this.previous) {
      this.intervals[this.cursor] = time - this.previous;
      this.cursor = (this.cursor + 1) % this.intervals.length;
      this.count = Math.min(this.count + 1, this.intervals.length);
      this.totalFrames++;
    }
    this.previous = time;
  }

  snapshot(): { frames: number; samples: number; fps: number; medianFrameMs: number; p95FrameMs: number; maximumFrameMs: number } {
    const values = Array.from(this.intervals.subarray(0, this.count)).sort((a, b) => a - b);
    const sum = values.reduce((total, value) => total + value, 0);
    return { frames: this.totalFrames, samples: this.count,
      fps: sum > 0 ? this.count * 1000 / sum : 0,
      medianFrameMs: values[Math.floor(values.length * 0.5)] || 0,
      p95FrameMs: values[Math.max(0, Math.ceil(values.length * 0.95) - 1)] || 0,
      maximumFrameMs: values.at(-1) || 0 };
  }
}
