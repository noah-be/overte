// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import {NativeCompressedColorCache,nativeCompressedColorAlpha} from '../../src/native-compressed-color';
import {classifyNativeAlpha} from '../../src/texture-alpha';
declare global {interface Window {runCompressedColorFixture(): Promise<unknown>}}
function check(value: unknown,message: string): asserts value {if(!value)throw Error(message);}
window.runCompressedColorFixture=async()=>{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 const renderer=new THREE.WebGLRenderer({antialias:false,alpha:true});renderer.setPixelRatio(1);renderer.setSize(32,32);document.body.append(renderer.domElement);
 const gl=renderer.getContext(),s3tc=gl.getExtension('WEBGL_compressed_texture_s3tc'),s3tcSRGB=gl.getExtension('WEBGL_compressed_texture_s3tc_srgb');
 const cache=new NativeCompressedColorCache({origin:location.origin,sessionId:'gpu-fixture',authority:()=>controller.signal.aborted?null:'controlled-fixture-revision-1',resolveAsset:url=>`${location.origin}/api/assets/gpu-fixture?url=${encodeURIComponent(url)}`,capabilities:{s3tc:!!s3tc,s3tcSRGB:!!s3tcSRGB,maximumTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE)}});
 const geometry=new THREE.PlaneGeometry(2,2),material=new THREE.RawShaderMaterial({uniforms:{map:{value:null},uvMatrix:{value:new THREE.Matrix3()}},vertexShader:'precision highp float; attribute vec3 position; attribute vec2 uv; varying vec2 vUV; void main(){vUV=uv;gl_Position=vec4(position,1.0);}',fragmentShader:'precision highp float; uniform sampler2D map; uniform mat3 uvMatrix; varying vec2 vUV; void main(){gl_FragColor=texture2D(map,(uvMatrix*vec3(vUV,1.0)).xy);}',depthTest:false,depthWrite:false,transparent:false,blending:THREE.NoBlending});
 const scene=new THREE.Scene();scene.add(new THREE.Mesh(geometry,material));const camera=new THREE.Camera();
 const textures: THREE.Texture[]=[],targets: THREE.WebGLRenderTarget[]=[],images: string[]=[],cases: unknown[]=[];
 let uploads=0,uploadBytes=0;const originalUpload=gl.compressedTexSubImage2D.bind(gl);
 gl.compressedTexSubImage2D=((...args: Parameters<WebGL2RenderingContext['compressedTexSubImage2D']>)=>{uploads++;const data=args[7];if(ArrayBuffer.isView(data))uploadBytes+=data.byteLength;return (originalUpload as (...a: unknown[])=>void)(...args);}) as WebGL2RenderingContext['compressedTexSubImage2D'];
 function render(texture: THREE.Texture,size: number) {
  check(!controller.signal.aborted,'The real GPU fixture exceeded its 30 second deadline');
  const target=new THREE.WebGLRenderTarget(size,size,{depthBuffer:false,stencilBuffer:false});target.texture.colorSpace=THREE.NoColorSpace;targets.push(target);
  material.uniforms.map.value=texture;if(texture.matrixAutoUpdate)texture.updateMatrix();material.uniforms.uvMatrix.value=texture.matrix;
  renderer.setRenderTarget(target);renderer.render(scene,camera);const data=new Uint8Array(size*size*4);renderer.readRenderTargetPixels(target,0,0,size,size,data);check(gl.getError()===gl.NO_ERROR,'Actual compressed texture upload or sampling produced a WebGL error');return data;
 }
 function compare(a: Uint8Array,b: Uint8Array){let rgbError=0,channels=0,maskDifferences=0,opaque=0,intermediate=0;
  for(let i=0;i<a.length;i+=4){const x=a[i+3]>=128,y=b[i+3]>=128;if(x!==y)maskDifferences++;if(b[i+3]===255)opaque++;else if(b[i+3]>0)intermediate++;if(x&&y){for(let c=0;c<3;c++){rgbError+=Math.abs(a[i+c]-b[i+c]);channels++;}}}
  return {rgbMAE:channels?rgbError/channels:0,maskDifferenceFraction:maskDifferences/(a.length/4),opaque,intermediate,total:a.length/4};
 }
 try {
  check(s3tc&&s3tcSRGB,'This actual GPU lacks the required color compression extensions');
  const bootstrap=await fetch('/__compressed-fixture/bootstrap',{credentials:'same-origin',signal:controller.signal});check(bootstrap.ok,'Controlled pixel fixture cookie initialization failed');
  for(const [name,size,classification] of [['opaque',768,'opaque'],['mask',512,'mask']] as const){
   const original=await fetch(`/api/assets/gpu-fixture?url=${encodeURIComponent(`fixture:${name}.png`)}`,{credentials:'same-origin',signal:controller.signal});check(original.ok,'Fixed original image could not be loaded');
   const blob=await original.blob(),url=URL.createObjectURL(blob);images.push(url);const image=new Image();image.src=url;await image.decode();check(image.width===size&&image.height===size,'Original fixture dimensions changed');
   const originalTexture=new THREE.Texture(image);originalTexture.colorSpace=THREE.SRGBColorSpace;originalTexture.wrapS=originalTexture.wrapT=THREE.RepeatWrapping;originalTexture.flipY=true;originalTexture.needsUpdate=true;textures.push(originalTexture);
   const originalUnflipped=originalTexture.clone();originalUnflipped.flipY=false;originalUnflipped.needsUpdate=true;textures.push(originalUnflipped);
   const compressed=await cache.load(`fixture:${name}.ktx`,{signal:controller.signal,sampler:{flipY:true}}),unflipped=await cache.load(`fixture:${name}.ktx`,{signal:controller.signal,sampler:{flipY:false}});textures.push(compressed,unflipped);
   check(nativeCompressedColorAlpha(compressed)===classification,'Owned compressed classification disagrees with independently audited native usage');
   const canvas=document.createElement('canvas');canvas.width=canvas.height=size;const context=canvas.getContext('2d',{willReadFrequently:true})!;context.drawImage(image,0,0);const png=context.getImageData(0,0,size,size).data;
   let opaque=0,intermediate=0;for(let i=3;i<png.length;i+=4){if(png[i]===255)opaque++;else if(png[i]>0)intermediate++;}
   check(classifyNativeAlpha(size*size,opaque,intermediate)===classification,'Actual original PNG alpha differs from native metadata');
   const baseline=render(originalTexture,size),matched=compare(baseline,render(compressed,size)),opposite=compare(baseline,render(unflipped,size));
   check(matched.rgbMAE<10,'Compressed sRGB color differs beyond the bounded lossy color tolerance');
   check(matched.maskDifferenceFraction<.01,'Compressed alpha coverage differs from the original image');
   check(matched.rgbMAE<opposite.rgbMAE,'Upload flip compensation did not preserve the original UV orientation');
   const unflippedMatch=compare(render(originalUnflipped,size),render(unflipped,size));
   check(unflippedMatch.rgbMAE<10&&unflippedMatch.maskDifferenceFraction<.01,'A no-flip original image convention differs from the compressed texture');
   if(classification==='opaque')check(matched.opaque===size*size,'RGB DXT1 unexpectedly introduced alpha holes on this implementation');
   const minified=compare(render(originalTexture,64),render(compressed,64));
   check(minified.rgbMAE<15&&minified.maskDifferenceFraction<.1,'Actual native mip chain sampling differs beyond its bounded lossy tolerance');
   cases.push({name,size,classification,originalAlpha:{total:size*size,opaque,intermediate},matched,opposite,unflippedMatch,minified,texture:{format:compressed.format,colorSpace:compressed.colorSpace,mipmapDimensions:compressed.mipmaps.map(m=>[m.width,m.height]),flipY:compressed.flipY,matrix:compressed.matrix.toArray()}});
  }
  return {completed:true,scope:'Isolated original PNG versus validated native color KTX GPU sampling, not a world loading or native framebuffer proof',cases,compressedUploads:uploads,compressedUploadBytes:uploadBytes,cache:cache.statistics,deadlineMs:30000};
 }finally{clearTimeout(timer);controller.abort();cache.dispose();for(const target of targets)target.dispose();for(const texture of textures)texture.dispose();for(const url of images)URL.revokeObjectURL(url);geometry.dispose();material.dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();}
};
