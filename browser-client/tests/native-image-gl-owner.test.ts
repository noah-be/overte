// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';import * as THREE from 'three';import {trackNativeImageTextures} from './native-image-gl-owner';
function fixture(){let next=0;const gl:any={ACTIVE_TEXTURE:1,NO_ERROR:0,getParameter:()=>10,getError:()=>0,isContextLost:()=>false,createTexture:()=>({id:++next}),deleteTexture(){},activeTexture(){},bindTexture(){},texImage2D(){},texSubImage2D(){}};return {gl,original:{...gl},track:trackNativeImageTextures(gl as unknown as WebGL2RenderingContext)};}
test('public GL identity tracker separates successful owned Image delete submissions from live borrowed DFG',()=>{
 const {gl,track}=fixture(),image={},dfg={},own=gl.createTexture(),shared=gl.createTexture();track.own(image);gl.bindTexture(2,own);gl.texSubImage2D(2,0,image);gl.bindTexture(2,shared);gl.texImage2D(2,0,dfg);gl.deleteTexture(own);
 assert.deepEqual(track.report(dfg),{created:2,deleted:1,deleteFailures:0,ownedUploaded:1,ownedRemaining:0,borrowedUploaded:1,borrowedRemaining:1,unrecognizedRemaining:0});track.restore();
});
test('tracker never claims live or unclassified GL handles are released',()=>{
 const {gl,track}=fixture(),image={},handle=gl.createTexture(),unknown=gl.createTexture();track.own(image);gl.bindTexture(2,handle);gl.texSubImage2D(2,0,image);assert.equal(track.report().ownedRemaining,1);assert.equal(track.report().unrecognizedRemaining,2);gl.deleteTexture(unknown);assert.equal(track.report().unrecognizedRemaining,1);track.restore();
});
test('sampler units retain independent binding identities and restoration preserves original GL methods',()=>{
 const {gl,track,original}=fixture(),image={},dfg={},a=gl.createTexture(),b=gl.createTexture();track.own(image);gl.activeTexture(10);gl.bindTexture(2,a);gl.activeTexture(11);gl.bindTexture(2,b);gl.activeTexture(10);gl.texSubImage2D(2,0,image);gl.activeTexture(11);gl.texSubImage2D(2,0,dfg);gl.deleteTexture(a);assert.equal(track.report(dfg).ownedRemaining,0);assert.equal(track.report(dfg).borrowedRemaining,1);track.restore();for(const key of ['createTexture','deleteTexture','activeTexture','bindTexture','texImage2D','texSubImage2D'] as const)assert.equal(gl[key],original[key]);
});

test('actual Three Texture upload ownership uses Source.data and rejects nonexistent Source.image',()=>{
 const {gl,track}=fixture(),image={width:8,height:8},texture=new THREE.Texture(image as any),handle=gl.createTexture();
 assert.equal(texture.source.data,image);assert.equal(texture.image,image);
 assert.throws(()=>track.own((texture.source as any).image),/actual Texture.source.data/);
 track.own(texture.source.data);gl.bindTexture(2,handle);gl.texSubImage2D(2,0,texture.image);
 assert.equal(track.report().ownedUploaded,1);gl.deleteTexture(handle);assert.equal(track.report().ownedRemaining,0);track.restore();texture.dispose();
});
test('a throwing original delete never marks the owned handle deleted and preserves original failure',()=>{
 const gl:any={ACTIVE_TEXTURE:1,NO_ERROR:0,getParameter:()=>10,getError:()=>0,isContextLost:()=>false,createTexture:()=>({}),deleteTexture(){throw Error('driver boundary failed');},activeTexture(){},bindTexture(){},texImage2D(){},texSubImage2D(){}};
 const track=trackNativeImageTextures(gl),image={},handle=gl.createTexture();track.own(image);gl.bindTexture(2,handle);gl.texImage2D(2,0,image);
 assert.throws(()=>gl.deleteTexture(handle),/driver boundary failed/);assert.equal(track.report().deleted,0);assert.equal(track.report().ownedRemaining,1);assert.equal(track.report().deleteFailures,1);track.restore();
});
for(const failure of ['error','context-loss'])test(`a ${failure} delete submission refuses successful cleanup evidence`,()=>{
 const {gl,track}=fixture(),image={},handle=gl.createTexture();track.own(image);gl.bindTexture(2,handle);gl.texSubImage2D(2,0,image);
 if(failure==='error')gl.getError=()=>1282;else gl.isContextLost=()=>true;
 assert.throws(()=>gl.deleteTexture(handle),/delete submission failed/);assert.equal(track.report().deleted,0);assert.equal(track.report().ownedRemaining,1);assert.equal(track.report().deleteFailures,1);track.restore();
});
test('bounded handle diagnostics refuse before creating an untracked allocation',()=>{
 const {gl,track}=fixture();for(let at=0;at<256;at++)gl.createTexture();assert.throws(()=>gl.createTexture(),/allocation diagnostics exceeded/);assert.equal(track.report().created,256);track.restore();
});
