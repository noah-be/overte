// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {BufferGeometry,Mesh,MeshStandardMaterial,Texture} from 'three';
import {RenderDispatchAttributionFrame} from '../../src/render-dispatch-attribution.ts';
if(typeof global.gc!=='function')throw Error('Explicit GC contract requires a dedicated test subprocess');
let retainedFrame;
function ownedSample(){const geometry=new BufferGeometry(),material=new MeshStandardMaterial(),owner=new Mesh(geometry,material),texture=new Texture(),program={};material.map=texture;const references=[owner,geometry,material,texture,texture.source,program].map(value=>new WeakRef(value));retainedFrame=new RenderDispatchAttributionFrame(()=>0);retainedFrame.observeDraw(geometry,material,owner);retainedFrame.observeProgram(program);retainedFrame.finish();return references;}
const references=ownedSample();let released=false;
for(let turn=0;turn<30;turn++){await new Promise(resolve=>setImmediate(resolve));global.gc();released=references.every(reference=>reference.deref()===undefined);if(released)break;}
if(!retainedFrame||retainedFrame.finish().drawsObserved!==1)throw Error('Finished owner was not retained for the GC proof');
process.stdout.write(JSON.stringify({released,observedReferences:references.length}));
