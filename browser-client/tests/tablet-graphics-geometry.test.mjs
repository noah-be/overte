// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {locateNativeGraphicsControls,resolutionSliderX,measureNativeGraphicsRows} from './integration/tablet-graphics-geometry.mjs';
function rows(offset=0){return Array.from({length:580},(_,i)=>{const y=i+70;return {y,slider:(y>=275+offset&&y<295+offset)||(y>=335+offset&&y<355+offset)?160:0,combo:y>=108&&y<143?145:0};});}
test('actual native tracks determine page rows after variable wrapped-description height',()=>{
    assert.equal(locateNativeGraphicsControls(rows()).resolutionPercent.y,344.5);
    assert.equal(locateNativeGraphicsControls(rows(24)).resolutionPercent.y,368.5);
    assert.equal(locateNativeGraphicsControls(rows()).profile.y,125);
});
test('missing/duplicate/ambiguous actual widgets fail, rather than a guessed input',()=>{
    assert.throws(()=>locateNativeGraphicsControls(rows().map(row=>({...row,slider:0}))));
    const duplicate=rows();for(let y=450;y<470;y++)duplicate[y-70].slider=170;
    assert.throws(()=>locateNativeGraphicsControls(duplicate));
    const malformed=rows();malformed[0].y=1;assert.throws(()=>locateNativeGraphicsControls(malformed));
});
test('resolution slider has pinned physical endpoints and exact valid native steps',()=>{
    assert.equal(resolutionSliderX(10),281);assert.equal(resolutionSliderX(200),449);
    assert.equal(resolutionSliderX(70),334.0526315789474);
    for(const value of [NaN,0,70.1,75,210])assert.throws(()=>resolutionSliderX(value));
});
test('canvas measurement rejects oversized/out-of-bounds access before any pixel allocation',()=>{
    const canvas={width:480,height:706,getContext(){throw Error('Must not read pixels');}};
    assert.throws(()=>measureNativeGraphicsRows(canvas,{x:0,y:0,width:481,height:706}),/Must not|Unsupported/);
    assert.throws(()=>measureNativeGraphicsRows({...canvas,width:8000,height:8000},{x:0,y:0,width:480,height:706}),/Unsupported/);
    assert.throws(()=>measureNativeGraphicsRows(canvas,{x:NaN,y:0,width:480,height:706}),/Unsupported/);
});
test('measurement decodes actual native palette at scaled Desktop tablet coordinates',()=>{
    const width=960,height=1412,pixels=new Uint8ClampedArray(width*height*4);
    for(let offset=0;offset<pixels.length;offset+=4){pixels[offset]=pixels[offset+1]=pixels[offset+2]=27;pixels[offset+3]=255;}
    function paint(x0,y0,x1,y1,r,g,b){for(let y=y0*2;y<y1*2;y++)for(let x=x0*2;x<x1*2;x++){const i=(y*width+x)*4;pixels[i]=r;pixels[i+1]=g;pixels[i+2]=b;}}
    paint(270,108,459,143,51,51,51);
    paint(272,275,459,295,255,255,255);paint(272,275,350,295,81,83,189);
    paint(272,335,459,355,255,255,255);paint(272,335,360,355,81,83,189);
    // A thumb interrupts a painted native track; it must not become a third row.
    paint(350,265,370,305,128,128,128);paint(360,325,380,365,128,128,128);
    const canvas={width,height,getContext(){return {getImageData(){return {data:pixels};}};}};
    const result=locateNativeGraphicsControls(measureNativeGraphicsRows(canvas,{x:0,y:0,width,height}));
    assert.deepEqual(result,{profile:{x:360,y:125},fieldOfView:{y:284.5},resolutionPercent:{y:344.5},localLights:{x:410,y:404.5},cameraClipping:{x:410,y:464.5}});
});
test('actual Qt caption-gap histogram finds the genuine combo without any guessed Y',async()=>{
    const {readFile}=await import('node:fs/promises');
    const fixture=JSON.parse(await readFile(new URL('./fixtures/native-graphics-profile-rows.json',import.meta.url),'utf8'));
    assert.equal(fixture.width,480);assert.equal(fixture.height,706);
    assert.match(fixture.sourcePngSha256,/^[0-9a-f]{64}$/);
    const actual=locateNativeGraphicsControls(fixture.rows);
    assert.deepEqual(actual,{profile:{x:360,y:123},fieldOfView:{y:285.5},resolutionPercent:{y:345.5},localLights:{x:410,y:405.5},cameraClipping:{x:410,y:465.5}});
    const shifted=fixture.rows.map((row,index,array)=>({...row,slider:index>=24?array[index-24].slider:0,combo:index>=24?array[index-24].combo:0}));
    assert.equal(locateNativeGraphicsControls(shifted).profile.y,147);
    assert.equal(locateNativeGraphicsControls(shifted).resolutionPercent.y,369.5);
});
test('glyph-gap bridging still rejects disconnected rectangles, sparse text and multiple native combos',()=>{
    const fragmented=rows();for(let y=118;y<130;y++)fragmented[y-70].combo=0;
    assert.throws(()=>locateNativeGraphicsControls(fragmented),/exactly one/);
    const sparse=rows();for(let y=108;y<143;y++)sparse[y-70].combo=(y%3===0?145:0);
    assert.throws(()=>locateNativeGraphicsControls(sparse),/exactly one/);
    const duplicate=rows();for(let y=180;y<215;y++)duplicate[y-70].combo=145;
    assert.throws(()=>locateNativeGraphicsControls(duplicate),/exactly one/);
    const tooTall=rows();for(let y=143;y<160;y++)tooTall[y-70].combo=145;
    assert.throws(()=>locateNativeGraphicsControls(tooTall),/exactly one/);
});
