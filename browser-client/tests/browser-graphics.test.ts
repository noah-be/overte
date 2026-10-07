// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {DEFAULT_BROWSER_GRAPHICS,validateBrowserGraphics,validateBrowserGraphicsChange,validateBrowserGraphicsRequest,validateBrowserGraphicsResult} from '../shared/browser-graphics.mjs';
import {BrowserGraphicsController} from '../src/browser-graphics-controller';
import {WorldGraphicsTarget} from '../src/browser-graphics-target';
test('graphics DTO bounds exact supported controls and returns independent plain clones',()=>{
    for(const fieldOfView of [20,130])for(const resolutionPercent of [10,200])assert.deepEqual(validateBrowserGraphics({...DEFAULT_BROWSER_GRAPHICS,fieldOfView,resolutionPercent}),{...DEFAULT_BROWSER_GRAPHICS,fieldOfView,resolutionPercent});
    for(const value of [null,[],{}, {...DEFAULT_BROWSER_GRAPHICS,version:2},{...DEFAULT_BROWSER_GRAPHICS,fieldOfView:NaN},{...DEFAULT_BROWSER_GRAPHICS,resolutionPercent:25},{...DEFAULT_BROWSER_GRAPHICS,localLights:1},{...DEFAULT_BROWSER_GRAPHICS,privateAccount:'secret'}])assert.throws(()=>validateBrowserGraphics(value));
    const source={...DEFAULT_BROWSER_GRAPHICS},result=validateBrowserGraphics(source);result.fieldOfView=80;assert.equal(source.fieldOfView,70);assert.equal(Object.getPrototypeOf(result),Object.prototype);
    assert.throws(()=>validateBrowserGraphicsChange('bloom',true));assert.throws(()=>validateBrowserGraphicsChange('resolutionPercent',201));
});
test('request/result correlation rejects unsupported schema, values and excessive messages',()=>{
    assert.deepEqual(validateBrowserGraphicsRequest({schemaVersion:1,requestId:2,operation:'change',field:'localLights',value:false}),{schemaVersion:1,requestId:2,operation:'change',field:'localLights',value:false});
    for(const value of [{schemaVersion:2,requestId:1,operation:'request'},{schemaVersion:1,requestId:0,operation:'request'},{schemaVersion:1,requestId:1,operation:'change',field:'resolutionPercent',value:'100'},{schemaVersion:1,requestId:1,operation:'request',value:1}])assert.throws(()=>validateBrowserGraphicsRequest(value));
    assert.throws(()=>validateBrowserGraphicsResult({schemaVersion:1,requestId:1,accepted:true,settings:DEFAULT_BROWSER_GRAPHICS,message:'x'.repeat(513)}));
});
function fixture(){
    const camera=new THREE.PerspectiveCamera(70,16/9,.05,10000);let ratio=1.5,lights=true,clipping=true,resizes=0;
    const target=new WorldGraphicsTarget({camera,renderer:{getPixelRatio:()=>ratio,setPixelRatio:(value:number)=>{ratio=value;}} as unknown as Pick<THREE.WebGLRenderer,'getPixelRatio'|'setPixelRatio'>,resize:()=>resizes++,localLights:()=>lights,setLocalLights:value=>{lights=value;},cameraClipping:()=>clipping,setCameraClipping:value=>{clipping=value;}});
    return {camera,target,get ratio(){return ratio;},get resizes(){return resizes;}};
}
test('actual Three camera projection and resolution percentage change while base density and inverse clipping stay independent',()=>{
    const {camera,target}=fixture(),before=camera.projectionMatrix.clone();target.apply({...DEFAULT_BROWSER_GRAPHICS,fieldOfView:100,resolutionPercent:50,localLights:false,cameraClipping:false});
    assert.equal(camera.fov,100);assert.notDeepEqual(camera.projectionMatrix.elements,before.elements);assert.equal(target.snapshot().resolutionPercent,50);assert.equal(target.snapshot().cameraClipping,false);
    target.apply({...DEFAULT_BROWSER_GRAPHICS,resolutionPercent:200});assert.equal(target.snapshot().resolutionPercent,200);assert.equal(target.snapshot().fieldOfView,70);
});
test('effective ACK is read from the target and revoked/stale/replayed requests cannot apply or persist',()=>{
    const {target}=fixture();let current=true;const saved:unknown[]=[];
    const controller=new BrowserGraphicsController(target,revision=>current&&revision===3,value=>saved.push(value));
    assert.equal(controller.receive({schemaVersion:1,requestId:1,operation:'request'},3),undefined);
    controller.setAuthority(3,true);const initial=controller.receive({schemaVersion:1,requestId:1,operation:'request'},3);assert.deepEqual(initial?.settings,target.snapshot());
    assert.equal(controller.receive({schemaVersion:1,requestId:1,operation:'change',field:'fieldOfView',value:90},3),undefined);
    const accepted=controller.receive({schemaVersion:1,requestId:2,operation:'change',field:'fieldOfView',value:90},3);assert.equal(accepted?.accepted,true);assert.equal(accepted?.settings.fieldOfView,90);assert.equal(saved.length,1);
    current=false;assert.equal(controller.receive({schemaVersion:1,requestId:3,operation:'change',field:'fieldOfView',value:100},3),undefined);assert.equal(target.snapshot().fieldOfView,90);
    controller.setAuthority(4,false);assert.equal(controller.receive({schemaVersion:1,requestId:4,operation:'request'},3),undefined);controller.close();current=true;controller.setAuthority(3,true);assert.equal(controller.receive({schemaVersion:1,requestId:4,operation:'request'},3),undefined);
});
test('partial apply failure ACK remains truthful and authority changes during target work suppress every result and persistence',()=>{
    let state={...DEFAULT_BROWSER_GRAPHICS},active=true,saved=0;
    const controller=new BrowserGraphicsController({snapshot:()=>({...state}),apply:next=>{state={...next,localLights:true};throw Error('private device detail');}},()=>active,()=>saved++);controller.setAuthority(1,true);
    const failure=controller.receive({schemaVersion:1,requestId:1,operation:'change',field:'localLights',value:false},1);assert.equal(failure?.accepted,false);assert.equal(failure?.settings.localLights,true);assert.equal(saved,0);assert.equal(failure?.message?.includes('private device'),false);
    const revoked=new BrowserGraphicsController({snapshot:()=>({...state}),apply:next=>{state=next;active=false;}},()=>active,()=>saved++);revoked.setAuthority(1,true);assert.equal(revoked.receive({schemaVersion:1,requestId:1,operation:'change',field:'fieldOfView',value:90},1),undefined);assert.equal(saved,0);
});

test('persistence observer failure preserves an honest effective rendering ACK',()=>{
    const {target}=fixture();const controller=new BrowserGraphicsController(target,()=>true,()=>{throw Error('Quota exceeded');});controller.setAuthority(1,true);
    const result=controller.receive({schemaVersion:1,requestId:1,operation:'change',field:'fieldOfView',value:80},1);assert.equal(result?.accepted,true);assert.equal(result?.settings.fieldOfView,80);assert.match(result?.message||'',/could not save/);
});

test('a silently ignored renderer control is refused by its actual effective snapshot',()=>{
    const controller=new BrowserGraphicsController({snapshot:()=>({...DEFAULT_BROWSER_GRAPHICS}),apply:()=>{}},()=>true);controller.setAuthority(1,true);
    const result=controller.receive({schemaVersion:1,requestId:1,operation:'change',field:'localLights',value:false},1);assert.equal(result?.accepted,false);assert.equal(result?.settings.localLights,true);
});

test('allocation limits reject oversized resolution before changing camera, density, switches or size',()=>{
    const camera=new THREE.PerspectiveCamera(70,1,.05,10000);let ratio=2,changes=0;
    const target=new WorldGraphicsTarget({camera,renderer:{getPixelRatio:()=>ratio,setPixelRatio:value=>{ratio=value;changes++;}},
        validatePixelRatio:value=>{if(value>2)throw Error('Framebuffer limit');},resize:()=>changes++,
        localLights:()=>true,setLocalLights:()=>changes++,cameraClipping:()=>true,setCameraClipping:()=>changes++});
    const before=camera.projectionMatrix.elements.slice();
    assert.throws(()=>target.apply({...DEFAULT_BROWSER_GRAPHICS,fieldOfView:120,resolutionPercent:200}),/Framebuffer limit/);
    assert.equal(camera.fov,70);assert.deepEqual(camera.projectionMatrix.elements,before);assert.equal(ratio,2);assert.equal(changes,0);
});
