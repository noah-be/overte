// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
// Observe the actual borrowed singleton, never change or dispose it. Its GPU
// allocation is nevertheless owned by each renderer context, not another World.
export function observeNativeImageDfg(texture:THREE.DataTexture){
 const sampler=()=>({minFilter:texture.minFilter,magFilter:texture.magFilter,wrapS:texture.wrapS,wrapT:texture.wrapT,anisotropy:texture.anisotropy,generateMipmaps:texture.generateMipmaps,flipY:texture.flipY,colorSpace:texture.colorSpace});
 const image=texture?.image;
 if(!texture?.isDataTexture||texture.name!=='DFG_LUT'||image?.width!==16||image?.height!==16||texture.format!==THREE.RGFormat||texture.type!==THREE.HalfFloatType||!(image.data instanceof Uint16Array)||image.data.length!==512||image.data.byteLength!==1024||texture.source.data!==image)throw Error('Authored Image fixture could not identify the actual borrowed Three DFG lookup');
 const expected={minFilter:THREE.LinearFilter,magFilter:THREE.LinearFilter,wrapS:THREE.ClampToEdgeWrapping,wrapT:THREE.ClampToEdgeWrapping,anisotropy:1,generateMipmaps:false,flipY:false,colorSpace:THREE.NoColorSpace};
 const before=sampler();if(JSON.stringify(before)!==JSON.stringify(expected))throw Error('Actual borrowed Three DFG sampler does not match its primary-source defaults');
 const source=texture.source,data=image.data,version=texture.version,sourceVersion=source.version;let disposeEvents=0;
 const onDispose=()=>disposeEvents++;texture.addEventListener('dispose',onDispose);
 return {uploadData:data,
  uniformMatches(current:unknown){return current===texture;},
  report(){return {identified:true,disposeEvents,sourceUnchanged:texture.source===source,dataUnchanged:texture.source.data===image&&texture.image.data===data,versionsUnchanged:texture.version===version&&texture.source.version===sourceVersion,samplerUnchanged:JSON.stringify(sampler())===JSON.stringify(before),metadata:{width:image.width,height:image.height,dataLength:data.length,dataBytes:data.byteLength,format:texture.format,type:texture.type},samplerBefore:before,samplerAfter:sampler()};},
  close(){texture.removeEventListener('dispose',onDispose);}
 };
}
