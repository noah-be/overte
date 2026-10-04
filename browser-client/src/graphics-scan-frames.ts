// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export interface GraphicsScanFrame {timestampMs:number;cpuSubmitMs:number;ready:boolean}
export class GraphicsScanCapacityError extends Error {constructor(){super('A graphics scan is already observing this World');this.name='GraphicsScanCapacityError';}}
/** Only the existing World render-success branch may publish. Never renders or schedules RAF. */
export class GraphicsScanFrames {
    private observer?:{frame:(value:GraphicsScanFrame)=>void;cancel:()=>void;epoch:number};
    private closed=false;
    private suspended=false;
    private epoch=0;
    constructor(readonly signal:AbortSignal,private readonly contextAvailable:()=>boolean=()=>true){signal.addEventListener('abort',this.close,{once:true});if(signal.aborted)this.close();}
    /** Unknown/unreadable state refuses and revokes even before a queued DOM loss event. */
    get contextEpoch():number|undefined {
        if(this.closed||this.suspended)return undefined;
        let available=false;try{available=this.contextAvailable()===true;}catch{/* Unreadable context cannot grant frames. */}
        if(!available){this.suspendContext();return undefined;}
        return this.closed||this.suspended?undefined:this.epoch;
    }
    get active(){return this.contextEpoch!==undefined&&!!this.observer;}
    suspendContext():void {
        if(this.closed||this.suspended)return;
        this.suspended=true;
        if(this.epoch>=Number.MAX_SAFE_INTEGER){this.close();return;}
        this.epoch++;this.cancel();
    }
    /** The World calls this only after its owned actual restored event and public GL check. */
    resumeContext():boolean {
        if(this.closed)return false;
        let available=false;try{available=this.contextAvailable()===true;}catch{/* Restoration remains unconfirmed. */}
        if(!available||this.closed||this.signal.aborted)return false;
        this.suspended=false;return true;
    }
    subscribe(frame:(value:GraphicsScanFrame)=>void,cancel:()=>void):()=>void {
        const epoch=this.contextEpoch;
        if(epoch===undefined)throw new DOMException('World graphics unavailable','AbortError');if(this.observer)throw new GraphicsScanCapacityError();
        const owner={frame,cancel,epoch};this.observer=owner;return()=>{if(this.observer===owner)this.observer=undefined;};
    }
    publish(value:GraphicsScanFrame):void {
        const owner=this.observer;if(!owner)return;
        const epoch=this.contextEpoch;if(this.observer!==owner||epoch!==owner.epoch)return;
        try{owner.frame(value);}catch{if(this.observer===owner)this.observer=undefined;try{owner.cancel();}catch{/* Diagnostics cannot interrupt the existing renderer. */}}
    }
    cancel():void{const owner=this.observer;this.observer=undefined;try{owner?.cancel();}catch{/* Cancellation does not alter rendering. */}}
    dispose():void{this.close();}
    private close=()=>{if(this.closed)return;this.closed=true;const owner=this.observer;this.observer=undefined;this.signal.removeEventListener('abort',this.close);try{owner?.cancel();}catch{/* A diagnostic observer cannot break World cleanup. */}};
}
