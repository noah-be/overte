// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as T from 'three';
import { getNativeAlphaOptions, hasNativeAlphaShader } from './native-alpha-material';
import { SessionUploadTexture } from './world-bitmap-upload';
import { hasNativeZeroLightShader } from './native-zero-lights';

/** Caller provides actual current entity facts, never labels or addresses. */
export interface DrawCensusOwner { root:T.Object3D; loaded:boolean; dynamic:boolean; scripted:boolean; parented:boolean; materialChildren:boolean; animated?:boolean }
export interface DrawCensusOptions { signal:AbortSignal; isCurrent:()=>boolean; now?:()=>number; maximumOwners?:number; maximumNodes?:number; maximumParts?:number; maximumBytes?:number; maximumMetadataBytes?:number; maximumCpuMs?:number }
interface GeometryRecord { id:number; shape:string; hash:number; arrays:Uint8Array[] }
interface Part { owner:number; geometry:GeometryRecord; material:number; equivalentMaterial:number; geometryIdentity:number; renderState:string }
const defaults={maximumOwners:1024,maximumNodes:16384,maximumParts:8192,maximumBytes:64*1024*1024,maximumMetadataBytes:2*1024*1024,maximumCpuMs:75};
const constructors=[T.MeshBasicMaterial,T.MeshLambertMaterial,T.MeshPhongMaterial,T.MeshStandardMaterial];
const materialFields=new Map(constructors.map(c=>[c.prototype,new Set(Object.keys(new c()))]));
const nodePrototypes=[T.Object3D,T.Group,T.Mesh,T.SkinnedMesh,T.InstancedMesh,T.BatchedMesh,T.Bone,T.Line,T.LineSegments,T.Points].map(c=>c.prototype);
const attributePrototypes=[T.BufferAttribute,T.Float32BufferAttribute,T.Float16BufferAttribute,T.Uint8BufferAttribute,T.Uint8ClampedBufferAttribute,T.Uint16BufferAttribute,T.Uint32BufferAttribute,T.Int8BufferAttribute,T.Int16BufferAttribute,T.Int32BufferAttribute].map(c=>c.prototype);
const ignored=new Set(['uuid','name','userData','version','_listeners','id','onBeforeCompile','customProgramCacheKey']);
const textureFields=['mapping','channel','wrapS','wrapT','magFilter','minFilter','anisotropy','format','internalFormat','type','rotation','matrixAutoUpdate','generateMipmaps','premultiplyAlpha','flipY','unpackAlignment','colorSpace','isRenderTargetTexture','isArrayTexture','normalized'] as const;
class Unsupported extends Error {}
class Censored extends Error { constructor(readonly reason:string){super(reason);} }
/** A synchronous, one-shot read-only census. No renderer calls, matrix updates,
 * getters supplied by models, source fetches, digests or owner labels escape. */
export function censusWorldDraws(owners:Iterable<DrawCensusOwner>,options:DrawCensusOptions) {
 const bounds={...defaults,...options},now=options.now??(()=>performance.now()),start=now();
 for(const key of Object.keys(defaults) as (keyof typeof defaults)[])if(!Number.isSafeInteger(bounds[key])||bounds[key]<=0||bounds[key]>defaults[key])throw Error('Invalid draw census bound');
 const reasons:Record<string,number>={},counts={owners:0,nodes:0,meshes:0,drawParts:0,triangles:0,candidateParts:0,geometryBytesRead:0,metadataBytes:0,textureBindings:0};
 const inc=(reason:string)=>{reasons[reason]=(reasons[reason]??0)+1;};
 const check=()=>{if(options.signal.aborted||!options.isCurrent())throw new Censored('owner-revoked');if(now()-start>=bounds.maximumCpuMs)throw new Censored('cpu-deadline');};
 const identity=new WeakMap<object,number>();let nextIdentity=0;
 const id=(value:object)=>{let n=identity.get(value);if(n===undefined){n=++nextIdentity;identity.set(value,n);}return n;};
 const geometries=new Map<T.BufferGeometry,GeometryRecord>(),classes=new Map<string,GeometryRecord[]>(),parts:Part[]=[],materials=new Map<T.Material,{identity:number;equivalent:number}|null>();
 const materialClasses=new Map<string,number>();
 const metadata=(text:string)=>{const size=text.length*2;if(counts.metadataBytes+size>bounds.maximumMetadataBytes)throw new Censored('metadata-byte-budget');counts.metadataBytes+=size;return text;};
 const sourceTextures=new Map<number,Set<number>>();
 const textureIds=new Set<number>(),sourceIds=new Set<number>(),samplerSources=new Set<string>(),hooks:Record<string,number>={},alphaFlags:Record<string,number>={};
 // Descriptor inspection rejects accessors before any model-owned value is read.
 // Reflect.ownKeys is a native primitive and cannot be preempted for arbitrary
 // Proxy/huge foreign objects: this is bounded Three-object diagnostics, not a JS sandbox.
 const preallocate=(bytes:number)=>{check();if(bytes>bounds.maximumMetadataBytes-counts.metadataBytes)throw new Censored('metadata-byte-budget');};
 const safeRecord=(value:unknown,prototypes:object[],maximum:number):Record<PropertyKey,PropertyDescriptor>=>{
  if(!value||typeof value!=='object'||!prototypes.includes(Object.getPrototypeOf(value)))throw new Unsupported('unsupported-object-prototype');
  const keys=Reflect.ownKeys(value);if(keys.length>maximum)throw new Unsupported('unsupported-object-field-bound');
  preallocate(keys.length*96);const descriptors=Object.create(null) as Record<PropertyKey,PropertyDescriptor>;
  for(const key of keys){check();const d=Object.getOwnPropertyDescriptor(value,key);if(!d||!('value'in d))throw new Unsupported('unsupported-accessor');descriptors[key]=d;}
  return descriptors;
 };
 const array=(value:unknown,maximum:number):unknown[]=>{
  if(!Array.isArray(value)||Object.getPrototypeOf(value)!==Array.prototype)throw new Unsupported('unsupported-array');
  const length=Object.getOwnPropertyDescriptor(value,'length')?.value;if(!Number.isSafeInteger(length)||length<0||length>maximum)throw new Unsupported('unsupported-array-bound');
  preallocate(length*16);const result:unknown[]=[];for(let i=0;i<length;i++){check();const d=Object.getOwnPropertyDescriptor(value,String(i));if(!d||!('value'in d))throw new Unsupported('unsupported-array-accessor');result.push(d.value);}return result;
 };
 const typedPrototypes=new Map([Float32Array,Float64Array,Uint8Array,Uint8ClampedArray,Uint16Array,Uint32Array,Int8Array,Int16Array,Int32Array].map(c=>[c.prototype,c.name]));
 const typedArray=(value:unknown)=>{if(!ArrayBuffer.isView(value)||!typedPrototypes.has(Object.getPrototypeOf(value)))throw new Unsupported('unsupported-typed-array');for(const key of ['buffer','byteOffset','byteLength','length','constructor']){const d=Object.getOwnPropertyDescriptor(value,key);if(d)throw new Unsupported('unsupported-typed-array-override');}const a=value as Exclude<ArrayBufferView,DataView>;if(!(a.buffer instanceof ArrayBuffer))throw new Unsupported('unsupported-shared-buffer');return a;};
 const safeGeometry=new Set<T.BufferGeometry>(),safeAttributes=new Set<T.BufferAttribute>();
 const attribute=(a:T.BufferAttribute)=>{if(safeAttributes.has(a))return;safeRecord(a,attributePrototypes,32);typedArray(a.array);safeAttributes.add(a);};
 const geometryShape=(g:T.BufferGeometry)=>{if(safeGeometry.has(g))return;safeRecord(g,[T.BufferGeometry.prototype],32);const attrs=safeRecord(g.attributes,[Object.prototype,null as unknown as object],16);safeRecord(g.morphAttributes,[Object.prototype,null as unknown as object],16);safeRecord(g.drawRange,[Object.prototype],2);const groups=array(g.groups,bounds.maximumParts);for(const group of groups)safeRecord(group,[Object.prototype],3);if(g.index)attribute(g.index);for(const key of Reflect.ownKeys(attrs)){if(typeof key!=='string'||key.length>128)throw new Unsupported('unsupported-attribute-name');attribute(attrs[key].value);}safeGeometry.add(g);};
 const safeMaterials=new Set<T.Material>();
 const consume=(bytes:number)=>{if(counts.geometryBytesRead+bytes>bounds.maximumBytes)throw new Censored('geometry-byte-budget');counts.geometryBytesRead+=bytes;};
 const finiteValues=(values:unknown[])=>{if(values.some(v=>typeof v!=='number'||!Number.isFinite(v)))throw new Unsupported('unsupported-nonfinite-math');return values;};
 const plain=(value:unknown):unknown=>{if(value===null||typeof value==='boolean')return value;if(typeof value==='number'&&Number.isFinite(value))return value;if(typeof value==='string'&&value.length<=128)return value;
  const proto=value&&typeof value==='object'?Object.getPrototypeOf(value):undefined;
  if(proto===T.Color.prototype){safeRecord(value,[proto],4);const v=value as T.Color;return finiteValues([v.r,v.g,v.b]);}
  if(proto===T.Vector2.prototype){safeRecord(value,[proto],2);const v=value as T.Vector2;return finiteValues([v.x,v.y]);}
  if(proto===T.Vector3.prototype){safeRecord(value,[proto],3);const v=value as T.Vector3;return finiteValues([v.x,v.y,v.z]);}
  if(proto===T.Euler.prototype){const d=safeRecord(value,[proto],6);if(typeof d._order.value!=='string'||d._order.value.length>16)throw new Unsupported('unsupported-euler-order');return [...finiteValues([d._x.value,d._y.value,d._z.value]),d._order.value];}
  if(proto===T.Matrix3.prototype){safeRecord(value,[proto],2);return finiteValues(array((value as T.Matrix3).elements,9));}
  throw new Unsupported('unsupported-material-value');};
 const texture=(value:T.Texture)=>{safeRecord(value,[T.Texture.prototype,T.CompressedTexture.prototype,SessionUploadTexture.prototype],64);safeRecord(value.source,[T.TextureSource.prototype],8);if(!Number.isSafeInteger(value.source.version)||value.source.version<0)throw new Unsupported('unsupported-source-version');const mipRecords=array(value.mipmaps,32);array(value.updateRanges,0);if(value.isRenderTargetTexture||value.onUpdate!==null||value.updateRanges.length||value.mipmaps.length>32)throw new Unsupported('unsupported-texture-binding');
  const tid=id(value),sid=id(value.source);textureIds.add(tid);sourceIds.add(sid);const users=sourceTextures.get(sid)??new Set<number>();users.add(tid);sourceTextures.set(sid,users);counts.textureBindings++;
  const fields=textureFields.map(key=>plain(value[key]));fields.push(plain(value.offset),plain(value.repeat),plain(value.center),plain(value.matrix));
  // Source identity is exact; equal URL/image names never imply equal bytes.
  const mips=mipRecords.map(m=>{if(!m||typeof m!=='object')throw new Unsupported('unsupported-mipmap');return id(m);});
  const signature=JSON.stringify([sid,value.source.version,fields,mips]);if(!samplerSources.has(signature)){metadata(signature);samplerSources.add(signature);}return signature;
 };
 const material=(m:T.Material)=>{if(materials.has(m))return materials.get(m)!;
  try{const descriptors=safeRecord(m,[...materialFields.keys()],128);safeMaterials.add(m);const allowed=materialFields.get(Object.getPrototypeOf(m)),alpha=hasNativeAlphaShader(m),zero=hasNativeZeroLightShader(m);
  const hooksKind=zero?'owned-zero-light':alpha?'owned-native-alpha':m.onBeforeCompile===T.Material.prototype.onBeforeCompile&&m.customProgramCacheKey===T.Material.prototype.customProgramCacheKey?'default':'foreign';
  hooks[hooksKind]=(hooks[hooksKind]??0)+1;
  const flags=JSON.stringify([m.transparent,m.opacity,(m as T.Material & {_alphaTest:number})._alphaTest,m.alphaHash,m.side,m.depthWrite,m.forceSinglePass,getNativeAlphaOptions(m)??null]);alphaFlags[flags]=(alphaFlags[flags]??0)+1;
  if(!allowed||hooksKind==='foreign'||m.onBeforeRender!==T.Material.prototype.onBeforeRender){inc('unsupported-material-hooks-or-class');materials.set(m,null);return null;}
  if(m.transparent||m.opacity!==1||m.alphaHash||(m as T.MeshBasicMaterial).wireframe){inc('nonopaque-or-wireframe');materials.set(m,null);return null;}
  const fields:unknown[]=[];

   for(const key of Object.keys(descriptors).sort()){if(ignored.has(key))continue;const d=descriptors[key];if(!('value'in d)||!allowed.has(key))throw new Unsupported('unsupported-material-field');
    const v=d.value;if(v instanceof T.Texture)fields.push([key,texture(v)]);else if(key==='defines'){if(!v||Object.keys(v).length>16)throw new Unsupported('unsupported-defines');fields.push([key,Object.entries(safeRecord(v,[Object.prototype],16)).sort().map(([k,d])=>[k,plain(d.value)])]);}else fields.push([key,plain(v)]);}
   const signature=JSON.stringify([fields,hooksKind,getNativeAlphaOptions(m)??null]);if(signature.length>16384)throw new Unsupported('material-signature-budget');let equivalent=materialClasses.get(signature);if(equivalent===undefined){metadata(signature);equivalent=materialClasses.size+1;materialClasses.set(signature,equivalent);}const result={identity:id(m),equivalent};materials.set(m,result);return result;
  }catch(error){if(!(error instanceof Unsupported))throw error;partial=true;inc('unsupported-material-value');materials.set(m,null);return null;}
 };
 const sameBytes=(a:GeometryRecord,b:GeometryRecord)=>{if(a.shape!==b.shape||a.hash!==b.hash)return false;for(let n=0;n<a.arrays.length;n++){const x=a.arrays[n],y=b.arrays[n];consume(x.byteLength);for(let j=0;j<x.length;j++){if((j&4095)===0)check();if(x[j]!==y[j])return false;}}return true;};
 const geometry=(g:T.BufferGeometry):GeometryRecord=>{const prior=geometries.get(g);if(prior)return prior;geometryShape(g);const names=Object.keys(g.attributes).sort();if(names.length>16||names.some(n=>n.length>128)||Object.keys(g.morphAttributes).length)throw new Unsupported('unsupported-geometry-layout');
  const shape:unknown[]=[g.drawRange.start,Number.isFinite(g.drawRange.count)?g.drawRange.count:'all',(preallocate(g.groups.length*96),g.groups).map(x=>[x.start,x.count,x.materialIndex??0])],arrays:Uint8Array[]=[];let hash=2166136261;
  for(const name of ['INDEX',...names]){const a=name==='INDEX'?g.index:g.attributes[name];if(!a){shape.push([name,null]);continue;}if(!(a instanceof T.BufferAttribute)||a.onUploadCallback!==T.BufferAttribute.prototype.onUploadCallback||!ArrayBuffer.isView(a.array)||!(a.array.buffer instanceof ArrayBuffer))throw new Unsupported('unsupported-geometry-buffer');
   const bytes=new Uint8Array(a.array.buffer,a.array.byteOffset,a.array.byteLength);consume(bytes.byteLength);arrays.push(bytes);shape.push([name,attributePrototypes.indexOf(Object.getPrototypeOf(a)),typedPrototypes.get(Object.getPrototypeOf(a.array)),a.itemSize,a.count,a.normalized,a.gpuType]);
   for(let i=0;i<bytes.length;i++){if((i&4095)===0)check();hash=Math.imul(hash^bytes[i],16777619)>>>0;}
  }
  const shapeText=metadata(JSON.stringify(shape)),key=shapeText+'|'+hash,bucket=classes.get(key)??[];const probe={id:classes.size+1,shape:shapeText,hash,arrays};const equal=bucket.find(other=>sameBytes(probe,other));if(equal)probe.id=equal.id;else{probe.id=nextGeometry++;bucket.push(probe);classes.set(key,bucket);}geometries.set(g,probe);return probe;
 };let nextGeometry=1,partial=false;
 try{
  check();
  for(const owner of owners){check();if(counts.owners>=bounds.maximumOwners)throw new Censored('owner-count-budget');counts.owners++;safeRecord(owner,[Object.prototype],8);if(!owner.loaded){inc('not-loaded');continue;}
   const firstOwnerPart=parts.length;let ownerReason=owner.dynamic?'dynamic':owner.scripted?'scripted':owner.parented?'native-parent':owner.materialChildren?'material-child':owner.animated?'animation':undefined;
   const stack:Array<{node:T.Object3D;visible:boolean}>=[{node:owner.root,visible:true}];
   while(stack.length){check();if(counts.nodes>=bounds.maximumNodes)throw new Censored('node-count-budget');const {node,visible}=stack.pop()!;counts.nodes++;try{safeRecord(node,nodePrototypes,64);}catch(error){if(!(error instanceof Unsupported))throw error;inc('unsupported-node-accessor-or-class');partial=true;continue;}const drawn=visible&&node.visible;
    const animations=array(node.animations,32),children=array(node.children,bounds.maximumNodes-counts.nodes-stack.length) as T.Object3D[];
    if(animations.length&&!ownerReason){ownerReason='animation';const removed=parts.length-firstOwnerPart;parts.splice(firstOwnerPart);counts.candidateParts-=removed;if(removed)inc('animation-owner-prior-parts');}
    if(children.length>bounds.maximumNodes-counts.nodes-stack.length)throw new Censored('node-count-budget');preallocate((stack.length+children.length)*32);for(let i=children.length-1;i>=0;i--)stack.push({node:children[i],visible:drawn});
    if(!(node instanceof T.Mesh)||!drawn)continue;counts.meshes++;const g=node.geometry;try{geometryShape(g);}catch(error){if(!(error instanceof Unsupported))throw error;inc('unsupported-geometry-accessor-or-class');partial=true;continue;}const available=g.index?.count??g.attributes.position?.count??0,first=Math.max(0,g.drawRange.start),end=Math.min(available,first+g.drawRange.count);
    if(g.groups.length>bounds.maximumParts)throw new Censored('draw-part-budget');const nodeMaterials=Array.isArray(node.material)?array(node.material,bounds.maximumParts) as T.Material[]:null;const ranges=nodeMaterials?g.groups:[{start:first,count:end-first,materialIndex:0}];let actual=0;
    for(const range of ranges){const m=nodeMaterials?nodeMaterials[range.materialIndex??0]:node.material as T.Material;if(m)material(m);const count=Math.max(0,Math.min(end,range.start+range.count)-Math.max(first,range.start));if(m&&safeMaterials.has(m)&&m.visible&&count){if(counts.drawParts>=bounds.maximumParts)throw new Censored('draw-part-budget');counts.drawParts++;counts.triangles+=count/3;actual++;material(m);}}
    if(ownerReason){inc(ownerReason);continue;}if(node instanceof T.SkinnedMesh||node instanceof T.InstancedMesh||node instanceof T.BatchedMesh){inc('skin-or-existing-instance');continue;}
    if(node.morphTargetInfluences)array(node.morphTargetInfluences,1024);if(animations.length||Object.keys(g.morphAttributes).length||node.morphTargetInfluences?.length){inc('animation-or-morph');continue;}
    if(node.customDepthMaterial||node.customDistanceMaterial){inc('custom-shadow-material');continue;}
    if(node.onBeforeRender!==T.Object3D.prototype.onBeforeRender||node.onAfterRender!==T.Object3D.prototype.onAfterRender){inc('custom-render-callback');continue;}
    safeRecord(node.matrixWorld,[T.Matrix4.prototype],2);const matrixElements=array(node.matrixWorld.elements,16);safeRecord(node.layers,[T.Layers.prototype],1);if(!matrixElements.every(v=>typeof v==='number'&&Number.isFinite(v))||T.Matrix4.prototype.determinant.call(node.matrixWorld)<=0){inc('mirrored-or-singular-transform');continue;}
    if(actual!==1||Array.isArray(node.material)||first!==0||end!==available){inc('multipart-or-partial-range');continue;}
    const m=material(node.material);if(!m)continue;
    try{const record=geometry(g);parts.push({owner:counts.owners,geometry:record,material:m.identity,equivalentMaterial:m.equivalent,geometryIdentity:id(g),renderState:JSON.stringify([node.castShadow,node.receiveShadow,node.renderOrder,node.layers.mask,node.frustumCulled])});counts.candidateParts++;}catch(error){if(!(error instanceof Unsupported))throw error;partial=true;inc('unsupported-geometry');}
   }
  }
 }catch(error){if(error instanceof Censored){partial=true;inc(error.reason);}else if(error instanceof Unsupported){partial=true;inc(error.message);}else throw error;}
 const groups=(key:(p:Part)=>string)=>{const map=new Map<string,{members:number;owners:Set<number>;geometries:Set<number>;materials:Set<number>}>();let processed=0;for(const p of parts){if((processed++&63)===0)check();const k=key(p),v=map.get(k)??{members:0,owners:new Set(),geometries:new Set(),materials:new Set()};v.members++;v.owners.add(p.owner);v.geometries.add(p.geometryIdentity);v.materials.add(p.material);map.set(k,v);}const repeated=[...map.values()].filter(v=>v.owners.size>1);return{groups:repeated.length,members:repeated.reduce((n,v)=>n+v.members,0),sourceOnlyDrawReductionUpperBound:repeated.reduce((n,v)=>n+v.members-1,0),independentlyLoadedGeometryGroups:repeated.filter(v=>v.geometries.size>1).length,independentMaterialGroups:repeated.filter(v=>v.materials.size>1).length};};
 const grouped=(key:(p:Part)=>string)=>{try{return groups(key);}catch(error){if(!(error instanceof Censored))throw error;partial=true;inc(error.reason);return{groups:0,members:0,sourceOnlyDrawReductionUpperBound:0,independentlyLoadedGeometryGroups:0,independentMaterialGroups:0};}};
 const exactGeometryAndMaterialIdentity=grouped(p=>p.geometry.id+'|'+p.material+'|'+p.renderState),exactGeometryAndAuditedMaterialValues=grouped(p=>p.geometry.id+'|'+p.equivalentMaterial+'|'+p.renderState);
 return{version:1,scope:'Scene-visible loaded mesh parts; not camera-frustum-tested renderer draw calls or approved instance eligibility',partial,elapsedMs:now()-start,bounds:{...defaults,...Object.fromEntries(Object.keys(defaults).map(k=>[k,bounds[k as keyof typeof defaults]]))},counts,reasons,resources:{geometryIdentities:geometries.size,geometryByteClasses:nextGeometry-1,materialIdentities:materials.size,textureIdentities:textureIds.size,sourceIdentities:sourceIds.size,sharedSources:[...sourceTextures.values()].filter(v=>v.size>1).length,samplerSourceBindings:samplerSources.size},hooks,alphaFlags,
  exactGeometryAndMaterialIdentity,exactGeometryAndAuditedMaterialValues,
  unresolved:['visitor rights and native edits','original per-entity picking','original collision ownership','per-instance frustum visibility','resource restoration before any member replacement','render order and lighting across entities']};
}
