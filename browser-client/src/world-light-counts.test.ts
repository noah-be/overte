// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {Group,PointLight,Scene,SpotLight} from 'three';
import {BrowserWorld} from './world';
import type {Entity} from './world-data';
function fixture(){
 const world=Object.create(BrowserWorld.prototype) as BrowserWorld;
 const state=world as unknown as {localLights:Set<PointLight|SpotLight>;localLightsEnabled:boolean;pointSlots:PointLight[];spotSlots:SpotLight[];populateEntity:(entity:Entity,root:Group)=>Promise<void>;[key:string]:unknown};
 Object.assign(state,{localLights:new Set(),localLightsEnabled:true,pointSlots:Array.from({length:8},()=>new PointLight(0xffffff,0)),spotSlots:Array.from({length:8},()=>new SpotLight(0xffffff,0)),entities:new Map(),signatures:new Map(),objects:new Map(),scene:new Scene(),meshCollisions:new Map(),modelGeometry:new WeakMap(),modelReaders:new WeakMap(),modelBatches:new WeakMap(),colliders:[],pendingModelColliders:[]});
 return {world,state};
}
test('actual native entity population counts hidden point and spot sources without changing the sixteen renderer slots',async()=>{
 const {world,state}=fixture(),a=new Group(),b=new Group();
 await state.populateEntity({id:'point',type:'Light'},a);
 await state.populateEntity({id:'spot',type:'Light',isSpotlight:true},b);
 assert.equal(state.localLights.size,2);assert([...state.localLights].every(light=>!light.visible));
 assert.deepEqual(world.getLocalLightStatistics(),{enabled:true,sourcePointLights:1,sourceSpotLights:1,pointSlotCapacity:8,spotSlotCapacity:8,visiblePointSlots:8,visibleSpotSlots:8,contributingPointSlots:0,contributingSpotSlots:0});
});
test('actual source deletion removes just its source count and does not infer a shader capacity change',async()=>{
 const {world,state}=fixture(),a=new Group(),b=new Group();
 for(const [id,root,isSpotlight]of [['point',a,false],['spot',b,true]] as const){
  const entity={id,type:'Light',isSpotlight} satisfies Entity;
  await state.populateEntity(entity,root);(state.objects as Map<string,Group>).set(id,root);(state.entities as Map<string,Entity>).set(id,entity);(state.scene as Scene).add(root);
 }
 world.removeEntities(['point']);const counts=world.getLocalLightStatistics();
 assert.equal(counts.sourcePointLights,0);assert.equal(counts.sourceSpotLights,1);assert.equal(counts.pointSlotCapacity,8);assert.equal(counts.spotSlotCapacity,8);
 world.removeEntities(['spot']);assert.equal(world.getLocalLightStatistics().sourceSpotLights,0);
});
test('disabled local contributions remain distinct from instantiated source totals and visible slot capacities',()=>{
 const {world,state}=fixture();state.localLights.add(new PointLight(0xffffff,4));state.localLights.add(new SpotLight(0xffffff,3));
 state.pointSlots[0].intensity=4;state.spotSlots[0].intensity=3;
 assert.equal(world.getLocalLightStatistics().contributingPointSlots,1);assert.equal(world.getLocalLightStatistics().contributingSpotSlots,1);
 state.localLightsEnabled=false;for(const light of [...state.pointSlots,...state.spotSlots])light.intensity=0;
 const counts=world.getLocalLightStatistics();assert.equal(counts.enabled,false);assert.equal(counts.sourcePointLights,1);assert.equal(counts.sourceSpotLights,1);assert.equal(counts.contributingPointSlots,0);assert.equal(counts.contributingSpotSlots,0);assert.equal(counts.visiblePointSlots,8);
});
test('aggregate getter invokes no renderer, model traversal or light matrix read and exposes no borrowed references',()=>{
 const {world,state}=fixture(),light=new PointLight(0xabcdee,1);state.localLights.add(light);
 light.getWorldPosition=()=>{throw Error('No light transform read');};
 Object.defineProperties(world,{renderer:{get(){throw Error('No renderer read');}},objects:{get(){throw Error('No model traversal');}}});
 const before={visible:light.visible,intensity:light.intensity,color:light.color.getHex(),matrix:light.matrix.elements.slice()},first=world.getLocalLightStatistics();first.sourcePointLights=100;first.pointSlotCapacity=0;
 assert.equal(world.getLocalLightStatistics().sourcePointLights,1);assert.equal(world.getLocalLightStatistics().pointSlotCapacity,8);
 assert.deepEqual({visible:light.visible,intensity:light.intensity,color:light.color.getHex(),matrix:light.matrix.elements.slice()},before);
 assert(Object.values(world.getLocalLightStatistics()).every(value=>typeof value==='boolean'||typeof value==='number'));
});
