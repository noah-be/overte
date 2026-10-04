// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import * as T from 'three';
import {RenderDispatchAttributionFrame,DISPATCH_ATTRIBUTION_LIMITS} from '../src/render-dispatch-attribution';
import {RenderCpuBreakdown} from '../src/render-cpu-breakdown';

function graph(){const geometry=new T.BufferGeometry(),material=new T.MeshStandardMaterial(),owner=new T.Mesh(geometry,material);return {geometry,material,owner};}
function source(name:string){return readFileSync(new URL(`../src/${name}.ts`,import.meta.url),'utf8');}
/** Single-expression counterfactuals execute the production classes with real Three constructors. */
function compile(name:string,text:string,bindings:Record<string,unknown>){const js=stripTypeScriptTypes(text.replace(/^import .*;\n/gm,'').replace(/export /g,''),{mode:'transform'} as unknown as Parameters<typeof stripTypeScriptTypes>[1]);return new Function(...Object.keys(bindings),`${js}\nreturn ${name};`)(...Object.values(bindings));}
test('actual color itemSize accessor is never invoked and cannot produce complete variant evidence; old omission does',()=>{
 const text=source('render-dispatch-attribution');assert.equal(text.split('colorItemSize===accessor||').length,2);
 const Old=compile('RenderDispatchAttributionFrame',text.replace('colorItemSize===accessor||',''),{BufferGeometry:T.BufferGeometry,Material:T.Material,Object3D:T.Object3D,TextureSource:T.TextureSource,Texture:T.Texture});
 for(const [Frame,expected]of [[RenderDispatchAttributionFrame,false],[Old,true]] as const){const a=graph(),attribute=new T.BufferAttribute(new Float32Array(4),4);let calls=0;Object.defineProperty(attribute,'itemSize',{get(){calls++;return 4;}});a.geometry.attributes.color=attribute;a.material.vertexColors=true;const frame=new Frame(()=>0);frame.observeDraw(a.geometry,a.material,a.owner);const result=frame.finish();assert.equal(calls,0);assert.equal(result.complete,expected);if(!expected)assert.equal(result.reason,'unsupported-input');}
});
function observe(Timing:typeof RenderCpuBreakdown,location:'gl'|'context'|'scene',inherited=false){let getterCalls=0,renders=0;const abort=new AbortController(),timing=new Timing(abort.signal,{dispatchAttribution:true,sampleEveryFrames:1,now:()=>0});const gl:any={},scene:any={updateMatrixWorld(){},onBeforeRender(){}},camera:any={updateMatrixWorld(){}},renderer:any={getContext(){return gl;},renderBufferDirect(){},info:{render:{calls:0,triangles:0}}};let target:any=location==='gl'?gl:location==='context'?renderer:scene,key=location==='gl'?'useProgram':location==='context'?'getContext':'onBeforeRender';
 if(inherited){const parent=Object.create(Object.getPrototypeOf(target));Object.setPrototypeOf(target,parent);delete target[key];target=parent;}
 Object.defineProperty(target,key,{configurable:true,get(){getterCalls++;return ()=>location==='context'?gl:undefined;}});const descriptor=Object.getOwnPropertyDescriptor(target,key);
 assert.equal(timing.measure(renderer,scene,camera,'emptyScene',()=>{renders++;return 'original';}),'original');assert.deepEqual(Object.getOwnPropertyDescriptor(target,key),descriptor);const report=timing.snapshot();timing.dispose();return {getterCalls,renders,report};
}
test('actual useProgram accessor refuses attribution before calling getter; exact old expression executes it',()=>{
 const text=source('render-cpu-breakdown');assert.equal(text.split('original=readDiagnosticMethod(gl,key)').length,2);const Old=compile('RenderCpuBreakdown',text.replace('original=readDiagnosticMethod(gl,key)','original=gl.useProgram'),{RenderDispatchAttributionFrame,DISPATCH_ATTRIBUTION_LIMITS});
 const good=observe(RenderCpuBreakdown,'gl'),bad=observe(Old,'gl');assert.equal(good.getterCalls,0);assert.equal(bad.getterCalls,1);assert.equal(good.renders,1);assert.equal(bad.renders,1);assert.equal(good.report.dispatchAttribution.populations.emptyScene.reasons['installation-refused'],1);assert.equal(good.report.completedFrames,1);
});
test('context and public-method own/inherited accessors refuse diagnostics with zero getter calls and preserve original callback',()=>{
 for(const location of ['gl','context','scene'] as const)for(const inherited of [false,true]){const result=observe(RenderCpuBreakdown,location,inherited);assert.equal(result.getterCalls,0);assert.equal(result.renders,1);assert.equal(result.report.dispatchAttribution.populations.emptyScene.reasons['installation-refused'],1);}
});
test('snapshot explicitly distinguishes public renderBufferDirect entries from confirmed GL draws',()=>{
 const timing=new RenderCpuBreakdown(new AbortController().signal,{dispatchAttribution:true});const report=timing.snapshot();assert.equal(report.dispatchAttribution.scope,'sampled-renderBufferDirect-call-entries');assert.equal(report.dispatchAttribution.entryEvidence,'call-entries-not-confirmed-GL-draws');timing.dispose();
});
