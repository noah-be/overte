// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from 'three';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {orderedFstTemplates} from '../src/fst-template-window';
import {BrowserWorld} from '../src/world';
import {inspectFbxOriginalTextures} from '../src/baked-fbx';
import {prepareFstTextureAdmission} from '../src/fst-texture-admission';
import {ModelResources} from '../src/model-resources';
import {ModelSlotResidence} from '../src/model-slot-residence';
import {fstTextureAdmissionFbx} from './fixtures/fst-texture-admission';
const turn=()=>new Promise<void>(resolve=>setImmediate(resolve));
function deferred<T>(){let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};}
test('two issued templates overlap genuinely deferred maps and results retain input order',async()=>{
 const abort=new AbortController(),pending=[0,1,2,3].map(()=>deferred<number>()),started:number[]=[],finished:number[]=[],checks:number[]=[];
 const result=orderedFstTemplates([0,1,2,3],async id=>{started.push(id);const value=await pending[id].promise;finished.push(id);return value;},{signal:abort.signal,assertCurrent:()=>{checks.push(started.length);}});
 await turn();assert.deepEqual(started,[0,1]);pending[1].resolve(11);await turn();assert.deepEqual(finished,[1]);assert.deepEqual(started,[0,1]);
 pending[0].resolve(10);await turn();assert.deepEqual(started,[0,1,2,3]);pending[3].resolve(13);pending[2].resolve(12);assert.deepEqual(await result,[10,11,12,13]);assert.ok(checks.length>0);
});
test('38 slow template cohorts need19 release rounds while serial control needs38; window never exceeds2',async()=>{
 async function run(parallel:boolean){let rounds=0,active=0,peak=0;const waiting:(()=>void)[]=[];const create=async(id:number)=>{active++;peak=Math.max(peak,active);await new Promise<void>(resolve=>waiting.push(resolve));active--;return id;};
  const promise=parallel?orderedFstTemplates(Array.from({length:38},(_,i)=>i),create,{signal:new AbortController().signal,assertCurrent:()=>{}}):(async()=>{const result:number[]=[];for(let i=0;i<38;i++)result.push(await create(i));return result;})();
  await turn();while(waiting.length){rounds++;for(const release of waiting.splice(0))release();await turn();}return{rounds,peak,result:await promise};}
 const serial=await run(false),parallel=await run(true);assert.equal(serial.rounds,38);assert.equal(parallel.rounds,19);assert.equal(parallel.peak,2);assert.deepEqual(parallel.result,serial.result);
});
test('failure is thrown at its input index and stops new admission even when observed out of order',async()=>{
 const pending=[deferred<number>(),deferred<number>(),deferred<number>()],started:number[]=[],error=new Error('second refused');
 const result=orderedFstTemplates([0,1,2],id=>{started.push(id);return pending[id].promise;},{signal:new AbortController().signal,assertCurrent:()=>{}});const refused=assert.rejects(result,e=>e===error);
 await turn();pending[1].reject(error);await turn();assert.deepEqual(started,[0,1]);pending[0].resolve(0);await refused;assert.deepEqual(started,[0,1]);
});
test('failed owner waits for its late abort-ignoring template before any resource cleanup',async()=>{
 const owner=new ModelResources(),late=deferred<THREE.Material>(),material=new THREE.MeshBasicMaterial({map:new THREE.Texture()}),error=new Error('first refused');let disposed=0,maps=0,settled=false;
 material.addEventListener('dispose',()=>disposed++);material.map!.addEventListener('dispose',()=>maps++);
 const result=orderedFstTemplates([0,1,2],async id=>{if(id===0)throw error;const value=await late.promise;owner.captureMaterial(value);return value;},{signal:new AbortController().signal,assertCurrent:()=>{}}).finally(()=>{settled=true;owner.releaseKeeping();});const refused=assert.rejects(result,e=>e===error);
 await turn();assert.equal(settled,false);assert.equal(disposed,0);late.resolve(material);await refused;assert.equal(disposed,1);assert.equal(maps,1);owner.releaseKeeping();assert.equal(disposed,1);
});
test('parent cancellation aborts the exact two readers, keeps slot pending until both settle, admits nothing else',async()=>{
 const abort=new AbortController(),late=[deferred<number>(),deferred<number>()],signals:AbortSignal[]=[];let settled=false;
 const result=orderedFstTemplates([0,1,2],(id,signal)=>{signals.push(signal);return late[id].promise;},{signal:abort.signal,assertCurrent:()=>{}}).finally(()=>{settled=true;});const refused=assert.rejects(result,{name:'AbortError'});
 await turn();abort.abort();assert.equal(signals.length,2);assert.ok(signals.every(s=>s.aborted));await turn();assert.equal(settled,false);late[0].resolve(0);await turn();assert.equal(settled,false);late[1].resolve(1);await refused;
});
test('stale authority after first completion cancels remaining producer without publishing a list',async()=>{
 const first=deferred<number>(),second=deferred<number>(),failure=new Error('authority retired');let current=true;const signals:AbortSignal[]=[];
 const result=orderedFstTemplates([0,1,2],(id,signal)=>{signals.push(signal);return id===0?first.promise:second.promise;},{signal:new AbortController().signal,assertCurrent:()=>{if(!current)throw failure;}});const refused=assert.rejects(result,e=>e===failure);
 await turn();current=false;first.resolve(0);await turn();assert.equal(signals.length,2);assert.ok(signals[1].aborted);second.resolve(1);await refused;
});
test('malformed/oversized plans and already-aborted owners create no templates',async()=>{
 let calls=0;const create=async()=>{calls++;return 0;},options={signal:new AbortController().signal,assertCurrent:()=>{}};
 for(const value of [null,{},new Array(257)])await assert.rejects(orderedFstTemplates(value as any,create,options),/Invalid complete/);
 const abort=new AbortController();abort.abort();await assert.rejects(orderedFstTemplates([0],create,{...options,signal:abort.signal}),{name:'AbortError'});assert.equal(calls,0);assert.deepEqual(await orderedFstTemplates([],create,options),[]);
});
function world(plan:Record<string,string>[],extra:Record<string,unknown>={}){
 const object=Object.create(BrowserWorld.prototype),abort=new AbortController(),buffer=fstTextureAdmissionFbx(),textures:THREE.Texture[]=[],materials:THREE.Material[]=[],disposedMaterials:THREE.Material[]=[],readers:((value:THREE.Texture)=>void)[]=[],events:string[]=[];
 const definitions=Object.fromEntries(plan.flatMap((part,i)=>Object.values(part).map(reference=>[reference,{name:i===0?'Renamed':`Final${i}`,unlit:true,albedoMap:`image${i}.png`,...extra}])));
 let current=true;
 Object.assign(object,{abort,disposed:false,options:{onStatus:()=>{},captureAssetAuthority:()=>({assertCurrent:()=>{if(!current)throw Error('retired authority');}})},nativeCullDefaults:false,replacementClonesEnabled:false,
  sourceText:async(url:string)=>url.endsWith('.fst')?`filename = authored.fbx\nmaterialMap = ${JSON.stringify(plan)}`:JSON.stringify({materials:[definitions[new URL(url).pathname.slice(1)]]}),
  loadPreparedFbx:async()=>({buffer}),fstGraphCache:{inspect:()=>inspectFbxOriginalTextures(buffer)},recordLoadPhase:()=>{},
  texture:()=>new Promise<THREE.Texture>(resolve=>readers.push(value=>{textures.push(value);resolve(value);})),configureAlpha:async()=>{},
  makeMaterial:async(...args:unknown[])=>{events.push('create');const material=await (BrowserWorld.prototype as any).makeMaterial.apply(object,args);materials.push(material);material.addEventListener('dispose',()=>disposedMaterials.push(material));return material;},
  loadModel:(source:string,...args:unknown[])=>{
   if(!source.endsWith('.fbx'))return (BrowserWorld.prototype as any).loadModel.call(object,source,...args);
   events.push('child');const admission=args[4] as any;let input=buffer;
   if(admission?.replacements){const result=prepareFstTextureAdmission(buffer,admission.replacements,[],abort.signal,admission.assertCurrent);assert(result);input=result.buffer;}
   const manager=new THREE.LoadingManager();class Loader extends THREE.Loader{override load(){events.push('original-image');return new THREE.Texture({width:1,height:1});}}
   manager.addHandler(/\.png$/,new Loader(manager));const model=new FBXLoader(manager).parse(input,'https://fixture.invalid/');const publish=args[3] as((model:THREE.Object3D)=>void)|undefined;publish?.(model);return Promise.resolve(model);
  }});
 return{object,abort,buffer,textures,materials,disposedMaterials,readers,events,revoke:()=>{current=false;}};
}
test('actual World only overlaps complete proven templates; genuine FBX binding/name effects remain ordered, geometry waits',async()=>{
 const f=world([{all:'0.json'},{'mat::Renamed':'1.json'},{'mat::Final1':'2.json'}]),geometry:THREE.Object3D[]=[];
 const result=f.object.loadModel('https://fixture.invalid/authored.fst',new Set(),undefined,f.abort.signal,(model:THREE.Object3D)=>geometry.push(model));
 await turn();assert.equal(f.readers.length,2);assert.equal(geometry.length,0);assert.ok(!f.events.includes('child'));
 f.readers[1](new THREE.Texture({width:1,height:1}));await turn();assert.equal(f.readers.length,2);f.readers[0](new THREE.Texture({width:1,height:1}));await turn();assert.equal(f.readers.length,3);
 f.readers[2](new THREE.Texture({width:1,height:1}));const model=await result;assert.deepEqual(geometry,[model]);assert.ok(!f.events.includes('original-image'));
 let meshes=0;model.traverse((part:THREE.Object3D)=>{if(part instanceof THREE.Mesh){meshes++;for(const material of(Array.isArray(part.material)?part.material:[part.material])){assert.equal(material.name,'Final2');assert.equal(((material as THREE.MeshBasicMaterial).map!.image as {width:number}).width,1);}}});assert.equal(meshes,1);assert.equal(f.materials.length,3);assert.equal(f.disposedMaterials.length,3);assert.equal(new Set(f.disposedMaterials).size,3);
 const resources=new ModelResources();resources.capture(model);resources.releaseKeeping();
});
test('unknown/fallthrough definition retains original serial template and original FBX image route',async()=>{
 const f=world([{'mat::A':'0.json'},{'mat::Renamed':'1.json'}],{defaultFallthrough:true});const result=f.object.loadModel('https://fixture.invalid/authored.fst');
 await turn();assert.equal(f.readers.length,1);assert.ok(f.events.includes('child'));assert.ok(f.events.includes('original-image'));f.readers[0](new THREE.Texture({width:1,height:1}));await turn();assert.equal(f.readers.length,2);f.readers[1](new THREE.Texture({width:1,height:1}));const model=await result;const owner=new ModelResources();owner.capture(model);owner.releaseKeeping();
});
test('actual World cancellation captures/disposes each late template and prevents child geometry',async()=>{
 const f=world([{all:'0.json'},{all:'1.json'},{all:'2.json'}]);const result=f.object.loadModel('https://fixture.invalid/authored.fst');const rejected=assert.rejects(result,{name:'AbortError'});await turn();assert.equal(f.readers.length,2);f.abort.abort();
 let disposed=0;for(const release of f.readers){const texture=new THREE.Texture({width:1,height:1});texture.addEventListener('dispose',()=>disposed++);release(texture);}await rejected;assert.equal(disposed,2);assert.ok(!f.events.includes('child'));assert.equal(f.readers.length,2);
});
test('actual concurrent World trace uses one exclusive template phase with uncensored independent waits',async()=>{
 const f=world([{all:'0.json'},{all:'1.json'}]),observer=new ModelSlotResidence(f.abort.signal),token=observer.start({},f.abort.signal)!;token.dispatch();const result=f.object.loadModel('https://fixture.invalid/authored.fst',new Set(),undefined,f.abort.signal,undefined,undefined,token);
 await turn();assert.equal(f.readers.length,2);f.readers[1](new THREE.Texture({width:1,height:1}));await turn();f.readers[0](new THREE.Texture({width:1,height:1}));const model=await result;token.loaderFinished();token.finish('completed');const row=observer.snapshot().recent[0];assert.equal(row.terminal,'completed');assert.equal(row.fst!.templateAttempts,2);assert.equal(row.fst!.templateCompleted,2);assert.equal(row.fst!.waits['map-readers'].completed,2);assert.equal(row.fst!.waitsCensored,false);const resources=new ModelResources();resources.capture(model);resources.releaseKeeping();
});
test('source keeps global six image slots/30s deadline, six model slots and exact complete-proof gate',()=>{
 const worldSource=readFileSync(new URL('../src/world.ts',import.meta.url),'utf8'),images=readFileSync(new URL('../src/world-image-cache.ts',import.meta.url),'utf8'),scheduler=readFileSync(new URL('../src/model-load-scheduler.ts',import.meta.url),'utf8');
 assert.ok(worldSource.indexOf('canFstDefinitionsReplaceOriginalTextures(inspection,definitions)')<worldSource.indexOf('preloaded=await orderedFstTemplates('));assert.match(images,/maximumActive=options.maximumActive\?\?6/);assert.match(images,/deadlineMs=options.deadlineMs\?\?30000/);assert.match(scheduler,/limit=options.limit\?\?6/);
});
