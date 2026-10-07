// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {Group,Mesh,BoxGeometry,MeshBasicMaterial} from 'three';
import {GraphicsWarmupOwner} from './graphics-warmup-owner';
function pending(){let resolve!:(value:number)=>void;const value=new Promise<number>(yes=>resolve=yes);return {value,resolve};}
test('private owner revokes superseded same-root generation and late previous completion cannot remove current owner',async()=>{
 const world=new AbortController(),owner=new GraphicsWarmupOwner(world.signal),root=new Group(),a=pending(),b=pending();let oldSignal!:AbortSignal,newSignal!:AbortSignal;
 const first=owner.run(root,()=>true,async signal=>{oldSignal=signal;return a.value;});const rejected=assert.rejects(first,{name:'AbortError'});
 const second=owner.run(root,()=>true,async signal=>{newSignal=signal;return b.value;});assert.equal(oldSignal.aborted,true);assert.equal(newSignal.aborted,false);
 a.resolve(1);await rejected;assert.equal(newSignal.aborted,false);b.resolve(2);assert.equal(await second,2);assert.equal(newSignal.aborted,true);
});
test('root graph ownership revokes child preparations before scene removal and world abort reaches unattached rig',async()=>{
 const world=new AbortController(),owner=new GraphicsWarmupOwner(world.signal),root=new Group(),child=new Group(),detached=new Group();root.add(child);
 let signal!:AbortSignal,rigSignal!:AbortSignal;const a=pending(),b=pending();
 const first=owner.run(child,()=>true,async value=>{signal=value;return a.value;});const firstError=assert.rejects(first,{name:'AbortError'});
 const second=owner.run(detached,()=>true,async value=>{rigSignal=value;return b.value;});const secondError=assert.rejects(second,{name:'AbortError'});
 owner.cancel(root);assert.equal(signal.aborted,true);assert.equal(rigSignal.aborted,false);world.abort();assert.equal(rigSignal.aborted,true);
 a.resolve(1);b.resolve(2);await firstError;await secondError;
});
test('superseded caller authority prevents entry and final success without using imported asset userData',async()=>{
 const world=new AbortController(),owner=new GraphicsWarmupOwner(world.signal),root=new Group();root.userData.shaderRevision=99999;root.userData.shadersReady=true;
 let called=false;await assert.rejects(owner.run(root,()=>false,async()=>{called=true;return 1;}),{name:'AbortError'});assert.equal(called,false);
 let current=true;const wait=pending(),output=owner.run(root,()=>current,async(_signal,guard)=>{assert.equal(guard(),true);return wait.value;});const rejected=assert.rejects(output,{name:'AbortError'});
 current=false;wait.resolve(1);await rejected;assert.equal(root.userData.shadersReady,true,'Owner does not trust or mutate imported metadata.');
});
test('compiler rejection releases exact owner without mutating real geometry/material/hierarchy',async()=>{
 const world=new AbortController(),owner=new GraphicsWarmupOwner(world.signal),root=new Group(),mesh=new Mesh(new BoxGeometry(),new MeshBasicMaterial());root.add(mesh);const geometry=mesh.geometry,material=mesh.material;let signal!:AbortSignal;
 await assert.rejects(owner.run(root,()=>true,async value=>{signal=value;throw Error('driver rejection');}),/driver rejection/);assert.equal(signal.aborted,true);
 assert.equal(await owner.run(root,()=>true,async()=>7),7);assert.equal(mesh.geometry,geometry);assert.equal(mesh.material,material);assert.equal(mesh.parent,root);
});
