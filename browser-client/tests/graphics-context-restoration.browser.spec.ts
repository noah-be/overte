// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import type * as THREE from 'three';

// Deliberate owned test stimulus, separate from spontaneous hosted loss.
// WEBGL_lose_context restore must occur after the loss event has fully completed:
// https://registry.khronos.org/webgl/extensions/WEBGL_lose_context/
test('owned actual World restores retained graphics scan controller and geometry after genuine context loss',async({page})=>{
    await page.goto('/');
    const result=await page.evaluate(async()=>{
        const worldPath='/src/world.ts',scanPath='/src/graphics-environment-scan.ts';
        const {BrowserWorld}=await import(worldPath) as typeof import('../src/world');
        const {GraphicsEnvironmentScan}=await import(scanPath) as typeof import('../src/graphics-environment-scan');
        const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0;width:320px;height:240px;';document.body.append(host);
        const world=new BrowserWorld(host,{resolveAsset:url=>url,onPose(){},onInteract(){},onStatus(){}});
        const internal=world as unknown as {renderer:THREE.WebGLRenderer;camera:THREE.PerspectiveCamera;objects:Map<string,THREE.Group>;enabled:boolean};
        const gl=internal.renderer.getContext(),extension=gl.getExtension('WEBGL_lose_context');
        let applyCalls=0,currentOwner=true;const frames=world.getGraphicsScanFrames();
        const scan=new GraphicsEnvironmentScan({frames,document,current:()=>currentOwner,
            presentationVisible:()=>world.graphicsScanPresentationVisible(),settings:()=>world.graphics.snapshot(),capabilities:()=>world.getGraphicsEnvironment(),
            applyResolution:async percent=>{applyCalls++;const settings={...world.graphics.snapshot(),resolutionPercent:percent};world.graphics.apply(settings);return world.graphics.snapshot();}});
        const listeners:Array<()=>void>=[];
        const eventWait=(kind:'webglcontextlost'|'webglcontextrestored')=>new Promise<{trusted:boolean;prevented:boolean}>( (resolve,reject)=>{
            const finish=()=>{clearTimeout(timer);world.canvas.removeEventListener(kind,received);};
            const received=(event:Event)=>{finish();if(event.target!==world.canvas||event.isTrusted!==true){reject(Error('Unowned or untrusted context event'));return;}resolve({trusted:event.isTrusted,prevented:event.defaultPrevented});};
            const timer=setTimeout(()=>{finish();reject(Error('Owned context event deadline'));},5000);
            world.canvas.addEventListener(kind,received);listeners.push(finish);
        });
        const frame=()=>new Promise<void>((resolve,reject)=>{let id=0;const timer=setTimeout(()=>{cancelAnimationFrame(id);reject(Error('Owned visible-frame deadline'));},1000);id=requestAnimationFrame(()=>{clearTimeout(timer);resolve();});});
        const pixel=()=>{internal.renderer.render(world.scene,internal.camera);const value=new Uint8Array(4);gl.readPixels(Math.floor(gl.drawingBufferWidth/2),Math.floor(gl.drawingBufferHeight/2),1,1,gl.RGBA,gl.UNSIGNED_BYTE,value);return [...value];};
        try{
            if(!extension)throw Error('Required actual WEBGL_lose_context extension unavailable');
            // Black owned background makes the unchanged nonblack center oracle discriminate authored geometry.
            const background=world.scene.background as THREE.Color|null;
            if(!background||background.isColor!==true)throw Error('Owned authored background is not a Color');
            background.setRGB(0,0,0);if(background.getHex()!==0)throw Error('Owned authored background is not black');
            world.setSpawn({x:0,y:0,z:4});world.setEntities([
                {id:'owned-context-floor',type:'Box',position:{x:0,y:-.25,z:0},dimensions:{x:20,y:.5,z:20},collisionless:false},
                {id:'owned-context-box',type:'Box',position:{x:0,y:1.4,z:0},dimensions:{x:2,y:2,z:2},color:{red:255,green:255,blue:255},collisionless:true},
            ]);world.setEnabled(true);
            const deadline=performance.now()+15000;
            while(performance.now()<deadline&&(!internal.objects.get('owned-context-box')?.userData.shadersReady||world.getPerformance().compilingGraphics))await frame();
            const root=internal.objects.get('owned-context-box');if(!root?.userData.shadersReady)throw Error('Owned actual geometry readiness deadline');
            let mesh:THREE.Mesh|undefined;root.traverse(object=>{if(!mesh&&(object as THREE.Mesh).isMesh)mesh=object as THREE.Mesh;});
            if(!mesh)throw Error('Owned authored box mesh missing');const geometry=mesh.geometry,positions=geometry.getAttribute('position').array;
            const settingsBefore=world.graphics.snapshot(),pixelsBefore=pixel(),before=await scan.scan();
            if(before.status!=='complete')throw Error('Original actual visible World scan did not complete');
            const reportEpoch=(scan as unknown as {resultContextEpoch:number}).resultContextEpoch;
            const lostWait=eventWait('webglcontextlost');extension.loseContext();const lostEvent=await lostWait;
            const lostFrames=world.getPerformance().renderedFrames;for(let i=0;i<3;i++)await frame();
            const lostStable=world.getPerformance().renderedFrames===lostFrames,lostApply=await scan.applyOptionalResolution(),lostScan=await scan.scan(),lostEpoch=frames.contextEpoch;
            // One later task guarantees the complete loss dispatch precedes our sole restore stimulus.
            await new Promise<void>(resolve=>setTimeout(resolve,0));
            const restoredWait=eventWait('webglcontextrestored');extension.restoreContext();const restoredEvent=await restoredWait;
            const restoredEpoch=frames.contextEpoch,staleApply=await scan.applyOptionalResolution();
            const after=await scan.scan();if(after.status!=='complete')throw Error('Restored same-controller actual World scan did not complete');
            const pixelsAfter=pixel(),retained=internal.objects.get('owned-context-box')===root&&mesh.geometry===geometry&&geometry.getAttribute('position').array===positions;
            currentOwner=false;const revoked=await scan.scan();
            return {lostEvent,restoredEvent,lostStable,lostApply:lostApply.accepted,lostScan:lostScan.status,lostEpoch:lostEpoch??null,
                restoredEpoch,reportEpoch,staleApply:staleApply.accepted,sameFacade:world.getGraphicsScanFrames()===frames,before:before.status,after:after.status,
                beforeIntervals:before.report.frameIntervals,afterIntervals:after.report.frameIntervals,resumedFrames:world.getPerformance().renderedFrames>lostFrames,
                retained,pixelsBefore,pixelsAfter,settingsBefore,settingsAfter:world.graphics.snapshot(),applyCalls,enabled:internal.enabled,revoked:revoked.status};
        }finally{for(const remove of listeners)remove();scan.dispose();world.dispose();internal.renderer.forceContextLoss();host.remove();}
    });
    expect(result.lostEvent).toEqual({trusted:true,prevented:true});expect(result.restoredEvent.trusted).toBe(true);
    expect(result.lostStable).toBe(true);expect(result.lostApply).toBe(false);expect(result.lostScan).toBe('refused');expect(result.lostEpoch).toBeNull();
    expect(result.restoredEpoch).toBe(result.reportEpoch+1);expect(result.staleApply).toBe(false);expect(result.applyCalls).toBe(0);
    expect(result.sameFacade).toBe(true);expect(result.before).toBe('complete');expect(result.after).toBe('complete');
    expect(result.beforeIntervals).toBeGreaterThanOrEqual(12);expect(result.afterIntervals).toBeGreaterThanOrEqual(12);expect(result.resumedFrames).toBe(true);
    expect(result.retained).toBe(true);expect(Math.max(...result.pixelsBefore.slice(0,3))).toBeGreaterThan(10);expect(result.pixelsAfter).toEqual(result.pixelsBefore);
    expect(result.settingsAfter).toEqual(result.settingsBefore);expect(result.enabled).toBe(true);expect(result.revoked).toBe('refused');
});
