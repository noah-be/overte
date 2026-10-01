// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual renderer methods and Three resources; fetch/texture I/O are fault inputs.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Group,Mesh,BufferGeometry,MeshStandardMaterial,Texture} from 'three';
import {BrowserWorld} from '../src/world';

const methods=BrowserWorld.prototype as unknown as {
  loadModel(source:string,visited?:Set<string>,textureBase?:string):Promise<Group>;
  makeMaterial(data:Record<string,unknown>,source?:string):Promise<MeshStandardMaterial>;
};
function watched<T extends BufferGeometry|MeshStandardMaterial|Texture>(resource:T):()=>number {
  let count=0;resource.addEventListener('dispose',()=>count++);return ()=>count;
}
function fixture(){
  const model=new Group(),geometry=new BufferGeometry(),texture=new Texture(),material=new MeshStandardMaterial({map:texture});
  const mesh=new Mesh(geometry,material);model.add(mesh);
  const counts=[geometry,texture,material].map(watched);
  const context=Object.create(BrowserWorld.prototype);
  Object.assign(context,{options:{resolveAsset:(url:string)=>url,onStatus(){}},abort:new AbortController(),disposed:false});
  context.loadModel=(source:string,visited?:Set<string>,textureBase?:string)=>source.endsWith('.fst')
    ?methods.loadModel.call(context,source,visited,textureBase):Promise.resolve(model);
  return {context,model,mesh,counts};
}

test('actual FST renderer path releases its parsed model on invalid mapping or denied material HTTP response',async t=>{
  for(const mapping of ['filename = body.fbx\nmaterialMap = {invalid}',
      'filename = body.fbx\nmaterialMap = [{"all":"material.json"}]']){
    const {context,counts}=fixture();
    t.mock.method(globalThis,'fetch',async(input:unknown)=>String(input).endsWith('.fst')
      ?new Response(mapping):new Response('Access denied',{status:403}));
    await assert.rejects(context.loadModel('https://assets.invalid/avatar.fst'));
    assert.deepEqual(counts.map(count=>count()),[1,1,1]);t.mock.restoreAll();
  }
});

test('actual successful FST material replacement releases orphan maps while its clone retains the new texture',async t=>{
  const {context,mesh,counts}=fixture(),texture=new Texture(),material=new MeshStandardMaterial({map:texture});
  const newTextureCount=watched(texture),templateCount=watched(material);
  t.mock.method(globalThis,'fetch',async(input:unknown)=>new Response(String(input).endsWith('.fst')
    ?'filename = body.fbx\nmaterialMap = [{"all":"material.json"}]':'{"materials":{"name":"skin"}}'));
  context.makeMaterial=async()=>material;
  await context.loadModel('https://assets.invalid/avatar.fst');
  assert.deepEqual(counts.map(count=>count()),[0,1,1]);
  assert.equal(templateCount(),1);assert.equal(newTextureCount(),0);
  assert.notEqual(mesh.material,material);assert.equal((mesh.material as MeshStandardMaterial).map,texture);
});

test('actual material factory releases previously loaded texture when its next dependency fails',async()=>{
  const {context}=fixture(),texture=new Texture(),failure=new Error('Normal texture was denied');
  const textureCount=watched(texture);let requests=0;
  context.texture=async()=>{if(++requests===1)return texture;throw failure;};
  await assert.rejects(methods.makeMaterial.call(context,{albedoMap:'skin.png',normalMap:'normal.png'},'https://assets.invalid/material.json'),error=>error===failure);
  assert.equal(requests,2);assert.equal(textureCount(),1);
});


test('actual successive FST assignments release intermediate clones that disappear before final traversal',async t=>{
  const {context,mesh,counts}=fixture();
  const first=new MeshStandardMaterial({map:new Texture()}),second=new MeshStandardMaterial({map:new Texture()});
  const intermediate=first.clone(),intermediateCount=watched(intermediate);
  const firstCount=watched(first),secondCount=watched(second),firstTextureCount=watched(first.map!),secondTextureCount=watched(second.map!);
  t.mock.method(first,'clone',()=>intermediate);
  t.mock.method(globalThis,'fetch',async(input:unknown)=>new Response(String(input).endsWith('.fst')
    ?'filename = body.fbx\nmaterialMap = [{"all":"a.json"},{"all":"b.json"}]':'{"materials":{"name":"skin"}}'));
  let assignment=0;context.makeMaterial=async()=>assignment++===0?first:second;
  await context.loadModel('https://assets.invalid/avatar.fst');
  assert.equal(assignment,2);assert.equal(intermediateCount(),1);
  assert.equal(firstCount(),1);assert.equal(secondCount(),1);
  assert.equal(firstTextureCount(),1);assert.equal(secondTextureCount(),0);
  assert.deepEqual(counts.map(count=>count()),[0,1,1]);
  assert.equal((mesh.material as MeshStandardMaterial).map,second.map);
});
