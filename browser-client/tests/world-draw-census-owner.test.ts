// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {BrowserWorld} from '../src/world';
const geometry=()=>new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3));
function fixture(){
 const world:any=Object.create(BrowserWorld.prototype),abort=new AbortController(),objects=new Map<string,T.Object3D>(),entities=new Map<string,Record<string,unknown>>();let current=true,checks=0;
 Object.assign(world,{disposed:false,enabled:true,abort,objects,entities,options:{captureAssetAuthority:()=>({assertCurrent(){checks++;if(!current)throw Error('Synthetic revoked authority');}})}});
 const add=(id:string,props:Record<string,unknown>={})=>{const root=new T.Group();root.userData.modelLoaded=true;root.add(new T.Mesh(geometry(),new T.MeshBasicMaterial()));objects.set(id,root);entities.set(id,{id,type:'Model',...props});return root;};
 return{world,abort,objects,entities,add,revoke(){current=false;},checks:()=>checks};
}
for(const reason of ['disabled','disposed','aborted','no-authority','capture-refused'])test('actual BrowserWorld diagnostic refuses '+reason+' without iterating model resources',()=>{
 const f=fixture();let resourceReads=0;f.add('own');f.objects[Symbol.iterator]=function*(){resourceReads++;yield* Map.prototype.entries.call(this);return undefined;};
 if(reason==='disabled')f.world.enabled=false;if(reason==='disposed')f.world.disposed=true;if(reason==='aborted')f.abort.abort();if(reason==='no-authority')f.world.options.captureAssetAuthority=undefined;if(reason==='capture-refused')f.world.options.captureAssetAuthority=()=>{throw Error('Synthetic private denial');};
 const r=f.world.getDrawCensus();assert(r.partial);assert(r.reasons['owner-revoked']);assert.equal(r.counts.owners,0);assert.equal(resourceReads,0);assert(!JSON.stringify(r).includes('Synthetic private denial'));
});
test('actual World generator classifies entity dynamics, scripts, animation, parenting and Material children',()=>{
 const f=fixture();f.add('static',{velocity:{x:0,y:0,z:0},angularVelocity:{x:0,y:0,z:0},parentID:'{00000000-0000-0000-0000-000000000000}'});f.add('dynamic',{dynamic:true});f.add('moving',{velocity:{x:.01,y:0,z:0}});f.add('turning',{angularVelocity:{x:0,y:.01,z:0}});f.add('scripted',{script:'synthetic-script'});f.add('server-scripted',{serverScripts:'synthetic-server-script'});f.add('parented',{parentID:'11111111-1111-1111-1111-111111111111'});f.add('animated',{animation:{url:'synthetic-animation'}});f.add('running-animation',{animation:{running:true}});f.add('material-owner');f.entities.set('material-child',{id:'material-child',type:'Material',parentID:'material-owner'});
 const r=f.world.getDrawCensus();assert.equal(r.partial,false);assert.equal(r.counts.candidateParts,1);assert.equal(r.reasons.dynamic,3);assert.equal(r.reasons.scripted,2);assert.equal(r.reasons['native-parent'],1);assert.equal(r.reasons.animation,2);assert.equal(r.reasons['material-child'],1);
});
test('actual World generator excludes a loaded object with missing native entity facts',()=>{
 const f=fixture();f.add('orphan');f.entities.delete('orphan');const r=f.world.getDrawCensus();assert.equal(r.counts.candidateParts,0);assert.equal(r.reasons.dynamic,1);
});
test('authority revoked between actual owner iterator yields stops the later owner and terminal grouping',()=>{
 const f=fixture();f.add('first');f.add('second');f.objects[Symbol.iterator]=function*(){const entries=Map.prototype.entries.call(this);yield entries.next().value!;f.revoke();yield entries.next().value!;return undefined;};
 const r=f.world.getDrawCensus();assert(r.partial);assert(r.reasons['owner-revoked']);assert.equal(r.counts.owners,1);assert.equal(r.counts.candidateParts,1);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert(f.checks()>1);
});
test('actual World diagnostic captures one fixed authority snapshot per invocation',()=>{
 const f=fixture();f.add('first');let captures=0;f.world.options.captureAssetAuthority=()=>{captures++;return{assertCurrent(){}};};const r=f.world.getDrawCensus();assert.equal(captures,1);assert.equal(r.counts.candidateParts,1);
});
