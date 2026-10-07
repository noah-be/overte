// SPDX-License-Identifier: Apache-2.0
// Read-only public asset audit: no domain admission, microphone or world edits.
import { chromium, firefox } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..'), origin='http://127.0.0.1:5187';
const output=path.join(repo,'build/browser-hub-lab/texture-alpha'), useFirefox=process.env.OVERTE_LAB_BROWSER==='firefox',systemFirefox=process.env.OVERTE_LAB_BROWSER==='system-firefox';
const report={startedAt:new Date().toISOString(),completed:false,domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,assets:[]};
let browser,vite;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
async function download(url) {
  assert.equal(new URL(url).origin,'https://content.overte.org');
  const response=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(15000)});assert.equal(response.status,200);
  const chunks=[];let size=0;for await(const chunk of response.body){size+=chunk.length;assert(size<=10*1024*1024,'Actual texture audit resource exceeds10MiB');chunks.push(chunk);}return Buffer.concat(chunks,size);
}
function nativeUsage(bytes) {
  assert(bytes.subarray(0,12).equals(Buffer.from([171,75,84,88,32,49,49,187,13,10,26,10])));assert.equal(bytes.readUInt32LE(12),0x04030201);
  const end=64+bytes.readUInt32LE(60);assert(end<=bytes.length);
  for(let at=64;at<end;){const length=bytes.readUInt32LE(at);at+=4;assert(at+length<=end);const value=bytes.subarray(at,at+length);at+=Math.ceil(length/4)*4;const zero=value.indexOf(0);if(value.subarray(0,zero).toString()!=='hifi.gpu')continue;
    const payload=value.subarray(zero+1);assert([36,44].includes(payload.length));assert(payload[0]<=2);
    // GPUKTXPayload: version1byte + serialized Sampler::Desc28bytes + usage uint32.
    const flags=payload.readUInt32LE(29);assert(flags<=15);return{flags,mode:(flags&4)?((flags&8)?'mask':'blend'):'opaque',internalFormat:bytes.readUInt32LE(28)};
  }throw Error('Actual native KTX lacks hifi.gpu usage metadata');
}
try {
  try{await fetch(origin,{signal:AbortSignal.timeout(300)});throw Error('Refusing occupied alpha audit port');}catch(error){if(error.message==='Refusing occupied alpha audit port')throw error;}
  await mkdir(output,{recursive:true});
  const fixture=path.join(repo,'browser-client/build/native-texture-alpha/index.html');
  await mkdir(path.dirname(fixture),{recursive:true});await writeFile(fixture,'<!doctype html><html><body></body></html>');
  vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5187','--strictPort'],{cwd:path.join(repo,'browser-client'),stdio:'ignore'});
  for(let i=0;i<50;i++){try{if((await fetch(origin)).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  const display=process.env.OVERTE_LAB_BROWSER_DISPLAY,browserEnv={...process.env,...(display?{DISPLAY:display}: {})};
  if(systemFirefox){
    const {default:puppeteer}=await import('puppeteer-core');
    browser=await puppeteer.launch({browser:'firefox',protocol:'webDriverBiDi',executablePath:'/usr/bin/firefox',headless:!display,env:browserEnv});
  }else if(useFirefox){
    browser=await firefox.launch({headless:true,env:{...browserEnv,LIBGL_ALWAYS_SOFTWARE:'1',MOZ_WEBRENDER_SOFTWARE:'1'},firefoxUserPrefs:{'webgl.force-enabled':true}});
  }else{
    const options={headless:!display,env:browserEnv,args:[...(display?[]:['--use-angle=swiftshader']),'--disable-dev-shm-usage','--mute-audio']};
    if(process.env.OVERTE_LAB_CHROMIUM)options.executablePath=path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM);
    if(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)options.env={...browserEnv,LD_LIBRARY_PATH:path.resolve(repo,process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)};
    browser=await chromium.launch(options);
  }
  report.browserVersion=await browser.version();report.browserEngine=systemFirefox?'stock-firefox':useFirefox?'playwright-firefox':process.env.OVERTE_LAB_CHROMIUM?'stock-chromium':'playwright-chromium';
  const page=await browser.newPage();await page.goto(origin+'/build/native-texture-alpha/index.html');
  report.graphics=await page.evaluate(()=>{const canvas=document.createElement('canvas'),gl=canvas.getContext('webgl2');if(!gl)return {webgl2:false};const debug=gl.getExtension('WEBGL_debug_renderer_info'),result={webgl2:true,renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),vendor:debug?gl.getParameter(debug.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR)};gl.getExtension('WEBGL_lose_context')?.loseContext();return result;});
  assert.equal(report.graphics.webgl2,true,'This pixel comparison requires an actual WebGL2 context');
  for(const asset of ['shrub-jungle-leafy-1a','tree-banana-GB','shrub-bluepops-1a']) {
    const base=`https://content.overte.org/Bazaar/Worlds/HQ_HiFi/content/${asset}/baked/`;
    const materialBytes=await download(base+asset+'.baked.json');const material=JSON.parse(materialBytes).materials;assert(!Array.isArray(material));
    const metadataURL=new URL(material.albedoMap,base);const metadataBytes=await download(metadataURL);const metadata=JSON.parse(metadataBytes);
    const png=await download(new URL(metadata.original,metadataURL));const compressed=Object.entries(metadata.compressed).find(([format])=>format.includes('DXT'));assert(compressed);
    const ktx=await download(new URL(compressed[1],metadataURL));const usage=nativeUsage(ktx);
    // Feed the exact downloaded PNG bytes through a data URL in both engines;
    // stock Firefox does not require a patched route or browser API adapter.
    const imagePath='data:image/png;base64,'+png.toString('base64');
    const counts=await page.evaluate(async imagePath=>{const image=new Image();image.src=imagePath;await image.decode();const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;const ctx=c.getContext('2d');ctx.drawImage(image,0,0);const bytes=ctx.getImageData(0,0,c.width,c.height).data;let opaque=0,transparent=0,intermediate=0;for(let i=3;i<bytes.length;i+=4){if(bytes[i]===255)opaque++;else if(bytes[i]===0)transparent++;else intermediate++;}return{width:c.width,height:c.height,opaque,transparent,intermediate};},imagePath);
    const pixels=asset==='shrub-jungle-leafy-1a'?await page.evaluate(async imagePath=>{const modulePath='/tests/texture-alpha-fixture.ts';return(await import(modulePath)).auditAlphaPixels(imagePath);},imagePath):null;
    const expected=counts.opaque===counts.width*counts.height?'opaque':counts.intermediate<=Math.floor(.05*counts.width*counts.height)?'mask':'blend';assert.equal(expected,usage.mode);
    if(pixels){assert.equal(pixels.alpha,'mask');assert.equal(counts.transparent,86224);assert.equal(pixels.before.background,0);assert.equal(pixels.after.background,86224);}
    report.assets.push({asset,materialSHA256:hash(materialBytes),metadataSHA256:hash(metadataBytes),originalPNG_SHA256:hash(png),nativeKTX_SHA256:hash(ktx),nativeUsage:usage,rgba:counts,pixels});
  }
  report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally {
  await browser?.close();if(vite){vite.kill('SIGTERM');await new Promise(resolve=>vite.exitCode!==null?resolve():vite.once('exit',resolve));}
  report.finishedAt=new Date().toISOString();report.sourceSHA256={};for(const file of ['browser-client/src/texture-alpha.ts','browser-client/src/texture-alpha-worker.ts'])report.sourceSHA256[file]=hash(await readFile(path.join(repo,file)));
  await mkdir(output,{recursive:true});await writeFile(path.join(output,systemFirefox?'native-texture-alpha-system-firefox.json':useFirefox?'native-texture-alpha-firefox.json':process.env.OVERTE_LAB_CHROMIUM?'native-texture-alpha-stock-chromium.json':'native-texture-alpha-chromium.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
