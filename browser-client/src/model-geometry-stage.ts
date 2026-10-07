// SPDX-License-Identifier: Apache-2.0
import {Box3,Group,Light,Object3D,Vector3} from 'three';
import type {Entity} from './world-data';
import {vector} from './world-data';
export interface NormalizedModelEntity {normalizer:Group;registrationOffset:Vector3}
/** The same real hierarchy, centering and dimensions used by completed native
 * Model entities. This does not synthesize collider geometry or render materials. */
export function normalizeModelEntity(model:Object3D,entity:Entity):NormalizedModelEntity {
  model.traverse(object=>{if(object instanceof Light)object.visible=false;});
  const bounds=new Box3().setFromObject(model),original=bounds.getSize(new Vector3());
  if(original.lengthSq()<1e-12||!original.toArray().every(Number.isFinite))throw Error('Model contains no finite geometry');
  const size=vector(entity.dimensions,1),normalizer=new Group();
  model.position.sub(bounds.getCenter(new Vector3()));normalizer.add(model);
  normalizer.scale.set(size.x/Math.max(original.x,1e-6),size.y/Math.max(original.y,1e-6),size.z/Math.max(original.z,1e-6));
  return{normalizer,registrationOffset:new Vector3(.5,.5,.5).sub(vector(entity.registrationPoint,.5)).multiply(size)};
}
/** A borrowed model is kept outside the scene while its loader owns pending
 * images/materials. Only collision geometry is published before final commit.
 * revoke never disposes model resources: loader or committed root owns those. */
export class ModelGeometryStage {
  private readonly anchor=new Group();private readonly detachedContent=new Group();
  private model?:Object3D;private normalized?:NormalizedModelEntity;private originalPosition?:Vector3;
  private committed=false;private revoked=false;
  constructor(private readonly options:{root:Group;entity:Entity;isCurrent:()=>boolean;publish:(geometryRoot:Object3D)=>void;withdraw:()=>void}){
    this.anchor.matrixAutoUpdate=false;this.anchor.add(this.detachedContent);
  }
  get state(){return{prepared:!!this.model,committed:this.committed,revoked:this.revoked};}
  prepare(model:Object3D):void {
    if(this.revoked||!this.options.isCurrent())throw new DOMException('The model geometry owner was removed','AbortError');
    if(this.model){if(this.model!==model)throw Error('Model geometry changed during one load');return;}
    if(model.parent)throw Error('Uncommitted model geometry already has an owner');
    this.originalPosition=model.position.clone();this.model=model;
    try{
      this.normalized=normalizeModelEntity(model,this.options.entity);
      this.detachedContent.position.copy(this.normalized.registrationOffset);this.detachedContent.add(this.normalized.normalizer);
      this.update();
    }catch(error){this.revoke();throw error;}
  }
  update():void {
    if(this.revoked||!this.model)return;
    if(!this.options.isCurrent()){this.revoke();return;}
    if(this.committed){this.options.publish(this.options.root);return;}
    this.options.root.updateWorldMatrix(true,false);this.anchor.matrix.copy(this.options.root.matrixWorld);this.anchor.matrixWorldNeedsUpdate=true;
    this.anchor.updateWorldMatrix(false,true);this.options.publish(this.anchor);
  }
  commit(content:Group):void {
    if(this.revoked||!this.options.isCurrent())throw new DOMException('The model geometry owner was removed','AbortError');
    if(!this.normalized)throw Error('Model geometry was not prepared');
    if(this.committed)throw Error('Model geometry was already committed');
    content.position.copy(this.normalized.registrationOffset);content.add(this.normalized.normalizer);this.committed=true;
    // The destination belongs to root. The helper retains no disposal authority.
    this.originalPosition=undefined;this.detachedContent.clear();
  }
  revoke():void {
    if(this.revoked)return;this.revoked=true;
    try{this.options.withdraw();}finally{
      if(!this.committed&&this.model){this.model.removeFromParent();if(this.originalPosition)this.model.position.copy(this.originalPosition);}
      this.detachedContent.clear();this.anchor.clear();this.model=undefined;this.normalized=undefined;this.originalPosition=undefined;
    }
  }
}
