// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Box3,BoxGeometry,Group,Mesh,MeshStandardMaterial,Vector3} from 'three';
import {ModelGeometryStage,normalizeModelEntity} from '../src/model-geometry-stage';
import {ModelResources} from '../src/model-resources';
import {MeshCollision} from '../src/mesh-collision';
import type {Entity} from '../src/world-data';
function fixture(){
 const root=new Group(),model=new Group(),geometry=new BoxGeometry(4,.2,6),material=new MeshStandardMaterial(),mesh=new Mesh(geometry,material);
 mesh.position.set(2,5,-7);model.add(mesh);root.position.set(3,2,-4);root.rotation.y=Math.PI/2;
 const entity:Entity={id:'actual',type:'Model',dimensions:{x:20,y:.4,z:30},registrationPoint:{x:.25,y:.5,z:.75}};
 let current=true,publishes=0,withdraws=0,collision:MeshCollision|undefined;const published:Group[]=[];
 const stage=new ModelGeometryStage({root,entity,isCurrent:()=>current,publish:value=>{publishes++;published.push(value as Group);collision?.dispose();collision=new MeshCollision(value);},withdraw:()=>{withdraws++;collision?.dispose();collision=undefined;}});
 return{root,model,geometry,material,mesh,entity,stage,published,collision:()=>collision,publishes:()=>publishes,withdraws:()=>withdraws,setCurrent:(value:boolean)=>{current=value;}};
}
test('real detached normalized model publishes native dimensions/registration triangles before images without scene or resource ownership',()=>{
 const f=fixture();let disposed=0;f.geometry.addEventListener('dispose',()=>disposed++);f.stage.prepare(f.model);
 assert.equal(f.root.children.length,0);assert.equal(f.stage.state.committed,false);assert.equal(disposed,0);
 const bounds=new Box3().setFromObject(f.published[0]),size=bounds.getSize(new Vector3()),center=bounds.getCenter(new Vector3());
 assert(size.distanceTo(new Vector3(30,.4,20))<1e-5);assert(center.distanceTo(new Vector3(-4.5,2,-9))<1e-5);
 const player=new Vector3(center.x,center.y+.9,center.z),contact=f.collision()!.resolve(player);assert(contact&&contact.y>.99,'Grounding uses genuine normalized floor triangles');
 f.stage.revoke();assert.equal(disposed,0);assert.equal(f.model.parent,null);assert.deepEqual(f.model.position.toArray(),[0,0,0]);assert.equal(f.withdraws(),1);
});
test('current native entity transforms rebuild pending collision without waiting for materials',()=>{
 const f=fixture();f.stage.prepare(f.model);f.root.position.y+=3;f.root.rotation.y=0;f.stage.update();
 const bounds=new Box3().setFromObject(f.published.at(-1)!);assert(Math.abs(bounds.getCenter(new Vector3()).y-5)<1e-5);assert.equal(f.publishes(),2);f.stage.revoke();
});
test('final material/FST completion commits the same real hierarchy once and matches completed normalization',()=>{
 const f=fixture(),baseline=f.model.clone(true),normalized=normalizeModelEntity(baseline,f.entity),content=new Group();content.position.copy(normalized.registrationOffset);content.add(normalized.normalizer);const baselineRoot=f.root.clone(false);baselineRoot.add(content);
 f.stage.prepare(f.model);const finalContent=new Group();f.root.add(finalContent);f.stage.commit(finalContent);f.stage.update();
 assert.equal(f.stage.state.committed,true);assert.equal(f.published.at(-1),f.root);assert.equal(finalContent.children[0].children[0],f.model);
 const a=new Box3().setFromObject(f.root),b=new Box3().setFromObject(baselineRoot);assert(a.min.distanceTo(b.min)<1e-7&&a.max.distanceTo(b.max)<1e-7);assert.throws(()=>f.stage.commit(finalContent),/already committed/);f.stage.revoke();assert.equal(f.model.parent,finalContent.children[0]);
});
test('failed textures/FST and root replacement withdraw geometry but loader releases model resources exactly once',()=>{
 for(const cause of ['texture','replacement']){
  const f=fixture(),owner=new ModelResources();owner.capture(f.model);let geometry=0,material=0;f.geometry.addEventListener('dispose',()=>geometry++);f.material.addEventListener('dispose',()=>material++);
  f.stage.prepare(f.model);if(cause==='replacement'){f.setCurrent(false);f.stage.update();}else f.stage.revoke();
  owner.releaseKeeping();owner.releaseKeeping();f.stage.revoke();assert.equal(geometry,1);assert.equal(material,1);assert.equal(f.withdraws(),1);assert.equal(f.collision(),undefined);assert.equal(f.root.children.length,0);
 }
});
test('committed model resource authority remains the actual root, while stale/current-failure callbacks cannot attach or republish',()=>{
 const f=fixture();let disposed=0;f.geometry.addEventListener('dispose',()=>disposed++);f.stage.prepare(f.model);const content=new Group();f.root.add(content);f.stage.commit(content);f.setCurrent(false);f.stage.update();
 const count=f.publishes();f.stage.update();assert.equal(f.publishes(),count);assert.throws(()=>f.stage.prepare(f.model),{name:'AbortError'});assert.equal(disposed,0);
 const owner=new ModelResources();owner.capture(f.root);owner.releaseKeeping();assert.equal(disposed,1);assert.equal(f.withdraws(),1);
});
test('failed collision publication rolls back borrowed hierarchy without disposing the loader-owned model',()=>{
 const root=new Group(),model=new Group(),geometry=new BoxGeometry(),material=new MeshStandardMaterial();model.position.set(1,2,3);model.add(new Mesh(geometry,material));let withdrawn=0,disposed=0;geometry.addEventListener('dispose',()=>disposed++);
 const stage=new ModelGeometryStage({root,entity:{id:'model',type:'Model'},isCurrent:()=>true,publish:()=>{throw Error('BVH failure');},withdraw:()=>withdrawn++});assert.throws(()=>stage.prepare(model),/BVH failure/);assert.equal(disposed,0);assert.equal(model.parent,null);assert.deepEqual(model.position.toArray(),[1,2,3]);assert.equal(withdrawn,1);
});
