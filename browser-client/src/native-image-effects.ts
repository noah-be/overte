// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Pinned native equations: f91d15a RenderableImageEntityItem.cpp,
// RenderableEntityItem.cpp, Sampler.h/ScriptValueUtils.cpp and Texture_ktx.cpp.
import * as THREE from 'three';
import type {Entity,Vec3} from './world-data';
import type {NativeImageMaterial} from './native-image-material';
import {nativeCompressedImageOriginalSize} from './native-compressed-color';

export interface ImageExtent {width:number;height:number}
export interface ImagePulse {min:number;max:number;period:number;colorMode:'none'|'in'|'out';alphaMode:'none'|'in'|'out';created:number}
export interface NativeImagePlan {size:Vec3;uv:readonly[number,number,number,number];sampler:{min:THREE.MinificationTextureFilter;mag:THREE.MagnificationTextureFilter;u:THREE.Wrapping;v:THREE.Wrapping;anisotropy:number};pulse?:ImagePulse;warnings:string[]}
function record(value:unknown,label:string):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw Error(`Image ${label} must be a native record`);return value as Record<string,unknown>;}
function number(value:unknown,fallback:number,label:string):number{const result=value===undefined?fallback:value;if(typeof result!=='number'||!Number.isFinite(result))throw Error(`Image ${label} must be finite`);return result;}
/** Native scaleX/scaleY and QRect setters use float arithmetic then int truncation. */
export function nativeImageCropCoordinate(value:number,loaded:number,original:number):number{return Math.trunc(Math.fround(Math.fround(loaded/original)*value));}
function extent(width:unknown,height:unknown):ImageExtent|undefined{return Number.isSafeInteger(width)&&Number.isSafeInteger(height)&&(width as number)>0&&(height as number)>0?{width:width as number,height:height as number}:undefined;}
function mode(value:unknown):ImagePulse['colorMode']{if(value===undefined)return 'none';if(value==='none'||value==='in'||value==='out')return value;throw Error('Image pulse mode is unsupported');}
const minFilters:Record<string,THREE.MinificationTextureFilter>={point:THREE.NearestFilter,linear:THREE.LinearFilter,mipmapPoint:THREE.NearestMipmapNearestFilter,mipmapLinear:THREE.NearestMipmapLinearFilter,linearMipmapPoint:THREE.LinearMipmapNearestFilter,linearMipmapLinear:THREE.LinearMipmapLinearFilter};
function wrap(value:unknown,warnings:string[]):THREE.Wrapping{if(value===undefined||value==='repeat')return THREE.RepeatWrapping;if(value==='mirror')return THREE.MirroredRepeatWrapping;if(value==='clamp')return THREE.ClampToEdgeWrapping;warnings.push('Image sampler wrap is unsupported; repeat is used');return THREE.RepeatWrapping;}
/** Pure source-based preparation. Unknown effects warn; no global/shared Texture state is changed. */
export function planNativeImageEffects(entity:Entity,map:THREE.Texture,maximumAnisotropy:number):NativeImagePlan{
 const image=map.image as {width?:number;height?:number;naturalWidth?:number;naturalHeight?:number}|undefined;
 const loaded=extent(image?.naturalWidth??image?.width,image?.naturalHeight??image?.height);if(!loaded)throw Error('Image effects require loaded texture dimensions');
 const original=map instanceof THREE.CompressedTexture?nativeCompressedImageOriginalSize(map):loaded;
 const warnings:string[]=[];const size={x:number(entity.dimensions?.x,1,'width'),y:number(entity.dimensions?.y,1,'height'),z:number(entity.dimensions?.z,1,'depth')};
 if(size.x<=0||size.y<=0)throw Error('Image width and height must be positive');
 if(entity.keepAspectRatio!==undefined&&typeof entity.keepAspectRatio!=='boolean')throw Error('Image keepAspectRatio must be a native boolean');
 if(entity.keepAspectRatio!==false){if(original){const target=original.width/original.height,current=size.x/size.y;if(target<current)size.x*=target/current;else size.y/=target/current;}else warnings.push('Image original dimensions are unavailable; aspect fitting is unsupported');}
 let x=0,y=0,width=loaded.width,height=loaded.height;
 if(entity.subImage!==undefined){const crop=record(entity.subImage,'subImage');if(Object.keys(crop).some(key=>!['x','y','width','height'].includes(key)))warnings.push('Image subImage has unsupported fields');
  const values=['x','y','width','height'].map(key=>number(crop[key],0,`subImage ${key}`));if(!values.every(value=>Number.isInteger(value)&&value>=-2147483648&&value<=2147483647))throw Error('Image subImage requires native signed integer coordinates');
  if(values[2]>0||values[3]>0){if(original){if(values[2]>0){x=nativeImageCropCoordinate(values[0],loaded.width,original.width);width=nativeImageCropCoordinate(values[2],loaded.width,original.width);}if(values[3]>0){y=nativeImageCropCoordinate(values[1],loaded.height,original.height);height=nativeImageCropCoordinate(values[3],loaded.height,original.height);}}else warnings.push('Image original dimensions are unavailable; subImage is unsupported');}
 }
 // Native upload has top-origin rows; the existing browser sampler compensates
 // that orientation. Convert native bottom-left V to the canonical browser V.
 const uv:[number,number,number,number]=[(x+.5)/loaded.width,1-(y+height-.5)/loaded.height,(x+width-.5)/loaded.width,1-(y+.5)/loaded.height];
 const sampler=entity.sampler===undefined?{}:record(entity.sampler,'sampler');
 if(Object.keys(sampler).some(key=>!['borderColor','minFilter','magFilter','wrapModeU','wrapModeV','wrapModeW','filter','wrap','wrapS','wrapT'].includes(key)))warnings.push('Image sampler has unsupported fields');
 // Native readback contains minFilter/magFilter and wrapModeU/V; authoring aliases
 // are accepted only when their equivalent native semantics are unambiguous.
 let min=sampler.minFilter??'linearMipmapLinear',mag=sampler.magFilter??'linear';
 if(sampler.filter!==undefined){if(sampler.filter==='point'||sampler.filter==='linear'){min=mag=sampler.filter;}else warnings.push('Image sampler filter is unsupported; native defaults are used');}
 if(typeof min!=='string'||!Object.hasOwn(minFilters,min)){warnings.push('Image sampler minFilter is unsupported; trilinear is used');min='linearMipmapLinear';}
 if(mag!=='point'&&mag!=='linear'){warnings.push('Image sampler magFilter is unsupported; linear is used');mag='linear';}
 if(!Number.isFinite(maximumAnisotropy)||maximumAnisotropy<0)throw Error('Image sampler requires current renderer anisotropy capability');
 const u=wrap(sampler.wrapModeU??sampler.wrap??sampler.wrapS,warnings),v=wrap(sampler.wrapModeV??sampler.wrap??sampler.wrapT,warnings);
 if(sampler.wrapModeW!==undefined&&!['repeat','mirror','clamp'].includes(String(sampler.wrapModeW)))warnings.push('Image sampler W wrap is unsupported');
 let pulse:ImagePulse|undefined;
 if(entity.pulse!==undefined){const p=record(entity.pulse,'pulse');if(Object.keys(p).some(key=>!['min','max','period','colorMode','alphaMode'].includes(key)))warnings.push('Image pulse has unsupported fields');
  const parsed={min:number(p.min,0,'pulse min'),max:number(p.max,1,'pulse max'),period:number(p.period,1,'pulse period'),colorMode:mode(p.colorMode),alphaMode:mode(p.alphaMode),created:0};
  if(parsed.colorMode!=='none'||parsed.alphaMode!=='none'){
   parsed.created=typeof entity.created==='number'?entity.created:NaN;
   // Native out-of-range factors can switch alpha decoding through its signed
   // vertex-alpha convention. This public-material adapter does not approximate it.
   if(!Number.isFinite(parsed.created)||parsed.min<0||parsed.min>1||parsed.max<0||parsed.max>1||!Number.isSafeInteger(parsed.created)||parsed.created<0)warnings.push('Image pulse range or creation timestamp is unsupported');
   else pulse=parsed;
  }
 }
 return {size,uv,sampler:{min:minFilters[min as string],mag:mag==='point'?THREE.NearestFilter:THREE.LinearFilter,u,v,anisotropy:Math.min(16,Math.max(1,maximumAnisotropy))},pulse,warnings};
}
/** Apply only before first publication to a new owned clone; Source/version and
 * compressed orientation compensation remain untouched. UVs belong to this Plane. */
export function applyNativeImageEffects(plan:NativeImagePlan,map:THREE.Texture,geometry:THREE.PlaneGeometry,material:NativeImageMaterial):void{
 map.minFilter=plan.sampler.min;map.magFilter=plan.sampler.mag;map.wrapS=plan.sampler.u;map.wrapT=plan.sampler.v;map.anisotropy=plan.sampler.anisotropy;
 const uv=geometry.getAttribute('uv'),[u0,v0,u1,v1]=plan.uv;for(let i=0;i<uv.count;i++)uv.setXY(i,u0+(u1-u0)*uv.getX(i),v0+(v1-v0)*uv.getY(i));uv.needsUpdate=true;
 if(plan.pulse&&plan.pulse.alphaMode!=='none'){material.transparent=true;material.depthWrite=false;}
}
/** The native pulse multiplies sRGB albedo BEFORE the SIMPLE vertex shader
 * linearizes it; multiplying a material's linear color would be different. */
export function updateNativeImagePulse(pulse:ImagePulse,entity:Pick<Entity,'color'|'alpha'>,material:NativeImageMaterial,nowUsec:number):void{
 if(!Number.isFinite(nowUsec)||nowUsec<pulse.created)throw Error('Image pulse requires a current native creation clock');
 const f=Math.fround,t=f(f(nowUsec-pulse.created)/f(1e6));
 const wave=pulse.period===0?1:f(f(f(.5)*f(f(Math.cos(f(f(t*f(2*f(Math.PI)))/f(pulse.period))))+f(1)))*f(f(pulse.max)-f(pulse.min))+f(pulse.min));
 const factor=(mode:ImagePulse['colorMode'])=>pulse.period===0||mode==='none'?1:mode==='in'?wave:f(1-wave);
 const color=entity.color??{red:255,green:255,blue:255},c=factor(pulse.colorMode),a=factor(pulse.alphaMode);
 material.color.setRGB(f(f(color.red/255)*c),f(f(color.green/255)*c),f(f(color.blue/255)*c),THREE.SRGBColorSpace);material.opacity=f(f(Math.max(0,Math.min(1,entity.alpha??1)))*a);
}
