// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {nativeWindingAsset,nativeWindingCases} from './native-winding-assets.mjs';
test('native winding glTF has explicit aligned indices and identical shared mesh under opposite node determinants',()=>{
 const asset=nativeWindingAsset(),bytes=Buffer.from(asset.buffers[0].uri.split(',')[1],'base64');
 assert.equal(asset.nodes[0].mesh,asset.nodes[1].mesh);assert.deepEqual(asset.nodes[1].scale,[-1,1,1]);
 assert.equal(asset.nodes[0].scale,undefined);assert.equal(asset.materials[0].doubleSided,undefined);
 assert.equal(bytes.length,asset.buffers[0].byteLength);assert(asset.bufferViews.every(view=>view.byteOffset%4===0));
 const read=(index,Type)=>{const view=asset.bufferViews[index];return new Type(bytes.buffer,bytes.byteOffset+view.byteOffset,view.byteLength/Type.BYTES_PER_ELEMENT);};
 const indices=read(3,Uint16Array),positions=read(0,Float32Array),normals=read(1,Float32Array);
 assert.deepEqual([...indices],[0,1,2,3,4,5]);
 const winding=start=>{const a=indices[start]*3,b=indices[start+1]*3,c=indices[start+2]*3;return (positions[b]-positions[a])*(positions[c+1]-positions[a+1])-(positions[b+1]-positions[a+1])*(positions[c]-positions[a]);};
 assert(winding(0)>0);assert(winding(3)<0);assert(positions[2]>positions[11]);
 assert.deepEqual([...normals],Array.from({length:18},(_,i)=>i%3===2?1:0));
});
test('normal oracle switches a single controlled key direction without changing cull, geometry or source color',()=>{
 const [towards,away]=nativeWindingCases.slice(-2);assert.equal(towards.unlit,false);assert.equal(away.unlit,false);
 assert.equal(towards.cull,'CULL_NONE');assert.equal(away.cull,'CULL_NONE');
 assert.deepEqual(towards.lightDirection,{x:0,y:0,z:-1});assert.deepEqual(away.lightDirection,{x:0,y:0,z:1});
 assert.equal(towards.brighter,'positive');assert.equal(away.brighter,'mirrored');
});
