// SPDX-License-Identifier: Apache-2.0
// Renderer/loader component proof with authored FBX and genuine delayed PNG I/O.
// This is not a native-domain or public-world performance proof.
import {test,expect} from '@playwright/test';
import {deflateSync} from 'node:zlib';
import {modelFloorFbx} from './fixtures/model-floor';
function greenPixelPng():Buffer {
 const crc=(bytes:Buffer)=>{let value=0xffffffff;for(const byte of bytes){value^=byte;for(let i=0;i<8;i++)value=value&1?(value>>>1)^0xedb88320:value>>>1;}return (value^0xffffffff)>>>0;};
 const chunk=(name:string,bytes:Buffer)=>{const type=Buffer.from(name),header=Buffer.alloc(4),tail=Buffer.alloc(4);header.writeUInt32BE(bytes.length);tail.writeUInt32BE(crc(Buffer.concat([type,bytes])));return Buffer.concat([header,type,bytes,tail]);};
 const header=Buffer.alloc(13);header.writeUInt32BE(1,0);header.writeUInt32BE(1,4);header[8]=8;header[9]=6;
 return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(Buffer.from([0,40,200,60,255]))),chunk('IEND',Buffer.alloc(0))]);
}
test('genuine normalized floor supports movement before its delayed PNG and becomes visibly textured only after completion',async({page})=>{
 let imageRequested=false,release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
 await page.route('**/geometry-fixture/floor.fst',route=>route.fulfill({body:'filename = floor.fbx'}));
 await page.route('**/geometry-fixture/floor.fbx',route=>route.fulfill({body:modelFloorFbx}));
 await page.route('**/geometry-fixture/floor.png',async route=>{imageRequested=true;await gate;await route.fulfill({contentType:'image/png',body:greenPixelPng()});});
 try{
  await page.goto('/');await page.evaluate(async()=>{
   const modulePath='/src/world.ts';const{BrowserWorld}=await import(/* @vite-ignore */modulePath);const state=window as any;
   document.body.innerHTML='<div id="geometry-test" style="width:800px;height:600px"></div>';
   state.world=new BrowserWorld(document.getElementById('geometry-test')!,{resolveAsset:(url:string)=>url,onPose(){},onInteract(){},onStatus(){}});
   state.world.setSpawn({x:-2,y:.85,z:-2});state.world.setEnabled(true);
   state.world.setEntities([{id:'floor',type:'Model',modelURL:location.origin+'/geometry-fixture/floor.fst',shapeType:'static-mesh',dimensions:{x:20,y:.2,z:20}}]);
  });
  await expect.poll(()=>imageRequested).toBe(true);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().meshColliders)).toBe(1);
  const before=await page.evaluate(()=>{const world=(window as any).world,root=world.objects.get('floor');return{position:world.getPose().position,visible:root.visible,ready:root.userData.modelLoaded,children:root.children[0].children.length};});
  expect(before.visible).toBe(false);expect(before.ready).not.toBe(true);expect(before.children).toBe(0);
  await page.keyboard.down('KeyW');try{await expect.poll(()=>page.evaluate(()=>(window as any).world.getPose().position.z)).toBeLessThan(before.position.z-.5);}finally{await page.keyboard.up('KeyW');}
  expect(await page.evaluate(()=>(window as any).world.getPose().position.y)).toBeCloseTo(.85,3);
  release();await expect.poll(()=>page.evaluate(()=>(window as any).world.objects.get('floor').visible)).toBe(true);
  expect(await page.evaluate(()=>(window as any).world.getPerformance().loadedModels)).toBe(1);
  const pixel=await page.evaluate(async()=>{
   const bitmap=await createImageBitmap(await (window as any).world.captureScene()),canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;const context=canvas.getContext('2d')!;context.drawImage(bitmap,0,0);const value=[...context.getImageData(400,550,1,1).data];bitmap.close();return value;
  });expect(pixel[1]).toBeGreaterThan(pixel[0]*1.5);expect(pixel[1]).toBeGreaterThan(pixel[2]*1.5);
 }finally{release();await page.evaluate(()=>(window as any).world?.dispose()).catch(()=>{});}
});
