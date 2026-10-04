// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {NativeImageConvergence} from './integration/native-image-convergence.mjs';
function diagnostic(frame,extra={}){return {current:'mask-original',resourceState:3,renderFrames:frame,finishedFrameBaseline:0,renderMethod:0,antialiasing:{kind:'taa',mode:1,stopped:false,frozen:false,minimumSnapshotFrames:16},camera:{mode:'independent',position:{x:60,y:10,z:4},orientation:{x:0,y:0,z:0,w:1},fieldOfView:55,aspectRatio:4/3},...extra};}
function pixels(value=40){return {width:128,height:128,crop:{x:2,y:2,width:124,height:124},rgb:Array.from({length:64*64*3},(_,index)=>value+index%3),mask:Array(64*64).fill(0)};}
test('requires at least three stable actual native frame captures, not merely three ticks',()=>{
 const c=new NativeImageConvergence();assert.equal(c.push(diagnostic(16),pixels()).ready,false);assert.equal(c.push(diagnostic(32),pixels()).ready,false);assert.equal(c.push(diagnostic(48),pixels()).ready,true);
 assert.throws(()=>new NativeImageConvergence().push(diagnostic(2),pixels()),/FINISHED/);
 const duplicate=new NativeImageConvergence();duplicate.push(diagnostic(16),pixels());assert.throws(()=>duplicate.push(diagnostic(16),pixels()),/separated/);
});
test('gradual temporal drift must settle for three pairwise-stable captures',()=>{
 const c=new NativeImageConvergence();c.push(diagnostic(16),pixels(30));c.push(diagnostic(32),pixels(30.4));assert.equal(c.push(diagnostic(48),pixels(30.8)).ready,false);
 assert.equal(c.push(diagnostic(64),pixels(30.8)).ready,false);assert.equal(c.push(diagnostic(80),pixels(30.8)).ready,true);
 const mask=new NativeImageConvergence();mask.push(diagnostic(16),pixels());const changed=pixels();changed.mask.fill(1,0,16);assert.equal(mask.push(diagnostic(32),changed).stableCaptures,1);
});
test('changed camera, texture/case or measured crop cannot borrow another stable frame cohort',()=>{
 for(const changed of [diagnostic(48,{current:'mask-compressed'}),diagnostic(48,{finishedFrameBaseline:16}),diagnostic(48,{camera:{...diagnostic(48).camera,fieldOfView:56}})]){
  const c=new NativeImageConvergence();c.push(diagnostic(16),pixels());c.push(diagnostic(32),pixels());assert.equal(c.push(changed,pixels()).ready,false);
 }
 const crop=new NativeImageConvergence();crop.push(diagnostic(16),pixels());crop.push(diagnostic(32),pixels());const changed=pixels();changed.crop.x=3;changed.crop.width=123;assert.equal(crop.push(diagnostic(48),changed).ready,false);
});
test('unstable output exhausts its finite eight-capture budget instead of extending readiness indefinitely',()=>{
 const c=new NativeImageConvergence();for(let index=1;index<=8;index++)assert.equal(c.push(diagnostic(index*16),pixels(index%2?30:100)).ready,false);
 assert.throws(()=>c.push(diagnostic(144),pixels()),/eight bounded captures/);
});
test('finite resource/camera/pixel geometry and a known actual AA frame spacing are mandatory',()=>{
 for(const d of [diagnostic(16,{resourceState:2}),diagnostic(16,{renderFrames:NaN}),diagnostic(16,{antialiasing:{minimumSnapshotFrames:null}}),diagnostic(16,{camera:{...diagnostic(16).camera,aspectRatio:Infinity}})])assert.throws(()=>new NativeImageConvergence().push(d,pixels()));
 const tooLarge=pixels();tooLarge.width=8192;tooLarge.height=8192;assert.throws(()=>new NativeImageConvergence().push(diagnostic(16),tooLarge),/bounded/);
 const bad=pixels();bad.rgb[0]=NaN;assert.throws(()=>new NativeImageConvergence().push(diagnostic(16),bad));
 const forward=diagnostic(3,{renderMethod:1,antialiasing:{kind:'forward-msaa',minimumSnapshotFrames:3}}),c=new NativeImageConvergence();c.push(forward,pixels());c.push({...forward,renderFrames:6},pixels());assert.equal(c.push({...forward,renderFrames:9},pixels()).ready,true);
});
