// SPDX-License-Identifier: Apache-2.0
export class BrowserAudio {
    private context?: AudioContext;
    private processor?: AudioWorkletNode;
    private microphone?: MediaStream;
    private source?: MediaStreamAudioSourceNode;
    private gain?: GainNode;
    private generation = 0;
    private microphoneGeneration = 0;
    private sentFrames = 0;
    private receivedFrames = 0;
    private playedFrames = 0;
    private playedPeak = 0;
    muted = true;
    sound = true;

    constructor(private send: (data: ArrayBuffer) => void,
                private onStatus: (message: string, kind?: string) => void,
                private onMicrophoneChange: (muted: boolean) => void = () => {}) {}

    async start(): Promise<void> {
        if (this.context) { await this.context.resume(); return; }
        if (!window.AudioContext || !window.isSecureContext) {
            throw new Error('Voice requires HTTPS or localhost and Web Audio support.');
        }
        const generation = this.generation;
        const context = new AudioContext({sampleRate: 48000, latencyHint: 'interactive'});
        this.context = context;
        try {
            await context.audioWorklet.addModule(new URL('./audio-worklet.js', import.meta.url));
            if (generation !== this.generation) return;
            this.processor = new AudioWorkletNode(context, 'overte-audio', {
                numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [2],
            });
            this.gain = context.createGain();
            this.gain.gain.value = this.sound ? 1 : 0;
            this.processor.connect(this.gain).connect(context.destination);
            this.processor.port.onmessage = ({data}) => {
                if (data.type === 'microphone' && !this.muted) {
                    this.sentFrames++;
                    this.send(data.buffer);
                } else if (data.type === 'playback') {
                    this.playedFrames = data.frames;
                    this.playedPeak = data.peak;
                }
            };
            await context.resume();
        } catch (error) {
            if (this.context === context) this.context = undefined;
            await context.close();
            throw error;
        }
    }

    receive(buffer: ArrayBuffer): void {
        if (!this.processor || buffer.byteLength % 4) return;
        this.receivedFrames++;
        this.processor.port.postMessage({type:'pcm', buffer}, [buffer]);
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
                audio: {channelCount:1, echoCancellation:true, noiseSuppression:true, autoGainControl:true},
                video: false,
            });
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) {
                stream.getTracks().forEach(track => track.stop()); return false;
            }
            this.microphone = stream;
            this.source = this.context!.createMediaStreamSource(stream);
            this.source.connect(this.processor!);
            this.muted = false;
            this.onMicrophoneChange(false);
            this.processor!.port.postMessage({type:'mute', muted:false});
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
        this.processor?.port.postMessage({type:'mute', muted:true});
        this.source?.disconnect();
        this.source = undefined;
        this.microphone?.getTracks().forEach(track => { track.onended = null; track.stop(); });
        this.microphone = undefined;
    }

    setSound(enabled: boolean): void {
        this.sound = enabled;
        if (this.gain) this.gain.gain.value = enabled ? 1 : 0;
    }

    get stats(): {sentFrames: number; receivedFrames: number; playedFrames:number; playedPeak:number; sampleRate?: number} {
        return {sentFrames:this.sentFrames, receivedFrames:this.receivedFrames, playedFrames:this.playedFrames,
            playedPeak:this.playedPeak, sampleRate:this.context?.sampleRate};
    }

    async dispose(): Promise<void> {
        this.generation++;
        this.stopMicrophone();
        this.processor?.disconnect();
        if (this.processor) this.processor.port.onmessage = null;
        this.processor = undefined;
        const context = this.context;
        this.context = undefined;
        await context?.close();
    }
}
