// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Prepared scaffold; actual GPU execution is owned by the parent. A call to
// public initTexture is deliberately NOT counted as a unique GPU upload.
import {expect,test} from '@playwright/test';
for(const sampler of ['shared','different'] as const)for(const alpha of ['opaque','mask','blend'] as const)test(`preparing ${sampler} sampler ${alpha} maps preserves exact rendered pixels and actual upload ownership`,async({page})=>{
 await page.goto('/');
 const result=await page.evaluate(async({sampler,alpha})=>{
  const fixturePath='/tests/world-texture-preparation-fixture.ts';
  const {THREE,WorldTexturePreparation}=await import(/* @vite-ignore */fixturePath);
  const pixels=document.createElement('canvas');pixels.width=pixels.height=4;const ctx=pixels.getContext('2d')!,data=ctx.createImageData(4,4);
  for(let i=0;i<16;i++)data.data.set([i%2?255:0,i%2?0:255,Math.floor(i/4)%2?255:0,[0,64,128,255][i%4]],i*4);ctx.putImageData(data,0,0);
  const image=new Image();image.src=pixels.toDataURL('image/png');await image.decode();
  async function draw(prepared:boolean){
   const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setSize(256,192);renderer.outputColorSpace=THREE.SRGBColorSpace;
   const gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 is required for texture preparation proof');
   const scene=new THREE.Scene();scene.background=new THREE.Color(0x102030);const root=new THREE.Group();root.visible=false;scene.add(root);
   const camera=new THREE.PerspectiveCamera(55,256/192,.1,20);camera.position.z=3;
   const a=new THREE.Texture(image);a.colorSpace=THREE.SRGBColorSpace;a.needsUpdate=true;const b=a.clone();b.repeat.set(2,3);if(sampler==='different')b.wrapS=THREE.RepeatWrapping;
   const materials=[a,b].map(map=>new THREE.MeshBasicMaterial({map,toneMapped:false,transparent:alpha==='blend',alphaTest:alpha==='mask'?.5:0,depthWrite:alpha!=='blend'}));
   const geometry=new THREE.PlaneGeometry(1,1.5);for(let i=0;i<2;i++){const mesh=new THREE.Mesh(geometry,materials[i]);mesh.position.x=i?.6:-.6;root.add(mesh);}
   const textureVersions=[a.version,b.version,a.source.version],hooks=materials.map(material=>[material.onBeforeCompile,material.customProgramCacheKey]);
   const original=gl.texSubImage2D;let imageUploads=0;gl.texSubImage2D=function(...args:any[]){if(args.includes(image))imageUploads++;return Reflect.apply(original,gl,args);};
   const owner=new AbortController(),preparer=new WorldTexturePreparation(renderer,{signal:owner.signal});let stats:any;
   try{
    await renderer.compileAsync(root,camera,scene);const afterCompile=imageUploads;
    if(prepared){await preparer.prepare(root,()=>{if(owner.signal.aborted)throw new DOMException('Closed','AbortError');});}
    const beforeRender=imageUploads;root.visible=true;renderer.render(scene,camera);const afterRender=imageUploads;
    const rgba=new Uint8Array(256*192*4);gl.readPixels(0,0,256,192,gl.RGBA,gl.UNSIGNED_BYTE,rgba);const hash=await crypto.subtle.digest('SHA-256',rgba);
    stats={webgl2:true,afterCompile,beforeRender,afterRender,actualGpuTextures:renderer.info.memory.textures,preparation:preparer.stats,versionsUnchanged:JSON.stringify(textureVersions)===JSON.stringify([a.version,b.version,a.source.version]),sourceShared:a.source===b.source,hooksUnchanged:materials.every((material,i)=>material.onBeforeCompile===hooks[i][0]&&material.customProgramCacheKey===hooks[i][1]),pixelHash:[...new Uint8Array(hash)].map(value=>value.toString(16).padStart(2,'0')).join(''),nonBackgroundPixels:Array.from({length:rgba.length/4},(_,i)=>rgba[i*4+1]).filter(value=>value>100).length};
   }finally{owner.abort();gl.texSubImage2D=original;for(const material of materials)material.dispose();a.dispose();b.dispose();geometry.dispose();if(stats)stats.texturesAfterRelease=renderer.info.memory.textures;renderer.dispose();}
   return stats;
  }
  return{baseline:await draw(false),prepared:await draw(true)};
 },{sampler,alpha});
 const copies=sampler==='shared'?1:2;
 expect(result.baseline.webgl2).toBe(true);expect(result.prepared.webgl2).toBe(true);
 expect(result.baseline.afterCompile).toBe(0);expect(result.prepared.afterCompile).toBe(0);
 expect(result.baseline.beforeRender).toBe(0);expect(result.baseline.afterRender).toBe(copies);
 expect(result.prepared.beforeRender).toBe(copies);expect(result.prepared.afterRender).toBe(copies);
 expect(result.prepared.preparation.initCalls).toBe(2);expect(result.prepared.preparation.imageCalls).toBe(2);
 expect(result.prepared.preparation.references).toBe(0);expect(result.prepared.preparation.active).toBe(0);
 expect(result.baseline.actualGpuTextures).toBe(copies);expect(result.prepared.actualGpuTextures).toBe(copies);
 expect(result.baseline.texturesAfterRelease).toBe(0);expect(result.prepared.texturesAfterRelease).toBe(0);
 expect(result.prepared.pixelHash).toBe(result.baseline.pixelHash);expect(result.prepared.nonBackgroundPixels).toBeGreaterThan(1000);
 expect(result.prepared.versionsUnchanged).toBe(true);expect(result.prepared.hooksUnchanged).toBe(true);expect(result.prepared.sourceShared).toBe(true);
});
