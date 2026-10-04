// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';

/** Actual World controls and pixels. The authored entities isolate lighting and
 * camera collision; this component proof is separate from the native Qt journey. */
export async function auditWorldGraphics(){
    const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0;width:320px;height:240px;';document.body.append(host);
    const warnings:string[]=[];
    const world=new BrowserWorld(host,{resolveAsset:url=>url,onPose(){},onInteract(){},onStatus(message,kind){if(kind==='warning'||kind==='error')warnings.push(message);}});
    const internal=world as unknown as {renderer:THREE.WebGLRenderer;camera:THREE.PerspectiveCamera;objects:Map<string,THREE.Group>};
    const gl=internal.renderer.getContext();
    const frame=()=>new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
    const settle=async()=>{for(let index=0;index<8;index++)await frame();};
    function pixel(){internal.renderer.render(world.scene,internal.camera);const bytes=new Uint8Array(4);gl.readPixels(Math.floor(gl.drawingBufferWidth/2),Math.floor(gl.drawingBufferHeight/2),1,1,gl.RGBA,gl.UNSIGNED_BYTE,bytes);return [...bytes];}
    try{
        for(const child of world.scene.children)if(child instanceof THREE.HemisphereLight||child instanceof THREE.DirectionalLight)child.visible=false;
        world.scene.background=new THREE.Color(0);
        world.setSpawn({x:0,y:0,z:4});
        world.setEntities([
            {id:'authored-box',type:'Box',position:{x:0,y:.65,z:0},dimensions:{x:2,y:2,z:2},color:{red:255,green:255,blue:255},collisionless:true},
            {id:'authored-local-light',type:'Light',position:{x:0,y:.65,z:3},dimensions:{x:20,y:20,z:20},intensity:40,color:{red:255,green:0,blue:0}},
        ]);
        const deadline=performance.now()+15000;
        while(performance.now()<deadline && (!internal.objects.get('authored-box')?.userData.shadersReady || world.getPerformance().compilingGraphics))await frame();
        if(!internal.objects.get('authored-box')?.userData.shadersReady)throw Error('Actual authored World geometry did not become ready');
        const before=world.graphics.snapshot(),base={width:gl.drawingBufferWidth,height:gl.drawingBufferHeight},density=internal.renderer.getPixelRatio();
        await new Promise(resolve=>setTimeout(resolve,300));await settle();const lit=pixel();
        world.graphics.apply({...before,localLights:false});await settle();const dark=pixel();
        world.graphics.apply({...before,localLights:true});await new Promise(resolve=>setTimeout(resolve,300));await settle();const relit=pixel();
        const projectionBefore=internal.camera.projectionMatrix.elements.slice();
        world.graphics.apply({...before,fieldOfView:20});const narrow=internal.camera.projectionMatrix.elements.slice();
        world.graphics.apply({...before,fieldOfView:130});const wide=internal.camera.projectionMatrix.elements.slice();
        const resolutions=[];
        for(const percent of [50,100,200]){world.graphics.apply({...before,resolutionPercent:percent});await frame();resolutions.push({percent,width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,effective:world.graphics.snapshot().resolutionPercent});}
        world.graphics.apply(before);
        world.setEntities([
            {id:'authored-floor',type:'Box',position:{x:0,y:-.25,z:0},dimensions:{x:20,y:.5,z:20},collisionless:false},
            {id:'authored-camera-wall',type:'Box',position:{x:0,y:1.5,z:1.5},dimensions:{x:6,y:4,z:.2},collisionless:false},
        ]);
        world.setSpawn({x:0,y:.85,z:0});world.setEnabled(true);world.canvas.focus();
        document.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyV',key:'v',bubbles:true}));await settle();
        const constrained=world.getSelfAvatarRenderState();
        if(!constrained.thirdPerson)throw Error('Actual visitor avatar-view control did not enable third person');
        world.graphics.apply({...before,cameraClipping:false});await settle();const free=world.getSelfAvatarRenderState();
        world.graphics.apply({...before,cameraClipping:true});await settle();const restored=world.getSelfAvatarRenderState();
        return {webgl2:gl instanceof WebGL2RenderingContext,warnings,base,density,lit,dark,relit,projectionBefore,narrow,wide,resolutions,
            camera:{constrained:constrained.cameraPosition.z,free:free.cameraPosition.z,restored:restored.cameraPosition.z},effective:world.graphics.snapshot()};
    }finally{world.dispose();internal.renderer.forceContextLoss();host.remove();}
}
