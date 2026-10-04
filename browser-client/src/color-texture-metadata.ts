// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import type {CompressionCapabilities} from './native-compressed-color';
export type TextureRole='albedo'|'emissive'|'other'|'linear';
const formats=new Map<string,THREE.CompressedPixelFormat>([
 ['COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT',THREE.RGBA_S3TC_DXT5_Format],
 ['COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT',THREE.RGBA_S3TC_DXT3_Format],
 ['COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT',THREE.RGBA_S3TC_DXT1_Format],
 ['COMPRESSED_SRGB_S3TC_DXT1_EXT',THREE.RGB_S3TC_DXT1_Format],
]);
function record(value:unknown):value is Record<string,unknown>{return !!value&&typeof value==='object'&&!Array.isArray(value);}
/** Audited native version1 candidates only; a missing supported codec is an ordinary original-image path. */
export function colorTextureCandidate(metadata:unknown,role:TextureRole,caps:CompressionCapabilities):{source:string;format:THREE.CompressedPixelFormat}|undefined{
 if(role!=='albedo'&&role!=='emissive')return undefined;
 if(!record(metadata)||metadata.version!==1)throw Error('Unsupported or malformed native color texture metadata');
 if(metadata.compressed===undefined)return undefined;
 if(!record(metadata.compressed)||Object.keys(metadata.compressed).length>32)throw Error('Invalid compressed texture metadata');
 for(const [name,value]of Object.entries(metadata.compressed))if(name.length>128||typeof value!=='string'||!value||value.length>4096)throw Error('Invalid compressed texture reference');
 for(const [name,format]of formats){
  const source=metadata.compressed[name];if(source===undefined)continue;
  // ATP content hashes need not have a filename extension. The byte parser verifies KTX1, never the suffix.
  if(!caps.s3tc||!caps.s3tcSRGB)return undefined;
  return {source:source as string,format};
 }
 return undefined;
}
/** Opted-in native color metadata is bounded before JSON decoding. */
export async function readColorTextureMetadata(response:Response,signal:AbortSignal):Promise<unknown>{
 const maximum=65536,declared=response.headers.get('content-length');
 if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>maximum)){await response.body?.cancel();throw Error('Native color metadata exceeds its byte bound');}
 if(!response.body)throw Error('Native color metadata has no body');
 const reader=response.body.getReader(),chunks:Uint8Array[]=[];let length=0;
 const abort=()=>{void reader.cancel(signal.reason).catch(()=>{});};signal.addEventListener('abort',abort,{once:true});
 if(signal.aborted)abort();
 try{signal.throwIfAborted();while(true){const next=await reader.read();signal.throwIfAborted();if(next.done)break;length+=next.value.byteLength;if(length>maximum)throw Error('Native color metadata exceeds its byte bound');chunks.push(next.value);}}
 catch(error){await reader.cancel().catch(()=>{});throw error;}finally{signal.removeEventListener('abort',abort);reader.releaseLock();}
 const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
 return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
