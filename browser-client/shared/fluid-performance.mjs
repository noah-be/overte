// SPDX-License-Identifier: Apache-2.0
// A loaded-world proof requires measured frame intervals, not a successful join.
export function assessFluidPerformance(samples) {
    const minimumFPS = 30, maximumP95FrameMs = 1000 / 15, maximumStallMs = 250;
    const valid = Array.isArray(samples) && samples.length >= 2 && samples.every(sample => sample
        && ['fps','p95FrameMs','maximumFrameMs','samples'].every(key => Number.isFinite(sample[key]))
        && sample.samples >= 120 && sample.p95FrameMs > 0 && sample.maximumFrameMs >= sample.p95FrameMs);
    const passed = valid && samples.every(sample => sample.fps >= minimumFPS
        && sample.p95FrameMs <= maximumP95FrameMs && sample.maximumFrameMs <= maximumStallMs);
    return {passed:Boolean(passed),validMeasurements:Boolean(valid),minimumFPS,maximumP95FrameMs,maximumStallMs};
}
