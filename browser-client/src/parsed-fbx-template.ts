// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {BufferAttribute,Float32BufferAttribute,Float16BufferAttribute,Uint8ClampedBufferAttribute,Uint8BufferAttribute,Int8BufferAttribute,Uint16BufferAttribute,Int16BufferAttribute,Uint32BufferAttribute,Int32BufferAttribute,AnimationClip,Color,Euler,Matrix3,Matrix4,Quaternion,Vector2,Vector3,Vector4, Bone, BufferGeometry, Group, Material, Mesh, MeshLambertMaterial, MeshPhongMaterial, Object3D, SkinnedMesh,Skeleton,KeyframeTrack,NumberKeyframeTrack,BooleanKeyframeTrack,ColorKeyframeTrack,QuaternionKeyframeTrack,StringKeyframeTrack,VectorKeyframeTrack, Texture, TextureSource,DirectionalLight,LightShadow,OrthographicCamera,Camera,WebGLRenderTarget,RenderTarget} from 'three';
import {ParsedFbxAdmissionEvidence,markFbxAdmissionStage,type FbxAdmissionStage,type FbxProducerEvidence} from './parsed-fbx-admission-evidence';
import {clone as cloneSkeletonGraph} from 'three/addons/utils/SkeletonUtils.js';
/** A typed, optional-cache refusal only; parser/driver failures retain their original error. */
export class ParsedFbxTemplateRefusal extends Error {constructor(readonly reason:'graph'|'image'|'capacity'|'changed'){super('Parsed FBX template refused: '+reason);}}
const refuse=(reason:ParsedFbxTemplateRefusal['reason']):never=>{throw new ParsedFbxTemplateRefusal(reason);};
const abort=()=>new DOMException('Parsed FBX template reader ended','AbortError');
const ATTRIBUTE_PROTOTYPES=new Set([BufferAttribute.prototype,Float32BufferAttribute.prototype,Float16BufferAttribute.prototype,Uint8ClampedBufferAttribute.prototype,Uint8BufferAttribute.prototype,Int8BufferAttribute.prototype,Uint16BufferAttribute.prototype,Int16BufferAttribute.prototype,Uint32BufferAttribute.prototype,Int32BufferAttribute.prototype]);
const NODE_PROTOTYPES=new Set([Object3D.prototype,Group.prototype,Mesh.prototype,SkinnedMesh.prototype,Bone.prototype,DirectionalLight.prototype]);
export interface ParsedFbxInspection {readonly bytes:number}
type Inspection=ParsedFbxInspection;
interface NodeLayout {node:Object3D;parent:Object3D|null;array:Object3D[];children:Object3D[];metadataBytes:number;nameBytes:number}
interface ResourceRecord {object:object;prototype:object|null;properties:[PropertyKey,PropertyDescriptor][];hooks:[string,PropertyDescriptor|undefined][];typed?:{buffer:ArrayBufferLike;byteLength:number;byteOffset:number}}
interface ResourceLinks {node:Object3D;properties:[string,PropertyDescriptor][]}
interface ResourceProof {records:ResourceRecord[];links:ResourceLinks[];bytes:number}
interface GraphInspection {nodes:Object3D[];layout:NodeLayout[];resources:ResourceProof;directionalLights:Set<DirectionalLight>; geometries:Set<BufferGeometry>;materials:Set<Material>;textures:Set<Texture>;bytes:number;images:Map<TextureSource<unknown>,{image:HTMLImageElement|null;src:string;width:number;height:number;version:number}>}
function plainOwn(object:object):void{for(const descriptor of Object.values(Object.getOwnPropertyDescriptors(object)))if(!('value'in descriptor))refuse('graph');}
function ordinaryChildren(node:Object3D):{array:Object3D[];children:Object3D[]}{
 const descriptor=Object.getOwnPropertyDescriptor(node,'children');if(!descriptor||!('value'in descriptor)||!Array.isArray(descriptor.value)||Object.getPrototypeOf(descriptor.value)!==Array.prototype)return refuse('graph');const array=descriptor.value as Object3D[],own=Object.getOwnPropertyDescriptors(array) as Record<string,PropertyDescriptor>,length=own['length'];
 if(!length||!('value'in length))return refuse('graph');const count=length.value;if(typeof count!=='number'||!Number.isSafeInteger(count)||count<0||count>8192||Reflect.ownKeys(array).length!==count+1)return refuse('graph');const children:Object3D[]=[];
 for(let i=0;i<count;i++){const child=own[String(i)];if(!child||!('value'in child)||!(child.value instanceof Object3D))return refuse('graph');children.push(child.value);}return{array,children};
}
function checkLayout(layout:readonly NodeLayout[]):void{
 for(const saved of layout){const node=saved.node;plainOwn(node);if(!NODE_PROTOTYPES.has(Object.getPrototypeOf(node))||node.constructor!==Object.getPrototypeOf(node).constructor||node.clone!==Object3D.prototype.clone||node.traverse!==Object3D.prototype.traverse||node.onBeforeRender!==Object3D.prototype.onBeforeRender||node.onAfterRender!==Object3D.prototype.onAfterRender||node.onBeforeShadow!==Object3D.prototype.onBeforeShadow||node.onAfterShadow!==Object3D.prototype.onAfterShadow||node.parent!==saved.parent)refuse('graph');if(jsonSize(node.userData,new Set<object>(),0,node.name==='')!==saved.metadataBytes||jsonSize(node.name)!==saved.nameBytes)refuse('changed');const current=ordinaryChildren(node);if(current.array!==saved.array||current.children.length!==saved.children.length||current.children.some((child,index)=>child!==saved.children[index]))refuse('graph');}
}
const RESOURCE_HOOKS=['constructor','clone','copy','toJSON','slice','map','forEach','getSize'] as const;
const TYPED_EXTENT_KEYS=['buffer','byteLength','byteOffset'] as const;
const typedArrayExtent=Object.getOwnPropertyDescriptors(Object.getPrototypeOf(Uint8Array.prototype)),dataViewExtent=Object.getOwnPropertyDescriptors(DataView.prototype);
function typedExtent(view:ArrayBufferView):{buffer:ArrayBufferLike;byteLength:number;byteOffset:number}{
 for(const key of TYPED_EXTENT_KEYS)if(Object.getOwnPropertyDescriptor(view,key))refuse('graph');const descriptors=view instanceof DataView?dataViewExtent:typedArrayExtent;
 try{return{buffer:descriptors.buffer.get!.call(view),byteLength:descriptors.byteLength.get!.call(view),byteOffset:descriptors.byteOffset.get!.call(view)};}catch{return refuse('changed');}
}
function inheritedDescriptor(object:object,key:string):PropertyDescriptor|undefined{
 for(let current:object|null=object,depth=0;current;current=Object.getPrototypeOf(current)){if(depth++>32)refuse('graph');const descriptor=Object.getOwnPropertyDescriptor(current,key);if(descriptor){if(!('value'in descriptor))refuse('graph');return descriptor;}}return undefined;
}
function sameDescriptor(a:PropertyDescriptor|undefined,b:PropertyDescriptor|undefined):boolean{return a===undefined?b===undefined:b!==undefined&&'value'in a&&'value'in b&&a.value===b.value&&a.enumerable===b.enumerable&&a.writable===b.writable&&a.configurable===b.configurable;}
/** Retain immutable resource references, never element copies or new image reads. */
function snapshotResources(nodes:readonly Object3D[]):ResourceProof{
 const records:ResourceRecord[]=[],links:ResourceLinks[]=[],seen=new Set<object>();let bytes=0,propertyCount=0;
 const charge=(amount:number)=>{bytes+=amount;if(bytes>64*1024*1024)refuse('capacity');};
 const visit=(value:unknown,depth=0):void=>{
  if(value===null||typeof value!=='object'||value instanceof Object3D||value instanceof ArrayBuffer||seen.has(value))return;if(depth>128||seen.size>=65536)refuse('capacity');seen.add(value);const prototype=Object.getPrototypeOf(value),hooks=RESOURCE_HOOKS.map(key=>[key,inheritedDescriptor(value,key)] as [string,PropertyDescriptor|undefined]);
  const typed=ArrayBuffer.isView(value)?typedExtent(value):undefined;
  // Typed arrays can contain millions of numeric properties. Clone only reads
  // their extent and intrinsic methods; do not enumerate or duplicate elements.
  const keys=typed?['constructor','slice','clone','copy','toJSON']:Reflect.ownKeys(value).filter(key=>key!=='_listeners');const properties:[PropertyKey,PropertyDescriptor][]=[];charge(64+hooks.length*48);
  for(const key of keys){const descriptor=Object.getOwnPropertyDescriptor(value,key);if(!descriptor)continue;if(!('value'in descriptor))refuse('graph');if(++propertyCount>262144)refuse('capacity');properties.push([key,descriptor]);charge(48+(typeof key==='string'?key.length*2:16));
   // Source.data is externally decoded HTML data; its original identity/version
   // and dimensions remain governed by the separate existing image stamp.
   if(!(value instanceof TextureSource&&key==='data'))visit(descriptor.value,depth+1);
  }records.push({object:value,prototype,properties,hooks,typed});
 };
 for(const node of nodes){const properties:[string,PropertyDescriptor][]=[];for(const key of ['animations','userData',...(node instanceof Mesh?['geometry','material']:[]),...(node instanceof SkinnedMesh?['skeleton']:[])]){const descriptor=Object.getOwnPropertyDescriptor(node,key);if(!descriptor||!('value'in descriptor))return refuse('graph');properties.push([key,descriptor]);charge(48+key.length*2);if(key!=='userData')visit(descriptor.value);}links.push({node,properties});charge(32);}
 return{records,links,bytes};
}
function checkResources(proof:ResourceProof):void{
 for(const {node,properties}of proof.links)for(const [key,descriptor]of properties)if(!sameDescriptor(descriptor,Object.getOwnPropertyDescriptor(node,key)))refuse('changed');
 for(const {object,prototype,properties,hooks,typed}of proof.records){if(Object.getPrototypeOf(object)!==prototype)refuse('graph');for(const [key,descriptor]of hooks)if(!sameDescriptor(descriptor,inheritedDescriptor(object,key)))refuse('graph');
  if(typed){if(!ArrayBuffer.isView(object))return refuse('changed');const current=typedExtent(object);if(current.buffer!==typed.buffer||current.byteLength!==typed.byteLength||current.byteOffset!==typed.byteOffset)refuse('changed');}
  else if(Reflect.ownKeys(object).filter(key=>key!=='_listeners').length!==properties.length)refuse('changed');
  for(const [key,descriptor]of properties)if(!sameDescriptor(descriptor,Object.getOwnPropertyDescriptor(object,key)))refuse('changed');
 }
}
const proofs=new WeakMap<Inspection,{root:Object3D;graph:GraphInspection}>();
const TRACK_PROTOTYPES=new Set([NumberKeyframeTrack.prototype,BooleanKeyframeTrack.prototype,ColorKeyframeTrack.prototype,QuaternionKeyframeTrack.prototype,StringKeyframeTrack.prototype,VectorKeyframeTrack.prototype]);
const MATH_PROTOTYPES=new Set([Color.prototype,Euler.prototype,Matrix3.prototype,Matrix4.prototype,Quaternion.prototype,Vector2.prototype,Vector3.prototype,Vector4.prototype]);
function jsonSize(value:unknown,seen=new Set<object>(),depth=0,allowUnnamedFbxOriginalName=false):number{
 if(depth>24)refuse('graph');if(value===null||typeof value==='boolean')return 8;if(typeof value==='number'){if(!Number.isFinite(value))refuse('graph');return 8;}
 if(typeof value==='string'){if(value.length>65536)refuse('graph');return value.length*2+8;}
 if(typeof value!=='object'||value===undefined) return refuse('graph');if(seen.has(value))refuse('graph');seen.add(value);plainOwn(value);
 if(!Array.isArray(value)&&Object.getPrototypeOf(value)!==Object.prototype&&!MATH_PROTOTYPES.has(Object.getPrototypeOf(value)))refuse('graph');let total=32;
 for(const [key,descriptor]of Object.entries(Object.getOwnPropertyDescriptors(value))){
  // FBXLoader assigns originalName even when BinaryParser has no attrName.
  // Keep this one ordinary top-level absent-name value, without deleting or
  // normalizing producer metadata. Nested/other undefined values still refuse.
  const absentName=allowUnnamedFbxOriginalName&&key==='originalName'&&descriptor.value===undefined&&descriptor.enumerable===true&&descriptor.writable===true&&descriptor.configurable===true&&Object.getPrototypeOf(value)===Object.prototype;
  total+=key.length*2+(absentName?8:jsonSize(descriptor.value,seen,depth+1));if(total>1024*1024)refuse('capacity');
 }seen.delete(value);return total;
}
// Only the detached default target/shadow graph constructed by FBXLoader.
// A graph-linked target requires explicit remapping and is deliberately refused.
const directionalDefaults=new DirectionalLight(),directionalShadowPrototype=Object.getPrototypeOf(directionalDefaults.shadow),directionalShadowConstructor=directionalDefaults.shadow.constructor;
function defaultDirectionalDescriptorBytes(value:unknown,reference:unknown,pairs=new Map<object,object>(),depth=0,key=''):number{
 if(depth>24)refuse('graph');
 if(reference===null||typeof reference!=='object'){
  // Object3D owns rotation/quaternion synchronization closures. Object3D.copy
  // creates its own closures; it does not copy or invoke the source closures.
  if(key==='_onChangeCallback'&&typeof reference==='function'&&typeof value==='function')return 16;
  if(key==='id'&&typeof reference==='number'&&typeof value==='number'&&Number.isSafeInteger(value)&&value>=0)return 8;
  if(key==='uuid'&&typeof reference==='string'&&typeof value==='string'&&value.length===reference.length)return value.length*2+8;
  if(value!==reference)refuse('graph');return typeof value==='string'?value.length*2+8:8;
 }
 if(value===null||typeof value!=='object'||Object.getPrototypeOf(value)!==Object.getPrototypeOf(reference))refuse('graph');
 if(pairs.has(value as object)){if(pairs.get(value as object)!==reference)refuse('graph');return 8;}pairs.set(value as object,reference as object);
 const a=Object.getOwnPropertyDescriptors(value),b=Object.getOwnPropertyDescriptors(reference);if(Reflect.ownKeys(value as object).length!==Reflect.ownKeys(reference).length)refuse('graph');let bytes=32;
 for(const [name,expected]of Object.entries(b)){const actual=a[name];if(!actual||!('value'in actual)||!('value'in expected)||actual.enumerable!==expected.enumerable||actual.writable!==expected.writable||actual.configurable!==expected.configurable)refuse('graph');bytes+=name.length*2+defaultDirectionalDescriptorBytes(actual.value,expected.value,pairs,depth+1,name);}
 return bytes;
}
function privateDirectionalBytes(light:DirectionalLight,privateDescriptors:Set<object>):number{
 plainOwn(light);if(Object.getPrototypeOf(light)!==DirectionalLight.prototype||light.constructor!==DirectionalLight||light.clone!==Object3D.prototype.clone||light.traverse!==Object3D.prototype.traverse||light.onBeforeRender!==Object3D.prototype.onBeforeRender||light.onAfterRender!==Object3D.prototype.onAfterRender||light.onBeforeShadow!==Object3D.prototype.onBeforeShadow||light.onAfterShadow!==Object3D.prototype.onAfterShadow)refuse('graph');jsonSize(light.userData,new Set<object>(),0,light.name==='');
 if(light.copy!==DirectionalLight.prototype.copy||light.dispose!==DirectionalLight.prototype.dispose||light.castShadow!==false)refuse('graph');
 if(Object.getPrototypeOf(light.color)!==Color.prototype||!Number.isFinite(light.intensity))refuse('graph');plainOwn(light.color);const colorBytes=jsonSize(light.color);
 const target=light.target,shadow=light.shadow;plainOwn(target);plainOwn(shadow);
 if(Object.getPrototypeOf(target)!==Object3D.prototype||target.constructor!==Object3D||target.clone!==Object3D.prototype.clone||target.copy!==Object3D.prototype.copy||target.traverse!==Object3D.prototype.traverse||target.parent!==null||target.children.length!==0)refuse('graph');
 if(Object.getPrototypeOf(shadow)!==directionalShadowPrototype||shadow.constructor!==directionalShadowConstructor||shadow.clone!==LightShadow.prototype.clone||shadow.copy!==LightShadow.prototype.copy||shadow.dispose!==LightShadow.prototype.dispose||shadow.map!==null||shadow.mapPass!==null||shadow.biasNode!==null)refuse('graph');
 const camera=shadow.camera;plainOwn(camera);if(Object.getPrototypeOf(camera)!==OrthographicCamera.prototype||camera.constructor!==OrthographicCamera||camera.clone!==Camera.prototype.clone||camera.copy!==OrthographicCamera.prototype.copy)refuse('graph');
 for(const descriptor of [target,shadow,camera]){if(privateDescriptors.has(descriptor))refuse('graph');privateDescriptors.add(descriptor);}
 return colorBytes+defaultDirectionalDescriptorBytes(target,directionalDefaults.target)+defaultDirectionalDescriptorBytes(shadow,directionalDefaults.shadow);
}
const disposedDirectionalLights=new WeakSet<DirectionalLight>(),disposedDirectionalTargets=new WeakSet<RenderTarget>();
function disposePrivateDirectionalLight(light:DirectionalLight):void{
 if(disposedDirectionalLights.has(light)||Object.getPrototypeOf(light)!==DirectionalLight.prototype)return;
 const descriptor=Object.getOwnPropertyDescriptor(light,'shadow');if(!descriptor||!('value'in descriptor))return;const shadow=descriptor.value;
 if(!shadow||Object.getPrototypeOf(shadow)!==directionalShadowPrototype||shadow.dispose!==LightShadow.prototype.dispose)return;
 try{plainOwn(shadow);}catch{return;}disposedDirectionalLights.add(light);
 try{Object3D.prototype.dispose.call(light);}finally{
  // One owned target's disposal listener must not skip another owned target.
  const targets=[shadow.map,shadow.mapPass];shadow.map=null;shadow.mapPass=null;for(const target of targets)if(target&&Object.getPrototypeOf(target)===WebGLRenderTarget.prototype&&!disposedDirectionalTargets.has(target)){try{plainOwn(target);if(target.constructor!==WebGLRenderTarget||target.dispatchEvent!==WebGLRenderTarget.prototype.dispatchEvent)continue;disposedDirectionalTargets.add(target);RenderTarget.prototype.dispose.call(target);}catch{}}
 }
}
function cloneData(value:any):any{if(value===null||typeof value!=='object')return value;if(MATH_PROTOTYPES.has(Object.getPrototypeOf(value)))return value.clone();if(Array.isArray(value))return value.map(cloneData);return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,cloneData(item)]));}
/** Inspect only the fully loaded private parse graph; never admit metadata/userData as trust. */
export function inspectParsedFbxTemplate(root:Object3D,allowPending=false,transientImages=false):Inspection{
 let stage:FbxAdmissionStage='nodes';try{
 const nodes:Object3D[]=[],layout:NodeLayout[]=[],directionalLights=new Set<DirectionalLight>(),geometries=new Set<BufferGeometry>(),materials=new Set<Material>(),textures=new Set<Texture>(),images:GraphInspection['images']=new Map(),todo:[[Object3D,number]]=[[root,0]],seen=new Set<Object3D>(),privateDirectionalDescriptors=new Set<object>();let bytes=0;
 while(todo.length){const [node,depth]=todo.pop()!;if(depth>128||seen.has(node)||nodes.length>=8192||!NODE_PROTOTYPES.has(Object.getPrototypeOf(node)))refuse('graph');seen.add(node);plainOwn(node);if(node.constructor!==Object.getPrototypeOf(node).constructor)refuse('graph');
  if(node.onBeforeRender!==Object3D.prototype.onBeforeRender||node.onAfterRender!==Object3D.prototype.onAfterRender||node.onBeforeShadow!==Object3D.prototype.onBeforeShadow||node.onAfterShadow!==Object3D.prototype.onAfterShadow)refuse('graph');
  if(node.clone!==Object3D.prototype.clone||node.traverse!==Object3D.prototype.traverse)refuse('graph');if(node instanceof DirectionalLight){bytes+=privateDirectionalBytes(node,privateDirectionalDescriptors);directionalLights.add(node);}nodes.push(node);const metadataBytes=jsonSize(node.userData,new Set<object>(),0,node.name===''),nameBytes=jsonSize(node.name);bytes+=512+metadataBytes+nameBytes;
  const childState=ordinaryChildren(node);layout.push({node,parent:node.parent,...childState,metadataBytes,nameBytes});bytes+=56+childState.children.length*8;for(const child of childState.children){plainOwn(child);if(child.parent!==node)refuse('graph');todo.push([child,depth+1]);}
  for(const clip of node.animations){plainOwn(clip);bytes+=jsonSize(clip.name);if(Object.getPrototypeOf(clip)!==AnimationClip.prototype||clip.clone!==AnimationClip.prototype.clone||clip.constructor!==AnimationClip)refuse('graph');for(const track of clip.tracks){plainOwn(track);if(!TRACK_PROTOTYPES.has(Object.getPrototypeOf(track))||track.clone!==KeyframeTrack.prototype.clone||track.constructor!==Object.getPrototypeOf(track).constructor)refuse('graph');bytes+=track.times.byteLength+(ArrayBuffer.isView(track.values)?track.values.byteLength:jsonSize(track.values))+jsonSize(track.name);}}
  if(node instanceof Mesh){if(Object.getPrototypeOf(node.geometry)!==BufferGeometry.prototype)refuse('graph');geometries.add(node.geometry);for(const material of Array.isArray(node.material)?node.material:[node.material])materials.add(material);}
 }
 stage='geometry';for(const geometry of geometries){plainOwn(geometry);if(geometry.clone!==BufferGeometry.prototype.clone)refuse('graph');bytes+=256+jsonSize(geometry.name)+jsonSize(geometry.userData);
  for(const attribute of [geometry.index,...Object.values(geometry.attributes),...Object.values(geometry.morphAttributes).flat()])if(attribute){plainOwn(attribute);if(!(attribute instanceof BufferAttribute)||!ATTRIBUTE_PROTOTYPES.has(Object.getPrototypeOf(attribute))||attribute.clone!==BufferAttribute.prototype.clone||attribute.constructor!==Object.getPrototypeOf(attribute).constructor||attribute.onUploadCallback!==BufferAttribute.prototype.onUploadCallback)refuse('graph');if('isInterleavedBufferAttribute'in attribute||!ArrayBuffer.isView(attribute.array))refuse('graph');bytes+=attribute.array.byteLength;}
 }
 stage='materials';for(const material of materials){plainOwn(material);if(![MeshPhongMaterial.prototype,MeshLambertMaterial.prototype].includes(Object.getPrototypeOf(material))||material.onBeforeCompile!==Material.prototype.onBeforeCompile||material.customProgramCacheKey!==Material.prototype.customProgramCacheKey||material.clone!==Material.prototype.clone||material.constructor!==Object.getPrototypeOf(material).constructor)refuse('graph');bytes+=512+jsonSize(material.userData)+jsonSize(material.name);for(const value of Object.values(material))if(value instanceof Texture)textures.add(value);}
 stage='textures';for(const texture of textures){plainOwn(texture);if(Object.getPrototypeOf(texture)!==Texture.prototype||texture.clone!==Texture.prototype.clone||texture.copy!==Texture.prototype.copy||texture.mipmaps.length||texture.isRenderTargetTexture)refuse('image');
  const source=texture.source;plainOwn(source);if(source.getSize!==TextureSource.prototype.getSize||source.dataReady!==true)refuse('image');if(source.constructor!==TextureSource)refuse('image');if(Object.getPrototypeOf(source)!==TextureSource.prototype)refuse('image');if(allowPending&&source.data===null){images.set(source,{image:null,src:'',width:0,height:0,version:source.version});bytes+=256;continue;}if(typeof HTMLImageElement==='undefined'||!(source.data instanceof HTMLImageElement))refuse('image');
  const image=source.data as HTMLImageElement;if(!image.complete||image.naturalWidth<=0||image.naturalHeight<=0||image.naturalWidth*image.naturalHeight>64*1024*1024)refuse('image');
  const src=image.currentSrc||image.src;if(src.length>65536)refuse('capacity');images.set(source,{image,src,width:image.naturalWidth,height:image.naturalHeight,version:source.version});bytes+=256+src.length*2+jsonSize(texture.userData)+jsonSize(texture.name);
 }
 let decodedBytes=0;for(const stamp of images.values())decodedBytes+=stamp.width*stamp.height*4;
 stage='skeleton';for(const node of nodes)if(node instanceof SkinnedMesh){plainOwn(node.skeleton);if(Object.getPrototypeOf(node.skeleton)!==Skeleton.prototype||node.skeleton.clone!==Skeleton.prototype.clone||node.skeleton.constructor!==Skeleton)refuse('graph');for(const inverse of node.skeleton.boneInverses){plainOwn(inverse);if(Object.getPrototypeOf(inverse)!==Matrix4.prototype||inverse.clone!==Matrix4.prototype.clone||inverse.constructor!==Matrix4)refuse('graph');}for(const bone of node.skeleton.bones)if(!seen.has(bone))refuse('graph');if(node.skeleton.bones.length>4096||node.skeleton.boneInverses.length!==node.skeleton.bones.length)refuse('graph');bytes+=(node.skeleton.boneMatrices?.byteLength??node.skeleton.bones.length*64)+node.skeleton.boneInverses.length*128;}
 stage='budget';const resources=snapshotResources(nodes);bytes+=resources.bytes;if(bytes>64*1024*1024||!transientImages&&bytes+decodedBytes>64*1024*1024)refuse('capacity');bytes+=decodedBytes;const token=Object.freeze({bytes});proofs.set(token,{root,graph:{nodes,layout,resources,directionalLights,geometries,materials,textures,bytes,images}});return token;
 }catch(error){markFbxAdmissionStage(error,stage);throw error;}
}
function checkImages(inspection:Inspection):void{try{const proof=proofs.get(inspection);if(!proof)refuse('graph');for(const [source,stamp]of proof!.graph.images){if(stamp.image===null){if(source.data!==null||source.version!==stamp.version)refuse('changed');continue;}const image=source.data as HTMLImageElement;if(image!==stamp.image||source.version!==stamp.version||!image.complete||(image.currentSrc||image.src)!==stamp.src||image.naturalWidth!==stamp.width||image.naturalHeight!==stamp.height)refuse('changed');}}catch(error){markFbxAdmissionStage(error,'image-stamp');throw error;}}
/** Each clone owns all mutable scene/GPU descriptors. Only immutable loaded HTML data is borrowed. */
export function cloneParsedFbxTemplate(root:Object3D,inspection=inspectParsedFbxTemplate(root)):Object3D{
 if(proofs.get(inspection)?.root!==root)refuse('graph');checkLayout(proofs.get(inspection)!.graph.layout);checkResources(proofs.get(inspection)!.graph.resources);checkImages(inspection);const privateDescriptors=new Set<object>();for(const light of proofs.get(inspection)!.graph.directionalLights)privateDirectionalBytes(light,privateDescriptors);const result=cloneSkeletonGraph(root),geometryClones=new Map<BufferGeometry,BufferGeometry>(),materialClones=new Map<Material,Material>(),textureClones=new Map<Texture,Texture>(),animationClones=new Map<AnimationClip,AnimationClip>();
 try{const pairs:[Object3D,Object3D][]=[[root,result]];while(pairs.length){const [source,node]=pairs.pop()!;node.userData=cloneData(source.userData);for(let index=0;index<source.children.length;index++)pairs.push([source.children[index],node.children[index]]);}
 result.traverse(node=>{
   node.animations=node.animations.map(clip=>{let copy=animationClones.get(clip);if(!copy){copy=clip.clone();animationClones.set(clip,copy);}return copy;});
   if(!(node instanceof Mesh))return;let geometry=geometryClones.get(node.geometry);if(!geometry){geometry=node.geometry.clone() as BufferGeometry;geometryClones.set(node.geometry,geometry);}node.geometry=geometry;
   const cloneMaterial=(material:Material)=>{let copy=materialClones.get(material);if(copy)return copy;copy=material.clone();materialClones.set(material,copy);
    for(const [key,value]of Object.entries(material))if(value instanceof Texture){let texture=textureClones.get(value);if(!texture){
      // Texture.copy raises Source.version; copy through a private temporary Source,
      // then restore the shared image-cache Source without modifying its version.
      const surrogate=Object.create(value)as Texture;Object.defineProperty(surrogate,'source',{value:new TextureSource(value.source.data)});
      texture=new Texture().copy(surrogate);texture.source=value.source;textureClones.set(value,texture);
     }(copy as unknown as Record<string,unknown>)[key]=texture;}
    return copy;
   };node.material=Array.isArray(node.material)?node.material.map(cloneMaterial):cloneMaterial(node.material);
   if(node instanceof SkinnedMesh)node.skeleton.boneInverses=node.skeleton.boneInverses.map(matrix=>matrix.clone());
  });checkImages(inspection);return result;
 }catch(error){for(const geometry of geometryClones.values())try{geometry.dispose();}catch{}for(const texture of textureClones.values())try{texture.dispose();}catch{}for(const material of materialClones.values())try{material.dispose();}catch{}result.traverse(node=>{if(node instanceof DirectionalLight)try{disposePrivateDirectionalLight(node);}catch{}if(node instanceof SkinnedMesh)try{node.skeleton.dispose();}catch{}});throw error;}
}
/** Caller supplies only its own graph. No image/bitmap close or cross-owner resource disposal. */
export function disposeParsedFbxGraph(root:Object3D):void{
 const geometries=new Set<BufferGeometry>(),materials=new Set<Material>(),textures=new Set<Texture>(),lights=new Set<DirectionalLight>();root.traverse(node=>{if(node instanceof DirectionalLight&&Object.getPrototypeOf(node)===DirectionalLight.prototype)lights.add(node);if(!(node instanceof Mesh))return;geometries.add(node.geometry);for(const m of Array.isArray(node.material)?node.material:[node.material]){materials.add(m);for(const v of Object.values(m))if(v instanceof Texture)textures.add(v);}if(node instanceof SkinnedMesh)try{node.skeleton.dispose();}catch{}});
 for(const light of lights)try{disposePrivateDirectionalLight(light);}catch{}
 for(const values of [geometries,textures,materials])for(const value of values)try{value.dispose();}catch{}
}
interface Entry {evidence:FbxProducerEvidence;transient?:boolean;buffer:ArrayBuffer;key:string;generation:number;controller:AbortController;readers:Set<Reader>;root?:Object3D;inspection?:Inspection;promise:Promise<Entry>;active:boolean;timer?:ReturnType<typeof setTimeout>}
interface Reader {assertCurrent():void;resolve(root:Object3D):void;reject(error:unknown):void;signal?:AbortSignal;clone?:Object3D;onGeometryReady?:(root:Object3D)=>void;cancel():void}
/** Standalone, disabled until integrated and genuinely qualified. No renderer or asset request. */
export class ParsedFbxTemplates {
 private readonly admissionEvidence=new ParsedFbxAdmissionEvidence();
 private noteProducerFailure(entry:Entry,error:unknown,location:Parameters<ParsedFbxAdmissionEvidence['failure']>[2]):void{let reason:ParsedFbxTemplateRefusal['reason']|undefined;try{if(error instanceof ParsedFbxTemplateRefusal){const descriptor=Object.getOwnPropertyDescriptor(error,'reason');if(descriptor&&'value'in descriptor&&['graph','image','capacity','changed'].includes(descriptor.value))reason=descriptor.value;}}catch{}this.admissionEvidence.failure(entry.evidence,error,location,reason);}
 private readonly groups=new WeakMap<ArrayBuffer,Map<string,Entry>>();private readonly ready=new Map<Entry,number>();private readonly pending=new Set<Entry>();private generation=0;private closed=false;private bytes=0;private readers=0;
 private readonly counts={producers:0,hits:0,joined:0,cloned:0,evicted:0,refused:0,transient:0};
 constructor(private readonly signal:AbortSignal){signal.addEventListener('abort',this.onAbort,{once:true});if(signal.aborted)this.dispose();}
 private readonly onAbort=()=>this.dispose();
 get(buffer:ArrayBuffer,key:string,assertCurrent:()=>void,producer:(signal:AbortSignal,onParsed:(root:Object3D)=>void)=>Promise<Object3D>,signal?:AbortSignal,onGeometryReady?:(root:Object3D)=>void):Promise<Object3D>{
  try{assertCurrent();if(this.closed||this.signal.aborted||signal?.aborted)throw abort();if(!(buffer instanceof ArrayBuffer)||!buffer.byteLength||buffer.byteLength>32*1024*1024||key.length>8192||this.readers>=64)refuse('capacity');}catch(error){return Promise.reject(error);}
  let group=this.groups.get(buffer);if(!group){group=new Map();this.groups.set(buffer,group);}let entry=group.get(key);
  if(entry?.root&&!entry.active){let clone:Object3D|undefined;try{assertCurrent();checkImages(entry.inspection!);clone=cloneParsedFbxTemplate(entry.root,entry.inspection);assertCurrent();if(this.closed||signal?.aborted||entry.generation!==this.generation)throw abort();onGeometryReady?.(clone);assertCurrent();if(this.closed||signal?.aborted)throw abort();const weight=this.ready.get(entry);if(weight!==undefined){this.ready.delete(entry);this.ready.set(entry,weight);}this.counts.hits++;this.counts.cloned++;const returned=clone;clone=undefined;return Promise.resolve(returned);}catch(error){if(clone)disposeParsedFbxGraph(clone);if(error instanceof ParsedFbxTemplateRefusal){this.drop(entry);this.counts.refused++;}return Promise.reject(error);}}
  if(!entry){if(this.pending.size>=6){this.counts.refused++;return Promise.reject(new ParsedFbxTemplateRefusal('capacity'));}const controller=new AbortController(),generation=this.generation;
   entry={evidence:this.admissionEvidence.start(buffer,key),buffer,key,generation,controller,readers:new Set(),promise:Promise.resolve(undefined as unknown as Entry),active:true};group.set(key,entry);this.pending.add(entry);this.counts.producers++;
   const owned=entry;entry.timer=setTimeout(()=>{owned.controller.abort();this.failReaders(owned,Error('Parsed FBX template exceeded existing 30 second readiness deadline'));this.drop(owned);},30000);
   entry.promise=Promise.resolve().then(()=>{assertCurrent();if(controller.signal.aborted)throw abort();return producer(controller.signal,root=>{assertCurrent();if(this.closed||controller.signal.aborted||generation!==this.generation)throw abort();if(owned.root&&owned.root!==root)refuse('changed');owned.root=root;let inspection:Inspection;try{inspection=inspectParsedFbxTemplate(root,true);}catch(error){this.noteProducerFailure(owned,error,'provisional-inspection');this.failReaders(owned,error);owned.controller.abort();return;}for(const reader of [...owned.readers])if(reader.onGeometryReady)this.prepareReader(owned,reader,inspection);});}).then(root=>{if(owned.root&&owned.root!==root){disposeParsedFbxGraph(root);refuse('changed');}owned.root=root;if(this.closed||generation!==this.generation||controller.signal.aborted||!owned.readers.size){disposeParsedFbxGraph(root);owned.root=undefined;throw abort();}try{
     try{owned.inspection=inspectParsedFbxTemplate(root,false,true);}catch(error){
      // The original parser can succeed with warned missing images. Finish the
      // already staged independent clones unchanged, but never cache that root.
      if(!(error instanceof ParsedFbxTemplateRefusal)||error.reason!=='image')throw error;
      owned.inspection=inspectParsedFbxTemplate(root,true,true);owned.transient=true;
     }
     assertCurrent();if(controller.signal.aborted)throw abort();
    }catch(error){this.noteProducerFailure(owned,error,'ready-inspection');disposeParsedFbxGraph(root);owned.root=undefined;throw error;}return owned;});
   entry.promise.then(value=>{clearTimeout(value.timer);value.active=false;this.pending.delete(value);if(this.closed||value.controller.signal.aborted){this.drop(value);this.failReaders(value,abort());return;}const weight=value.inspection!.bytes+buffer.byteLength+key.length*2;if(weight>64*1024*1024)value.transient=true;if(!value.transient){this.ready.set(value,weight);this.bytes+=weight;while(this.ready.size>32||this.bytes>64*1024*1024){const old=this.ready.keys().next().value!;this.drop(old);this.counts.evicted++;}}else this.counts.transient++;for(const reader of [...value.readers]){let clone:Object3D|undefined;try{if(!value.readers.has(reader))continue;reader.assertCurrent();if(this.closed||value.generation!==this.generation||reader.signal?.aborted)throw abort();clone=reader.clone??cloneParsedFbxTemplate(value.root!,value.inspection);reader.clone=undefined;reader.assertCurrent();if(this.closed||reader.signal?.aborted||value.generation!==this.generation)throw abort();reader.resolve(clone);clone=undefined;this.counts.cloned++;}catch(error){if(clone)disposeParsedFbxGraph(clone);reader.reject(error);}finally{this.removeReader(value,reader);}}if(value.transient)this.drop(value);},error=>{this.noteProducerFailure(owned,error,'producer-rejection');clearTimeout(owned.timer);owned.active=false;this.pending.delete(owned);owned.root=undefined;this.drop(owned);this.failReaders(owned,error);}).catch(()=>{});
  }else this.counts.joined++;
  const owned=entry;return new Promise((resolve,reject)=>{const reader:Reader={assertCurrent,resolve,reject,signal,onGeometryReady,cancel:()=>{if(reader.clone){disposeParsedFbxGraph(reader.clone);reader.clone=undefined;}reject(abort());this.removeReader(owned,reader);if(!owned.readers.size&&owned.active){owned.controller.abort();this.drop(owned);}}};owned.readers.add(reader);this.readers++;signal?.addEventListener('abort',reader.cancel,{once:true});if(signal?.aborted)reader.cancel();else if(owned.active&&owned.root&&reader.onGeometryReady)try{this.prepareReader(owned,reader,inspectParsedFbxTemplate(owned.root,true));}catch(error){reader.reject(error);this.removeReader(owned,reader);if(!owned.readers.size)owned.controller.abort();}});
 }
 private prepareReader(entry:Entry,reader:Reader,inspection:Inspection):void{if(reader.clone)return;let clone:Object3D|undefined;try{reader.assertCurrent();if(this.closed||reader.signal?.aborted||entry.controller.signal.aborted)throw abort();clone=cloneParsedFbxTemplate(entry.root!,inspection);reader.onGeometryReady?.(clone);reader.assertCurrent();if(this.closed||reader.signal?.aborted||entry.controller.signal.aborted)throw abort();reader.clone=clone;clone=undefined;}catch(error){if(clone)disposeParsedFbxGraph(clone);reader.reject(error);this.removeReader(entry,reader);if(!entry.readers.size)entry.controller.abort();}}
 private removeReader(entry:Entry,reader:Reader):void{if(!entry.readers.delete(reader))return;this.readers--;reader.signal?.removeEventListener('abort',reader.cancel);}
 private failReaders(entry:Entry,error:unknown):void{for(const reader of [...entry.readers]){if(reader.clone){disposeParsedFbxGraph(reader.clone);reader.clone=undefined;}reader.reject(error);this.removeReader(entry,reader);}}
 private drop(entry:Entry):void{clearTimeout(entry.timer);const group=this.groups.get(entry.buffer);if(group?.get(entry.key)===entry)group.delete(entry.key);const weight=this.ready.get(entry);if(weight!==undefined){this.ready.delete(entry);this.bytes-=weight;}if(entry.root&&!entry.active){disposeParsedFbxGraph(entry.root);entry.root=undefined;entry.inspection=undefined;}}
 get statistics(){return {admissionEvidence:this.admissionEvidence.snapshot,...this.counts,ready:this.ready.size,pending:this.pending.size,readers:this.readers,bytes:this.bytes};}
 dispose():void{if(this.closed)return;this.closed=true;this.admissionEvidence.dispose();this.generation++;this.signal.removeEventListener('abort',this.onAbort);for(const entry of this.pending){entry.controller.abort();this.failReaders(entry,abort());this.drop(entry);}for(const entry of [...this.ready.keys()])this.drop(entry);}
}
