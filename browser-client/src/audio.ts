// SPDX-License-Identifier: Apache-2.0
import type {CaptureBinding} from './browser-capture-target';
import {restartConsentedCapture} from './browser-capture-restart';
import type {CaptureChange,CaptureReason} from '../shared/browser-capture.mjs';
export class BrowserAudio {
    private context?: AudioContext;
    private processor?: AudioWorkletNode;
    private microphone?: MediaStream;
    private source?: MediaStreamAudioSourceNode;
    private microphoneGain?: GainNode;
    private capture?: CaptureBinding;
    private captureReconfiguring=false;
    private microphoneRestartPending=false;
    private captureSettings={echoCancellation:true,noiseSuppression:true,autoGainControl:true,inputGainPercent:100};
    private explicitCaptureFields=new Set<'echoCancellation'|'noiseSuppression'|'autoGainControl'>();
    private gain?: GainNode;
    private generation = 0;
    private microphoneGeneration = 0;
    private sentFrames = 0;
    private receivedFrames = 0;
    private playedFrames = 0;
    private playedPeak = 0;
    private transmitEnabled = true;
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
                if (data.type === 'microphone' && !this.muted && this.transmitEnabled && !this.captureReconfiguring) {
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
        // A revoked unresolved browser request still owns its one resource slot.
        if(this.microphoneRestartPending)return false;
        const generation = this.generation;
        this.stopMicrophone();
        const microphoneGeneration = this.microphoneGeneration;
        try {
            if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone requires HTTPS or localhost.');
            await this.start();
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) return false;
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {channelCount:1,...Object.fromEntries((['echoCancellation','noiseSuppression','autoGainControl'] as const).map(field=>[field,this.explicitCaptureFields.has(field)?{exact:this.captureSettings[field]}:this.captureSettings[field]]))},
                video: false,
            });
            if (generation !== this.generation || microphoneGeneration !== this.microphoneGeneration) {
                stream.getTracks().forEach(track => track.stop()); return false;
            }
            this.microphone = stream;
            this.source = this.context!.createMediaStreamSource(stream);
            const tracks=stream.getAudioTracks();
            if(tracks.length!==1||tracks[0].readyState!=='live')throw Error('The browser microphone did not supply one live audio track.');
            const track=tracks[0],settings=track.getSettings();
            for(const field of this.explicitCaptureFields)if(settings[field]!==this.captureSettings[field])throw Error('The browser could not confirm the selected microphone processing.');
            const gain=this.context!.createGain();this.microphoneGain=gain;gain.gain.value=this.captureSettings.inputGainPercent/100;
            this.source.connect(gain).connect(this.processor!);
            const binding:CaptureBinding={track,gain,current:()=>generation===this.generation&&microphoneGeneration===this.microphoneGeneration&&this.capture===binding&&!this.muted,
                inhibit:held=>{if(this.capture!==binding)return;this.captureReconfiguring=held;this.processor?.port.postMessage({type:'mute',muted:this.muted||!this.transmitEnabled||held});},
                stop:()=>{if(this.capture===binding)this.stopMicrophone();},
                restartProcessing:(change,current)=>this.restartProcessing(binding,change,current),
                committed:change=>{if(!binding.current())return;if(change.field==='inputGainPercent')this.captureSettings.inputGainPercent=change.value;else{this.captureSettings[change.field]=change.value;this.explicitCaptureFields.add(change.field);}}};
            this.capture=binding;
            this.muted = false;
            this.onMicrophoneChange(false);
            this.processor!.port.postMessage({type:'mute', muted:!this.transmitEnabled||this.captureReconfiguring});
            this.watchMicrophone(stream,track,binding);
            this.onStatus(this.transmitEnabled ? 'Microphone enabled. Other participants can hear you.' : 'Microphone ready. Voice transmission is waiting for the native voice control.', 'info');
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

    private watchMicrophone(stream:MediaStream,track:MediaStreamTrack,binding:CaptureBinding):void {
        track.onended=()=>{
            // A queued ended event from the retired source cannot stop its replacement.
            if(!binding.current()||this.microphone!==stream||this.capture!==binding||binding.track!==track)return;
            this.stopMicrophone();
            this.onStatus('Microphone disconnected. Enable it again to resume voice.', 'warning');
        };
    }

    private async restartProcessing(binding:CaptureBinding,change:CaptureChange,current:()=>boolean):Promise<CaptureReason>{
        if(this.microphoneRestartPending)return 'busy';
        const context=this.context,processor=this.processor,stream=this.microphone,source=this.source;
        if(!context||!processor||!stream||!source||!binding.current()||!current())return 'inactive';
        this.microphoneRestartPending=true;
        try{return await restartConsentedCapture(binding.track,change,{
            current:()=>binding.current()&&current()&&this.context===context&&this.processor===processor,
            acquire:constraints=>navigator.mediaDevices.getUserMedia(constraints),
            retire:()=>{
                source.disconnect();this.source=undefined;this.microphone=undefined;
                for(const track of stream.getTracks()){track.onended=null;track.stop();}
            },
            publish:(replacement,track)=>{
                const valid=()=>binding.current()&&current()&&this.context===context&&this.processor===processor;
                if(!valid())throw Error('Capture ownership changed.');
                const next=context.createMediaStreamSource(replacement);
                try{next.connect(binding.gain);if(!valid())throw Error('Capture ownership changed.');}catch(error){next.disconnect();throw error;}
                // Keep the existing input gain, worklet and PTT/transmission ownership.
                this.source=next;this.microphone=replacement;binding.track=track;
                this.watchMicrophone(replacement,track,binding);
            },
            stop:()=>{if(this.capture===binding)this.stopMicrophone();},
        });}finally{this.microphoneRestartPending=false;}
    }

    stopMicrophone(): void {
        this.microphoneGeneration++;
        this.muted = true;
        this.onMicrophoneChange(true);
        this.processor?.port.postMessage({type:'mute', muted:true});
        this.source?.disconnect();
        this.source = undefined;
        this.capture=undefined;this.captureReconfiguring=false;
        this.microphoneGain?.disconnect();this.microphoneGain=undefined;
        this.microphone?.getTracks().forEach(track => { track.onended = null; track.stop(); });
        this.microphone = undefined;
    }

    captureBinding():CaptureBinding|undefined {return this.capture?.current()?this.capture:undefined;}

    setTransmitEnabled(enabled:boolean):void {
        this.transmitEnabled=enabled;
        this.processor?.port.postMessage({type:'mute',muted:this.muted||!enabled||this.captureReconfiguring});
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
