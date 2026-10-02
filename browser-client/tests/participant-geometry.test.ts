// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { BrowserWorld } from '../src/world';
import { inspectParticipantGeometry } from '../src/participant-geometry';
import { createPeopleGeometryProof } from './integration/tablet-people-geometry.mjs';
const proof=createPeopleGeometryProof();
const all=[{id:'self',displayName:'Self',position:{x:0,y:1,z:0}},
 {id:'author',displayName:'Author',position:{x:3,y:1,z:3}},
 {id:'peer',displayName:'Peer',position:{x:0,y:1,z:-3}}];
function fixture(t:test.TestContext){
 const previous=globalThis.document;
 Object.assign(globalThis,{document:{createElement(){return{width:0,height:0,getContext(){return{fillRect(){},fillText(){}};}};}}});
 t.after(()=>{Object.assign(globalThis,{document:previous});});
 const world:any=Object.create(BrowserWorld.prototype);
 Object.assign(world,{scene:new THREE.Scene(),avatars:new Map(),avatarModels:new Map(),localAvatarID:'self',shaderWarmup:false,
  disposed:false,options:{onStatus(){throw Error('Unexpected status');}},prepareGraphics:async(root:THREE.Group)=>{root.userData.shadersReady=true;}});
 world.self=world.makeAvatar('Self',0x64c5ff);world.scene.add(world.self);
 const inspect=()=>world.getParticipantGeometry();
 return{world,inspect};
}
test('actual World setAvatars creates usable fallback geometry with zero rigs, removes/disposes peer and restores a fresh root',async t=>{
 const{world,inspect}=fixture(t);world.setAvatars(all);await Promise.resolve();
 const before={count:2,ids:all.map(v=>v.id),geometry:inspect()};
 assert.equal(before.geometry.rigRoots,0);assert.equal(before.geometry.fallbackRoots,2);
 assert.deepEqual(before.geometry.rows.map((row:any)=>row.geometryMeshes),[3,3]);
 assert(proof.ready(all,'self',before.geometry,2));
 const removed=world.avatars.get('peer') as THREE.Group;
 let geometries=0,materials=0;removed.traverse(node=>{if(node instanceof THREE.Mesh){node.geometry.addEventListener('dispose',()=>geometries++);for(const material of Array.isArray(node.material)?node.material:[node.material])material.addEventListener('dispose',()=>materials++);}});
 const remaining=all.filter(value=>value.id!=='peer');world.setAvatars(remaining);
 assert.equal(removed.parent,null);assert.equal(world.avatars.has('peer'),false);
 assert.equal(geometries,4);assert.equal(materials,4);
 const ignored={snapshot:remaining,self:'self',batches:Array.from({length:3},()=>({ids:remaining.map(v=>v.id)})),count:1,render:inspect(),before,peer:'peer'};
 assert(proof.ignored(ignored));
 world.setAvatars(all);await Promise.resolve();assert(proof.restored({snapshot:all,self:'self',count:2,render:inspect(),before,peer:'peer'}));
 assert.notEqual(world.avatars.get('peer'),removed);
 world.setAvatars([]);
});
test('wrong peer, raw-only count removal, orphan scene geometry, hidden body and missing three batches refuse',async t=>{
 const{world,inspect}=fixture(t);world.setAvatars(all);await Promise.resolve();
 const before={count:2,ids:all.map(v=>v.id),geometry:inspect()},peer=world.avatars.get('peer');
 const remaining=all.filter(value=>value.id!=='peer');
 const value={snapshot:remaining,self:'self',batches:Array.from({length:3},()=>({ids:remaining.map(v=>v.id)})),count:1,render:inspect(),before,peer:'peer'};
 assert.equal(proof.ignored(value),false);
 world.setAvatars(all.filter(value=>value.id!=='author'));assert.equal(proof.ignored({...value,render:inspect()}),false);
 world.setAvatars(all);await Promise.resolve();value.before={...before,geometry:inspect()};world.setAvatars(remaining);world.scene.add(peer);
 assert.equal(inspect().orphanRoots,1);assert.equal(proof.ignored({...value,render:inspect()}),false);
 world.scene.remove(peer);const render=inspect();assert(proof.ignored({...value,render}));
 assert.equal(proof.ignored({...value,render,batches:value.batches.slice(0,2)}),false);
 world.avatars.get('author').visible=false;assert.equal(proof.ignored({...value,render:inspect()}),false);
 world.setAvatars([]);
});
test('missing scene membership, label-only geometry, duplicate ownership and graph censoring do not qualify',async t=>{
 const{world,inspect}=fixture(t);world.setAvatars(all);await Promise.resolve();
 const peer=world.avatars.get('peer') as THREE.Group;world.scene.remove(peer);
 assert.equal(proof.ready(all,'self',inspect(),2),false);world.scene.add(peer);
 for(const node of peer.children)if(node!==peer.userData.avatarLabel)node.visible=false;
 assert.equal(inspect().rows.find((row:any)=>row.id==='peer').geometryMeshes,0);
 assert.equal(proof.ready(all,'self',inspect(),2),false);
 world.avatars.set('duplicate',peer);assert.equal(inspect().censored,true);world.avatars.delete('duplicate');
 peer.children.push(peer);assert.equal(inspect().censored,true);peer.children.pop();
 world.setAvatars([]);
});
test('removed pending fallback cannot be resurrected by the original shader completion callback',async t=>{
 const{world,inspect}=fixture(t);let finish!:()=>void;
 world.prepareGraphics=(root:THREE.Group)=>{root.visible=false;return new Promise<void>(resolve=>{finish=()=>{root.userData.shadersReady=true;resolve();};});};
 world.setAvatars([all[2]]);const old=world.avatars.get('peer');
 assert.equal(inspect().renderableRoots,0);world.setAvatars([]);finish();await Promise.resolve();
 assert.equal(old.parent,null);assert.equal(inspect().remoteRoots,0);assert.equal(inspect().orphanRoots,0);
});
test('rig status is explicit and self/label geometry never inflates remote participant counts',()=>{
 const scene=new THREE.Scene(),self=new THREE.Group(),peer=new THREE.Group();scene.add(self,peer);
 const body=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshBasicMaterial());peer.add(body);
 const label=new THREE.Mesh(new THREE.PlaneGeometry(),new THREE.MeshBasicMaterial());peer.add(label);peer.userData.avatarLabel=label;
 const state=inspectParticipantGeometry(scene,self,new Map([['peer',peer]]),new Map([[peer,{rig:{root:body}}]]));
 assert.equal(state.rigRoots,1);assert.equal(state.fallbackRoots,0);assert.equal(state.rows[0].geometryMeshes,1);
 assert(proof.ready([{id:'self'},{id:'peer'}],'self',state,1));
 body.geometry.dispose();label.geometry.dispose();(body.material as THREE.Material).dispose();(label.material as THREE.Material).dispose();
});
