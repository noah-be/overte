// SPDX-License-Identifier: Apache-2.0
// Actual World/FBX/BVH methods; delayed image I/O is injected, no GPU claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Box3,Group,Mesh,MeshStandardMaterial,Scene,Texture,TextureLoader,Vector3,type LoadingManager} from 'three';
import {BrowserWorld} from '../src/world';
import {PreparedFbxCache} from '../src/prepared-fbx-cache';
import {ModelLoadScheduler} from '../src/model-load-scheduler';
import {ModelGeometryStage} from '../src/model-geometry-stage';
import {MeshCollision} from '../src/mesh-collision';
import type {Entity} from '../src/world-data';
const fbx=`; FBX 7.4.0 project file
FBXHeaderExtension:  {
\tFBXVersion: 7400
}
Objects:  {
\tGeometry: 201, "Geometry::Floor", "Mesh" {
\t\tVertices: *9 {
\t\t\ta: 0,0,0,10,0,0,0,0,10
\t\t}
\t\tPolygonVertexIndex: *3 {
\t\t\ta: 0,2,-2
\t\t}
\t}
\tModel: 401, "Model::Floor", "Mesh" {
\t}
\tMaterial: 101, "Material::Floor", "" {
\t\tShadingModel: "phong"
\t}
\tVideo: 501, "Video::Floor", "Clip" {
\t\tRelativeFilename: "floor.png"
\t\tFilename: "floor.png"
\t}
\tTexture: 301, "Texture::Floor", "TextureVideoClip" {
\t\tRelativeFilename: "floor.png"
\t\tFileName: "floor.png"
\t}
}
Connections:  {
\tC: "OO",201,401
\tC: "OO",101,401
\tC: "OO",401,0
\tC: "OP",301,101,"DiffuseColor"
\tC: "OO",501,301
}
`;
const methods=BrowserWorld.prototype as unknown as {populateEntity(entity:Entity,root:Group):Promise<void>};
function fixture(){
 const context=Object.create(BrowserWorld.prototype),abort=new AbortController(),root=new Group(),entity:Entity={id:'floor',type:'Model',modelURL:'https://assets.invalid/floor.fst',dimensions:{x:10,y:.2,z:10},shapeType:'static-mesh'};
 let finish!:()=>void,fail!:()=>void;
 class DelayedImages extends TextureLoader {
  load(url:string,onLoad?:(texture:Texture<HTMLImageElement>)=>void,_progress?:(event:ProgressEvent)=>void,onError?:(error:unknown)=>void):Texture<HTMLImageElement> {
   const key=this.manager.resolveURL((this.path||'')+url),texture=new Texture<HTMLImageElement>();this.manager.itemStart(key);
   finish=()=>{texture.image={width:1,height:1} as HTMLImageElement;onLoad?.(texture);this.manager.itemEnd(key);};
   fail=()=>{onError?.(Error('Image failed'));this.manager.itemError(key);this.manager.itemEnd(key);};return texture;
  }
 }
 Object.assign(context,{abort,disposed:false,options:{resolveAsset:(url:string)=>url,onStatus(){}},position:new Vector3(),objects:new Map([[entity.id,root]]),entities:new Map([[entity.id,entity]]),meshCollisions:new Map(),
  modelReaders:new WeakMap(),modelGeometry:new WeakMap<Group,ModelGeometryStage>(),modelScheduler:new ModelLoadScheduler({signal:abort.signal}),preparedFbx:new PreparedFbxCache({signal:abort.signal}),
  loadManagers:new Set(),imageCache:{loader:(manager:LoadingManager)=>new DelayedImages(manager)},fbxPreparePool:{prepare:async(buffer:ArrayBuffer)=>({buffer,phases:{materialBindingsMs:0,decodeMs:0}})},
  recordLoadPhase(){},recordLoadDuration(){},configureAlpha:async()=>{},localLights:new Set(),signatures:new Map(),scene:new Scene(),colliders:[],pendingModelColliders:[],restoreModelBatch(){},
 });
 const pending=()=>typeof finish==='function';return{context,abort,root,entity,pending,finish:()=>finish(),fail:()=>fail()};
}
const wait=async(condition:()=>boolean)=>{for(let i=0;i<2000;i++){if(condition())return;await new Promise(resolve=>setImmediate(resolve));}assert.fail('Expected genuine geometry/image stage did not start');};
test('actual FST→FBX publishes hidden correctly transformed floor triangles before delayed image completion and commits same model',async t=>{
 const f=fixture();t.mock.method(globalThis,'fetch',async(input:unknown)=>new Response(String(input).endsWith('.fst')?'filename = floor.fbx':fbx));
 const loading=methods.populateEntity.call(f.context,f.entity,f.root);await wait(f.pending);
 assert.equal(f.root.userData.modelGeometryReady,true);assert.notEqual(f.root.userData.modelLoaded,true);assert.equal(f.root.children[0].children.length,0,'Pending model is not a rendered placeholder');
 let position=new Vector3(-2,.75,-2);assert(f.context.meshCollisions.get(f.entity.id).value.resolve(position));assert(position.y>=.8499);
 f.root.position.y=3;f.context.modelGeometry.get(f.root).update();position=new Vector3(-2,3.75,-2);assert(f.context.meshCollisions.get(f.entity.id).value.resolve(position));assert(position.y>=3.8499);
 f.finish();await loading;assert.equal(f.root.userData.modelLoaded,true);assert.equal(f.root.children[0].children.length,1);assert.equal(f.context.modelGeometry.get(f.root).state.committed,true);f.abort.abort();f.context.meshCollisions.get(f.entity.id).value.dispose();
});
test('actual root removal during FST texture wait withdraws BVH without disposing borrowed model before its loader handles cancellation',async t=>{
 const f=fixture();t.mock.method(globalThis,'fetch',async(input:unknown)=>new Response(String(input).endsWith('.fst')?'filename = floor.fbx':fbx));
 const loading=methods.populateEntity.call(f.context,f.entity,f.root);await wait(f.pending);
 const stage=f.context.modelGeometry.get(f.root) as ModelGeometryStage;assert.equal(stage.state.prepared,true);
 const rejected=assert.rejects(loading,{name:'AbortError'});f.context.removeEntities([f.entity.id]);await rejected;
 assert.equal(stage.state.revoked,true);assert.equal(f.context.meshCollisions.size,0);assert.equal(f.root.children[0].children.length,0);f.finish();f.abort.abort();
});
test('actual rejected FST material after image completion withdraws pending triangles and releases parsed resources exactly once',async t=>{
 const f=fixture();let geometry=0,material=0,texture=0;const original=ModelGeometryStage.prototype.prepare;
 t.mock.method(ModelGeometryStage.prototype,'prepare',function(this:ModelGeometryStage,model:Group){
  model.traverse(object=>{if(object instanceof Mesh){object.geometry.addEventListener('dispose',()=>geometry++);for(const value of Array.isArray(object.material)?object.material:[object.material]){
   value.addEventListener('dispose',()=>material++);const map=(value as MeshStandardMaterial).map;map?.addEventListener('dispose',()=>texture++);
  }}});original.call(this,model);
 });
 t.mock.method(globalThis,'fetch',async(input:unknown)=>String(input).endsWith('.json')?new Response('Denied',{status:403}):new Response(String(input).endsWith('.fst')?'filename = floor.fbx\nmaterialMap = [{"all":"material.json"}]':fbx));
 const loading=methods.populateEntity.call(f.context,f.entity,f.root);await wait(f.pending);assert.equal(f.root.userData.modelGeometryReady,true);
 const rejected=assert.rejects(loading,/403/);f.finish();await rejected;assert.equal(f.context.meshCollisions.size,0);assert.equal(f.root.userData.modelGeometryReady,false);assert.deepEqual([geometry,material,texture],[1,1,1]);assert.equal(f.root.children[0].children.length,0);f.abort.abort();
});

// FST mapping transforms are avatar metadata in the current loader. Model
// geometry retains actual imported nested transforms; this consistency proof
// does not introduce a new interpretation of FST Model scale or rotation.
test('successful nonidentity nested FST metadata preserves completed-loader geometry/BVH before images and after final commit',async t=>{
 const staged=fixture(),completed=fixture();t.after(()=>{staged.abort.abort();completed.abort.abort();});
 const configure=(f:ReturnType<typeof fixture>)=>{
  f.entity.dimensions={x:12,y:4,z:16};f.entity.registrationPoint={x:.3,y:.4,z:.6};
  f.root.position.set(2,3,4);f.root.rotation.set(.1,.2,-.05);
 };configure(staged);configure(completed);
 const transformed=fbx.replace('\tModel: 401, "Model::Floor", "Mesh" {\n\t}',`\tModel: 401, "Model::Floor", "Mesh" {
\t\tProperties70:  {
\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",2,-1,3
\t\t\tP: "Lcl Rotation", "Lcl Rotation", "", "A",15,30,10
\t\t\tP: "Lcl Scaling", "Lcl Scaling", "", "A",2,0.7,1.3
\t\t}
\t}
\tModel: 402, "Model::NativeParent", "Null" {
\t\tProperties70:  {
\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",3,4,5
\t\t\tP: "Lcl Rotation", "Lcl Rotation", "", "A",0,20,0
\t\t\tP: "Lcl Scaling", "Lcl Scaling", "", "A",1.2,0.9,0.8
\t\t}
\t}`).replace('\tC: "OO",401,0','\tC: "OO",401,402\n\tC: "OO",402,0');
 assert.notEqual(transformed,fbx);
 const outer='filename = inner.fst\nscale = 1.7\nrx = 20\nry = -45\nrz = 10\njoint = jointRoot = OuterRoot';
 const inner='filename = floor.fbx\nscale = 0.4\nrx = -10\nry = 80\nrz = 5\njoint = jointRoot = InnerRoot';
 t.mock.method(globalThis,'fetch',async(input:unknown)=>new Response(String(input).endsWith('/inner.fst')?inner:String(input).endsWith('.fst')?outer:transformed));
 const loading=methods.populateEntity.call(staged.context,staged.entity,staged.root);void loading.catch(()=>{});await wait(staged.pending);
 const pendingModel=(staged.context.modelGeometry.get(staged.root) as any).model as Group;
 const expectedMapping={scale:1.7,rotation:{x:20*Math.PI/180,y:-45*Math.PI/180,z:10*Math.PI/180},root:'OuterRoot'};
 assert.deepEqual(pendingModel.userData.avatarMapping,expectedMapping,'Outer metadata must already win before the actual geometry consumer');
 const stagedScale=pendingModel.scale.toArray(),stagedRotation=pendingModel.quaternion.toArray();
 const referenceLoading=completed.context.loadModel(completed.entity.modelURL);void referenceLoading.catch(()=>{});
 await wait(completed.pending);completed.finish();const reference=await referenceLoading as Group;
 assert.deepEqual(reference.userData.avatarMapping,expectedMapping);assert.deepEqual(stagedScale,reference.scale.toArray());assert.deepEqual(stagedRotation,reference.quaternion.toArray());
 assert(reference.parent,'The actual FBX importer returned a Group with its private parse parent');assert.deepEqual(reference.parent.matrix.elements,new Group().matrix.elements,'The discarded parse SceneGraph transform is identity');
 // Independent completed-loader normalization reproduces the old Model path;
 // it does not call the new staged normalization helper.
 const bounds=new Box3().setFromObject(reference),size=bounds.getSize(new Vector3()),normalizer=new Group();
 reference.position.sub(bounds.getCenter(new Vector3()));normalizer.add(reference);normalizer.scale.set(12/size.x,4/size.y,16/size.z);
 const content=new Group();content.position.set((.5-.3)*12,(.5-.4)*4,(.5-.6)*16);content.add(normalizer);
 const referenceRoot=completed.root.clone(false);referenceRoot.add(content);const referenceCollision=new MeshCollision(referenceRoot);
 const triangleBytes=(value:MeshCollision)=>Array.from((value as any).geometry.getAttribute('position').array as Float32Array);
 const expectedTriangles=triangleBytes(referenceCollision),initialCollision=staged.context.meshCollisions.get(staged.entity.id).value as MeshCollision;
 assert(expectedTriangles.some(value=>Math.abs(value)>1),'The imported nested transforms must produce nontrivial real geometry');
 assert.deepEqual(triangleBytes(initialCollision),expectedTriangles);
 assert.equal(staged.root.children[0].children.length,0);staged.finish();await loading;
 assert.equal(staged.root.children[0].children[0].children[0],pendingModel);assert.deepEqual(pendingModel.userData.avatarMapping,expectedMapping);
 const finalCollision=new MeshCollision(staged.root);assert.deepEqual(triangleBytes(finalCollision),expectedTriangles);finalCollision.dispose();
 assert.deepEqual(triangleBytes(staged.context.meshCollisions.get(staged.entity.id).value),expectedTriangles);
 const actualBounds=new Box3().setFromObject(staged.root),expectedBounds=new Box3().setFromObject(referenceRoot);
 assert(actualBounds.min.distanceTo(expectedBounds.min)<1e-7&&actualBounds.max.distanceTo(expectedBounds.max)<1e-7);
 staged.abort.abort();completed.abort.abort();initialCollision.dispose();referenceCollision.dispose();
});
test('invalid FST metadata is rejected before an early geometry consumer or dependent model acquires resources',async t=>{
 const f=fixture();let dependentFetches=0;
 t.mock.method(globalThis,'fetch',async(input:unknown)=>{if(!String(input).endsWith('.fst'))dependentFetches++;return new Response(String(input).endsWith('.fst')?'filename = floor.fbx\nscale = NaN':fbx);});
 await assert.rejects(methods.populateEntity.call(f.context,f.entity,f.root),/Invalid avatar mapping transform/);
 assert.equal(dependentFetches,0);assert.equal(f.context.meshCollisions.size,0);assert.notEqual(f.root.userData.modelGeometryReady,true);f.abort.abort();
});
