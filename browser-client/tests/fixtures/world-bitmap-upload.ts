// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual WebGL parity scaffold; not executed by CPU contracts.
import * as THREE from 'three';
import {WorldBitmapUpload,BitmapUploadUnsupportedVariantError,type SessionUploadTexture} from '../../src/world-bitmap-upload';
export async function runBitmapUploadProof(){
 const signal=new AbortController(),owner=new WorldBitmapUpload({signal:signal.signal,maximumEntries:2}),renderer=new THREE.WebGLRenderer({alpha:true,antialias:false}),target=new THREE.WebGLRenderTarget(16,16),geometry=new THREE.PlaneGeometry(2,2),material=new THREE.MeshBasicMaterial({transparent:true,toneMapped:false}),scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);
 renderer.outputColorSpace=THREE.SRGBColorSpace;target.texture.colorSpace=THREE.SRGBColorSpace;camera.position.z=1;scene.add(new THREE.Mesh(geometry,material));
 const originals:THREE.Texture[]=[],owned:SessionUploadTexture[]=[];const checks:Array<{flipY:boolean;premultiplyAlpha:boolean;colorSpace:string;prepared:boolean;exact:boolean;maximumChannelError:number}>=[];
 let completed=false;
 try{
  const canvas=document.createElement('canvas');canvas.width=2;canvas.height=2;const ctx=canvas.getContext('2d')!;ctx.putImageData(new ImageData(new Uint8ClampedArray([255,20,5,255,5,240,20,128,20,5,255,64,210,120,30,0]),2,2),0,0);
  const image=new Image();image.src=canvas.toDataURL('image/png');await image.decode();
  const read=(map:THREE.Texture)=>{material.map=map;material.needsUpdate=true;renderer.setRenderTarget(target);renderer.setClearColor(0x26394d,1);renderer.clear();renderer.render(scene,camera);const bytes=new Uint8Array(16*16*4);renderer.readRenderTargetPixels(target,0,0,16,16,bytes);return bytes;};
  for(const flipY of [false,true])for(const premultiplyAlpha of [false,true])for(const colorSpace of [THREE.SRGBColorSpace,THREE.NoColorSpace,THREE.LinearSRGBColorSpace]){
   const original=new THREE.Texture(image);original.flipY=flipY;original.premultiplyAlpha=premultiplyAlpha;original.colorSpace=colorSpace;original.magFilter=THREE.NearestFilter;original.minFilter=THREE.NearestFilter;original.generateMipmaps=false;original.needsUpdate=true;originals.push(original);
   const baseline=read(original);let bitmap:SessionUploadTexture;
   try{bitmap=await owner.prepare(original,signal.signal);}catch(error){
    if(!(error instanceof BitmapUploadUnsupportedVariantError)||!premultiplyAlpha)throw error;
    const actual=read(original);let maximumChannelError=0;for(let i=0;i<actual.length;i++)maximumChannelError=Math.max(maximumChannelError,Math.abs(actual[i]-baseline[i]));checks.push({flipY,premultiplyAlpha,colorSpace,prepared:false,exact:maximumChannelError===0,maximumChannelError});continue;
   }
   owned.push(bitmap);const clone=bitmap.clone();owned.push(clone);const actual=read(clone);let maximumChannelError=0;for(let i=0;i<actual.length;i++)maximumChannelError=Math.max(maximumChannelError,Math.abs(actual[i]-baseline[i]));checks.push({flipY,premultiplyAlpha,colorSpace,prepared:true,exact:maximumChannelError===0,maximumChannelError});
   if(!owner.isCurrent(bitmap)||!owner.isCurrent(clone))throw Error('Actual sampler publication lost its bitmap lease.');
   bitmap.dispose();owned.splice(owned.indexOf(bitmap),1);clone.dispose();owned.splice(owned.indexOf(clone),1);
  }
  completed=true;
 }finally{
  signal.abort();for(const texture of owned)texture.dispose();for(const texture of originals)texture.dispose();material.dispose();geometry.dispose();target.dispose();renderer.dispose();renderer.domElement.remove();
 }
 return{completed,checks,ownership:owner.stats(),textureCountAfterClose:renderer.info.memory.textures,geometryCountAfterClose:renderer.info.memory.geometries};
}
