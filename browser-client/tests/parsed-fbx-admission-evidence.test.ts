// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {Mesh,MeshPhongMaterial,Object3D,Texture} from 'three';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {replacementMaterialFbx} from './fixtures/parsed-template-fbx';
import {ParsedFbxTemplates,ParsedFbxTemplateRefusal,disposeParsedFbxGraph,inspectParsedFbxTemplate} from '../src/parsed-fbx-template';
import {ParsedFbxAdmissionEvidence,fbxAdmissionStage,markFbxAdmissionStage} from '../src/parsed-fbx-admission-evidence';
const later=()=>new Promise<void>(resolve=>setImmediate(resolve));
const bytes=()=>replacementMaterialFbx({withoutOriginalTextures:true,vertexColors:true});
const parse=(buffer=bytes())=>new FBXLoader().parse(buffer,'');
const mesh=(root:Object3D)=>{let found:Mesh|undefined;root.traverse(node=>{if(node instanceof Mesh)found??=node;});assert(found);return found;};
const material=(root:Object3D)=>(mesh(root).material as MeshPhongMaterial[])[0];
const graphProducer=async(_signal:AbortSignal,onParsed:(root:Object3D)=>void)=>{const root=parse();material(root).onBeforeCompile=()=>{};onParsed(root);return root;};

test('real FBX producer failure repeats exact bytes/base, with no skip, joined failure counted once and every authority callback retained',async()=>{
 const world=new AbortController(),cache=new ParsedFbxTemplates(world.signal),buffer=bytes();let produced=0,authority=0;
 const producer:typeof graphProducer=async(s,onParsed)=>{produced++;return graphProducer(s,onParsed);};
 const a=cache.get(buffer,'private-route/base',()=>authority++,producer),b=cache.get(buffer,'private-route/base',()=>authority++,producer);
 await Promise.all([assert.rejects(a,ParsedFbxTemplateRefusal),assert.rejects(b,ParsedFbxTemplateRefusal)]);await later();
 await assert.rejects(cache.get(buffer,'private-route/base',()=>authority++,producer),ParsedFbxTemplateRefusal);await later();
 assert.equal(produced,2);assert(authority>=5);assert.equal(cache.statistics.joined,1);
 const evidence=cache.statistics.admissionEvidence;assert.equal(evidence.producerStarts,2);assert.equal(evidence.producerFailures,2);assert.equal(evidence.repeatProducerStarts,1);assert.equal(evidence.repeatAfterGraphRefusal,1);assert.equal(evidence.reasons.graph,2);assert.equal(evidence.stages.materials,2);assert.equal(evidence.locations['provisional-inspection'],2);cache.dispose();
});
test('different prepared identities and texture bases never become same-source evidence',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),buffer=bytes();
 for(const [input,key]of [[buffer,'a'],[buffer.slice(0),'a'],[buffer,'b']] as const){await assert.rejects(cache.get(input,key,()=>{},graphProducer));await later();}
 assert.equal(cache.statistics.admissionEvidence.identityCharges,3);assert.equal(cache.statistics.admissionEvidence.repeatProducerStarts,0);cache.dispose();
});
test('terminal inspection records graph stage without changing original refusal',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),root=parse();material(root).onBeforeCompile=()=>{};
 await assert.rejects(cache.get(bytes(),'base',()=>{},async()=>root),ParsedFbxTemplateRefusal);await later();
 assert.equal(cache.statistics.admissionEvidence.locations['ready-inspection'],1);assert.equal(cache.statistics.admissionEvidence.stages.materials,1);cache.dispose();
});
test('opaque producer failure remains identical, is not structural evidence and contains no reflected private key/message',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),error=Error('PRIVATE_MESSAGE'),buffer=bytes();
 for(let i=0;i<2;i++){await assert.rejects(cache.get(buffer,'PRIVATE_ROUTE',()=>{},async()=>{throw error;}),e=>e===error);await later();}
 const evidence=cache.statistics.admissionEvidence;assert.equal(evidence.reasons.other,2);assert.equal(evidence.repeatProducerStarts,1);assert.equal(evidence.repeatAfterTypedRefusal,0);assert.equal(evidence.repeatAfterGraphRefusal,0);assert(!JSON.stringify(evidence).includes('PRIVATE'));cache.dispose();
});
test('abort and image refusal do not become graph-refusal repeats and still call original producers',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),buffer=bytes();let produced=0;
 for(let i=0;i<2;i++){await assert.rejects(cache.get(buffer,'abort',()=>{},async()=>{produced++;throw new DOMException('private','AbortError');}),{name:'AbortError'});await later();}
 for(let i=0;i<2;i++){await assert.rejects(cache.get(buffer,'image',()=>{},async(_s,onParsed)=>{produced++;const root=parse();material(root).map=new Texture({width:1,height:1,data:new Uint8Array(4)});onParsed(root);return root;}),ParsedFbxTemplateRefusal);await later();}
 const evidence=cache.statistics.admissionEvidence;assert.equal(produced,4);assert.equal(evidence.reasons.abort,2);assert.equal(evidence.reasons.image,2);assert.equal(evidence.repeatAfterGraphRefusal,0);assert.equal(evidence.stages.textures,2);cache.dispose();
});
test('actual inspection preserves errors, refuses getters without calling them and distinguishes node/geometry/material stages',()=>{
 for(const which of ['nodes','geometry','materials']as const){const root=parse();let calls=0;const target=which==='nodes'?root:which==='geometry'?mesh(root).geometry:material(root);Object.defineProperty(target,'untrusted',{configurable:true,get(){calls++;throw Error('must not execute');}});
 let caught:unknown;try{inspectParsedFbxTemplate(root);}catch(e){caught=e;}assert(caught instanceof ParsedFbxTemplateRefusal);assert.equal(fbxAdmissionStage(caught),which);assert.equal(calls,0);delete(target as unknown as Record<string,unknown>).untrusted;disposeParsedFbxGraph(root);}
});
test('foreign error reason getter is never invoked by diagnostic and original error remains unchanged',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),error=new ParsedFbxTemplateRefusal('graph');let calls=0;Object.defineProperty(error,'reason',{get(){calls++;throw Error('not callable');}});
 await assert.rejects(cache.get(bytes(),'base',()=>{},async()=>{throw error;}),e=>e===error);await later();assert.equal(calls,0);assert.equal(cache.statistics.admissionEvidence.reasons.other,1);cache.dispose();
});
test('bounded identity/key metadata refuses evidence only, never producer work; close clears weak metadata',()=>{
 const evidence=new ParsedFbxAdmissionEvidence();for(let i=0;i<513;i++)evidence.start(new ArrayBuffer(1),'key');let snapshot=evidence.snapshot;assert.equal(snapshot.producerStarts,513);assert.equal(snapshot.identityCharges,512);assert(snapshot.censored);
 const keys=new ParsedFbxAdmissionEvidence(),buffer=new ArrayBuffer(1);for(let i=0;i<130;i++)keys.start(buffer,String(i).padEnd(8192,'x'));assert(keys.snapshot.censored);assert(keys.snapshot.keyBytesCharged<=1024*1024);
 const attempt=evidence.start(new ArrayBuffer(1),'ignored'),error=new ParsedFbxTemplateRefusal('graph');markFbxAdmissionStage(error,'geometry');evidence.failure(attempt,error,'producer-rejection','graph');evidence.failure(attempt,error,'producer-rejection','graph');assert.equal(evidence.snapshot.producerFailures,1);evidence.dispose();evidence.start(buffer,'closed');snapshot=evidence.snapshot;assert(snapshot.closed);assert.equal(snapshot.identityCharges,0);assert.equal(snapshot.keyBytesCharged,0);assert.equal(snapshot.producerStarts,514);assert.equal(snapshot.producerFailures,1);keys.dispose();
});
test('ready cache reuse is unchanged and never reported as a new producer',async()=>{
 const cache=new ParsedFbxTemplates(new AbortController().signal),buffer=bytes();let produced=0;
 const producer=async()=>{produced++;return parse();};const a=await cache.get(buffer,'base',()=>{},producer),b=await cache.get(buffer,'base',()=>{},producer);
 assert.equal(produced,1);assert.equal(cache.statistics.hits,1);assert.equal(cache.statistics.admissionEvidence.producerStarts,1);assert.equal(cache.statistics.admissionEvidence.producerFailures,0);disposeParsedFbxGraph(a);disposeParsedFbxGraph(b);cache.dispose();
});
