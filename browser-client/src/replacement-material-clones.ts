// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {BufferGeometry,Euler,Material,Mesh,MeshBasicMaterial,MeshStandardMaterial,Object3D,SkinnedMesh,Texture} from 'three';
import {cloneNativeMaterialForGeometry} from './native-render-state';
import {matchesNativeAlphaHooks} from './native-alpha-material';
import {matchesNativeZeroLightHooks} from './native-zero-lights';
import {ModelResources} from './model-resources';
const refused=Symbol('unsupported material descriptor');
const defaults={clone:Material.prototype.clone,compile:Material.prototype.onBeforeCompile,key:Material.prototype.customProgramCacheKey,render:Material.prototype.onBeforeRender,basicCopy:MeshBasicMaterial.prototype.copy,standardCopy:MeshStandardMaterial.prototype.copy,meshHooks:Object.fromEntries(['onBeforeRender','onAfterRender','onBeforeShadow','onAfterShadow'].map(name=>[name,(Object3D.prototype as unknown as Record<string,unknown>)[name]]))};
function data(object:object,key:PropertyKey):unknown{
 let at:object|null=object;for(let depth=0;at&&depth<6;depth++,at=Object.getPrototypeOf(at)){const entry=Object.getOwnPropertyDescriptor(at,key);if(entry)return 'value'in entry?entry.value:refused;}return at?refused:undefined;
}
function noAccessors(object:object):boolean{return Reflect.ownKeys(object).length<=128&&Reflect.ownKeys(object).every(key=>{const entry=Object.getOwnPropertyDescriptor(object,key)!;return 'value'in entry;});}
type Stamp=Map<PropertyKey,unknown>;
function snapshot(template:Material):Stamp|undefined{
 const prototype=Object.getPrototypeOf(template);
 if(prototype!==MeshBasicMaterial.prototype&&prototype!==MeshStandardMaterial.prototype||!noAccessors(template))return;
 if(data(template,'clone')!==defaults.clone||data(template,'copy')!==(prototype===MeshBasicMaterial.prototype?defaults.basicCopy:defaults.standardCopy)||data(template,'constructor')!==(prototype===MeshBasicMaterial.prototype?MeshBasicMaterial:MeshStandardMaterial))return;
 const compile=data(template,'onBeforeCompile'),key=data(template,'customProgramCacheKey');
 if(typeof compile!=='function'||typeof key!=='function'||!(compile===defaults.compile&&key===defaults.key
  ||matchesNativeAlphaHooks(template,compile as Material['onBeforeCompile'],key as Material['customProgramCacheKey'])
  ||matchesNativeZeroLightHooks(template,compile as Material['onBeforeCompile'],key as Material['customProgramCacheKey'])))return;
 if(data(template,'onBeforeRender')!==defaults.render)return;
 const result=new Map<PropertyKey,unknown>();
 for(const name of Reflect.ownKeys(template)){
  const value=data(template,name);if(value===refused)return;result.set(name,value);
  // Material.copy clones colors/vectors by value. Changes to those values must
  // invalidate reuse even if their object identity and material.version persist.
  if(value&&typeof value==='object'&&!(value instanceof Texture)&&name!=='userData'&&name!=='_listeners'){
   if(!noAccessors(value))return;
   const components=name==='envMapRotation'?['_x','_y','_z','_order']:['r','g','b','x','y','z','w'];
   if(name==='envMapRotation'&&Object.getPrototypeOf(value)!==Euler.prototype)return;
   for(const component of components){const v=data(value,component);if(v===refused)return;if(v!==undefined){if(component==='_order'){if(typeof v!=='string')return;}else if(typeof v!=='number'||!Number.isFinite(v))return;result.set(`${String(name)}:${component}`,v);}}
  }
 }
 // Three's Material.copy serializes userData. Refuse accessors/cycles/custom
 // objects here, rather than invoking arbitrary code in a new shared clone.
 const pending=[{value:data(template,'userData'),depth:0,path:[] as string[]}],seen=new Set<object>();let entries=0;
 while(pending.length){const {value,depth,path}=pending.pop()!;result.set(`userdata:${JSON.stringify(path)}`,value);
  if(value===undefined||value===null||typeof value==='boolean'||typeof value==='number'&&Number.isFinite(value)||typeof value==='string'&&value.length<=4096)continue;
  if(!value||typeof value!=='object'||depth>4||seen.has(value)||entries>256||!noAccessors(value)||Object.getPrototypeOf(value)!==Object.prototype&&!Array.isArray(value))return;
  seen.add(value);for(const name of Reflect.ownKeys(value)){if(name==='length'&&Array.isArray(value))continue;if(typeof name!=='string'||name.length>128)return;entries++;pending.push({value:data(value,name),depth:depth+1,path:[...path,name]});}
 }
 return result;
}
function equal(left:Stamp,right:Stamp):boolean{return left.size===right.size&&[...left].every(([key,value])=>right.has(key)&&Object.is(value,right.get(key)));}
/** Own no textures, geometry or live graph. One synchronous ordered replacement
 * application may reuse at most two exact native material clones. Resources are
 * captured before publication; its ModelResources owner remains authoritative.
 * A refused consumer stays on the original per-slot clone path. Never reuse this
 * scope across roots, templates, selector applications or asynchronous awaits. */
export class ReplacementMaterialClones{
 private template:Material|undefined;private initial:Stamp|undefined;private clones=new Map<boolean,Material>();private closed=false;
 private counts={created:0,reused:0,refused:0};
 constructor(template:Material,private resources:ModelResources|undefined,private signal?:AbortSignal,private assertCurrent:(()=>void)|undefined=()=>{}){this.template=template;this.initial=snapshot(template);}
 forMesh(mesh:Mesh):Material|undefined{
  this.signal?.throwIfAborted();this.assertCurrent?.();
  const template=this.template;if(this.closed||!template||!this.initial){this.counts.refused++;return;}
  const next=snapshot(template);if(!next||!equal(this.initial,next)){this.initial=undefined;this.counts.refused++;return;}
  if(Object.getPrototypeOf(mesh)!==Mesh.prototype&&Object.getPrototypeOf(mesh)!==SkinnedMesh.prototype){this.counts.refused++;return;}
  for(const hook of ['onBeforeRender','onAfterRender','onBeforeShadow','onAfterShadow'] as const)if(data(mesh,hook)!==defaults.meshHooks[hook]){this.counts.refused++;return;}
  const geometry=data(mesh,'geometry');if(!(geometry instanceof BufferGeometry)){this.counts.refused++;return;}
  const attributes=data(geometry,'attributes');if(!attributes||typeof attributes!=='object'){this.counts.refused++;return;}
  const color=data(attributes,'color');if(color===refused){this.counts.refused++;return;}const colored=!!color;
  const current=this.clones.get(colored);if(current){this.counts.reused++;return current;}
  const clone=cloneNativeMaterialForGeometry(template,geometry);this.resources!.captureMaterial(clone);
  this.signal?.throwIfAborted();this.assertCurrent?.();this.clones.set(colored,clone);this.counts.created++;return clone;
 }
 snapshot(){return {...this.counts};}
 close():void{this.closed=true;this.template=undefined;this.initial=undefined;this.clones.clear();this.resources=undefined;this.signal=undefined;this.assertCurrent=undefined;}
}
