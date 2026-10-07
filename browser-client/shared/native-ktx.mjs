// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Strict native KTX1 validation shared by offline audit and the isolated color prototype.
const formats=new Map([
 [0x83f0,{name:'RGB_DXT1',threeFormat:0x83f0,blockBytes:8,srgb:false,alpha:false}],
 [0x83f1,{name:'RGBA_DXT1',threeFormat:0x83f1,blockBytes:8,srgb:false,alpha:true}],
 [0x83f2,{name:'RGBA_DXT3',threeFormat:0x83f2,blockBytes:16,srgb:false,alpha:true}],
 [0x83f3,{name:'RGBA_DXT5',threeFormat:0x83f3,blockBytes:16,srgb:false,alpha:true}],
 [0x8c4c,{name:'SRGB_DXT1',threeFormat:0x83f0,blockBytes:8,srgb:true,alpha:false}],
 [0x8c4d,{name:'SRGBA_DXT1',threeFormat:0x83f1,blockBytes:8,srgb:true,alpha:true}],
 [0x8c4e,{name:'SRGBA_DXT3',threeFormat:0x83f2,blockBytes:16,srgb:true,alpha:true}],
 [0x8c4f,{name:'SRGBA_DXT5',threeFormat:0x83f3,blockBytes:16,srgb:true,alpha:true}],
]);
const signature=[0xab,0x4b,0x54,0x58,0x20,0x31,0x31,0xbb,13,10,26,10];
function require(value,message){if(!value)throw Error(message);}
/** Return primitive diagnostics and exact bounded mip views, without altering bytes. */
export function inspectNativeKtx(input){
 const bytes=input instanceof ArrayBuffer?new Uint8Array(input):new Uint8Array(input.buffer,input.byteOffset,input.byteLength);
 require(bytes.length>=64&&bytes.length<=32*1024*1024,'KTX byte bounds');
 require(signature.every((n,i)=>bytes[i]===n),'KTX1 signature');
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
 require(view.getUint32(12,true)===0x04030201,'Only audited native little-endian KTX1 is supported');
 const h=Array.from({length:13},(_,i)=>view.getUint32(12+4*i,true));
 require(h[1]===0&&h[2]===1&&h[3]===0,'Compressed KTX type/size/format');
 const format=formats.get(h[4]);require(format,'Unsupported native compressed format');
 require(h[5]===(format.alpha?0x1908:0x1907),'KTX base format mismatch');
 const width=h[6],height=h[7],count=h[11];require(width>0&&height>0&&width<=16384&&height<=16384,'KTX dimensions');
 require(h[8]===0&&h[9]===0&&h[10]===1,'Only non-array single-face 2D KTX is supported');
 const fullLevels=Math.floor(Math.log2(Math.max(width,height)))+1;
 require(count>=1&&count<=fullLevels,'KTX mip count');
 require(h[12]<=65536&&h[12]%4===0&&64+h[12]<=bytes.length,'KTX metadata bounds');
 const keys=new Set();let offset=64,gpu=null,orientation=null;
 while(offset<64+h[12]){
  require(offset+4<=64+h[12],'KTX metadata length bounds');const size=view.getUint32(offset,true);offset+=4;
  require(size>1&&offset+size<=64+h[12],'KTX metadata item bounds');const item=bytes.subarray(offset,offset+size),nul=item.indexOf(0);
  require(nul>0&&nul<=256,'KTX metadata key bounds');
  const name=new TextDecoder('utf-8',{fatal:true}).decode(item.subarray(0,nul));require(!keys.has(name),'Duplicate KTX metadata key');keys.add(name);
  const payload=item.subarray(nul+1);
  if(name==='hifi.gpu'){
   require((payload[0]===1&&payload.length===36)||(payload[0]===2&&payload.length===44),'Native GPU payload version/size');
   const data=new DataView(payload.buffer,payload.byteOffset,payload.byteLength),flags=data.getUint32(29,true);
   require(flags<=15&&(!(flags&8)||(flags&4)),'Native GPU usage flags');require(!(flags&4)||format.alpha,'Native alpha usage requires alpha-capable format');
   const originalSize=payload[0]===2?{width:data.getInt32(34,true),height:data.getInt32(38,true)}:undefined;
   gpu={...(originalSize?{originalSize}:{}),version:payload[0],flags,color:Boolean(flags&1),normal:Boolean(flags&2),classification:flags&4?(flags&8?'mask':'blend'):'opaque'};
  }
  if(name==='KTXorientation'){
   orientation=new TextDecoder('utf-8',{fatal:true}).decode(payload).replace(/\0$/,'');require(orientation==='S=r,T=u'||orientation==='S=r,T=d','Unsupported KTX orientation');
  }
  offset+=Math.ceil(size/4)*4;require(offset<=64+h[12],'KTX metadata padding bounds');
 }
 require(offset===64+h[12]&&gpu,'Native GPU metadata is required for this audit');
 const mipmaps=[];let w=width,t=height,payloadBytes=0;
 for(let level=0;level<count;level++){
  require(offset+4<=bytes.length,'KTX mip size bounds');const size=view.getUint32(offset,true);offset+=4;
  const expected=Math.ceil(w/4)*Math.ceil(t/4)*format.blockBytes;
  require(size===expected,'KTX compressed block byte count mismatch');require(offset+size<=bytes.length,'KTX mip payload bounds');
  mipmaps.push({width:w,height:t,byteLength:size,data:bytes.subarray(offset,offset+size)});payloadBytes+=size;offset+=Math.ceil(size/4)*4;require(offset<=bytes.length,'KTX mip padding bounds');
  w=Math.max(1,Math.floor(w/2));t=Math.max(1,Math.floor(t/2));
 }
 require(offset===bytes.length,'KTX trailing/missing bytes');
 return {width,height,mipmapCount:count,completeMipChain:count===fullLevels,glInternalFormat:h[4],format:{...format},nativeUsage:gpu,orientation,payloadBytes,mipmaps};
}
