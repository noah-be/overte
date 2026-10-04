// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** User-triggered visitor clipboard only; never reads the gateway host clipboard. */
export class TabletClipboard {
    private fallback:HTMLTextAreaElement;private copy:HTMLButtonElement;
    constructor(toolbar:HTMLElement,private onStatus:(message:string)=>void){
        this.fallback=document.createElement('textarea');this.fallback.readOnly=true;this.fallback.hidden=true;this.fallback.setAttribute('aria-label','Selected native text');
        Object.assign(this.fallback.style,{maxWidth:'100%',height:'44px',boxSizing:'border-box'});
        this.copy=document.createElement('button');this.copy.type='button';this.copy.textContent='Copy selected text';this.copy.hidden=true;
        this.copy.addEventListener('click',()=>void this.write(this.fallback.value));toolbar.append(this.fallback,this.copy);
    }
    private async write(text:string):Promise<void>{
        try{if(!navigator.clipboard?.writeText)throw Error('Clipboard permission is unavailable');await navigator.clipboard.writeText(text);this.onStatus('Selected native text copied to your clipboard.');this.fallback.hidden=true;this.copy.hidden=true;}
        catch{this.onStatus('Use Copy selected text, or select the text field and copy it.');this.fallback.hidden=false;this.copy.hidden=false;this.fallback.focus();this.fallback.select();}
    }
    receive(text:string):void{this.fallback.value=text;void this.write(text);}
    dispose():void{this.fallback.remove();this.copy.remove();}
}
