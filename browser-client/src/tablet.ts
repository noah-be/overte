// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {parseTabletMessage, type TabletMessage} from './tablet-protocol';
import {TabletFiles} from './tablet-files';
import {TabletSnapshots} from './tablet-snapshots';
import {TabletClipboard} from './tablet-clipboard';
import {validateBrowserGraphicsResult,type BrowserGraphicsResult} from '../shared/browser-graphics.mjs';

export interface TabletOptions {
    send:(message:unknown)=>void;
    onStatus:(message:string)=>void;
    onVisibility:(visible:boolean)=>void;
    onMicrophoneRequest?:(muted:boolean)=>void;
    onGraphics?:(request:Extract<TabletMessage,{kind:'graphics'}>)=>BrowserGraphicsResult|undefined;
    fileURL?:(name?:string)=>string;
    captureScene?:()=>Promise<Blob>;
}

/** Native Qt tablet and its associated dialogs; the world remains local WebGL. */
export class BrowserTablet {
    private element:HTMLElement;
    private canvas:HTMLCanvasElement;
    private keyboard:HTMLTextAreaElement;
    private status:HTMLElement;
    private holder:HTMLElement;
    private resize:ResizeObserver;
    private buttons:HTMLButtonElement[] = [];
    private revision = 0;
    private sequence = 0;
    private frameSequence = 0;
    private connected = false;
    private generation = 0;
    private disposed = false;
    private files?:TabletFiles;
    private snapshots:TabletSnapshots;
    private clipboard:TabletClipboard;
    private abort = new AbortController();
    visible = false;

    constructor(container:HTMLElement, private options:TabletOptions) {
        this.element = document.createElement('section');
        this.element.setAttribute('aria-label','Overte tablet');
        this.element.hidden = true;
        Object.assign(this.element.style,{position:'absolute',inset:'10px',zIndex:'20',background:'#141a24',border:'1px solid #718098',borderRadius:'12px',display:'flex',flexDirection:'column',alignItems:'center',overflow:'hidden',boxShadow:'0 12px 40px #0009'});
        const toolbar = document.createElement('nav');
        toolbar.setAttribute('aria-label','Tablet navigation');
        Object.assign(toolbar.style,{display:'flex',flexWrap:'wrap',alignItems:'center',gap:'8px',padding:'8px',width:'100%',boxSizing:'border-box',flexShrink:'0'});
        for (const [label,action] of [['Back','back'],['Home','home'],['Close tablet','close']] as const) {
            const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
            button.addEventListener('click',()=>action === 'close' ? this.close() : this.send({action}));
            toolbar.append(button); this.buttons.push(button);
        }
        this.status = document.createElement('span'); this.status.setAttribute('role','status');
        Object.assign(this.status.style,{overflowWrap:'anywhere',maxWidth:'100%',flex:'1 1 140px'});
        this.status.textContent = 'Opening the native tablet…'; toolbar.append(this.status);
        if(options.fileURL)this.files=new TabletFiles(toolbar,this.element,{fileURL:options.fileURL,onStatus:options.onStatus});
        this.clipboard=new TabletClipboard(toolbar,options.onStatus);
        this.snapshots=new TabletSnapshots(toolbar,{captureScene:options.captureScene,fileURL:options.fileURL,send:value=>this.send(value),onStatus:options.onStatus});
        const holder = document.createElement('div');
        this.holder=holder;
        Object.assign(holder.style,{minHeight:'0',flex:'1',width:'100%',display:'flex',justifyContent:'center',alignItems:'center'});
        this.canvas = document.createElement('canvas'); this.canvas.width = 480; this.canvas.height = 706;
        this.canvas.tabIndex = 0; this.canvas.setAttribute('aria-label','Native tablet apps and dialogs');
        Object.assign(this.canvas.style,{maxWidth:'100%',maxHeight:'100%',objectFit:'contain',touchAction:'none',outlineOffset:'-3px'});
        this.keyboard=document.createElement('textarea');this.keyboard.tabIndex=-1;this.keyboard.setAttribute('aria-label','Native tablet text input');
        this.keyboard.autocomplete='off';this.keyboard.spellcheck=false;this.keyboard.setAttribute('autocapitalize','off');
        Object.assign(this.keyboard.style,{position:'absolute',width:'1px',height:'1px',opacity:'0',padding:'0',border:'0',left:'0',top:'0'});
        holder.append(this.canvas,this.keyboard); this.element.append(toolbar,holder); container.append(this.element);
        this.resize=new ResizeObserver(()=>this.fit());this.resize.observe(holder);
        this.element.hidden = true; this.element.style.display = 'none';
        const signal = this.abort.signal;
        for (const name of ['keydown','keyup','pointerdown','pointerup','pointermove','wheel'] as const) {
            this.element.addEventListener(name,event=>event.stopPropagation(),{signal});
        }
        this.canvas.addEventListener('pointerdown',event=>{
            if (!this.revision) return;
            event.preventDefault(); this.keyboard.focus({preventScroll:true}); this.canvas.setPointerCapture(event.pointerId);
            this.pointer('press',event);
        },{signal});
        this.canvas.addEventListener('pointerup',event=>{
            event.preventDefault(); this.pointer('release',event);
            if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
        },{signal});
        this.canvas.addEventListener('pointermove',event=>this.pointer('move',event),{signal});
        this.canvas.addEventListener('pointercancel',event=>this.pointer('release',event),{signal});
        this.canvas.addEventListener('contextmenu',event=>event.preventDefault(),{signal});
        this.canvas.addEventListener('wheel',event=>{
            event.preventDefault(); const coordinates = this.coordinates(event);
            const multiplier = event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? 400 : 1;
            this.send({action:'input',event:'wheel',...coordinates,deltaX:Math.max(-1200,Math.min(1200,-event.deltaX*multiplier)),deltaY:Math.max(-1200,Math.min(1200,-event.deltaY*multiplier)),modifiers:this.modifiers(event)});
        },{signal,passive:false});
        const keydown=(event:KeyboardEvent)=>{
            if(event.isComposing)return;
            const shortcut=event.ctrlKey||event.metaKey;
            if(shortcut&&event.key.toLowerCase()==='v')return; // Browser supplies the trusted paste event.
            if(shortcut&&['c','x'].includes(event.key.toLowerCase())){event.preventDefault();this.send({action:'input',event:'clipboard',operation:event.key.toLowerCase()==='x'?'cut':'copy'});return;}
            event.preventDefault();
            if (!['Shift','Control','Alt','Meta','Dead','Unidentified','Process','Compose'].includes(event.key)) this.send({action:'input',event:'key',key:event.key,modifiers:this.modifiers(event)});
        };
        this.canvas.addEventListener('keydown',keydown,{signal});this.keyboard.addEventListener('keydown',keydown,{signal});
        this.canvas.addEventListener('keyup',event=>event.preventDefault(),{signal});
        const paste=(event:ClipboardEvent)=>{event.preventDefault();event.stopPropagation();const text=event.clipboardData?.getData('text/plain');
            if(text)this.sendText(text,'Pasted text');this.keyboard.value='';};
        this.canvas.addEventListener('paste',paste,{signal});this.keyboard.addEventListener('paste',paste,{signal});
        // Browser IMEs emit committed text independently of keydown.
        this.keyboard.addEventListener('compositionend',event=>{
            event.stopPropagation(); if (event.data) this.sendText(event.data,'Composed text');
            this.keyboard.value='';
        },{signal});
    }

    private sendText(text:string,label:string):void {
        if(new TextEncoder().encode(text).length>65536){this.options.onStatus(`${label} exceeds the 64 KiB limit.`);return;}
        // Match the native command policy before transmission, preserving the
        // connection when an ordinary paste includes unsupported C0 controls.
        if(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(text)){this.options.onStatus('Tablet text contains unsupported control characters.');return;}
        this.send({action:'input',event:'text',text});
    }

    private modifiers(event:KeyboardEvent|MouseEvent):number {return (event.shiftKey?1:0)|(event.ctrlKey?2:0)|(event.altKey?4:0)|(event.metaKey?8:0);}
    private fit():void {
        const bounds=this.holder.getBoundingClientRect();
        if(bounds.width<1||bounds.height<1)return;
        const scale=Math.min(1,bounds.width/this.canvas.width,bounds.height/this.canvas.height);
        this.canvas.style.width=`${this.canvas.width*scale}px`;this.canvas.style.height=`${this.canvas.height*scale}px`;
    }
    private coordinates(event:MouseEvent):{x:number;y:number} {
        const bounds = this.canvas.getBoundingClientRect();
        return {x:Math.max(0,Math.min(1,(event.clientX-bounds.left)/Math.max(1,bounds.width))),y:Math.max(0,Math.min(1,(event.clientY-bounds.top)/Math.max(1,bounds.height)))};
    }
    private pointer(event:'press'|'release'|'move',pointer:PointerEvent):void {
        this.send({action:'input',event,...this.coordinates(pointer),button:Math.min(2,Math.max(0,pointer.button)),buttons:pointer.buttons&7,modifiers:this.modifiers(pointer)});
    }
    private send(value:Record<string,unknown>):void {
        if (!this.connected || this.disposed || (value.action !== 'open' && !this.revision)) return;
        this.options.send({type:'tablet',...value,...(this.revision ? {revision:this.revision} : {}),sequence:++this.sequence});
    }
    private show(visible:boolean):void {
        if (this.visible === visible) return;
        this.visible = visible; this.element.hidden = !visible; this.element.style.display = visible ? 'flex' : 'none';
        this.options.onVisibility(visible);
        if (visible) {this.fit();if (document.pointerLockElement) void document.exitPointerLock();this.canvas.focus();}
        else if (document.activeElement instanceof HTMLElement && this.element.contains(document.activeElement)) document.activeElement.blur();
    }
    open():void {if (this.connected) {this.show(true);this.status.textContent='Opening the native tablet…';this.send({action:'open'});}}
    close():void {this.snapshots.cancel(true);this.send({action:'close'});this.show(false);this.generation++;}
    setConnected(connected:boolean):void {
        this.connected=connected; this.buttons.forEach(button=>button.disabled=!connected);
        if (!connected) {this.revision=0;this.sequence=0;this.frameSequence=0;this.generation++;this.snapshots.cancel();this.show(false);}
    }
    receive(message:TabletMessage):void {
        const value = parseTabletMessage(message);
        if (!this.connected || value.revision < this.revision) return;
        if (value.revision !== this.revision) {this.revision=value.revision;this.frameSequence=0;this.generation++;this.snapshots.cancel();}
        if (value.kind === 'state') {this.show(value.visible);this.status.textContent=value.loading?'Loading native tablet…':value.screen || 'Tablet';}
        else if (value.kind === 'error') {this.status.textContent=value.message;this.options.onStatus(value.message);}
        else if (value.kind === 'clipboard') this.clipboard.receive(value.text);
        else if (value.kind === 'snapshot') {this.show(false);void this.snapshots.capture(value);}
        else if (value.kind === 'microphone') this.options.onMicrophoneRequest?.(value.muted);
        else if (value.kind === 'graphics') {
            try {
                const result=this.options.onGraphics?.(value);
                if(result && this.connected && !this.disposed && value.revision===this.revision)
                    this.send({action:'graphicsResult',...validateBrowserGraphicsResult(result)});
            } catch {this.options.onStatus('The browser could not apply that graphics setting.');}
        }
        else if (value.kind === 'frame' && value.sequence > this.frameSequence) {
            this.frameSequence=value.sequence;const generation=this.generation;
            void this.draw(value,generation);
        }
    }
    private async draw(frame:Extract<TabletMessage,{kind:'frame'}>,generation:number):Promise<void> {
        try {
            const raw=atob(frame.data);const bytes=new Uint8Array(raw.length);
            for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
            const image=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
            try {
                if (this.disposed || generation!==this.generation || frame.sequence!==this.frameSequence) return;
                if (image.width!==frame.width || image.height!==frame.height) throw new Error('Tablet frame dimensions do not match');
                this.canvas.width=frame.width;this.canvas.height=frame.height;
                const context=this.canvas.getContext('2d');if(!context) throw new Error('Tablet display is unavailable');
                context.drawImage(image,0,0);this.canvas.style.aspectRatio=`${frame.width} / ${frame.height}`;
                this.fit();
                this.status.textContent=frame.surface==='dialogs'?'Native tablet dialog':'Tablet';
            } finally {image.close();}
        } catch(error) {if(generation===this.generation)this.options.onStatus(`Tablet display error: ${error instanceof Error ? error.message : String(error)}`);}
        finally {if(!this.disposed && generation===this.generation)this.send({action:'frameAck',frameSequence:frame.sequence});}
    }
    dispose():void {if(this.disposed)return;this.close();this.disposed=true;this.abort.abort();this.resize.disconnect();this.files?.dispose();this.snapshots.dispose();this.clipboard.dispose();this.element.remove();}
}
