// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {validateBrowserGraphics,validateBrowserGraphicsRequest,type BrowserGraphicsSettings,type BrowserGraphicsResult} from '../shared/browser-graphics.mjs';
export interface BrowserGraphicsTarget {
    snapshot():BrowserGraphicsSettings;
    apply(settings:BrowserGraphicsSettings):void;
}
export interface GraphicsAcknowledgement extends BrowserGraphicsResult {type:'tablet';action:'graphicsResult';revision:number}
/** One World/visitor instance. Authority revocation cancels every pending result. */
export class BrowserGraphicsController {
    private closed=false;
    private revision=0;
    private allowed=false;
    private lastRequest=0;
    constructor(private target:BrowserGraphicsTarget,private current:(revision:number)=>boolean,private changed?:(settings:BrowserGraphicsSettings)=>void){}
    setAuthority(revision:number,allowed:boolean):void {
        if(this.closed)return;
        if(!Number.isSafeInteger(revision)||revision<1){revision=0;allowed=false;}
        if(this.revision!==revision||this.allowed!==allowed){this.revision=revision;this.allowed=allowed;this.lastRequest=0;}
    }
    receive(input:unknown,revision:number):GraphicsAcknowledgement|undefined {
        if(!this.active(revision))return;
        const request=validateBrowserGraphicsRequest(input);
        if(request.requestId<=this.lastRequest)return;
        this.lastRequest=request.requestId;
        const before=validateBrowserGraphics(this.target.snapshot());
        let accepted=true,desired=before;
        if(request.operation==='change'){
            const candidate=validateBrowserGraphics({...before,[request.field]:request.value});desired=candidate;
            if(!this.active(revision))return;
            try{this.target.apply(candidate);}catch{accepted=false;}
        }
        if(!this.active(revision))return;
        // Read the actual target after apply, including a partial failed apply.
        const settings=validateBrowserGraphics(this.target.snapshot());
        if(request.operation==='change'&&Object.keys(desired).some(key=>settings[key as keyof BrowserGraphicsSettings]!==desired[key as keyof BrowserGraphicsSettings]))accepted=false;
        if(!this.active(revision))return;
        let persistenceWarning=false;
        if(accepted&&request.operation==='change'){try{this.changed?.({...settings});}catch{persistenceWarning=true;}}
        if(!this.active(revision))return;
        return {type:'tablet',action:'graphicsResult',revision,schemaVersion:1,requestId:request.requestId,accepted,settings,...(accepted?(persistenceWarning?{message:'The setting was applied, but the browser could not save it.'}:{}):{message:'The browser could not apply that graphics setting.'})};
    }
    private active(revision:number):boolean{return !this.closed&&this.allowed&&revision===this.revision&&this.current(revision);}
    close():void{this.closed=true;this.allowed=false;this.lastRequest=0;}
}
