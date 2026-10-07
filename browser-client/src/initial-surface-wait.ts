// SPDX-License-Identifier: Apache-2.0
/** A spawn/reposition safeguard, not a recurring midair loading freeze.
 * Only a real current collision contact may verify support. Pending entity
 * bounds can delay initial motion but cannot establish contact themselves. */
export class InitialSurfaceWait {
  private supported = false;
  private startedAt: number | undefined;
  private lastTime = 0;
  private waiting = false;
  private expired = false;

  get needsSupport() { return !this.supported && !this.expired; }
  get state() { return { verified: this.supported, waiting: this.waiting, startedAt: this.startedAt, expired: this.expired }; }

  reset(): void {
    this.supported = false;
    this.startedAt = undefined;
    this.lastTime = 0;
    this.waiting = false;
    this.expired = false;
  }

  update(time: number, pendingBounds: boolean, actualSupport: boolean): { waiting: boolean; started: boolean } {
    if (!Number.isFinite(time) || time < 0) throw Error('Invalid surface-wait timestamp');
    // Clock regression cannot extend the existing bounded episode.
    this.lastTime = Math.max(time, this.lastTime);
    if (!this.expired && actualSupport) this.supported = true;
    let started = false;
    if (this.needsSupport && pendingBounds && this.startedAt === undefined) {
      this.startedAt = this.lastTime;
      started = true;
    }
    if (!this.supported && this.startedAt !== undefined && this.lastTime - this.startedAt >= 15000) this.expired = true;
    this.waiting = this.needsSupport && pendingBounds && this.startedAt !== undefined;
    return { waiting: this.waiting, started };
  }
}
