// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {Bone,DataTexture,Object3D,Skeleton,SkinnedMesh,Texture,TextureSource} from 'three';
const claims=new WeakMap<Skeleton,readonly Bone[]>();
function ownValue(object:object,key:string):unknown{return Object.getOwnPropertyDescriptor(object,key)?.value;}
/** The caller already owns this complete loader graph; userData is not authority.
 * Bones outside the graph, foreign Skeleton/texture implementations and borrowed
 * texture data are excluded. No image/bitmap or other graph is ever closed here.
 */
export function ownedGraphSkeletons(root:Object3D):Set<Skeleton>{
 const nodes=new Set<Object3D>(),queue:Object3D[]=[root],meshes:SkinnedMesh[]=[];
 while(queue.length){const node=queue.pop()!;if(nodes.has(node)||nodes.size>=16384)return new Set();nodes.add(node);
  const children=ownValue(node,'children');if(!Array.isArray(children))return new Set();
  for(const child of children){if(!(child instanceof Object3D)||ownValue(child,'parent')!==node)return new Set();queue.push(child);}
  if(node instanceof SkinnedMesh)meshes.push(node);
 }
 const result=new Set<Skeleton>();
 for(const mesh of meshes){const skeleton=ownValue(mesh,'skeleton');
  if(!(skeleton instanceof Skeleton)||Object.getPrototypeOf(skeleton)!==Skeleton.prototype||Object.getOwnPropertyDescriptor(skeleton,'dispose'))continue;
  const bones=ownValue(skeleton,'bones'),texture=ownValue(skeleton,'boneTexture');
  if(!Array.isArray(bones)||bones.length>4096||bones.some(bone=>!(bone instanceof Bone)||!nodes.has(bone)))continue;
  if(texture!==null){
   if(!(texture instanceof DataTexture)||Object.getPrototypeOf(texture)!==DataTexture.prototype||Object.getOwnPropertyDescriptor(texture,'dispose')||texture.dispose!==Texture.prototype.dispose)continue;
   const source=ownValue(texture,'source');if(!(source instanceof TextureSource)||Object.getPrototypeOf(source)!==TextureSource.prototype)continue;
   const data=ownValue(source,'data'),matrices=ownValue(skeleton,'boneMatrices');
   if(!data||typeof data!=='object'||ownValue(data,'data')!==matrices||!(matrices instanceof Float32Array))continue;
  }
  claims.set(skeleton,[...bones]);result.add(skeleton);
 }
 return result;
}

/** Revalidate the captured loader ownership before a delayed mapping cleanup.
 * In particular, replacement with foreign data/callbacks must not transfer the
 * earlier claim to a different texture or a borrowed bone hierarchy.
 */
export function disposeOwnedSkeleton(skeleton:Skeleton):void{
 const expected=claims.get(skeleton);if(!expected||Object.getPrototypeOf(skeleton)!==Skeleton.prototype||Object.getOwnPropertyDescriptor(skeleton,'dispose'))return;
 const bones=ownValue(skeleton,'bones');if(!Array.isArray(bones)||bones.length!==expected.length||bones.some((bone,index)=>bone!==expected[index]))return;
 const texture=ownValue(skeleton,'boneTexture');
 if(texture!==null){
  if(!(texture instanceof DataTexture)||Object.getPrototypeOf(texture)!==DataTexture.prototype||Object.getOwnPropertyDescriptor(texture,'dispose')||texture.dispose!==Texture.prototype.dispose)return;
  const source=ownValue(texture,'source'),matrices=ownValue(skeleton,'boneMatrices');
  if(!(source instanceof TextureSource)||Object.getPrototypeOf(source)!==TextureSource.prototype)return;
  const data=ownValue(source,'data');if(!data||typeof data!=='object'||ownValue(data,'data')!==matrices||!(matrices instanceof Float32Array))return;
 }
 skeleton.dispose();
}
