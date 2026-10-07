// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type {EmbeddedFbxImage,EmbeddedFbxPreparation} from './baked-fbx';
export interface EmbeddedFbxFields {embeddedImages?:readonly EmbeddedFbxImage[];embeddedCounts?:EmbeddedFbxPreparation['counts']}
/** Count actual transferred bytes; an ID/digest string never establishes a byte budget. */
export function embeddedFbxFields(input:EmbeddedFbxFields):{fields:EmbeddedFbxFields;bytes:number}{
 if(input.embeddedImages===undefined&&input.embeddedCounts===undefined)return {fields:{},bytes:0};
 if(!Array.isArray(input.embeddedImages)||input.embeddedImages.length>64||!input.embeddedCounts)throw Error('Invalid prepared embedded-image metadata');
 const images:EmbeddedFbxImage[]=[],keys=new Set<string>();let bytes=0;
 for(const image of input.embeddedImages){
  if(!image||typeof image!=='object'||typeof image.digest!=='string'||!/^[a-f0-9]{64}$/.test(image.digest)||!['image/png','image/jpeg','image/bmp','image/webp'].includes(image.mimeType)||!(image.bytes instanceof ArrayBuffer)||image.bytes.byteLength<1||image.bytes.byteLength>8*1024*1024)throw Error('Invalid prepared embedded-image descriptor');
  const key=image.mimeType+'|'+image.digest;if(keys.has(key))throw Error('Duplicate prepared embedded-image descriptor');keys.add(key);bytes+=image.bytes.byteLength;
  if(bytes>16*1024*1024)throw Error('Prepared embedded images exceed 16 MiB');images.push(Object.freeze({digest:image.digest,mimeType:image.mimeType,bytes:image.bytes}));
 }
 const counts=input.embeddedCounts;
 if(!['converted','rawBytes','skippedOversize','skippedUnsupported'].every(key=>Number.isSafeInteger(counts[key as keyof typeof counts])&&counts[key as keyof typeof counts]>=0)||counts.converted<images.length||counts.converted>64||counts.rawBytes!==bytes||counts.skippedOversize>100000||counts.skippedUnsupported>100000)throw Error('Invalid prepared embedded-image accounting');
 return {fields:{embeddedImages:Object.freeze(images),embeddedCounts:Object.freeze({converted:counts.converted,rawBytes:bytes,skippedOversize:counts.skippedOversize,skippedUnsupported:counts.skippedUnsupported})},bytes};
}
export function preparedFbxBytes(input:{buffer:ArrayBuffer}&EmbeddedFbxFields){
 if(!(input.buffer instanceof ArrayBuffer)||input.buffer.byteLength<1)throw Error('Invalid prepared FBX buffer');const result=embeddedFbxFields(input),total=input.buffer.byteLength+result.bytes;if(total>256*1024*1024)throw Error('Prepared FBX and embedded images exceed 256 MiB');return {fields:result.fields,bytes:total};
}
