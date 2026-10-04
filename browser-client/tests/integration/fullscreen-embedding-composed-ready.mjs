// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {expectedEmbeddingScreenshotColor,preservePrivateComposedPng} from './fullscreen-screenshot-profile.mjs';
import assert from 'node:assert/strict';import {createHash}from'node:crypto';import{inflateSync}from'node:zlib';
/** Actual compositor output, not a replacement for original physical-event proof. */
export function readEmbeddingCanvasReady(element){
 const p=window.__fullscreenTablet,r=element.getBoundingClientRect(),acks=p?.sent.filter(v=>v.action==='frameAck'&&v.displayed===true)||[],ack=acks.at(-1),navigation=p?.sent.filter(v=>['open','home','back','close'].includes(v.action)).at(-1);
 return {connected:element.isConnected===true&&p?.host.isConnected===true,currentCanvas:element===p?.host.querySelector('canvas'),visible:document.visibilityState==='visible',density:devicePixelRatio,inner:{width:innerWidth,height:innerHeight},bounds:{x:r.x,y:r.y,width:r.width,height:r.height},ack:ack?{revision:ack.revision,frameSequence:ack.frameSequence,sequence:ack.sequence,displayed:ack.displayed}:null,navigation:navigation?{action:navigation.action,sequence:navigation.sequence}:null};
}
export function qualifyEmbeddingCanvasState(value){
 assert(value&&value.connected===true&&value.currentCanvas===true&&value.visible===true,'The current owned canvas must remain visible/connected');assert(Number.isFinite(value.density)&&value.density>0&&value.density<=8);assert([value.inner.width,value.inner.height].every(v=>Number.isSafeInteger(v)&&v>0&&v<=16384));const r=value.bounds;assert(r&&Object.values(r).every(v=>Number.isFinite(v)&&Math.abs(v)<=16384));assert(r.width>0&&r.height>0&&r.x>=0&&r.y>=0&&r.x+r.width<=value.inner.width&&r.y+r.height<=value.inner.height,'Original center must already be in the viewport; do not scroll');assert(r.width*value.density<=4096&&r.height*value.density<=4096&&r.width*r.height*value.density**2<=4*1024*1024);assert(value.ack?.displayed===true&&value.ack.revision===1&&value.ack.frameSequence===1);assert(value.navigation?.action==='open'&&Number.isSafeInteger(value.navigation.sequence)&&value.navigation.sequence>=1);assert(Number.isSafeInteger(value.ack.sequence)&&value.ack.sequence>value.navigation.sequence,'Actual displayed ACK must follow the current authored open command');return value;
}
export function pngCrc32(bytes){let c=0xffffffff;for(const v of bytes){c^=v;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;}
export function qualifyEmbeddingComposedPng(bytes){
 assert(bytes instanceof Uint8Array&&bytes.byteLength>=33&&bytes.byteLength<=4*1024*1024,'Bounded owned PNG required');const b=Buffer.from(bytes.buffer,bytes.byteOffset,bytes.byteLength);assert(b.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
 let offset=8,width,height,channels,seenHeader=false,seenData=false,dataEnded=false,ended=false,count=0,idatBytes=0,profile=null,explicitSrgb=false;const idats=[];
 while(offset<b.length){assert(++count<=4096&&offset+12<=b.length);const n=b.readUInt32BE(offset);assert(n<=b.length-offset-12);const type=b.toString('ascii',offset+4,offset+8);assert(/^[A-Za-z]{4}$/.test(type));const data=b.subarray(offset+8,offset+8+n);assert.equal(pngCrc32(b.subarray(offset+4,offset+8+n)),b.readUInt32BE(offset+8+n),'Owned PNG CRC must verify');
  if(type==='IHDR'){assert(!seenHeader&&offset===8&&n===13);seenHeader=true;width=data.readUInt32BE(0);height=data.readUInt32BE(4);assert(width>0&&height>0&&width<=4096&&height<=4096&&width*height<=4*1024*1024,'Bound decompression dimensions before decoding');assert.equal(data[8],8);assert([2,6].includes(data[9]));channels=data[9]===6?4:3;assert.equal(data[10],0);assert.equal(data[11],0);assert.equal(data[12],0);}
  else if(type==='iCCP'){assert(seenHeader&&!seenData&&!profile&&!explicitSrgb&&n<=4096,'Unsupported ICC placement/duplicate/bound');const separator=data.indexOf(0);assert(separator>=1&&separator<=79&&separator+2<data.length);const name=data.subarray(0,separator);assert(name[0]!==32&&name.at(-1)!==32&&!name.toString('latin1').includes('  ')&&[...name].every(v=>(v>=32&&v<=126)||v>=161));assert.equal(data[separator+1],0);const compressed=data.subarray(separator+2),decoded=inflateSync(compressed,{maxOutputLength:480,info:true});assert.equal(decoded.engine.bytesWritten,compressed.length,'No extra compressed ICC stream bytes');profile=decoded.buffer;}
  else if(type==='sRGB'){assert(seenHeader&&!seenData&&!profile&&!explicitSrgb&&n===1&&data[0]<=3);explicitSrgb=true;}
  else if(['gAMA','cHRM','cICP','mDCV','cLLI','sBIT','tRNS','acTL','fcTL','fdAT'].includes(type))assert.fail('Unsupported screenshot color/transparency/animation metadata');
  else if(type==='IDAT'){assert(seenHeader&&!dataEnded&&!ended);seenData=true;idatBytes+=n;assert(idatBytes<=4*1024*1024);idats.push(data);}
  else if(type==='IEND'){assert(seenHeader&&seenData&&!ended&&n===0&&offset+12===b.length);ended=true;}
  else{assert(seenHeader&&!ended);assert((b[offset+4]&32)!==0,'Unsupported critical PNG chunk');if(seenData)dataEnded=true;}
  offset+=n+12;
 }
 assert(ended);const color=expectedEmbeddingScreenshotColor(profile);if(explicitSrgb)color.encoding={kind:'explicit-srgb'};const stride=width*channels,expected=(stride+1)*height,raw=inflateSync(Buffer.concat(idats,idatBytes),{maxOutputLength:expected});assert.equal(raw.length,expected);let previous=Buffer.alloc(stride),current=Buffer.alloc(stride);const centerX=Math.floor(width/2),centerY=Math.floor(height/2),paeth=(a,b,c)=>{const p=a+b-c,da=Math.abs(p-a),db=Math.abs(p-b),dc=Math.abs(p-c);return da<=db&&da<=dc?a:db<=dc?b:c;};
 let pixel;for(let y=0;y<height;y++){const at=y*(stride+1),filter=raw[at];assert(filter<=4);for(let x=0;x<stride;x++){const left=x>=channels?current[x-channels]:0,up=previous[x],upperLeft=x>=channels?previous[x-channels]:0,predict=filter===0?0:filter===1?left:filter===2?up:filter===3?Math.floor((left+up)/2):paeth(left,up,upperLeft);current[x]=(raw[at+1+x]+predict)&255;}if(y===centerY){const at=centerX*channels;pixel=[current[at],current[at+1],current[at+2],channels===4?current[at+3]:255];}const swap=previous;previous=current;current=swap;}
 assert.deepEqual(pixel,color.expected,'Composed center must contain the exact authored color in the actual PNG encoding');return {width,height,bytes:b.length,sha256:createHash('sha256').update(b).digest('hex'),center:pixel,authoredCenter:[40,80,100,255],expectedEncodedCenter:color.expected,colorEncoding:color.encoding};
}
export async function observeEmbeddingComposedReady(canvas,{privatePngPath}={}){
 // Existing outer case deadline still owns all operations/cleanup. This extra
 // setup observation is additionally bounded by the existing ten-second size.
 let timer,retired=false;const current=()=>{if(retired)throw Error('Owned composed-pixel observation expired');};const work=Promise.resolve().then(async()=>{
  const before=qualifyEmbeddingCanvasState(await canvas.evaluate(readEmbeddingCanvasReady));current();
  const bytes=await canvas.screenshot({type:'png',scrollIntoView:false,captureBeyondViewport:false,fromSurface:true,omitBackground:false});current();if(privatePngPath!==undefined){await preservePrivateComposedPng(bytes,privatePngPath);current();}const composed=qualifyEmbeddingComposedPng(bytes);
  const after=qualifyEmbeddingCanvasState(await canvas.evaluate(readEmbeddingCanvasReady));current();assert.deepEqual(after,before,'No owner/frame/layout/native density change during composed-pixel qualification');
  return {kind:'public-composed-canvas-pixel',before,after,composed,hitTargetQualified:false};
 });void work.catch(()=>{});
 try{return await Promise.race([work,new Promise((_,reject)=>{timer=setTimeout(()=>{retired=true;reject(Error('Original bounded compositor-output setup deadline'));},10000);})]);}finally{retired=true;clearTimeout(timer);}
}
