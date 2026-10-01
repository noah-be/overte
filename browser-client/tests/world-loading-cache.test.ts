// SPDX-License-Identifier: Apache-2.0
// Real renderer load/remove methods and actual Three FBX parser. Fetch and the
// worker transport are injected I/O; prepared output is real authored ASCII FBX.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {BoxGeometry,Group,Mesh,MeshStandardMaterial,Scene,TextureLoader,Vector3,type LoadingManager} from 'three';
import {BrowserWorld} from '../src/world';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {ModelLoadScheduler} from '../src/model-load-scheduler';
import {normalizeNativeFbxTransparency} from '../src/baked-fbx';
import type {Entity} from '../src/world-data';
const text=`; FBX 7.4.0 project file
FBXHeaderExtension:  {
\tFBXVersion: 7400
}
Objects:  {
\tGeometry: 201, "Geometry::Body", "Mesh" {
\t\tVertices: *9 {
\t\t\ta: 0,0,0,1,0,0,0,1,0
\t\t}
\t\tPolygonVertexIndex: *3 {
\t\t\ta: 0,1,-3
\t\t}
\t}
\tModel: 401, "Model::Body", "Mesh" {
\t\tProperties70:  {
\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",10,20,30
\t\t}
\t}
\tMaterial: 101, "Material::Body", "" {
\t\tShadingModel: "phong"
\t}
}
Connections:  {
\tC: "OO",201,401
\tC: "OO",101,401
\tC: "OO",401,0
}
`;
const source='https://assets.invalid/authored.fbx';
const methods=BrowserWorld.prototype as unknown as {loadModel(source:string,visited?:Set<string>,base?:string,signal?:AbortSignal):Promise<Group>;queuedModel(source:string,entity:Entity,root:Group):Promise<Group>};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function fixture(){
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),durations:string[]=[];
 let prepares=0;
 Object.assign(context,{options:{resolveAsset:(url:string)=>'https://gateway.invalid/asset?url='+encodeURIComponent(url),onStatus(){}},abort,disposed:false,
   preparedFbx:new PreparedFbxCache({signal:abort.signal}),loadManagers:new Set(),imageCache:{loader:(manager:LoadingManager)=>new TextureLoader(manager)},
   fbxPreparePool:{prepare:async(bytes:ArrayBuffer,signal:AbortSignal)=>{signal.throwIfAborted();prepares++;return{buffer:normalizeNativeFbxTransparency(bytes),phases:{materialBindingsMs:1,decodeMs:2}};}},
   recordLoadPhase(){},recordLoadDuration:(phase:string)=>durations.push(phase),configureAlpha:async()=>{},
 });
 return{context,abort,durations,prepares:()=>prepares};
}
test('actual World FBX path shares one authorized preparation while keeping distinct Three objects and phases counted once',async t=>{
 const {context,abort,durations,prepares}=fixture();let fetches=0;
 t.mock.method(globalThis,'fetch',async(input:unknown)=>{assert.equal(String(input),context.options.resolveAsset(source));fetches++;return new Response(text);});
 const [a,b]=await Promise.all([methods.loadModel.call(context,source),methods.loadModel.call(context,source)]);
 let x!:Mesh,y!:Mesh;a.traverse(object=>{if(object instanceof Mesh)x=object;});b.traverse(object=>{if(object instanceof Mesh)y=object;});
 assert(x&&y);assert.notEqual(a,b);assert.notEqual(x.geometry,y.geometry);assert.notEqual(x.material,y.material);
 assert.deepEqual(Array.from(x.geometry.getAttribute('position').array),[0,0,0,1,0,0,0,1,0]);assert.deepEqual(x.position.toArray(),[10,20,30]);
 assert.equal(fetches,1);assert.equal(prepares(),1);assert.deepEqual(durations,['fbxMaterialBindings','fbxDecode']);
 await methods.loadModel.call(context,source);assert.equal(fetches,1);assert.equal(context.preparedFbx.stats.hits,2);abort.abort();
});
test('actual World reader cancellation preserves another preparation reader but last reader aborts the fetch',async t=>{
 const {context,abort}=fixture();let release!:(value:Response)=>void,owned:AbortSignal|undefined;
 t.mock.method(globalThis,'fetch',async(_input:unknown,options:RequestInit)=>{owned=options.signal as AbortSignal;return new Promise<Response>(resolve=>release=resolve);});
 const a=new AbortController(),b=new AbortController();
 const first=methods.loadModel.call(context,source,undefined,undefined,a.signal),second=methods.loadModel.call(context,source,undefined,undefined,b.signal);
 while(!owned)await flush();const rejected=assert.rejects(first,{name:'AbortError'});a.abort();await rejected;assert.equal(owned.aborted,false);
 release(new Response(text));await second;assert.equal(context.preparedFbx.stats.ready,1);
 let ownedNext:AbortSignal|undefined;t.mock.method(globalThis,'fetch',async(_input:unknown,options:RequestInit)=>{ownedNext=options.signal as AbortSignal;return new Promise<Response>(()=>{});});
 const lastController=new AbortController(),last=methods.loadModel.call(context,source+'?different',undefined,undefined,lastController.signal);
 while(!ownedNext)await flush();const lastRejected=assert.rejects(last,{name:'AbortError'});lastController.abort();await lastRejected;assert.equal(ownedNext.aborted,true);assert.equal(context.preparedFbx.stats.active,0);abort.abort();
});
test('actual entity removal revokes its queued/active reader before disposing the old root',async()=>{
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),scheduler=new ModelLoadScheduler({signal:abort.signal,limit:1});
 const entity:Entity={id:'model',type:'Model',collisionless:true},root=new Group();let owned:AbortSignal|undefined;
 Object.assign(context,{abort,disposed:false,position:new Vector3(),entities:new Map([[entity.id,entity]]),objects:new Map([[entity.id,root]]),modelReaders:new WeakMap(),modelGeometry:new WeakMap(),modelScheduler:scheduler,
   meshCollisions:new Map(),signatures:new Map(),localLights:new Set(),scene:new Scene(),colliders:[],pendingModelColliders:[],restoreModelBatch(){},
   loadModel:async(_source:string,_visited:Set<string>,_base:unknown,signal:AbortSignal)=>{owned=signal;return new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Removed','AbortError')),{once:true}));},
 });
 const promise=methods.queuedModel.call(context,source,entity,root);await flush();assert(owned);const rejected=assert.rejects(promise,{name:'AbortError'});
 context.removeEntities([entity.id]);await rejected;await flush();assert.equal(owned.aborted,true);assert.equal(scheduler.stats.active,0);assert.equal(context.objects.has(entity.id),false);abort.abort();
});
test('actual World queue ranks current native bounds after position-only updates while all six loads remain busy',async()=>{
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),scheduler=new ModelLoadScheduler({signal:abort.signal});
 const started:string[]=[],releases=new Map<string,{promise:Promise<Group>;resolve:(model:Group)=>void}>(),entities=new Map<string,Entity>(),objects=new Map<string,Group>();
 Object.assign(context,{abort,disposed:false,position:new Vector3(),entities,objects,modelReaders:new WeakMap(),modelGeometry:new WeakMap(),modelScheduler:scheduler,meshCollisions:new Map(),recordLoadPhase(){},
   loadModel:async(source:string)=>{started.push(source);return releases.get(source)!.promise;},
 });
 const add=(id:string,x:number)=>{
  const entity:Entity={id,type:'Model',position:{x,y:0,z:0},dimensions:{x:2,y:2,z:2}},root=new Group();root.position.x=x;entities.set(id,entity);objects.set(id,root);
  let resolve!:(model:Group)=>void;const promise=new Promise<Group>(yes=>resolve=yes);releases.set(id,{promise,resolve});return methods.queuedModel.call(context,id,entity,root);
 };
 const promises=Array.from({length:6},(_,i)=>add('busy'+i,i*3));await flush();assert.equal(started.length,6);
 const near=add('originally-near',10),far=add('originally-far',20);await flush();assert.equal(started.length,6);
 // This is the entity-map/root transform update used by native position-only
 // snapshots: the model signature/root ownership remains unchanged.
 entities.set('originally-near',{...entities.get('originally-near')!,position:{x:100,y:0,z:0}});objects.get('originally-near')!.position.x=100;
 entities.set('originally-far',{...entities.get('originally-far')!,position:{x:1,y:0,z:0}});objects.get('originally-far')!.position.x=1;
 const create=()=>{const model=new Group();model.add(new Mesh(new BoxGeometry(),new MeshStandardMaterial()));return model;};
 releases.get(started[0])!.resolve(create());await flush();assert.equal(started[6],'originally-far','Dispatch must use current native collider, not the collider captured at enqueue');
 for(const [id,release]of releases)if(id!==started[0])release.resolve(create());const models=await Promise.all([...promises,near,far]);abort.abort();
 for(const root of objects.values())context.modelGeometry.get(root)?.revoke();
 for(const model of models)model.traverse(object=>{if(object instanceof Mesh){object.geometry.dispose();for(const material of Array.isArray(object.material)?object.material:[object.material])material.dispose();}});
});
