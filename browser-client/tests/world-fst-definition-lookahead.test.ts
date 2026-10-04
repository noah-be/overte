// SPDX-License-Identifier: Apache-2.0
// Actual FST loader/material methods; authored CPU geometry/dependency boundaries.
// This is not an actual FBX/network/renderer qualification.
import test from 'node:test';import assert from 'node:assert/strict';import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
const deferred=<T>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};};const tick=()=>new Promise<void>(r=>setImmediate(r));
function fixture(enabled:boolean,maps='[{"all":"first.json"},{"mat::first":"second.json"}]',child='owned.fbx'){
 const object=Object.create(BrowserWorld.prototype),abort=new AbortController(),gate=deferred<THREE.Texture>(),events:string[]=[],textures:THREE.Texture[]=[],model=new THREE.Group();let current=true;
 const old=new THREE.MeshBasicMaterial();old.name='original';model.add(new THREE.Mesh(new THREE.BoxGeometry(),old));
 Object.assign(object,{abort,disposed:false,fstDefinitionLookaheadEnabled:enabled,fstLookaheadCounts:{started:0,consumed:0,capacityFallback:0},replacementClonesEnabled:false,nativeCullDefaults:false,options:{onStatus(){},captureAssetAuthority:()=>({assertCurrent(){if(!current)throw new DOMException('Authority ended','AbortError');}})},fstGraphCache:{inspect:()=>undefined},recordLoadPhase(){},loadPreparedFbx:async()=>{events.push('prepared');return {buffer:new ArrayBuffer(8)};},sourceText:async(url:string,_l:unknown,_m:unknown,signal:AbortSignal)=>{signal.throwIfAborted();if(url.endsWith('.fst'))return 'filename = '+child+'\nscale = 2\nmaterialMap = '+maps;const first=url.endsWith('first.json');events.push(first?'read-first':'read-second');return JSON.stringify({materials:[{name:first?'first':'second',unlit:true,albedoMap:first?'first.png':'second.png',albedo:first?[1,0,0]:[0,1,0]}]});},texture:async(url:string)=>{events.push(url.endsWith('first.png')?'map-first':'map-second');const t=url.endsWith('first.png')?await gate.promise:new THREE.Texture();textures.push(t);return t;},configureAlpha:async()=>{events.push('alpha');}});
 object.loadModel=(url:string,...args:unknown[])=>url.endsWith('.fbx')||url.endsWith('.gltf')?(events.push('geometry'),(args[3]as ((r:THREE.Group)=>void)|undefined)?.(model),Promise.resolve(model)):(BrowserWorld.prototype as any).loadModel.call(object,url,...args);
 const start=()=>object.loadModel('https://example.invalid/owned.fst',new Set(),undefined,abort.signal,(root:THREE.Group)=>{events.push('published');assert.equal(root.userData.avatarMapping.scale,2);});
 return {object,abort,gate,events,model,textures,start,revoke(){current=false;}};
}
test('actual direct FST next immutable definition overlaps map wait; real makeMaterial and selector application stay ordered',async()=>{
 for(const enabled of [false,true]){const f=fixture(enabled),result=f.start();void result.catch(()=>{});await tick();assert(f.events.includes('published'));assert(!f.events.includes('map-second'));assert.equal(f.events.includes('read-second'),enabled);f.gate.resolve(new THREE.Texture());const root=await result;const material=(root.children[0]as THREE.Mesh).material as THREE.MeshBasicMaterial;assert.equal(material.name,'second');assert.equal(material.color.g,1);assert.equal(material.color.r,0);assert(f.events.indexOf('map-second')>f.events.indexOf('alpha'));assert.equal(f.object.fstLookaheadCounts.started,enabled?1:0);for(const t of f.textures)t.dispose();material.dispose();(root.children[0]as THREE.Mesh).geometry.dispose();}
});
test('single and non-FBX mapping preserve ordinary geometry-first ordered definition path with opt-in',async()=>{
 for(const [maps,child]of [['[{"all":"first.json"}]','owned.fbx'],['[{"all":"first.json"},{"mat::first":"second.json"}]','owned.gltf']]){const f=fixture(true,maps,child),p=f.start();await tick();assert(f.events.includes('published'));assert(!f.events.includes('read-second'));f.gate.resolve(new THREE.Texture());await p;assert.equal(f.object.fstLookaheadCounts.started,0);}
});
test('actual FST authority loss after image wait retires staged geometry and templates without second material publication',async()=>{
 const f=fixture(true),p=f.start(),terminal=assert.rejects(p,{name:'AbortError'});await tick();const texture=new THREE.Texture();let releases=0;texture.addEventListener('dispose',()=>releases++);f.revoke();f.gate.resolve(texture);await terminal;assert(!f.events.includes('map-second'));assert.equal(releases,1);
});
test('over-budget flat mapping preserves existing serial fallback and original assignment limit',async()=>{
 const map:Record<string,string>={all:'first.json'};for(let i=0;i<256;i++)map['mat::absent-'+i]='second.json';
 const f=fixture(true,JSON.stringify([map])),p=f.start();void p.catch(()=>{});await tick();assert(!f.events.includes('read-second'));assert(!f.events.includes('prepared'));f.gate.resolve(new THREE.Texture());const root=await p;assert.equal(f.object.fstLookaheadCounts.started,0);assert.equal(((root.children[0]as THREE.Mesh).material as THREE.MeshBasicMaterial).name,'first');
 const invalid=fixture(true,JSON.stringify(Array.from({length:257},()=>({all:'first.json'}))));await assert.rejects(invalid.start(),/Invalid baked material map/);assert(!invalid.events.includes('geometry'));
});
