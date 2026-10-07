// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Browser permission/device lifecycle adapted from the immutable renderer source.
// The network frame format is Overte's native 24 kHz PCM, not gateway audio.
export class BrowserAudio {
    private context?: AudioContext;
    private processor?: AudioWorkletNode;
    private microphone?: MediaStream;
    private source?: MediaStreamAudioSourceNode;
    private gain?: GainNode;
    private generation = 0;
    private microphoneGeneration = 0;
    private starting?: Promise<void>;
    private audioPortAttached = false;
    private audioEpoch = 0;
    private audioPortSerial = 0;
    private attaching?: { id: number; resolve: () => void; reject: (error: Error) => void; timeout: ReturnType<typeof setTimeout> };
    private sentFrames = 0;
    private receivedFrames = 0;
    private playedFrames = 0;
    private playedPeak = 0;
    private droppedFrames = 0;
    private capturedFrames = 0;
    private droppedMicrophoneFrames = 0;
    private pendingMicrophoneFrames = 0;
    muted = true;
    sound = true;

    constructor(private send: (data: ArrayBuffer) => void,
                private onStatus: (message: string, kind?: string) => void,
                private onMicrophoneChange: (muted: boolean) => void = () => {}) {}

    async start(): Promise<void> {
        if (this.starting) return this.starting;
        if (this.context) { await this.context.resume(); return; }
        if (!window.AudioContext || !window.isSecureContext) throw new Error('Voice requires HTTPS or localhost and Web Audio support.');
        const operation = this.startContext();
        this.starting = operation;
        try { await operation; } finally { if (this.starting === operation) this.starting = undefined; }
    }

    private async startContext(): Promise<void> {
        const generation = this.generation;
        const context = new AudioContext({ latencyHint: 'interactive' });
        this.context = context;
        try {
            await context.audioWorklet.addModule(new URL('./audio-worklet.js', import.meta.url));
            if (generation !== this.generation) return;
            this.processor = new AudioWorkletNode(context, 'overte-direct-audio', {
                numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [2],
            });
            this.gain = context.createGain();
            this.gain.gain.value = this.sound ? 1 : 0;
            this.processor.connect(this.gain).connect(context.destination);
            this.processor.port.onmessage = ({ data }) => {
                if (!data || typeof data !== 'object') return;
                const attachment = this.attaching;
                if (data.type === 'audio-port-attached' && attachment && data.id === attachment.id
                        && Number.isSafeInteger(data.epoch) && data.epoch >= 0) {
                    this.audioPortAttached = true;
                    this.audioEpoch = data.epoch;
                    this.attaching = undefined;
                    clearTimeout(attachment.timeout);
                    attachment.resolve();
                } else if (data.type === 'transport-state' && Number.isSafeInteger(data.epoch) && data.epoch >= this.audioEpoch) {
                    this.audioEpoch = data.epoch;
                    if (data.muted === true) this.stopMicrophone();
                } else if (data.type === 'audio-port-error') {
                    this.stopMicrophone();
                    this.onStatus('Voice transport stopped. Reconnect before enabling your microphone again.', 'warning');
                } else if (data.type === 'microphone' && !this.audioPortAttached && !this.attaching && !this.muted
                        && data.buffer instanceof ArrayBuffer && data.buffer.byteLength === 480) {
                    this.sentFrames++;
                    this.send(data.buffer);
                } else if (data.type === 'playback') {
                    this.playedFrames = data.frames;
                    this.playedPeak = data.peak;
                    this.droppedFrames = data.droppedFrames;
                    this.sentFrames = Math.max(this.sentFrames, data.sentMicrophoneFrames ?? data.capturedFrames ?? 0);
                    this.capturedFrames = Math.max(this.capturedFrames, data.capturedFrames ?? 0);
                    this.droppedMicrophoneFrames = data.droppedMicrophoneFrames ?? 0;
                    this.pendingMicrophoneFrames = data.pendingMicrophoneFrames ?? 0;
                    this.receivedFrames = Math.max(this.receivedFrames, data.receivedFrames ?? 0);
                }
            };
            await context.resume();
        } catch (error) {
            if (this.context === context) this.context = undefined;
            if (context.state !== 'closed') await context.close();
            throw error;
        }
    }

    receive(buffer: ArrayBuffer): void {
        if (!this.processor || this.audioPortAttached || buffer.byteLength !== 960) return;
        this.receivedFrames++;
        this.processor.port.postMessage({ type: 'pcm', buffer }, [buffer]);
    }

    // This port joins the AudioWorklet directly to the dedicated session worker.
    // The existing node.port remains the UI's permission/mute/statistics channel.
    // Starting playback here never requests microphone permission.
    async attachAudioPort(port: MessagePort): Promise<void> {
        const generation = this.generation;
        try { await this.start(); } catch (error) { port.close(); throw error; }
        if (generation !== this.generation || !this.processor) {
            port.close(); throw new Error('Audio context closed before voice transport was attached.');
        }
        this.cancelAudioAttachment(new Error('Voice transport attachment superseded.'));
        this.stopMicrophone();
        this.audioPortAttached = false;
        const id = ++this.audioPortSerial;
        await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => {
                if (this.attaching?.id !== id) return;
                this.processor?.port.postMessage({ type: 'detach-audio-port', id });
                this.cancelAudioAttachment(new Error('AudioWorklet did not attach the voice transport.'));
            }, 5000);
            this.attaching = { id, resolve, reject, timeout };
            try { this.processor!.port.postMessage({ type: 'attach-audio-port', id, port }, [port]); }
            catch (error) {
                port.close();
                this.cancelAudioAttachment(error instanceof Error ? error : new Error(String(error)));
            }
        });
    }

    private cancelAudioAttachment(error: Error): void {
        const operation = this.attaching;
        if (!operation) return;
        this.attaching = undefined;
        clearTimeout(operation.timeout);
        operation.reject(error);
    }

    async enableMicrophone(): Promise<boolean> {
        const generation = this.generation;
        this.stopMicrophone();
        const microphoneGeneration = this.microphoneGeneration;
        try {
            if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone requires HTTPS or localhost.');
            await this.start();
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) return false;
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false,
            });
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) {
                stream.getTracks().forEach(track => track.stop()); return false;
            }
            this.microphone = stream;
            this.source = this.context!.createMediaStreamSource(stream);
            this.source.connect(this.processor!);
            this.muted = false;
            this.onMicrophoneChange(false);
            // Tag explicit unmute with the epoch the UI has acknowledged. A
            // queued old permission result cannot revive a leave/NoisyMute gate.
            this.processor!.port.postMessage({ type: 'mute', muted: false, epoch: this.audioEpoch });
            stream.getAudioTracks().forEach(track => { track.onended = () => {
                this.stopMicrophone();
                this.onStatus('Microphone disconnected. Enable it again to resume voice.', 'warning');
            }; });
            this.onStatus('Microphone enabled. Other participants can hear you.', 'info');
            return true;
        } catch (error) {
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) return false;
            this.stopMicrophone();
            const name = error instanceof DOMException ? error.name : '';
            const message = name === 'NotAllowedError'
                ? 'Microphone permission denied. You can still explore and listen; allow microphone access in your browser to talk.'
                : name === 'NotFoundError' ? 'No microphone found. Connect one and try again.'
                : `Microphone unavailable: ${error instanceof Error ? error.message : String(error)}`;
            this.onStatus(message, 'error');
            return false;
        }
    }

    stopMicrophone(): void {
        this.microphoneGeneration++;
        this.muted = true;
        this.onMicrophoneChange(true);
        this.processor?.port.postMessage({ type: 'mute', muted: true });
        this.source?.disconnect();
        this.source = undefined;
        this.microphone?.getTracks().forEach(track => { track.onended = null; track.stop(); });
        this.microphone = undefined;
    }

    setSound(enabled: boolean): void { this.sound = enabled; if (this.gain) this.gain.gain.value = enabled ? 1 : 0; }
    resetPlayback(): void { this.processor?.port.postMessage({ type: 'reset' }); }

    get stats() {
        return { sentFrames: this.sentFrames, receivedFrames: this.receivedFrames, playedFrames: this.playedFrames,
            playedPeak: this.playedPeak, droppedFrames: this.droppedFrames, sampleRate: this.context?.sampleRate,
            microphoneMuted: this.muted, soundEnabled: this.sound, networkSampleRate: 24000,
            transport: this.audioPortAttached ? 'worker' : 'main', audioEpoch: this.audioEpoch,
            capturedFrames: this.capturedFrames, droppedMicrophoneFrames: this.droppedMicrophoneFrames,
            pendingMicrophoneFrames: this.pendingMicrophoneFrames };
    }

    async dispose(): Promise<void> {
        this.generation++;
        this.cancelAudioAttachment(new Error('Audio context closed while attaching voice transport.'));
        this.stopMicrophone();
        this.processor?.port.postMessage({ type: 'detach-audio-port' });
        this.audioPortAttached = false;
        this.processor?.disconnect();
        if (this.processor) this.processor.port.onmessage = null;
        this.processor = undefined;
        const context = this.context;
        this.context = undefined;
        if (context && context.state !== 'closed') await context.close();
    }
}
