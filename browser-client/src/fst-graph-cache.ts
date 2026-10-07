// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {inspectFbxOriginalTextures} from './baked-fbx';
type Inspection=NonNullable<ReturnType<typeof inspectFbxOriginalTextures>>;
const ZERO=Symbol('No removable original FBX texture'),UNKNOWN=Symbol('Unknown original FBX graph');
type Entry=typeof ZERO|typeof UNKNOWN|WeakRef<Inspection>;
/** Per-World metadata only, keyed by exact immutable prepared buffer identity.
 * Empty/uncertain graphs retain no parsed tree. Positive trees are weak too:
 * prepared-byte cache retention must not retain64 whole metadata hierarchies.
 * One active caller borrows a tree; collection causes safe reinspection only. */
export class FstGraphCache{
 private entries=new WeakMap<ArrayBuffer,Entry>();private closed=false;
 private inspections=0;private hits=0;private zeroResults=0;private unknownResults=0;private positiveResults=0;private positiveReinspections=0;
 private readonly onAbort=()=>this.dispose();
 constructor(private readonly signal:AbortSignal){if(signal.aborted)this.closed=true;else signal.addEventListener('abort',this.onAbort,{once:true});}
 get stats(){return{inspections:this.inspections,hits:this.hits,zeroResults:this.zeroResults,unknownResults:this.unknownResults,positiveResults:this.positiveResults,positiveReinspections:this.positiveReinspections,disposed:this.closed};}
 inspect(buffer:ArrayBuffer):Inspection|undefined{
  this.signal.throwIfAborted();if(this.closed)throw new DOMException('FST graph inspection owner ended','AbortError');
  if(!(buffer instanceof ArrayBuffer)||!buffer.byteLength)throw Error('Detached or invalid prepared FBX buffer');
  const entry=this.entries.get(buffer);
  if(entry===ZERO||entry===UNKNOWN){this.hits++;return undefined;}
  if(entry){const cached=entry.deref();if(cached){this.hits++;return cached;}this.positiveReinspections++;}
  this.inspections++;
  let graph:Inspection|undefined;try{graph=inspectFbxOriginalTextures(buffer);}catch{graph=undefined;}
  this.signal.throwIfAborted();
  if(!graph){this.unknownResults++;this.entries.set(buffer,UNKNOWN);return undefined;}
  if(!graph.hasRemovableTextures(new Set(graph.materials.map(material=>material.id)))){this.zeroResults++;this.entries.set(buffer,ZERO);return undefined;}
  this.positiveResults++;this.entries.set(buffer,new WeakRef(graph));return graph;
 }
 dispose(){if(this.closed)return;this.closed=true;this.signal.removeEventListener('abort',this.onAbort);this.entries=new WeakMap();}
}
