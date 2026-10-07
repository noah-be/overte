// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Modified for Overte direct browser compatibility: exact native PCM framing,
// worker ports, bounded tickets and epoch-controlled audio lifecycle.
// Native Overte audio: 24 kHz, 240 samples/channel, 10 ms per network frame.
// Browser capture and output run at the real AudioContext sample rate.
class OverteDirectAudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.capture = new Float32Array(240);
        this.captureOffset = 0;
        this.capturePhase = 0;
        this.muted = true;
        this.queue = [];
        this.offset = 0;
        this.playing = false;
        this.receivedFrames = 0;
        this.droppedFrames = 0;
        this.playedFrames = 0;
        this.playedPeak = 0;
        this.capturedFrames = 0;
        this.sentMicrophoneFrames = 0;
        this.droppedMicrophoneFrames = 0;
        this.microphoneTicket = 0;
        this.pendingMicrophone = new Set();
        this.lastMixerTicket = 0;
        this.telemetrySamples = 0;
        this.transportPort = null;
        this.transportID = 0;
        this.audioEpoch = 0;
        this.port.onmessage = ({ data }) => {
            if (!data || typeof data !== 'object') return;
            if (data.type === 'attach-audio-port' && data.port
                    && typeof data.port.postMessage === 'function' && typeof data.port.close === 'function') {
                this.attachTransport(data.port, data.id);
            } else if (data.type === 'detach-audio-port' && (data.id === undefined || data.id === this.transportID)) {
                this.detachTransport();
            } else if (data.type === 'reset') {
                // UI reset is playback-only. Session reset below also closes
                // capture, independently of the renderer's main thread.
                this.resetPlayback();
            } else if (data.type === 'mute') {
                if (data.muted === false && this.transportPort && data.epoch !== this.audioEpoch) {
                    this.reportTransportState();
                } else {
                    this.setMuted(data.muted !== false);
                }
            } else if (data.type === 'pcm' && !this.transportPort) {
                this.receivePCM(data.buffer);
            }
        };
    }
    resetPlayback() { this.queue = []; this.offset = 0; this.playing = false; }
    setMuted(muted) {
        this.muted = muted;
        this.captureOffset = 0;
        this.capturePhase = 0;
        this.transportPort?.postMessage({ type: 'microphoneState', muted, epoch: this.audioEpoch });
    }
    reportTransportState() {
        this.port.postMessage({ type: 'transport-state', epoch: this.audioEpoch, muted: this.muted });
    }
    detachTransport() {
        if (this.transportPort) {
            this.transportPort.onmessage = null;
            this.transportPort.close();
            this.transportPort = null;
        }
        this.muted = true; this.captureOffset = 0; this.capturePhase = 0;
        this.pendingMicrophone.clear(); this.lastMixerTicket = 0;
        this.resetPlayback();
    }
    attachTransport(port, id) {
        this.detachTransport();
        this.transportPort = port;
        this.transportID = id;
        this.audioEpoch = 0;
        port.onmessage = ({ data }) => {
            if (this.transportPort !== port || !data || typeof data !== 'object'
                    || !Number.isSafeInteger(data.epoch) || data.epoch < 0) return;
            if ((data.type === 'reset' || data.type === 'mute') && data.epoch >= this.audioEpoch) {
                this.audioEpoch = data.epoch;
                this.pendingMicrophone.clear(); this.lastMixerTicket = 0;
                if (data.type === 'reset') this.resetPlayback();
                // Only a new explicit UI action can reopen capture. Worker
                // resets and mixer NoisyMute never enable a physical device.
                this.setMuted(true);
                this.reportTransportState();
            } else if (data.epoch === this.audioEpoch && Number.isSafeInteger(data.ticket) && data.ticket > 0) {
                if (data.type === 'microphoneAck') {
                    this.pendingMicrophone.delete(data.ticket);
                } else if (data.type === 'pcm') {
                    // Return credit even when the ring drops a frame or its
                    // buffer is malformed. Epoch/ticket still identify only
                    // the current worker's bounded outstanding messages.
                    port.postMessage({ type: 'playbackAck', epoch: this.audioEpoch, ticket: data.ticket });
                    if (data.ticket > this.lastMixerTicket) {
                        this.lastMixerTicket = data.ticket;
                        this.receivePCM(data.buffer);
                    }
                }
            }
        };
        port.start();
        port.postMessage({ type: 'microphoneState', muted: true, epoch: this.audioEpoch });
        this.port.postMessage({ type: 'audio-port-attached', id, epoch: this.audioEpoch });
    }
    receivePCM(buffer) {
        if (!(buffer instanceof ArrayBuffer) || buffer.byteLength !== 960) return;
        const view = new DataView(buffer);
        const samples = new Float32Array(480);
        for (let index = 0; index < 480; index++) samples[index] = view.getInt16(index * 2, true) / 32768;
        this.queue.push(samples);
        this.receivedFrames++;
        // Keep at most 100 ms. A background-tab scheduling stall must
        // not turn into an unbounded queue or stale speech playback.
        while (this.queue.length > 10) {
            this.queue.shift(); this.offset = 0; this.droppedFrames++;
        }
        if (this.queue.length >= 2) this.playing = true;
    }
    process(inputs, outputs) {
        const input = inputs[0]?.[0];
        if (input && !this.muted) {
            for (let index = 0; index < input.length; index++) {
                this.capturePhase += 24000 / sampleRate;
                while (this.capturePhase >= 1) {
                    this.capture[this.captureOffset++] = Number.isFinite(input[index]) ? input[index] : 0;
                    this.capturePhase--;
                    if (this.captureOffset === 240) {
                        this.capturedFrames++;
                        if (this.transportPort && this.pendingMicrophone.size >= 10) {
                            this.droppedMicrophoneFrames++;
                        } else {
                            const buffer = new ArrayBuffer(480), view = new DataView(buffer);
                            for (let sample = 0; sample < 240; sample++) {
                                const value = Math.max(-1, Math.min(1, this.capture[sample]));
                                view.setInt16(sample * 2, Math.round(value < 0 ? value * 32768 : value * 32767), true);
                            }
                            if (this.transportPort) {
                                const ticket = ++this.microphoneTicket;
                                this.pendingMicrophone.add(ticket);
                                this.transportPort.postMessage({ type: 'microphone', buffer, epoch: this.audioEpoch, ticket }, [buffer]);
                            } else {
                                this.port.postMessage({ type: 'microphone', buffer }, [buffer]);
                            }
                            this.sentMicrophoneFrames++;
                        }
                        this.captureOffset = 0;
                    }
                }
            }
        }
        const output = outputs[0];
        if (!output?.length) return true;
        for (const channel of output) channel.fill(0);
        for (let index = 0; index < output[0].length; index++) {
            if (!this.playing || !this.queue.length) continue;
            const chunk = this.queue[0], sample = Math.floor(this.offset), fraction = this.offset - sample;
            const next = sample < 239 ? chunk : this.queue[1] ?? chunk;
            const nextIndex = sample < 239 ? (sample + 1) * 2 : this.queue[1] ? 0 : sample * 2;
            const left = chunk[sample * 2] + (next[nextIndex] - chunk[sample * 2]) * fraction;
            const right = chunk[sample * 2 + 1] + (next[nextIndex + 1] - chunk[sample * 2 + 1]) * fraction;
            output[0][index] = left;
            if (output[1]) output[1][index] = right;
            this.playedPeak = Math.max(this.playedPeak, Math.abs(left), Math.abs(right));
            this.playedFrames++;
            this.offset += 24000 / sampleRate;
            while (this.offset >= 240 && this.queue.length) {
                this.offset -= 240;
                this.queue.shift();
            }
            if (!this.queue.length) { this.offset = 0; this.playing = false; }
        }
        // Only bounded numeric summaries cross the UI thread. Even silence
        // reports capture counts without routing PCM through renderer tasks.
        this.telemetrySamples += output[0].length;
        if (this.telemetrySamples >= sampleRate / 10) {
            this.telemetrySamples %= sampleRate / 10;
            this.port.postMessage({ type: 'playback', frames: this.playedFrames, peak: this.playedPeak,
                capturedFrames: this.capturedFrames, receivedFrames: this.receivedFrames,
                sentMicrophoneFrames: this.sentMicrophoneFrames, droppedMicrophoneFrames: this.droppedMicrophoneFrames,
                pendingMicrophoneFrames: this.pendingMicrophone.size,
                droppedFrames: this.droppedFrames });
            this.playedPeak = 0;
        }
        return true;
    }
}
registerProcessor('overte-direct-audio', OverteDirectAudioProcessor);
