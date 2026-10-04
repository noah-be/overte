// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {CompressedTexture,Material,Object3D,Texture,type WebGLRenderer} from 'three';
import {WorkerTaskYield} from './worker-task-yield';
export class TexturePreparationCapacityError extends Error {}
interface Options{signal:AbortSignal;maximumJobs?:number;maximumReferences?:number;deadlineMs?:number}
interface Job{accept?:(texture:Texture)=>boolean;textures:Texture[];cursor:number;weight:number;assertCurrent():void;resolve():void;reject(error:unknown):void;controller:AbortController;reader?:AbortSignal;onAbort():void;onTextureDisposed():void;timer:ReturnType<typeof setTimeout>;yieldTask?:WorkerTaskYield;settled:boolean}
const ended=()=>new DOMException('Texture preparation owner ended','AbortError');
/** Public initTexture only, borrowed static material maps, one call per task.
 * Calls are NOT unique GPU uploads: Three owns Source+sampler/version dedup.
 * No map downsampling, mutation, cached Source shortcut or shader hook changes.
 */
export class WorldTexturePreparation{
 private readonly jobs:Job[]=[];private active?:Job;private pumping=false;private references=0;private closed=false;
 private readonly maximumJobs:number;private readonly maximumReferences:number;private readonly deadlineMs:number;
 private readonly counts={submitted:0,completed:0,cancelled:0,failed:0,initCalls:0,imageCalls:0,bitmapCalls:0,compressedCalls:0,skipped:0,totalInitMs:0,maxInitMs:0,peakReferences:0};
 private readonly onAbort=()=>this.dispose();
 constructor(private readonly renderer:Pick<WebGLRenderer,'initTexture'>,private readonly options:Options){
  this.maximumJobs=options.maximumJobs??64;this.maximumReferences=options.maximumReferences??8192;this.deadlineMs=options.deadlineMs??30000;
  for(const [value,max]of [[this.maximumJobs,64],[this.maximumReferences,8192],[this.deadlineMs,30000]])if(!Number.isSafeInteger(value)||value<1||value>max)throw Error('Invalid texture preparation resource bound');
  if(options.signal.aborted)this.closed=true;else options.signal.addEventListener('abort',this.onAbort,{once:true});
 }
 get stats(){return{...this.counts,queued:this.jobs.length,active:this.active&&!this.active.settled?1:0,references:this.references,disposed:this.closed};}
 prepare(root:Object3D,assertCurrent:()=>void,reader?:AbortSignal,accept?:(texture:Texture)=>boolean):Promise<void>{
  try{
   this.options.signal.throwIfAborted();reader?.throwIfAborted();if(this.closed)throw ended();assertCurrent();
   const textures=new Set<Texture>(),materials=new Set<Material>();let objects=0;
   root.traverse(object=>{
    if(++objects>100000)throw new TexturePreparationCapacityError('Texture preparation graph exceeds its object bound');
    const material=(object as Object3D&{material?:Material|Material[]}).material;if(!material)return;
    for(const item of Array.isArray(material)?material:[material]){
     if(materials.has(item))continue;materials.add(item);
     for(const value of Object.values(item))if(value instanceof Texture){
     if(!this.staticReady(value)||(accept&&!accept(value))){this.counts.skipped++;continue;}
     textures.add(value);if(textures.size>4096)throw new TexturePreparationCapacityError('Texture preparation graph exceeds its map bound');
    }}
   });
   assertCurrent();reader?.throwIfAborted();this.options.signal.throwIfAborted();
   if(!textures.size)return Promise.resolve();
   if(this.jobs.length+(this.active&&!this.active.settled?1:0)>=this.maximumJobs||this.references+textures.size>this.maximumReferences)throw new TexturePreparationCapacityError('Too many pending texture preparation resources');
   return new Promise<void>((resolve,reject)=>{
    const controller=new AbortController();
    const job:Job={accept,textures:[...textures],cursor:0,weight:textures.size,assertCurrent,resolve,reject,controller,reader,settled:false,onAbort:()=>this.finish(job,ended()),onTextureDisposed:()=>this.finish(job,new DOMException('Borrowed preparation texture was disposed','AbortError')),timer:setTimeout(()=>this.finish(job,Error('Texture preparation exceeded its loading deadline')),this.deadlineMs)};
    reader?.addEventListener('abort',job.onAbort,{once:true});for(const texture of job.textures)texture.addEventListener('dispose',job.onTextureDisposed);this.jobs.push(job);this.references+=job.weight;this.counts.submitted++;this.counts.peakReferences=Math.max(this.counts.peakReferences,this.references);void this.pump();
   });
  }catch(error){return Promise.reject(error);}
 }
 private staticReady(texture:Texture):boolean{
  const flags=texture as Texture&{isDataTexture?:boolean;isData3DTexture?:boolean;isDataArrayTexture?:boolean;isCanvasTexture?:boolean;isVideoTexture?:boolean;isDepthTexture?:boolean;isExternalTexture?:boolean;isCubeTexture?:boolean;isCompressedArrayTexture?:boolean};
  if(texture.version<=0||texture.isRenderTargetTexture||flags.isDataTexture||flags.isData3DTexture||flags.isDataArrayTexture||flags.isCanvasTexture||flags.isVideoTexture||flags.isDepthTexture||flags.isExternalTexture||flags.isCubeTexture||flags.isCompressedArrayTexture)return false;
  if(texture instanceof CompressedTexture)return texture.mipmaps.length>0&&texture.image?.width>0&&texture.image?.height>0;
  const image=texture.image;
  return (typeof HTMLImageElement!=='undefined'&&image instanceof HTMLImageElement&&image.complete&&image.naturalWidth>0&&image.naturalHeight>0)
   ||(typeof ImageBitmap!=='undefined'&&image instanceof ImageBitmap&&image.width>0&&image.height>0);
 }
 private async pump():Promise<void>{
  if(this.pumping)return;this.pumping=true;
  try{while(!this.closed&&this.jobs.length){
   const job=this.jobs.shift()!;if(job.settled)continue;this.active=job;job.yieldTask??=new WorkerTaskYield({signal:job.controller.signal});
   try{
    // Round-robin jobs after one call so a large mapped model cannot hold
    // every smaller foreground owner's preparation behind its whole map list.
    await job.yieldTask.yield();if(job.settled)throw ended();job.assertCurrent();job.reader?.throwIfAborted();this.options.signal.throwIfAborted();
    const texture=job.textures[job.cursor++];
    if(!this.staticReady(texture)||(job.accept&&!job.accept(texture)))this.counts.skipped++;
    else{
     const started=performance.now();try{this.renderer.initTexture(texture);}finally{const elapsed=performance.now()-started;this.counts.initCalls++;if(texture instanceof CompressedTexture)this.counts.compressedCalls++;else if(typeof ImageBitmap!=='undefined'&&texture.image instanceof ImageBitmap)this.counts.bitmapCalls++;else this.counts.imageCalls++;this.counts.totalInitMs+=elapsed;this.counts.maxInitMs=Math.max(this.counts.maxInitMs,elapsed);}
    }
    if(job.settled)throw ended();job.assertCurrent();job.reader?.throwIfAborted();this.options.signal.throwIfAborted();
    if(job.cursor<job.textures.length)this.jobs.push(job);else this.finish(job);
   }catch(error){this.finish(job,error);}finally{if(job.settled)job.yieldTask.close();if(this.active===job)this.active=undefined;}
  }}finally{this.pumping=false;}
 }
 private finish(job:Job,error?:unknown):void{
  if(job.settled)return;job.settled=true;clearTimeout(job.timer);job.reader?.removeEventListener('abort',job.onAbort);job.controller.abort();
  const index=this.jobs.indexOf(job);if(index>=0)this.jobs.splice(index,1);this.references-=job.weight;for(const texture of job.textures)texture.removeEventListener('dispose',job.onTextureDisposed);job.textures.length=0;
  if(error!==undefined){if(error instanceof DOMException&&error.name==='AbortError')this.counts.cancelled++;else this.counts.failed++;job.reject(error);}else{this.counts.completed++;job.resolve();}
 }
 dispose():void{
  if(this.closed)return;this.closed=true;this.options.signal.removeEventListener('abort',this.onAbort);for(const job of [...this.jobs,...(this.active?[this.active]:[])])this.finish(job,ended());
 }
}
