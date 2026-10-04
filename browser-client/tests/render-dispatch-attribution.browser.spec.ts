// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {expect,test} from '@playwright/test';
test('actual World dispatch attribution preserves exact rendered pixels and program-call boundaries',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/');
 const report=await page.evaluate(async()=>{
  const path='/tests/render-cpu-breakdown-fixture.ts';const {THREE,BrowserWorld}=await import(/* @vite-ignore */path);
  const cases:any[]=[];
  for(const enabled of [false,true]){
   const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;width:256px;height:192px';document.body.append(host);let world:any;
   try{
    const warnings:string[]=[];world=new BrowserWorld(host,{renderCpuTiming:true,renderDispatchAttribution:enabled,resolveAsset(){throw Error('No external assets are authorized by this fixture');},onPose(){},onInteract(){},onStatus:(text:string,kind?:string)=>{if(kind==='warning'||kind==='error')warnings.push(text);}});
    cancelAnimationFrame(world.frame);world.setInputEnabled(false);world.setEnabled(false);world.setPresentationEnabled(false);world.renderer.setPixelRatio(1);world.renderer.setSize(256,192);
    const gl=world.renderer.getContext();if(!(gl instanceof WebGL2RenderingContext))throw Error('Actual WebGL2 is required');
    world.setSpawn({x:0,y:0,z:3});world.camera.aspect=256/192;world.camera.updateProjectionMatrix();
    world.upsertEntities([{id:'box',type:'Box',position:{x:-.55,y:.65,z:0},dimensions:{x:.8,y:.8,z:.8},color:{red:255,green:80,blue:20}},{id:'sphere',type:'Sphere',position:{x:.55,y:.65,z:0},dimensions:{x:.8,y:.8,z:.8},color:{red:20,green:80,blue:255}}]);
    const deadline=performance.now()+15000;while(['box','sphere'].some(id=>world.objects.get(id)?.userData.shadersReady!==true)){if(performance.now()>deadline)throw Error('Actual fixture graphics did not become ready');await new Promise(resolve=>setTimeout(resolve,10));}
    const programBefore=gl.useProgram;const before={scene:world.scene.updateMatrixWorld,camera:world.camera.updateMatrixWorld,hook:world.scene.onBeforeRender,draw:world.renderer.renderBufferDirect};
    const matrices=()=>['box','sphere'].map(id=>world.objects.get(id).matrixWorld.elements.slice());
    world.setPresentationEnabled(true);for(let at=0;at<9;at++){world.animate(performance.now()+at*20);cancelAnimationFrame(world.frame);}world.setPresentationEnabled(false);
    const pixels=new Uint8Array(256*192*4);gl.readPixels(0,0,256,192,gl.RGBA,gl.UNSIGNED_BYTE,pixels);if(gl.isContextLost()||gl.getError()!==gl.NO_ERROR)throw Error('Actual diagnostic comparison graphics failed');
    const pixelHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))).map(byte=>byte.toString(16).padStart(2,'0')).join('');
    const center=(x:number)=>{const p=new THREE.Vector3(x,.65,0).project(world.camera),offset=(Math.floor((p.y*.5+.5)*192)*256+Math.floor((p.x*.5+.5)*256))*4;return Array.from(pixels.slice(offset,offset+4));};
    const performanceReport=world.getPerformance();cases.push({enabled,pixelHash,programIdentityUnchanged:gl.useProgram===programBefore,centers:[center(-.55),center(.55)],matrices:matrices(),methodIdentitiesUnchanged:before.scene===world.scene.updateMatrixWorld&&before.camera===world.camera.updateMatrixWorld&&before.hook===world.scene.onBeforeRender&&before.draw===world.renderer.renderBufferDirect,matrixAutoUpdates:[world.scene.matrixWorldAutoUpdate,...['box','sphere'].map(id=>world.objects.get(id).matrixAutoUpdate)],renderCpuTiming:performanceReport.renderCpuTiming,drawCalls:performanceReport.drawCalls,warnings});
   }finally{try{world?.dispose();}finally{host.remove();}}
  }
  return cases;
 });
 await testInfo.attach('actual-world-dispatch-attribution-boundaries',{contentType:'application/json',body:JSON.stringify({schemaVersion:1,browser:page.context().browser()?.version(),project:testInfo.project.name,report,errors})});
 expect(errors).toEqual([]);expect(report[0].warnings).toEqual([]);expect(report[1].warnings).toEqual([]);expect(report[0].renderCpuTiming.dispatchAttribution.enabled).toBe(false);expect(report[1].pixelHash).toBe(report[0].pixelHash);expect(report[1].centers).toEqual(report[0].centers);
 expect(report[1].centers[0][0]).toBeGreaterThan(report[1].centers[0][2]*2);expect(report[1].centers[1][2]).toBeGreaterThan(report[1].centers[1][0]*2);
 expect(report[1].matrices).toEqual(report[0].matrices);expect(report.every((value:any)=>value.methodIdentitiesUnchanged)).toBe(true);expect(report[1].matrixAutoUpdates).toEqual([true,true,true]);expect(report[1].drawCalls).toBe(report[0].drawCalls);
 expect(report.every((value:any)=>value.programIdentityUnchanged)).toBe(true);
 const attribution=report[1].renderCpuTiming.dispatchAttribution,population=attribution.populations.modelJobsIdle;expect(attribution.enabled).toBe(true);expect(population.completeSamples).toBeGreaterThan(0);expect(population.censoredSamples).toBe(0);expect(population.completeTotals.drawsObserved).toBeGreaterThanOrEqual(2);expect(population.completeTotals.materialTransitions).toBeGreaterThan(0);expect(population.completeTotals.geometryTransitions).toBeGreaterThan(0);expect(population.completeTotals.owners).toBeGreaterThanOrEqual(2);expect(population.completeTotals.drawsWithObservedProgram+population.completeTotals.drawsWithoutObservedProgram).toBe(population.completeTotals.drawsObserved);
 const diagnostics=report[1].renderCpuTiming;expect(diagnostics.completedFrames).toBeGreaterThan(0);expect(diagnostics.invalidFrames).toBe(0);expect(diagnostics.failedRenders).toBe(0);expect(diagnostics.foreignHookChanges).toBe(0);expect(diagnostics.installationRefusals).toBe(0);expect(diagnostics.active).toBe(false);
 const p=diagnostics.populations.modelJobsIdle;expect(p.samples).toBeGreaterThan(0);expect(p.drawDispatchCalls.meanCalls).toBeGreaterThanOrEqual(2);
 const assigned=p.phases.sceneMatrices.totalMs+p.phases.cameraMatrices.totalMs+p.phases.sceneBeforeHook.totalMs+p.phases.drawDispatch.totalMs+p.phases.renderRemainder.totalMs;expect(Math.abs(assigned-p.phases.total.totalMs)).toBeLessThan(1e-8);
});
