// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as T from 'three';
import type {Entity} from './world-data';
import type {DrawCensusOwner} from './world-draw-census';
const LIMIT=64,OWNER_LIMIT=1024,ENTITY_LIMIT=16384;
const fields=['id','type','position','rotation','localPosition','localRotation','parentID','dimensions','registrationPoint','visible','collisionless','shapeType','shape','color','alpha','unlit','emissive','modelURL','textures','materialURL','materialData','parentMaterialName','userData','dynamic','velocity','angularVelocity','script','serverScripts','animation'] as const;
class Refused extends Error {constructor(){super('Model cohort source refused');}}
function data(value:unknown,key:string):unknown {
 if(!value||typeof value!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw new Refused();
 const descriptor=Object.getOwnPropertyDescriptor(value,key);if(!descriptor)return undefined;
 if(!('value'in descriptor))throw new Refused();return descriptor.value;
}
function scalar(value:unknown):number {if(typeof value!=='number'||!Number.isFinite(value))throw new Refused();return value;}
function own(value:object,key:string):unknown {const d=Object.getOwnPropertyDescriptor(value,key);if(!d||!('value'in d))throw new Refused();return d.value;}
function transform(root:T.Object3D):number[] {
 const vector=(key:string)=>{const value=own(root,key) as object;if(Object.getPrototypeOf(value)!==T.Vector3.prototype)throw new Refused();return ['x','y','z'].map(axis=>scalar(own(value,axis)));};
 const q=own(root,'quaternion') as object;if(Object.getPrototypeOf(q)!==T.Quaternion.prototype)throw new Refused();
 const matrix=(key:string)=>{const m=own(root,key) as object;if(Object.getPrototypeOf(m)!==T.Matrix4.prototype)throw new Refused();const values=own(m,'elements');if(!Array.isArray(values)||Object.getPrototypeOf(values)!==Array.prototype||own(values,'length')!==16)throw new Refused();return Array.from({length:16},(_,i)=>scalar(own(values,String(i))));};
 return [...vector('position'),...['_x','_y','_z','_w'].map(key=>scalar(own(q,key))),...vector('scale'),...matrix('matrix'),...matrix('matrixWorld')];
}
function semantics(entity:Entity):string {
 let nodes=0,bytes=0;
 const charge=(n:number)=>{bytes+=n;if(bytes>65536)throw new Refused();};
 const encode=(value:unknown,depth:number):unknown=>{
  if(++nodes>512||depth>6)throw new Refused();charge(16);
  if(value===undefined)return ['undefined'];if(value===null)return ['null'];
  if(typeof value==='number'){if(!Number.isFinite(value))throw new Refused();return ['number',Object.is(value,-0)?'-0':value];}
  if(typeof value==='boolean')return ['boolean',value];if(typeof value==='string'){charge(value.length*2);return ['string',value];}
  if(Array.isArray(value)){
   if(Object.getPrototypeOf(value)!==Array.prototype)throw new Refused();const length=own(value,'length');
   if(!Number.isSafeInteger(length)||(length as number)<0||(length as number)>128)throw new Refused();
   return ['array',Array.from({length:length as number},(_,i)=>encode(own(value,String(i)),depth+1))];
  }
  if(value&&typeof value==='object'&&[Object.prototype,null].includes(Object.getPrototypeOf(value))){
   const keys=Reflect.ownKeys(value);if(keys.length>64||keys.some(key=>typeof key!=='string'))throw new Refused();
   return ['object',(keys as string[]).sort().map(key=>{charge(key.length*2);return [key,encode(own(value,key),depth+1)];})];
  }
  throw new Refused();
 };
 return JSON.stringify(fields.map(key=>[key,encode(data(entity,key),0)]));
}
function nonzero(value:unknown):boolean {return value!==undefined&&value!==null&&['x','y','z'].some(key=>{const n=data(value,key);return typeof n!=='number'||!Number.isFinite(n)||n!==0;});}
function eligible(entity:Entity|undefined,materialChild:boolean):boolean {
 if(!entity||data(entity,'type')!=='Model'||materialChild)return false;
 const parent=data(entity,'parentID'),animation=data(entity,'animation');
 return data(entity,'dynamic')!==true&&!nonzero(data(entity,'velocity'))&&!nonzero(data(entity,'angularVelocity'))&&
 !data(entity,'script')&&!data(entity,'serverScripts')&&(!parent||typeof parent==='string'&&/^\{?00000000-0000-0000-0000-000000000000\}?$/.test(parent))&&
 !(animation&&typeof animation==='object'&&(data(animation,'url')||data(animation,'running')===true));
}
function flags(root:T.Object3D):[boolean,boolean,boolean,unknown] {
 if(Object.getPrototypeOf(root)!==T.Group.prototype)throw new Refused();const user=own(root,'userData');
 const revision=data(user,'shaderRevision');if(revision!==undefined&&(!Number.isSafeInteger(revision)||(revision as number)<0))throw new Refused();
 return [data(user,'modelLoaded')===true,data(user,'shadersReady')===true,data(user,'modelFailed')===true,revision];
}
export interface LoadedModelCohortSource {
 objects:ReadonlyMap<string,T.Object3D>;entities:ReadonlyMap<string,Entity>;signatures:ReadonlyMap<string,string>;scene:T.Scene;
}
interface Selected {id:string;root:T.Object3D;signature:string|undefined;semantic:string;status:ReturnType<typeof flags>;pose:number[];parent:T.Object3D|null}
/** A request-local captured static loaded Model prefix, never world coverage or
 * instance admission. No model getters/matrix updates/resource mutations. */
export class LoadedModelCohort {
 private selected:Selected[]=[];private scene:T.Scene|undefined;private sceneParent:T.Object3D|null=null;private scenePose:number[]=[];
 private metadata=512;private eligibleCount=0;private modelCount=0;private closed=false;
 constructor(private source:LoadedModelCohortSource|undefined,maximumMetadataBytes=2*1024*1024){
  try {
   if(!source||source.objects.size>OWNER_LIMIT||source.entities.size>ENTITY_LIMIT)throw new Refused();
   this.metadata+=source.objects.size*32+source.entities.size*24;
   if(this.metadata>maximumMetadataBytes)throw new Refused();
   if(Object.getPrototypeOf(source.scene)!==T.Scene.prototype)throw new Refused();
   this.scene=source.scene;this.sceneParent=own(source.scene,'parent') as T.Object3D|null;this.scenePose=transform(source.scene);
   const selection=this.prefix();this.eligibleCount=selection.eligible;this.modelCount=selection.models;
   for(const [id,root]of selection.roots){
    const entity=source.entities.get(id)!;const semantic=semantics(entity),signature=source.signatures.get(id);
    if(id.length>256||signature!==undefined&&(typeof signature!=='string'||signature.length>65536))throw new Refused();
    this.metadata+=semantic.length*2+id.length*2+(signature?.length??0)*2+512;
    if(this.metadata>maximumMetadataBytes)throw new Refused();
    this.selected.push({id,root,signature,semantic,status:flags(root),pose:transform(root),parent:own(root,'parent') as T.Object3D|null});
   }
  }catch{this.release();throw new Refused();}
 }
 private prefix(){
  const source=this.source;if(!source||source.objects.size>OWNER_LIMIT||source.entities.size>ENTITY_LIMIT)throw new Refused();
  const materialParents=new Set<unknown>();
  for(const entity of source.entities.values())if(data(entity,'type')==='Material')materialParents.add(data(entity,'parentID'));
  const roots:Array<[string,T.Object3D]>=[];let eligibleCount=0,models=0;
  for(const [id,root]of source.objects){
   const entity=source.entities.get(id);if(!entity||data(entity,'type')!=='Model')continue;models++;
   const [loaded,ready,failed]=flags(root);if(!loaded||!ready||failed||!eligible(entity,materialParents.has(id)))continue;
   eligibleCount++;if(roots.length<LIMIT)roots.push([id,root]);
  }
  return{roots,eligible:eligibleCount,models};
 }
 get metadataBytes(){return this.metadata;}
 get reportScope(){return{scope:'captured-static-loaded-Model-cohort' as const,maximumSelectedOwners:LIMIT,
  selectedOwners:this.selected.length,eligibleAtCapture:this.eligibleCount,modelOwnersAtCapture:this.modelCount,
  selectionPartial:this.eligibleCount>this.selected.length,wholeWorldCoverage:false as const};}
 owners():DrawCensusOwner[]{return this.selected.map(({root})=>({root,loaded:true,dynamic:false,scripted:false,parented:false,materialChildren:false,animated:false}));}
 current():boolean {
  if(this.closed||!this.source||!this.scene)return false;
  try {
   if(this.source.scene!==this.scene||own(this.scene,'parent')!==this.sceneParent||!transform(this.scene).every((v,i)=>Object.is(v,this.scenePose[i])))return false;
   const prefix=this.prefix().roots;if(prefix.length!==this.selected.length||prefix.some(([id,root],i)=>id!==this.selected[i].id||root!==this.selected[i].root))return false;
   return this.selected.every(snapshot=>{
    const {id,root}=snapshot,entity=this.source!.entities.get(id);
    return !!entity&&this.source!.objects.get(id)===root&&this.source!.signatures.get(id)===snapshot.signature&&
     flags(root).every((value,i)=>Object.is(value,snapshot.status[i]))&&own(root,'parent')===snapshot.parent&&
     semantics(entity)===snapshot.semantic&&transform(root).every((v,i)=>Object.is(v,snapshot.pose[i]));
   });
  }catch{return false;}
 }
 release():void{if(this.closed)return;this.closed=true;this.selected.length=0;this.scenePose.length=0;this.scene=undefined;this.sceneParent=null;this.source=undefined;}
}
