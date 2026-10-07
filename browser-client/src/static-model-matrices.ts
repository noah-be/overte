// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {Group,Material,Mesh,MeshBasicMaterial,MeshLambertMaterial,MeshPhongMaterial,MeshStandardMaterial,MeshPhysicalMaterial,Object3D} from 'three';
import {hasNativeAlphaShader} from './native-alpha-material';
import {hasNativeZeroLightShader} from './native-zero-lights';

const methods=['updateWorldMatrix','updateMatrix','onBeforeRender','onAfterRender','onBeforeShadow','onAfterShadow'] as const;
interface Snapshot {object:Object3D;parent:Object3D|null;children:readonly Object3D[];values:Float64Array;auto:boolean;worldAuto:boolean}
export interface StaticMatrixStatistics {activeRoots:number;retainedNodes:number;skippedTraversals:number;updatedTraversals:number;refusedRoots:number;changedGraphs:number}
const MAX_ROOTS=512,MAX_NODES=20000,MAX_ROOT_NODES=8192;
function values(object:Object3D):number[]{return [object.position.x,object.position.y,object.position.z,object.quaternion.x,object.quaternion.y,object.quaternion.z,object.quaternion.w,object.scale.x,object.scale.y,object.scale.z,...object.matrix.elements,...object.matrixWorld.elements];}
const knownMaterials=new Set<Function>([MeshBasicMaterial,MeshLambertMaterial,MeshPhongMaterial,MeshStandardMaterial,MeshPhysicalMaterial]);
function materialSafe(material:Material):boolean{
 if(!knownMaterials.has(material.constructor))return false;
 return material.onBeforeCompile===Material.prototype.onBeforeCompile&&material.customProgramCacheKey===Material.prototype.customProgramCacheKey||hasNativeAlphaShader(material)||hasNativeZeroLightShader(material);}
function safe(object:Object3D,root:Object3D,wrapper:Object3D['updateMatrixWorld']):boolean{
 if(object.constructor!==Object3D&&object.constructor!==Group&&object.constructor!==Mesh)return false;
 if(object.animations.length)return false;
 for(const key of methods)if(object[key]!==Object3D.prototype[key])return false;
 if(object.updateMatrixWorld!==(object===root?wrapper:Object3D.prototype.updateMatrixWorld))return false;
 if(object instanceof Mesh){
  if(object.morphTargetInfluences?.length)return false;
  for(const key in object.geometry.morphAttributes)if(object.geometry.morphAttributes[key].length)return false;
  if(Array.isArray(object.material)){for(const material of object.material)if(!materialSafe(material))return false;}else if(!materialSafe(object.material))return false;
 }
 return true;
}
function inspect(root:Object3D,wrapper:Object3D['updateMatrixWorld'],available:number):Snapshot[]|undefined{
 const queue=[root],result:Snapshot[]=[];
 for(let at=0;at<queue.length;at++){
  const object=queue[at];if(queue.length>available||queue.length>MAX_ROOT_NODES||!safe(object,root,wrapper))return undefined;
  const state=values(object);if(!state.every(Number.isFinite))return undefined;
  result.push({object,parent:object.parent,children:object.children.slice(),values:new Float64Array(state),auto:object.matrixAutoUpdate,worldAuto:object.matrixWorldAutoUpdate});
  if(queue.length+object.children.length>available||queue.length+object.children.length>MAX_ROOT_NODES)return undefined;queue.push(...object.children);
 }
 return result;
}
function unchanged(snapshot:Snapshot[],root:Object3D,wrapper:Object3D['updateMatrixWorld']):boolean{
 for(const item of snapshot){
  const object=item.object;if(!safe(object,root,wrapper)||object.parent!==item.parent||object.children.length!==item.children.length||object.matrixAutoUpdate!==item.auto||object.matrixWorldAutoUpdate!==item.worldAuto||object.matrixWorldNeedsUpdate)return false;
  for(let at=0;at<object.children.length;at++)if(object.children[at]!==item.children[at])return false;
  // Avoid allocating a 42-number vector on the hot path. These public scalar
  // reads also detect direct child/manual matrix mutations without setters.
  const {position:p,quaternion:q,scale:s}=object,v=item.values;
  if(p.x!==v[0]||p.y!==v[1]||p.z!==v[2]||q.x!==v[3]||q.y!==v[4]||q.z!==v[5]||q.w!==v[6]||s.x!==v[7]||s.y!==v[8]||s.z!==v[9])return false;
  let at=10;
  for(const value of object.matrix.elements)if(value!==item.values[at++])return false;
  for(const value of object.matrixWorld.elements)if(value!==item.values[at++])return false;
 }
 return true;
}
/** Exact unchanged-matrix memoization of bounded, exclusively owned static Model
 * subtrees. No auto-update flags, geometry, culling, visibility or quality change.
 * Any local/parent/hierarchy/manual matrix change runs Three's original traversal.
 * Unsupported dynamic graphs/foreign methods retire the optional optimization.
 */
export class StaticModelMatrices {
 private readonly owners=new Map<Object3D,()=>void>();
 private readonly counters:StaticMatrixStatistics={activeRoots:0,retainedNodes:0,skippedTraversals:0,updatedTraversals:0,refusedRoots:0,changedGraphs:0};
 private closed=false;
 constructor(private readonly signal:AbortSignal){signal.addEventListener('abort',this.dispose,{once:true});if(signal.aborted)this.dispose();}
 get statistics():StaticMatrixStatistics{return {...this.counters};}
 attach(root:Object3D,isCurrent:()=>boolean):boolean{
  this.release(root);if(this.closed||this.signal.aborted||!isCurrent()||this.owners.size>=MAX_ROOTS){this.counters.refusedRoots++;return false;}
  if(root.updateMatrixWorld!==Object3D.prototype.updateMatrixWorld){this.counters.refusedRoots++;return false;}
  const descriptor=Object.getOwnPropertyDescriptor(root,'updateMatrixWorld');if(descriptor&&!descriptor.configurable){this.counters.refusedRoots++;return false;}
  const owner=this,original=Object3D.prototype.updateMatrixWorld;let snapshot:Snapshot[]=[];let parent:Object3D|null=null,parentMatrix:number[]=[];let disposed=false;
  const retire=()=>{if(disposed)return;disposed=true;owner.counters.retainedNodes-=snapshot.length;snapshot=[];parentMatrix=[];owner.owners.delete(root);owner.counters.activeRoots=owner.owners.size;if(root.updateMatrixWorld===wrapper){if(descriptor)Object.defineProperty(root,'updateMatrixWorld',descriptor);else Reflect.deleteProperty(root,'updateMatrixWorld');}};
  function wrapper(this:Object3D,force?:boolean):void{
   if(disposed){original.call(this,force);return;}
   if(this!==root||owner.closed||owner.signal.aborted||!isCurrent()){retire();original.call(this,force);return;}
   const parentSame=root.parent===parent&&(!parent||parent.matrixWorld.elements.every((value,at)=>value===parentMatrix[at]));
   if(snapshot.length&&parentSame&&unchanged(snapshot,root,wrapper)){owner.counters.skippedTraversals++;return;}
   owner.counters.updatedTraversals++;original.call(root,force);
   const next=inspect(root,wrapper,MAX_NODES-owner.counters.retainedNodes+snapshot.length);
   if(!next){owner.counters.refusedRoots++;retire();return;}
   owner.counters.changedGraphs++;owner.counters.retainedNodes+=next.length-snapshot.length;snapshot=next;parent=root.parent;parentMatrix=parent?.matrixWorld.elements.slice()??[];
  }
  Object.defineProperty(root,'updateMatrixWorld',{value:wrapper,writable:true,configurable:true,enumerable:descriptor?.enumerable??false});
  this.owners.set(root,retire);this.counters.activeRoots=this.owners.size;
  // Initial publication must establish all derived matrices, including invisible
  // originals retained by static-model batching, before any traversal is skipped.
  wrapper.call(root,true);return !disposed;
 }
 release(root:Object3D):void{this.owners.get(root)?.();}
 dispose=():void=>{if(this.closed)return;this.closed=true;this.signal.removeEventListener('abort',this.dispose);for(const release of [...this.owners.values()])release();};
}
