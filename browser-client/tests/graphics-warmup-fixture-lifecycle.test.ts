// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {DataTexture,RGFormat,HalfFloatType,RGBAFormat} from 'three';
import {closeWarmupFixtureResources} from './graphics-warmup-fixture';
function lut(){const value=new DataTexture(new Uint16Array(16*16*2),16,16,RGFormat,HalfFloatType);value.name='DFG_LUT';return value;}
test('complete authored renderer set releases all resources, shared lookup once, then both property registries',()=>{
 const texture=lut(),events:string[]=[];let textureDisposals=0;const registries=[true,true];
 texture.addEventListener('dispose',()=>{textureDisposals++;assert.deepEqual(registries,[true,true]);events.push('lookup');});
 closeWarmupFixtureResources([0,1].map(index=>({releaseResources(){events.push(`resources${index}`);return texture;},finalizeRenderer(){events.push(`renderer${index}`);registries[index]=false;}})));
 assert.equal(textureDisposals,1);assert.deepEqual(events,['resources0','resources1','lookup','renderer0','renderer1']);
});
test('different lookup identities cannot be disposed just because metadata looks identical',()=>{
 const values=[lut(),lut()];let disposal=0,finalized=0;for(const value of values)value.addEventListener('dispose',()=>disposal++);
 assert.throws(()=>closeWarmupFixtureResources(values.map(value=>({releaseResources:()=>value,finalizeRenderer(){finalized++;}}))),/same Three DFG/);
 assert.equal(disposal,0);assert.equal(finalized,2);
});
test('unknown borrowed texture is never disposed and normal renderer finalization still occurs',()=>{
 const texture=lut();texture.format=RGBAFormat;let disposal=0,finalized=0;texture.addEventListener('dispose',()=>disposal++);
 assert.throws(()=>closeWarmupFixtureResources([{releaseResources:()=>texture,finalizeRenderer(){finalized++;}}]),/Unrecognized/);
 assert.equal(disposal,0);assert.equal(finalized,1);
});
test('one resource-release failure does not omit other owned release/finalize paths',()=>{
 const events:string[]=[];assert.throws(()=>closeWarmupFixtureResources([{releaseResources(){events.push('release0');throw Error('owned failure');},finalizeRenderer(){events.push('final0');}},
 {releaseResources(){events.push('release1');return undefined;},finalizeRenderer(){events.push('final1');}}]),/owned failure/);
 assert.deepEqual(events,['release0','release1','final0','final1']);
});
test('renderer finalization failure does not skip sibling renderer cleanup',()=>{
 const events:string[]=[];assert.throws(()=>closeWarmupFixtureResources([{releaseResources:()=>undefined,finalizeRenderer(){events.push('final0');throw Error('renderer failure');}},
 {releaseResources:()=>undefined,finalizeRenderer(){events.push('final1');}}]),/renderer failure/);assert.deepEqual(events,['final0','final1']);
});
test('cancelled before render has no borrowed LUT and still closes its single owned renderer',()=>{
 let finalized=0;closeWarmupFixtureResources([{releaseResources:()=>undefined,finalizeRenderer(){finalized++;}}]);assert.equal(finalized,1);
 assert.throws(()=>closeWarmupFixtureResources([]),/ownership bound/);
});
