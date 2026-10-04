// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Pose packets use the same captured native PCM frames for audio loudness.
 * Capture and consent belong to the local browser AudioWorklet, not the SDK. */
export class BrowserAudioLevels {
    static readonly contextItemType = 'BrowserAudioLevels';
    private loudness = 0;
    getLastInputLoudness(): number { return this.loudness; }
    update(frame: ArrayBuffer): void {
        const samples = new Int16Array(frame);
        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        this.loudness = Math.sqrt(sum / Math.max(1, samples.length));
    }
    clear(): void { this.loudness = 0; }
}
