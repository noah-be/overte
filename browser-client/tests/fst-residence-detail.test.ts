// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {BrowserWorld} from '../src/world';
import {OriginalFstMaterial as OriginalWorld} from './fixtures/fst-residence-original-material';
import {ModelSlotResidence} from '../src/model-slot-residence';
function clock(){let time=0,reads=0;const abort=new AbortController(),owner=new ModelSlotResidence(abort.signal,()=>{reads++;return time;});return {owner,abort,tick:(n:number)=>{time=n;},reads:()=>reads};}
test('two template attempts and map readers counted without clock or source access',()=>{
 const f=clock(),token=f.owner.start({get source(){throw Error('private');}},new AbortController().signal)!;const reads=f.reads();token.fstCount('mapping');for(let i=0;i<2;i++){token.fstCount('template-attempt');token.fstCount('map-reader');token.fstCount('template-completed');}assert.equal(f.reads(),reads);token.finish('completed');const detail=f.owner.snapshot().recent[0].fst!;assert.equal(detail.mappingCount,1);assert.equal(detail.templateAttempts,2);assert.equal(detail.templateCompleted,2);assert.equal(detail.mapReaderAttempts,2);assert.equal(detail.countsCensored,false);assert.ok(!JSON.stringify(detail).includes('private'));
});
test('overlapping template substage intervals never use or censor nested exclusive stack',()=>{
 const f=clock(),token=f.owner.start({},new AbortController().signal)!;token.dispatch();const span=token.span('fst-template');f.tick(1);const maps=token.fstWait('map-readers');f.tick(3);const alpha=token.fstWait('alpha');f.tick(5);maps();f.tick(8);alpha();span();token.loaderFinished();token.finish('completed');const row=f.owner.snapshot().recent[0];assert.equal(row.terminal,'completed');assert.equal(row.exclusiveLeafWallMs['fst-template'],8);assert.equal(Object.values(row.exclusiveLeafWallMs).reduce((a,b)=>a+b,0),8);assert.equal(row.fst!.waits['map-readers'].totalWallMs,4);assert.equal(row.fst!.waits.alpha.totalWallMs,5);assert.equal(row.fst!.waitsCensored,false);
});
test('observer abort suppresses late callbacks and clock reads, records incomplete interval',()=>{
 const f=clock(),signal=new AbortController(),token=f.owner.start({},signal.signal)!;const end=token.fstWait('alpha');f.tick(4);signal.abort();const reads=f.reads();end();token.fstCount('template-completed');token.fstWait('map-readers')();assert.equal(f.reads(),reads);const row=f.owner.snapshot().recent[0];assert.equal(row.terminal,'cancelled');assert.equal(row.fst!.waits.alpha.completed,0);assert.equal(row.fst!.waitsCensored,true);
});
test('fixed count and interval bounds censor details without application-owner retirement',()=>{
 const f=clock(),token=f.owner.start({},new AbortController().signal)!;for(let i=0;i<257;i++){token.fstCount('map-reader');token.fstWait('map-readers')();}assert.equal(f.owner.snapshot().active,1);token.finish('completed');const detail=f.owner.snapshot().recent[0].fst!;assert.equal(detail.mapReaderAttempts,256);assert.equal(detail.waits['map-readers'].started,256);assert.equal(detail.countsCensored,true);assert.equal(detail.waitsCensored,true);
});
test('snapshot detached copies cannot mutate retained metrics and final report remains bounded',()=>{
 const f=clock();for(let i=0;i<512;i++){const token=f.owner.start({},new AbortController().signal)!;token.fstCount('mapping');token.fstCount('template-attempt');token.fstWait('alpha')();f.tick(i+1);token.finish('completed');}const a=f.owner.snapshot();a.recent[0].fst!.waits.alpha.completed=999;assert.equal(f.owner.snapshot().recent[0].fst!.waits.alpha.completed,1);assert.ok(Buffer.byteLength(JSON.stringify(f.owner.snapshot()))<=128*1024);assert.equal(f.owner.snapshot().reportCensored,false);assert.equal(f.owner.snapshot().recent.length,64);
});
function materialWorld(proto:object){
 const object=Object.create(proto);const abort=new AbortController(),calls:unknown[][]=[];Object.assign(object,{abort,options:{onStatus:()=>{}},nativeCullDefaults:false,texture:async(...args:unknown[])=>{calls.push(args);return new THREE.Texture();},configureAlpha:async(...args:unknown[])=>{calls.push(['alpha',...args]);}});return {object,abort,calls};
}
test('actual current makeMaterial off-path retains original requests, alpha and clock calls',async()=>{
 const performanceDescriptor=Object.getOwnPropertyDescriptor(globalThis,'performance')!;let reads=0;Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>++reads}});
 try{
  const execute=async(proto:object)=>{const w=materialWorld(proto),before=reads;const m=await w.object.makeMaterial({name:'authored',unlit:false,albedoMap:'a.png',normalMap:'n.png',opacityMap:'a.png'},'https://example.invalid/m.json',w.abort.signal);return {reads:reads-before,calls:w.calls.map(([first,...rest])=>first==='alpha'?[first,(rest[1]as any).useAlpha]:[first]),material:m};};
  const a=await execute(BrowserWorld.prototype),b=await execute(OriginalWorld.prototype);assert.equal(a.reads,b.reads);assert.deepEqual(a.calls,b.calls);assert.equal(a.material.type,b.material.type);a.material.dispose();b.material.dispose();
 }finally{Object.defineProperty(globalThis,'performance',performanceDescriptor);}
});
test('actual makeMaterial map cohort remains concurrent; independent alpha wait and readers observed',async()=>{
 const f=clock(),token=f.owner.start({},new AbortController().signal)!,w=materialWorld(BrowserWorld.prototype),releases:((value:THREE.Texture)=>void)[]=[];
 w.object.texture=()=>new Promise<THREE.Texture>(resolve=>releases.push(resolve));w.object.configureAlpha=async()=>{f.tick(9);};f.tick(1);const result=w.object.makeMaterial({albedoMap:'a.png',normalMap:'n.png'},undefined,w.abort.signal,token);assert.equal(releases.length,2);f.tick(6);for(const release of releases)release(new THREE.Texture());const m=await result;token.finish('completed');const detail=f.owner.snapshot().recent[0].fst!;assert.equal(detail.mapReaderAttempts,2);assert.equal(detail.waits['map-readers'].totalWallMs,5);assert.equal(detail.waits.alpha.totalWallMs,3);m.map?.dispose();m.normalMap?.dispose();m.dispose();
});
test('actual material map failure identity and late successful-map disposal remain unchanged',async()=>{
 const f=clock(),token=f.owner.start({},new AbortController().signal)!,w=materialWorld(BrowserWorld.prototype),error=new Error('authored refusal'),map=new THREE.Texture();let disposed=0;map.addEventListener('dispose',()=>{disposed++;});w.object.texture=async(url:string)=>{if(url==='a.png')throw error;return map;};await assert.rejects(w.object.makeMaterial({albedoMap:'a.png',normalMap:'n.png'},undefined,w.abort.signal,token),e=>e===error);token.finish('refused');assert.equal(disposed,1);assert.equal(f.owner.snapshot().recent[0].fst!.waits['map-readers'].completed,1);assert.equal(f.owner.snapshot().recent[0].fst!.waits.alpha.started,0);
});
test('actual FST two ordered replacements now expose count and preserve nested authority checks',async()=>{
 const f=clock(),token=f.owner.start({},new AbortController().signal)!,w=materialWorld(BrowserWorld.prototype),model=new THREE.Group();for(const name of ['one','two']){const m=new THREE.MeshBasicMaterial();m.name=name;model.add(new THREE.Mesh(new THREE.BoxGeometry(),m));}let current=0;
 w.object.options.captureAssetAuthority=()=>({assertCurrent:()=>{current++;}});w.object.sourceText=async(url:string)=>url.endsWith('.fst')?'filename = authored.fbx\nmaterialMap = [{"mat::one":"one.json"},{"mat::two":"two.json"}]':JSON.stringify({materials:[{name:'authored',unlit:true}]});w.object.loadPreparedFbx=async()=>({buffer:new ArrayBuffer(8)});w.object.fstGraphCache={inspect:()=>undefined};w.object.recordLoadPhase=()=>{};w.object.loadModel=(source:string,...args:unknown[])=>source.endsWith('.fbx')?Promise.resolve(model):(BrowserWorld.prototype as any).loadModel.call(w.object,source,...args);
 const output=await w.object.loadModel('https://example.invalid/authored.fst',new Set(),undefined,w.abort.signal,undefined,undefined,token);assert.equal(output,model);token.finish('completed');const detail=f.owner.snapshot().recent[0].fst!;assert.equal(detail.mappingCount,1);assert.equal(detail.templateAttempts,2);assert.equal(detail.templateCompleted,2);assert.ok(current>=8);for(const child of model.children as THREE.Mesh[]){child.geometry.dispose();(child.material as THREE.Material).dispose();}
});
