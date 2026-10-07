// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {spawnSync} from 'node:child_process';
import {censusWorldDraws,type DrawCensusOwner} from '../src/world-draw-census';
import {censusWorldDrawsAsync} from '../src/world-draw-census-async';
const geometry=()=>new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3));
const owner=(root:T.Object3D):DrawCensusOwner=>({root,loaded:true,dynamic:false,scripted:false,parented:false,materialChildren:false});
function scene(count=293){const g=geometry(),m=new T.MeshBasicMaterial();return Array.from({length:count},()=>owner(new T.Mesh(g,m)));}
function clock(){let time=0;return()=>time+=.002;}
const options=()=>({signal:new AbortController().signal,isCurrent:()=>true,isRevisionCurrent:()=>true});
test('complete 293 static owners use multiple owned task turns with the same exact grouping as the synchronous census',async()=>{
 const owners=scene(),sync=censusWorldDraws(owners,{signal:new AbortController().signal,isCurrent:()=>true,now:()=>0});
 const report=await censusWorldDrawsAsync(owners,{...options(),now:clock(),maximumSliceMs:1});
 assert.equal(report.partial,false);assert.equal(report.counts.owners,293);assert.equal(report.counts.meshes,293);assert.equal(report.counts.drawParts,293);assert(report.scheduling.taskSlices>1);
 assert.deepEqual(report.exactGeometryAndMaterialIdentity,sync.exactGeometryAndMaterialIdentity);assert.deepEqual(report.exactGeometryAndAuditedMaterialValues,sync.exactGeometryAndAuditedMaterialValues);
 assert.equal(report.counts.geometryBytesRead,72,'The shared36byte geometry is copied once and verified once');assert.equal(report.resources.geometryIdentities,1);
});
test('293 independently parsed equivalent geometries keep exact byte classification and material values',async()=>{
 const original=scene(1)[0].root as T.Mesh;const owners=Array.from({length:293},()=>owner(new T.Mesh(original.geometry.clone(),(original.material as T.MeshBasicMaterial).clone())));
 const report=await censusWorldDrawsAsync(owners,{...options(),now:clock(),maximumSliceMs:1});
 assert.equal(report.partial,false);assert.equal(report.counts.owners,293);assert.equal(report.resources.geometryIdentities,293);assert.equal(report.resources.geometryByteClasses,1);
 assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert.equal(report.exactGeometryAndAuditedMaterialValues.members,293);
});
test('a revoked source-owned World revision between tasks censors every terminal group',async()=>{
 let revisions=0;const report=await censusWorldDrawsAsync(scene(),{...options(),now:clock(),maximumSliceMs:1,isRevisionCurrent:()=>++revisions<2});
 assert.equal(report.partial,true);assert(report.reasons['owner-revision-changed']);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert(report.counts.owners<293);
});
test('owner abort during a real queued task settles and never reports complete grouping',async()=>{
 const controller=new AbortController();const pending=censusWorldDrawsAsync(scene(),{...options(),signal:controller.signal,now:clock(),maximumSliceMs:1});controller.abort();
 const report=await pending;assert.equal(report.partial,true);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert(report.reasons['owner-revoked']);
});
for(const field of ['position','quaternion','matrix','matrixWorld','children','material','geometry','color','source','sampler','attributeVersion','attributeBytes','getter']as const)test('inter-task '+field+' mutation cannot retain complete grouping',async()=>{
 const owners=scene(),mesh=owners[0].root as T.Mesh;const texture=new T.Texture();(mesh.material as T.MeshBasicMaterial).map=texture;
 let calls=0;let getters=0;
 const report=await censusWorldDrawsAsync(owners,{...options(),now:clock(),maximumSliceMs:1,isRevisionCurrent:()=>{
  if(++calls===2){
   if(field==='position')mesh.position.x=10;if(field==='quaternion')mesh.quaternion.x=.1;
   if(field==='matrix')mesh.matrix.elements[12]=10;if(field==='matrixWorld')mesh.matrixWorld.elements[12]=10;
   if(field==='children')mesh.add(new T.Group());if(field==='material')mesh.material=new T.MeshBasicMaterial();if(field==='geometry')mesh.geometry=geometry();
   if(field==='color')(mesh.material as T.MeshBasicMaterial).color.r=.3;
   if(field==='source')texture.source=new T.TextureSource({});if(field==='sampler')texture.wrapS=T.RepeatWrapping;
   if(field==='attributeVersion')mesh.geometry.attributes.position.needsUpdate=true;
   if(field==='attributeBytes')mesh.geometry.attributes.position.setX(0,17);
   if(field==='getter')Object.defineProperty(mesh,'visible',{get(){getters++;throw Error('Private getter must not run');}});
  }return true;
 }});
 assert.equal(report.partial,true);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert(report.reasons['resource-revision-changed']);assert.equal(getters,0);
});
test('separate geometry index/layout changes never collapse to the same byte class',async()=>{
 const a=geometry().setIndex([0,1,2]),b=a.clone();b.index!.setX(2,1);const m=new T.MeshBasicMaterial();
 const report=await censusWorldDrawsAsync([owner(new T.Mesh(a,m)),owner(new T.Mesh(b,m))],options());
 assert.equal(report.partial,false);assert.equal(report.resources.geometryByteClasses,2);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);
});
for(const [key,value,reason]of [['maximumOwners',2,'owner-count-budget'],['maximumNodes',2,'node-count-budget'],['maximumParts',2,'draw-part-budget'],['maximumBytes',1,'geometry-byte-budget'],['maximumMetadataBytes',1,'metadata-byte-budget']]as const)test('unchanged '+key+' aggregate budget remains fail-closed across turns',async()=>{
 const report=await censusWorldDrawsAsync(scene(3),{...options(),[key]:value});assert.equal(report.partial,true);assert(report.reasons[reason]);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);
});
test('total CPU deadline includes every active slice instead of resetting the aggregate budget',async()=>{
 const report=await censusWorldDrawsAsync(scene(),{...options(),now:clock(),maximumSliceMs:1,maximumTotalCpuMs:3});
 assert.equal(report.partial,true);assert(report.reasons['total-cpu-deadline']);assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);
});
test('asynchronous scheduling cannot raise its explicit2000ms aggregate CPU maximum',async()=>{
 await assert.rejects(censusWorldDrawsAsync(scene(),{...options(),maximumTotalCpuMs:2001}),/Invalid asynchronous draw census bound/);
});
test('late grouping-budget refusal zeros an already computed first grouping',async()=>{
 const owners=scene(3),full=await censusWorldDrawsAsync(owners,options());assert.equal(full.partial,false);assert.equal(full.exactGeometryAndMaterialIdentity.groups,1);
 const censored=await censusWorldDrawsAsync(owners,{...options(),maximumMetadataBytes:full.counts.metadataBytes-1});
 assert(censored.partial);assert(censored.reasons['metadata-byte-budget']);assert.equal(censored.exactGeometryAndMaterialIdentity.groups,0);assert.equal(censored.exactGeometryAndAuditedMaterialValues.groups,0);
});
test('already-revoked owner never reads the model iterable',async()=>{
 const controller=new AbortController();controller.abort();let reads=0;
 const owners={*[Symbol.iterator](){reads++;yield owner(new T.Mesh(geometry(),new T.MeshBasicMaterial()));}};
 const report=await censusWorldDrawsAsync(owners,{...options(),signal:controller.signal});assert.equal(reads,0);assert.equal(report.counts.owners,0);assert.equal(report.partial,true);
});
test('diagnostic retains matrices, shader versions and disposal ownership without publishing names/addresses',async()=>{
 const owners=scene(2),mesh=owners[0].root as T.Mesh;mesh.name='private-identity';const material=mesh.material as T.MeshBasicMaterial;material.map=new T.Texture({src:'https://private.example/account'});
 const before={matrix:[...mesh.matrix.elements],world:[...mesh.matrixWorld.elements],position:mesh.position.clone(),version:material.version,texture:material.map,source:material.map.source};let writes=0;mesh.updateMatrix=()=>{writes++;};mesh.geometry.dispose=()=>{writes++;};material.dispose=()=>{writes++;};
 const report=await censusWorldDrawsAsync(owners,options());assert.equal(writes,0);assert.deepEqual([...mesh.matrix.elements],before.matrix);assert.deepEqual([...mesh.matrixWorld.elements],before.world);assert.deepEqual(mesh.position,before.position);assert.equal(material.version,before.version);assert.equal(material.map,before.texture);assert.equal(material.map.source,before.source);assert(!JSON.stringify(report).includes('private'));assert(!JSON.stringify(report).includes('account'));
});
test('owned MessageChannel ports close once after complete census and cancellation',async()=>{
 const Original=globalThis.MessageChannel,closed:number[][]=[];
 globalThis.MessageChannel=class extends Original {constructor(){super();const pair=[0,0];closed.push(pair);for(const [index,port]of [this.port1,this.port2].entries()){const close=port.close.bind(port);port.close=()=>{pair[index]++;close();};}}};
 try{
  const r=await censusWorldDrawsAsync(scene(),{...options(),now:clock(),maximumSliceMs:1});assert.equal(r.partial,false);assert.deepEqual(closed,[[1,1]]);
  const controller=new AbortController(),p=censusWorldDrawsAsync(scene(),{...options(),signal:controller.signal,now:clock(),maximumSliceMs:1});controller.abort();assert.equal((await p).partial,true);assert.deepEqual(closed,[[1,1],[1,1]]);
 }finally{globalThis.MessageChannel=Original;}
});
test('a genuinely undelivered continuation is cancelled at the bounded wall deadline',async t=>{
 const Original=globalThis.MessageChannel,closed=[0,0];
 globalThis.MessageChannel=class extends Original {constructor(){super();this.port2.postMessage=()=>{};for(const [index,port]of [this.port1,this.port2].entries()){const close=port.close.bind(port);port.close=()=>{closed[index]++;close();};}}};
 t.mock.timers.enable({apis:['setTimeout']});
 try{const pending=censusWorldDrawsAsync(scene(),{...options(),now:clock(),maximumSliceMs:1});t.mock.timers.tick(5000);const r=await pending;assert(r.partial);assert(r.reasons['wall-deadline']);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert.deepEqual(closed,[1,1]);}
 finally{globalThis.MessageChannel=Original;t.mock.timers.reset();}
});
test('completed request does not retain original graphs, material or raw geometry buffers',()=>{
 const script=`
 import * as T from 'three';import {censusWorldDrawsAsync} from './src/world-draw-census-async.ts';
 import {setImmediate as turn} from 'node:timers/promises';
 const refs=[];
 async function owned(){const g=new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3)),m=new T.MeshBasicMaterial(),root=new T.Mesh(g,m);refs.push(new WeakRef(root),new WeakRef(g),new WeakRef(m),new WeakRef(g.attributes.position.array.buffer));return await censusWorldDrawsAsync([{root,loaded:true,dynamic:false,scripted:false,parented:false,materialChildren:false}],{signal:new AbortController().signal,isCurrent:()=>true,isRevisionCurrent:()=>true});}
 const report=await owned();if(report.partial||report.counts.candidateParts!==1)throw Error('Incomplete census');
 let released=false;for(let i=0;i<60;i++){await turn();globalThis.gc();await turn();if(refs.every(ref=>ref.deref()===undefined)){released=true;break;}}
 if(!released)throw Error('Original graph was retained');process.stdout.write('released');`;
 const result=spawnSync(process.execPath,['--expose-gc','--import','tsx','--input-type=module','-e',script],{cwd:process.cwd(),encoding:'utf8',timeout:15000});
 assert.equal(result.status,0,result.stderr);assert.equal(result.stdout,'released');
});
