// SPDX-License-Identifier: Apache-2.0
// Native gateway audio: 48 kHz signed PCM, microphone mono / received mix stereo.
class OverteAudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.queue = [];
        this.offset = 0;
        this.frames = 0;
        this.playing = false;
        this.muted = true;
        this.capture = new Float32Array(960);
        this.captureOffset = 0;
        this.capturePhase = 0;
        this.playedFrames = 0;
        this.playedPeak = 0;
        this.port.onmessage = ({data}) => {
            if (data.type === 'mute') {
                this.muted = data.muted;
                this.captureOffset = 0;
            } else if (data.type === 'pcm') {
                const view = new DataView(data.buffer);
                if (view.byteLength % 4 || view.byteLength > 384000) return;
                const samples = new Float32Array(view.byteLength / 2);
                for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
                this.queue.push(samples);
                this.frames += samples.length / 2;
                // Drop stale audio, keeping latency and memory bounded after scheduling stalls.
                while (this.frames > 12000 && this.queue.length > 1) {
                    const chunk = this.queue.shift();
                    this.frames -= chunk.length / 2 - this.offset;
                    this.offset = 0;
                }
                if (this.frames >= 1920) this.playing = true;
            }
        };
    }
    process(inputs, outputs) {
        const input = inputs[0]?.[0];
        if (input && !this.muted) {
            for (let i = 0; i < input.length; i++) {
                this.capturePhase += 48000 / sampleRate;
                while (this.capturePhase >= 1) {
                    this.capture[this.captureOffset++] = input[i];
                    this.capturePhase--;
                    if (this.captureOffset === 960) {
                        const buffer = new ArrayBuffer(1920);
                        const view = new DataView(buffer);
                        for (let j = 0; j < 960; j++) {
                            const value = Math.max(-1, Math.min(1, this.capture[j]));
                            view.setInt16(j * 2, Math.round(value < 0 ? value * 32768 : value * 32767), true);
                        }
                        this.port.postMessage({type:'microphone', buffer}, [buffer]);
                        this.captureOffset = 0;
                    }
                }
            }
        }
        const output = outputs[0];
        if (!output?.length) return true;
        for (let i = 0; i < output[0].length; i++) {
            if (!this.playing || !this.queue.length) continue;
            const chunk = this.queue[0];
            const index = Math.floor(this.offset) * 2;
            output[0][i] = chunk[index] || 0;
            if (output[1]) output[1][i] = chunk[index + 1] || 0;
            this.playedPeak = Math.max(this.playedPeak, Math.abs(output[0][i]), Math.abs(output[1]?.[i] || 0));
            if (++this.playedFrames % 4800 === 0) {
                this.port.postMessage({type:'playback', frames:this.playedFrames, peak:this.playedPeak});
                this.playedPeak = 0;
            }
            const advance = 48000 / sampleRate;
            this.offset += advance;
            this.frames -= advance;
            if (this.offset >= chunk.length / 2) {
                this.offset -= chunk.length / 2;
                this.queue.shift();
                if (!this.queue.length) { this.offset = 0; this.frames = 0; this.playing = false; }
            }
        }
        return true;
    }
}
registerProcessor('overte-audio', OverteAudioProcessor);
