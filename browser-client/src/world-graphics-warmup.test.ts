// SPDX-License-Identifier: Apache-2.0
// Actual World/owner/Three lifetimes; compiler completion is controlled I/O,
// not a GPU, shader-fidelity or native-avatar acceptance claim.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BoxGeometry, Group, Mesh, MeshBasicMaterial, PerspectiveCamera, PlaneGeometry, Scene } from 'three';
import { BrowserWorld } from './world';
import { GraphicsWarmupOwner } from './graphics-warmup-owner';
import type { Avatar } from './world-data';

function deferred<T>() { let resolve!:(value:T)=>void, reject!:(reason:unknown)=>void; const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; }
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
function fixture(enabled=false) {
  const world=Object.create(BrowserWorld.prototype),abort=new AbortController();
  const compilations:{root:Group;finish:ReturnType<typeof deferred<void>>}[]=[],loads:{source:string;finish:ReturnType<typeof deferred<Group>>}[]=[],warnings:string[]=[];
  Object.assign(world,{abort,disposed:false,shaderWarmup:enabled,zeroLightGuard:false,compilingGraphics:0,
    shaderWarmupCounters:{roots:0,bindings:0,batches:0,yielded:0,smallRoots:0,conservativeFallbacks:0},
    scene:new Scene(),camera:new PerspectiveCamera(),avatars:new Map(),avatarModels:new Map(),self:new Group(),localAvatarID:'',enabled:true,thirdPerson:true,
    loadPhases:new Map(),options:{onStatus:(message:string)=>warnings.push(message)},
    renderer:{compile(){throw Error('Fixture has at most four bindings; slicing is covered separately');},compileAsync(root:Group){const finish=deferred<void>();compilations.push({root,finish});return finish.promise;}},
    textPlane(){return new Mesh(new PlaneGeometry(1,1),new MeshBasicMaterial());},
    loadModel(source:string){const finish=deferred<Group>();loads.push({source,finish});return finish.promise;},
  });
  // Deliberately absent off: constructor-bypassing existing lifecycle fixtures
  // must not acquire a new experimental dependency in baseline methods.
  if(enabled)world.graphicsWarmups=new GraphicsWarmupOwner(abort.signal);
  return {world,abort,compilations,loads,warnings};
}
const peer=(overrides:Partial<Avatar>={}):Avatar=>({id:'owned-peer',displayName:'Participant',position:{x:1,y:1,z:1},...overrides});
function disposalCounts(root:Group) {
  const counts={geometry:0,material:0};root.traverse(object=>{if(object instanceof Mesh){object.geometry.addEventListener('dispose',()=>counts.geometry++);for(const material of Array.isArray(object.material)?object.material:[object.material])material.addEventListener('dispose',()=>counts.material++);}});return counts;
}

test('default-off actual avatar methods require no experimental owner and preserve one ordinary compile across repeated empty-source snapshots',async()=>{
  const f=fixture();f.world.setAvatars([peer()]);const root=f.world.avatars.get('owned-peer') as Group;
  for(let i=0;i<20;i++)f.world.setAvatars([peer()]);assert.equal(f.compilations.length,1);assert.equal(f.world.avatarModels.size,0);assert.equal(f.world.graphicsWarmups,undefined);
  f.compilations[0].finish.resolve();await flush();assert.equal(root.visible,true);assert.equal(root.userData.shadersReady,true);
  f.world.options.shaderWarmup=true;f.world.setAvatars([peer({displayName:'Changed'})]);assert.equal(f.compilations.length,1,'Retained options cannot activate the captured experiment');
  f.world.setAvatars([]);assert.equal(f.world.avatars.size,0);f.abort.abort();
});

test('legacy one-argument actual preparation retains default compile contract and its publication revision',async()=>{
  const f=fixture(),root=new Group();const pending=f.world.prepareGraphics(root);assert.equal(f.compilations.length,1);assert.equal(root.visible,false);
  f.compilations[0].finish.resolve();await pending;assert.equal(root.userData.shadersReady,true);assert.equal(f.world.compilingGraphics,0);f.abort.abort();
});

test('opted-in empty-source snapshots are one generation and cannot perpetually cancel/hide the usable fallback',async t=>{
  const f=fixture(true);t.after(()=>f.abort.abort());f.world.setAvatars([peer()]);const root=f.world.avatars.get('owned-peer') as Group;
  // The new source generation deliberately replaces the initial generic compile.
  assert.equal(f.compilations.length,2);const state=f.world.avatarModels.get(root);assert.equal(state.source,'');
  for(let i=0;i<30;i++)f.world.setAvatars([peer()]);assert.equal(f.compilations.length,2);assert.equal(f.world.avatarModels.get(root),state);
  for(const job of f.compilations)job.finish.resolve();await flush();assert.equal(root.visible,true);assert.equal(root.userData.shadersReady,true);assert.equal(f.world.compilingGraphics,0);
  for(let i=0;i<30;i++)f.world.setAvatars([peer()]);assert.equal(root.visible,true);assert.equal(f.compilations.length,2);assert.deepEqual(f.warnings,[]);
  f.world.setAvatars([]);f.abort.abort();
});

test('latest actual label refresh owns visibility and cancelled old completion cannot reveal an unprepared root',async()=>{
  const f=fixture(true);f.world.setAvatars([peer()]);const root=f.world.avatars.get('owned-peer') as Group,oldLabel=root.userData.avatarLabel as Mesh;let labelDisposed=0;oldLabel.geometry.addEventListener('dispose',()=>labelDisposed++);
  f.world.setAvatars([peer({displayName:'Current name'})]);assert.equal(f.compilations.length,3);assert.equal(labelDisposed,1);assert.equal(root.visible,false);
  f.compilations[0].finish.resolve();f.compilations[1].finish.resolve();await flush();assert.equal(root.visible,false);assert.equal(root.userData.shadersReady,false);
  f.compilations[2].finish.resolve();await flush();assert.equal(root.visible,true);assert.equal(root.userData.shadersReady,true);assert.equal(root.userData.avatarLabelName,'Current name');assert.deepEqual(f.warnings,[]);
  f.world.setAvatars([]);f.abort.abort();
});

test('actual failed source preserves ready fallback, then clearing the source establishes a stable usable empty generation',async()=>{
  const f=fixture(true);f.world.setAvatars([peer()]);for(const job of f.compilations)job.finish.resolve();await flush();const root=f.world.avatars.get('owned-peer') as Group;
  f.world.setAvatars([peer({skeletonModelURL:'https://fixture.invalid/denied.fbx'})]);assert.equal(f.loads.length,1);f.compilations.at(-1)!.finish.resolve();await flush();assert.equal(root.visible,true);
  f.loads[0].finish.reject(Error('Asset approval refused'));await flush();assert.equal(root.visible,true);assert.equal(f.warnings.length,1);assert.match(f.warnings[0],/Asset approval refused/);
  f.world.setAvatars([peer()]);const previous=f.compilations.length;for(let i=0;i<20;i++)f.world.setAvatars([peer()]);assert.equal(f.compilations.length,previous);f.compilations.at(-1)!.finish.resolve();await flush();assert.equal(root.visible,true);assert.equal(f.world.avatarModels.get(root).source,'');
  f.world.setAvatars([]);f.abort.abort();
});

test('removing actual peer cancels its unattached rig preparation and releases fallback and rig exactly once, including late compiler failure',async()=>{
  const f=fixture(true);f.world.setAvatars([peer({skeletonModelURL:'https://fixture.invalid/model.glb'})]);const root=f.world.avatars.get('owned-peer') as Group,fallback=disposalCounts(root);
  const model=new Group();model.userData.avatarFormat='gltf';model.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));const rigResources=disposalCounts(model);
  f.loads[0].finish.resolve(model);await flush();assert(f.world.avatarModels.get(root).preparing,'Actual unattached rig must still belong to the current state');assert.equal(f.compilations.length,3);
  f.world.setAvatars([]);await flush();assert.equal(f.world.avatars.size,0);assert.equal(f.world.avatarModels.size,0);assert.deepEqual(fallback,{geometry:4,material:4});assert.deepEqual(rigResources,{geometry:1,material:1});assert.equal(f.world.compilingGraphics,0);assert.deepEqual(f.warnings,[]);
  for(const job of f.compilations)job.finish.reject(Error('Late original driver failure'));await flush();assert.deepEqual(rigResources,{geometry:1,material:1});assert.deepEqual(f.warnings,[]);f.abort.abort();
});

test('actual final avatar parent compile includes the retained label and exact new rig before visibility publication',async()=>{
  const f=fixture(true);f.world.setAvatars([peer({skeletonModelURL:'https://fixture.invalid/model.glb'})]);const root=f.world.avatars.get('owned-peer') as Group;
  for(const job of f.compilations)job.finish.resolve();await flush();const model=new Group();model.userData.avatarFormat='gltf';model.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  f.loads[0].finish.resolve(model);await flush();const rig=f.world.avatarModels.get(root).preparing;assert(rig);f.compilations.at(-1)!.finish.resolve();await flush();
  const final=f.compilations.at(-1)!;assert.equal(final.root,root);assert.equal(root.children.length,2);assert.equal(root.children[0],root.userData.avatarLabel);assert.equal(root.children[1],rig);assert.equal(root.visible,false);
  final.finish.resolve();await flush();assert.equal(root.visible,true);assert.equal(root.userData.shadersReady,true);assert.equal(f.world.avatarModels.get(root).rig.root,rig);assert.equal(f.world.compilingGraphics,0);
  f.world.setAvatars([]);f.abort.abort();
});
