// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owned authored FBX pixels through actual BrowserWorld, worker and image loader.
import * as THREE from 'three';
import {BrowserWorld} from '../../src/world';
import {ModelResources} from '../../src/model-resources';
interface TestWorld extends Pick<BrowserWorld,'getPerformance'|'dispose'|'setPresentationEnabled'> {
 loadModel(source:string,visited?:Set<string>,base?:string,signal?:AbortSignal,geometry?:(root:THREE.Object3D)=>void):Promise<THREE.Object3D>;
 renderer:THREE.WebGLRenderer;
}
const assert=(value:unknown,message:string)=>{if(!value)throw Error(message);};
function map(root:THREE.Object3D){let result:THREE.Texture|undefined;root.traverse(object=>{if(object instanceof THREE.Mesh){const material=Array.isArray(object.material)?object.material[0]:object.material;result=(material as THREE.MeshPhongMaterial).map??undefined;}});assert(result,'The actual FBX model has no albedo map');return result!;}
// BEGIN bounded embedded diagnostic (authored fixture only).
function createEmbeddedDiagnostic(){return {version:1,phase:'model-await',decodedRGBA:[] as number[],frames:[] as number[][]};}
function recordEmbeddedFrame(diagnostic:ReturnType<typeof createEmbeddedDiagnostic>,frame:number,pixel:number[],uploads:number,ma:THREE.Texture,mb:THREE.Texture,calls:number){
 if(diagnostic.frames.length<20)diagnostic.frames.push([frame,...pixel,uploads,ma.version,mb.version,ma.source.version,mb.source.version,calls]);
}
// END bounded embedded diagnostic.
export async function runEmbeddedWorldFixture(){
 const diagnostic=createEmbeddedDiagnostic();Object.assign(window,{__embeddedWorldDiagnostic:diagnostic});
 const container=document.querySelector('#world') as HTMLElement,warnings:string[]=[],world=new BrowserWorld(container,{resolveAsset:source=>{
  const address=new URL(source,location.href);assert(address.origin===location.origin&&address.pathname==='/__embedded/model.fbx','Fixture refused an unapproved asset');return address.href;
 },onPose:()=>{},onInteract:()=>{throw Error('Fixture cannot edit a world');},onStatus:message=>warnings.push(message)}) as unknown as TestWorld;
 const models:THREE.Object3D[]=[];world.setPresentationEnabled(false);
 try{
  const first=new AbortController(),second=new AbortController();
  // Real prepared-cache readers share one worker output; two model parses own
  // distinct Texture/sampler instances while one HTML image/source is decoded.
  const [a,b]=await Promise.all([world.loadModel(new URL('/__embedded/model.fbx',location.href).href,undefined,undefined,first.signal),world.loadModel(new URL('/__embedded/model.fbx',location.href).href,undefined,undefined,second.signal)]);models.push(a,b);
  const ma=map(a),mb=map(b);assert(ma!==mb,'Samplers must remain independent');assert(ma.source===mb.source&&ma.image===mb.image,'Repeated parser consumers must share their decoded Source');ma.repeat.set(2,3);assert(mb.repeat.x===1&&mb.repeat.y===1,'One material changed its neighboring sampler');ma.repeat.set(1,1);
  const image=ma.image as HTMLImageElement;assert(image.complete&&image.naturalWidth===1&&image.naturalHeight===1,'Actual HTML image decode did not finish');
  const pixels=document.createElement('canvas');pixels.width=pixels.height=1;const context=pixels.getContext('2d')!;context.drawImage(image,0,0);const imagePixel=Array.from(context.getImageData(0,0,1,1).data);assert(imagePixel.join(',')==='255,0,0,255','Embedded exact PNG bytes changed during preparation');diagnostic.decodedRGBA=imagePixel.slice();diagnostic.phase='gpu-loop';
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,0.1,10);camera.position.z=2;
  const materialA=new THREE.MeshBasicMaterial({map:ma}),materialB=new THREE.MeshBasicMaterial({map:mb}),geometry=new THREE.PlaneGeometry(2,2),target=new THREE.WebGLRenderTarget(16,16),mesh=new THREE.Mesh(geometry,materialA);scene.add(mesh);
  const renderer=world.renderer,oldTone=renderer.toneMapping;renderer.toneMapping=THREE.NoToneMapping;renderer.setRenderTarget(target);renderer.setClearColor(0,0);
  const output=new Uint8Array(16*16*4),startTextures=renderer.info.memory.textures;
  let gpuPixel:number[]=[],uploads=0;const gl=renderer.getContext(),original=gl.texImage2D,originalSub=gl.texSubImage2D;
  gl.texImage2D=function(this:WebGL2RenderingContext,...args:unknown[]){if(args.some(arg=>arg===image))uploads++;return Reflect.apply(original,this,args);} as typeof original;
  gl.texSubImage2D=function(this:WebGL2RenderingContext,...args:unknown[]){if(args.some(arg=>arg===image))uploads++;return Reflect.apply(originalSub,this,args);} as typeof originalSub;
  try{
   for(let frame=0;frame<20;frame++){mesh.material=frame%2?materialA:materialB;renderer.render(scene,camera);renderer.readRenderTargetPixels(target,0,0,16,16,output);gpuPixel=Array.from(output.slice((8*16+8)*4,(8*16+8)*4+4));recordEmbeddedFrame(diagnostic,frame,gpuPixel,uploads,ma,mb,renderer.info.render.calls);assert(gpuPixel.join(',')==='255,0,0,255','Actual GPU embedded pixels changed');assert(gl.getError()===gl.NO_ERROR,'Embedded GPU upload raised a GL error');}
   diagnostic.phase='gpu-upload-check';assert(uploads===1,'Independent samplers reuploaded their shared HTML Source');
  }finally{gl.texImage2D=original;gl.texSubImage2D=originalSub;renderer.setRenderTarget(null);renderer.toneMapping=oldTone;target.dispose();geometry.dispose();materialA.dispose();materialB.dispose();}
  diagnostic.phase='post-gpu-resources';const before=world.getPerformance();assert(before.imageLoading.sourceKinds.blob.uniqueImages===1,'Actual World path created duplicate blob images');assert(before.embeddedImages.createdURLs===1&&before.embeddedImages.reusedURLs===1&&before.embeddedImages.scopes===0,'Texture leases were not closed after real decode');
  // Cancel a real model immediately after its geometry is published. The
  // neighboring reader keeps its actual prepared/source ownership and pixels.
  diagnostic.phase='model-cancellation';const cancelled=new AbortController(),neighbor=new AbortController();
  const cancelledResult=world.loadModel(new URL('/__embedded/model.fbx',location.href).href,undefined,undefined,cancelled.signal,()=>cancelled.abort()).then(()=>false,error=>error?.name==='AbortError');
  const survivor=await world.loadModel(new URL('/__embedded/model.fbx',location.href).href,undefined,undefined,neighbor.signal);models.push(survivor);assert(await cancelledResult,'Cancelled actual World model completed successfully');assert(map(survivor).source===mb.source,'Cancelling one model revoked its neighboring decoded image');
  assert(world.getPerformance().embeddedImages.scopes===0,'Model cancellation orphaned a blob lease');
  assert(warnings.length===0,'Expected model cancellation was reported as a missing asset');
  const rendererName=gl.getExtension('WEBGL_debug_renderer_info');
  const result={completed:true,imagePixel,gpuPixel,uploads,frames:20,independentSamplers:true,realModelCancellation:true,prepared:before.preparedFbxCache,imageLoading:before.imageLoading,embeddedImages:before.embeddedImages,textureObjectsAdded:renderer.info.memory.textures-startTextures,gpu:{version:gl.getParameter(gl.VERSION),renderer:rendererName?gl.getParameter(rendererName.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)},warnings};
  diagnostic.phase='complete';return result;
 }finally{
  for(const root of models){const resources=new ModelResources();resources.capture(root);resources.releaseKeeping();}
  world.dispose();const after=world.getPerformance();assert(after.embeddedImages.bytes===0&&after.embeddedImages.entries===0&&after.embeddedImages.scopes===0,'World revocation retained owned blob resources');assert(after.imageLoading.active===0&&after.imageLoading.queued===0,'World revocation retained an image reader');
 }
}
Object.assign(window,{runEmbeddedWorldFixture});
