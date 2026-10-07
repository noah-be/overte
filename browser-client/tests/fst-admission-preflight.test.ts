// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectFbxOriginalTextures} from '../src/baked-fbx';
import {canFstDefinitionsReplaceOriginalTextures} from '../src/fst-texture-admission';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const plan=(selector='mat::A',extra:Record<string,unknown>={})=>({selector,definition:{name:'Replacement',model:'hifi_pbr',albedoMap:'replacement.png',...extra}});
test('metadata preflight and derived graph agree on removable shared/private texture consumers without mutating bytes',()=>{
 const buffer=fstTextureAdmissionFbx({nativeEndRecords:true}),before=buffer.slice(0),graph=inspectFbxOriginalTextures(buffer);assert(graph);
 for(const covered of [new Set<number>(),new Set([101]),new Set([102]),new Set([101,102])])assert.equal(graph.hasRemovableTextures(covered),graph.derive(covered).removedTextures>0);
 assert.deepEqual(new Uint8Array(buffer),new Uint8Array(before));assert.throws(()=>graph.hasRemovableTextures(new Set([999])),/replacement proof/);
});
test('zero-texture and unknown-consumer graphs cannot start replacement-first image loading',()=>{
 const empty=inspectFbxOriginalTextures(fstTextureAdmissionFbx({withoutOriginalTextures:true,nativeEndRecords:true}));assert(empty);assert.equal(empty.hasRemovableTextures(new Set([101,102])),false);assert.equal(canFstDefinitionsReplaceOriginalTextures(empty,[plan('all')]),false);
 const unknown=inspectFbxOriginalTextures(fstTextureAdmissionFbx({unknownTextureConsumer:true,nativeEndRecords:true}));assert(unknown);assert.equal(canFstDefinitionsReplaceOriginalTextures(unknown,[plan()]),false);
});
test('ordered supported definitions follow names and require a genuinely removable original consumer',()=>{
 const graph=inspectFbxOriginalTextures(fstTextureAdmissionFbx({nativeEndRecords:true}));assert(graph);
 assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,[plan('all')]),true);assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,[plan('mat::NoSuchMaterial')]),false);
 assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,[plan('mat::A'),plan('mat::Replacement',{name:'Final'})]),true);
});
test('unsupported fallthrough, transform, occlusion, gloss and foreign selectors preserve original loading order',()=>{
 const graph=inspectFbxOriginalTextures(fstTextureAdmissionFbx({nativeEndRecords:true}));assert(graph);
 for(const extra of [{defaultFallthrough:true},{texCoordTransform0:{}},{occlusionMap:'required.png'},{glossMap:'required.png'},{procedural:{}},{opacityMap:'different.png'}])assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,[plan('all',extra)]),false);
 assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,[plan('0')]),false);assert.equal(canFstDefinitionsReplaceOriginalTextures(graph,Array.from({length:257},()=>plan('all'))),false);
});
