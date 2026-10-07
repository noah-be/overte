// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine BrowserWorld Image entity path on fixed, isolated, cookie-owned inputs.
import * as THREE from 'three';
import {BrowserWorld} from '../../src/world';
import {NativeCompressedColorCache,nativeCompressedColorAlpha} from '../../src/native-compressed-color';
import {ModelResources} from '../../src/model-resources';
interface ImageWorld extends Pick<BrowserWorld,'setPresentationEnabled'|'getPerformance'|'dispose'>{
 renderer:THREE.WebGLRenderer;objects:Map<string,THREE.Group>;abort:AbortController;
 populateEntity(entity:{id:string;type:string;imageURL:string;dimensions:{x:number;y:number;z:number}},root:THREE.Group):Promise<void>;
}
const assert=(value:unknown,message:string)=>{if(!value)throw Error(message);};
const address=(name:string)=>`https://image-fixture.invalid/${name}`;
export async function runImageCompressedWorldFixture(){
 const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),30000),caches:NativeCompressedColorCache[]=[],warnings:string[]=[],roots:THREE.Group[]=[],cases:unknown[]=[];
 let expectedCompressedUploads=0;let approval='controlled-image-fixture-revision-1';
 const resolve=(url:string)=>{const parsed=new URL(url);assert(parsed.origin==='https://image-fixture.invalid'&&!parsed.username&&!parsed.password&&!parsed.hash,'The fixture refused an unapproved asset');return `${location.origin}/api/assets/image-fixture?url=${encodeURIComponent(url)}`;};
 const world=new BrowserWorld(document.querySelector('#world') as HTMLElement,{resolveAsset:resolve,onPose:()=>{},onInteract:()=>{throw Error('The pixel fixture cannot edit domains');},onStatus:message=>warnings.push(message),compressedColors:(caps,signal)=>{
  const cache=caches[0]??new NativeCompressedColorCache({origin:location.origin,sessionId:'image-fixture',authority:()=>signal.aborted?null:approval,resolveAsset:resolve,capabilities:caps});
  if(!caches.length){caches.push(cache);signal.addEventListener('abort',()=>cache.dispose(),{once:true});}return cache;
 }}) as unknown as ImageWorld;
 controller.signal.addEventListener('abort',()=>world.abort.abort(),{once:true});world.setPresentationEnabled(false);
 const renderer=world.renderer,gl=renderer.getContext(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);camera.position.z=2;
 const targets:THREE.WebGLRenderTarget[]=[],owned=new ModelResources(),uploads={compressed:0,compressedBytes:0};
 const original=gl.compressedTexSubImage2D;
 gl.compressedTexSubImage2D=function(this:WebGL2RenderingContext,...args:Parameters<WebGL2RenderingContext['compressedTexSubImage2D']>){uploads.compressed++;const bytes=args[7];if(ArrayBuffer.isView(bytes))uploads.compressedBytes+=bytes.byteLength;return Reflect.apply(original,this,args);} as typeof original;
 const create=async(name:string)=>{
  assert(!controller.signal.aborted,'Image proof exceeded its unchanged30second deadline');
  const id=`image-proof-${roots.length}`,root=new THREE.Group();roots.push(root);world.objects.set(id,root);
  await world.populateEntity({id,type:'Image',imageURL:address(name+'.texmeta.json'),dimensions:{x:2,y:2,z:.01}},root);
  const mesh=root.children[0]?.children[0];assert(mesh instanceof THREE.Mesh,'Actual Image renderer did not create a plane');
  const material=(mesh as THREE.Mesh).material;assert(material instanceof THREE.MeshBasicMaterial,'Actual Image uses its existing native-style simple material');
  owned.capture(root);return {root,material:material as THREE.MeshBasicMaterial};
 };
 const paint=(root:THREE.Group,size:number)=>{
  assert(!controller.signal.aborted,'Image proof exceeded its unchanged30second deadline');const scene=new THREE.Scene();scene.add(root.clone(true));
  const target=new THREE.WebGLRenderTarget(size,size,{depthBuffer:true});target.texture.colorSpace=THREE.NoColorSpace;targets.push(target);
  renderer.setRenderTarget(target);renderer.setClearColor(0,0);renderer.toneMapping=THREE.NoToneMapping;renderer.render(scene,camera);
  const data=new Uint8Array(size*size*4);renderer.readRenderTargetPixels(target,0,0,size,size,data);assert(gl.getError()===gl.NO_ERROR,'Actual Image texture sampling raised a WebGL error');return data;
 };
 const compare=(a:Uint8Array,b:Uint8Array)=>{let error=0,channels=0,mask=0;for(let i=0;i<a.length;i+=4){const x=a[i+3]>=128,y=b[i+3]>=128;if(x!==y)mask++;if(x&&y)for(let c=0;c<3;c++){error+=Math.abs(a[i+c]-b[i+c]);channels++;}}return {rgbMAE:channels?error/channels:0,maskDifferenceFraction:mask/(a.length/4)};};
 try{
  assert(gl.getExtension('WEBGL_compressed_texture_s3tc')&&gl.getExtension('WEBGL_compressed_texture_s3tc_srgb'),'Actual GPU lacks the audited native color codecs');
  const bootstrap=await fetch('/__image-fixture/bootstrap',{credentials:'same-origin',signal:controller.signal});assert(bootstrap.ok,'Controlled Image fixture cookie initialization failed');
  for(const [name,size,classification]of [['opaque',768,'opaque'],['mask',512,'mask']] as const){
   const png=await create(name+'-original'),compressed=await create(name),repeated=await create(name);
   assert(!(png.material.map instanceof THREE.CompressedTexture),'Unsupported native metadata must keep the original image fallback');
   assert(compressed.material.map instanceof THREE.CompressedTexture,'The actual Image entity bypassed supported native KTX');
   assert(nativeCompressedColorAlpha(compressed.material.map!)===classification,'The approved native usage classification changed');expectedCompressedUploads+=(compressed.material.map as THREE.CompressedTexture).mipmaps.length;
   assert(compressed.material.map!==repeated.material.map&&compressed.material.map!.source===repeated.material.map!.source,'Image entity samplers must be independent while their approved byte Source is shared');
   for(const material of [png.material,compressed.material,repeated.material]){assert(material.transparent&&material.alphaTest===0&&!material.depthWrite&&material.side===THREE.DoubleSide&&material.forceSinglePass,'The role change altered existing Image blend, alpha or cull behavior');assert(material.map!.colorSpace===THREE.SRGBColorSpace,'Image color space changed');}
   const baseline=paint(png.root,size),matched=compare(baseline,paint(compressed.root,size));assert(matched.rgbMAE<10&&matched.maskDifferenceFraction<.01,'Actual Image KTX differs from original sRGB colors/alpha/orientation');
   for(let i=0;i<20;i++){const current=compare(baseline,paint(i%2?compressed.root:repeated.root,size));assert(current.rgbMAE<10&&current.maskDifferenceFraction<.01,'Shared Image texture pixels changed acrossframes');}
   const minified=compare(paint(png.root,64),paint(compressed.root,64));assert(minified.rgbMAE<15&&minified.maskDifferenceFraction<.1,'Actual Image native mip chain differs beyond its bounded lossy tolerance');
   cases.push({name,size,classification,matched,minified,frames:20,independentSamplers:true,material:{transparent:compressed.material.transparent,alphaTest:compressed.material.alphaTest,depthWrite:compressed.material.depthWrite,forceSinglePass:compressed.material.forceSinglePass},matrix:compressed.material.map!.matrix.toArray()});
  }
  assert(uploads.compressed===expectedCompressedUploads,'Independent Image samplers repeated their shared compressed GPU uploads');
  // Real fetch cancellation while a fixed HTTP KTX response is delayed. The
  // authority owner revokes its World before bytes can become a late image.
  const pending=create('delayed');await new Promise(resolve=>setTimeout(resolve,30));approval='';world.abort.abort();caches[0].dispose();
  let cancelled=false;try{await pending;}catch(error){cancelled=(error as Error)?.name==='AbortError';}assert(cancelled,'Ended Image owner accepted delayed compressed bytes');
  await new Promise(resolve=>setTimeout(resolve,400));assert(caches[0].statistics.active===0&&caches[0].statistics.retainedEntries===0,'Canceled Image transfer left retained resources');
  return {completed:true,scope:'Actual BrowserWorld Image entity pixels on fixed cookie-owned inputs; no domain, native framebuffer or whole-world loading claim',deadlineMs:30000,cases,uploads,warnings,realImageCancellation:true,performance:world.getPerformance()};
 }finally{
  clearTimeout(deadline);controller.abort();approval='';gl.compressedTexSubImage2D=original;renderer.setRenderTarget(null);for(const target of targets)target.dispose();
  owned.releaseKeeping();world.objects.clear();world.dispose();for(const cache of caches)cache.dispose();
  assert(caches.every(cache=>cache.statistics.active===0&&cache.statistics.readers===0&&cache.statistics.retainedEntries===0),'World teardown retained compressed Image ownership');
 }
}
Object.assign(window,{runImageCompressedWorldFixture});
