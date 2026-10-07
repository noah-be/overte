// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';

test('actual World disposal revokes owned readers, releases graph references and is idempotent',t=>{
 const documentBefore=Object.getOwnPropertyDescriptor(globalThis,'document');
 const cancelBefore=Object.getOwnPropertyDescriptor(globalThis,'cancelAnimationFrame');
 const calls:string[]=[];
 Object.defineProperty(globalThis,'document',{configurable:true,value:{pointerLockElement:null}});
 Object.defineProperty(globalThis,'cancelAnimationFrame',{configurable:true,value:()=>calls.push('frame')});
 t.after(()=>{for(const [key,before]of [['document',documentBefore],['cancelAnimationFrame',cancelBefore]] as const){if(before)Object.defineProperty(globalThis,key,before);else Reflect.deleteProperty(globalThis,key);}});
 const world:any=Object.create(BrowserWorld.prototype),root=new THREE.Group(),avatar=new THREE.Group(),self=new THREE.Group(),scene=new THREE.Scene();
 const geometry=new THREE.BoxGeometry(),material=new THREE.MeshBasicMaterial(),map=new THREE.Texture();material.map=map;root.add(new THREE.Mesh(geometry,material));scene.add(root,avatar,self);
 for(const [name,value]of [['geometry',geometry],['material',material],['texture',map]] as const)value.addEventListener('dispose',()=>calls.push(name));
 const reader=new AbortController(),abort=new AbortController(),modelReaders=new WeakMap([[root,reader]]);
 reader.signal.addEventListener('abort',()=>calls.push('reader'));
 Object.assign(world,{disposed:false,enabled:true,frame:1,abort,resizeObserver:{disconnect(){calls.push('resize');}},modelReaders,loadManagers:new Set([{abort(){calls.push('manager');}}]),canvas:{remove(){calls.push('canvas');}},modelBatches:new Map(),modelGeometry:new WeakMap([[root,{revoke(){calls.push('geometry-owner');}}]]),objects:new Map([['own',root]]),avatars:new Map([['participant',avatar]]),self,scene,entities:new Map([['own',{id:'own',type:'Model'}]]),signatures:new Map([['own','private-source-signature']]),localLights:new Set([new THREE.PointLight()]),colliders:[{}],pendingModelColliders:[{}],avatarModels:new Map([[avatar,{}]]),meshCollisions:new Map([['own',{value:{dispose(){calls.push('collision');}}}]]),gpuTiming:{dispose(){calls.push('gpu-timing');}},renderer:{dispose(){calls.push('renderer');}}});
 world.dispose();
 assert.equal(world.disposed,true);assert.equal(world.enabled,false);assert.equal(abort.signal.aborted,true);assert.equal(reader.signal.aborted,true);
 for(const key of ['objects','avatars','entities','signatures','localLights','avatarModels','meshCollisions','loadManagers'])assert.equal(world[key].size,0,key);
 assert.equal(scene.children.length,0);assert.equal(root.parent,null);assert.equal(avatar.parent,null);assert.equal(self.parent,null);assert.deepEqual(world.colliders,[]);assert.deepEqual(world.pendingModelColliders,[]);
 assert(calls.indexOf('reader')<calls.indexOf('geometry-owner'));assert(calls.indexOf('geometry-owner')<calls.indexOf('geometry'));assert(calls.indexOf('geometry')<calls.indexOf('renderer'));
 for(const name of ['geometry','material','texture','collision','renderer','canvas'])assert.equal(calls.filter(value=>value===name).length,1,name);
 const first=[...calls];world.dispose();assert.deepEqual(calls,first);
});
