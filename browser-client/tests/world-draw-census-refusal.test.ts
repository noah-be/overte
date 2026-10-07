// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {censusWorldDrawsAsync} from '../src/world-draw-census-async';
import {checkedDrawRevisionRefusal,unsupportedDrawNodeReason} from '../src/world-draw-census-refusal';
const owner=(root:T.Object3D)=>({root,loaded:true,dynamic:false,scripted:false,parented:false,materialChildren:false});
const options=()=>({signal:new AbortController().signal,isCurrent:()=>true,isRevisionCurrent:()=>true});
test('exact hidden imported light remains refused, with fixed class evidence only',async()=>{
 const root=new T.Group(),light=new T.DirectionalLight(),geometry=new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3));
 light.visible=false;light.name='PRIVATE-AUTHORING-LIGHT';root.add(light,new T.Mesh(geometry,new T.MeshBasicMaterial()));
 const report=await censusWorldDrawsAsync([owner(root)],options());
 assert.equal(report.partial,true);assert.equal(report.reasons['unsupported-node-accessor-or-class'],1);
 assert.equal(report.reasons['unsupported-node-known-light-prototype'],1);assert.equal(report.counts.candidateParts,1);
 assert(!JSON.stringify(report).includes('PRIVATE'));assert.equal(light.visible,false);
});
test('known Sprite/camera and foreign subclasses are not turned into admitted node classes',()=>{
 assert.equal(unsupportedDrawNodeReason(new T.Sprite(),'node','unsupported-object-prototype'),'unsupported-node-known-sprite-prototype');
 assert.equal(unsupportedDrawNodeReason(new T.PerspectiveCamera(),'node','unsupported-object-prototype'),'unsupported-node-known-camera-prototype');
 class ForeignLight extends T.DirectionalLight{}
 assert.equal(unsupportedDrawNodeReason(new ForeignLight(),'node','unsupported-object-prototype'),'unsupported-node-other-prototype');
});
test('descriptor and transform refusals stay distinguishable without executing getters',async()=>{
 const root=new T.Group();let calls=0;Object.defineProperty(root,'privateAccessor',{get(){calls++;return 'PRIVATE';}});
 const report=await censusWorldDrawsAsync([owner(root)],options());assert.equal(calls,0);
 assert.equal(report.reasons['unsupported-node-own-accessor'],1);
 const other=new T.Group();Object.defineProperty(other.position,'x',{get(){calls++;return 4;}});
 const transformed=await censusWorldDrawsAsync([owner(other)],options());assert.equal(calls,0);
 assert.equal(transformed.reasons['unsupported-node-transform-accessor'],1);
});
test('fixed revision detail does not preserve terminal grouping or change admission',async()=>{
 const root=new T.Mesh(new T.BufferGeometry(),new T.MeshBasicMaterial());
 const report=await censusWorldDrawsAsync([owner(root)],{...options(),isRevisionCurrent:()=>false,revisionRefusalReason:()=> 'revision-entity-record'});
 assert(report.partial);assert(report.reasons['owner-revision-changed']);assert(report.reasons['revision-entity-record']);
 assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert.equal(report.exactGeometryAndAuditedMaterialValues.groups,0);
});
test('foreign/private revision strings cannot escape the typed hook at runtime',async()=>{
 assert.equal(checkedDrawRevisionRefusal('PRIVATE-SENTINEL'),undefined);
 const report=await censusWorldDrawsAsync([],{...options(),isRevisionCurrent:()=>false,revisionRefusalReason:(()=> 'PRIVATE-SENTINEL') as never});
 assert(report.partial);assert(!JSON.stringify(report).includes('PRIVATE-SENTINEL'));
});
