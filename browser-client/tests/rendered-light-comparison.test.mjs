// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {compareRenderedLightImages as compare}from './fixtures/rendered-light-comparison.mjs';
const image=(width,height,pixels)=>({width,height,pixels:Uint8ClampedArray.from(pixels)});
test('exact old full-image counts remain zero and have no invented changed bounds',()=>{
 const a=image(2,1,[80,40,90,255,0,255,80,255]);assert.deepEqual(compare(a,a),{different:0,maximum:0,foreground:4,changedPixels:0,changedChannels:[0,0,0,0],changedPixelBounds:null,sampledPixels:[]});
});
test('independent known two-channel one-level oracle records exact pixel coordinates/RGBA and preserves rejection',()=>{
 const a=image(2,2,[80,40,90,255,0,255,80,255,20,30,40,255,50,60,70,255]),b=image(2,2,[80,40,90,255,0,255,80,255,20,31,41,255,50,60,70,255]);const proof=compare(a,b);assert.equal(proof.different,2);assert.equal(proof.maximum,1);assert.equal(proof.changedPixels,1);assert.deepEqual(proof.changedChannels,[0,1,1,0]);assert.deepEqual(proof.changedPixelBounds,{minX:0,minY:1,maxX:0,maxY:1});assert.deepEqual(proof.sampledPixels,[{x:0,y:1,baselineRGBA:[20,30,40,255],candidateRGBA:[20,31,41,255]}]);assert.throws(()=>assert.equal(proof.different,0));
});
test('sixteen-sample cap never truncates full-image counts, channel histogram or changed-pixel bounds',()=>{
 const a=image(20,2,Array(160).fill(80)),b=image(20,2,Array(160).fill(81)),proof=compare(a,b);assert.equal(proof.different,160);assert.equal(proof.maximum,1);assert.equal(proof.foreground,120);assert.equal(proof.changedPixels,40);assert.deepEqual(proof.changedChannels,[40,40,40,40]);assert.deepEqual(proof.changedPixelBounds,{minX:0,minY:0,maxX:19,maxY:1});assert.equal(proof.sampledPixels.length,16);assert.equal(proof.sampledPixels[15].x,15);proof.sampledPixels[0].baselineRGBA[0]=0;assert.equal(a.pixels[0],80);assert.equal(b.pixels[0],81);
});
test('dimension/buffer alias, oversize, incomplete and malformed arrays refuse rather than imply equality',()=>{
 const a=image(1,1,[0,0,0,255]);for(const broken of[{...a,width:0},{...a,width:4097},{...a,height:1.5},{...a,pixels:[0,0,0,255]},{...a,pixels:new Uint8Array(3)}])assert.throws(()=>compare(a,broken),/RGBA/);assert.throws(()=>compare(a,image(2,1,Array(8).fill(0))),/Drawing buffer changed/);
});
