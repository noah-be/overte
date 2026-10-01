// SPDX-License-Identifier: Apache-2.0
import {BakedFbxPreparePool} from '../../src/model-fbx-pool';
import {adaptBakedFbx, normalizeNativeFbxTransparency} from '../../src/baked-fbx';
import {disposeBakedDracoDecoder} from '../../src/baked-draco';
import {disposeLegacyBakedDraco} from '../../src/baked-draco-legacy';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import type {Mesh} from 'three';
export {BakedFbxPreparePool};
export async function baseline(bytes:ArrayBuffer) {
  try {return await adaptBakedFbx(normalizeNativeFbxTransparency(bytes));}
  finally {disposeBakedDracoDecoder();disposeLegacyBakedDraco();}
}
export async function inspect(bytes:ArrayBuffer) {
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  const root=new FBXLoader().parse(bytes,location.origin+'/unused-textures/');
  let meshes=0,vertices=0,triangles=0,groups=0,bones=0;
  const materials=new Set<number>();
  root.traverse(object=>{const mesh=object as Mesh;if(!mesh.isMesh)return;meshes++;
    vertices+=mesh.geometry.attributes.position.count;
    triangles+=(mesh.geometry.index?.count??mesh.geometry.attributes.position.count)/3;
    groups+=mesh.geometry.groups.length;for(const group of mesh.geometry.groups)materials.add(group.materialIndex??0);
    if('skeleton' in mesh)bones+=(mesh.skeleton as {bones:unknown[]}).bones.length;
    mesh.geometry.dispose();for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])material.dispose();
  });
  return {sha256:[...new Uint8Array(hash)].map(value=>value.toString(16).padStart(2,'0')).join(''),bytes:bytes.byteLength,meshes,vertices,triangles,groups,bones,materialIndices:[...materials].sort((a,b)=>a-b)};
}
