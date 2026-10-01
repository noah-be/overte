// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DataTexture, MeshPhongMaterial, MeshStandardMaterial } from 'three';
import { applyNativeMaterialAlpha, hasNativeAlphaShader } from '../src/native-alpha-material';
import { applyNativeRenderState } from '../src/native-render-state';
import { warmupNativeAlphaContract } from './graphics-warmup-native-alpha';
async function authored(){
 const map=new DataTexture(new Uint8Array([255,255,255,0]),1,1),mask=new MeshStandardMaterial({map}),blend=new MeshPhongMaterial({map,opacity:.55});
 await applyNativeMaterialAlpha(mask,{useAlpha:true,mode:'OPACITY_MAP_MASK',cutoff:.375});await applyNativeMaterialAlpha(blend,{useAlpha:true,mode:'OPACITY_MAP_BLEND'});
 for(const material of [mask,blend])applyNativeRenderState(material,{cullFaceMode:'CULL_NONE'});
 return {mask,blend,close(){mask.dispose();blend.dispose();map.dispose();}};
}
test('actual native alpha setup has owned MASK hook and original BLEND callbacks before any compiler runs',async()=>{
 const f=await authored();try{assert.equal(hasNativeAlphaShader(f.mask),true);assert.equal(hasNativeAlphaShader(f.blend),false);assert.equal(warmupNativeAlphaContract(f.mask,f.blend),true);}finally{f.close();}
});
test('lost mask ownership or a copied userData/callback pair cannot satisfy the fidelity contract',async()=>{
 const f=await authored(),copy=new MeshStandardMaterial({map:f.mask.map});try{
  Object.assign(copy,{opacity:f.mask.opacity,alphaTest:f.mask.alphaTest,transparent:f.mask.transparent,depthWrite:f.mask.depthWrite,side:f.mask.side,forceSinglePass:f.mask.forceSinglePass,onBeforeCompile:f.mask.onBeforeCompile,customProgramCacheKey:f.mask.customProgramCacheKey});copy.userData={...f.mask.userData};
  assert.equal(warmupNativeAlphaContract(copy,f.blend),false);f.mask.onBeforeCompile=()=>{};assert.equal(warmupNativeAlphaContract(f.mask,f.blend),false);
 }finally{copy.dispose();f.close();}
});
test('BLEND shader or native scalar/render-state mutations remain strict failures rather than an accepted missing hook',async()=>{
 for(const mutate of [
  (f:Awaited<ReturnType<typeof authored>>)=>{f.blend.onBeforeCompile=()=>{};},
  (f:Awaited<ReturnType<typeof authored>>)=>{f.blend.customProgramCacheKey=()=> 'foreign';},
  (f:Awaited<ReturnType<typeof authored>>)=>{f.blend.alphaTest=.5;},
  (f:Awaited<ReturnType<typeof authored>>)=>{f.blend.depthWrite=true;},
  (f:Awaited<ReturnType<typeof authored>>)=>{f.blend.opacity=1;},
  (f:Awaited<ReturnType<typeof authored>>)=>{f.mask.forceSinglePass=false;},
 ]){const f=await authored();try{assert.equal(warmupNativeAlphaContract(f.mask,f.blend),true);mutate(f);assert.equal(warmupNativeAlphaContract(f.mask,f.blend),false);}finally{f.close();}}
});
test('a genuine authored mode replacement cannot silently retain the previous MASK contract',async()=>{
 const f=await authored();try{await applyNativeMaterialAlpha(f.mask,{useAlpha:true,mode:'OPACITY_MAP_BLEND'});applyNativeRenderState(f.mask,{cullFaceMode:'CULL_NONE'});assert.equal(hasNativeAlphaShader(f.mask),false);assert.equal(warmupNativeAlphaContract(f.mask,f.blend),false);}finally{f.close();}
});
