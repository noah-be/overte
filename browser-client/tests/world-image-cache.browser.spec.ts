// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Synthetic authored model fixtures test source reuse and actual pixels, not public-domain admission.
import {expect,test} from '@playwright/test';
import type {Page} from '@playwright/test';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==','base64');
const vertices=Buffer.from(new Float32Array([-.5,-.5,0,.5,-.5,0,0,.5,0,0,0,1,0,.5,1]).buffer);
const gltf={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0,TEXCOORD_0:1},material:0}]}],
  buffers:[{byteLength:vertices.length,uri:'triangle.bin'}],bufferViews:[{buffer:0,byteOffset:0,byteLength:36},{buffer:0,byteOffset:36,byteLength:24}],
  accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[-.5,-.5,0],max:[.5,.5,0]},{bufferView:1,componentType:5126,count:3,type:'VEC2'}],
  extensionsUsed:['KHR_materials_unlit'],materials:[{extensions:{KHR_materials_unlit:{}},pbrMetallicRoughness:{baseColorTexture:{index:0}},doubleSided:true}],textures:[{source:0}],images:[{uri:'color.png'}]};
// Analytic oracle from pinned Three 0.186.1 tonemapping_pars_fragment.glsl.js:
// ACES input/output matrices, RRT/ODT fit, then sRGB OETF. Independent of GPU
// pixels and cache implementation. KHR unlit still has toneMapped=true; our
// authored FST unlit disables grading explicitly.
function acesGreen(exposure:number):number[]{
  const [r,g,b]=[.35458,.90834,.13383].map(value=>value*exposure/.6)
    .map(value=>(value*(value+.0245786)-.000090537)/(value*(.983729*value+.432951)+.238081));
  return [1.60475*r-.53108*g-.07367*b,-.10208*r+1.10813*g-.00605*b,-.00327*r-.07276*g+1.07602*b]
    .map(value=>Math.max(0,Math.min(1,value))).map(value=>Math.round(255*(value<=.0031308?value*12.92:1.055*Math.pow(value,1/2.4)-.055)));
}
function expectPixel(actual:number[],expected:number[]){
  expect(actual[3]).toBe(255);
  for(let channel=0;channel<3;channel++)expect(Math.abs(actual[channel]-expected[channel]),`Color channel ${channel} must match the analytic authored-color oracle`).toBeLessThanOrEqual(1);
}
async function pixels(page:Page){
  const bytes=await page.locator('#cache-world canvas').screenshot();
  return page.evaluate(async base64=>{const image=await createImageBitmap(await(await fetch(`data:image/png;base64,${base64}`)).blob());const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const context=canvas.getContext('2d')!;context.drawImage(image,0,0);const rgb=[...context.getImageData(image.width/2,image.height/2,1,1).data];image.close();return rgb;},bytes.toString('base64'));
}
for(const format of ['gltf','fst'] as const)test(`Decoded source reuse preserves ${format} textures after neighboring model removal and rejoins cold`,async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
  let imageRequests=0;const imageAuthorities:string[]=[];
  await page.route('**/cache-assets/**',async route=>{
    const url=route.request().url();const headers={'cache-control':'no-store'};
    if(url.endsWith('color.png')){imageRequests++;imageAuthorities.push(new URL(url).pathname.split('/')[2]);await route.fulfill({headers,contentType:'image/png',body:png});}
    else if(url.endsWith('triangle.gltf'))await route.fulfill({headers,contentType:'model/gltf+json',body:JSON.stringify(gltf)});
    else if(url.endsWith('triangle.bin'))await route.fulfill({headers,contentType:'application/octet-stream',body:vertices});
    else if(url.endsWith('triangle.fst'))await route.fulfill({headers,body:'filename = triangle.obj\nmaterialMap = [{"mat::Wood":"material.json#Wood"}]\n'});
    else if(url.endsWith('triangle.obj'))await route.fulfill({headers,body:'v -0.5 -0.5 0\nv 0.5 -0.5 0\nv 0 0.5 0\nvt 0 0\nvt 1 0\nvt 0.5 1\nusemtl Wood\nf 1/1 2/2 3/3\n'});
    else if(url.includes('material.json'))await route.fulfill({headers,contentType:'application/json',body:JSON.stringify({materials:{model:'hifi_pbr',name:'Wood',unlit:true,albedoMap:'color.png'}})});
    else await route.fulfill({status:404,body:'Unexpected fixture dependency'});
  });
  await page.goto('/');
  await page.evaluate(async format=>{
    const path='/src/world.ts';const {BrowserWorld}=await import(/* @vite-ignore */path);const state=window as any;
    document.body.innerHTML='<div id="cache-world" style="width:800px;height:600px"></div>';
    state.authority=0;state.createWorld=()=>{
      const authority=++state.authority;
      // Production gateway asset paths contain a fresh session authority. The
      // browser itself may reuse a live Image's decoded bytes for an identical
      // URL even with HTTP no-store; that is outside this application's cache.
      return new BrowserWorld(document.getElementById('cache-world')!,{resolveAsset:(url:string)=>url.replace('/cache-assets/',`/cache-assets/authority-${authority}/`),onPose:()=>{},onInteract:()=>{},onStatus:()=>{}});
    };
    state.world=state.createWorld();state.entities=[{id:'center',type:'Model',modelURL:`${location.origin}/cache-assets/triangle.${format}`,position:{x:0,y:1.5,z:-3},dimensions:{x:2,y:2,z:.1}},{id:'neighbor',type:'Model',modelURL:`${location.origin}/cache-assets/triangle.${format}`,position:{x:4,y:1.5,z:-3},dimensions:{x:2,y:2,z:.1}}];
    state.world.setSpawn({x:0,y:.85,z:0});state.world.setEntities(state.entities);
    state.material=(id:string)=>{let material:any;state.world.objects.get(id).traverse((object:any)=>{if(object.isMesh)material=Array.isArray(object.material)?object.material[0]:object.material;});return material;};
  },format);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(2);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.compilingGraphics)).toBe(0);
  expect(await page.evaluate(()=>{const state=window as any,left=state.material('center').map,right=state.material('neighbor').map;left.repeat.set(2,3);return {sameSource:left.source===right.source,sameImage:left.image===right.image,separateTexture:left!==right,neighborRepeat:right.repeat.toArray(),actualImage:left.image instanceof HTMLImageElement};})).toEqual({sameSource:true,sameImage:true,separateTexture:true,neighborRepeat:[1,1],actualImage:true});
  const renderState=await page.evaluate(()=>{const state=window as any,material=state.material('center'),canvas=document.createElement('canvas');canvas.width=canvas.height=1;const context=canvas.getContext('2d')!;context.drawImage(material.map.image,0,0,1,1);return {sourcePixel:[...context.getImageData(0,0,1,1).data],mapColorSpace:material.map.colorSpace,toneMapped:material.toneMapped,toneMapping:state.world.renderer.toneMapping,exposure:state.world.renderer.toneMappingExposure};});
  expect(renderState.sourcePixel).toEqual([0,255,0,255]);expect(renderState.mapColorSpace).toBe('srgb');expect(renderState.toneMapping).toBe(4);expect(renderState.toneMapped).toBe(format==='gltf');
  const expected=format==='gltf'?acesGreen(renderState.exposure):[0,255,0];
  expect(imageRequests).toBe(1);expect(imageAuthorities).toEqual(['authority-1']);await page.evaluate(()=>{const state=window as any;state.previousSource=state.material('center').map.source;state.previousImage=state.previousSource.data;});const before=await pixels(page);expectPixel(before,expected);
  await page.evaluate(()=>{const state=window as any;state.world.setEntities([state.entities[0]]);});
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(1);
  const after=await pixels(page);expectPixel(after,expected);expect(imageRequests).toBe(1);
  // An actual new browser world represents a fresh session; no decoded image
  // or stale authority from the old world's cache may carry across it.
  await page.evaluate(()=>{const state=window as any;state.world.dispose();state.world=state.createWorld();state.world.setSpawn({x:0,y:.85,z:0});state.world.setEntities([state.entities[0]]);});
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.compilingGraphics)).toBe(0);expect(imageRequests).toBe(2);expect(imageAuthorities).toEqual(['authority-1','authority-2']);
  expect(await page.evaluate(()=>{const state=window as any,map=state.material('center').map;return {sourceChanged:map.source!==state.previousSource,imageChanged:map.image!==state.previousImage,currentAuthority:new URL(map.image.src).pathname.split('/')[2]};})).toEqual({sourceChanged:true,imageChanged:true,currentAuthority:'authority-2'});
  const joined=await pixels(page);expectPixel(joined,expected);
  expect(await page.evaluate(()=>(window as any).world.getPerformance().imageLoading.uniqueImages)).toBe(1);expect(errors).toEqual([]);
  await page.evaluate(()=>(window as any).world.dispose());
});
