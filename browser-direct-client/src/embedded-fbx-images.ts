// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owner-scoped registry; caller binds descriptors to its approved prepared bytes.
import type {EmbeddedFbxImage} from './baked-fbx';
import {embeddedContentCounts} from './embedded-content-counts';
interface Entry {key:string;url:string;bytes:number;readers:number}
const abortError=()=>new DOMException('Embedded image owner ended','AbortError');
/** Buffer identity is issued by the approved per-world preparation/cache owner. */
export class EmbeddedFbxImages {
 private owners=new WeakMap<ArrayBuffer,number>();private nextOwner=0;private entries=new Map<string,Entry>();private bytes=0;private closed=false;
 private scopes=new Set<{close():void}>();private counters={createdURLs:0,reusedURLs:0,revokedURLs:0};
 constructor(private worldSignal:AbortSignal,private limits={bytes:64*1024*1024,entries:128,scopes:16}){
  if(Object.keys(limits).length!==3||!['bytes','entries','scopes'].every(name=>Object.prototype.hasOwnProperty.call(limits,name)))throw Error('Invalid embedded image resource bound');
  for(const [name,value]of Object.entries(limits))if(!Number.isSafeInteger(value)||value<1||value>({bytes:128*1024*1024,entries:256,scopes:16} as Record<string,number>)[name])throw Error('Invalid embedded image resource bound');
  worldSignal.addEventListener('abort',this.close,{once:true});if(worldSignal.aborted)this.close();
 }
 get statistics(){return {...this.counters,bytes:this.bytes,entries:this.entries.size,scopes:this.scopes.size,...embeddedContentCounts(this.entries.values())};}
 register(buffer:ArrayBuffer,images:readonly EmbeddedFbxImage[],signal:AbortSignal){
  if(this.closed||signal.aborted)throw abortError();if(!(buffer instanceof ArrayBuffer)||!buffer.byteLength||!Array.isArray(images)||images.length>64||this.scopes.size>=this.limits.scopes)throw Error('Invalid embedded image owner or scope limit');
  const mappings=new Map<string,{key:string;image:EmbeddedFbxImage}>();let total=0;
  let owner=this.owners.get(buffer);if(!owner){owner=++this.nextOwner;this.owners.set(buffer,owner);}
  for(const image of images){
   if(!image||typeof image.digest!=='string'||typeof image.mimeType!=='string'||!/^[a-f0-9]{64}$/.test(image.digest)||!['image/png','image/jpeg','image/bmp','image/webp'].includes(image.mimeType)||!(image.bytes instanceof ArrayBuffer)||!image.bytes.byteLength||image.bytes.byteLength>8*1024*1024)throw Error('Invalid embedded source descriptor');
   total+=image.bytes.byteLength;if(total>16*1024*1024)throw Error('Embedded source scope exceeds 16 MiB');
   const marker=`data:${image.mimeType};base64,overte-embedded-${image.digest}`;if(mappings.has(marker))throw Error('Duplicate embedded descriptor');
   mappings.set(marker,{key:`${owner}|${image.mimeType}|${image.digest}`,image});
  }
  const held=new Set<Entry>();let closed=false;
  const scope={resolveURL:(url:string)=>{
   if(this.closed||closed||signal.aborted)throw abortError();
   const record=mappings.get(url);if(!record){if(/^data:[^,]*;base64,overte-embedded-/.test(url))throw Error('Unregistered embedded image marker');return url;}
   let entry=this.entries.get(record.key);
   if(entry){this.entries.delete(entry.key);this.entries.set(entry.key,entry);this.counters.reusedURLs++;}
   else{
    this.trim(record.image.bytes.byteLength,1);
    if(this.bytes+record.image.bytes.byteLength>this.limits.bytes||this.entries.size>=this.limits.entries)throw Error('Active embedded sources exceed their resource bound');
    const url=URL.createObjectURL(new Blob([record.image.bytes],{type:record.image.mimeType}));
    entry={key:record.key,url,bytes:record.image.bytes.byteLength,readers:0};this.entries.set(record.key,entry);this.bytes+=entry.bytes;this.counters.createdURLs++;
   }
   if(!held.has(entry)){held.add(entry);entry.readers++;}
   return entry.url;
  },close:()=>{
   if(closed)return;closed=true;signal.removeEventListener('abort',scope.close);this.scopes.delete(scope);for(const entry of held)entry.readers--;held.clear();mappings.clear();
  }};
  this.scopes.add(scope);signal.addEventListener('abort',scope.close,{once:true});return scope;
 }
 private revoke(entry:Entry){URL.revokeObjectURL(entry.url);this.entries.delete(entry.key);this.bytes-=entry.bytes;this.counters.revokedURLs++;}
 private trim(extraBytes:number,extraEntries:number){for(const entry of this.entries.values()){if(this.bytes+extraBytes<=this.limits.bytes&&this.entries.size+extraEntries<=this.limits.entries)return;if(!entry.readers)this.revoke(entry);}}
 readonly close=()=>{if(this.closed)return;this.closed=true;this.worldSignal.removeEventListener('abort',this.close);for(const scope of [...this.scopes])scope.close();for(const entry of [...this.entries.values()])this.revoke(entry);};
}
