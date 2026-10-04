// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Synthetic native-property renderer checks, never evidence of a real domain.
// Prepared under restricted execution: these browser cases have NOT been run yet.
import {expect,test,type Page} from '@playwright/test';
async function centerPixel(page:Page):Promise<number[]>{
  const png=await page.locator('#zone-proof canvas').screenshot();
  return page.evaluate(async encoded=>{
    const image=await createImageBitmap(await(await fetch('data:image/png;base64,'+encoded)).blob());
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const context=canvas.getContext('2d')!;context.drawImage(image,0,0);const pixel=[...context.getImageData(image.width/2,image.height/2,1,1).data];image.close();return pixel;
  },png.toString('base64'));
}
test.beforeEach(async({page})=>{
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><div id="zone-proof" style="width:640px;height:480px"></div>'}));
  await page.goto('/');
  await page.evaluate(async()=>{
    const threePath='/node_modules/.vite/deps/three.js',zonePath='/src/zone-effects.ts';
    const THREE=await import(/* @vite-ignore */threePath),module=await import(/* @vite-ignore */zonePath);
    const proof=window as any;proof.THREE=THREE;proof.scene=new THREE.Scene();proof.camera=new THREE.PerspectiveCamera(60,640/480,.1,1000);
    proof.renderer=new THREE.WebGLRenderer({antialias:false});proof.renderer.setSize(640,480);proof.renderer.toneMapping=THREE.NoToneMapping;
    document.querySelector('#zone-proof')!.appendChild(proof.renderer.domElement);
    proof.warnings=[];proof.effects=new module.NativeZoneEnvironment(proof.scene,{resolveAsset:(source:string)=>source==='atp:/actual.tga'?'/zone-strip.tga':source,onStatus:(message:string)=>proof.warnings.push(message)});
    proof.render=()=>{proof.effects.update({x:0,y:0,z:0},proof.camera);proof.renderer.render(proof.scene,proof.camera);};
    const context=proof.renderer.getContext();proof.actualWebGL2=context instanceof WebGL2RenderingContext;
  });
  expect(await page.evaluate(()=>(window as any).actualWebGL2)).toBe(true);
});
test.afterEach(async({page})=>{await page.evaluate(()=>{const proof=window as any;proof.effects.dispose();proof.object?.geometry.dispose();proof.object?.material.dispose();proof.renderer.dispose();});});
test('Native solid sky uses independently inherited small-Zone sky color',async({page})=>{
  await page.evaluate(()=>{
    const proof=window as any;proof.effects.setEntities(new Map([
      ['outer',{id:'outer',type:'Zone',dimensions:{x:100,y:100,z:100},skyboxMode:'enabled',skybox:{color:{red:255,green:0,blue:0}}}],
      ['inner',{id:'inner',type:'Zone',dimensions:{x:5,y:5,z:5},keyLightMode:'disabled',skyboxMode:'enabled',skybox:{color:{red:0,green:255,blue:0}}}],
    ]));proof.render();
  });
  const pixel=await centerPixel(page);expect(pixel[1]).toBeGreaterThan(250);expect(pixel[0]).toBeLessThan(4);expect(pixel[2]).toBeLessThan(4);
});
test('Actual GPU haze reaches native 95-percent opacity at the authored distance before display conversion',async({page})=>{
  await page.evaluate(()=>{
    const proof=window as any,THREE=proof.THREE;
    proof.effects.setEntities(new Map([['haze',{id:'haze',type:'Zone',dimensions:{x:1000,y:1000,z:1000},hazeMode:'enabled',haze:{hazeRange:120,hazeColor:{red:255,green:0,blue:0}}}]]));
    proof.object=new THREE.Mesh(new THREE.BoxGeometry(100,100,1),new THREE.MeshBasicMaterial({color:0xffffff}));proof.object.position.z=-120.5;
    proof.effects.attachMaterial(proof.object.material);proof.scene.add(proof.object);proof.render();
  });
  const pixel=await centerPixel(page);expect(pixel[0]).toBeGreaterThan(250);expect(pixel[1]).toBeGreaterThan(59);expect(pixel[1]).toBeLessThan(68);expect(Math.abs(pixel[1]-pixel[2])).toBeLessThan(2);
});
test('ATP-resolved native cube sky samples actual image faces and inverse Zone rotation',async({page})=>{
  // One texel per face lets an off-axis center pixel's bilinear footprint
  // cross a cube edge. Native sampling should remain linear; use a real
  // interior region as the color oracle rather than weaken the pixel bounds.
  const faceSize=16,bytes=Buffer.alloc(18+faceSize*faceSize*6*3);bytes[2]=2;bytes.writeUInt16LE(faceSize,12);bytes.writeUInt16LE(faceSize*6,14);bytes[16]=24;bytes[17]=32;
  const colors=[[255,0,0],[0,255,0],[255,255,0],[0,255,255],[0,0,255],[255,0,255]];
  for(let face=0;face<6;face++){const [r,g,b]=colors[face];for(let pixel=0;pixel<faceSize*faceSize;pixel++)bytes.set([b,g,r],18+(face*faceSize*faceSize+pixel)*3);}
  await page.route('**/zone-strip.tga',route=>route.fulfill({body:bytes,contentType:'image/x-tga'}));
  await page.evaluate(()=>{
    const proof=window as any;proof.camera.lookAt(1,0,0);proof.zone={id:'sky',type:'Zone',dimensions:{x:100,y:100,z:100},skyboxMode:'enabled',skybox:{url:'atp:/actual.tga',color:{red:0,green:0,blue:0}}};
    proof.effects.setEntities(new Map([['sky',proof.zone]]));proof.render();
  });
  await expect.poll(()=>page.evaluate(()=>(window as any).effects.sky.material.uniforms.nativeSkyTextured.value)).toBe(true);
  await page.evaluate(()=>(window as any).render());const before=await centerPixel(page);
  expect(before[0]).toBeGreaterThan(250);expect(before[2]).toBeLessThan(4);
  await page.evaluate(()=>{const proof=window as any;proof.zone.rotation={x:0,y:Math.SQRT1_2,z:0,w:Math.SQRT1_2};proof.effects.setEntities(new Map([['sky',proof.zone]]));proof.render();});
  const after=await centerPixel(page);expect(after[2]).toBeGreaterThan(250);expect(after[0]).toBeLessThan(4);expect(await page.evaluate(()=>(window as any).warnings)).toEqual([]);
});
