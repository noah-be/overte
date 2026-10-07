// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {expect,test} from '@playwright/test';

test('actual World Images respond to native local Light only when emissivefalse; tint and blended alpha remain authored',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/');
 const report=await page.evaluate(async()=>{
  const path='/tests/native-image-material-fixture.ts';const {THREE,BrowserWorld}=await import(/* @vite-ignore */path);
  const trackerPath='/tests/native-image-gl-owner.ts';const {trackNativeImageTextures}=await import(/* @vite-ignore */trackerPath);
  const dfgPath='/tests/native-image-dfg-observer.ts';const {observeNativeImageDfg}=await import(/* @vite-ignore */dfgPath);
  const canvas=document.createElement('canvas');canvas.width=canvas.height=8;const ctx=canvas.getContext('2d')!;
  ctx.fillStyle='white';ctx.fillRect(0,0,8,8);const white=canvas.toDataURL('image/png');
  ctx.clearRect(0,0,8,8);ctx.fillStyle='rgba(255,255,255,.5)';ctx.fillRect(0,0,8,8);const half=canvas.toDataURL('image/png');
  ctx.clearRect(0,0,8,8);ctx.fillStyle='white';ctx.fillRect(4,0,4,8);const binary=canvas.toDataURL('image/png');
  const assets=new Map([['https://image-light-fixture.invalid/white.png',white],['https://image-light-fixture.invalid/half.png',half],['https://image-light-fixture.invalid/binary.png',binary]]);
  let approved=true;const authority={generation:'owned-image-fixture',assertCurrent(){if(!approved)throw new DOMException('Fixture permission revoked','AbortError');}};
  const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:256px;height:192px';document.body.append(host);
  const warnings:string[]=[],ownedMaps:any[]=[],disposed=new Map<any,number>();
  let world:any,renderer:any,gl:WebGL2RenderingContext,tracker:ReturnType<typeof trackNativeImageTextures>|undefined,referenceMaterial:any,referenceGeometry:any,reference:any,result:any,dfgObserver:ReturnType<typeof observeNativeImageDfg>|undefined;
  const ownMap=(map:any)=>{ownedMaps.push(map);disposed.set(map,0);map.addEventListener('dispose',()=>disposed.set(map,disposed.get(map)!+1));if(map.image!==map.source.data)throw Error('Actual Image texture/source data mismatch');tracker!.own(map.source.data);};
  try{
  world=new BrowserWorld(host,{captureAssetAuthority:()=>authority,resolveAsset:(url:string)=>{authority.assertCurrent();const source=assets.get(url);if(!source)throw Error('Unapproved Image fixture asset');return source;},onPose(){},onInteract(){},onStatus:(text:string,kind?:string)=>{if(kind==='warning'||kind==='error')warnings.push(text);}});
  cancelAnimationFrame(world.frame);world.setInputEnabled(false);world.setPresentationEnabled(false);
  renderer=world.renderer;gl=renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 is required');renderer.setPixelRatio(1);renderer.setSize(256,192);renderer.setClearColor(0x000000,1);tracker=trackNativeImageTextures(gl);
  const entities=[
   {id:'lit',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/white.png',position:{x:-.55,y:0,z:0},dimensions:{x:.8,y:1,z:.01},color:{red:128,green:128,blue:128},emissive:false},
   {id:'unlit',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/white.png',position:{x:.55,y:0,z:0},dimensions:{x:.8,y:1,z:.01},color:{red:128,green:128,blue:128},emissive:true},
   {id:'owned-local-light',type:'Light',position:{x:0,y:0,z:2},dimensions:{x:20,y:20,z:20},intensity:20,color:{red:255,green:255,blue:255},visible:false},
  ];
  world.upsertEntities(entities);
  const ready=async(ids:string[])=>{const deadline=performance.now()+15000;while(ids.some(id=>world.objects.get(id)?.userData.shadersReady!==true)){if(performance.now()>deadline)throw Error(`Image preparation did not complete: ${warnings.join('; ')}`);await new Promise(resolve=>setTimeout(resolve,10));}};
  await ready(['lit','unlit']);
  const material=(id:string)=>{let found:any;world.objects.get(id).traverse((object:any)=>{if(object instanceof THREE.Mesh)found=object.material;});if(!found)throw Error('Actual Image mesh missing');return found;};
  const lit=material('lit'),unlit=material('unlit'),maps=[lit.map,unlit.map],sources=maps.map(map=>map.source),versions=maps.map(map=>[map.version,map.source.version]);
  for(const map of maps)ownMap(map);
  const setupCamera=()=>{world.camera.position.set(0,0,3);world.camera.quaternion.identity();world.camera.aspect=256/192;world.camera.updateProjectionMatrix();};
  const pixel=(position:any)=>{const p=new THREE.Vector3(position.x,position.y,position.z).project(world.camera),out=new Uint8Array(4);gl.readPixels(Math.floor((p.x*.5+.5)*256),Math.floor((p.y*.5+.5)*192),1,1,gl.RGBA,gl.UNSIGNED_BYTE,out);return Array.from(out);};
  let time=performance.now()+1000;
  const draw=(light:boolean)=>{world.upsertEntities([{id:'owned-local-light',type:'Light',visible:light}]);time+=500;world.animate(time);cancelAnimationFrame(world.frame);setupCamera();renderer.render(world.scene,world.camera);if(gl.getError()!==gl.NO_ERROR)throw Error('Actual Image rendering failed');return {lit:pixel(entities[0].position),unlit:pixel(entities[1].position),selectedIntensity:world.pointSlots.reduce((sum:number,light:any)=>sum+light.intensity,0)};};
  const off=draw(false);
  const actualDfg=()=>renderer.properties.get(lit).uniforms?.dfgLUT?.value;
  dfgObserver=observeNativeImageDfg(actualDfg());
  const uniformIdentities=[dfgObserver.uniformMatches(actualDfg())];
  const on=draw(true);uniformIdentities.push(dfgObserver.uniformMatches(actualDfg()));
  const again=draw(false);uniformIdentities.push(dfgObserver.uniformMatches(actualDfg()));
  // Independent explicit Basic reference: native byte tint decoded once,
  // texture alpha multiplied by uniform alpha and ordinary blending. This
  // reference deliberately does not call the production Image factory.
  world.removeEntities(['lit','unlit','owned-local-light']);
  world.upsertEntities([{id:'blend',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/half.png',position:{x:-.55,y:0,z:0},dimensions:{x:.8,y:1,z:.01},color:{red:64,green:128,blue:192},alpha:.5,emissive:true},
   {id:'binary',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/binary.png',position:{x:0,y:10,z:0},dimensions:{x:.8,y:1,z:.01},emissive:true}]);
  await ready(['blend','binary']);const blended=material('blend'),masked=material('binary');ownMap(blended.map);ownMap(masked.map);
  const linear=(byte:number)=>{const value=byte/255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4;};
  referenceMaterial=new THREE.MeshBasicMaterial({map:blended.map,color:new THREE.Color(linear(64),linear(128),linear(192)),opacity:.5,transparent:true,toneMapped:false,side:THREE.DoubleSide,depthWrite:false});referenceMaterial.forceSinglePass=true;
  referenceGeometry=new THREE.PlaneGeometry(.8,1);reference=new THREE.Mesh(referenceGeometry,referenceMaterial);reference.position.set(.55,0,0);world.scene.add(reference);setupCamera();renderer.render(world.scene,world.camera);
  if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual Image reference rendering failed');
  const alphaPixels={actual:pixel({x:-.55,y:0,z:0}),reference:pixel({x:.55,y:0,z:0})};
  result={off,on,again,alphaPixels,uniformIdentities,defaultClass:lit.type,explicitUnlitClass:unlit.type,binaryBlend:{transparent:masked.transparent,alphaTest:masked.alphaTest,depthWrite:masked.depthWrite},versionsUnchanged:maps.every((map,index)=>map.version===versions[index][0]&&map.source.version===versions[index][1]),sourcesUnchanged:maps.every((map,index)=>map.source===sources[index]),warnings};
  return result;
  }finally{
   approved=false;
   try{
    try{if(reference)world.scene.remove(reference);}
    finally{try{referenceMaterial?.dispose();}finally{try{referenceGeometry?.dispose();}finally{world?.dispose();}}}
   }
   finally{
    try{
     const contextValid=!!gl!&&!gl!.isContextLost()&&gl!.getError()===gl!.NO_ERROR;
     const cleanup={ownedTextureDisposeCounts:ownedMaps.map(map=>disposed.get(map)),gpuOwnership:tracker?.report(dfgObserver?.uploadData),borrowedDFG:dfgObserver?.report(),contextValid};
     if(result)Object.assign(result,cleanup);
     // Preserve failure-path diagnostics without returning handles or user data.
     (window as any).__nativeImageFixtureCleanup=cleanup;
    }finally{try{dfgObserver?.close();}finally{try{tracker?.restore();}finally{host.remove();}}}
   }
  }
 });
 await testInfo.attach('actual-world-image-light',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(errors).toEqual([]);expect(report.warnings).toEqual([]);expect(report.defaultClass).toBe('MeshStandardMaterial');expect(report.explicitUnlitClass).toBe('MeshBasicMaterial');
 expect(report.off.selectedIntensity).toBe(0);expect(report.on.selectedIntensity).toBe(20);expect(report.again.selectedIntensity).toBe(0);
 expect(report.on.lit[0]-report.off.lit[0]).toBeGreaterThan(15);expect(report.again.lit).toEqual(report.off.lit);
 expect(report.off.unlit).toEqual([128,128,128,255]);expect(report.on.unlit).toEqual(report.off.unlit);expect(report.again.unlit).toEqual(report.off.unlit);
 expect(report.alphaPixels.actual).toEqual(report.alphaPixels.reference);expect(report.alphaPixels.actual.slice(0,3).some((value:number)=>value>0)).toBe(true);
 expect(report.binaryBlend).toEqual({transparent:true,alphaTest:0,depthWrite:false});expect(report.versionsUnchanged).toBe(true);expect(report.sourcesUnchanged).toBe(true);expect(report.ownedTextureDisposeCounts).toEqual([1,1,1,1]);
 expect(report.uniformIdentities).toEqual([true,true,true]);expect(report.contextValid).toBe(true);
 expect(report.borrowedDFG.identified).toBe(true);expect(report.borrowedDFG.disposeEvents).toBe(0);expect(report.borrowedDFG.sourceUnchanged).toBe(true);expect(report.borrowedDFG.dataUnchanged).toBe(true);expect(report.borrowedDFG.versionsUnchanged).toBe(true);expect(report.borrowedDFG.samplerUnchanged).toBe(true);expect(report.borrowedDFG.samplerAfter).toEqual(report.borrowedDFG.samplerBefore);expect(report.borrowedDFG.metadata).toEqual({width:16,height:16,dataLength:512,dataBytes:1024,format:1030,type:1016});
 expect(report.gpuOwnership.deleteFailures).toBe(0);expect(report.gpuOwnership.borrowedRemaining).toBe(1);expect(report.gpuOwnership.created-report.gpuOwnership.deleted).toBe(report.gpuOwnership.borrowedRemaining);expect(report.gpuOwnership.ownedUploaded).toBeGreaterThanOrEqual(2);expect(report.gpuOwnership.ownedRemaining).toBe(0);expect(report.gpuOwnership.borrowedUploaded).toBe(1);expect(report.gpuOwnership.unrecognizedRemaining).toBe(0);
});

test('actual World removed Image immediately cancels a late real alpha bitmap and never publishes',async({page},testInfo)=>{
 await page.goto('/');const report=await page.evaluate(async()=>{
  const path='/tests/native-image-material-fixture.ts';const {THREE,BrowserWorld}=await import(/* @vite-ignore */path);
  const source=document.createElement('canvas');source.width=source.height=8;source.getContext('2d')!.fillRect(0,0,8,8);const uri=source.toDataURL();
  const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:128px;height:96px';document.body.append(host);
  let approved=true;const warnings:string[]=[],authority={generation:'late-image-reader',assertCurrent(){if(!approved)throw new DOMException('Image permission revoked','AbortError');}};
  const gatePath='/tests/native-image-bitmap-gate.ts';const {createNativeImageBitmapGate}=await import(/* @vite-ignore */gatePath);
  const realBitmap=globalThis.createImageBitmap;let world:any,loaded:any,disposed=0,gate:ReturnType<typeof createNativeImageBitmapGate>|undefined;
  const bound=async(promise:Promise<unknown>)=>{let timer:any;try{await Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('Real Image alpha ownership did not settle')),10000))]);}finally{clearTimeout(timer);}};
  try{
   world=new BrowserWorld(host,{captureAssetAuthority:()=>authority,resolveAsset:(url:string)=>{authority.assertCurrent();if(url!=='https://image-light-fixture.invalid/pending.png')throw Error('Unapproved fixture');return uri;},onPose(){},onInteract(){},onStatus:(text:string,kind?:string)=>{if(kind==='warning'||kind==='error')warnings.push(text);}});
   cancelAnimationFrame(world.frame);world.setInputEnabled(false);world.setPresentationEnabled(false);
   const texture=world.texture.bind(world);
   world.texture=async(...args:any[])=>{loaded=await texture(...args);loaded.addEventListener('dispose',()=>disposed++);return loaded;};
   gate=createNativeImageBitmapGate(()=>loaded?.image,realBitmap);
   globalThis.createImageBitmap=gate.invoke;
   world.upsertEntities([{id:'pending',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/pending.png',emissive:false}]);await bound(gate.ready);
   const bitmap=await gate.ready,reader=world.modelReaders.get(world.objects.get('pending'));world.removeEntities(['pending']);approved=false;
   for(let at=0;at<100&&disposed!==1;at++)await new Promise(resolve=>setTimeout(resolve,10));
   gate.deliver();
   // Preserve the original 20ms post-delivery observation window.
   await new Promise(resolve=>setTimeout(resolve,20));
   return {realBitmapWasProduced:true,bitmapClosed:bitmap.width===0,readerAborted:reader.signal.aborted,disposed,lateRootPublished:world.objects.has('pending'),warnings};
  }finally{
   approved=false;globalThis.createImageBitmap=realBitmap;
   try{gate?.close();}finally{try{world?.dispose();}finally{host.remove();}}
  }
 });
 await testInfo.attach('actual-world-image-cancellation',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report})});
 expect(report).toEqual({realBitmapWasProduced:true,bitmapClosed:true,readerAborted:true,disposed:1,lateRootPublished:false,warnings:[]});
});


test('actual World Image fixture failure closes a real bitmap produced only after owned teardown',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/');
 const report=await page.evaluate(async()=>{
  const path='/tests/native-image-material-fixture.ts';const {BrowserWorld}=await import(/* @vite-ignore */path);
  const gatePath='/tests/native-image-bitmap-gate.ts';const {createNativeImageBitmapGate}=await import(/* @vite-ignore */gatePath);
  const source=document.createElement('canvas');source.width=source.height=8;source.getContext('2d')!.fillRect(0,0,8,8);const uri=source.toDataURL();
  const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:128px;height:96px';document.body.append(host);
  let approved=true,world:any,loaded:any,disposed=0,startedResolve!:()=>void,releaseFactory!:()=>void,gate:ReturnType<typeof createNativeImageBitmapGate>|undefined;
  const warnings:string[]=[],authority={generation:'failed-image-fixture',assertCurrent(){if(!approved)throw new DOMException('Image permission revoked','AbortError');}};
  const started=new Promise<void>(resolve=>startedResolve=resolve),factoryHeld=new Promise<void>(resolve=>releaseFactory=resolve),realBitmap=globalThis.createImageBitmap;
  const bound=async<T>(promise:Promise<T>)=>{let timer:any;try{return await Promise.race([promise,new Promise<never>((_,reject)=>timer=setTimeout(()=>reject(Error('Real late bitmap fixture did not settle')),10000))]);}finally{clearTimeout(timer);}};
  try{
   world=new BrowserWorld(host,{captureAssetAuthority:()=>authority,resolveAsset:(url:string)=>{authority.assertCurrent();if(url!=='https://image-light-fixture.invalid/failure.png')throw Error('Unapproved fixture');return uri;},onPose(){},onInteract(){},onStatus:(text:string,kind?:string)=>{if(kind==='warning'||kind==='error')warnings.push(text);}});
   cancelAnimationFrame(world.frame);world.setInputEnabled(false);world.setPresentationEnabled(false);
   if(!(world.renderer.getContext() instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 is required');
   const texture=world.texture.bind(world);world.texture=async(...args:any[])=>{loaded=await texture(...args);loaded.addEventListener('dispose',()=>disposed++);return loaded;};
   gate=createNativeImageBitmapGate(()=>loaded?.image,(async(...args:any[])=>{startedResolve();await factoryHeld;return Reflect.apply(realBitmap,globalThis,args);}) as typeof createImageBitmap);
   globalThis.createImageBitmap=gate.invoke;
   world.upsertEntities([{id:'failed',type:'Image',keepAspectRatio:false,imageURL:'https://image-light-fixture.invalid/failure.png',emissive:false}]);await bound(started);
   const reader=world.modelReaders.get(world.objects.get('failed'));
   // This is the real cleanup order of a failed fixture, while the factory has
   // not yet produced its bitmap. No held global result may survive that exit.
   approved=false;globalThis.createImageBitmap=realBitmap;gate.close();world.dispose();host.remove();releaseFactory();
   const bitmap=await bound<ImageBitmap>(gate.ready);
   return {producedAfterTeardown:true,bitmapClosed:bitmap.width===0,readerAborted:reader.signal.aborted,disposed,lateRootPublished:world.objects.has('failed'),globalFactoryRestored:globalThis.createImageBitmap===realBitmap,warnings};
  }finally{approved=false;globalThis.createImageBitmap=realBitmap;try{gate?.close();}finally{releaseFactory();try{world?.dispose();}finally{host.remove();}}}
 });
 await testInfo.attach('actual-world-image-failure-cleanup',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(errors).toEqual([]);expect(report).toEqual({producedAfterTeardown:true,bitmapClosed:true,readerAborted:true,disposed:1,lateRootPublished:false,globalFactoryRestored:true,warnings:[]});
});
