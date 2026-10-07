// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual Three graph/material inputs; controlled compiler/task I/O. GPU proof pending.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Bone, BoxGeometry, BufferAttribute, DoubleSide, Group, InstancedMesh, Material, Mesh, MeshBasicMaterial,
  PerspectiveCamera, PointLight, Scene, Skeleton, SkinnedMesh, Sprite, SpriteMaterial, type Object3D } from 'three';
import { graphicsWarmupView, prepareGraphicsYielding } from './graphics-warmup';

const frame = () => ({ camera: new PerspectiveCamera(), scene: new Scene() });
function materials(object: Object3D) {
  const list: { object: any; material: Material }[] = [];
  object.traverse(value => { const draw = value as any;
    if (draw.isMesh || draw.isPoints || draw.isLine || draw.isSprite) for (const material of Array.isArray(draw.material) ? draw.material : [draw.material]) list.push({ object: draw, material });
  }); return list;
}
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
function compiler(readiness: Promise<unknown> = Promise.resolve()) {
  const calls: {root:Object3D; bindings:ReturnType<typeof materials>; final:boolean}[]=[];
  return { calls, compile(root:Object3D) { calls.push({root,bindings:materials(root),final:false}); },
    compileAsync(root:Object3D) { calls.push({root,bindings:materials(root),final:true}); return readiness; } };
}
function tasks() { let yielded=0,closed=0;return {value:{async yield(){yielded++;},close(){closed++;}},yielded:()=>yielded,closed:()=>closed}; }

test('compile-only views preserve exact skin, morph, instance and sprite inputs without reparenting or replacing materials', () => {
  const root=new Group(),geometry=new BoxGeometry(),material=new MeshBasicMaterial(),bone=new Bone();
  geometry.morphAttributes.position=[new BufferAttribute(new Float32Array(geometry.getAttribute('position').array),3)];
  const skin=new SkinnedMesh(geometry,material);skin.add(bone);skin.bind(new Skeleton([bone]));skin.updateMorphTargets();
  const instances=new InstancedMesh(geometry,material,2),sprite=new Sprite(new SpriteMaterial());root.add(skin,instances,sprite);
  const sourceChildren=[...root.children],parents=root.children.map(child=>child.parent),array=[material,new MeshBasicMaterial()];
  const mesh=new Mesh(geometry,array);root.add(mesh);
  const view=graphicsWarmupView(root,[{object:skin,material},{object:instances,material},{object:sprite,material:sprite.material},{object:mesh,material:array[1]}]);
  const bindings=materials(view);assert.equal(bindings.length,4);
  assert.equal(bindings[0].object.skeleton,skin.skeleton);assert.equal(bindings[0].object.morphTargetInfluences,skin.morphTargetInfluences);
  assert.equal(bindings[1].object.instanceMatrix,instances.instanceMatrix);assert.equal(bindings[1].object.count,2);
  assert.equal(bindings[2].object.isSprite,true);assert.equal(bindings[3].material,array[1]);
  assert.deepEqual(root.children.slice(0,3),sourceChildren);assert.deepEqual(root.children.slice(0,3).map(child=>child.parent),parents);
  assert.equal(mesh.material,array);assert.equal(mesh.geometry,geometry);
});
test('large roots yield between bounded material slices, retain shared-material geometry variants and finish on the exact original root',async()=>{
  const root=new Group(),shared=new MeshBasicMaterial(),other=new MeshBasicMaterial();
  for(let i=0;i<4;i++)root.add(new Mesh(new BoxGeometry(),[shared,shared,other]));
  const input=materials(root),driver=compiler(),t=tasks(),{camera,scene}=frame();
  const result=await prepareGraphicsYielding(driver,camera,scene,root,{bindingsPerBatch:3,taskFactory:()=>t.value});
  assert.equal(result.bindings,8);assert.equal(result.batches,3);assert.equal(result.yielded,3);assert.equal(t.closed(),1);
  assert.deepEqual(driver.calls.filter(call=>!call.final).map(call=>call.bindings.length),[3,3,2]);
  assert.equal(driver.calls.at(-1)?.root,root);assert.equal(driver.calls.filter(call=>call.final).length,1);
  // Shared material appears on every distinct geometry object, not just once
  // across the root; only duplicate same-object array slots are coalesced.
  const submitted=driver.calls.filter(call=>!call.final).flatMap(call=>call.bindings);
  for(const child of root.children)assert.equal(submitted.filter(binding=>Object.getPrototypeOf(binding.object)===child).length,2);
  assert.deepEqual(materials(root),input);assert.equal(result.fallback,null);
});
test('visible/hidden local lights and layers exactly follow the original root while no scene graph is mutated',()=>{
  const root=new Group(),a=new PointLight(),b=new PointLight();b.visible=false;a.layers.set(3);root.add(a,b);
  const view=graphicsWarmupView(root,[]),seen:Object3D[]=[];view.traverseVisible(object=>{if((object as any).isLight)seen.push(object);});
  assert.equal(seen.length,1);assert.equal(seen[0],a);assert.equal((seen[0] as PointLight).layers,a.layers);assert.equal(a.parent,root);assert.equal(b.parent,root);
  root.visible=false;seen.length=0;view.traverseVisible(object=>{if((object as any).isLight)seen.push(object);});assert.deepEqual(seen,[]);
});
test('small, node and legacy two-pass transparent roots preserve the existing single-call compile behavior and material versions',async()=>{
  for(const kind of ['small','node','two-pass']){
    const root=new Group(),material=new MeshBasicMaterial();if(kind==='node')(material as any).isNodeMaterial=true;
    if(kind==='two-pass'){material.transparent=true;material.side=DoubleSide;material.forceSinglePass=false;}
    for(let i=0;i<(kind==='small'?1:6);i++)root.add(new Mesh(new BoxGeometry(),material));
    const version=material.version,driver=compiler(),t=tasks(),{camera,scene}=frame();
    const value=await prepareGraphicsYielding(driver,camera,scene,root,{taskFactory:()=>t.value});
    assert.equal(driver.calls.length,1);assert.equal(driver.calls[0].root,root);assert.equal(t.yielded(),0);assert.equal(material.version,version);
    assert.equal(value.fallback,kind==='small'?'small-root':kind==='node'?'node-material':'two-pass-transparent');
  }
});
test('owner abort during an actual task boundary stops later submissions and closes its task resource',async()=>{
  const root=new Group();for(let i=0;i<10;i++)root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  const abort=new AbortController(),driver=compiler();let closed=0;const {camera,scene}=frame();
  await assert.rejects(prepareGraphicsYielding(driver,camera,scene,root,{signal:abort.signal,taskFactory:()=>({async yield(){abort.abort();},close(){closed++;}})}),{name:'AbortError'});
  assert.equal(driver.calls.length,1);assert.equal(driver.calls[0].final,false);assert.equal(closed,1);
});
test('superseded ownership and synchronous compiler errors cannot publish a successful warmup or swallow errors',async()=>{
  const root=new Group();for(let i=0;i<5;i++)root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  const {camera,scene}=frame(),driver=compiler();let current=true,closed=0;
  await assert.rejects(prepareGraphicsYielding(driver,camera,scene,root,{isCurrent:()=>current,taskFactory:()=>({async yield(){current=false;},close(){closed++;}})}),{name:'AbortError'});
  assert.equal(driver.calls.length,1);assert.equal(closed,1);
  const t=tasks();await assert.rejects(prepareGraphicsYielding({compile(){throw Error('actual compile failed');},compileAsync(){throw Error('must not follow');}},camera,scene,root,{taskFactory:()=>t.value}),/actual compile failed/);
  assert.equal(t.closed(),1);
});
test('readiness remains awaited separately, abort is immediate and a late compiler failure is consumed',async()=>{
  const root=new Group();root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  let fail!:(error:unknown)=>void;const pending=new Promise((_,reject)=>fail=reject),driver=compiler(pending),abort=new AbortController(),{camera,scene}=frame();
  const ready=prepareGraphicsYielding(driver,camera,scene,root,{signal:abort.signal});await flush();const rejected=assert.rejects(ready,{name:'AbortError'});abort.abort();await rejected;
  fail(Error('late driver failure'));await flush();assert.equal(driver.calls.length,1);
});
test('a bounded genuine readiness timeout fails explicitly instead of marking shaders ready',async()=>{
  const root=new Group(),driver=compiler(new Promise(()=>{})),{camera,scene}=frame();
  await assert.rejects(prepareGraphicsYielding(driver,camera,scene,root,{readinessTimeoutMs:12}),/bounded timeout/);
  assert.equal(driver.calls.length,1);
});
test('synchronous submission and asynchronous readiness clocks have separate populations',async()=>{
  const root=new Group();root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));let time=0,resolve!:()=>void;
  const waiting=new Promise<void>(yes=>resolve=yes),driver={compile(){},compileAsync(){time=7;return waiting;}}, {camera,scene}=frame();
  const output=prepareGraphicsYielding(driver,camera,scene,root,{clock:()=>time});await flush();time=31;resolve();
  const result=await output;assert.equal(result.finalSubmitMs,7);assert.equal(result.readinessWaitMs,24);assert.equal(result.submitMs,0);
});
test('stalled owned task delivery has a total deadline, closes immediately and late success cannot submit another slice',async()=>{
  const root=new Group();for(let i=0;i<5;i++)root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  let resolve!:()=>void,closed=0;const pending=new Promise<void>(yes=>resolve=yes),driver=compiler(),{camera,scene}=frame();
  await assert.rejects(prepareGraphicsYielding(driver,camera,scene,root,{preparationTimeoutMs:12,taskFactory:()=>({yield:()=>pending,close(){closed++;}})}),/bounded timeout/);
  assert.equal(closed,1);assert.equal(driver.calls.length,1);resolve();await flush();assert.equal(driver.calls.length,1);
});
test('total submission bound is checked after each nonpreemptible actual compile and never fakes final readiness',async()=>{
  const root=new Group();for(let i=0;i<5;i++)root.add(new Mesh(new BoxGeometry(),new MeshBasicMaterial()));
  let time=0,finalCalls=0,closed=0;const {camera,scene}=frame();
  await assert.rejects(prepareGraphicsYielding({compile(){time=61;},async compileAsync(){finalCalls++;}},camera,scene,root,{clock:()=>time,preparationTimeoutMs:60,
    taskFactory:()=>({async yield(){assert.fail('Deadline already expired');},close(){closed++;}})}),/bounded timeout/);
  assert.equal(finalCalls,0);assert.equal(closed,1);
});
test('warming the actual targetScene cannot duplicate its light contribution in the public new-object compile branch',()=>{
  const scene=new Scene(),light=new PointLight();scene.add(light);const view=graphicsWarmupView(scene,[],scene),lights:Object3D[]=[];
  scene.traverseVisible(object=>{if((object as PointLight).isLight)lights.push(object);});
  view.traverseVisible(object=>{if((object as PointLight).isLight)lights.push(object);});
  assert.deepEqual(lights,[light]);assert.equal(light.parent,scene);
});
