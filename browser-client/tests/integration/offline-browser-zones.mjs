// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual browser decoder/lifecycle proof without a listener or external network.
// This does not exercise WebGL, native ambient shading, or a real Overte domain.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {resolve,relative,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {deflateSync} from 'node:zlib';
import {firefox} from '@playwright/test';
const client=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const argument=name=>{const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];};
const bundle=resolve(argument('--bundle')||process.env.OVERTE_OFFLINE_ZONES_BUNDLE||resolve(client,'build/offline-zone-fixture'));
const entry=argument('--entry')||process.env.OVERTE_OFFLINE_ZONES_ENTRY||'zones.js';
if(entry.includes('..')||entry.startsWith('/')||!/\.m?js$/.test(entry))throw Error('The offline Zone entry must be a relative JavaScript bundle path.');
const output=resolve(argument('--report')||process.env.OVERTE_OFFLINE_ZONES_REPORT||resolve(client,'build/offline-zone-evidence.json'));
const executablePath=argument('--firefox')||process.env.OVERTE_OFFLINE_FIREFOX;
const origin='https://zone-proof.invalid';
const startedAt=new Date().toISOString(),cases=[],routeCounts=new Map(),routedFiles=new Map();
async function collect(directory){
  for(const item of await readdir(directory,{withFileTypes:true})){
    if(item.isSymbolicLink())throw Error('Offline fixture bundles must not contain symlinks.');
    const path=resolve(directory,item.name);
    if(item.isDirectory())await collect(path);
    else if(item.isFile()&&/\.(js|mjs)$/.test(item.name))routedFiles.set('/'+relative(bundle,path).replaceAll('\\','/'),await readFile(path));
  }
}
await collect(bundle);assert(routedFiles.has('/'+entry),'Root-built exact bundle entry must exist.');
function tga(width,height){const result=Buffer.alloc(18+width*height*3);result[2]=2;result.writeUInt16LE(width,12);result.writeUInt16LE(height,14);result[16]=24;result[17]=32;for(let index=18;index<result.length;index+=3)result.set([32,64,128],index);return result;}
function hdr(width,height){
  assert(width>=8&&width<=32767);
  const header=Buffer.from(`#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y ${height} +X ${width}\n`),parts=[header];
  for(let row=0;row<height;row++){
    parts.push(Buffer.from([2,2,width>>8,width&255]));
    for(const value of [128,64,32,129])for(let remaining=width;remaining>0;){const run=Math.min(127,remaining);parts.push(Buffer.from([128+run,value]));remaining-=run;}
  }
  return Buffer.concat(parts);
}
function crc32(bytes){let value=0xffffffff;for(const byte of bytes){value^=byte;for(let bit=0;bit<8;bit++)value=(value>>>1)^((value&1)?0xedb88320:0);}return (value^0xffffffff)>>>0;}
function chunk(type,bytes){const name=Buffer.from(type),length=Buffer.alloc(4),checksum=Buffer.alloc(4);length.writeUInt32BE(bytes.length);checksum.writeUInt32BE(crc32(Buffer.concat([name,bytes])));return Buffer.concat([length,name,bytes,checksum]);}
const pngHeader=Buffer.alloc(13);pngHeader.writeUInt32BE(2);pngHeader.writeUInt32BE(1,4);pngHeader[8]=8;pngHeader[9]=6;
const png=Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',pngHeader),chunk('IDAT',deflateSync(Buffer.from([0,255,0,0,255,0,255,0,255]))),chunk('IEND',Buffer.alloc(0))]);
const assetRoutes=new Map([
  ['/assets/panorama.png',{body:png,type:'image/png'}],
  ['/assets/sky-strip.tga',{body:tga(1,6),type:'image/x-tga'}],
  ['/assets/actual.texmeta.json',{body:Buffer.from(JSON.stringify({original:'sky-strip.tga'})),type:'application/json'}],
]);
const browser=await firefox.launch({headless:true,timeout:15000,...executablePath?{executablePath}:{}});
const browserVersion=browser.version();
let context,report;
try{
  context=await browser.newContext();const page=await context.newPage();const pageErrors=[];
  page.on('pageerror',error=>pageErrors.push(error.message.slice(0,512)));
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==origin){await route.abort();throw Error('The offline Zone proof attempted an unexpected network origin.');}
    routeCounts.set(url.pathname,(routeCounts.get(url.pathname)||0)+1);
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><title>Offline native Zone decoder proof</title>',headers:{'content-security-policy':"default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:"}});
    if(url.pathname==='/assets/slow.tga'){
      // A real browser fetch stays pending until AbortSignal cancels it. A late
      // response cannot resurrect the load; no local HTTP server is involved.
      await new Promise(resolve=>setTimeout(resolve,250));
      try{await route.fulfill({body:tga(2,1),contentType:'image/x-tga'});}catch{/* cancelled browser request */}return;
    }
    const asset=assetRoutes.get(url.pathname);if(asset)return route.fulfill({body:asset.body,contentType:asset.type});
    const file=routedFiles.get(url.pathname);if(file)return route.fulfill({body:file,contentType:'text/javascript'});
    await route.abort();throw Error('The offline Zone proof requested a file absent from its exact fixture bundle.');
  });
  await page.goto(origin+'/');
  await page.evaluate(async entry=>{
    window.zoneModule=await import(entry);
    window.zoneProof={workerCreated:0,workerMessages:0,workerTerminated:0,bitmapClosed:0};
    const NativeWorker=window.Worker;
    // Delegate every operation to the actual Firefox Worker. Instrumentation
    // counts lifecycle events; it does not substitute decoding or responses.
    window.Worker=class extends NativeWorker{
      constructor(...args){super(...args);window.zoneProof.workerCreated++;this.addEventListener('message',()=>window.zoneProof.workerMessages++);}
      terminate(){window.zoneProof.workerTerminated++;return super.terminate();}
    };
    const close=ImageBitmap.prototype.close;ImageBitmap.prototype.close=function(){window.zoneProof.bitmapClosed++;return close.call(this);};
  },origin+'/'+entry);
  async function run(name,operation,expected){
    const started=Date.now(),result=await operation();expected(result);
    cases.push({name,passed:true,elapsedMs:Date.now()-started,result});
  }
  await run('actual large TGA worker pixels',()=>page.evaluate(async bytes=>{
    const before={...window.zoneProof},buffer=new Uint8Array(bytes).buffer;
    const image=await window.zoneModule.decodeNativeSkyBounded('tga',buffer,new AbortController().signal);
    return {width:image.width,height:image.height,pixel:[...image.data.slice(0,4)],transferredBytes:buffer.byteLength,created:window.zoneProof.workerCreated-before.workerCreated,messages:window.zoneProof.workerMessages-before.workerMessages,terminated:window.zoneProof.workerTerminated-before.workerTerminated};
  },[...tga(512,256)]),result=>{assert.deepEqual(result,{width:512,height:256,pixel:[128,64,32,255],transferredBytes:0,created:1,messages:1,terminated:1});});
  await run('actual compressed HDR worker linear pixels',()=>page.evaluate(async bytes=>{
    const before={...window.zoneProof},buffer=new Uint8Array(bytes).buffer;
    const image=await window.zoneModule.decodeNativeSkyBounded('hdr',buffer,new AbortController().signal);
    const half=value=>{const sign=(value&0x8000)?-1:1,exponent=(value>>10)&31,mantissa=value&1023;return sign*(exponent===0?mantissa*2**-24:exponent===31?(mantissa?NaN:Infinity):(1+mantissa/1024)*2**(exponent-15));};
    return {width:image.width,height:image.height,pixel:[...image.data.slice(0,4)].map(half),transferredBytes:buffer.byteLength,created:window.zoneProof.workerCreated-before.workerCreated,messages:window.zoneProof.workerMessages-before.workerMessages,terminated:window.zoneProof.workerTerminated-before.workerTerminated};
  },[...hdr(512,256)]),result=>{assert.equal(result.width,512);assert.equal(result.height,256);for(const [index,expected] of [256/255,128/255,64/255,1].entries())assert(Math.abs(result.pixel[index]-expected)<.001);assert.equal(result.transferredBytes,0);assert.equal(result.created,1);assert.equal(result.messages,1);assert.equal(result.terminated,1);});
  await run('actual worker cancellation',()=>page.evaluate(async bytes=>{
    const before={...window.zoneProof},controller=new AbortController();
    const pending=window.zoneModule.decodeNativeSkyBounded('tga',new Uint8Array(bytes).buffer,controller.signal);controller.abort(new Error('authority revoked'));
    let error='';try{await pending;}catch(value){error=value.message;}
    return {error,created:window.zoneProof.workerCreated-before.workerCreated,terminated:window.zoneProof.workerTerminated-before.workerTerminated};
  },[...tga(512,256)]),result=>{assert.match(result.error,/authority revoked/);assert.equal(result.created,1);assert.equal(result.terminated,1);});
  const invalid=tga(512,256).subarray(0,18);invalid[2]=0;
  await run('actual worker decoder failure',()=>page.evaluate(async bytes=>{
    const before={...window.zoneProof};let error='';try{await window.zoneModule.decodeNativeSkyBounded('tga',new Uint8Array(bytes).buffer,new AbortController().signal);}catch(value){error=value.message;}
    return {error,created:window.zoneProof.workerCreated-before.workerCreated,terminated:window.zoneProof.workerTerminated-before.workerTerminated};
  },[...invalid]),result=>{assert.match(result.error,/TGA|tga|type|data/i);assert.equal(result.created,1);assert.equal(result.terminated,1);});
  await run('actual PNG ImageBitmap closes on owned texture disposal',()=>page.evaluate(async()=>{
    const before=window.zoneProof.bitmapClosed,texture=await window.zoneModule.loadNativeSkyTexture('atp:/panorama.png',()=>'/assets/panorama.png');
    const dimensions={width:texture.image.width,height:texture.image.height};texture.dispose();return {...dimensions,closed:window.zoneProof.bitmapClosed-before};
  }),result=>assert.deepEqual(result,{width:2,height:1,closed:1}));
  await run('ATP-relative texmeta and actual TGA cube face disposal',()=>page.evaluate(async()=>{
    const paths=[],texture=await window.zoneModule.loadNativeSkyTexture('atp:/actual.texmeta.json',source=>{paths.push(source);return '/assets/'+source.slice(5);});
    let disposed=0;const pixels=texture.images.map(face=>{face.addEventListener('dispose',()=>disposed++);return [...face.image.data.slice(0,4)];});texture.dispose();
    return {paths,cube:!!texture.isCubeTexture,pixels,disposed};
  }),result=>{assert.deepEqual(result.paths,['atp:/actual.texmeta.json','atp:/sky-strip.tga']);assert.equal(result.cube,true);assert.equal(result.disposed,6);assert.deepEqual(result.pixels,Array.from({length:6},()=>[128,64,32,255]));});
  await run('actual browser fetch deadline and explicit revocation',()=>page.evaluate(async()=>{
    let deadline='',cancel='';const start=performance.now();
    try{await window.zoneModule.loadNativeSkyTexture('atp:/slow.tga',()=>'/assets/slow.tga',{timeoutMs:40});}catch(value){deadline=value.message;}
    const elapsed=performance.now()-start,controller=new AbortController(),pending=window.zoneModule.loadNativeSkyTexture('atp:/slow.tga',()=>'/assets/slow.tga',{signal:controller.signal});controller.abort(new Error('session closed'));
    try{await pending;}catch(value){cancel=value.message;}
    return {deadline,cancel,elapsedMs:elapsed};
  }),result=>{assert.match(result.deadline,/deadline/);assert.match(result.cancel,/session closed/);assert(result.elapsedMs<1000);});
  assert.deepEqual(pageErrors,[],'Actual browser primitive tests must not produce uncaught page errors.');
  const capabilities=await page.evaluate(()=>({worker:typeof Worker==='function',imageBitmap:typeof createImageBitmap==='function',abortSignal:typeof AbortController==='function',webgl2Available:!!document.createElement('canvas').getContext('webgl2')}));
  const sourceFiles=['src/zone-effects.ts','src/zone-texture-worker.ts','tests/integration/offline-browser-zones.mjs'];
  const sources={};for(const file of sourceFiles)sources[file]=createHash('sha256').update(await readFile(resolve(client,file))).digest('hex');
  const bundles={};for(const [name,bytes] of routedFiles)bundles[name.slice(1)]=createHash('sha256').update(bytes).digest('hex');
  report={startedAt,finishedAt:new Date().toISOString(),browser:{engine:'Firefox',version:browserVersion,headless:true},scope:{actualBrowserPrimitives:true,webglTested:false,nativeDomainTested:false,ambientParityProved:false,httpListener:false,externalNetwork:false},capabilities,sources,bundles,passedCases:cases.length,cases,routes:Object.fromEntries(routeCounts),uncaughtPageErrors:pageErrors.length};
}finally{await context?.close();await browser.close();}
await mkdir(dirname(output),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');
process.stdout.write(JSON.stringify({passedCases:report.passedCases,browser:report.browser,scope:report.scope})+'\n');
