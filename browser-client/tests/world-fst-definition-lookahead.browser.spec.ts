// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine BrowserWorld FST loading, production worker/parser, authorized HTTP
// asset routes and final local-WebGL pixels. This is not a native-domain proof.
import {test,expect} from '@playwright/test';
import {replacementMaterialFbx} from './fixtures/parsed-template-fbx';
const green=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==','base64');
const red=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==','base64');
test('Actual FST lookahead preserves pixels with genuinely detached staged geometry',async({page})=>{
 const releases:{baseline:(()=>void)|undefined;candidate:(()=>void)|undefined}={baseline:undefined,candidate:undefined};
 const errors:string[]=[],requests:{baseline:string[];candidate:string[]}={baseline:[],candidate:[]};page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body style="margin:0"></body>'}));
 await page.route('**/world-fst-lookahead/**',async route=>{
  const path=new URL(route.request().url()).pathname,which=path.includes('/baseline/')?'baseline':'candidate',file=path.split('/').at(-1)!;
  const headers={'cache-control':'no-store'};requests[which].push(file);
  if(file==='model.fbx')await route.fulfill({headers,contentType:'application/octet-stream',body:Buffer.from(replacementMaterialFbx({withoutOriginalTextures:true}))});
  else if(file==='model.fst')await route.fulfill({headers,body:'filename = model.fbx\nmaterialMap = '+JSON.stringify([{all:'first.json#First'},{'mat::First':'replacement.json#Replacement'}])});
  else if(file==='first.json')await route.fulfill({headers,contentType:'application/json',body:JSON.stringify({materials:[{name:'First',model:'hifi_pbr',unlit:true,albedoMap:'first.png'}]})});
  else if(file==='first.png'){await new Promise<void>(resolve=>{releases[which]=resolve;});await route.fulfill({headers,contentType:'image/png',body:red});}
  else if(file==='replacement.json')await route.fulfill({headers,contentType:'application/json',body:JSON.stringify({materials:[{name:'Replacement',model:'hifi_pbr',unlit:true,albedoMap:'replacement.png'}]})});
  else if(['replacement.png','shared.png','unused-a.png','only-b.png'].includes(file))await route.fulfill({headers,contentType:'image/png',body:file==='replacement.png'?green:red});
  else await route.fulfill({status:404,body:'Unexpected authorized fixture dependency'});
 });
 await page.goto('/');
 for(const which of ['baseline','candidate'] as const){
  await page.evaluate(async which=>{
   const module='/src/world.ts';const {BrowserWorld}=await import(/* @vite-ignore */module);const state=window as any;
   document.body.innerHTML='<div id="fst-world" style="width:800px;height:600px"></div>';
   state.warnings=[];state.current=true;
   const route=(url:string)=>new URL(url,location.href).href;
   state.world=new BrowserWorld(document.getElementById('fst-world')!,{fstDefinitionLookahead:which==='candidate',resolveAsset:route,
    captureAssetAuthority:()=>({generation:which,assertCurrent:()=>{if(!state.current)throw Error('Fixture visitor approval ended');}}),
    onPose(){},onInteract(){},onStatus:(message:string,kind:string)=>{if(kind==='warning'||kind==='error')state.warnings.push(message);}});
   state.world.setSpawn({x:0,y:.85,z:0});state.world.setInputEnabled(false);state.world.setEntities([{id:'actual-fst',type:'Model',modelURL:`${location.origin}/world-fst-lookahead/${which}/model.fst`,position:{x:0,y:1.5,z:-3},dimensions:{x:2,y:1.2,z:.1},collisionless:true}]);
  },which);
  await expect.poll(()=>!!releases[which]).toBe(true);
  await expect.poll(()=>page.evaluate(async()=>{const module='/tests/fst-lookahead-stage-fixture.ts';const {readStageWitness}=await import(/* @vite-ignore */module);return readStageWitness((window as any).world,'actual-fst').valid;})).toBe(true);
  if(which==='candidate')await expect.poll(()=>requests.candidate.includes('replacement.json')).toBe(true);
  else expect(requests.baseline).not.toContain('replacement.json');
  expect(requests[which]).not.toContain('replacement.png');
  releases[which]!();
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>{const s=window as any;return s.world.compilingGraphics===0&&s.world.objects.get('actual-fst').visible;})).toBe(true);
  // While disabled, the genuine RAF still updates camera/render state without
  // simulation. Await that exact fixed pose, then enable only the synchronous
  // capture invocation; toBlob owns its snapshot before any later RAF can run.
  await expect.poll(()=>page.evaluate(()=>(window as any).world.camera.position.toArray())).toEqual([0,1.5,0]);
  const proof=await page.evaluate(async which=>{
   const s=window as any,world=s.world,root=world.objects.get('actual-fst');let mesh:any;root.traverse((object:any)=>{if(object.isMesh)mesh=object;});
   const capturePromise=(()=>{world.setEnabled(true);try{return world.captureScene();}finally{world.setEnabled(false);}})();
   const capture=await capturePromise,bitmap=await createImageBitmap(capture),canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;const context=canvas.getContext('2d')!;context.drawImage(bitmap,0,0);bitmap.close();
   const bytes=context.getImageData(0,0,canvas.width,canvas.height).data;
   const point=mesh.geometry.attributes.position;const center=new (mesh.position.constructor)();for(const i of [0,1,2])center.add(new (mesh.position.constructor)().fromBufferAttribute(point,i));center.multiplyScalar(1/3);mesh.localToWorld(center);center.project(world.camera);
   const left=[...context.getImageData(Math.floor((center.x+1)*canvas.width/2),Math.floor((1-center.y)*canvas.height/2),1,1).data];
   s.proofs??={};s.proofs[which]={bytes:Uint8Array.from(bytes),geometry:JSON.stringify({positions:[...point.array],groups:mesh.geometry.groups})};
   const material=Array.isArray(mesh.material)?mesh.material[0]:mesh.material;const sourceCanvas=document.createElement('canvas');sourceCanvas.width=sourceCanvas.height=1;const sourceContext=sourceCanvas.getContext('2d')!;sourceContext.drawImage(material.map.image,0,0,1,1);
   const result={pose:world.getPose().position,camera:world.camera.position.toArray(),enabledAfterCapture:world.enabled,left,sourcePixel:[...sourceContext.getImageData(0,0,1,1).data],modelName:material.name,actualSource:material.map.image instanceof HTMLImageElement,imageLoading:world.getPerformance().imageLoading,lookahead:world.getPerformance().fstDefinitionLookahead,warnings:[...s.warnings],webGL2:world.renderer.getContext() instanceof WebGL2RenderingContext};
   world.dispose();s.current=false;return result;
  },which);
  expect(proof.pose).toEqual({x:0,y:.85,z:0});expect(proof.camera).toEqual([0,1.5,0]);expect(proof.enabledAfterCapture).toBe(false);
  expect(proof.webGL2).toBe(true);expect(proof.actualSource).toBe(true);expect(proof.modelName).toBe('Replacement');expect(proof.sourcePixel).toEqual([0,255,0,255]);expect(proof.left).toEqual([0,255,0,255]);expect(proof.warnings).toEqual([]);expect(proof.lookahead).toEqual({enabled:which==='candidate',started:which==='candidate'?1:0,consumed:which==='candidate'?1:0,capacityFallback:0});
 }
 const equality=await page.evaluate(()=>{const {baseline,candidate}=(window as any).proofs;let different=0;for(let i=0;i<baseline.bytes.length;i++)if(baseline.bytes[i]!==candidate.bytes[i])different++;return{different,geometry:baseline.geometry===candidate.geometry,sizeSame:baseline.bytes.length===candidate.bytes.length};});
 expect(equality).toEqual({different:0,geometry:true,sizeSame:true});
 expect(requests.baseline.filter(url=>url.endsWith('.png')).sort()).toEqual(['first.png','replacement.png']);
 expect(requests.candidate.filter(url=>url.endsWith('.png')).sort()).toEqual(['first.png','replacement.png']);
 expect(requests.candidate).not.toContain('unused-a.png');expect(errors).toEqual([]);
});
