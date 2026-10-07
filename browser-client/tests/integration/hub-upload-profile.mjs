// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Serialized directly by addInitScript: keep all dependencies inside function.
export function installHubUploadProfile(){
 const maximumRecords=1000000,maximumBucketsPerPhase=128,maximumSources=1024;
 const methods=new Set(['texImage2D','texSubImage2D','compressedTexImage2D','compressedTexSubImage2D']);
 const phases=['before-join','loading','steady','leaving','reloading','rejoined-ready'];
 let phase='before-join',records=0,droppedRecords=0,invalidDurations=0,unknownSignatures=0,sourceLimitReached=false;
 const seen=new WeakSet(),buckets=new Map(),phaseBucketCounts={},sourceCounts={image:0,bitmap:0,canvas:0,offscreen:0,video:0,imageData:0,videoFrame:0,data:0,unknown:0};
 let sources=0;
 const integer=(value,maximum=Number.MAX_SAFE_INTEGER)=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0&&value<=maximum;
 const scalar=value=>integer(value,65536)?value:null;
 const uint=value=>integer(value,0xffffffff),sizei=value=>integer(value,0x7fffffff);
 const size=(object,constructor,field)=>{const descriptor=Object.getOwnPropertyDescriptor(constructor.prototype,field);try{return descriptor?.get?scalar(Reflect.apply(descriptor.get,object,[])):null;}catch{return null;}};
 const classify=source=>{
  if(ArrayBuffer.isView(source))return{kind:'data',width:null,height:null};
  for(const [name,kind,width,height]of [['HTMLImageElement','image','naturalWidth','naturalHeight'],['ImageBitmap','bitmap','width','height'],['HTMLCanvasElement','canvas','width','height'],['OffscreenCanvas','offscreen','width','height'],['HTMLVideoElement','video','videoWidth','videoHeight'],['ImageData','imageData','width','height'],['VideoFrame','videoFrame','displayWidth','displayHeight']]){
   const Type=globalThis[name];if(typeof Type==='function'&&source instanceof Type)return{kind,width:size(source,Type,width),height:size(source,Type,height)};
  }
  return{kind:'unknown',width:null,height:null};
 };
 // Parse the exact WebGL1/WebGL2 2-D overload positions. A syntactically
 // recognized call is not proof that the GL accepted/transferred its pixels.
 // Never coerce foreign scalar values or inspect arbitrary object fields.
 const describe=(name,args)=>{
  const unknown={kind:'unknown',width:null,height:null,format:null,type:null,source:undefined,signatureKnown:false};
  if(!Array.isArray(args)||args.length<6||args.length>10)return unknown;
  const sub=name.includes('Sub'),compressed=name.startsWith('compressed');
  if(!uint(args[0])||!sizei(args[1]))return unknown;
  if(sub&&(!sizei(args[2])||!sizei(args[3])))return unknown;
  if(!sub&&!(compressed?uint(args[2]):sizei(args[2])))return unknown;
  const domLength=sub?7:6,sourceIndex=compressed?(sub?7:6):8;
  if(!compressed&&args.length===domLength){
   const formatIndex=sub?4:3;
   if(!uint(args[formatIndex])||!uint(args[formatIndex+1]))return unknown;
   const source=args[domLength-1],description=classify(source);
   if(description.kind==='data'||description.kind==='unknown')return unknown;
   return{...description,format:args[formatIndex],type:args[formatIndex+1],source,signatureKnown:true};
  }
  const dimensionOffset=sub?4:3,formatIndex=compressed?(sub?6:2):6;
  if(!sizei(args[dimensionOffset])||!sizei(args[dimensionOffset+1])||!uint(args[formatIndex]))return unknown;
  if(!sub&&args[5]!==0)return unknown;
  if(!compressed&&!uint(args[7]))return unknown;
  const source=args[sourceIndex];let description;
  if(compressed){
   // Compressed PBO overload: imageSize then byte offset, both numbers.
   if(args.length===sourceIndex+2&&sizei(source)&&integer(args[sourceIndex+1]))description={kind:'pbo'};
   else if(ArrayBuffer.isView(source)&&args.length>=sourceIndex+1&&args.length<=sourceIndex+3&&
    (args.length<sourceIndex+2||args[sourceIndex+1]===undefined||uint(args[sourceIndex+1]))&&
    (args.length<sourceIndex+3||args[sourceIndex+2]===undefined||uint(args[sourceIndex+2])))description={kind:'data'};
   else return unknown;
  }else if(args.length===9){
   if(integer(source))description={kind:'pbo'};
   else if(source===null)description={kind:'null-data'};
   else {description=classify(source);if(description.kind==='unknown')return unknown;}
  }else if(args.length===10&&ArrayBuffer.isView(source)&&uint(args[9]))description={kind:'data'};
  else return unknown;
  return{kind:description.kind,width:args[dimensionOffset],height:args[dimensionOffset+1],format:args[formatIndex],type:compressed?null:args[7],source:source&&typeof source==='object'?source:undefined,signatureKnown:true};
 };
 globalThis.__hubUploadProfile={
  setPhase(value){if(phases.includes(value))phase=value;},
  record(name,args,elapsed){
   if(!methods.has(name))return;
   if(records>=maximumRecords){droppedRecords=Math.min(maximumRecords,droppedRecords+1);return;}
   records++;
   const description=describe(name,args),{source,width,height,format,type}=description;
   if(!description.signatureKnown)unknownSignatures++;
   if(source&&typeof source==='object'&&!sourceLimitReached&&!seen.has(source)){
    if(sources>=maximumSources)sourceLimitReached=true;
    else{seen.add(source);sources++;sourceCounts[description.kind]++;}
   }
   const key=[phase,name,description.kind,scalar(Array.isArray(args)?args[1]:undefined),width,height,format,type].join('|');
   let bucket=buckets.get(key);
   if(!bucket){if((phaseBucketCounts[phase]||0)>=maximumBucketsPerPhase){droppedRecords++;return;}phaseBucketCounts[phase]=(phaseBucketCounts[phase]||0)+1;bucket={phase,method:name,kind:description.kind,mipLevel:scalar(Array.isArray(args)?args[1]:undefined),width,height,format,type,calls:0,totalMs:0,maxMs:0};buckets.set(key,bucket);}
   bucket.calls++;if(typeof elapsed==='number'&&Number.isFinite(elapsed)&&elapsed>=0&&elapsed<=60000){bucket.totalMs+=elapsed;bucket.maxMs=Math.max(bucket.maxMs,elapsed);}else invalidDurations++;
  },
  snapshot(){return{enabled:true,maximumRecords,maximumBucketsPerPhase,maximumTotalBuckets:maximumBucketsPerPhase*phases.length,maximumSources,records,droppedRecords,invalidDurations,unknownSignatures,sourceLimitReached,uniqueArgumentSourcesLowerBound:sources,uniqueArgumentSourcesByKind:{...sourceCounts},scope:'Observed existing upload calls and argument identities, not GPU residency, successful transfer proof, unique texture count or pure GPU time',buckets:[...buckets.values()].map(value=>({...value}))};}
 };
}
