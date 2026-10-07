// SPDX-License-Identifier: Apache-2.0
// Authored actual FBX/BVH and delayed network I/O; not a native-domain proof.
import {test,expect} from '@playwright/test';
import {modelFloorFbx} from './fixtures/model-floor';

test('a genuine staged floor releases an unrelated huge-model spawn guard and jumping never re-freezes it',async({page})=>{
 let floorImageRequested=false,hugeModelRequested=false,release!:()=>void;
 const closed=new Promise<void>(resolve=>release=resolve);
 await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><body></body>'}));
 await page.route('**/support-fixture/floor.fbx',route=>route.fulfill({body:modelFloorFbx}));
 await page.route('**/support-fixture/floor.png',async route=>{floorImageRequested=true;await closed;await route.abort().catch(()=>{});});
 await page.route('**/support-fixture/unrelated.fbx',async route=>{hugeModelRequested=true;await closed;await route.abort().catch(()=>{});});
 try{
  await page.goto('/');
  await page.evaluate(async()=>{
   const modulePath='/src/world.ts';const{BrowserWorld}=await import(/* @vite-ignore */modulePath);
   document.body.innerHTML='<div id="support-test" style="width:800px;height:600px"></div>';
   const world=(window as any).world=new BrowserWorld(document.getElementById('support-test')!,{resolveAsset:(url:string)=>url,onPose(){},onInteract(){},onStatus(){}});
   world.setSpawn({x:-2,y:.85,z:-2});world.setEnabled(true);
   world.setEntities([
    {id:'floor',type:'Model',modelURL:location.origin+'/support-fixture/floor.fbx',shapeType:'static-mesh',dimensions:{x:20,y:.2,z:20}},
    {id:'unrelated',type:'Model',modelURL:location.origin+'/support-fixture/unrelated.fbx',shapeType:'static-mesh',dimensions:{x:1000,y:1000,z:1000}},
   ]);
  });
  await expect.poll(()=>floorImageRequested&&hugeModelRequested).toBe(true);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().meshColliders)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().initialSurfaceWait.verified)).toBe(true);
  const before=await page.evaluate(()=>{const world=(window as any).world;return{pose:world.getPose().position,waiting:world.getPerformance().initialSurfaceWait.waiting,visible:world.objects.get('floor').visible};});
  expect(before.waiting).toBe(false);expect(before.visible).toBe(false);
  await page.keyboard.down('KeyW');
  try{
   await expect.poll(()=>page.evaluate(()=>(window as any).world.getPose().position.z)).toBeLessThan(before.pose.z-.5);
   await page.keyboard.down('Space');
   try{await expect.poll(()=>page.evaluate(()=>(window as any).world.getPose().position.y)).toBeGreaterThan(1.1);}
   finally{await page.keyboard.up('Space');}
   expect(await page.evaluate(()=>(window as any).world.getPerformance().initialSurfaceWait.waiting)).toBe(false);
  }finally{await page.keyboard.up('KeyW');}
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPose().position.y)).toBeCloseTo(.85,3);

  // A real reposition starts a new bounded episode. Actual loaded triangles
  // do not pretend an airborne pose is supported merely because bounds overlap.
  await page.evaluate(()=>(window as any).world.setSpawn({x:-2,y:1.2,z:-2}));
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().initialSurfaceWait.waiting)).toBe(true);
  await page.keyboard.down('KeyW');try{
   await page.waitForTimeout(250);
   const waiting=await page.evaluate(()=>(window as any).world.getPose().position);
   expect(waiting.y).toBe(1.2);expect(waiting.z).toBe(-2);
  }finally{await page.keyboard.up('KeyW');}
  await page.evaluate(()=>(window as any).world.setSpawn({x:-2,y:.85,z:-2}));
  await expect.poll(()=>page.evaluate(()=>(window as any).world.getPerformance().initialSurfaceWait.verified)).toBe(true);
  expect(await page.evaluate(()=>(window as any).world.getPerformance().initialSurfaceWait.waiting)).toBe(false);
 }finally{
  await page.evaluate(()=>(window as any).world?.dispose()).catch(()=>{});release();
 }
});
