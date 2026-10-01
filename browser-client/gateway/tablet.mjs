// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {readFile,writeFile,lstat,unlink,open} from 'node:fs/promises';
import {constants} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {prepareSnapshotOverride} from './tablet-snapshots.mjs';
import {visitorFilename} from './tablet-files.mjs';
import {nativeChatMessage} from './tablet-chat.mjs';

// Cache trusted helpers together with the gateway module at process startup.
// Every worker uses these exact bytes even if a development checkout changes.
const nativeTabletSource=await readFile(new URL('./native-tablet.js',import.meta.url));
const tabletCaptureSource=await readFile(new URL('./tablet-capture.qml',import.meta.url));
const nativeChatSource=await readFile(new URL('./native-tablet-chat.js',import.meta.url));

export const MAX_FRAME_BYTES=4*1024*1024;
const KEYS=new Set(['Backspace','Tab','Enter','Delete','Insert','Home','End','PageUp','PageDown','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Escape','F1','F2','F3','F4','F5','F6','F7','F8','F9','F10','F11','F12']);
function integer(value,min,max){return Number.isSafeInteger(value)&&value>=min&&value<=max;}
function nativeEffects(value){if(!value||typeof value!=='object')return {};const effects={};for(const key of ['muted','shield'])if(typeof value[key]==='boolean')effects[key]=value[key];return Object.keys(effects).length?{effects}:{};}
export function validateTabletInput(value) {
    if (!value||typeof value!=='object'||Array.isArray(value)||value.type!=='tablet'||!integer(value.sequence,1,Number.MAX_SAFE_INTEGER)) throw new Error('Invalid tablet command');
    const result={type:'tablet',action:value.action,sequence:value.sequence};
    if(value.revision!==undefined){if(!integer(value.revision,1,Number.MAX_SAFE_INTEGER))throw new Error('Invalid tablet revision');result.revision=value.revision;}
    if(!['open','close','home','back','input','frameAck','snapshotResult'].includes(value.action))throw new Error('Unsupported tablet command');
    if(value.action==='snapshotResult'){
        if(!integer(value.requestId,1,Number.MAX_SAFE_INTEGER))throw Error('Invalid snapshot request');result.requestId=value.requestId;
        if(value.error!==undefined){if(typeof value.error!=='string'||value.error.length>512)throw Error('Invalid snapshot error');result.error=value.error;}
        else{result.stillName=visitorFilename(value.stillName);if(!result.stillName.endsWith('.png'))throw Error('Invalid still snapshot');if(value.gifName!==undefined){result.gifName=visitorFilename(value.gifName);if(!result.gifName.endsWith('.gif'))throw Error('Invalid animated snapshot');}}
    }
    if(value.action==='frameAck'){if(!integer(value.frameSequence,1,Number.MAX_SAFE_INTEGER))throw new Error('Invalid tablet acknowledgement');result.frameSequence=value.frameSequence;}
    if(value.action==='input'){
        if(!['press','release','move','wheel','key','text','clipboard'].includes(value.event))throw new Error('Invalid tablet input');
        result.event=value.event;
        if(['press','release','move','wheel'].includes(value.event)){
            if(!['x','y'].every(key=>typeof value[key]==='number'&&Number.isFinite(value[key])&&value[key]>=0&&value[key]<=1))throw new Error('Invalid tablet coordinates');
            result.x=value.x;result.y=value.y;
            if(value.event==='wheel'){
                if(!['deltaX','deltaY'].every(key=>typeof value[key]==='number'&&Number.isFinite(value[key])&&Math.abs(value[key])<=1200))throw new Error('Invalid tablet wheel');
                result.deltaX=Math.round(value.deltaX);result.deltaY=Math.round(value.deltaY);
            }else{
                if(!integer(value.button,0,2)||!integer(value.buttons,0,7))throw new Error('Invalid tablet buttons');result.button=value.button;result.buttons=value.buttons;
            }
        }
        if(value.event==='key'){
            if(typeof value.key!=='string'||(!KEYS.has(value.key)&&([...value.key].length!==1||/\p{C}/u.test(value.key))))throw new Error('Invalid tablet key');result.key=value.key;
        }
        if(value.event==='clipboard'){if(!['copy','cut'].includes(value.operation))throw Error('Invalid tablet clipboard operation');result.operation=value.operation;}
        if(value.event==='text'){
            if(typeof value.text!=='string'||value.text.length<1||Buffer.byteLength(value.text,'utf8')>65536||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value.text))throw new Error('Invalid tablet text');result.text=value.text;
        }else if(value.event!=='clipboard'){
            if(!integer(value.modifiers,0,15))throw new Error('Invalid tablet modifiers');result.modifiers=value.modifiers;
        }
    }
    return result;
}

export async function prepareTablet(directory,{defaultScriptsURL,filesDirectory}){
    const defaults=new URL(defaultScriptsURL);
    if(defaults.protocol!=='file:'||defaults.host)throw new Error('Default tablet scripts must be an installed local file');
    const info=await lstat(fileURLToPath(defaults));
    if(!info.isFile()||info.isSymbolicLink()||!fileURLToPath(defaults).endsWith('/defaultScripts.js'))throw new Error('Invalid installed default scripts');
    const script=join(directory,'native-tablet.js'),qml=join(directory,'tablet-capture.qml'),chat=join(directory,'native-tablet-chat.js');
    await writeFile(script,nativeTabletSource,{mode:0o600,flag:'wx'});
    await writeFile(qml,tabletCaptureSource,{mode:0o600,flag:'wx'});
    await writeFile(chat,nativeChatSource,{mode:0o600,flag:'wx'});
    const snapshotChannel=`browser-tablet-snapshot-${randomUUID()}`;
    const snapshotOverride=filesDirectory?await prepareSnapshotOverride(directory,{defaultScriptsURL:defaults.href,channel:snapshotChannel}):undefined;
    return {scriptURL:pathToFileURL(script).href,qmlURL:pathToFileURL(qml).href,chatURL:pathToFileURL(chat).href,framePath:join(directory,'tablet.png'),defaultScriptsURL:defaults.href,...(snapshotOverride?{snapshotChannel,snapshotOverride,filesDirectory}:{})};
}

export function validateTabletPNG(bytes,width,height){
    if(!Buffer.isBuffer(bytes)||bytes.length<33||bytes.length>MAX_FRAME_BYTES||!bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))||bytes.readUInt32BE(8)!==13||bytes.toString('ascii',12,16)!=='IHDR'||!integer(width,1,2048)||!integer(height,1,2048)||bytes.readUInt32BE(16)!==width||bytes.readUInt32BE(20)!==height)throw new Error('Invalid native tablet PNG');
}

/** All callbacks are bound to one authenticated native worker and its browser. */
export class TabletSession {
    constructor({framePath,filesDirectory,sendNative,sendBrowser,isActive,getRevision}){
        this.framePath=framePath;this.sendNative=sendNative;this.sendBrowser=sendBrowser;this.isActive=isActive;this.getRevision=getRevision;
        this.closed=false;this.sequence=0;this.frameSequence=0;this.pendingFrame=0;this.revision=0;this.pendingTimer=null;
        this.filesDirectory=filesDirectory;this.snapshotRequest=0;this.clipboardRequest=0;this.chatSequence=0;
    }
    current(revision){return !this.closed&&this.isActive()&&integer(revision,1,Number.MAX_SAFE_INTEGER)&&revision===this.getRevision();}
    resetRevision(){const next=this.getRevision();if(next!==this.revision){this.revision=next;this.frameSequence=0;this.pendingFrame=0;this.snapshotRequest=0;this.clipboardRequest=0;this.chatSequence=0;clearTimeout(this.pendingTimer);}}
    receive(value){
        if(this.closed)throw new Error('Tablet session has ended');
        const message=validateTabletInput(value);this.resetRevision();
        if(!this.current(this.revision))throw new Error('Tablet is unavailable until the domain permissions are approved');
        if(message.action!=='open'&&message.revision!==this.revision)throw new Error('Stale tablet command');
        if(message.revision!==undefined&&message.revision!==this.revision)throw new Error('Stale tablet command');
        if(message.sequence<=this.sequence)throw new Error('Repeated tablet command');this.sequence=message.sequence;message.revision=this.revision;
        if(message.action==='input'&&message.event==='clipboard')this.clipboardRequest=message.sequence;
        if(message.action==='frameAck'){
            if(message.frameSequence!==this.pendingFrame)return;
            this.pendingFrame=0;clearTimeout(this.pendingTimer);
        }
        if(message.action==='snapshotResult'){
            if(message.requestId!==this.snapshotRequest||!this.filesDirectory)throw Error('Stale snapshot response');
            this.snapshotRequest=0;
            if(!message.error){message.stillPath=join(this.filesDirectory,message.stillName);if(message.gifName)message.gifPath=join(this.filesDirectory,message.gifName);}
        }
        this.sendNative(message);
    }
    async receiveNative(message){
        this.resetRevision();if(!this.current(message.revision)||message.type!=='tablet')return;
        const revision=message.revision;
        if(message.kind==='frameReady'){
            if(this.pendingFrame||!integer(message.sequence,1,Number.MAX_SAFE_INTEGER)||message.sequence<=this.frameSequence||!['tablet','dialogs'].includes(message.surface))return;
            this.pendingFrame=message.sequence;this.frameSequence=message.sequence;
            const frameFile=`${this.framePath}.${revision}.${message.sequence}.png`;
            try{
                // No following native-created symlinks into gateway-host files.
                // Read a fixed upper bound even if a file grows after stat().
                const file=await open(frameFile,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
                let bytes;
                try {
                    const info=await file.stat();
                    if(!info.isFile()||info.size>MAX_FRAME_BYTES)throw new Error('Invalid native tablet frame file');
                    const buffer=Buffer.alloc(MAX_FRAME_BYTES+1);let length=0;
                    while(length<buffer.length){const chunk=await file.read(buffer,length,buffer.length-length,length);if(!chunk.bytesRead)break;length+=chunk.bytesRead;}
                    bytes=buffer.subarray(0,length);validateTabletPNG(bytes,message.width,message.height);
                } finally {await file.close();}
                if(!this.current(revision)||this.pendingFrame!==message.sequence)return;
                const rect=message.tabletRect;
                const tabletRect=rect&&['x','y','width','height'].every(key=>typeof rect[key]==='number'&&Number.isFinite(rect[key])&&Math.abs(rect[key])<=4096)&&rect.width>0&&rect.height>0?{x:rect.x,y:rect.y,width:rect.width,height:rect.height}:undefined;
                this.sendBrowser({type:'tablet',kind:'frame',revision,sequence:message.sequence,width:message.width,height:message.height,surface:message.surface,mime:'image/png',data:bytes.toString('base64'),...(tabletRect?{tabletRect}:{}),...nativeEffects(message.effects)});
                this.pendingTimer=setTimeout(()=>this.releaseFrame(revision,message.sequence),5000);this.pendingTimer.unref?.();
            }catch{
                if(this.current(revision)){this.sendBrowser({type:'tablet',kind:'error',revision,message:'The native tablet display could not be read. Try opening it again.'});this.releaseFrame(revision,message.sequence);}
            }finally{await unlink(frameFile).catch(()=>{});}
        }else if(message.kind==='chat'){
            const chat=nativeChatMessage(message);if(chat.sequence<=this.chatSequence)return;this.chatSequence=chat.sequence;
            this.sendBrowser({type:'tablet',kind:'chat',revision,...chat});
        }else if(message.kind==='state'&&typeof message.visible==='boolean'&&typeof message.loading==='boolean'&&typeof message.screen==='string'&&message.screen.length<=256){
            this.sendBrowser({type:'tablet',kind:'state',revision,visible:message.visible,loading:message.loading,screen:message.screen,...nativeEffects(message.effects)});
        }else if(message.kind==='error'&&typeof message.message==='string'){
            this.sendBrowser({type:'tablet',kind:'error',revision,message:message.message.slice(0,1024)});
        }else if(message.kind==='microphone'&&typeof message.muted==='boolean'){
            this.sendBrowser({type:'tablet',kind:'microphone',revision,muted:message.muted});
        }else if(message.kind==='clipboard'&&message.requestId===this.clipboardRequest&&typeof message.text==='string'&&Buffer.byteLength(message.text,'utf8')<=65536){
            this.clipboardRequest=0;this.sendBrowser({type:'tablet',kind:'clipboard',revision,requestId:message.requestId,text:message.text});
        }else if(message.kind==='snapshot'&&this.filesDirectory&&integer(message.requestId,1,Number.MAX_SAFE_INTEGER)&&typeof message.animated==='boolean'&&typeof message.aspectRatio==='number'&&Number.isFinite(message.aspectRatio)&&message.aspectRatio>=.1&&message.aspectRatio<=4){
            this.snapshotRequest=message.requestId;
            this.sendBrowser({type:'tablet',kind:'snapshot',revision,requestId:message.requestId,animated:message.animated,aspectRatio:message.aspectRatio});
        }
    }
    releaseFrame(revision,sequence){if(!this.current(revision)||this.pendingFrame!==sequence)return;this.pendingFrame=0;clearTimeout(this.pendingTimer);this.sendNative({type:'tablet',action:'frameAck',revision,frameSequence:sequence});}
    close(){if(this.closed)return;this.closed=true;clearTimeout(this.pendingTimer);this.pendingFrame=0;void unlink(this.framePath).catch(()=>{});}
}
