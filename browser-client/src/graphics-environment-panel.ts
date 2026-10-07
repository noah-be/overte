// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {GraphicsEnvironmentScan} from './graphics-environment-scan';
/** Static browser-owned Tablet panel. Closing/reopening native Tablet may return Home. */
export class GraphicsEnvironmentPanel {
    private root=document.createElement('section');private scan=document.createElement('button');private apply=document.createElement('button');
    private status=document.createElement('span');private closed=false;private serial=0;private applying=false;
    constructor(toolbar:HTMLElement,private scanner:GraphicsEnvironmentScan,private options:{
        /** Synchronously close the owned Tablet so the existing World renders visibly. */
        showWorld():void;
        /** Reopen only if the same session/user scan still owns this action. Native open returns Home. */
        showResultIfCurrent():void;
    }){
        this.root.setAttribute('aria-label','Browser graphics environment');Object.assign(this.root.style,{display:'flex',flexWrap:'wrap',gap:'8px',alignItems:'center',width:'100%'});
        this.scan.type=this.apply.type='button';this.scan.textContent='Scan browser graphics';this.apply.textContent='Apply optional resolution';this.apply.disabled=true;
        this.status.setAttribute('role','status');Object.assign(this.status.style,{overflowWrap:'anywhere',flex:'1 1 180px',maxWidth:'100%'});
        this.status.textContent='Scan the visible World for 2 seconds. Current settings stay unchanged.';
        this.root.append(this.scan,this.apply,this.status);toolbar.append(this.root);
        this.scan.addEventListener('click',()=>{void this.run();});
        this.apply.addEventListener('click',()=>{if(this.closed||this.applying)return;this.applying=true;this.scan.disabled=true;this.apply.disabled=true;const serial=this.serial;this.status.textContent='Waiting for the browser and native Graphics app to confirm…';void this.scanner.applyOptionalResolution().then(result=>{if(!this.closed&&serial===this.serial)this.status.textContent=result.message;}).finally(()=>{this.applying=false;if(!this.closed)this.scan.disabled=this.scanner.sampling;});});
    }
    private async run():Promise<void>{
        if(this.closed||this.scan.disabled)return;const serial=++this.serial;this.scan.disabled=true;this.apply.disabled=true;
        this.status.textContent='Sampling only the current visible World; settings are unchanged…';
        try{
            this.options.showWorld();const result=await this.scanner.scan();if(this.closed||serial!==this.serial)return;
            if(result.status==='complete'){
                const r=result.report;this.status.textContent=`WebGL2; buffer ${r.capabilities.drawingBufferWidth}×${r.capabilities.drawingBufferHeight} at scan start; observed ${r.observedCadenceHz.toFixed(1)} Hz, p95 ${r.p95IntervalMs.toFixed(1)} ms in this model-jobs-idle view; images/materials may still arrive. ${r.explanation}`;
                this.apply.disabled=r.optionalResolutionPercent===null;
            }else this.status.textContent=result.reason;
            if(result.status!=='cancelled')this.options.showResultIfCurrent();
        }catch{if(!this.closed&&serial===this.serial)this.status.textContent='The current World could not be scanned; settings are unchanged.';}
        finally{if(!this.closed&&serial===this.serial)this.scan.disabled=false;}
    }
    get sampling():boolean{return this.scanner.sampling;}
    cancel():void{this.serial++;this.scanner.cancel();this.scan.disabled=this.applying;this.apply.disabled=true;this.status.textContent=this.applying?'Scan cancelled; a previously requested setting may have applied. Check effective settings.':'Scan cancelled; the scan requested no setting change.';}
    dispose():void{if(this.closed)return;this.closed=true;this.cancel();this.scanner.dispose();this.root.remove();}
}
