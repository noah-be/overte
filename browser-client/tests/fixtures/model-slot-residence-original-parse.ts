// SPDX-License-Identifier: Apache-2.0
// Exact pre-proposal World parse helper; authored fields supply its original dependencies.
import * as THREE from 'three';
import {parseTexturedModel}from'../../src/model-textures';
import {ModelParseTurn,ModelParseCapacityError}from'../../src/model-parse-turn';
import {isOwnedUploadBitmap}from'../../src/world-bitmap-upload';
function disposeObject(root: THREE.Object3D): void {
  // One owned graph may share geometry, material slots, maps and bitmap data.
  // Do not transfer disposal authority across graphs or suppress listener errors.
  const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>(), bitmaps = new Set<ImageBitmap>();
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
    if (!geometries.has(object.geometry)) { geometries.add(object.geometry); object.geometry.dispose(); }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (materials.has(material)) continue;
      materials.add(material);
      for (const value of Object.values(material)) if (value instanceof THREE.Texture && !textures.has(value)) {
        textures.add(value);
        value.dispose();
        if (typeof ImageBitmap !== 'undefined' && value.image instanceof ImageBitmap && !isOwnedUploadBitmap(value.image) && !bitmaps.has(value.image)) { bitmaps.add(value.image); value.image.close(); }
      }
      material.dispose();
    }
  });
}

export class OriginalModelParseWorld {
 private options:any={modelParseTurn:false};private abort=new AbortController();private disposed=false;
 private modelParseTurn?:ModelParseTurn;private modelParseEpoch?:AbortController;private parseTurnCounts={capacityFallbacks:0};
 private recordLoadPhase(_name:string,_started:number){}
  private async parseTexturedModel(manager: THREE.LoadingManager, parse: () => THREE.Object3D, signal = this.abort.signal, weight=0): Promise<THREE.Object3D> {
    let texturesStarted: number|undefined;
    const enabled=this.options.modelParseTurn===true;
    const authority=enabled?this.options.captureAssetAuthority!():undefined;
    const assertCurrent=():void=>{signal.throwIfAborted();this.abort.signal.throwIfAborted();if(this.disposed)throw new DOMException('The parse owner ended','AbortError');authority?.assertCurrent();};
    if(enabled){
      assertCurrent();
      if(!this.modelParseTurn){this.modelParseEpoch=new AbortController();this.modelParseTurn=new ModelParseTurn(AbortSignal.any([this.abort.signal,this.modelParseEpoch.signal]));}
      signal=AbortSignal.any([signal,this.modelParseEpoch!.signal]);
    }
    const turn=enabled?this.modelParseTurn:undefined;
    const measuredParse=()=>{const model=parse();texturesStarted=performance.now();return model;};
    const schedule=turn?async(parser:()=>THREE.Object3D,queuedSignal:AbortSignal):Promise<THREE.Object3D>=>{
      const started=performance.now(),reader=AbortSignal.any([signal,queuedSignal]);
      const guardedParse=()=>{
        reader.throwIfAborted();assertCurrent();
        const model=parser();
        try{reader.throwIfAborted();assertCurrent();return model;}catch(error){disposeObject(model);throw error;}
      };
      const dispatched=()=>{this.recordLoadPhase('fbxParseQueueWait',started);return guardedParse();};
      try{return await turn.run(dispatched,{signal:reader,weight,discard:disposeObject});}
      catch(error){
        if(!(error instanceof ModelParseCapacityError))throw error;
        reader.throwIfAborted();assertCurrent();this.parseTurnCounts.capacityFallbacks++;
        return dispatched();
      }
    }:undefined;
    // Preserve the original synchronous path and deadline. Queue time is a
    // separate observation, not an image-dependency CPU duration.
    if(!turn)texturesStarted=performance.now();
    try{
      const model=await parseTexturedModel(manager,signal,measuredParse,disposeObject,schedule);
      try{if(turn)assertCurrent();return model;}catch(error){disposeObject(model);throw error;}
    }
    finally{if(texturesStarted!==undefined)this.recordLoadPhase('fbxTextures',texturesStarted);}
  }

}
