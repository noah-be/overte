// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type {Object3D} from 'three';
interface Entry {abort:AbortController;detach():void}
const cancelled=()=>new DOMException('The graphics preparation owner was cancelled','AbortError');
/** Private per-root lifetimes; imported asset userData cannot grant ownership. */
export class GraphicsWarmupOwner {
  private entries=new WeakMap<Object3D,Entry>();
  constructor(private world:AbortSignal){}
  async run<T>(root:Object3D,isCurrent:()=>boolean,prepare:(signal:AbortSignal,current:()=>boolean)=>Promise<T>):Promise<T>{
    this.cancel(root);
    if(this.world.aborted||!isCurrent())throw cancelled();
    const abort=new AbortController(),onWorld=()=>abort.abort();
    this.world.addEventListener('abort',onWorld,{once:true});
    const entry={abort,detach:()=>this.world.removeEventListener('abort',onWorld)};
    this.entries.set(root,entry);
    const current=()=>!abort.signal.aborted&&!this.world.aborted&&this.entries.get(root)===entry&&isCurrent();
    try {
      if(!current())throw cancelled();
      const value=await prepare(abort.signal,current);
      if(!current())throw cancelled();
      return value;
    } finally {
      entry.detach();
      if(this.entries.get(root)===entry)this.entries.delete(root);
      abort.abort();
    }
  }
  /** Called before reparenting/disposal, including owned child rig preparations. */
  cancel(root:Object3D):void {
    root.traverse(object=>{const entry=this.entries.get(object);if(!entry)return;this.entries.delete(object);entry.detach();entry.abort.abort();});
  }
}
