// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {BoxGeometry,Mesh,MeshBasicMaterial,OrthographicCamera,Scene,WebGLRenderer} from 'three';
import {GpuTimeObserver} from '../src/gpu-time-observer';

export async function auditGpuTimeObserver(){
 const renderer=new WebGLRenderer({antialias:false,preserveDrawingBuffer:true});renderer.setSize(32,32);
 const geometry=new BoxGeometry(1,1,1),material=new MeshBasicMaterial({color:0xff0000}),scene=new Scene(),camera=new OrthographicCamera(-1,1,1,-1,.1,10);camera.position.z=2;scene.add(new Mesh(geometry,material));
 const gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 is required');
 const observer=new GpuTimeObserver(gl,{maxPending:4,timeoutMs:5000});
 try{
  const before={width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,pixelRatio:renderer.getPixelRatio()};
  const began=observer.begin();try{renderer.render(scene,camera);}finally{if(began)observer.end();}
  const deadline=performance.now()+6000;
  while(observer.supported&&observer.getSnapshot().pending&&performance.now()<deadline){await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));observer.poll();}
  const measured=observer.getSnapshot();observer.dispose();
  const pixel=new Uint8Array(4);gl.readPixels(16,16,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
  return {webgl2:true,began,before,after:{width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,pixelRatio:renderer.getPixelRatio()},pixel:Array.from(pixel),measured,disposed:observer.getSnapshot()};
 }finally{observer.dispose();geometry.dispose();material.dispose();renderer.dispose();renderer.forceContextLoss();}
}
