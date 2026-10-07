// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import * as THREE from 'three';import {RenderCpuBreakdown} from '../src/render-cpu-breakdown';
function setup(every=1){let time=0;const controller=new AbortController(),clock=()=>time,timing=new RenderCpuBreakdown(controller.signal,{now:clock,sampleEveryFrames:every});const calls:string[]=[];
 const scene:any={updateMatrixWorld(force:boolean){assert.equal(this,scene);assert.equal(force,true);calls.push('scene');time+=2;},onBeforeRender(...args:unknown[]){assert.equal(this,scene);assert.equal(args[0],renderer);calls.push('hook');time+=.5;}},camera:any={updateMatrixWorld(){assert.equal(this,camera);calls.push('camera');time+=1;}},renderer:any={info:{render:{calls:2,triangles:42}},renderBufferDirect(...args:unknown[]){assert.equal(this,renderer);assert.deepEqual(args,['authored']);calls.push('draw');time+=3;return 'draw-value';}};
 const render=()=>{scene.updateMatrixWorld(true);camera.updateMatrixWorld();scene.onBeforeRender(renderer);time+=4;assert.equal(renderer.renderBufferDirect('authored'),'draw-value');renderer.renderBufferDirect('authored');time+=2;return 'actual-value';};return {timing,controller,scene,camera,renderer,render,calls,advance:(ms:number)=>time+=ms};}
const sample=(timing:RenderCpuBreakdown)=>(timing.snapshot().populations as any).modelJobsIdle;
test('real public call boundaries preserve arguments/this/return and partition exclusive CPU spans',()=>{
 const f=setup(),descriptors=[Object.getOwnPropertyDescriptor(f.scene,'updateMatrixWorld'),Object.getOwnPropertyDescriptor(f.camera,'updateMatrixWorld'),Object.getOwnPropertyDescriptor(f.scene,'onBeforeRender'),Object.getOwnPropertyDescriptor(f.renderer,'renderBufferDirect')];
 assert.equal(f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',f.render),'actual-value');assert.deepEqual(f.calls,['scene','camera','hook','draw','draw']);const p=sample(f.timing);
 assert.equal(p.phases.total.meanMs,15.5);assert.equal(p.phases.sceneMatrices.meanMs,2);assert.equal(p.phases.cameraMatrices.meanMs,1);assert.equal(p.phases.sceneBeforeHook.meanMs,.5);assert.equal(p.phases.drawDispatch.meanMs,6);assert.equal(p.phases.renderRemainder.meanMs,6);assert.equal(p.afterSceneHookToFirstDispatch.meanMs,4);assert.equal(p.drawDispatchCalls.totalCalls,2);
 assert.deepEqual([Object.getOwnPropertyDescriptor(f.scene,'updateMatrixWorld'),Object.getOwnPropertyDescriptor(f.camera,'updateMatrixWorld'),Object.getOwnPropertyDescriptor(f.scene,'onBeforeRender'),Object.getOwnPropertyDescriptor(f.renderer,'renderBufferDirect')],descriptors);f.timing.dispose();
});
test('a camera nested in scene traversal is measured exclusively, not counted twice',()=>{
 const f=setup();f.scene.updateMatrixWorld=function(){f.advance(2);f.camera.updateMatrixWorld();};f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{f.scene.updateMatrixWorld();f.renderer.renderBufferDirect('authored');});const p=sample(f.timing);assert.equal(p.phases.sceneMatrices.meanMs,2);assert.equal(p.phases.cameraMatrices.meanMs,1);assert.equal(p.phases.drawDispatch.meanMs,3);assert.equal(p.phases.total.meanMs,6);assert.equal(p.phases.renderRemainder.meanMs,0);f.timing.dispose();
});
test('original renderer errors propagate unchanged and restore every installed hook',()=>{
 const f=setup(),original=f.renderer.renderBufferDirect,failure=Error('driver submission failed');assert.throws(()=>f.timing.measure(f.renderer,f.scene,f.camera,'loading',()=>{f.scene.updateMatrixWorld(true);throw failure;}),error=>error===failure);assert.equal(f.renderer.renderBufferDirect,original);assert.equal(Object.hasOwn(f.camera,'updateMatrixWorld'),true);assert.equal(f.timing.snapshot().failedRenders,1);assert.equal(f.timing.snapshot().completedFrames,0);assert.equal(f.timing.snapshot().active,false);f.timing.dispose();
});
test('foreign hook replacement during a render remains intact and refuses the incomplete timing sample',()=>{
 const f=setup(),foreign=()=>{};f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{f.renderer.renderBufferDirect('authored');f.renderer.renderBufferDirect=foreign;});assert.equal(f.renderer.renderBufferDirect,foreign);assert.equal(f.timing.snapshot().foreignHookChanges,1);assert.equal(f.timing.snapshot().invalidFrames,1);assert.equal(sample(f.timing).samples,0);f.timing.dispose();
});
test('nonwritable boundary falls back before rendering and restores earlier hooks without dropping a draw',()=>{
 const f=setup(),original=f.scene.updateMatrixWorld;Object.defineProperty(f.renderer,'renderBufferDirect',{writable:false});let invoked=0;assert.equal(f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{invoked++;assert.equal(f.scene.updateMatrixWorld,original);return f.render();}),'actual-value');assert.equal(invoked,1);assert.equal(f.timing.snapshot().installationRefusals,1);assert.equal(f.timing.snapshot().completedFrames,0);f.timing.dispose();
});
test('an already-aborted owner performs no diagnostic clock or method installation',()=>{
 const signal=AbortSignal.abort();let clocks=0,renders=0;const observer=new RenderCpuBreakdown(signal,{now:()=>{clocks++;return 0;}});assert.equal(observer.measure({} as any,{} as any,{} as any,'loading',()=>++renders),1);assert.equal(clocks,0);assert.equal(observer.snapshot().status,'disposed');
});
for(const kind of ['abort','context-loss'])test(`${kind} during synchronous submission invalidates the sample and restores methods`,()=>{
 const f=setup(),original=f.renderer.renderBufferDirect;f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{f.renderer.renderBufferDirect('authored');if(kind==='abort')f.controller.abort();else f.timing.loseContext();});assert.equal(f.renderer.renderBufferDirect,original);assert.equal(f.timing.snapshot().completedFrames,0);assert.equal(f.timing.snapshot().invalidFrames,1);f.timing.dispose();
});
test('only scheduled frames install wrappers; all unsampled renders retain the original boundary identity',()=>{
 const f=setup(8),original=f.renderer.renderBufferDirect;for(let at=0;at<9;at++)f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{if(at%8!==0)assert.equal(f.renderer.renderBufferDirect,original);return f.render();});assert.equal(f.timing.snapshot().completedFrames,2);assert.equal(f.calls.filter(value=>value==='draw').length,18);f.timing.dispose();
});
test('boundary-call capacity refuses partial evidence while preserving all actual dispatches',()=>{
 const f=setup();let draws=0;f.renderer.renderBufferDirect=()=>{draws++;};f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{for(let at=0;at<4097;at++)f.renderer.renderBufferDirect();});assert.equal(draws,4097);assert.equal(f.timing.snapshot().completedFrames,0);assert.equal(f.timing.snapshot().invalidFrames,1);f.timing.dispose();
});
test('bad diagnostic clocks cannot replace renderer behavior or fabricate negative CPU times',()=>{
 let clocks=0;const f=setup(),observer=new RenderCpuBreakdown(f.controller.signal,{sampleEveryFrames:1,now:()=>{if(++clocks===2)throw Error('clock failed');return clocks;}});assert.equal(observer.measure(f.renderer,f.scene,f.camera,'loading',f.render),'actual-value');assert.equal(observer.snapshot().invalidFrames,1);assert.equal(observer.snapshot().completedFrames,0);observer.dispose();f.timing.dispose();
});
test('inherited scene methods are restored by deleting the temporary own property',()=>{
 const f=setup(),proto={updateMatrixWorld:f.scene.updateMatrixWorld};delete f.scene.updateMatrixWorld;Object.setPrototypeOf(f.scene,proto);f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',f.render);assert.equal(Object.hasOwn(f.scene,'updateMatrixWorld'),false);assert.equal(f.scene.updateMatrixWorld,proto.updateMatrixWorld);f.timing.dispose();
});
test('actual Three graph matrices and parented camera retain exactly their ordinary transforms',()=>{
 const scene=new THREE.Scene(),parent=new THREE.Group(),child=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshBasicMaterial()),camera=new THREE.PerspectiveCamera();scene.add(parent);parent.add(child,camera);parent.position.set(2,3,4);child.rotation.set(.2,.4,.6);camera.position.set(1,2,3);scene.updateMatrixWorld(true);const childBefore=child.matrixWorld.clone(),cameraBefore=camera.matrixWorld.clone();const renderer:any={info:{render:{calls:0,triangles:0}},renderBufferDirect(){}};const controller=new AbortController(),observer=new RenderCpuBreakdown(controller.signal,{sampleEveryFrames:1});observer.measure(renderer,scene,camera,'modelJobsIdle',()=>scene.updateMatrixWorld(true));assert.deepEqual(child.matrixWorld.elements,childBefore.elements);assert.deepEqual(camera.matrixWorld.elements,cameraBefore.elements);assert.equal(scene.matrixWorldAutoUpdate,true);assert.equal(child.matrixAutoUpdate,true);assert.equal(observer.snapshot().completedFrames,1);observer.dispose();child.geometry.dispose();child.material.dispose();
});
test('returned aggregate snapshots cannot mutate retained counters or reveal graph identities',()=>{
 const f=setup();f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',f.render);const snapshot=f.timing.snapshot() as any;snapshot.populations.modelJobsIdle.phases.total.histogram.fill(999);assert.equal(sample(f.timing).phases.total.histogram.includes(999),false);const serialized=JSON.stringify(f.timing.snapshot());assert.equal(serialized.includes('authored'),false);assert.equal(serialized.includes('uuid'),false);f.timing.dispose();
});

test('reentrant diagnostic entry never double-installs renderer hooks or drops the nested actual render',()=>{
 const f=setup();let inner=0;f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{f.timing.measure(f.renderer,f.scene,f.camera,'loading',()=>{inner++;f.renderer.renderBufferDirect('authored');});});assert.equal(inner,1);assert.equal(f.timing.snapshot().reentrantFrames,1);assert.equal(sample(f.timing).drawDispatchCalls.totalCalls,1);f.timing.dispose();
});
test('an empty scene has no invented project/list-to-draw interval',()=>{
 const f=setup();f.timing.measure(f.renderer,f.scene,f.camera,'emptyScene',()=>{f.scene.updateMatrixWorld(true);f.camera.updateMatrixWorld();f.scene.onBeforeRender(f.renderer);});const p=(f.timing.snapshot().populations as any).emptyScene;assert.equal(p.firstDispatchObserved,0);assert.equal(p.afterSceneHookToFirstDispatch.count,0);assert.equal(p.phases.total.meanMs,3.5);f.timing.dispose();
});
test('a pathological long synchronous render is not truncated or represented as a valid bounded sample',()=>{
 const f=setup();let actual=0;f.timing.measure(f.renderer,f.scene,f.camera,'loading',()=>{actual++;f.advance(5001);});assert.equal(actual,1);assert.equal(f.timing.snapshot().invalidFrames,1);assert.equal(f.timing.snapshot().completedFrames,0);f.timing.dispose();
});
test('fixed sample/frame capacity cannot retain an unbounded observation stream',()=>{
 const f=setup();for(let at=0;at<2050;at++)f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{});assert.equal(f.timing.snapshot().completedFrames,2048);assert.equal(f.timing.snapshot().capacitySkippedFrames,2);f.timing.dispose();
});

test('a foreign descriptor lock refuses timing proof without replacing the original render result or throwing from diagnostic restoration',()=>{
 const f=setup();let drawCalls=0;f.renderer.renderBufferDirect=()=>{drawCalls++;return 'original';};
 assert.equal(f.timing.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{Object.defineProperty(f.renderer,'renderBufferDirect',{configurable:false,writable:false});return 'rendered';}),'rendered');
 assert.equal(f.timing.snapshot().foreignHookChanges,1);assert.equal(f.timing.snapshot().completedFrames,0);assert.equal(f.timing.snapshot().active,false);assert.equal(f.renderer.renderBufferDirect(),'original');assert.equal(drawCalls,1);f.timing.dispose();
});
