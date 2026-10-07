// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,mock} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {readFileSync} from 'node:fs';
import {bindAttributionFixtureClock,RenderCpuBreakdown} from './render-cpu-breakdown-fixture';
import {DISPATCH_ATTRIBUTION_LIMITS} from '../src/render-dispatch-attribution';

function fixture(onCensus:()=>void=()=>{}){
 const abort=new AbortController(),geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial(),mesh=new THREE.Mesh(geometry,material),program={};
 const proxied=new Proxy(geometry,{getOwnPropertyDescriptor(target,key){if(key==='attributes')onCensus();return Reflect.getOwnPropertyDescriptor(target,key);}});
 const gl={useProgram(value:unknown){assert.equal(this,gl);assert.equal(value,program);return 'program-result';}};
 const scene:any={updateMatrixWorld(){},onBeforeRender(){}},camera:any={updateMatrixWorld(){}};
 let renders=0,draws=0;
 const renderer:any={getContext(){return gl;},info:{render:{calls:2,triangles:24}},renderBufferDirect(...args:unknown[]){assert.equal(this,renderer);assert.equal(args[2],proxied);assert.equal(gl.useProgram(program),'program-result');draws++;return 'draw-result';}};
 const world={abort,renderCpuTiming:new RenderCpuBreakdown(abort.signal,{dispatchAttribution:true})};
 const render=()=>{renders++;scene.updateMatrixWorld();camera.updateMatrixWorld();scene.onBeforeRender();for(let at=0;at<2;at++)assert.equal(renderer.renderBufferDirect(camera,scene,proxied,material,mesh),'draw-result');return 'render-result';};
 const run=(count=9)=>{for(let at=0;at<count;at++)assert.equal(world.renderCpuTiming.measure(renderer,scene,camera,'modelJobsIdle',render),'render-result');};
 return {world,scene,camera,renderer,gl,material,run,render,counts:()=>({renders,draws}),population:()=>world.renderCpuTiming.snapshot().dispatchAttribution.populations.modelJobsIdle,close:()=>{world.renderCpuTiming.dispose();abort.abort();geometry.dispose();material.dispose();}};
}

test('real default clock records a controlled host pause as partial evidence; fixture clock preserves the same render and complete census',()=>{
 let hostTime=0;const hostClock=mock.method(performance,'now',()=>hostTime);
 const old=fixture(()=>{hostTime+=3;}),current=fixture(()=>{hostTime+=3;});
 try{old.run();assert.equal(old.population().completeSamples,0);assert.equal(old.population().censoredSamples,2);assert.equal(old.population().reasons['cpu-limit'],2);
  const initial=current.world.renderCpuTiming;assert.equal(bindAttributionFixtureClock(current.world,true),'synthetic-fixture-not-host-CPU');assert.equal(initial.snapshot().status,'disposed');current.run();
  assert.equal(current.population().completeSamples,2);assert.equal(current.population().censoredSamples,0);assert.equal(current.population().completeTotals.drawsObserved,4);assert.equal(current.population().completeTotals.programCalls,4);assert.deepEqual(current.counts(),old.counts());assert.deepEqual(current.counts(),{renders:9,draws:18});
 }finally{old.close();current.close();hostClock.mock.restore();}
});

test('replacement retains exact owned abort signal, default first/ninth sampling, and original public descriptors',()=>{
 const f=fixture(),before=[Object.getOwnPropertyDescriptor(f.gl,'useProgram'),Object.getOwnPropertyDescriptor(f.renderer,'renderBufferDirect'),Object.getOwnPropertyDescriptor(f.scene,'updateMatrixWorld')];
 try{bindAttributionFixtureClock(f.world,true);f.run();assert.equal(f.world.renderCpuTiming.snapshot().sampleEveryFrames,8);assert.equal(f.population().samples,2);assert.deepEqual([Object.getOwnPropertyDescriptor(f.gl,'useProgram'),Object.getOwnPropertyDescriptor(f.renderer,'renderBufferDirect'),Object.getOwnPropertyDescriptor(f.scene,'updateMatrixWorld')],before);f.world.abort.abort();assert.equal(f.world.renderCpuTiming.snapshot().status,'disposed');const samples=f.population().samples;f.run(1);assert.equal(f.population().samples,samples);assert.equal(f.counts().renders,10);}finally{f.close();}
});

test('disabled attribution remains disabled and the finite synthetic clock refuses forever at its exact ceiling',()=>{
 const f=fixture();try{bindAttributionFixtureClock(f.world,false);assert.equal(f.world.renderCpuTiming.snapshot().dispatchAttribution.enabled,false);const now=(f.world.renderCpuTiming as any).now;let last=0;for(let at=0;at<65536;at++){const value=now();assert.equal(value-last,1/1024);last=value;}assert.equal(last,64);assert.throws(now,/capacity exceeded/);assert.throws(now,/capacity exceeded/);f.run(1);assert.equal(f.world.renderCpuTiming.snapshot().invalidFrames,1);assert.equal(f.counts().renders,1);}finally{f.close();}
});

test('active or foreign observer replacement is refused without disposal or lost rendering',()=>{
 const f=fixture(),initial=f.world.renderCpuTiming;try{assert.equal(initial.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',()=>{assert.throws(()=>bindAttributionFixtureClock(f.world,true),/Invalid owned/);assert.equal(f.world.renderCpuTiming,initial);return f.render();}),'render-result');assert.equal(initial.snapshot().status,'sampling');assert.throws(()=>bindAttributionFixtureClock({...f.world,renderCpuTiming:{} as any},true),/Invalid owned/);assert.throws(()=>bindAttributionFixtureClock(f.world,'true' as any),/Invalid owned/);}finally{f.close();}
});

test('abort and context loss still censor evidence and original driver exceptions still escape unchanged',()=>{
 for(const cause of ['abort','context','throw']){const f=fixture(),failure=Error('original-driver-failure'),original=f.gl.useProgram;try{bindAttributionFixtureClock(f.world,true);const render=()=>{f.render();if(cause==='abort')f.world.abort.abort();else if(cause==='context')f.world.renderCpuTiming.loseContext();else throw failure;};if(cause==='throw')assert.throws(()=>f.world.renderCpuTiming.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',render),value=>value===failure);else f.world.renderCpuTiming.measure(f.renderer,f.scene,f.camera,'modelJobsIdle',render);assert.equal(f.population().censoredSamples,1);assert.equal(f.population().completeSamples,0);assert.equal(f.gl.useProgram,original);}finally{f.close();}}
});

test('production census and clock limits are unchanged; synthetic binding does not admit unsupported material reads',()=>{
 const f=fixture();try{bindAttributionFixtureClock(f.world,true);assert.deepEqual(f.world.renderCpuTiming.snapshot().dispatchAttribution.limits,DISPATCH_ATTRIBUTION_LIMITS);assert.equal(DISPATCH_ATTRIBUTION_LIMITS.maximumCpuMsPerSample,2);assert.equal(DISPATCH_ATTRIBUTION_LIMITS.maximumAggregateCpuMs,500);assert.equal(DISPATCH_ATTRIBUTION_LIMITS.maximumSamples,512);let reads=0;Object.defineProperty(f.material,'map',{get(){reads++;throw Error('private material');}});f.run(1);assert.equal(reads,0);assert.equal(f.population().reasons['unsupported-input'],1);assert.equal(f.counts().renders,1);}finally{f.close();}
});

test('actual browser fixture keeps every original assertion and nine renders while labeling only the owned synthetic observer',()=>{
 const source=readFileSync(new URL('./render-dispatch-attribution.browser.spec.ts',import.meta.url),'utf8');assert.ok(source.includes('const clockScope=bindAttributionFixtureClock(world,enabled);'));assert.ok(source.indexOf('bindAttributionFixtureClock(world,enabled)')<source.indexOf('cancelAnimationFrame(world.frame)'));assert.ok(source.includes('cases.push({enabled,clockScope,pixelHash,'));assert.ok(source.includes('for(let at=0;at<9;at++)'));assert.ok(source.includes('expect(population.censoredSamples).toBe(0)'));assert.ok(!source.includes('performance.now='));
});
