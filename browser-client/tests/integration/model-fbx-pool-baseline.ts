// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Independent same-thread reference for the complete current preparation protocol.
import {adaptBakedFbx,normalizeNativeFbxTransparency,extractEmbeddedFbxImages} from '../../src/baked-fbx';
import {embeddedFbxFields,type EmbeddedFbxFields} from '../../src/embedded-fbx-protocol';
export async function prepareFbxProofBaseline(input:ArrayBuffer){
 const embedded=await extractEmbeddedFbxImages(normalizeNativeFbxTransparency(input));
 const buffer=await adaptBakedFbx(embedded.buffer);
 return {buffer,embeddedImages:embedded.images,embeddedCounts:embedded.counts};
}
const sha=async(bytes:ArrayBuffer)=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');
/** An FBX marker alone is not image fidelity. Validate/hash every exact sidecar. */
export async function inspectFbxProofEmbedded(input:EmbeddedFbxFields){
 const checked=embeddedFbxFields(input),descriptors=[];
 for(const image of checked.fields.embeddedImages??[]){
  const sha256=await sha(image.bytes);
  if(sha256!==image.digest)throw Error('Prepared embedded-image digest does not match exact bytes');
  descriptors.push({digest:image.digest,mimeType:image.mimeType,bytes:image.bytes.byteLength,sha256});
 }
 descriptors.sort((a,b)=>a.mimeType<b.mimeType?-1:a.mimeType>b.mimeType?1:a.digest<b.digest?-1:a.digest>b.digest?1:0);
 return {embeddedImages:descriptors,...(checked.fields.embeddedCounts?{embeddedCounts:{...checked.fields.embeddedCounts}}:{})};
}
