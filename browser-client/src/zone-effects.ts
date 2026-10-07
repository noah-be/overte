// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Native references: EntityItem.cpp.in, EntityTreeRenderer::LayeredZones,
// graphics/{Haze.h,Haze.slh,Skybox.cpp,Light.slh} and image/TextureProcessing.cpp.
import {Camera,Color,CubeTexture,DataTexture,DirectionalLight,EquirectangularReflectionMapping,Light,Material,Matrix4,Mesh,BoxGeometry,BackSide,Quaternion,Scene,ShaderChunk,ShaderMaterial,SRGBColorSpace,LinearSRGBColorSpace,RGBAFormat,LinearFilter,Texture,Vector3,type IUniform,type PixelFormat,type WebGLProgramParametersWithUniforms} from 'three';
import {assetDependency,entityTransform,quaternion,vector,type Entity,type Quat,type Vec3} from './world-data';
import {requireAssetResponse} from './asset-errors';
import type {NativeSkyDecoded} from './zone-texture-worker';

export type ZoneComponent='keyLight'|'ambientLight'|'skybox'|'haze';
export type ComponentMode='inherit'|'enabled'|'disabled';
export interface ZoneComponentSelection {mode:'enabled'|'disabled';entity:Entity}
export interface ZoneEnvironment {
  zones:Entity[];
  keyLight?:ZoneComponentSelection;ambientLight?:ZoneComponentSelection;
  skybox?:ZoneComponentSelection;haze?:ZoneComponentSelection;
}
/** Undefined means the compound resource is not loaded, matching native's box fallback. */
export type CompoundZoneContains=(entity:Entity,point:Vec3)=>boolean|undefined;
const record=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const finite=(value:unknown,fallback:number)=>typeof value==='number'&&Number.isFinite(value)?value:fallback;
const dimensions=(entity:Entity)=>vector(entity.dimensions,.1);
const uuid=(id:string)=>id.replace(/[{}-]/g,'').toLowerCase();

export function zoneContains(entity:Entity,point:Vec3,entities:ReadonlyMap<string,Entity>,compound?:CompoundZoneContains):boolean {
  if(entity.type!=='Zone'||entity.visible===false)return false;
  const d=dimensions(entity);if(![d.x,d.y,d.z].every(v=>Number.isFinite(v)&&v>0))return false;
  if(entity.shapeType==='compound'&&compound){const result=compound(entity,point);if(result!==undefined)return result;}
  const transform=entityTransform(entity,entities),registration=vector(entity.registrationPoint,.5).clampScalar(0,1);
  const center=new Vector3(.5,.5,.5).sub(registration).multiply(d).applyQuaternion(transform.rotation).add(transform.position);
  const local=vector(point).sub(center).applyQuaternion(transform.rotation.clone().invert()).divide(d);
  const shape=entity.shapeType||'box';
  // Native equal-dimension spheres use strict '<'; ellipsoids use inclusive '<='.
  if(shape==='sphere'&&d.x===d.y&&d.y===d.z)return local.lengthSq()<.25;
  if(shape==='sphere'||shape==='ellipsoid')return local.lengthSq()<=.25;
  if(shape.startsWith('cylinder-')){
    const axis=shape.slice(-1);if(!['x','y','z'].includes(axis))return false;
    const [a,b]=(['x','y','z'] as const).filter(component=>component!==axis);
    return Math.abs(local[axis as 'x'|'y'|'z'])<=.5&&local[a]**2+local[b]**2<=.25;
  }
  if(shape==='none')return false;
  // EntityItem::contains explicitly treats these as bounding boxes. A loaded
  // compound resource overrides that result through the callback above.
  if(!['box','compound','simple-compound','simple-hull','hull','static-mesh','plane','circle','capsule-x','capsule-y','capsule-z'].includes(shape))return false;
  return Math.max(Math.abs(local.x),Math.abs(local.y),Math.abs(local.z))<=.5;
}

export function resolveZoneEnvironment(entities:ReadonlyMap<string,Entity>,position:Vec3,compound?:CompoundZoneContains):ZoneEnvironment {
  const zones=[...entities.values()].filter(entity=>zoneContains(entity,position,entities,compound));
  zones.sort((left,right)=>{
    const l=dimensions(left),r=dimensions(right),difference=l.x*l.y*l.z-r.x*r.y*r.z;
    if(difference)return difference;
    const a=uuid(left.id),b=uuid(right.id);return a<b?-1:a>b?1:0;
  });
  const result:ZoneEnvironment={zones};
  for(const component of ['keyLight','ambientLight','skybox','haze'] as const){
    for(const entity of zones){const mode=entity[component+'Mode'];
      if(mode==='enabled'||mode==='disabled'){result[component]={mode,entity};break;}
    }
  }
  return result;
}

export function nativeZoneColor(value:unknown,fallback:readonly number[]):Vector3 {
  const color=record(value);
  return new Vector3(...(['red','green','blue'] as const).map((key,index)=>Math.max(0,Math.min(255,finite(color[key],fallback[index])))/255) as [number,number,number]);
}
export interface NativeHazeParameters {
  rangeFactor:number;heightFactor:number;base:number;altitude:boolean;
  color:Vector3;glareColor:Vector3;glare:boolean;glarePower:number;backgroundBlend:number;
  attenuateKeyLight:boolean;keyRangeFactor:number;keyHeightFactor:number;
}
const LOG_POINT_ZERO_FIVE=Math.log(.05);
export const nativeHazeRangeFactor=(range:number)=>-LOG_POINT_ZERO_FIVE/Math.max(range,1);
export const nativeHazeHeightFactor=(height:number)=>-LOG_POINT_ZERO_FIVE*Math.sign(height)/Math.max(Math.abs(height),1);
export function nativeHazeParameters(entity:Entity):NativeHazeParameters {
  const haze=record(entity.haze),base=finite(haze.hazeBaseRef,0),angle=Math.max(.1,finite(haze.hazeGlareAngle,20));
  // The native API permits values outside useful glare angles. Preserve its
  // formula; invalid powers are reported instead of silently inventing a sky.
  const power=Math.log(.5)/Math.log(Math.cos(angle*Math.PI/180));
  if(!Number.isFinite(power))throw Error('The Zone haze glare angle cannot produce a finite native glare effect.');
  return {rangeFactor:nativeHazeRangeFactor(finite(haze.hazeRange,1000)),heightFactor:nativeHazeHeightFactor(finite(haze.hazeCeiling,200)-base),
    base,altitude:haze.hazeAltitudeEffect===true,color:nativeZoneColor(haze.hazeColor,[128,154,179]),
    glareColor:nativeZoneColor(haze.hazeGlareColor,[255,229,179]),glare:haze.hazeEnableGlare===true,glarePower:power,
    backgroundBlend:finite(haze.hazeBackgroundBlend,0),attenuateKeyLight:haze.hazeAttenuateKeyLight===true,
    keyRangeFactor:nativeHazeRangeFactor(finite(haze.hazeKeyLightRange,1000)),keyHeightFactor:nativeHazeHeightFactor(finite(haze.hazeKeyLightAltitude,200))};
}
/** The actual native Haze.slh integral, including its 1 cm altitude threshold. */
export function sampleNativeHaze(haze:NativeHazeParameters,eye:Vec3,fragment:Vec3,lightDirection:Vec3={x:0,y:-1,z:0}):{color:Vector3;amount:number} {
  const ray=vector(fragment).sub(vector(eye)),distance=ray.length(),deltaHeight=fragment.y-eye.y;
  let integral=haze.rangeFactor*distance;
  if(haze.altitude){
    integral*=Math.exp(-haze.heightFactor*(eye.y-haze.base));
    const t=haze.heightFactor*deltaHeight;
    if(Math.abs(t)>1e-7&&Math.abs(deltaHeight)>.01)integral*= -Math.expm1(-t)/t;
  }
  let amount=-Math.expm1(-integral);
  if(distance>27000)amount*=haze.backgroundBlend;
  const color=haze.color.clone();
  if(haze.glare&&distance>0){const dot=Math.max(0,ray.divideScalar(distance).dot(vector(lightDirection).negate()));
    color.lerp(haze.glareColor,Math.min(1,Math.pow(dot,haze.glarePower)));
  }
  return {color,amount};
}
export function nativeKeyLightAttenuation(haze:NativeHazeParameters,fragment:Vec3,direction:Vec3):number {
  if(!haze.attenuateKeyLight)return 1;
  const height=haze.keyHeightFactor>0?-LOG_POINT_ZERO_FIVE/haze.keyHeightFactor:2000;
  const distance=height/Math.max(Math.abs(direction.y),.001);
  const density=haze.keyRangeFactor*Math.exp(-haze.keyHeightFactor*(fragment.y-haze.base));
  return Math.exp(-density*distance*.3171178);
}

/** Skybox.cpp negates w, equivalent to the inverse normalized Zone rotation. */
export function nativeSkyDirection(direction:Vec3,rotation?:Quat):Vector3 {return vector(direction).normalize().applyQuaternion(quaternion(rotation).invert());}
/** Native black tint is neutral when textured; every other tint multiplies. */
export function nativeSkyColor(texel:Vec3|undefined,tint:Vec3):Vector3 {
  if(!texel)return vector(tint);
  if(tint.x===0&&tint.y===0&&tint.z===0)return vector(texel);
  return vector(texel).multiply(vector(tint));
}
export interface NativeCubeFace {column:number;row:number;flipX:boolean;flipY:boolean}
export interface NativeSkyLayout {kind:'equirectangular'|'cube';faceSize:number;faces?:NativeCubeFace[]}
/** Exact native TextureProcessing.cpp layouts, in +X,-X,+Y,-Y,+Z,-Z order. */
export function nativeSkyLayout(width:number,height:number):NativeSkyLayout {
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width*height>32*1024*1024)throw Error('The Zone sky image has invalid or unsupported dimensions.');
  if(width===2*height)return {kind:'equirectangular',faceSize:Math.min(width/4,2048)};
  const face=(column:number,row:number,flipX:boolean,flipY:boolean)=>({column,row,flipX,flipY});
  if(height===width*6)return {kind:'cube',faceSize:width,faces:[face(0,0,true,false),face(0,1,true,false),face(0,2,false,true),face(0,3,false,true),face(0,4,true,false),face(0,5,true,false)]};
  if(width*3===height*4)return {kind:'cube',faceSize:width/4,faces:[face(2,1,true,false),face(0,1,true,false),face(1,0,false,true),face(1,2,false,true),face(3,1,true,false),face(1,1,true,false)]};
  if(width*4===height*3)return {kind:'cube',faceSize:width/3,faces:[face(2,1,true,false),face(0,1,true,false),face(1,0,false,true),face(1,2,false,true),face(1,3,false,true),face(1,1,true,false)]};
  throw Error('The Zone sky image must use a native 2:1 panorama, 1:6 strip, 4:3 cross or 3:4 cross layout.');
}

export interface NativeKeyLight {color:Vector3;intensity:number;direction:Vector3;castShadows:boolean;shadowBias:number;shadowMaxDistance:number}
export function nativeZoneKeyLight(entity:Entity,entities:ReadonlyMap<string,Entity>):NativeKeyLight {
  const source=record(entity.keyLight),rotation=entityTransform(entity,entities).rotation;
  const direction=source.direction?vector(record(source.direction) as unknown as Vec3):new Vector3(0,-1,0);
  return {color:nativeZoneColor(source.color,[255,255,255]),intensity:finite(source.intensity,1),direction:direction.applyQuaternion(rotation),
    castShadows:source.castShadows===true,shadowBias:finite(source.shadowBias,.5),shadowMaxDistance:finite(source.shadowMaxDistance,40)};
}
export interface NativeAmbientLight {color:Vector3;intensity:number;url:string;rotation:Quaternion}
export function nativeZoneAmbientLight(entity:Entity,entities:ReadonlyMap<string,Entity>):NativeAmbientLight {
  const source=record(entity.ambientLight),sky=record(entity.skybox);
  return {color:nativeZoneColor(source.ambientColor,[0,0,0]),intensity:finite(source.ambientIntensity,.5),
    url:typeof source.ambientURL==='string'&&source.ambientURL?source.ambientURL:typeof sky.url==='string'?sky.url:'',rotation:entityTransform(entity,entities).rotation};
}

/** Source algebra pinned to fork cafd1f2b28bf513a53aec22f73260efcfed0e715.
 * gpu/Texture.cpp: sphericalHarmonicsFromTexture; graphics/SphericalHarmonics.shared.slh.
 * Input is the decoded native cube's LINEAR RGB pixels, not browser sRGB bytes.
 */
export type NativeSH=readonly Vector3[];
export interface NativeLinearCube {
  size:number;
  readPixel:(face:number,x:number,y:number,output:Vector3)=>void;
}
export const NATIVE_BREEZEWAY_SH:NativeSH=Object.freeze([[.32,.36,.38],[.37,.41,.45],[-.01,-.01,-.01],[-.10,-.12,-.12],[-.13,-.15,-.17],[-.01,-.02,.02],[-.07,-.08,-.09],[.02,.03,.03],[-.29,-.32,-.36]].map(rgb=>Object.freeze(new Vector3(...rgb as [number,number,number]))));
/** Native cube storage axes differ from Three's SH generator, including sign flips. */
export function nativeSHCubeDirection(face:number,x:number,y:number,size:number):Vector3 {
  if(!Number.isInteger(face)||face<0||face>5||!Number.isInteger(size)||size<1)throw Error('Invalid native SH cube coordinates.');
  const u=(2*x+1)/size,v=(2*y+1)/size;
  const directions=[[-1,v-1,u-1],[1,v-1,1-u],[1-u,-1,1-v],[1-u,1,v-1],[u-1,1-v,1],[1-u,1-v,-1]];
  return new Vector3(...directions[face] as [number,number,number]).normalize();
}
export async function integrateNativeAmbientSH(cube:NativeLinearCube,options:NativeSkyLoadOptions={}):Promise<NativeSH> {
  const size=cube.size;
  if(!Number.isInteger(size)||size<1||size>4096||size*size*6>SKY_TOTAL_PIXELS)throw Error('The native ambient cube exceeds its decoded pixel budget.');
  const controller=new AbortController(),signal=controller.signal;
  const abort=()=>controller.abort(options.signal?.reason||new DOMException('The native ambient calculation was cancelled.','AbortError'));
  options.signal?.addEventListener('abort',abort,{once:true});if(options.signal?.aborted)abort();
  const timer=setTimeout(()=>controller.abort(new Error('The native ambient calculation exceeded its deadline.')),options.timeoutMs??30000);
  const coefficients=Array.from({length:9},()=>new Vector3()),pixel=new Vector3(),sum=new Vector3();
  const divisions=Math.min(32,size),stride=Math.floor(size/divisions),half=Math.floor(stride/2);
  let weight=0,lastYield=performance.now(),work=0;
  try{
    checkAbort(signal);
    for(let face=0;face<6;face++)for(let y=half;y<size-half;y+=stride)for(let x=half;x<size-half;x+=stride){
      const direction=nativeSHCubeDirection(face,x,y,size),{x:dx,y:dy,z:dz}=direction;
      const u=-1+(2*x+1)/size,v=-1+(2*y+1)/size,solid=4/((1+u*u+v*v)**1.5);
      const basis=[.28209479177,-.4886025119*dy,.4886025119*dz,-.4886025119*dx,1.09254843059*dx*dy,-1.09254843059*dz*dy,.94617469576*dz*dz-.31539156525,-1.09254843059*dz*dx,.5462742153*(dx*dx-dy*dy)];
      sum.set(0,0,0);
      for(let i=0;i<stride;i++)for(let j=0;j<stride;j++){
        cube.readPixel(face,x+i-half,y+j-half,pixel);
        if(![pixel.x,pixel.y,pixel.z].every(Number.isFinite))throw Error('The native ambient cube contains non-finite linear pixels.');
        sum.add(pixel);
        if(++work%2048===0&&performance.now()-lastYield>=8){await new Promise<void>(resolve=>setTimeout(resolve,0));checkAbort(signal);lastYield=performance.now();}
      }
      for(let index=0;index<9;index++)coefficients[index].addScaledVector(sum,basis[index]*solid);
      weight+=solid;
    }
    checkAbort(signal);
    // Native averages all pixels in each tile and projects its center direction.
    const normalization=4*Math.PI/(weight*stride*stride);
    for(const coefficient of coefficients)coefficient.multiplyScalar(normalization);
    return coefficients;
  }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}
/** Exact native irradiance polynomial; normalization/clamping belongs to the renderer. */
export function evaluateNativeAmbientSH(coefficients:NativeSH,normal:Vec3):Vector3 {
  if(coefficients.length!==9)throw Error('Native ambient lighting requires nine SH coefficients.');
  const {x,y,z}=normal,weights=[.886227,2*.511664*y,2*.511664*z,2*.511664*x,2*.429043*x*y,2*.429043*y*z,.743125*z*z-.247708,2*.429043*x*z,.429043*(x*x-y*y)];
  const result=new Vector3();for(let index=0;index<9;index++)result.addScaledVector(coefficients[index],weights[index]);return result;
}
export function sampleNativeAmbient(light:NativeAmbientLight,normal:Vec3,coefficients?:NativeSH):Vector3 {
  if(!light.url)return light.color.clone().multiplyScalar(light.intensity);
  const local=vector(normal).applyQuaternion(light.rotation.clone().invert());
  return nativeSkyColor(evaluateNativeAmbientSH(coefficients||NATIVE_BREEZEWAY_SH,local),light.color).multiplyScalar(light.intensity);
}

export interface NativeSkyLoadOptions {signal?:AbortSignal;timeoutMs?:number}
const SKY_SOURCE_PIXELS=32*1024*1024,SKY_TOTAL_PIXELS=64*1024*1024,SKY_MAX_BYTES=64*1024*1024;
const checkAbort=(signal:AbortSignal)=>{if(signal.aborted)throw signal.reason||new DOMException('The Zone sky load was cancelled.','AbortError');};
function skyDecodeDimensions(width:number,height:number):void {nativeSkyLayout(width,height);}
function preflightSkyDimensions(bytes:Uint8Array,source:string):void {
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(/\.hdr(?:[?#]|$)/i.test(source)){
    const header=new TextDecoder().decode(bytes.subarray(0,8192));
    const match=/(?:^|\n)-Y\s+(\d+)\s+\+X\s+(\d+)\s*(?:\r?\n)/.exec(header);
    if(!match)throw Error('The native HDR sky has an unsupported resolution header.');
    skyDecodeDimensions(Number(match[2]),Number(match[1]));
  }else if(/\.tga(?:[?#]|$)/i.test(source)){
    if(bytes.length<18)throw Error('The native TGA sky header is incomplete.');
    skyDecodeDimensions(view.getUint16(12,true),view.getUint16(14,true));
  }else if(bytes.length>=24&&bytes[0]===137&&bytes[1]===80&&bytes[2]===78&&bytes[3]===71){
    skyDecodeDimensions(view.getUint32(16,false),view.getUint32(20,false));
  }else if(bytes.length>=4&&bytes[0]===255&&bytes[1]===216){
    let cursor=2;
    while(cursor+4<=bytes.length){
      if(bytes[cursor++]!==255)break;while(bytes[cursor]===255)cursor++;
      const marker=bytes[cursor++];if(marker===217||marker===218)break;
      if(marker===0||marker===1||marker>=208&&marker<=215)continue;
      const size=view.getUint16(cursor,false);if(size<2||cursor+size>bytes.length)break;
      if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker)&&size>=7){skyDecodeDimensions(view.getUint16(cursor+5,false),view.getUint16(cursor+3,false));break;}
      cursor+=size;
    }
  }
}
async function boundedSkyBytes(response:Response,signal:AbortSignal,maximum:number):Promise<Uint8Array<ArrayBuffer>>{
  if(!response.body)throw Error('The Zone sky response has no data.');
  const reader=response.body.getReader(),parts:Uint8Array[]=[];let bytes=0;
  const aborted=()=>{void reader.cancel(signal.reason).catch(()=>{});};signal.addEventListener('abort',aborted,{once:true});
  try{while(true){checkAbort(signal);const part=await reader.read();checkAbort(signal);if(part.done)break;
    bytes+=part.value.byteLength;if(bytes>maximum){await reader.cancel();throw Error('The Zone sky response exceeds its permitted byte limit.');}parts.push(part.value);}
    const output=new Uint8Array(bytes);let offset=0;for(const part of parts){output.set(part,offset);offset+=part.byteLength;}return output;
  }finally{signal.removeEventListener('abort',aborted);reader.releaseLock();}
}
/** The actual trusted worker is bounded, owns one request, and always terminates. */
export async function decodeNativeSkyBounded(kind:'hdr'|'tga',buffer:ArrayBuffer,signal:AbortSignal):Promise<NativeSkyDecoded> {
  checkAbort(signal);
  let pixels=Infinity;
  if(kind==='tga'&&buffer.byteLength>=18){const view=new DataView(buffer);pixels=view.getUint16(12,true)*view.getUint16(14,true);}
  if(kind==='hdr'){const match=/(?:^|\n)-Y\s+(\d+)\s+\+X\s+(\d+)\s*(?:\r?\n)/.exec(new TextDecoder().decode(new Uint8Array(buffer,0,Math.min(buffer.byteLength,8192))));if(match)pixels=Number(match[1])*Number(match[2]);}
  if(buffer.byteLength<=512*1024&&pixels<=65536){
    const {decodeNativeSky}=await import('./zone-texture-worker');checkAbort(signal);return decodeNativeSky(kind,buffer);
  }
  if(typeof Worker==='undefined')throw Error('This browser cannot decode a large native HDR/TGA sky without a worker.');
  const worker=new Worker(new URL('./zone-texture-worker.ts',import.meta.url),{type:'module'});
  return new Promise<NativeSkyDecoded>((resolve,reject)=>{
    let settled=false;
    const finish=(error?:unknown,image?:NativeSkyDecoded)=>{
      if(settled)return;settled=true;signal.removeEventListener('abort',abort);worker.terminate();
      if(error)reject(error);else resolve(image!);
    };
    const abort=()=>finish(signal.reason||new DOMException('The native sky decode was cancelled.','AbortError'));
    signal.addEventListener('abort',abort,{once:true});
    worker.onerror=()=>finish(new Error('The native HDR/TGA sky decoder worker failed.'));
    worker.onmessage=(event:MessageEvent)=>{
      if(signal.aborted){abort();return;}
      const value=event.data;
      if(value?.error){finish(new Error(String(value.error).slice(0,512)));return;}
      const image=value?.image;
      if(!image||!Number.isInteger(image.width)||!Number.isInteger(image.height)||image.width<1||image.height<1||image.width*image.height>SKY_SOURCE_PIXELS||
        !(image.data instanceof Uint8Array||image.data instanceof Uint16Array||image.data instanceof Float32Array)||image.data.length!==image.width*image.height*4||image.data.byteLength>256*1024*1024){
        finish(new Error('The native sky decoder returned invalid or oversized pixels.'));return;
      }
      finish(undefined,image);
    };
    try{worker.postMessage({kind,buffer},[buffer]);}catch(error){finish(error);}
  });
}
async function requireSkyResponse(response:Response,label:string,signal:AbortSignal):Promise<void>{
  if(response.ok)return;
  // Bound/cancel error bodies too; the shared readable-error helper otherwise
  // has no signal because most callers already own an asset request deadline.
  let body:Uint8Array<ArrayBuffer>|undefined;
  if(response.body){try{body=await boundedSkyBytes(response,signal,8192);}catch(error){checkAbort(signal);}}
  await requireAssetResponse(new Response(body||null,{status:response.status,headers:response.headers}),label);
}
/** Abort the request, bound bytes/pixels/deadline, and dispose every late decoded resource. */
export async function loadNativeSkyTexture(source:string,resolveAsset:(source:string)=>string,options:NativeSkyLoadOptions={}):Promise<Texture|CubeTexture> {
  const controller=new AbortController(),signal=controller.signal;
  const cancel=()=>controller.abort(options.signal?.reason||new DOMException('The Zone sky load was cancelled.','AbortError'));
  options.signal?.addEventListener('abort',cancel,{once:true});if(options.signal?.aborted)cancel();
  const timer=setTimeout(()=>controller.abort(new Error('The Zone sky did not finish loading within its 30-second deadline.')),options.timeoutMs??30000);
  let texture:Texture|undefined,bitmap:ImageBitmap|undefined;const ownedFaces:DataTexture[]=[];
  try{
    checkAbort(signal);
    if(/\.texmeta\.json(?:[?#]|$)/i.test(source)){
      const response=await fetch(resolveAsset(source),{signal});await requireSkyResponse(response,'Zone texture metadata',signal);
      const metadata=record(JSON.parse(new TextDecoder().decode(await boundedSkyBytes(response,signal,65536))));
      const original=metadata.original||metadata.uncompressed;
      if(typeof original!=='string'||!original||original.length>8192||/\.texmeta\.json(?:[?#]|$)/i.test(original))throw Error('The Zone texture metadata has no supported original image.');
      source=assetDependency(source,original);
    }
    const response=await fetch(resolveAsset(source),{signal});await requireSkyResponse(response,'Zone sky',signal);
    const bytes=await boundedSkyBytes(response,signal,SKY_MAX_BYTES);checkAbort(signal);preflightSkyDimensions(bytes,source);
    if(/\.hdr(?:[?#]|$)/i.test(source)){
      const image=await decodeNativeSkyBounded('hdr',bytes.buffer,signal);checkAbort(signal);
      texture=new DataTexture(image.data,image.width,image.height,RGBAFormat,image.type);texture.colorSpace=LinearSRGBColorSpace;
      texture.minFilter=texture.magFilter=LinearFilter;texture.flipY=true;texture.needsUpdate=true;
    }else if(/\.tga(?:[?#]|$)/i.test(source)){
      const image=await decodeNativeSkyBounded('tga',bytes.buffer,signal);checkAbort(signal);
      texture=new DataTexture(image.data,image.width,image.height,RGBAFormat);texture.colorSpace=SRGBColorSpace;texture.flipY=true;texture.needsUpdate=true;
    }else{
      // Decoder completion can occur after cancellation. Close its late bitmap
      // immediately; it must never become another session's displayed sky.
      const pending=createImageBitmap(new Blob([bytes],{type:response.headers.get('content-type')||'application/octet-stream'}));
      bitmap=await new Promise<ImageBitmap>((resolve,reject)=>{
        const aborted=()=>reject(signal.reason);signal.addEventListener('abort',aborted,{once:true});
        pending.then(image=>{signal.removeEventListener('abort',aborted);if(signal.aborted){image.close();reject(signal.reason);}else resolve(image);},error=>{signal.removeEventListener('abort',aborted);reject(error);});
      });
      checkAbort(signal);texture=new Texture(bitmap);texture.colorSpace=SRGBColorSpace;texture.needsUpdate=true;
    }
    const image=texture.image as {width:number;height:number;data?:Uint8Array|Uint16Array|Float32Array};
    const layout=nativeSkyLayout(image.width,image.height);checkAbort(signal);
    if(image.width*image.height>SKY_SOURCE_PIXELS||layout.faceSize>4096)throw Error('The Zone sky exceeds its decoded pixel or cube-face limit.');
    const allocated=image.width*image.height+(layout.kind==='cube'?layout.faceSize**2*6:Math.min(layout.faceSize,2048)**2*6);
    if(allocated>SKY_TOTAL_PIXELS)throw Error('The Zone sky atlas exceeds its total decoded pixel budget.');
    if(layout.kind==='equirectangular'){texture.mapping=EquirectangularReflectionMapping;
      if(bitmap){const owned=bitmap;texture.addEventListener('dispose',()=>owned.close());bitmap=undefined;}
      const result=texture;texture=undefined;return result;}
    const faces:Array<HTMLCanvasElement|DataTexture>=[];
    for(const face of layout.faces!){checkAbort(signal);
      if(image.data){
        const channels=image.data.length/(image.width*image.height);
        if(!Number.isInteger(channels)||channels<3||channels>4)throw Error('The native sky texture pixel format is unsupported.');
        const Data=image.data.constructor as typeof Uint8Array;
        const output=new Data(layout.faceSize*layout.faceSize*channels);
        let lastYield=performance.now();
        for(let y=0;y<layout.faceSize;y++){
          for(let x=0;x<layout.faceSize;x++){
            const sourceX=face.column*layout.faceSize+(face.flipX?layout.faceSize-1-x:x);
            const sourceY=face.row*layout.faceSize+(face.flipY?layout.faceSize-1-y:y);
            const from=(sourceY*image.width+sourceX)*channels,to=(y*layout.faceSize+x)*channels;
            for(let channel=0;channel<channels;channel++)output[to+channel]=image.data[from+channel];
          }
          if(performance.now()-lastYield>=8){await new Promise<void>(resolve=>setTimeout(resolve,0));checkAbort(signal);lastYield=performance.now();}
        }
        const data=new DataTexture(output,layout.faceSize,layout.faceSize,texture.format as PixelFormat,texture.type);
        data.colorSpace=texture.colorSpace;data.needsUpdate=true;faces.push(data);ownedFaces.push(data);
      }else{
        const canvas=document.createElement('canvas');canvas.width=canvas.height=layout.faceSize;
        const context=canvas.getContext('2d');if(!context)throw Error('The browser cannot decode the native cube sky image.');
        context.translate(face.flipX?layout.faceSize:0,face.flipY?layout.faceSize:0);context.scale(face.flipX?-1:1,face.flipY?-1:1);
        context.drawImage(texture.image as CanvasImageSource,face.column*layout.faceSize,face.row*layout.faceSize,layout.faceSize,layout.faceSize,0,0,layout.faceSize,layout.faceSize);
        faces.push(canvas);await new Promise<void>(resolve=>setTimeout(resolve,0));checkAbort(signal);
      }
    }
    const cube=new CubeTexture<HTMLCanvasElement|DataTexture>(faces);cube.colorSpace=texture.colorSpace;cube.format=texture.format;cube.type=texture.type;cube.needsUpdate=true;
    texture.dispose();texture=undefined;bitmap?.close();bitmap=undefined;const transferred=ownedFaces.splice(0);cube.addEventListener('dispose',()=>{for(const face of transferred)face.dispose();});return cube;
  }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',cancel);texture?.dispose();bitmap?.close();for(const face of ownedFaces)face.dispose();}
}

export interface NativeHazeUniforms {[key:string]:IUniform}
export function createNativeHazeUniforms():NativeHazeUniforms {
  return {nativeHazeActive:{value:false},nativeHazeAltitude:{value:false},nativeHazeGlare:{value:false},nativeHazeRange:{value:0},nativeHazeHeight:{value:0},
    nativeHazeBase:{value:0},nativeHazeColor:{value:new Vector3()},nativeHazeGlareColor:{value:new Vector3()},nativeHazeGlarePower:{value:1},nativeHazeBackground:{value:0},
    nativeHazeEye:{value:new Vector3()},nativeHazeLightDirection:{value:new Vector3(0,-1,0)},nativeHazeCameraWorld:{value:new Matrix4()},
    nativeHazeKeyAttenuated:{value:false},nativeHazeKeyRange:{value:0},nativeHazeKeyHeight:{value:0}};
}
export function updateNativeHazeUniforms(uniforms:NativeHazeUniforms,haze:NativeHazeParameters|undefined,camera:Camera,direction:Vec3):void {
  camera.updateWorldMatrix(true,false);uniforms.nativeHazeCameraWorld.value.copy(camera.matrixWorld);
  uniforms.nativeHazeEye.value.setFromMatrixPosition(camera.matrixWorld);uniforms.nativeHazeLightDirection.value.copy(vector(direction));
  uniforms.nativeHazeActive.value=!!haze;if(!haze)return;
  for(const [key,value] of Object.entries({nativeHazeAltitude:haze.altitude,nativeHazeGlare:haze.glare,nativeHazeRange:haze.rangeFactor,nativeHazeHeight:haze.heightFactor,
    nativeHazeBase:haze.base,nativeHazeGlarePower:haze.glarePower,nativeHazeBackground:haze.backgroundBlend,
    nativeHazeKeyAttenuated:haze.attenuateKeyLight,nativeHazeKeyRange:haze.keyRangeFactor,nativeHazeKeyHeight:haze.keyHeightFactor}))uniforms[key].value=value;
  uniforms.nativeHazeColor.value.copy(haze.color);uniforms.nativeHazeGlareColor.value.copy(haze.glareColor);
}
// Adapted from graphics/Haze.slh (High Fidelity, Inc.; Overte e.V.; Apache-2.0).
export const NATIVE_HAZE_GLSL=`
uniform bool nativeHazeActive,nativeHazeAltitude,nativeHazeGlare,nativeHazeKeyAttenuated;
uniform float nativeHazeRange,nativeHazeHeight,nativeHazeBase,nativeHazeGlarePower,nativeHazeBackground,nativeHazeKeyRange,nativeHazeKeyHeight;
uniform vec3 nativeHazeColor,nativeHazeGlareColor,nativeHazeEye,nativeHazeLightDirection;
vec4 overteNativeHaze(vec3 point) {
  vec3 ray=point-nativeHazeEye;float distance=length(ray),integral=nativeHazeRange*distance;
  if(nativeHazeAltitude){
    integral*=exp(-nativeHazeHeight*(nativeHazeEye.y-nativeHazeBase));
    float dy=point.y-nativeHazeEye.y,t=nativeHazeHeight*dy;
    if(abs(t)>0.0000001&&abs(dy)>0.01)integral*=(1.0-exp(-t))/t;
  }
  float amount=1.0-exp(-integral);if(distance>27000.0)amount*=nativeHazeBackground;
  vec3 color=nativeHazeColor;
  if(nativeHazeGlare&&distance>0.0){float glare=max(0.0,dot(ray/distance,-nativeHazeLightDirection));color=mix(color,nativeHazeGlareColor,min(1.0,pow(glare,nativeHazeGlarePower)));}
  return vec4(color,amount);
}
float overteNativeKeyAttenuation(vec3 point){
  if(!nativeHazeActive||!nativeHazeKeyAttenuated)return 1.0;
  float height=nativeHazeKeyHeight>0.0?2.995732273553991/nativeHazeKeyHeight:2000.0;
  float distance=height/max(abs(nativeHazeLightDirection.y),0.001);
  float density=nativeHazeKeyRange*exp(-nativeHazeKeyHeight*(point.y-nativeHazeBase));
  return exp(-density*distance*0.3171178);
}`;

type CompileHook=Material['onBeforeCompile'];
type CacheHook=Material['customProgramCacheKey'];
interface OwnedHazeHooks {compile:CompileHook;cache:CacheHook;parentCompile:CompileHook;parentCache:CacheHook;uniforms:NativeHazeUniforms}
const ownedHazeHooks=new WeakMap<Material,OwnedHazeHooks>();
/** Asset userData cannot grant shader trust; both the owned wrapper and parent must be proved. */
export function hasNativeHazeShader(material:Material,parentIsSafe:(compile:CompileHook,cache:CacheHook)=>boolean):boolean {
  const hooks=ownedHazeHooks.get(material);
  return !!hooks&&material.onBeforeCompile===hooks.compile&&material.customProgramCacheKey===hooks.cache&&parentIsSafe(hooks.parentCompile,hooks.parentCache);
}
/** Restore only our exact current pair. Never overwrite a later foreign mutation. */
export function restoreNativeHazeShader(material:Material):boolean {
  const hooks=ownedHazeHooks.get(material);
  if(!hooks||material.onBeforeCompile!==hooks.compile||material.customProgramCacheKey!==hooks.cache)return false;
  material.onBeforeCompile=hooks.parentCompile;material.customProgramCacheKey=hooks.parentCache;
  ownedHazeHooks.delete(material);material.needsUpdate=true;return true;
}
/** Compose with existing shader hooks; one stable program variant, no per-Zone recompilation. */
export function installNativeZoneHaze(material:Material,uniforms:NativeHazeUniforms):void {
  const installed=ownedHazeHooks.get(material);
  if(installed){
    if(material.onBeforeCompile===installed.compile&&material.customProgramCacheKey===installed.cache){
      if(installed.uniforms!==uniforms)throw Error('The material already belongs to another native Zone environment.');return;
    }
    throw Error('The material shader changed after native Zone haze was installed.');
  }
  const previous=material.onBeforeCompile,previousKey=material.customProgramCacheKey;
  material.onBeforeCompile=function(shader:WebGLProgramParametersWithUniforms,renderer){
    previous.call(this,shader,renderer);
    if(!shader.vertexShader.includes('#include <project_vertex>')||!shader.fragmentShader.includes('#include <tonemapping_fragment>'))return;
    Object.assign(shader.uniforms,uniforms);
    shader.vertexShader='uniform mat4 nativeHazeCameraWorld;\nvarying vec3 overteHazeWorldPosition;\n'+shader.vertexShader.replace('#include <project_vertex>',
      '#include <project_vertex>\noverteHazeWorldPosition=(nativeHazeCameraWorld*mvPosition).xyz;');
    shader.fragmentShader='varying vec3 overteHazeWorldPosition;\n'+NATIVE_HAZE_GLSL+'\n'+shader.fragmentShader;
    // Haze is part of native linear scene lighting, before display tone/color conversion.
    shader.fragmentShader=shader.fragmentShader.replace('#include <tonemapping_fragment>',
      'if(nativeHazeActive){vec4 haze=overteNativeHaze(overteHazeWorldPosition);gl_FragColor.rgb=mix(gl_FragColor.rgb,haze.rgb,haze.a);}\n#include <tonemapping_fragment>');
    // Native haze attenuates its key directional light, never entity point/spot lights.
    // The owned Zone light is the only matching directional source; leave all
    // other native/embedded lighting paths untouched.
    if(shader.fragmentShader.includes('#include <lights_fragment_begin>'))shader.fragmentShader=shader.fragmentShader.replace('#include <lights_fragment_begin>',
      ShaderChunk.lights_fragment_begin.replace('getDirectionalLightInfo( directionalLight, directLight );',
        'getDirectionalLightInfo( directionalLight, directLight );\nif(dot(directLight.direction,transformDirection(-nativeHazeLightDirection,viewMatrix))>0.999999){directLight.color*=overteNativeKeyAttenuation(overteHazeWorldPosition);}'));
  };
  material.customProgramCacheKey=function(){return previousKey.call(this)+'|overte-native-zone-haze-v1';};
  ownedHazeHooks.set(material,{compile:material.onBeforeCompile,cache:material.customProgramCacheKey,parentCompile:previous,parentCache:previousKey,uniforms});material.needsUpdate=true;
}

export const NATIVE_SKY_VERTEX=`varying vec3 nativeSkyRay;void main(){nativeSkyRay=position;vec4 clip=projectionMatrix*mat4(mat3(viewMatrix))*vec4(position,1.0);gl_Position=clip.xyww;}`;
export const NATIVE_SKY_FRAGMENT=`
varying vec3 nativeSkyRay;uniform bool nativeSkyTextured,nativeSkyCube;uniform sampler2D nativeSkyImage;uniform samplerCube nativeSkyCubeImage;
uniform vec3 nativeSkyTint;uniform mat4 nativeSkyRotation;
${NATIVE_HAZE_GLSL}
void main(){
 vec3 ray=normalize(nativeSkyRay),sampleRay=(nativeSkyRotation*vec4(ray,0.0)).xyz;
 vec3 color=nativeSkyTint;
 if(nativeSkyTextured){
  vec2 uv=vec2(atan(sampleRay.z,sampleRay.x)/6.283185307179586+0.5,asin(clamp(sampleRay.y,-1.0,1.0))/3.141592653589793+0.5);
  color=nativeSkyCube?textureCube(nativeSkyCubeImage,sampleRay).rgb:texture2D(nativeSkyImage,uv).rgb;
  if(any(notEqual(nativeSkyTint,vec3(0.0))))color*=nativeSkyTint;
 }
 if(nativeHazeActive){vec4 haze=overteNativeHaze(nativeHazeEye+ray*32000.0);color=mix(color,haze.rgb,haze.a);}
 gl_FragColor=vec4(color,1.0);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;

export interface ZoneEnvironmentOptions {
  resolveAsset:(source:string)=>string;onStatus:(message:string)=>void;
  fallbackKeyLights?:Light[];fallbackAmbientLights?:Light[];
  compoundContains?:CompoundZoneContains;
}
/** Own local sky/key light and the shared haze state. Ambient SH is exposed separately for renderer integration. */
export class NativeZoneEnvironment {
  readonly hazeUniforms=createNativeHazeUniforms();
  readonly keyLight=new DirectionalLight();
  readonly sky:Mesh;
  private entities:ReadonlyMap<string,Entity>=new Map();private selection:ZoneEnvironment={zones:[]};
  private signature='';private source='';private texture:Texture|undefined;private generation=0;private disposed=false;
  private materials=new Set<Material>();private skyAbort:AbortController|undefined;private fallbackState=new Map<Light,{visible:boolean;intensity:number}>();
  private haze:NativeHazeParameters|undefined;private direction=new Vector3(0,-1,0);
  constructor(private scene:Scene,private options:ZoneEnvironmentOptions){
    const material=new ShaderMaterial({vertexShader:NATIVE_SKY_VERTEX,fragmentShader:NATIVE_SKY_FRAGMENT,side:BackSide,depthWrite:false,depthTest:true,
      uniforms:{...this.hazeUniforms,nativeSkyTextured:{value:false},nativeSkyCube:{value:false},nativeSkyImage:{value:null},nativeSkyCubeImage:{value:null},nativeSkyTint:{value:new Vector3()},nativeSkyRotation:{value:new Matrix4()}}});
    this.sky=new Mesh(new BoxGeometry(2,2,2),material);this.sky.frustumCulled=false;this.sky.renderOrder=-10000;this.sky.visible=false;
    for(const light of [...options.fallbackKeyLights||[],...options.fallbackAmbientLights||[]])this.fallbackState.set(light,{visible:light.visible,intensity:light.intensity});
    this.keyLight.intensity=0;scene.add(this.sky,this.keyLight,this.keyLight.target);
  }
  setEntities(entities:ReadonlyMap<string,Entity>):void {this.entities=entities;this.signature='';}
  getSelection():ZoneEnvironment {return this.selection;}
  getAmbientLight():NativeAmbientLight|undefined {return this.selection.ambientLight?.mode==='enabled'?nativeZoneAmbientLight(this.selection.ambientLight.entity,this.entities):undefined;}
  attachMaterial(material:Material):void {if(this.disposed)return;installNativeZoneHaze(material,this.hazeUniforms);this.materials.add(material);}
  update(position:Vec3,camera:Camera):void {
    if(this.disposed)return;
    const selection=resolveZoneEnvironment(this.entities,position,this.options.compoundContains);
    const signature=JSON.stringify(['keyLight','ambientLight','skybox','haze'].map(component=>{const selected=selection[component as ZoneComponent];return selected?[selected.entity.id,selected.mode]:null;}));
    if(signature!==this.signature){this.selection=selection;this.signature=signature;this.apply();}
    updateNativeHazeUniforms(this.hazeUniforms,this.haze,camera,this.direction);
  }
  private apply():void {
    const selection=this.selection,key=selection.keyLight;
    for(const light of this.options.fallbackKeyLights||[])light.intensity=key?0:this.fallbackState.get(light)!.intensity;
    // This prepared class exposes native ambient data, but must not replace
    // renderer ambient lighting until its native Fresnel/mip adapter is reviewed.
    if(selection.ambientLight)this.options.onStatus('Zone ambient rendering is awaiting the validated native Fresnel and filtered-cubemap adapter.');
    this.keyLight.intensity=0;
    if(key?.mode==='enabled'){
      const state=nativeZoneKeyLight(key.entity,this.entities);this.direction.copy(state.direction);
      this.keyLight.color.copy(new Color().setRGB(state.color.x,state.color.y,state.color.z));this.keyLight.intensity=state.intensity;
      this.keyLight.position.copy(this.direction).negate();this.keyLight.target.position.set(0,0,0);
      this.keyLight.castShadow=false;
      if(state.castShadows)this.options.onStatus('Zone key-light shadows require a validated native bias/cascade mapping and are not yet supported.');
    }else this.direction.set(0,-1,0);
    try{this.haze=selection.haze?.mode==='enabled'?nativeHazeParameters(selection.haze.entity):undefined;}
    catch(error){this.haze=undefined;this.options.onStatus(error instanceof Error?error.message:String(error));}
    const sky=selection.skybox;this.sky.visible=!!sky;const material=this.sky.material as ShaderMaterial;
    if(sky?.mode==='enabled'){
      const properties=record(sky.entity.skybox),rotation=entityTransform(sky.entity,this.entities).rotation;
      material.uniforms.nativeSkyTint.value.copy(nativeZoneColor(properties.color,[0,0,0]));
      material.uniforms.nativeSkyRotation.value.makeRotationFromQuaternion(rotation.invert());
      this.setSource(typeof properties.url==='string'?properties.url:'');
    }else{material.uniforms.nativeSkyTint.value.set(0,0,0);this.setSource('');}
  }
  private setSource(source:string):void {
    if(source===this.source)return;this.skyAbort?.abort();this.skyAbort=undefined;this.source=source;const generation=++this.generation,material=this.sky.material as ShaderMaterial;
    this.texture?.dispose();this.texture=undefined;material.uniforms.nativeSkyTextured.value=false;
    if(!source)return;
    this.skyAbort=new AbortController();
    void loadNativeSkyTexture(source,this.options.resolveAsset,{signal:this.skyAbort.signal}).then(texture=>{
      if(this.disposed||generation!==this.generation){texture.dispose();return;}
      this.texture=texture;material.uniforms.nativeSkyTextured.value=true;material.uniforms.nativeSkyCube.value=texture instanceof CubeTexture;
      material.uniforms[texture instanceof CubeTexture?'nativeSkyCubeImage':'nativeSkyImage'].value=texture;
    }).catch(error=>{if(!this.disposed&&generation===this.generation)this.options.onStatus('Zone sky image could not load: '+(error instanceof Error?error.message:String(error)));});
  }
  dispose():void {
    if(this.disposed)return;this.disposed=true;this.generation++;this.skyAbort?.abort();this.skyAbort=undefined;this.texture?.dispose();this.keyLight.shadow.dispose();
    for(const material of this.materials)restoreNativeHazeShader(material);this.materials.clear();
    this.scene.remove(this.sky,this.keyLight,this.keyLight.target);this.sky.geometry.dispose();(this.sky.material as Material).dispose();
    for(const [light,state] of this.fallbackState){light.visible=state.visible;light.intensity=state.intensity;}
  }
}
