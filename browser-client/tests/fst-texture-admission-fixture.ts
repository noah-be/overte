// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {WorldImageCache} from '../src/world-image-cache';
import {parseTexturedModel} from '../src/model-textures';
import {ModelResources} from '../src/model-resources';
import {applyNativeMaterialAlpha} from '../src/native-alpha-material';
import {applyNativeRenderState,cloneNativeMaterialForGeometry} from '../src/native-render-state';
import {prepareFstTextureAdmission,type ResolvedFstReplacement} from '../src/fst-texture-admission';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';

/** Actual renderer/HTML image/network acceptance for the proposed admission
 * helper. This does not activate or claim BrowserWorld FST integration. */
export async function auditFstTextureAdmission(mode:'partial'|'all'){
 const owner=new AbortController(),resources=new ModelResources(),caches:WorldImageCache[]=[],dependencyErrors:string[]=[];
 const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setSize(256,128,false);renderer.setPixelRatio(1);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.NoToneMapping;document.body.append(renderer.domElement);
 const camera=new THREE.OrthographicCamera(-1.1,1.1,.85,-.85,.1,10);camera.position.z=3;camera.lookAt(0,0,0);
 const pixels=(model:THREE.Object3D)=>{
  const scene=new THREE.Scene();scene.background=new THREE.Color(0);scene.add(model);scene.add(new THREE.AmbientLight(0xffffff,1));renderer.render(scene,camera);
  const data=new Uint8Array(256*128*4);renderer.getContext().readPixels(0,0,256,128,renderer.getContext().RGBA,renderer.getContext().UNSIGNED_BYTE,data);const calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;scene.remove(model);return {data,calls,triangles};
 };
 try{
  const input=fstTextureAdmissionFbx(),original=input.slice(0),stats:{removedTextures:number;removedVideos:number;retainedTextures:number}|undefined={removedTextures:0,removedVideos:0,retainedTextures:3};
  let admission=stats;
  async function load(which:'baseline'|'candidate'){
   const cache=new WorldImageCache({signal:owner.signal});caches.push(cache);const manager=new THREE.LoadingManager();manager.onError=url=>dependencyErrors.push(new URL(url,location.href).pathname);
   const base=new URL(`/fst-admission-assets/${mode}/${which}/`,location.href).href;manager.setURLModifier(url=>new URL(url,base).href);manager.addHandler(/\.png$/i,cache.loader(manager));
   const replacement=await cache.loader(manager).loadAsync(base+'replacement.png');replacement.colorSpace=THREE.SRGBColorSpace;
   const template=new THREE.MeshBasicMaterial({name:'Replacement',map:replacement,toneMapped:false,side:THREE.DoubleSide});resources.captureMaterial(template);
   await applyNativeMaterialAlpha(template,{useAlpha:false},owner.signal);applyNativeRenderState(template,{cullFaceMode:'CULL_NONE'});
   const recipe:ResolvedFstReplacement={selector:mode==='all'?'all':'mat::A',definition:{model:'hifi_pbr',name:'Replacement',unlit:true,albedoMap:'replacement.png'},template};
   const result=which==='candidate'?prepareFstTextureAdmission(input,[recipe],[],owner.signal,()=>{}):undefined;
   if(which==='candidate'){if(!result)throw Error('Authored complete FST fixture was not admitted');admission=result;}
   const model=await parseTexturedModel(manager,owner.signal,()=>new FBXLoader(manager).parse(result?.buffer??input,base),model=>{resources.capture(model);resources.releaseKeeping();});resources.capture(model);
   model.traverse(object=>{if(!(object instanceof THREE.Mesh))return;const old=Array.isArray(object.material)?object.material:[object.material];const next=old.map(material=>{if(recipe.selector!=='all'&&recipe.selector!==`mat::${material.name}`)return material;const clone=cloneNativeMaterialForGeometry(template,object.geometry);resources.captureMaterial(clone);return clone;});object.material=Array.isArray(object.material)?next:next[0];});
   return model;
  }
  const baseline=await load('baseline'),candidate=await load('candidate');
  const scene=new THREE.Scene();scene.add(new THREE.AmbientLight(0xffffff,1));await renderer.compileAsync(baseline,camera,scene);await renderer.compileAsync(candidate,camera,scene);
  const before=pixels(baseline),after=pixels(candidate);let differences=0;for(let i=0;i<before.data.length;i++)if(before.data[i]!==after.data[i])differences++;
  const sample=(x:number)=>[...after.data.subarray((64*256+x)*4,(64*256+x)*4+4)];
  const background=sample(0),left=sample(70),right=sample(186);
  let geometryEqual=true;const beforeMeshes:THREE.Mesh[]=[],afterMeshes:THREE.Mesh[]=[];baseline.traverse(o=>{if(o instanceof THREE.Mesh)beforeMeshes.push(o);});candidate.traverse(o=>{if(o instanceof THREE.Mesh)afterMeshes.push(o);});
  const signature=(mesh:THREE.Mesh)=>JSON.stringify({attributes:Object.fromEntries(Object.entries(mesh.geometry.attributes).map(([k,v])=>[k,[v.itemSize,...Array.from(v.array)]])),index:mesh.geometry.index?Array.from(mesh.geometry.index.array):null,groups:mesh.geometry.groups});
  geometryEqual=beforeMeshes.length===afterMeshes.length&&beforeMeshes.every((mesh,i)=>signature(mesh)===signature(afterMeshes[i]));
  resources.capture(baseline);resources.capture(candidate);resources.releaseKeeping();
  return {webGL2:renderer.getContext() instanceof WebGL2RenderingContext,mode,admission:{removedTextures:admission.removedTextures,removedVideos:admission.removedVideos,retainedTextures:admission.retainedTextures},geometryEqual,inputUnchanged:new Uint8Array(input).every((value,i)=>value===new Uint8Array(original)[i]),differentRGBAComponents:differences,left,right,background,before:{calls:before.calls,triangles:before.triangles},after:{calls:after.calls,triangles:after.triangles},dependencyErrors,sourceStats:caches.map(cache=>cache.stats())};
 }finally{owner.abort();resources.releaseKeeping();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();}
}
