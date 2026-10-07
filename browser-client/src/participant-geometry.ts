// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
/** Read-only renderer-owned geometry, not a pixel/native-visual assertion. */
export function inspectParticipantGeometry(scene: THREE.Scene, self: THREE.Group,
  avatars: ReadonlyMap<string, THREE.Group>, states: ReadonlyMap<THREE.Group, {rig?:unknown}>) {
  const result={remoteRoots:avatars.size,attachedRoots:0,renderableRoots:0,rigRoots:0,fallbackRoots:0,
    orphanRoots:0,censored:false,rows:[] as Array<{id:string,rootObjectID:number,attached:boolean,visible:boolean,rig:boolean,geometryMeshes:number}>};
  if(avatars.size>128||scene.children.length>4096){result.censored=true;return result;}
  const owners=new Set(avatars.values());
  if(owners.size!==avatars.size){result.censored=true;return result;}
  result.orphanRoots=scene.children.filter(root=>root!==self&&root.userData.avatar===true&&!owners.has(root as THREE.Group)).length;
  let visited=0;
  for(const[id,root]of avatars){
    const attached=root.parent===scene,rig=!!states.get(root)?.rig;
    let geometryMeshes=0;
    const stack=[{node:root as THREE.Object3D,visible:true}],seen=new Set<THREE.Object3D>();
    while(stack.length){
      const entry=stack.pop()!,node=entry.node;
      if(++visited>16384||seen.has(node)){result.censored=true;return result;}
      seen.add(node);const visible=entry.visible&&node.visible;
      if(visible&&node!==root.userData.avatarLabel&&node instanceof THREE.Mesh){
        const positions=node.geometry.getAttribute('position'),available=node.geometry.index?.count??positions?.count??0;
        const start=Math.max(0,node.geometry.drawRange.start),end=Math.min(available,start+node.geometry.drawRange.count);
        const ranges=Array.isArray(node.material)?node.geometry.groups:[{start,count:end-start,materialIndex:0}];
        if(positions&&ranges.some((range:{start:number;count:number;materialIndex?:number})=>{
          const material=Array.isArray(node.material)?node.material[range.materialIndex??0]:node.material;
          return material?.visible&&material.opacity>0&&Math.min(end,range.start+range.count)>Math.max(start,range.start);
        }))geometryMeshes++;
      }
      if(stack.length+node.children.length>16384){result.censored=true;return result;}
      for(const child of node.children)stack.push({node:child,visible});
    }
    if(attached)result.attachedRoots++;
    if(attached&&geometryMeshes>0)result.renderableRoots++;
    if(rig)result.rigRoots++;else result.fallbackRoots++;
    result.rows.push({id,rootObjectID:root.id,attached,visible:root.visible,rig,geometryMeshes});
  }
  return result;
}
