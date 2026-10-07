// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Opt-in proposal: convert already decoded images, never fetch or use global Cache.
import * as THREE from 'three';
import {Texture} from 'three';
type UploadSource=Texture['source'];
const SourceClass=(THREE as unknown as {TextureSource:new(data:unknown)=>UploadSource}).TextureSource;
const ownedBitmaps=new WeakSet<object>();
const sourceOwners=new WeakMap<UploadSource,Entry>();
export function isOwnedUploadBitmap(value:unknown):boolean{return typeof value==='object'&&value!==null&&ownedBitmaps.has(value);}
const aborted=()=>new DOMException('Session bitmap preparation was cancelled','AbortError');
export class BitmapUploadCapacityError extends Error{constructor(){super('Session bitmap preparation capacity is exhausted.');this.name='BitmapUploadCapacityError';}}
/** The original HTML upload remains authoritative for variants whose bitmap
 * conversion does not preserve actual browser pixels. Never guess by UA. */
export class BitmapUploadUnsupportedVariantError extends Error{constructor(message='Premultiplied textures retain their original decoded-image upload.'){super(message);this.name='BitmapUploadUnsupportedVariantError';}}
interface DecodedInput { id:number;src:string|undefined;currentSrc:string|undefined;width:number;height:number;complete:boolean|undefined }
interface Binding{source:UploadSource;version:number;image:HTMLImageElement;input:number;width:number;height:number;flipY:boolean;premultiplyAlpha:boolean;colorSpace:string}
// Ready entries retain only conversion metadata and their owned bitmap Source.
// The original decoded HTML Source is borrowed while conversion/readers run.
type EntryBinding=Omit<Binding,'source'|'image'>&Partial<Pick<Binding,'source'|'image'>>;
interface Entry{key:string;binding:EntryBinding;owner:WorldBitmapUpload;state:'queued'|'converting'|'ready'|'failed';cached:boolean;obsolete:boolean;readers:number;leases:number;bytes:number;source?:UploadSource;bitmap?:ImageBitmap;promise:Promise<Entry>;resolve:(value:Entry)=>void;reject:(error:unknown)=>void;timer?:ReturnType<typeof setTimeout>}
export interface WorldBitmapUploadOptions{signal:AbortSignal;maximumActive?:number;maximumPending?:number;maximumReaders?:number;maximumEntries?:number;maximumBytes?:number;deadlineMs?:number;createBitmap?:(image:HTMLImageElement,options:ImageBitmapOptions)=>Promise<ImageBitmap>;isImage?:(image:unknown)=>boolean}
/** Managed subclasses are the supported clone/copy boundary. Arbitrary copying
 * into unrelated Texture classes must not be published without a new lease.
 */
export class SessionUploadTexture extends Texture {
 private lease?:Entry;
 override copy(original:Texture):this{
  const entry=sourceOwners.get(original.source);
  if(isOwnedUploadBitmap(original.image)&&!entry)throw aborted();
  if(entry&&(entry.owner.closed||entry.obsolete||entry.state!=='ready'))throw aborted();
  // Texture.copy sets needsUpdate after copying Source. A detached Source avoids
  // changing the original shared image/version on every new sampler or clone.
  const view=Object.create(original) as Texture;
  Object.defineProperty(view,'source',{value:new SourceClass(original.image),enumerable:true});
  super.copy(view);
  const previous=this.lease;this.lease=undefined;
  if(entry){this.source=original.source;this.lease=entry;entry.leases++;}
  previous?.owner.release(previous);
  return this;
 }
 /** Internal only: called with an entry owned by this module, not asset metadata. */
 bind(entry:Entry):void{
  if(entry.owner.closed||entry.obsolete||entry.state!=='ready'||!entry.source)throw aborted();
  const previous=this.lease;this.source=entry.source;this.lease=entry;entry.leases++;previous?.owner.release(previous);
 }
 owns(entry:Entry):boolean{return this.lease===entry;}
 override dispose():void{const entry=this.lease;this.lease=undefined;try{super.dispose();}finally{entry?.owner.release(entry);}}
}
/** Ready cache + live texture pixels share one fixed budget. Eviction releases
 * only the cache lease. Cancellation rejects immediately but an unresolved
 * platform conversion retains its active slot/budget until it actually settles.
 */
export class WorldBitmapUpload{
 private readonly entries=new Map<string,Entry>();private readonly live=new Set<Entry>();private readonly queue:Entry[]=[];private readonly ids=new WeakMap<UploadSource,number>();private readonly inputs=new WeakMap<HTMLImageElement,DecodedInput>();private nextInputID=1;private nextID=1;private active=0;private bytes=0;private pending=0;private readers=0;private invalidating=false;closed=false;
 private readonly maximumActive:number;private readonly maximumPending:number;private readonly maximumReaders:number;private readonly maximumEntries:number;private readonly maximumBytes:number;private readonly deadlineMs:number;
 private readonly counters={requests:0,hits:0,created:0,closed:0,evictions:0,cancelled:0,failed:0,closeFailures:0,peakActive:0,invalidations:0};
 constructor(private readonly options:WorldBitmapUploadOptions){
  this.maximumActive=options.maximumActive??2;this.maximumPending=options.maximumPending??16;this.maximumReaders=options.maximumReaders??128;this.maximumEntries=options.maximumEntries??32;this.maximumBytes=options.maximumBytes??128*1024*1024;this.deadlineMs=options.deadlineMs??15000;
  for(const value of [this.maximumActive,this.maximumPending,this.maximumReaders,this.maximumEntries,this.maximumBytes,this.deadlineMs])if(!Number.isSafeInteger(value)||value<1)throw Error('Invalid bitmap preparation resource bound.');
  options.signal.addEventListener('abort',this.close,{once:true});if(options.signal.aborted)this.close();
 }
 stats(){return{...this.counters,active:this.active,pending:this.pending,readers:this.readers,retainedEntries:this.entries.size,liveEntries:this.live.size,bytes:this.bytes,leases:[...this.live].reduce((n,e)=>n+e.leases,0)};}
 /** The weak image record may retain address strings only while that HTML
  * input remains reachable. Ready bitmap entries retain only its numeric stamp,
  * never the borrowed element, Source, or address. Image replacement must be a
  * cache miss even when Texture.image does not increment Source.version. */
 private inputStamp(image:HTMLImageElement):number{
  const src=typeof image.src==='string'?image.src:undefined,currentSrc=typeof image.currentSrc==='string'?image.currentSrc:undefined;
  const width=image.naturalWidth,height=image.naturalHeight,complete=typeof image.complete==='boolean'?image.complete:undefined;
  const previous=this.inputs.get(image);
  if(previous&&previous.src===src&&previous.currentSrc===currentSrc&&previous.width===width&&previous.height===height&&previous.complete===complete)return previous.id;
  const id=this.nextInputID++;this.inputs.set(image,{id,src,currentSrc,width,height,complete});return id;
 }
 private snapshot(texture:Texture):Binding{
  // Actual Firefox WebGL comparison found one-to-three channel levels of
  // conversion rounding for premultiplied images. Keep their ordinary path.
  if(texture.premultiplyAlpha)throw new BitmapUploadUnsupportedVariantError();
  const image:unknown=texture.image;
  if(!(this.options.isImage?.(image)??(typeof HTMLImageElement!=='undefined'&&image instanceof HTMLImageElement)))throw Error('Only an already decoded ordinary image can be prepared.');
  const html=image as HTMLImageElement,w=html.naturalWidth,h=html.naturalHeight,input=this.inputStamp(html);
  if(html.complete===false)throw new BitmapUploadUnsupportedVariantError('An image still decoding retains its original upload.');
  if(!Number.isSafeInteger(w)||!Number.isSafeInteger(h)||w<1||h<1||w*h>64*1024*1024)throw Error('Invalid decoded image dimensions.');
  if(texture.isRenderTargetTexture||texture.mipmaps.length||!([THREE.NoColorSpace,THREE.SRGBColorSpace,THREE.LinearSRGBColorSpace] as string[]).includes(texture.colorSpace))throw Error('This texture variant is not supported for bitmap preparation.');
  return{source:texture.source,version:texture.source.version,image:html,input,width:w,height:h,flipY:texture.flipY,premultiplyAlpha:texture.premultiplyAlpha,colorSpace:texture.colorSpace};
 }
 private matches(texture:Texture,b:Binding){return texture.source===b.source&&texture.source.version===b.version&&texture.image===b.image&&this.inputStamp(b.image)===b.input&&texture.flipY===b.flipY&&texture.premultiplyAlpha===b.premultiplyAlpha&&texture.colorSpace===b.colorSpace;}
 async prepare(texture:Texture,signal:AbortSignal):Promise<SessionUploadTexture>{
  this.counters.requests++;if(this.closed||this.invalidating||signal.aborted)throw aborted();if(this.readers>=this.maximumReaders)throw new BitmapUploadCapacityError();const binding=this.snapshot(texture);if(!this.options.createBitmap&&typeof createImageBitmap!=='function')throw new BitmapUploadUnsupportedVariantError('ImageBitmap conversion is unavailable; original decoded-image uploads remain active.');
  let id=this.ids.get(binding.source);if(!id){id=this.nextID++;this.ids.set(binding.source,id);}
  const key=[id,binding.version,binding.input,Number(binding.flipY),Number(binding.premultiplyAlpha),binding.colorSpace].join(':');
  let entry=this.entries.get(key);
  if(entry){this.counters.hits++;this.entries.delete(key);this.entries.set(key,entry);}
  else{
   const bytes=binding.image.naturalWidth*binding.image.naturalHeight*4;
   this.trim(bytes);
   if(this.pending>=this.maximumPending||bytes+this.bytes>this.maximumBytes||this.live.size>=this.maximumEntries+this.maximumPending)throw new BitmapUploadCapacityError();
   let resolve!:(value:Entry)=>void,reject!:(error:unknown)=>void;const promise=new Promise<Entry>((yes,no)=>{resolve=yes;reject=no;});
   entry={key,binding,owner:this,state:'queued',cached:true,obsolete:false,readers:0,leases:0,bytes,promise,resolve,reject};this.entries.set(key,entry);this.live.add(entry);this.queue.push(entry);this.bytes+=bytes;this.pending++;
   const current=entry;current.timer=setTimeout(()=>this.fail(current,Error('Session bitmap preparation exceeded its deadline.')),this.deadlineMs);
  }
  const current=entry;current.readers++;this.readers++;let onAbort!:()=>void;
  try{
   const ready=new Promise<Entry>((resolve,reject)=>{onAbort=()=>reject(aborted());signal.addEventListener('abort',onAbort,{once:true});current.promise.then(resolve,reject);});
   this.pump();await ready;if(this.closed||signal.aborted||current.obsolete)throw aborted();if(!this.matches(texture,binding))throw Error('Texture binding changed during bitmap preparation.');
   const owned=new SessionUploadTexture();try{owned.copy(texture);owned.bind(current);return owned;}catch(error){owned.dispose();throw error;}
  }finally{
   signal.removeEventListener('abort',onAbort);current.readers--;this.readers--;
   if(!current.readers&&(current.state==='queued'||current.state==='converting'))this.fail(current,aborted());
   this.collect(current);
  }
 }
 isCurrent(texture:Texture):boolean{const e=sourceOwners.get(texture.source);return texture instanceof SessionUploadTexture&&!!e&&texture.owns(e)&&!this.closed&&!e.obsolete&&e.state==='ready'&&texture.image===e.bitmap&&texture.flipY===e.binding.flipY&&texture.premultiplyAlpha===e.binding.premultiplyAlpha&&texture.colorSpace===e.binding.colorSpace;}
 /** Recheck the exact decoded input at the later atomic material publication.
  * Ready cache entries deliberately do not retain the original HTML/Source. */
 isCompatible(original:Texture,prepared:SessionUploadTexture):boolean{
  const entry=sourceOwners.get(prepared.source),id=this.ids.get(original.source),image:unknown=original.image;
  if(!entry||!id||!this.isCurrent(prepared)||!(this.options.isImage?.(image)??(typeof HTMLImageElement!=='undefined'&&image instanceof HTMLImageElement)))return false;
  return entry.key===[id,original.source.version,this.inputStamp(image as HTMLImageElement),Number(original.flipY),Number(original.premultiplyAlpha),original.colorSpace].join(':');
 }
 private pump(){while(!this.closed&&!this.invalidating&&this.active<this.maximumActive&&this.queue.length){const e=this.queue.shift()!;if(e.state!=='queued')continue;if(this.inputStamp(e.binding.image!)!==e.binding.input){this.fail(e,Error('Texture binding changed before bitmap preparation.'));continue;}e.state='converting';this.active++;this.counters.peakActive=Math.max(this.counters.peakActive,this.active);
  const options:ImageBitmapOptions={imageOrientation:e.binding.flipY?'flipY':'from-image',premultiplyAlpha:e.binding.premultiplyAlpha?'premultiply':'none',colorSpaceConversion:'none'};
  let work:Promise<ImageBitmap>;try{work=(this.options.createBitmap??createImageBitmap)(e.binding.image!,options);}catch(error){this.fail(e,error);e.state='failed';this.active--;this.collect(e);this.pump();continue;}
  void Promise.resolve(work).then(bitmap=>{
   this.active--;if(this.closed||e.obsolete){this.closeBitmap(bitmap);e.state='failed';this.collect(e);this.pump();return;}
   if(this.inputStamp(e.binding.image!)!==e.binding.input){this.closeBitmap(bitmap);this.fail(e,Error('Texture binding changed during bitmap preparation.'));e.state='failed';this.collect(e);this.pump();return;}
   if(bitmap.width!==e.binding.width||bitmap.height!==e.binding.height){this.closeBitmap(bitmap);this.fail(e,Error('Prepared bitmap dimensions differ from the decoded source.'));e.state='failed';this.collect(e);this.pump();return;}
   e.bitmap=bitmap;ownedBitmaps.add(bitmap);e.source=new SourceClass(bitmap);e.source.needsUpdate=true;sourceOwners.set(e.source,e);e.state='ready';clearTimeout(e.timer);this.pending--;this.counters.created++;e.resolve(e);this.trim(0);this.pump();
  },error=>{this.active--;this.fail(e,error);e.state='failed';this.collect(e);this.pump();});
 }}
 private fail(e:Entry,error:unknown){if(e.obsolete||e.state==='ready'||e.state==='failed')return;e.obsolete=true;clearTimeout(e.timer);this.pending--;if(this.entries.get(e.key)===e)this.entries.delete(e.key);e.cached=false;
  if(error instanceof DOMException&&error.name==='AbortError')this.counters.cancelled++;else this.counters.failed++;
  e.reject(error);if(e.state==='queued'){e.state='failed';const index=this.queue.indexOf(e);if(index>=0)this.queue.splice(index,1);this.collect(e);}this.pump();
 }
 private trim(extra:number){for(const e of [...this.entries.values()]){if(this.entries.size<=this.maximumEntries&&this.bytes+extra<=this.maximumBytes)break;if(e.state!=='ready')continue;this.entries.delete(e.key);e.cached=false;this.counters.evictions++;this.collect(e);}}
 release(e:Entry){if(e.leases<=0)throw Error('Bitmap texture lease is not owned.');e.leases--;this.collect(e);}
 private closeBitmap(bitmap:ImageBitmap){try{bitmap.close();}catch{this.counters.closeFailures++;}finally{this.counters.closed++;}}
 private collect(e:Entry){if(e.state==='ready'&&!e.readers){e.binding.source=undefined;e.binding.image=undefined;}if(e.cached||e.readers||e.leases||e.state==='converting')return;if(!this.live.delete(e))return;if(e.source)sourceOwners.delete(e.source);if(e.bitmap){this.closeBitmap(e.bitmap);}this.bytes-=e.bytes;}
 /** Revoke cached approval without creating another physical conversion pool.
  * Outstanding platform promises retain their original slot/bytes until settled;
  * old leased pixels close only after their final sampler disposes. */
 invalidate():void{if(this.closed||this.invalidating)return;this.counters.invalidations++;this.discardEntries();this.pump();}
 private discardEntries():void{
  this.invalidating=true;
  try{for(const e of [...this.live]){if(e.state==='queued'||e.state==='converting')this.fail(e,aborted());else{e.obsolete=true;e.cached=false;if(this.entries.get(e.key)===e)this.entries.delete(e.key);this.collect(e);}}}
  finally{this.queue.length=0;this.invalidating=false;}
 }
 readonly close=()=>{if(this.closed)return;this.closed=true;this.options.signal.removeEventListener('abort',this.close);this.discardEntries();};
}
