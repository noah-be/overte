// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld preparation on explicit fixture authority, real browser
// images/bitmaps and validated native KTX. Not a public-domain/performance proof.
import {expect,test} from '@playwright/test';
function greenKtx(){
 const key=new TextEncoder().encode('hifi.gpu\0'),payload=new Uint8Array(36);payload[0]=1;new DataView(payload.buffer).setUint32(29,1,true);
 const meta=4+Math.ceil((key.length+payload.length)/4)*4,bytes=new Uint8Array(64+meta+36),view=new DataView(bytes.buffer);
 bytes.set([0xab,0x4b,0x54,0x58,0x20,0x31,0x31,0xbb,13,10,26,10]);[0x04030201,0,1,0,0x8c4c,0x1907,4,4,0,0,1,3,meta].forEach((value,index)=>view.setUint32(12+4*index,value,true));view.setUint32(64,key.length+payload.length,true);bytes.set(key,68);bytes.set(payload,68+key.length);
 let at=64+meta;for(let i=0;i<3;i++){view.setUint32(at,8,true);view.setUint16(at+4,0x07e0,true);at+=12;}return Buffer.from(bytes);
}
for(const source of ['image','bitmap','native-ktx'] as const)for(const sampler of ['shared','different'] as const)test(`foreground World ${source} ${sampler}: exact pixels with bounded first-visible residency and clean disposal`,async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/assets/foreground-fixture?**',async route=>{
  const address=new URL(route.request().url());expect(address.searchParams.size).toBe(1);expect(['https://foreground-fixture.invalid/green.ktx','https://foreground-fixture.invalid/hidden.ktx','https://foreground-fixture.invalid/behind.ktx']).toContain(address.searchParams.get('url'));
  await route.fulfill({contentType:'image/ktx',headers:{'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'},body:greenKtx()});
 });
 await page.goto('/');
 const result=await page.evaluate(async({source,sampler})=>{
  const path='/tests/foreground-textures-fixture.ts';const {THREE,BrowserWorld,NativeCompressedColorCache,nativeCompressedColorAlpha}=await import(/* @vite-ignore */path);
  async function draw(prepared:boolean){
   let active=true;const authority={generation:'controlled-foreground-approval-1',assertCurrent(){if(!active)throw new DOMException('Fixture authority ended','AbortError');}};
   const resolve=(url:string)=>{const address=new URL(url);if(address.origin!=='https://foreground-fixture.invalid'||address.username||address.password||address.hash)throw Error('Unapproved fixture asset');return `${location.origin}/api/assets/foreground-fixture?url=${encodeURIComponent(url)}`;};
   const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:256px;height:192px';document.body.append(host);const warnings:string[]=[];
   const world:any=new BrowserWorld(host,{texturePreparation:prepared,captureAssetAuthority:()=>authority,resolveAsset:resolve,onPose:()=>{},onInteract:()=>{},onStatus:(text:string,kind?:string)=>{if(kind==='warning'||kind==='error')warnings.push(text);}});
   cancelAnimationFrame(world.frame);world.setEnabled(true);world.setInputEnabled(false);const renderer=world.renderer,gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 required');renderer.setPixelRatio(1);renderer.setSize(256,192);world.camera.position.set(0,0,3);world.camera.rotation.set(0,0,0);world.camera.aspect=256/192;world.camera.updateProjectionMatrix();
   const maps:any[]=[],materials:any[]=[],geometry=new THREE.PlaneGeometry(1,1.5),root=new THREE.Group();root.visible=false;world.scene.add(root);world.objects.set('owned-fixture',root);world.entities.set('owned-fixture',{id:'owned-fixture',type:'Model',visible:true});
   let cache:any,bitmap:ImageBitmap|undefined;const allocations:{levels:number;width:number;height:number}[]=[],originalStorage=gl.texStorage2D;
   gl.texStorage2D=function(...args:any[]){allocations.push({levels:args[1],width:args[3],height:args[4]});return Reflect.apply(originalStorage,gl,args);};
   const uploads={image:0,bitmap:0,compressed:0},originalImage=gl.texSubImage2D,originalCompressed=gl.compressedTexSubImage2D;
   gl.texSubImage2D=function(...args:any[]){if(args.some(value=>value instanceof HTMLImageElement))uploads.image++;if(args.some(value=>value instanceof ImageBitmap))uploads.bitmap++;return Reflect.apply(originalImage,gl,args);};
   gl.compressedTexSubImage2D=function(...args:any[]){uploads.compressed++;return Reflect.apply(originalCompressed,gl,args);};
   let stats:any;
   try{
    if(source==='native-ktx'){
     const s3tc=!!gl.getExtension('WEBGL_compressed_texture_s3tc'),s3tcSRGB=!!gl.getExtension('WEBGL_compressed_texture_s3tc_srgb');if(!s3tc||!s3tcSRGB)throw Error('Actual GPU lacks required native KTX capabilities');
     cache=new NativeCompressedColorCache({origin:location.origin,sessionId:'foreground-fixture',authority:()=>active?'controlled-foreground-approval-1':null,resolveAsset:resolve,capabilities:{s3tc,s3tcSRGB,maximumTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE)}});
     maps.push(await cache.load('https://foreground-fixture.invalid/green.ktx'),await cache.load('https://foreground-fixture.invalid/green.ktx'),await cache.load('https://foreground-fixture.invalid/hidden.ktx'),await cache.load('https://foreground-fixture.invalid/behind.ktx'));
     if(!maps.every(map=>nativeCompressedColorAlpha(map)==='opaque'))throw Error('Actual KTX ownership/usage classification failed');
    }else{
     const pixels=document.createElement('canvas');pixels.width=pixels.height=4;const context=pixels.getContext('2d')!;context.fillStyle='#00ff00';context.fillRect(0,0,4,4);const image=new Image();image.src=pixels.toDataURL('image/png');await image.decode();
     const input=source==='bitmap'?(bitmap=await createImageBitmap(image)):image,a=new THREE.Texture(input);a.colorSpace=THREE.SRGBColorSpace;a.needsUpdate=true;maps.push(a,a.clone(),new THREE.Texture(input),new THREE.Texture(input));for(const map of maps){map.colorSpace=THREE.SRGBColorSpace;if(map.version===0)map.needsUpdate=true;}
    }
    if(sampler==='different')maps[1].wrapS=maps[0].wrapS===THREE.RepeatWrapping?THREE.ClampToEdgeWrapping:THREE.RepeatWrapping;
    const samplerDifference=maps[0].wrapS!==maps[1].wrapS;
    if(samplerDifference!==(sampler==='different'))throw Error('The fixture failed to create genuinely shared/different sampler keys');
    for(let i=0;i<maps.length;i++){const material=new THREE.MeshBasicMaterial({map:maps[i],toneMapped:false});materials.push(material);const mesh=new THREE.Mesh(geometry,material);mesh.position.x=i===0?-.6:i===1?.6:100;mesh.position.z=i===3?10:0;if(i===3){mesh.position.x=0;mesh.visible=false;}root.add(mesh);}
    const versions=maps.map(map=>[map.version,map.source.version]),hooks=materials.map(material=>[material.onBeforeCompile,material.customProgramCacheKey]),sampleCount=()=>({...uploads}),sum=(value:any)=>value.image+value.bitmap+value.compressed;
    const before=sampleCount();await world.prepareGraphics(root,()=>world.objects.get('owned-fixture')===root);const beforeRender=sampleCount(),beforeAllocations=allocations.map(value=>({...value})),beforeGpu=renderer.info.memory.textures;
    if(bitmap&&bitmap.width!==4)throw Error('Borrowed ImageBitmap was closed by preparation');root.visible=true;renderer.render(world.scene,world.camera);if(gl.getError()!==gl.NO_ERROR)throw Error('Foreground rendering raised an actual WebGL error');
    const afterRender=sampleCount(),firstGpu=renderer.info.memory.textures,rgba=new Uint8Array(256*192*4);gl.readPixels(0,0,256,192,gl.RGBA,gl.UNSIGNED_BYTE,rgba);if(gl.getError()!==gl.NO_ERROR)throw Error('Pixel readback raised an actual WebGL error');const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',rgba))].map(value=>value.toString(16).padStart(2,'0')).join('');
    const centerPixels=[0,1].map(index=>{const projected=new THREE.Vector3(0,0,0).applyMatrix4(root.children[index].matrixWorld).project(world.camera);if(projected.x<=-1||projected.x>=1||projected.y<=-1||projected.y>=1||projected.z<=-1||projected.z>=1)throw Error('An independently projected visible fixture center is outside the actual view');const x=Math.floor((projected.x*.5+.5)*256),y=Math.floor((projected.y*.5+.5)*192),at=(y*256+x)*4;return Array.from(rgba.slice(at,at+4));});
    const greenPixels=Array.from({length:rgba.length/4},(_,i)=>i*4).filter(i=>rgba[i+1]>240&&rgba[i]<5&&rgba[i+2]<5).length;
    stats={before,beforeRender,afterRender,beforeGpu,firstGpu,beforeAllocations,firstAllocations:allocations.map(value=>({...value})),warnings,hash,greenPixels,centerPixels,samplerDifference,initialWrapS:[maps[0].wrapS,maps[1].wrapS],versionsUnchanged:maps.every((map,i)=>map.version===versions[i][0]&&map.source.version===versions[i][1]),hooksUnchanged:materials.every((material,i)=>material.onBeforeCompile===hooks[i][0]&&material.customProgramCacheKey===hooks[i][1]),sourceShared:maps[0].source===maps[1].source,preparation:world.getPerformance().texturePreparation,uploadDelta:sum(afterRender)-sum(beforeRender)};
    // The normal renderer must still initialize an originally offscreen map
    // when the real camera/geometry makes it visible; it was never discarded.
    root.children[2].position.x=0;renderer.render(world.scene,world.camera);stats.afterReveal=sampleCount();stats.gpuAfterReveal=renderer.info.memory.textures;stats.bitmapLiveAfterReveal=bitmap?bitmap.width===4:true;
   }finally{
    active=false;gl.texStorage2D=originalStorage;gl.texSubImage2D=originalImage;gl.compressedTexSubImage2D=originalCompressed;cache?.dispose();world.dispose();bitmap?.close();geometry.dispose();host.remove();if(stats){stats.releasedGpu=renderer.info.memory.textures;stats.releasedReferences=world.texturePreparations?.stats.references??0;}renderer.forceContextLoss();
   }
   return stats;
  }
  return {baseline:await draw(false),prepared:await draw(true)};
 },{source,sampler});
 await testInfo.attach('foreground-texture-fidelity',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,source,sampler,report:result,errors})});
 expect(errors).toEqual([]);
 const {baseline,prepared}=result,keys=sampler==='shared'?1:2,uploads=source==='native-ktx'?keys*3:keys;
 expect(prepared.hash).toBe(baseline.hash);expect(prepared.greenPixels).toBeGreaterThan(1000);expect(prepared.sourceShared).toBe(true);expect(prepared.samplerDifference).toBe(sampler==='different');expect(baseline.samplerDifference).toBe(sampler==='different');expect(prepared.centerPixels).toEqual([[0,255,0,255],[0,255,0,255]]);expect(baseline.centerPixels).toEqual([[0,255,0,255],[0,255,0,255]]);expect(prepared.versionsUnchanged).toBe(true);expect(prepared.hooksUnchanged).toBe(true);
 expect(Object.values(baseline.beforeRender).reduce((a:number,b:any)=>a+b,0)).toBe(0);expect(Object.values(prepared.beforeRender).reduce((a:number,b:any)=>a+b,0)).toBe(uploads);expect(baseline.uploadDelta).toBe(uploads);expect(prepared.uploadDelta).toBe(0);
 expect(prepared.beforeGpu).toBe(keys);expect(baseline.firstGpu).toBe(keys);expect(prepared.firstGpu).toBe(keys);expect(prepared.gpuAfterReveal).toBe(keys+1);expect(prepared.bitmapLiveAfterReveal).toBe(true);expect(prepared.releasedGpu).toBe(0);expect(baseline.releasedGpu).toBe(0);expect(prepared.releasedReferences).toBe(0);expect(prepared.preparation.initCalls).toBe(2);expect(prepared.preparation.peakReferences).toBe(2);expect(prepared.preparation.failed).toBe(0);expect(prepared.preparation.activeBindings).toBe(0);expect(prepared.preparation.peakBindings).toBe(4);expect(prepared.warnings).toEqual([]);expect(baseline.warnings).toEqual([]);expect(prepared.beforeAllocations).toHaveLength(keys);expect(prepared.firstAllocations).toEqual(prepared.beforeAllocations);expect(baseline.firstAllocations).toEqual(prepared.firstAllocations);for(const dimensions of prepared.firstAllocations){expect(dimensions.width).toBe(4);expect(dimensions.height).toBe(4);expect(dimensions.levels).toBe(3);}
});
