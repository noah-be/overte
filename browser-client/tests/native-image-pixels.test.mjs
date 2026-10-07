// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {imagePixelComparison,assertLoadedImagePixels,compositeImagePixel} from './integration/native-image-pixels.mjs';
const actual=JSON.parse(await readFile(new URL('./fixtures/native-image-dark-pixels.json',import.meta.url),'utf8'));
const clone=value=>JSON.parse(JSON.stringify(value));
function variance(sample){const totals=[];for(let i=0;i<sample.rgb.length;i+=3)totals.push(sample.rgb[i]+sample.rgb[i+1]+sample.rgb[i+2]);const mean=totals.reduce((a,b)=>a+b)/totals.length;return totals.reduce((a,b)=>a+(b-mean)**2,0)/totals.length;}
function flip(sample,horizontal,vertical){const n=actual.grid,rgb=[];for(let y=0;y<n;y++)for(let x=0;x<n;x++){const index=((vertical?n-1-y:y)*n+(horizontal?n-1-x:x))*3;rgb.push(...sample.rgb.slice(index,index+3));}return{rgb,mask:sample.mask};}
test('genuine dark authored source and actual native pixels pass source detail even though both refute the universal variance200 guard',()=>{
 assert.equal(actual.sourcePNG_SHA256,'0087b3a3a9c9347b3a592db7b7e4f88fe333aedb7c6bd6aae48ed664c3f98739');assert(variance(actual.source)<200);assert(variance(actual.native)<200);const result=assertLoadedImagePixels(actual.native,actual.source);assert(result.rgbMAE<=10);assert(result.correlation>=.9);
});
test('a color-matched dark solid frame cannot pass solely because its mean color and RGB error are plausible',()=>{
 const means=[0,0,0];for(let i=0;i<actual.source.rgb.length;i++)means[i%3]+=actual.source.rgb[i]/(actual.source.rgb.length/3);const flat={rgb:Array.from({length:actual.source.rgb.length},(_,i)=>means[i%3]),mask:actual.source.mask};assert(imagePixelComparison(flat,actual.source).rgbMAE<10);assert.throws(()=>assertLoadedImagePixels(flat,actual.source),/detail|orientation/);
});
test('missing/background magenta and all three UV reversal controls fail without lowering existing color or correlation thresholds',()=>{
 const missing={rgb:Array.from({length:actual.source.rgb.length},(_,i)=>[255,0,255][i%3]),mask:actual.source.mask.map(()=>1)};assert.throws(()=>assertLoadedImagePixels(missing,actual.source),/colors/);for(const[h,v]of[[true,false],[false,true],[true,true]])assert.throws(()=>assertLoadedImagePixels(actual.native,flip(actual.source,h,v)),/detail|orientation/);
});
test('source RGBA is genuinely composed over authored magenta in linear light and hidden RGB never becomes visible detail',()=>{
 assert.deepEqual(compositeImagePixel(5,30,99,0),[255,0,255]);assert.deepEqual(compositeImagePixel(5,30,99,255),[5,30,99]);assert.deepEqual(compositeImagePixel(0,0,0,128),[187,0,187]);assert.notDeepEqual(compositeImagePixel(0,0,0,128),[127,0,127]);assert.throws(()=>compositeImagePixel(0,0,0,256),/Invalid/);
});
test('the ten-level RGB limit remains strict even when texture pattern correlation is exactly preserved',()=>{
 const shifted=clone(actual.source);shifted.rgb=shifted.rgb.map(v=>v+11);assert(imagePixelComparison(shifted,actual.source).correlation>=.99);assert.throws(()=>assertLoadedImagePixels(shifted,actual.source),/colors/);
});
test('pixel sample shape, finite channel values, mask values and fixed sample bounds are explicit',()=>{
 for(const value of[null,{rgb:[0,0,0],mask:[]},{rgb:[NaN,0,0],mask:[0]},{rgb:[0,0,0],mask:[2]},{rgb:Array(64*64*3+3).fill(0),mask:Array(64*64+1).fill(0)}])assert.throws(()=>imagePixelComparison(value,actual.source),/Invalid/);assert.throws(()=>imagePixelComparison({rgb:[0,0,0],mask:[0]},actual.source),/same grid/);
});
