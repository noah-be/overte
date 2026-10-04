// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type {TabletMessage} from './tablet-protocol';
type SnapshotRequest=Extract<TabletMessage,{kind:'snapshot'}>;
export async function cropSceneSnapshot(blob:Blob,aspectRatio:number):Promise<Blob>{
    const image=await createImageBitmap(blob);
    try {
        const width=Math.max(1,Math.floor(Math.min(image.width,image.height*aspectRatio)));
        const height=Math.max(1,Math.floor(Math.min(image.height,image.width/aspectRatio)));
        const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
        const context=canvas.getContext('2d');if(!context)throw Error('Snapshot canvas is unavailable');
        context.drawImage(image,(image.width-width)/2,(image.height-height)/2,width,height,0,0,width,height);
        return await new Promise<Blob>((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(Error('The scene could not be exported')),'image/png'));
    }finally{image.close();}
}
/** Exports the visitor's local world; no native world framebuffer is captured. */
export class TabletSnapshots {
    private active?:AbortController;private request?:SnapshotRequest;private worker?:Worker;private urls:string[]=[];private downloads:HTMLElement;
    constructor(toolbar:HTMLElement,private options:{captureScene?:()=>Promise<Blob>;fileURL?:(name?:string)=>string;send:(value:Record<string,unknown>)=>void;onStatus:(value:string)=>void}){
        this.downloads=document.createElement('span');this.downloads.setAttribute('aria-label','Scene snapshot downloads');toolbar.append(this.downloads);
    }
    private async upload(name:string,blob:Blob,signal:AbortSignal):Promise<void>{
        if(!this.options.fileURL)throw Error('Visitor snapshot files are unavailable');
        const response=await fetch(this.options.fileURL(name),{method:'PUT',body:blob,signal});
        if(!response.ok)throw Error(`Snapshot upload failed (${response.status})`);
    }
    private link(name:string,blob:Blob):void{
        const url=URL.createObjectURL(blob);this.urls.push(url);const link=document.createElement('a');link.href=url;link.download=name;
        link.textContent=name.endsWith('.gif')?'Download animated snapshot':'Download still snapshot';link.style.margin='0 8px';this.downloads.append(link);
    }
    async capture(request:SnapshotRequest):Promise<void>{
        this.cancel();const active=new AbortController();this.active=active;this.request=request;const signal=active.signal;
        const valid=()=>{if(signal.aborted)throw new DOMException('Snapshot cancelled','AbortError');};
        const send=(value:Record<string,unknown>)=>{valid();this.options.send({action:'snapshotResult',requestId:request.requestId,...value});};
        try {
            if(!this.options.captureScene)throw Error('Browser scene capture is unavailable');
            this.options.onStatus(request.animated?'Recording a five-second animated scene snapshot…':'Capturing the browser scene…');
            valid();const still=await cropSceneSnapshot(await this.options.captureScene(),request.aspectRatio);valid();
            const prefix=`overte-snapshot-${Date.now()}-${request.requestId}`,stillName=`${prefix}.png`;let gif:Blob|undefined;
            if(request.animated){
                const worker=new Worker(new URL('./tablet-gif.worker.ts',import.meta.url),{type:'module'});this.worker=worker;let id=0;
                const ask=(action:string,value:Record<string,unknown>={})=>new Promise<any>((resolve,reject)=>{
                    const requestId=++id;let timer:ReturnType<typeof setTimeout>;
                    const cleanup=()=>{clearTimeout(timer);worker.removeEventListener('message',message);worker.removeEventListener('error',error);signal.removeEventListener('abort',abort);};
                    const message=(event:MessageEvent)=>{if(event.data.id!==requestId)return;cleanup();event.data.error?reject(Error(event.data.error)):resolve(event.data);};
                    const error=(event:ErrorEvent)=>{cleanup();reject(Error(event.message||'Animated snapshot encoder failed'));};
                    const abort=()=>{cleanup();reject(new DOMException('Snapshot cancelled','AbortError'));};
                    worker.addEventListener('message',message);worker.addEventListener('error',error);signal.addEventListener('abort',abort,{once:true});
                    timer=setTimeout(()=>{cleanup();reject(Error('Animated snapshot encoding timed out'));},10000);
                    worker.postMessage({id:requestId,action,...value});
                });
                const started=performance.now();let previous=started,frames=0;
                do {
                    valid();const now=performance.now();
                    const frame=frames?await cropSceneSnapshot(await this.options.captureScene(),request.aspectRatio):still;valid();
                    await ask('frame',{blob:frame,delay:Math.max(100,now-previous)});previous=now;frames++;
                    if(frames<50&&performance.now()-started<5000)await new Promise<void>(resolve=>setTimeout(resolve,Math.max(0,100-(performance.now()-now))));
                }while(frames<50&&(frames<2||performance.now()-started<5000));
                valid();const result=await ask('finish');gif=new Blob([result.bytes],{type:'image/gif'});worker.terminate();this.worker=undefined;
            }
            await this.upload(stillName,still,signal);valid();
            const gifName=gif?`${prefix}.gif`:undefined;if(gif&&gifName)await this.upload(gifName,gif,signal);valid();
            this.downloads.replaceChildren();this.urls.forEach(url=>URL.revokeObjectURL(url));this.urls=[];this.link(stillName,still);if(gif&&gifName)this.link(gifName,gif);
            send({stillName,...(gifName?{gifName}:{})});this.options.onStatus('Browser scene snapshot saved. Use the download links in the tablet.');
        }catch(error){
            if(!signal.aborted){const message=error instanceof Error?error.message:String(error);send({error:message.slice(0,512)});this.options.onStatus(`Snapshot failed: ${message}`);}
        }finally{if(this.active===active){this.worker?.terminate();this.worker=undefined;this.active=undefined;this.request=undefined;}}
    }
    cancel(notify=false):void{if(notify&&this.request)this.options.send({action:'snapshotResult',requestId:this.request.requestId,error:'Snapshot cancelled.'});this.request=undefined;this.active?.abort();this.worker?.terminate();this.worker=undefined;this.active=undefined;}
    dispose():void{this.cancel();this.urls.forEach(url=>URL.revokeObjectURL(url));this.urls=[];this.downloads.remove();}
}
