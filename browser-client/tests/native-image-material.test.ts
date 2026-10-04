// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {inspectNativeImageAlpha,makeNativeImageMaterial} from '../src/native-image-material';

test('native Image omitted emissive is lit, roughness .9 metal0, explicit emissive stays exact unlit',()=>{
 const map=new THREE.Texture();
 for(const emissive of [undefined,false,true]){
  const material=makeNativeImageMaterial({emissive},map,'opaque');
  assert.equal(material instanceof THREE.MeshStandardMaterial,emissive!==true);assert.equal(material instanceof THREE.MeshBasicMaterial,emissive===true);
  assert.equal(material.toneMapped,emissive!==true);assert.equal(material.map,map);assert.equal(material.color.getHex(THREE.SRGBColorSpace),0xffffff);
  if(material instanceof THREE.MeshStandardMaterial){assert.equal(material.roughness,.9);assert.equal(material.metalness,0);}
  assert.equal(material.side,THREE.DoubleSide);assert.equal(material.forceSinglePass,true);assert.equal(material.transparent,false);assert.equal(material.depthWrite,true);material.dispose();
 }
 map.dispose();
});
test('native sRGB byte tint is linearized once and alpha uses normal continuous blending',()=>{
 const map=new THREE.Texture(),color={red:128,green:64,blue:32};
 for(const kind of ['opaque','mask','blend'] as const)for(const opacity of [0,.25,1]){
  const material=makeNativeImageMaterial({color,alpha:opacity,emissive:true},map,kind);
  assert.equal(material.color.r,THREE.MathUtils.clamp(new THREE.Color().setRGB(128/255,64/255,32/255,THREE.SRGBColorSpace).r,0,1));
  assert.equal(material.opacity,opacity);assert.equal(material.alphaTest,0);assert.equal(material.blending,THREE.NormalBlending);
  assert.equal(material.transparent,kind!=='opaque'||opacity<1);assert.equal(material.depthWrite,!material.transparent);material.dispose();
 }
 map.dispose();
});
test('native opacity bounds clamp; malformed colors/emissive/alpha/classification refuse without texture ownership changes',()=>{
 const map=new THREE.Texture();let disposed=0;map.addEventListener('dispose',()=>disposed++);
 for(const opacity of [-1,2]){const material=makeNativeImageMaterial({alpha:opacity},map,'opaque');assert.equal(material.opacity,Math.max(0,Math.min(1,opacity)));material.dispose();}
 for(const entity of [{alpha:NaN},{color:{red:256,green:0,blue:0}},{color:{red:.5,green:0,blue:0}},{emissive:'false'}])assert.throws(()=>makeNativeImageMaterial(entity as never,map,'opaque'));
 assert.throws(()=>makeNativeImageMaterial({},map,'unknown' as never));assert.equal(disposed,0);map.dispose();
});
test('foreign compressed and unreadable original alpha cannot invent opaque or MASK behavior',async()=>{
 const controller=new AbortController(),map=new THREE.CompressedTexture([],4,4);map.userData.nativeAlpha='mask';
 await assert.rejects(inspectNativeImageAlpha(map,controller.signal),/approved native texture/);map.dispose();
 const image=new THREE.Texture();await assert.rejects(inspectNativeImageAlpha(image,controller.signal),/loaded image/);
 controller.abort();await assert.rejects(inspectNativeImageAlpha(image,controller.signal),{name:'AbortError'});image.dispose();
});
