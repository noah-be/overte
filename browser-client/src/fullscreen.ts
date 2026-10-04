// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Browser-owned current-screen fullscreen. No native screen selection or keyboard lock. */
export interface FullscreenDocument extends EventTarget {
    readonly fullscreenEnabled:boolean;
    readonly fullscreenElement:Element|null;
    exitFullscreen():Promise<void>;
}
export interface FullscreenTarget {
    readonly ownerDocument:FullscreenDocument;
    readonly isConnected:boolean;
    requestFullscreen():Promise<void>;
}
export interface FullscreenState {
    readonly available:boolean;
    readonly active:boolean;
    readonly pending:boolean;
    readonly message:string;
}
interface Lease {owner:object;busy:boolean;owned:boolean;connected:boolean;notify?:()=>void;}
const leases=new WeakMap<object,Lease>();
const REFUSED='The browser could not enter or leave fullscreen. Try the button again.';
/** Cleanup is shared by same-target replacements, without retaining a disposed UI observer. */
function releaseOwnedFullscreen(document:FullscreenDocument,target:FullscreenTarget,lease:Lease):void {
    if(!lease.owned||lease.busy||document.fullscreenElement!==target as unknown as Element)return;
    lease.owned=false;lease.busy=true;
    const finished=()=>{lease.busy=false;lease.notify?.();};
    try{void Promise.resolve(document.exitFullscreen()).then(finished,finished);}
    catch{finished();}
}
/** invoke() must be called directly from the browser button's trusted click handler. */
export class BrowserFullscreen {
    private readonly document:FullscreenDocument;
    private readonly lease:Lease;
    private readonly owner={};
    private connected=false;
    private disposed=false;
    private epoch=0;
    private waiting?:()=>void;
    private message='';
    private readonly changed=()=>this.publish();
    private readonly escape=(event:Event):void=>{
        const key=event as KeyboardEvent;
        if(event.type!=='keydown'||event.isTrusted!==true||key.key!=='Escape'||key.repeat!==false||key.isComposing!==false||key.defaultPrevented
            ||key.altKey!==false||key.ctrlKey!==false||key.metaKey!==false||key.shiftKey!==false
            ||this.disposed||!this.connected||this.lease.owner!==this.owner||!this.lease.connected||!this.lease.owned||this.lease.busy
            ||!this.snapshot().available||this.document.fullscreenElement!==this.target as unknown as Element)return;
        // An application Escape action exits only this established owned view.
        // Preserve the same real API/wait/deadline path as the visible button.
        event.preventDefault();void this.change(false);
    };
    constructor(private target:FullscreenTarget,private onState:(state:FullscreenState)=>void,private deadlineMs=8000){
        if(!Number.isInteger(deadlineMs)||deadlineMs<1||deadlineMs>8000)throw Error('Invalid fullscreen deadline');
        this.document=target.ownerDocument;
        this.lease=leases.get(target)??{owner:this.owner,busy:false,owned:false,connected:false};
        this.lease.owner=this.owner;this.lease.connected=false;this.lease.notify=()=>this.publish();leases.set(target,this.lease);
        this.document.addEventListener('fullscreenchange',this.changed);
        this.document.addEventListener('fullscreenerror',this.changed);
        this.document.addEventListener('keydown',this.escape,true);
    }
    snapshot():FullscreenState {
        return {available:this.connected&&!this.disposed&&this.target.isConnected&&this.target.ownerDocument===this.document&&this.document.fullscreenEnabled===true&&typeof this.target.requestFullscreen==='function'&&typeof this.document.exitFullscreen==='function',
            active:this.document.fullscreenElement===this.target as unknown as Element,pending:this.lease.busy,
            message:this.message||(!this.document.fullscreenEnabled?'Fullscreen is unavailable in this browser or embedding.':'')};
    }
    private publish():void {if(!this.disposed){try{this.onState(this.snapshot());}catch{/* A UI observer cannot strand an already requested browser operation. */}}}
    setConnected(value:boolean):void {
        if(this.disposed||this.connected===value)return;
        this.connected=value;this.epoch++;this.waiting?.();this.message='';
        if(this.lease.owner===this.owner)this.lease.connected=value;
        if(!value)this.releaseOwned();
        this.publish();
    }
    invoke(event:Pick<Event,'isTrusted'|'type'>):Promise<boolean> {
        if(this.disposed||!this.connected||event.type!=='click'||event.isTrusted!==true||!this.snapshot().available)return Promise.resolve(false);
        if(this.lease.owner!==this.owner||this.lease.busy){this.message='A fullscreen change is still pending.';this.publish();return Promise.resolve(false);}
        const before=this.document.fullscreenElement;
        if(before!==null&&before!==this.target as unknown as Element){this.message='Exit the other fullscreen view before opening Overte fullscreen.';this.publish();return Promise.resolve(false);}
        return this.change(before===null);
    }
    private change(entering:boolean):Promise<boolean> {
        const epoch=this.epoch;
        this.lease.busy=true;this.message='';
        let operation:Promise<void>;
        // Calling the real API before any await preserves transient activation.
        try{operation=entering?this.target.requestFullscreen():this.document.exitFullscreen();}
        catch{this.lease.busy=false;this.message=REFUSED;this.publish();return Promise.resolve(false);}
        this.publish();
        return this.wait(operation,epoch,entering);
    }
    private wait(operation:Promise<void>,epoch:number,entering:boolean):Promise<boolean> {
        return new Promise(resolve=>{
            let settled=false;
            const finish=(accepted:boolean,message='')=>{
                if(settled)return;settled=true;clearTimeout(timer);if(this.waiting===cancel)this.waiting=undefined;
                if(!this.disposed&&epoch===this.epoch){this.message=message;this.publish();}resolve(accepted);
            };
            const cancel=()=>finish(false);
            const timer=setTimeout(()=>finish(false,'The browser has not finished fullscreen within 8 seconds. Reload the page if it remains pending.'),this.deadlineMs);
            this.waiting=cancel;
            if(this.disposed||!this.connected||epoch!==this.epoch)cancel();
            void Promise.resolve(operation).then(()=>{
                this.lease.busy=false;
                const active=this.document.fullscreenElement===this.target as unknown as Element;
                const current=!this.disposed&&this.connected&&epoch===this.epoch&&this.lease.owner===this.owner;
                if(entering&&active)this.lease.owned=true;
                if(!entering)this.lease.owned=false;
                if(!current){
                    if(this.lease.owner===this.owner)this.releaseOwned();
                    else if(!this.lease.connected)releaseOwnedFullscreen(this.document,this.target,this.lease);
                    this.lease.notify?.();finish(false);return;
                }
                if(settled)this.message=entering===active?'Fullscreen changed after the browser confirmation deadline.':REFUSED;
                finish(entering===active,entering===active?'':REFUSED);this.publish();
            },()=>{this.lease.busy=false;finish(false,REFUSED);this.lease.notify?.();});
        });
    }
    private releaseOwned():void {
        if(this.lease.owner===this.owner)releaseOwnedFullscreen(this.document,this.target,this.lease);
    }
    dispose():void {
        if(this.disposed)return;
        if(this.lease.owner===this.owner)this.lease.connected=false;
        this.connected=false;this.epoch++;this.waiting?.();this.releaseOwned();this.disposed=true;
        if(this.lease.owner===this.owner)this.lease.notify=undefined;
        this.document.removeEventListener('fullscreenchange',this.changed);
        this.document.removeEventListener('fullscreenerror',this.changed);
        this.document.removeEventListener('keydown',this.escape,true);
    }
}
