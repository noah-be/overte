// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import * as THREE from 'three';import {observeNativeImageDfg} from './native-image-dfg-observer';
// Test the installed primary-source singleton; it must never be disposed here.
// @ts-expect-error Internal Three primary-source module has no public declarations.
import {getDFGLUT} from 'three/src/renderers/shaders/DFGLUTData.js';
test('the actual installed Three DFG singleton exposes exact half-float metadata and sampler defaults without mutations',()=>{
 const lut=getDFGLUT(),beforeVersion=lut.version,observer=observeNativeImageDfg(lut);
 assert.equal(observer.uniformMatches(getDFGLUT()),true);assert.equal(observer.uniformMatches(new THREE.DataTexture()),false);
 const result=observer.report();assert.equal(result.disposeEvents,0);assert.equal(result.sourceUnchanged,true);assert.equal(result.dataUnchanged,true);assert.equal(result.versionsUnchanged,true);assert.equal(result.samplerUnchanged,true);
 assert.deepEqual(result.metadata,{width:16,height:16,dataLength:512,dataBytes:1024,format:THREE.RGFormat,type:THREE.HalfFloatType});assert.deepEqual(result.samplerBefore,result.samplerAfter);observer.close();assert.equal(lut.version,beforeVersion);
});
test('a changed sampler or Source/data identity cannot pass borrowed lookup invariance',()=>{
 const data=new Uint16Array(512),lut=new THREE.DataTexture(data,16,16,THREE.RGFormat,THREE.HalfFloatType);lut.name='DFG_LUT';lut.minFilter=lut.magFilter=THREE.LinearFilter;
 const observer=observeNativeImageDfg(lut);lut.wrapS=THREE.RepeatWrapping;assert.equal(observer.report().samplerUnchanged,false);
 lut.source=new THREE.Texture({data,width:16,height:16} as any).source;assert.equal(observer.report().sourceUnchanged,false);assert.equal(observer.report().dataUnchanged,false);observer.close();lut.dispose();
});
test('observing disposal events never suppresses an actual owned lookup disposal',()=>{
 const lut=new THREE.DataTexture(new Uint16Array(512),16,16,THREE.RGFormat,THREE.HalfFloatType);lut.name='DFG_LUT';lut.minFilter=lut.magFilter=THREE.LinearFilter;
 const observer=observeNativeImageDfg(lut);lut.dispose();assert.equal(observer.report().disposeEvents,1);observer.close();
});
