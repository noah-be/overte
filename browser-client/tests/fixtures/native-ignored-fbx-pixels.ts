// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine Three loaders/production preparation worker, authored fixture only.
import * as THREE from 'three';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {BakedFbxPreparePool} from '../../src/model-fbx-pool';
import {EmbeddedFbxImages} from '../../src/embedded-fbx-images';
import {normalizeNativeFbxTransparency} from '../../src/baked-fbx';
import {ModelResources} from '../../src/model-resources';
const assert=(v:unknown,m:string)=>{if(!v)throw Error(m);};
// BEGIN fixed native-ignored GPU read observation.
function createNativeIgnoredGpuDiagnostic(){return {version:2,records:[] as (number|null)[][],refused:false,contextStates:[] as (number|null)[][],contextEvents:[] as number[][]};}
function recordNativeIgnoredGpuRead(diagnostic:ReturnType<typeof createNativeIgnoredGpuDiagnostic>,code:unknown){
 try{
  if(diagnostic.records.length>=22){diagnostic.refused=true;return;}
  const ordinal=diagnostic.records.length,kind=ordinal===0?0:ordinal===1?1:2;
  const valid=typeof code==='number'&&Number.isSafeInteger(code)&&code>=0&&code<=65535;
  if(!valid)diagnostic.refused=true;
  diagnostic.records.push([ordinal,kind,valid?code:null]);
 }catch{try{diagnostic.refused=true;}catch{}}
}
function observeNativeIgnoredGpuContext(diagnostic:ReturnType<typeof createNativeIgnoredGpuDiagnostic>,canvas:HTMLCanvasElement){
 let phase=0,retired=false;
 const refuse=()=>{try{diagnostic.refused=true;}catch{}};
 const event=(kind:number)=>(value:Event)=>{
  if(retired)return;
  try{
   if(value.isTrusted!==true||value.target!==canvas||value.currentTarget!==canvas)return;
   if(diagnostic.contextEvents.length>=8){refuse();return;}
   diagnostic.contextEvents.push([diagnostic.contextEvents.length,kind,phase]);
  }catch{refuse();}
 };
 const lost=event(0),restored=event(1);
 try{canvas.addEventListener('webglcontextlost',lost);canvas.addEventListener('webglcontextrestored',restored);}catch{refuse();}
 return {
  phase(value:number){if(retired)return;if(Number.isSafeInteger(value)&&value>=0&&value<=8)phase=value;else refuse();},
  sample(read:()=>unknown){
   if(retired)return;
   try{
    if(diagnostic.contextStates.length>=2){refuse();return;}
    let value:unknown;try{value=read();}catch{refuse();}
    const valid=typeof value==='boolean';if(!valid)refuse();
    diagnostic.contextStates.push([diagnostic.contextStates.length,phase,valid?(value?1:0):null]);
   }catch{refuse();}
  },
  retire(){if(retired)return;retired=true;try{canvas.removeEventListener('webglcontextlost',lost);}catch{refuse();}try{canvas.removeEventListener('webglcontextrestored',restored);}catch{refuse();}}
 };
}
// END fixed native-ignored GPU read observation.
export async function runNativeIgnoredFbxPixels(){
 const gpuReadDiagnostic=createNativeIgnoredGpuDiagnostic();Object.assign(window,{__nativeIgnoredGpuReadDiagnostic:gpuReadDiagnostic});
 const owner=new AbortController(),pool=new BakedFbxPreparePool({signal:owner.signal,limit:1}),registry=new EmbeddedFbxImages(owner.signal),renderer=new THREE.WebGLRenderer({antialias:false}),roots:THREE.Object3D[]=[],ownedURLs=new Set<string>(),originalURL=URL.createObjectURL;
 const contextObservation=observeNativeIgnoredGpuContext(gpuReadDiagnostic,renderer.domElement);
 URL.createObjectURL=function(blob){const url=originalURL.call(URL,blob);ownedURLs.add(url);return url;};
 const target=new THREE.WebGLRenderTarget(64,64),scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);camera.position.z=2;
 scene.add(new THREE.AmbientLight(0xffffff,3));renderer.setSize(64,64);renderer.setPixelRatio(1);renderer.toneMapping=THREE.NoToneMapping;renderer.outputColorSpace=THREE.LinearSRGBColorSpace;
 document.body.appendChild(renderer.domElement);
 contextObservation.sample(()=>renderer.getContext().isContextLost());
 let baselineRequests=0,candidateRequests=0;const errors={baseline:0,candidate:0};
 function load(bytes:ArrayBuffer,resolver:(url:string)=>string,kind:'baseline'|'candidate'){
  return new Promise<THREE.Group>((resolve,reject)=>{
   let root:THREE.Group|undefined,finished=false;const manager=new THREE.LoadingManager(()=>{finished=true;if(root)resolve(root);},undefined,url=>{
    if(!url.endsWith('/unused-a.dds')){reject(Error('A surviving image dependency failed'));return;}errors[kind]++;
   });
   manager.setURLModifier(url=>{if(kind==='baseline')baselineRequests++;else candidateRequests++;return resolver(url);});
   try{root=new FBXLoader(manager).parse(bytes,`${location.origin}/__native_ignored/`);roots.push(root);if(finished)resolve(root);}catch(error){reject(error);}
  });
 }
 function signature(root:THREE.Object3D){const records:unknown[]=[];root.traverse(o=>{if(o instanceof THREE.Mesh){const g=o.geometry;records.push({matrix:o.matrix.toArray(),attrs:Object.fromEntries(Object.entries(g.attributes).map(([key,raw])=>{const a=raw as THREE.BufferAttribute;return [key,{size:a.itemSize,values:Array.from(a.array)}];})),index:g.index&&Array.from(g.index.array),groups:g.groups,materials:(Array.isArray(o.material)?o.material:[o.material]).map((m:any)=>({opacity:m.opacity,transparent:m.transparent,color:m.color.toArray(),normal:!!m.normalMap,map:!!m.map}))});}});return JSON.stringify(records);}
 const read=(root?:THREE.Object3D)=>{contextObservation.phase(gpuReadDiagnostic.records.length===0?6:gpuReadDiagnostic.records.length===1?7:8);if(root)scene.add(root);renderer.setRenderTarget(target);renderer.setClearColor(0x123456,1);renderer.render(scene,camera);const output=new Uint8Array(64*64*4);renderer.readRenderTargetPixels(target,0,0,64,64,output);if(root)scene.remove(root);const glErrorCode=renderer.getContext().getError();recordNativeIgnoredGpuRead(gpuReadDiagnostic,glErrorCode);assert(glErrorCode===0,'Actual GPU render produced a GL error');return output;};
 try{
  contextObservation.phase(1);const response=await fetch('/__native_ignored/model.fbx');assert(response.ok,'Owned fixture model unavailable');const bytes=await response.arrayBuffer();
  contextObservation.phase(2);const baseline=await load(normalizeNativeFbxTransparency(bytes),url=>{assert(url.startsWith('blob:')&&ownedURLs.has(url)||url===`${location.origin}/__native_ignored/unused-a.dds`,'Baseline dependency escaped its fixed owned source');return url;},'baseline');
  contextObservation.phase(3);const prepared=await pool.prepare(bytes.slice(0)),reader=new AbortController(),lease=registry.register(prepared.buffer,prepared.embeddedImages||[],reader.signal);
  contextObservation.phase(4);const candidate=await load(prepared.buffer,url=>lease.resolveURL(url),'candidate');contextObservation.phase(5);lease.close();assert(errors.baseline===1&&errors.candidate===0,'Unused external DDS request was not removed');assert(baselineRequests===3&&candidateRequests===2,'Surviving actual texture request counts changed');assert(signature(baseline)===signature(candidate),'Rendered geometry/material binding changed');
  contextObservation.sample(()=>renderer.getContext().isContextLost());
  let coloredPixels=0;const background=read(),original=read(baseline);for(let i=0;i<original.length;i+=4)if(original[i]!==background[i]||original[i+1]!==background[i+1]||original[i+2]!==background[i+2])coloredPixels++;assert(coloredPixels>500,'Fixture model did not produce a substantial drawn surface');
  for(let frame=0;frame<20;frame++){const output=read(candidate);assert(output.every((value,index)=>value===original[index]),'Original/pruned actual GPU pixels differ');}
  const cancel=new AbortController(),cancelledJob=pool.prepare(bytes.slice(0),cancel.signal);cancel.abort();let cancelled=false;try{await cancelledJob;}catch(e){cancelled=e instanceof DOMException&&e.name==='AbortError';}assert(cancelled,'Cancelled active worker completed');assert(pool.counters.workers===0&&pool.counters.outstanding===0,'Cancelled worker retained transfer ownership');const replacement=await pool.prepare(bytes.slice(0)),referenceBytes=new Uint8Array(prepared.buffer);assert(new Uint8Array(replacement.buffer).every((value,index)=>value===referenceBytes[index])&&replacement.buffer.byteLength===prepared.buffer.byteLength,'Cancellation changed the fresh replacement worker output');
  const gl=renderer.getContext(),info=gl.getExtension('WEBGL_debug_renderer_info');return {completed:true,pixelsCompared:64*64*20,frames:20,coloredPixels,errors,baselineRequests,candidateRequests,geometryAndMaterialBindingsEqual:true,cancelledAdmission:true,pool:pool.counters,gpu:{version:gl.getParameter(gl.VERSION),renderer:info?gl.getParameter(info.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)}};
 }finally{
  contextObservation.retire();owner.abort();URL.createObjectURL=originalURL;for(const url of ownedURLs)URL.revokeObjectURL(url);
  for(const root of roots){const ledger=new ModelResources();ledger.capture(root);ledger.releaseKeeping();}renderer.setRenderTarget(null);target.dispose();renderer.dispose();renderer.domElement.remove();
  assert(pool.counters.outstanding===0&&pool.counters.workers===0&&pool.counters.inputBytes===0,'Pool cleanup retained resources');assert(registry.statistics.entries===0&&registry.statistics.scopes===0,'Registry cleanup retained resources');
 }
}
Object.assign(window,{runNativeIgnoredFbxPixels});
