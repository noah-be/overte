// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {cloneParsedFbxTemplate,disposeParsedFbxGraph} from '../src/parsed-fbx-template';
import {replacementMaterialFbx} from './fixtures/replacement-material-fbx';
import {disposeObject as original} from './fixtures/skeleton-disposal-original';
import {disposeObject as candidate} from './fixtures/skeleton-disposal-candidate';
function skeletons(root:THREE.Object3D){const result=new Set<THREE.Skeleton>();root.traverse(node=>{if(node instanceof THREE.SkinnedMesh)result.add(node.skeleton);});return[...result];}
/** Real renderer/FBXLoader and exact World removal body; only its exact private
 * frozen cleanup binding changes. World construction/global DFG is excluded. */
export async function auditOwnedSkeletonGpu(enabled:boolean,survivor:boolean){
 const canvas=document.createElement('canvas');document.body.append(canvas);let renderer:THREE.WebGLRenderer|undefined;try{renderer=new THREE.WebGLRenderer({canvas,antialias:false});renderer.setSize(256,192);renderer.setPixelRatio(1);const scene=new THREE.Scene();scene.background=new THREE.Color(0);const camera=new THREE.PerspectiveCamera(60,256/192,.01,100);camera.position.set(0,0,3);scene.add(new THREE.AmbientLight(0xffffff,1));
 const raw=new FBXLoader().parse(replacementMaterialFbx({skin:true,vertexColors:true,withoutOriginalTextures:true}),''),retained=survivor?cloneParsedFbxTemplate(raw):undefined;raw.removeFromParent();raw.position.x=survivor?-.9:0;scene.add(raw);if(retained){retained.position.x=.9;scene.add(retained);}
 const owned=skeletons(raw),other=retained?skeletons(retained):[],events={owned:0,retained:0},buffers={before:renderer.info.memory.textures,allocated:0,after:0,final:0};let report;
 const world:any=Object.create(BrowserWorld.prototype);Object.assign(world,{scene,entities:new Map([['model',{id:'model',type:'Model'}]]),objects:new Map([['model',raw]]),signatures:new Map(),meshCollisions:new Map(),modelGeometry:new WeakMap(),modelReaders:new WeakMap(),localLights:new Set(),modelBatches:new Map(),colliders:[],pendingModelColliders:[]});
 const body=BrowserWorld.prototype.removeEntities.toString(),remove=new Function('THREE','disposeObject',`return ({${body}}).removeEntities;`)(THREE,enabled?candidate:original)as BrowserWorld['removeEntities'];
 try{
  if(!owned.length)throw Error('Real FBX skin required');renderer.render(scene,camera);buffers.allocated=renderer.info.memory.textures;
  for(const skeleton of owned){if(!skeleton.boneTexture)throw Error('Renderer must allocate owned bone texture');skeleton.boneTexture.addEventListener('dispose',()=>events.owned++);}
  for(const skeleton of other){if(!skeleton.boneTexture)throw Error('Renderer must allocate retained bone texture');skeleton.boneTexture.addEventListener('dispose',()=>events.retained++);}
  const gl=renderer.getContext(),bytes=new Uint8Array(256*192*4);gl.readPixels(0,0,256,192,gl.RGBA,gl.UNSIGNED_BYTE,bytes);let visible=0;for(let at=0;at<bytes.length;at+=4)if(bytes[at]||bytes[at+1]||bytes[at+2])visible++;
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');remove.call(world,['model']);buffers.after=renderer.info.memory.textures;
  renderer.render(scene,camera);const kept=new Uint8Array(bytes.length);gl.readPixels(0,0,256,192,gl.RGBA,gl.UNSIGNED_BYTE,kept);let retainedVisible=0;for(let at=0;at<kept.length;at+=4)if(kept[at]||kept[at+1]||kept[at+2])retainedVisible++;
  report={webgl2:gl instanceof WebGL2RenderingContext,enabled,survivor,visible,retainedVisible,hash,buffers,events:{...events},ownedSkeletons:owned.length,retainedSkeletons:other.length,retainedAlive:other.every(skeleton=>skeleton.boneTexture!==null),rootRetired:raw.parent===null&&world.objects.size===0&&world.entities.size===0,cleanup:false};
 }finally{
  // Recover only recorded PRIVATE allocations after the original negative
  // measurements. Do not dispose a global singleton or report this as its fix.
  for(const skeleton of [...owned,...other])skeleton.dispose();disposeParsedFbxGraph(raw);if(retained)disposeParsedFbxGraph(retained);scene.clear();buffers.final=renderer.info.memory.textures;
 }
 report.cleanup=buffers.final===0;return report;
 }finally{try{renderer?.dispose();}finally{try{renderer?.forceContextLoss();}finally{canvas.remove();}}}
}
