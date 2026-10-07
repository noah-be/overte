// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owned, isolated browser contexts; no domain, network assets, microphone or scene writes.
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const engine=process.env.OVERTE_LAB_BROWSER||'system-chromium',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['system-chromium','system-firefox'].includes(engine),'Capability proof requires an explicitly selected stock browser');
const report={startedAt:new Date().toISOString(),completed:false,engine,scope:'Actual stock-engine WebGL2 compressed texture capabilities only',domainConnected:false,microphoneRequested:false,worldInteractionsSent:0};
let browser;
try {
 const env={...process.env,...(display?{DISPLAY:display}:{})};
 if(engine==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else {
  assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');
  browser=await chromium.launch({executablePath:process.env.OVERTE_LAB_CHROMIUM,headless:!display,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});
 }
 report.browserVersion=await browser.version();
 const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();
 report.capabilities=await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=canvas.height=16;document.body.append(canvas);
  const gl=canvas.getContext('webgl2');if(!gl)return {webgl2:false};
  try {
   const names=gl.getSupportedExtensions()||[];if(names.length>128||names.some(s=>s.length>128))throw Error('Unexpected extension inventory bounds');
   const linear=gl.getExtension('WEBGL_compressed_texture_s3tc'),srgb=gl.getExtension('WEBGL_compressed_texture_s3tc_srgb');
   const select=(ext,fields)=>ext?Object.fromEntries(fields.map(name=>[name,Number(ext[name])])):null;
   const debug=gl.getExtension('WEBGL_debug_renderer_info');
   return {webgl2:true,supportedExtensions:names.sort(),s3tc:select(linear,['COMPRESSED_RGB_S3TC_DXT1_EXT','COMPRESSED_RGBA_S3TC_DXT1_EXT','COMPRESSED_RGBA_S3TC_DXT3_EXT','COMPRESSED_RGBA_S3TC_DXT5_EXT']),s3tcSRGB:select(srgb,['COMPRESSED_SRGB_S3TC_DXT1_EXT','COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT','COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT','COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT']),compressedTextureFormats:Array.from(gl.getParameter(gl.COMPRESSED_TEXTURE_FORMATS)),maximumTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE),vendor:String(gl.getParameter(debug?debug.UNMASKED_VENDOR_WEBGL:gl.VENDOR)),renderer:String(gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER)),contextAttributes:gl.getContextAttributes(),devicePixelRatio:window.devicePixelRatio};
  }finally{gl.getExtension('WEBGL_lose_context')?.loseContext();canvas.remove();}
 });
 assert.equal(report.capabilities.webgl2,true,'Actual WebGL2 is required; a missing context is not a compression capability pass');
 report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{
 await browser?.close();report.finishedAt=new Date().toISOString();report.sourceSHA256={};
 for(const file of ['browser-client/tests/integration/texture-capabilities.mjs','browser-client/tests/integration/system-firefox.mjs'])report.sourceSHA256[file]=createHash('sha256').update(await readFile(path.join(repo,file))).digest('hex');
 const output=path.join(repo,'build/browser-hub-lab/evidence');await mkdir(output,{recursive:true});await writeFile(path.join(output,`texture-capabilities-${engine}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
