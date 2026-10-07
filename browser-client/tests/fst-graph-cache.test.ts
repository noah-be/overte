// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {MeshBasicMaterial,Texture} from 'three';
import {FstGraphCache} from '../src/fst-graph-cache';
import {prepareFstTextureAdmission} from '../src/fst-texture-admission';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
test('repeated Hub-like zero-texture consumers inspect once and retain only a tiny weak-key sentinel',()=>{
 const owner=new AbortController(),cache=new FstGraphCache(owner.signal),buffer=fstTextureAdmissionFbx({withoutOriginalTextures:true,nativeEndRecords:true});
 for(let i=0;i<20;i++)assert.equal(cache.inspect(buffer),undefined);
 assert.equal(cache.stats.inspections,1);assert.equal(cache.stats.hits,19);assert.equal(cache.stats.zeroResults,1);
 const entries=(cache as any).entries;assert(entries instanceof WeakMap);assert.equal(typeof entries.get(buffer),'symbol');cache.inspect(buffer.slice(0));assert.equal(cache.stats.inspections,2);owner.abort();
});
test('unknown graph results retain no parsed tree and are isolated from another World memo',()=>{
 const a=new AbortController(),b=new AbortController(),first=new FstGraphCache(a.signal),second=new FstGraphCache(b.signal),buffer=fstTextureAdmissionFbx({ambiguousID:'negative',nativeEndRecords:true});
 for(let i=0;i<5;i++)assert.equal(first.inspect(buffer),undefined);assert.equal(first.stats.inspections,1);assert.equal(first.stats.unknownResults,1);assert.equal(typeof (first as any).entries.get(buffer),'symbol');
 assert.equal(second.inspect(buffer),undefined);assert.equal(second.stats.inspections,1);a.abort();assert.equal(second.inspect(buffer),undefined);b.abort();
});
test('positive graphs reuse exact immutable prepared identity and final helper proof shares the same owned memo',()=>{
 const owner=new AbortController(),cache=new FstGraphCache(owner.signal),buffer=fstTextureAdmissionFbx({nativeEndRecords:true}),before=buffer.slice(0),graph=cache.inspect(buffer);assert(graph);
 assert((cache as any).entries.get(buffer) instanceof WeakRef);assert.equal(cache.inspect(buffer),graph);
 const map=new Texture({width:1,height:1}),template=new MeshBasicMaterial({name:'Replacement',map});
 const proof=prepareFstTextureAdmission(buffer,[{selector:'mat::A',definition:{name:'Replacement',unlit:true,albedoMap:'replacement.png'},template}],[],owner.signal,()=>{},cache);assert(proof);assert.equal(proof.removedTextures,1);
 assert.equal(cache.stats.inspections,1);assert.equal(cache.stats.hits,2);assert.deepEqual(new Uint8Array(buffer),new Uint8Array(before));template.dispose();map.dispose();owner.abort();
});
test('collected positive metadata causes safe observable reinspection without retaining a strong tree',t=>{
 const owner=new AbortController(),cache=new FstGraphCache(owner.signal),buffer=fstTextureAdmissionFbx(),first=cache.inspect(buffer);assert(first);const weak=(cache as any).entries.get(buffer) as WeakRef<typeof first>;
 // Controlled GC boundary only; production uses genuine WeakRef, no factory/hook.
 t.mock.method(weak,'deref',()=>undefined);const next=cache.inspect(buffer);assert(next);assert.notEqual(next,first);assert.deepEqual(next.materials,first.materials);assert.equal(cache.stats.positiveReinspections,1);assert.equal(cache.stats.inspections,2);owner.abort();
});
test('abort/disposal and detached input never return a stale positive or zero graph',()=>{
 const owner=new AbortController(),cache=new FstGraphCache(owner.signal),buffer=fstTextureAdmissionFbx({withoutOriginalTextures:true});cache.inspect(buffer);structuredClone(buffer,{transfer:[buffer]});assert.throws(()=>cache.inspect(buffer),/Detached/);
 owner.abort();assert.equal(cache.stats.disposed,true);assert.throws(()=>cache.inspect(fstTextureAdmissionFbx()),{name:'AbortError'});cache.dispose();
});
