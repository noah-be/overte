// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
export async function auditStaticModelMatrices(url:string,enabled:boolean){
 const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:512px;height:384px';document.body.append(host);
 const warnings:string[]=[];const world=new BrowserWorld(host,{staticModelMatrices:enabled,resolveAsset:url=>url,onPose(){},onInteract(){},onStatus:(message,kind)=>{if(kind==='warning'||kind==='error')warnings.push(message);}});
 const w=world as unknown as {camera:THREE.PerspectiveCamera;renderer:THREE.WebGLRenderer;objects:Map<string,THREE.Group>;frame:number;staticMatrices?:{statistics:unknown};meshCollisions:Map<string,{value:{dispose():void}}>};
 const records:unknown[]=[];let disposedStats:unknown;
 world.setPresentationEnabled(false);world.setEnabled(false);world.setInputEnabled(false);cancelAnimationFrame(w.frame);
 // Material publication can prepare an empty root before its Model finishes.
 // Require both real imported primitives and the completed owned Model.
 const ready=async(name?:string)=>{
  const installed=()=>{const root=w.objects.get('model');let meshes=0,match=true;
   root?.traverse(object=>{if(object instanceof THREE.Mesh&&object.geometry.getAttribute('position')?.count===6){meshes++;for(const material of Array.isArray(object.material)?object.material:[object.material])if(name&&material.name!==name)match=false;}});
   return root?.userData.modelLoaded===true&&world.getPerformance().loadedModels===1&&meshes===2&&match;
  };
  const deadline=performance.now()+15000;
  while(w.objects.get('model')?.userData.shadersReady!==true||world.getPerformance().compilingGraphics!==0||!installed()){
   if(w.objects.get('model')?.userData.modelFailed)throw Error(warnings.join('; '));
   if(performance.now()>deadline)throw Error('Real World Model graphics deadline');
   await new Promise(resolve=>setTimeout(resolve,10));
  }
 };
 const assertPose=(root:THREE.Group)=>{
  if(root.position.distanceTo(new THREE.Vector3(.3,.1,0))>1e-12||Math.abs(root.quaternion.y-Math.sin(.15))>1e-12||Math.abs(root.quaternion.w-Math.cos(.15))>1e-12||root.quaternion.x!==0||root.quaternion.z!==0)throw Error('Native pose upsert did not reach the actual root');
 };
 const assertDimensions=(root:THREE.Group)=>{
  root.updateWorldMatrix(true,true);const inverse=root.matrixWorld.clone().invert(),bounds=new THREE.Box3(),point=new THREE.Vector3();
  root.traverse(object=>{if(object instanceof THREE.Mesh){const positions=object.geometry.getAttribute('position'),relative=inverse.clone().multiply(object.matrixWorld);for(let index=0;index<positions.count;index++)bounds.expandByPoint(point.fromBufferAttribute(positions,index).applyMatrix4(relative));}});
  if(bounds.getSize(new THREE.Vector3()).distanceTo(new THREE.Vector3(4,1.8,.1))>1e-6)throw Error('Dimensions upsert did not normalize the actual imported vertices');
 };
 try{
  w.renderer.setPixelRatio(1);w.renderer.setSize(512,384);const gl=w.renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 required');
  w.camera.position.set(0,0,4);w.camera.quaternion.identity();w.camera.aspect=512/384;w.camera.updateProjectionMatrix();world.scene.background=new THREE.Color(0);
  world.upsertEntities([{id:'model',type:'Model',modelURL:new URL(url,location.href).href,dimensions:{x:5,y:2,z:.1},position:{x:0,y:0,z:0},collisionless:true},{id:'material',type:'Material',parentID:'model',parentMaterialName:'all',materialData:JSON.stringify({materials:{model:'hifi_pbr',unlit:true,albedo:[1,1,1],cullFaceMode:'CULL_NONE'}})}]);await ready();
  const capture=async(label:string)=>{
   for(let frame=0;frame<20;frame++)w.renderer.render(world.scene,w.camera);
   const pixels=new Uint8Array(512*384*4);gl.readPixels(0,0,512,384,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual comparison GL error');
   const pixelHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))).map(value=>value.toString(16).padStart(2,'0')).join('');
   const root=w.objects.get('model')!,matrices:number[][]=[],autoFlags:boolean[][]=[],versions:number[]=[];root.traverse(o=>{matrices.push(o.matrixWorld.elements.slice());autoFlags.push([o.matrixAutoUpdate,o.matrixWorldAutoUpdate]);if(o instanceof THREE.Mesh)for(const mat of Array.isArray(o.material)?o.material:[o.material])versions.push(mat.version);});
   const point=new THREE.Vector3(-1.5,0,.05).project(w.camera),offset=(Math.floor((point.y*.5+.5)*384)*512+Math.floor((point.x*.5+.5)*512))*4;
   const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(point.x,point.y),w.camera);const hits=ray.intersectObject(root,true).map(hit=>({point:hit.point.toArray(),distance:hit.distance,faceIndex:hit.faceIndex}));
   records.push({label,pixelHash,center:Array.from(pixels.slice(offset,offset+4)),matrices,autoFlags,versions,drawCalls:w.renderer.info.render.calls,programs:w.renderer.info.programs?.length,hits});
  };
  await capture('idle');const first=w.objects.get('model')!;
  world.upsertEntities([{id:'model',type:'Model',position:{x:.3,y:.1,z:0},rotation:{x:0,y:Math.sin(.15),z:0,w:Math.cos(.15)}}]);if(w.objects.get('model')!==first)throw Error('Pose upsert unexpectedly replaced the Model root');assertPose(first);await capture('native-pose-upsert');
  world.scene.position.x=-.2;world.scene.scale.set(-1,1,1);await capture('negative-parent-transform');world.scene.scale.set(1,1,1);world.scene.position.x=0;
  let mesh:THREE.Mesh|undefined;first.traverse(o=>{if(!mesh&&o instanceof THREE.Mesh)mesh=o;});if(!mesh)throw Error('Actual imported mesh required');mesh.position.y+=.15;await capture('direct-local-change');
  world.upsertEntities([{id:'material',type:'Material',parentID:'model',parentMaterialName:'all',materialData:JSON.stringify({materials:{name:'matrix-edited',model:'hifi_pbr',unlit:true,albedo:[.25,1,.5],cullFaceMode:'CULL_NONE'}})}]);await ready('matrix-edited');await capture('native-material-edit');
  world.upsertEntities([{id:'model',type:'Model',dimensions:{x:4,y:1.8,z:.1}}]);await ready();if(w.objects.get('model')===first)throw Error('Dimensions must rebuild owned root');assertPose(w.objects.get('model')!);assertDimensions(w.objects.get('model')!);if(first.updateMatrixWorld!==THREE.Object3D.prototype.updateMatrixWorld)throw Error('Old root wrapper remains after replacement');await capture('rebuild');
  world.removeEntities(['material','model']);if(world.getPerformance().staticModelMatrices.enabled&&(world.getPerformance().staticModelMatrices as {activeRoots:number}).activeRoots!==0)throw Error('Removed root retained');
  return {records,warnings,statistics:world.getPerformance().staticModelMatrices,webgl2:true};
 }finally{try{world.dispose();disposedStats=w.staticMatrices?.statistics;if(enabled&&(disposedStats as {retainedNodes:number}).retainedNodes!==0)throw Error('Whole World retained static graph');}finally{try{w.renderer.forceContextLoss();}finally{host.remove();}}}
}
