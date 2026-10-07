// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Keep third-party synchronous HDR/TGA parsing off the visitor's render thread.
import {HDRLoader} from 'three/addons/loaders/HDRLoader.js';
import {TGALoader} from 'three/addons/loaders/TGALoader.js';
import {UnsignedByteType,type TextureDataType} from 'three';
export interface NativeSkyDecoded {width:number;height:number;data:Uint8Array<ArrayBuffer>|Uint16Array<ArrayBuffer>|Float32Array<ArrayBuffer>;type:TextureDataType}
export function decodeNativeSky(kind:'hdr'|'tga',buffer:ArrayBuffer):NativeSkyDecoded {
  if(buffer.byteLength>64*1024*1024)throw Error('The native sky decoder received an oversized source.');
  const view=new DataView(buffer);let width:number,height:number;
  if(kind==='tga'){
    if(buffer.byteLength<18)throw Error('The native TGA header is incomplete.');
    width=view.getUint16(12,true);height=view.getUint16(14,true);
  }else if(kind==='hdr'){
    const header=new TextDecoder().decode(new Uint8Array(buffer,0,Math.min(buffer.byteLength,8192)));
    const match=/(?:^|\n)-Y\s+(\d+)\s+\+X\s+(\d+)\s*(?:\r?\n)/.exec(header);
    if(!match)throw Error('The native HDR resolution header is unsupported.');
    width=Number(match[2]);height=Number(match[1]);
  }else throw Error('The native sky decoder format is unsupported.');
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width*height>32*1024*1024)throw Error('The native sky decoder exceeds its pixel budget.');
  const image=kind==='hdr'?new HDRLoader().parse(buffer):new TGALoader().parse(buffer);
  if(image.width!==width||image.height!==height||!image.data||image.data.byteLength>256*1024*1024)throw Error('The native sky decoder returned an invalid or oversized image.');
  return {width,height,data:image.data as NativeSkyDecoded['data'],type:'type' in image&&image.type!==undefined?image.type:UnsignedByteType};
}
// Node unit tests import the real decoder without creating a browser worker.
const scope=globalThis as unknown as {document?:unknown;postMessage?:(message:unknown,transfer:ArrayBuffer[])=>void;onmessage?:((event:MessageEvent)=>void)};
if(!scope.document&&typeof scope.postMessage==='function')scope.onmessage=(event:MessageEvent)=>{
  try{
    const input=event.data;
    if(!input||!['hdr','tga'].includes(input.kind)||!(input.buffer instanceof ArrayBuffer))throw Error('Invalid native sky decode request.');
    const image=decodeNativeSky(input.kind,input.buffer);
    scope.postMessage!({image},[image.data.buffer]);
  }catch(error){scope.postMessage!({error:error instanceof Error?error.message:'The native sky decoder failed.'},[]);}
};
