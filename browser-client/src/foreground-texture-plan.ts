// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {Camera,Frustum,Line,Material,Matrix4,Mesh,Object3D,Points,Texture,WebGLCoordinateSystem} from 'three';
export class ForegroundTextureCapacityError extends Error {}
interface Binding {object:Mesh|Line|Points;slot:number|null;field:string}
/** Borrow only Texture references and object/slot/field descriptors. Materials
 * are resolved afresh at every boundary; replacing a map cannot warm old data.
 * This is optional main-view preparation, never renderer visibility authority. */
export class ForegroundTexturePlan {
 private readonly bindings=new Map<Texture,Binding[]>();
 private readonly frustum=new Frustum();private readonly projection=new Matrix4();
 private closed=false;private objects=0;private references=0;private unsupported=0;
 constructor(private readonly root:Object3D,private readonly scene:Object3D,private readonly camera:Camera,private readonly willPublish:()=>boolean,maximumBindings=65536){
  if(!Number.isSafeInteger(maximumBindings)||maximumBindings<0||maximumBindings>65536)throw Error('Invalid foreground preparation binding bound');
  const visit=(object:Object3D,uncertain:boolean)=>{
   if(++this.objects>100000)throw new ForegroundTextureCapacityError('Foreground preparation exceeds its object bound');
   const special=object as Object3D&{isLOD?:boolean;isSkinnedMesh?:boolean;isInstancedMesh?:boolean;isBatchedMesh?:boolean};
   uncertain ||= special.isLOD===true;
   if(object instanceof Mesh||object instanceof Line||object instanceof Points){
    // Dynamic/instanced/LOD bounds can change during renderer traversal. Leave
    // their first texture use on the unchanged normal renderer path.
    if(uncertain||special.isSkinnedMesh||special.isInstancedMesh||special.isBatchedMesh||!this.ordinaryFrustumMethod(object)){this.unsupported++;}
    else{
     const materials=Array.isArray(object.material)?object.material:[object.material];
     const slots:Set<number|null>=Array.isArray(object.material)?new Set<number>(object.geometry.groups.map((group:{materialIndex?:number})=>group.materialIndex).filter((index:number|undefined):index is number=>Number.isInteger(index)&&index!==undefined&&index>=0)):new Set<number|null>([null]);
     for(const slot of slots){
      const material=slot===null?materials[0]:materials[slot??-1];if(!(material instanceof Material))continue;
      for(const [field,value]of Object.entries(material))if(value instanceof Texture){
       if(++this.references>maximumBindings)throw new ForegroundTextureCapacityError('Foreground preparation exceeds its binding bound');
       let owners=this.bindings.get(value);if(!owners){if(this.bindings.size>=4096)throw new ForegroundTextureCapacityError('Foreground preparation exceeds its map bound');this.bindings.set(value,owners=[]);}
       owners.push({object,slot:slot??null,field});
      }
     }
    }
   }
   return uncertain;
  };
  // Iterator frames avoid a JS stack overflow for deeply nested valid models.
  const stack:{object:Object3D;index:number;uncertain:boolean}[]=[{object:root,index:0,uncertain:visit(root,false)}];
  while(stack.length){const frame=stack[stack.length-1];if(frame.index>=frame.object.children.length){stack.pop();continue;}
   const child=frame.object.children[frame.index++];stack.push({object:child,index:0,uncertain:visit(child,frame.uncertain)});
  }
 }
 get stats(){return{objects:this.objects,textures:this.bindings.size,bindings:this.references,unsupported:this.unsupported,disposed:this.closed};}
 private ordinaryFrustumMethod(object:Mesh|Line|Points):boolean{
  const value=object as typeof object&{intersectsFrustum?:(frustum:Frustum)=>boolean};
  const prototype=object instanceof Mesh?Mesh.prototype:object instanceof Line?Line.prototype:Points.prototype;
  return object.onBeforeRender===Object3D.prototype.onBeforeRender&&value.intersectsFrustum===(prototype as typeof value).intersectsFrustum&&typeof value.intersectsFrustum==='function';
 }
 private ancestry(object:Object3D):boolean{
  let foundRoot=false;
  let depth=0;for(let current:Object3D|null=object;current;current=current.parent){
   if(++depth>100000)return false;
   if(current===this.root)foundRoot=true;
   // Only the owned publishing root can be temporarily hidden by preparation.
   if(current!==this.root&&!current.visible)return false;
   if((current as Object3D&{isLOD?:boolean}).isLOD)return false;
   if(current===this.scene)return foundRoot;
  }
  return false;
 }
 isEligible(texture:Texture):boolean{
  if(this.closed||!this.willPublish())return false;
  const owners=this.bindings.get(texture);if(!owners)return false;
  // Match WebGLRenderer's actual WebGL coordinate convention/reversed depth.
  this.camera.updateWorldMatrix(true,false);
  this.projection.multiplyMatrices(this.camera.projectionMatrix,this.camera.matrixWorldInverse);
  this.frustum.setFromProjectionMatrix(this.projection,WebGLCoordinateSystem,(this.camera as Camera&{reversedDepth?:boolean}).reversedDepth===true);
  for(const {object,slot,field}of owners){
   if(!this.ancestry(object)||!object.layers.test(this.camera.layers)||!this.ordinaryFrustumMethod(object))continue;
   const materials=object.material;
   if(slot===null?Array.isArray(materials):!Array.isArray(materials)||!object.geometry.groups.some(group=>group.materialIndex===slot))continue;
   const material=Array.isArray(materials)?materials[slot!]:materials;
   if(!(material instanceof Material)||!material.visible||(material as Material&Record<string,unknown>)[field]!==texture)continue;
   object.updateWorldMatrix(true,false);
   if(!object.frustumCulled||(object as typeof object&{intersectsFrustum(frustum:Frustum):boolean}).intersectsFrustum(this.frustum))return true;
  }
  return false;
 }
 dispose():void{if(this.closed)return;this.closed=true;this.bindings.clear();this.references=0;}
}
