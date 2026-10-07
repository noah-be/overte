// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import * as T from 'three';
import {censusWorldDraws,type DrawCensusOwner} from '../src/world-draw-census';
const geometry=()=>new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3));
const owner=(mesh:T.Mesh):DrawCensusOwner=>({root:mesh,loaded:true,dynamic:false,scripted:false,parented:false,materialChildren:false});
const census=(owners:DrawCensusOwner[],options={})=>censusWorldDraws(owners,{signal:new AbortController().signal,isCurrent:()=>true,...options});
test('exact bytes distinguish shared geometry identity, independent geometry, and actual material identity',()=>{
 const g=geometry(),m=new T.MeshBasicMaterial();const report=census([owner(new T.Mesh(g,m)),owner(new T.Mesh(g,m)),owner(new T.Mesh(g.clone(),m))]);
 assert.equal(report.counts.drawParts,3);assert.equal(report.resources.geometryIdentities,2);assert.equal(report.resources.geometryByteClasses,1);assert.equal(report.exactGeometryAndMaterialIdentity.groups,1);assert.equal(report.exactGeometryAndMaterialIdentity.members,3);assert.equal(report.exactGeometryAndMaterialIdentity.independentlyLoadedGeometryGroups,1);assert.equal(report.partial,false);
});
test('independent cloned materials compare only exact source and sampler state, never URLs',()=>{
 const texture=new T.Texture({src:'https://private.example/identity'}),m=new T.MeshBasicMaterial({map:texture}),clone=m.clone(),changed=m.clone();clone.map=texture.clone();changed.map=texture.clone();changed.map.offset.x=.25;
 const report=census([owner(new T.Mesh(geometry(),m)),owner(new T.Mesh(geometry(),clone)),owner(new T.Mesh(geometry(),changed))]);
 assert.equal(report.exactGeometryAndMaterialIdentity.groups,0);assert.equal(report.exactGeometryAndAuditedMaterialValues.members,2);assert.equal(report.resources.sourceIdentities,1);assert.equal(report.resources.textureIdentities,3);assert.equal(report.resources.samplerSourceBindings,2);assert(!JSON.stringify(report).includes('private.example'));
});
test('same image address with independently owned Sources does not establish equivalence',()=>{
 const image={src:'same'},a=new T.MeshBasicMaterial({map:new T.Texture(image)}),b=new T.MeshBasicMaterial({map:new T.Texture(image)});
 assert.equal(census([owner(new T.Mesh(geometry(),a)),owner(new T.Mesh(geometry(),b))]).exactGeometryAndAuditedMaterialValues.groups,0);
});
test('one different index or attribute byte cannot match content class',()=>{
 const a=geometry().setIndex([0,1,2]),b=a.clone();b.index!.setX(2,1);const m=new T.MeshBasicMaterial();const r=census([owner(new T.Mesh(a,m)),owner(new T.Mesh(b,m))]);assert.equal(r.resources.geometryByteClasses,2);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);
});
test('foreign shader functions and render callbacks are never invoked or authorized by userData',()=>{
 let calls=0;const foreign=new T.MeshBasicMaterial();foreign.onBeforeCompile=()=>{calls++;};foreign.customProgramCacheKey=()=>{calls++;return 'claimed';};foreign.userData.nativeShader=true;
 const render=new T.Mesh(geometry(),new T.MeshBasicMaterial());render.onBeforeRender=()=>{calls++;};const r=census([owner(new T.Mesh(geometry(),foreign)),owner(render)]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);assert.equal(r.hooks.foreign,1);assert.equal(r.reasons['custom-render-callback'],1);
});
test('dynamic, script, native-parent, animation, skin and morph restrictions retain separate reasons',()=>{
 const create=()=>owner(new T.Mesh(geometry(),new T.MeshBasicMaterial()));const a=create(),b=create(),c=create(),d=create(),e=owner(new T.SkinnedMesh(geometry(),new T.MeshBasicMaterial())),f=create();a.dynamic=true;b.scripted=true;c.parented=true;d.root.animations=[new T.AnimationClip('private',1,[])];(f.root as T.Mesh).geometry.morphAttributes.position=[new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3)];
 const r=census([a,b,c,d,e,f]);for(const reason of ['dynamic','scripted','native-parent','animation','skin-or-existing-instance','animation-or-morph'])assert.equal(r.reasons[reason],1);assert.equal(r.counts.candidateParts,0);
});
test('actual mesh render state prevents shadow/layer/order false equivalence',()=>{
 const g=geometry(),m=new T.MeshBasicMaterial(),a=new T.Mesh(g,m),b=new T.Mesh(g,m);b.castShadow=true;const r=census([owner(a),owner(b)]);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);
});
test('census leaves matrices, versions, resources and callbacks untouched',()=>{
 const mesh=new T.Mesh(geometry(),new T.MeshBasicMaterial());mesh.position.x=17;mesh.matrixAutoUpdate=false;const before=mesh.toJSON();mesh.updateMatrix=()=>{throw Error('matrix write');};mesh.updateWorldMatrix=()=>{throw Error('world matrix write');};mesh.geometry.dispose=()=>{throw Error('dispose');};const r=census([owner(mesh)]);assert.equal(r.counts.candidateParts,1);assert.deepEqual(mesh.toJSON(),before);
});
for(const [key,value,reason]of [['maximumNodes',1,'node-count-budget'],['maximumParts',1,'draw-part-budget'],['maximumBytes',1,'geometry-byte-budget'],['maximumMetadataBytes',1,'metadata-byte-budget']]as const)test('bounded '+key+' reports partial census',()=>{
 const a=owner(new T.Mesh(geometry(),new T.MeshBasicMaterial())),b=owner(new T.Mesh(geometry(),new T.MeshBasicMaterial()));const r=census([a,b],{[key]:value});assert(r.partial);assert.equal(r.reasons[reason],1);
});
test('revocation and hard CPU deadline stop without publishing false complete census',()=>{
 const controller=new AbortController();controller.abort();const revoked=census([],{signal:controller.signal}); // An empty iterable still requires admission.
 assert.equal(revoked.partial,true);assert(revoked.reasons['owner-revoked']>=1);
 let ticks=0;const expired=census([owner(new T.Mesh(geometry(),new T.MeshBasicMaterial()))],{now:()=>++ticks,maximumCpuMs:1});assert(expired.partial);assert(expired.reasons['cpu-deadline']>=1);
});
test('same owner repeated meshes are not cross-entity candidates and names never leave',()=>{
 const root=new T.Group(),g=geometry(),m=new T.MeshBasicMaterial();root.name='private model';root.userData.entityID='private id';root.add(new T.Mesh(g,m),new T.Mesh(g,m));const r=census([{...owner(new T.Mesh()),root}]);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert(!JSON.stringify(r).includes('private'));
});

test('late descendant animation excludes the entire owner, including an earlier sibling mesh',()=>{
 const root=new T.Group(),g=geometry(),m=new T.MeshBasicMaterial(),first=new T.Mesh(g,m),animated=new T.Group();animated.animations=[new T.AnimationClip('private animation',1,[])];root.add(first,animated);const r=census([{...owner(first),root},owner(new T.Mesh(g,m))]);assert.equal(r.counts.candidateParts,1);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);assert.equal(r.reasons['animation-owner-prior-parts'],1);
});
test('only native WeakMap-owned alpha/zero-light hooks qualify, copied function identities do not',async()=>{
 const {applyNativeMaterialAlpha}=await import('../src/native-alpha-material');const {installNativeZeroLightShader}=await import('../src/native-zero-lights');
 const owned=new T.MeshBasicMaterial({map:new T.Texture()}),forged=new T.MeshBasicMaterial({map:new T.Texture()}),lit=new T.MeshStandardMaterial();
 await applyNativeMaterialAlpha(owned,{useAlpha:true,mode:'OPACITY_MAP_MASK',cutoff:.4});forged.onBeforeCompile=owned.onBeforeCompile;forged.customProgramCacheKey=owned.customProgramCacheKey;installNativeZeroLightShader(lit);
 const r=census([owner(new T.Mesh(geometry(),owned)),owner(new T.Mesh(geometry(),forged)),owner(new T.Mesh(geometry(),lit))]);assert.equal(r.hooks['owned-native-alpha'],1);assert.equal(r.hooks['owned-zero-light'],1);assert.equal(r.hooks.foreign,1);assert.equal(r.counts.candidateParts,2);
});
test('hidden ancestry and actual partial/multi-material draw ranges are counted but never instanced',()=>{
 const group=new T.Group(),hidden=new T.Group();hidden.visible=false;hidden.add(new T.Mesh(geometry(),new T.MeshBasicMaterial()));group.add(hidden);const partial=new T.Mesh(geometry(),new T.MeshBasicMaterial());partial.geometry.setDrawRange(0,2);const multiGeometry=geometry();multiGeometry.addGroup(0,3,0);const multi=new T.Mesh(multiGeometry,[new T.MeshBasicMaterial()]);
 const r=census([{...owner(partial),root:group},owner(partial),owner(multi)]);assert.equal(r.counts.meshes,2);assert.equal(r.counts.drawParts,2);assert.equal(r.counts.candidateParts,0);assert.equal(r.reasons['multipart-or-partial-range'],2);
});
for(const key of ['opacity','transparent','onBeforeCompile','onBeforeRender','constructor'])test('material accessor '+key+' is rejected before it can execute',()=>{
 let calls=0;const m=new T.MeshBasicMaterial();Object.defineProperty(m,key,{get(){calls++;throw Error('foreign getter');}});const r=census([owner(new T.Mesh(geometry(),m))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);assert(r.reasons['unsupported-material-value']);
});
for(const key of ['material','geometry','animations','children','visible'])test('mesh accessor '+key+' is rejected before it can execute',()=>{
 let calls=0;const mesh=new T.Mesh(geometry(),new T.MeshBasicMaterial());Object.defineProperty(mesh,key,{get(){calls++;throw Error('foreign getter');}});const r=census([owner(mesh)]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);assert.equal(r.reasons['unsupported-node-accessor-or-class'],1);
});
for(const key of ['source','wrapS','offset','onUpdate'])test('texture accessor '+key+' is rejected before it can execute',()=>{
 let calls=0;const t=new T.Texture();Object.defineProperty(t,key,{get(){calls++;throw Error('foreign getter');}});const r=census([owner(new T.Mesh(geometry(),new T.MeshBasicMaterial({map:t})))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);
});
test('source version and nested Color getter traps do not execute',()=>{
 let calls=0;const t=new T.Texture(),m=new T.MeshBasicMaterial({map:t}),other=new T.MeshBasicMaterial();Object.defineProperty(t.source,'version',{get(){calls++;throw Error('source getter');}});Object.defineProperty(other.color,'r',{get(){calls++;throw Error('color getter');}});const r=census([owner(new T.Mesh(geometry(),m)),owner(new T.Mesh(geometry(),other))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);
});
for(const key of ['attributes','groups','index','drawRange'])test('geometry accessor '+key+' is rejected before draw inspection',()=>{
 let calls=0;const g=geometry();Object.defineProperty(g,key,{get(){calls++;throw Error('foreign getter');}});const r=census([owner(new T.Mesh(g,new T.MeshBasicMaterial()))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);assert.equal(r.reasons['unsupported-geometry-accessor-or-class'],1);
});
test('BufferAttribute and underlying TypedArray getter traps do not execute',()=>{
 let calls=0;const g=geometry(),other=geometry();Object.defineProperty(g.attributes.position,'count',{get(){calls++;throw Error('attribute getter');}});Object.defineProperty(other.attributes.position.array,'buffer',{get(){calls++;throw Error('buffer getter');}});const r=census([owner(new T.Mesh(g,new T.MeshBasicMaterial())),owner(new T.Mesh(other,new T.MeshBasicMaterial()))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);
});
test('unknown material/node subclasses are rejected without calling inherited accessors',()=>{
 let calls=0;class ForeignMaterial extends T.MeshBasicMaterial{}Object.defineProperty(ForeignMaterial.prototype,'onBeforeCompile',{get(){calls++;throw Error('foreign prototype getter');}});class ForeignMesh extends T.Mesh{}Object.defineProperty(ForeignMesh.prototype,'onBeforeRender',{get(){calls++;throw Error('foreign prototype getter');}});
 const r=census([owner(new T.Mesh(geometry(),new ForeignMaterial())),owner(new ForeignMesh(geometry(),new T.MeshBasicMaterial()))]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,0);
});
test('array index accessors and oversized temporary metadata lists reject before allocating or invoking',()=>{
 let calls=0;const root=new T.Group();root.children.length=1;Object.defineProperty(root.children,'0',{get(){calls++;throw Error('child getter');}});const bad=census([{...owner(new T.Mesh()),root}]);assert(bad.partial);assert.equal(bad.reasons['unsupported-array-accessor'],1);assert.equal(calls,0);
 const r=census([owner(new T.Mesh(geometry(),new T.MeshBasicMaterial()))],{maximumMetadataBytes:1});assert(r.partial);assert(r.reasons['metadata-byte-budget']);
});
test('known static matrix onUpdate wrapper is neither invoked nor misclassified as render callback',()=>{
 let calls=0;const mesh=new T.Mesh(geometry(),new T.MeshBasicMaterial());(mesh as T.Mesh&{onUpdate?:()=>void}).onUpdate=()=>{calls++;throw Error('static matrix wrapper');};const r=census([owner(mesh)]);assert.equal(calls,0);assert.equal(r.counts.candidateParts,1);
});
test('matrix/layer/morph-array accessors are rejected before native math or index access',()=>{
 let calls=0;const a=new T.Mesh(geometry(),new T.MeshBasicMaterial()),b=new T.Mesh(geometry(),new T.MeshBasicMaterial()),c=new T.Mesh(geometry(),new T.MeshBasicMaterial());Object.defineProperty(a.matrixWorld,'elements',{get(){calls++;throw Error('matrix getter');}});Object.defineProperty(b.layers,'mask',{get(){calls++;throw Error('layer getter');}});c.morphTargetInfluences=[0];Object.defineProperty(c.morphTargetInfluences,'0',{get(){calls++;throw Error('morph getter');}});
 for(const mesh of [a,b,c]){const r=census([owner(mesh)]);assert(r.partial);assert.equal(r.counts.candidateParts,0);}assert.equal(calls,0);
});
test('identical Uint16 bytes with half-float versus integer attribute layout remain separate',()=>{
 const a=geometry(),b=geometry();a.setAttribute('uv',new T.Float16BufferAttribute([0,0,0,0,0,0],2));b.setAttribute('uv',new T.Uint16BufferAttribute([0,0,0,0,0,0],2));const m=new T.MeshBasicMaterial(),r=census([owner(new T.Mesh(a,m)),owner(new T.Mesh(b,m))]);assert.equal(r.resources.geometryByteClasses,2);assert.equal(r.exactGeometryAndMaterialIdentity.groups,0);
});
test('nonfinite nested material math cannot collapse to equal JSON null values',()=>{
 const m=new T.MeshBasicMaterial();m.color.r=NaN;const r=census([owner(new T.Mesh(geometry(),m))]);assert(r.partial);assert.equal(r.counts.candidateParts,0);
});
