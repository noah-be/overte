// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {KTXLoader} from 'three/addons/loaders/KTXLoader.js';
import {inspectNativeKtx} from './audit-native-ktx.mjs';
const root=process.env.OVERTE_KTX_AUDIT_ROOT||path.resolve('..','build/browser-hub-lab/hub');
const leaf=await readFile(path.join(root,'shrub-jungle-leafy-1a.ktx'));
test('actual native leaf validates all ten mips and independently verified mask metadata',()=>{
 const result=inspectNativeKtx(leaf);assert.equal(result.glInternalFormat,35919);assert.equal(result.format.threeFormat,33779);assert.equal(result.width,512);assert.equal(result.mipmapCount,10);assert.equal(result.nativeUsage.flags,13);assert.equal(result.nativeUsage.classification,'mask');assert.equal(result.payloadBytes,349552);assert.equal(result.completeMipChain,true);
 const exact=leaf.buffer.slice(leaf.byteOffset,leaf.byteOffset+leaf.byteLength),three=new KTXLoader().parse(exact,true);
 assert.equal(three.format,35919,'Unadapted Three loader returns native sRGB enum, not THREE.DXT5 format');
 assert.deepEqual(three.mipmaps.map(x=>x.data.byteLength),result.mipmaps.map(x=>x.byteLength));
});
test('actual non-power-of-two opaque native texture retains integer mip dimensions',async()=>{
 const result=inspectNativeKtx(await readFile(path.join(root,'shrub-bluepops-1a.ktx')));
 assert.equal(result.nativeUsage.flags,1);assert.equal(result.format.threeFormat,33776);assert.equal(result.width,768);assert.equal(result.mipmapCount,10);assert.deepEqual(result.mipmaps.slice(-3).map(x=>x.width),[6,3,1]);
});
test('malformed native headers, unsupported shapes and exact payload bounds fail closed',()=>{
 for(const [at,value,message] of [[12,0x01020304,'little-endian'],[16,1,'type'],[32,0x1907,'base'],[36,0,'dimensions'],[44,1,'2D'],[48,1,'2D'],[52,6,'2D'],[56,1000,'mip count'],[60,0xffffffff,'metadata']]){
  const bad=Buffer.from(leaf);bad.writeUInt32LE(value,at);assert.throws(()=>inspectNativeKtx(bad),new RegExp(message));
 }
 assert.throws(()=>inspectNativeKtx(leaf.subarray(0,-1)),/bounds|bytes/);assert.throws(()=>inspectNativeKtx(Buffer.concat([leaf,Buffer.alloc(4)])),/trailing/);
 const bad=Buffer.from(leaf);bad.writeUInt32LE(1,64+bad.readUInt32LE(60));assert.throws(()=>inspectNativeKtx(bad),/block byte/);
});
test('native usage version, flags and duplicate metadata cannot be silently trusted',()=>{
 const version=Buffer.from(leaf);version[77]=3;assert.throws(()=>inspectNativeKtx(version),/version/);
 const flags=Buffer.from(leaf);flags.writeUInt32LE(8,77+29);assert.throws(()=>inspectNativeKtx(flags),/flags/);
 // Duplicate the exact first native key-value; update metadata size without changing any mip bytes.
 const firstSize=leaf.readUInt32LE(64),first=leaf.subarray(64,68+Math.ceil(firstSize/4)*4),duplicate=Buffer.concat([leaf.subarray(0,64),first,leaf.subarray(64)]);duplicate.writeUInt32LE(leaf.readUInt32LE(60)+first.length,60);assert.throws(()=>inspectNativeKtx(duplicate),/Duplicate/);
});

test('native version2 payload preserves usage with exact additional original-size bytes',()=>{
 const firstSize=leaf.readUInt32LE(64),oldEnd=68+Math.ceil(firstSize/4)*4;
 const entry=Buffer.from(leaf.subarray(64,oldEnd)),payloadOffset=13;
 const enlarged=Buffer.concat([entry.subarray(0,payloadOffset+34),Buffer.alloc(8),entry.subarray(payloadOffset+34)]);
 enlarged[payloadOffset]=2;enlarged.writeUInt32LE(firstSize+8,0);
 const bytes=Buffer.concat([leaf.subarray(0,64),enlarged,leaf.subarray(oldEnd)]);bytes.writeUInt32LE(leaf.readUInt32LE(60)+8,60);
 const result=inspectNativeKtx(bytes);assert.equal(result.nativeUsage.version,2);assert.equal(result.nativeUsage.flags,13);assert.equal(result.mipmapCount,10);
});
