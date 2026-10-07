// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {CompressedTexture,Color,MeshBasicMaterial,MeshStandardMaterial,SRGBColorSpace,type Texture} from 'three';
import {nativeCompressedColorAlpha} from './native-compressed-color';
import {nativeTextureAlpha,type NativeTextureAlpha} from './texture-alpha';
import {applyNativeRenderState} from './native-render-state';
import type {Entity} from './world-data';

export type NativeImageMaterial=MeshBasicMaterial|MeshStandardMaterial;
/** Image SIMPLE material defaults from RenderableImageEntityItem and DefaultMaterials.slh.
 * Image alpha is blended directly; model OPACITY_MAP_MASK is deliberately absent.
 * This factory borrows the texture. The owning World disposes its own clone.
 */
export function makeNativeImageMaterial(entity:Pick<Entity,'color'|'alpha'>&{emissive?:unknown},map:Texture,alpha:NativeTextureAlpha):NativeImageMaterial {
 if(alpha!=='opaque'&&alpha!=='mask'&&alpha!=='blend')throw Error('Image texture alpha classification is unavailable');
 if(entity.emissive!==undefined&&typeof entity.emissive!=='boolean')throw Error('Image emissive must be a native boolean');
 const channels=entity.color?[entity.color.red,entity.color.green,entity.color.blue]:[255,255,255];
 if(!channels.every(value=>Number.isInteger(value)&&value>=0&&value<=255))throw Error('Image color requires native byte channels');
 if(entity.alpha!==undefined&&!Number.isFinite(entity.alpha))throw Error('Image alpha must be finite');
 const opacity=Math.max(0,Math.min(1,entity.alpha??1)),color=new Color().setRGB(channels[0]/255,channels[1]/255,channels[2]/255,SRGBColorSpace);
 const parameters={map,color,opacity,transparent:opacity<1||alpha!=='opaque',alphaTest:0,toneMapped:entity.emissive!==true};
 const material=entity.emissive===true?new MeshBasicMaterial(parameters):new MeshStandardMaterial({...parameters,roughness:.9,metalness:0});
 applyNativeRenderState(material,{cullFaceMode:'CULL_NONE'});
 return material;
}
/** Preserve compressed ownership and real original-image alpha inspection.
 * Unknown compressed sources and unreadable originals fail honestly, never use RGB as a mask.
 */
export async function inspectNativeImageAlpha(map:Texture,signal:AbortSignal):Promise<NativeTextureAlpha> {
 signal.throwIfAborted();
 const compressed=nativeCompressedColorAlpha(map);
 if(map instanceof CompressedTexture&&!compressed)throw Error('Image compressed alpha requires an approved native texture');
 const result=compressed??await nativeTextureAlpha(map,signal);
 signal.throwIfAborted();return result;
}
