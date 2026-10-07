// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {prepareFbxProofBaseline,inspectFbxProofEmbedded} from './integration/model-fbx-pool-baseline';
import {normalizeNativeFbxTransparency,adaptBakedFbx} from '../src/baked-fbx';
import {embeddedFbx,embeddedPNG} from './fixtures/embedded-fbx';
const hash=(bytes:ArrayBuffer)=>createHash('sha256').update(new Uint8Array(bytes)).digest('hex');
const source=()=>({embeddedImages:[{digest:hash(embeddedPNG.slice().buffer),mimeType:'image/png',bytes:embeddedPNG.slice().buffer}],embeddedCounts:{converted:1,rawBytes:embeddedPNG.byteLength,skippedOversize:0,skippedUnsupported:0}});
for(const wide of [false,true])test('complete independent FBX baseline retains exact embedded bytes under '+(wide?'64':'32')+'-bit node format',async()=>{
 const input=embeddedFbx(embeddedPNG,'png',wide),old=await adaptBakedFbx(normalizeNativeFbxTransparency(input)),actual=await prepareFbxProofBaseline(input);
 assert.notEqual(hash(actual.buffer),hash(old),'A stale buffer-only baseline cannot cover extracted image sidecars');assert.equal(actual.embeddedCounts.converted,1);assert.equal(actual.embeddedCounts.rawBytes,embeddedPNG.byteLength);assert.deepEqual(new Uint8Array(actual.embeddedImages[0].bytes),embeddedPNG);
 assert.deepEqual(await inspectFbxProofEmbedded(actual),{embeddedImages:[{digest:hash(embeddedPNG.slice().buffer),mimeType:'image/png',bytes:embeddedPNG.byteLength,sha256:hash(embeddedPNG.slice().buffer)}],embeddedCounts:{converted:1,rawBytes:embeddedPNG.byteLength,skippedOversize:0,skippedUnsupported:0}});
});
test('unextracted unsupported embedded formats preserve original buffer and exact refusal accounting',async()=>{const input=embeddedFbx(embeddedPNG,'psd'),actual=await prepareFbxProofBaseline(input);assert.equal(actual.embeddedImages.length,0);assert.equal(actual.embeddedCounts.converted,0);assert.equal(actual.embeddedCounts.skippedUnsupported,1);assert.equal(actual.buffer.byteLength,(await adaptBakedFbx(normalizeNativeFbxTransparency(input))).byteLength);});
test('sidecar digest inspection rejects actual mutated bytes rather than trusting declared markers',async()=>{const input=source();new Uint8Array(input.embeddedImages[0].bytes)[0]^=1;await assert.rejects(inspectFbxProofEmbedded(input),/digest does not match exact bytes/);});
test('dropping a transferred embedded descriptor cannot retain successful original accounting',async()=>{const input=source();input.embeddedImages=[];await assert.rejects(inspectFbxProofEmbedded(input),/accounting/);});
test('altered MIME metadata cannot be silently accepted as the same prepared output',async()=>{const expected=await inspectFbxProofEmbedded(source()),input=source();input.embeddedImages[0].mimeType='image/jpeg';assert.notDeepEqual(await inspectFbxProofEmbedded(input),expected);input.embeddedImages[0].mimeType='image/unsupported';await assert.rejects(inspectFbxProofEmbedded(input),/descriptor/);});
test('missing all sidecar metadata differs from a complete extracted image result',async()=>{assert.notDeepEqual(await inspectFbxProofEmbedded({}),await inspectFbxProofEmbedded(source()));});
test('exact sidecar inspection retains immutable input buffers and private aggregate shape',async()=>{const input=source(),before=hash(input.embeddedImages[0].bytes),actual=await inspectFbxProofEmbedded(input);assert.equal(hash(input.embeddedImages[0].bytes),before);assert.deepEqual(Object.keys(actual).sort(),['embeddedCounts','embeddedImages']);assert.equal(actual.embeddedImages[0].sha256,before);});
