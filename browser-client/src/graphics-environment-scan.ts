// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {validateBrowserGraphics,type BrowserGraphicsSettings} from '../shared/browser-graphics.mjs';
import {GraphicsScanFrames,GraphicsScanCapacityError,type GraphicsScanFrame} from './graphics-scan-frames';
export interface GraphicsScanCapabilities {webgl2:boolean;contextAntialias:boolean|null;maximumTextureDimension:number;maximumRenderbufferDimension:number;maximumViewportWidth:number;maximumViewportHeight:number;drawingBufferWidth:number;drawingBufferHeight:number}
export interface GraphicsScanHost {
    frames:GraphicsScanFrames;document:Pick<Document,'visibilityState'|'addEventListener'|'removeEventListener'>;
    current():boolean;presentationVisible():boolean;settings():BrowserGraphicsSettings;capabilities():GraphicsScanCapabilities;
    /** Apply through the ordinary owned graphics target and persistence path. Never native Render.*. */
    applyResolution(percent:number):Promise<BrowserGraphicsSettings>;
}
export interface GraphicsScanReport {
    version:1;scope:'sampled-current-visible-scene';capabilities:GraphicsScanCapabilities;settings:BrowserGraphicsSettings;
    frameIntervals:number;elapsedMs:number;observedCadenceHz:number;p95IntervalMs:number;maximumIntervalMs:number;meanCpuSubmitMs:number;
    defaultRecommendation:'keep-current-settings';optionalResolutionPercent:number|null;explanation:string;
}
export type GraphicsScanResult={status:'complete';report:GraphicsScanReport}|{status:'cancelled'|'inconclusive'|'refused';reason:string};
const equal=(a:BrowserGraphicsSettings,b:BrowserGraphicsSettings)=>a.fieldOfView===b.fieldOfView&&a.resolutionPercent===b.resolutionPercent&&a.localLights===b.localLights&&a.cameraClipping===b.cameraClipping;
function capability(value:GraphicsScanCapabilities):GraphicsScanCapabilities {
    if(!value||typeof value.webgl2!=='boolean'||(typeof value.contextAntialias!=='boolean'&&value.contextAntialias!==null))throw Error('Invalid capability response');
    const out={webgl2:value.webgl2,contextAntialias:value.contextAntialias} as GraphicsScanCapabilities;
    for(const key of ['maximumTextureDimension','maximumRenderbufferDimension','maximumViewportWidth','maximumViewportHeight','drawingBufferWidth','drawingBufferHeight'] as const){const n=value[key];if(!Number.isInteger(n)||n<1||n>65536)throw Error('Invalid graphics dimension');out[key]=n;}
    return out;
}
/** Explicit request only; at most one≤512 interval sample,2s observed span/5s wall. */
export class GraphicsEnvironmentScan {
    private disposed=false;private applying=false;private cancelPending?:()=>void;private result?:GraphicsScanReport;private resultAt=0;private serial=0;
    constructor(private host:GraphicsScanHost,private deadlineMs=5000,private now=()=>performance.now()){if(!Number.isInteger(deadlineMs)||deadlineMs<1||deadlineMs>5000)throw Error('Invalid graphics scan deadline');}
    async scan():Promise<GraphicsScanResult>{
        try{if(this.disposed||this.cancelPending||this.applying||this.serial>=Number.MAX_SAFE_INTEGER||!this.host.current()||this.host.document.visibilityState!=='visible'||!this.host.presentationVisible())return {status:'refused',reason:'A scan requires the current visible World and no other scan or pending setting confirmation.'};}catch{return {status:'refused',reason:'The current visible World could not be read safely.'};}
        this.result=undefined;let settings:BrowserGraphicsSettings,caps:GraphicsScanCapabilities;
        try{settings=validateBrowserGraphics(this.host.settings());caps=capability(this.host.capabilities());}catch{return {status:'refused',reason:'The browser could not report its effective graphics environment.'};}
        if(!caps.webgl2)return {status:'refused',reason:'This client requires an actual WebGL2 renderer.'};
        const serial=++this.serial;
        return new Promise(resolve=>{
            let done=false,remove:(()=>void)|undefined,first:number|undefined,last:number|undefined,cpuSum=0;const intervals:number[]=[];
            const finish=(input:GraphicsScanResult)=>{if(done)return;let value=input;let completedAt=0;if(value.status==='complete'){try{completedAt=this.now();if(!Number.isFinite(completedAt)||completedAt<0)throw Error('Invalid sample clock');if(!this.current(settings,serial))value={status:'cancelled',reason:'The scan owner changed; the scan did not request another setting change.'};}catch{value={status:'refused',reason:'The current graphics environment could not be read safely.'};}}done=true;clearTimeout(timer);remove?.();this.host.document.removeEventListener('visibilitychange',hidden);if(this.cancelPending===cancel)this.cancelPending=undefined;if(value.status==='complete'){this.result=Object.freeze({...value.report,settings:Object.freeze({...value.report.settings}),capabilities:Object.freeze({...value.report.capabilities})});this.resultAt=completedAt;}resolve(value);};
            const cancel=()=>finish({status:'cancelled',reason:'The scan was cancelled; the scan did not request another setting change.'});
            const hidden=()=>{if(this.host.document.visibilityState!=='visible')cancel();};
            const timer=setTimeout(()=>finish({status:'inconclusive',reason:'The visible World did not provide enough completed frames within 5 seconds.'}),this.deadlineMs);
            this.cancelPending=cancel;this.host.document.addEventListener('visibilitychange',hidden);
            try{remove=this.host.frames.subscribe((frame:GraphicsScanFrame)=>{
                try{
                    if(!this.current(settings,serial)||this.host.document.visibilityState!=='visible'||!this.host.presentationVisible()){cancel();return;}
                    if(!frame.ready){finish({status:'inconclusive',reason:'Model jobs or shaders are still loading. Images/materials may continue arriving after those jobs become idle.'});return;}
                    if(!Number.isFinite(frame.timestampMs)||!Number.isFinite(frame.cpuSubmitMs)||frame.cpuSubmitMs<0||frame.cpuSubmitMs>5000||frame.timestampMs<0||(last!==undefined&&frame.timestampMs<=last)){finish({status:'inconclusive',reason:'The renderer did not provide valid consecutive timing samples.'});return;}
                    if(first===undefined){first=last=frame.timestampMs;return;}
                    const delta=frame.timestampMs-last!;last=frame.timestampMs;intervals.push(delta);cpuSum+=frame.cpuSubmitMs;
                    const elapsed=last-first;
                    if(elapsed>=2000&&intervals.length>=12){
                        const sorted=[...intervals].sort((a,b)=>a-b),p95=sorted[Math.ceil(sorted.length*.95)-1],hz=intervals.length*1000/elapsed;
                        const slow=hz<30||p95>50,optional=slow&&settings.resolutionPercent>10?Math.max(10,settings.resolutionPercent-10):null;
                        finish({status:'complete',report:{version:1,scope:'sampled-current-visible-scene',capabilities:caps,settings:{...settings},frameIntervals:intervals.length,elapsedMs:elapsed,observedCadenceHz:hz,p95IntervalMs:p95,maximumIntervalMs:sorted.at(-1)!,meanCpuSubmitMs:cpuSum/intervals.length,
                            defaultRecommendation:'keep-current-settings',optionalResolutionPercent:optional,
                            explanation:optional===null?'Keep the current settings. This short sample describes only the visible view, not every world or the GPU.':`Keep the current settings by default. Optional: try ${optional}% resolution and scan again. This reduces pixel work and may not help CPU or other bottlenecks; no setting was changed.`}});return;
                    }
                    if(intervals.length>=512)finish({status:'inconclusive',reason:'The bounded frame sample filled before a representative 2 second span.'});
                }catch{finish({status:'refused',reason:'The current graphics environment could not be read safely.'});}
            },cancel);}catch(error){finish({status:'refused',reason:error instanceof GraphicsScanCapacityError?'Another graphics scan owns this World.':'The current World cannot be sampled.'});}
        });
    }
    private current(settings:BrowserGraphicsSettings,serial:number):boolean {return !this.disposed&&serial===this.serial&&this.host.current()&&equal(settings,validateBrowserGraphics(this.host.settings()));}
    /** A separate explicit browser click may apply only the offered density. */
    async applyOptionalResolution():Promise<{accepted:boolean;settings?:BrowserGraphicsSettings;message:string}>{
        const report=this.result;let ownsApply=false;
        try{
            if(this.applying||!report||!Number.isFinite(this.now())||this.now()-this.resultAt<0||this.now()-this.resultAt>30000||report.optionalResolutionPercent===null||!this.current(report.settings,this.serial)||this.host.document.visibilityState!=='visible')return {accepted:false,message:'Scan the current World before applying a suggestion.'};
            const serial=this.serial;this.applying=true;ownsApply=true;this.result=undefined;
            const next=validateBrowserGraphics(await this.host.applyResolution(report.optionalResolutionPercent));
            if(this.disposed||serial!==this.serial||!this.host.current())return {accepted:false,message:'The graphics owner changed while applying the suggestion.'};
            const wanted={...report.settings,resolutionPercent:report.optionalResolutionPercent};
            this.result=undefined;
            return equal(next,wanted)?{accepted:true,settings:next,message:'The optional resolution was applied. Scan again to check its effect.'}:{accepted:false,settings:next,message:'The browser did not apply the suggested resolution.'};
        }catch{return {accepted:false,message:'The browser/native confirmation did not finish. Check the effective graphics settings.'};}
        finally{if(ownsApply)this.applying=false;}
    }
    get sampling():boolean{return !!this.cancelPending;}
    cancel():void{this.serial=Math.min(Number.MAX_SAFE_INTEGER,this.serial+1);this.cancelPending?.();this.result=undefined;}
    dispose():void{if(this.disposed)return;this.cancel();this.disposed=true;}
}
