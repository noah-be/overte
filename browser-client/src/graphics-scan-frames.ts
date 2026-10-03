// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export interface GraphicsScanFrame {timestampMs:number;cpuSubmitMs:number;ready:boolean}
export class GraphicsScanCapacityError extends Error {constructor(){super('A graphics scan is already observing this World');this.name='GraphicsScanCapacityError';}}
/** Only the existing World render-success branch may publish. Never renders or schedules RAF. */
export class GraphicsScanFrames {
    private observer?:{frame:(value:GraphicsScanFrame)=>void;cancel:()=>void};
    private closed=false;
    constructor(readonly signal:AbortSignal){signal.addEventListener('abort',this.close,{once:true});if(signal.aborted)this.close();}
    get active(){return !this.closed&&!!this.observer;}
    subscribe(frame:(value:GraphicsScanFrame)=>void,cancel:()=>void):()=>void {
        if(this.closed)throw new DOMException('World closed','AbortError');if(this.observer)throw new GraphicsScanCapacityError();
        const owner={frame,cancel};this.observer=owner;return()=>{if(this.observer===owner)this.observer=undefined;};
    }
    publish(value:GraphicsScanFrame):void {const owner=this.observer;if(!owner)return;try{owner.frame(value);}catch{if(this.observer===owner)this.observer=undefined;try{owner.cancel();}catch{/* Diagnostics cannot interrupt the existing renderer. */}}}
    cancel():void{const owner=this.observer;this.observer=undefined;try{owner?.cancel();}catch{/* Cancellation does not alter rendering. */}}
    dispose():void{this.close();}
    private close=()=>{if(this.closed)return;this.closed=true;const owner=this.observer;this.observer=undefined;this.signal.removeEventListener('abort',this.close);try{owner?.cancel();}catch{/* A diagnostic observer cannot break World cleanup. */}};
}
