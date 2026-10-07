// SPDX-License-Identifier: Apache-2.0
// Test-only private stage inspection. No scene/resource/input state is changed.
import type {Group,Object3D,Mesh} from 'three';
import type {ModelGeometryStage} from '../src/model-geometry-stage';
interface OwnedStage extends ModelGeometryStage { }
export function readStageWitness(world:{objects:Map<string,Group>;modelGeometry:WeakMap<Group,OwnedStage>},id:string){
 const root=world.objects.get(id),stage=root?world.modelGeometry.get(root):undefined,state=stage?.state;
 const model=(stage as unknown as {model?:Object3D}|undefined)?.model;
 let importedMeshes=0,sceneMeshes=0,nodes=0,components=0,censored=false,finite=true;
 const scan=(start:Object3D|undefined,scene:boolean)=>{
  const stack=start?[start]:[],seen=new Set<Object3D>();
  while(stack.length){const node=stack.pop()!;if(++nodes>128||seen.has(node)){censored=true;break;}seen.add(node);
   if((node as Mesh).isMesh){if(scene)sceneMeshes++;else{
    importedMeshes++;const position=(node as Mesh).geometry.attributes.position;
    if(!position||position.count<1||!Number.isSafeInteger(position.count)||components+position.count*3>4096){censored=true;break;}
    for(let i=0;i<position.count;i++){components+=3;if(!Number.isFinite(position.getX(i))||!Number.isFinite(position.getY(i))||!Number.isFinite(position.getZ(i)))finite=false;}
   }}
   if(node.children.length>128-nodes-stack.length){censored=true;break;}stack.push(...node.children);
  }
 };
 scan(model,false);scan(root,true);
 const valid=!!state?.prepared&&!state.committed&&!state.revoked&&root?.userData.modelGeometryReady===true&&importedMeshes>0&&sceneMeshes===0&&finite&&!censored;
 return {valid,prepared:state?.prepared===true,committed:state?.committed===true,revoked:state?.revoked===true,importedMeshes,sceneMeshes,finitePositions:finite,censored};
}
