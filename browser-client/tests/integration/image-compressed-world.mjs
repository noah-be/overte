// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual BrowserWorld Image entities on isolated controlled asset inputs. No domain is joined or changed.
import {createServer} from 'vite';
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash,randomBytes} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),repo=path.resolve(client,'..');
const root=process.env.OVERTE_KTX_AUDIT_ROOT||path.join(repo,'build/browser-hub-lab/hub');
const engine=process.env.OVERTE_LAB_BROWSER||'system-chromium',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['system-chromium','system-firefox'].includes(engine));
const fixtures=[
 {name:'opaque',asset:'shrub-bluepops-1a',png:'materialTextures/111/shrub-bluepops-D-768_2.png',pngSHA:'0087b3a3a9c9347b3a592db7b7e4f88fe333aedb7c6bd6aae48ed664c3f98739',ktxSHA:'665f2c22827bafda51eb0127b69cce6c5d33869a98ae7331b8aafa88985d89f6'},
 {name:'mask',asset:'shrub-jungle-leafy-1a',png:'materialTextures/1/foliage-1-D-512_2.png',pngSHA:'43d594a99f2b8d8412348a45b0556f4af8c1960ccbce0e2b3164c8fa61beba6c',ktxSHA:'8271f00457196483ecf617df4f644885d35e52fad010ad31b9bd35afe2cc5355'},
];
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const report={startedAt:new Date().toISOString(),completed:false,engine,domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,scope:'Original saved public Hub PNG and KTX on an owned isolated fixture server; genuine BrowserWorld Image renderer and approved native color-cache path; no domain/native framebuffer or whole-load speed claim',inputs:[]};
const sourceFiles=['tests/integration/image-compressed-world.mjs','tests/integration/system-firefox.mjs','tests/fixtures/image-compressed-world.ts','src/world.ts','src/native-compressed-color.ts','src/native-alpha-material.ts','src/native-render-state.ts','src/world-image-cache.ts','src/world-source-text-cache.ts','shared/native-ktx.mjs'];
async function sourceHashes(){return Object.fromEntries(await Promise.all(sourceFiles.map(async name=>[name,digest(await readFile(path.join(client,name)))])));}
let server,browser;
try {
 report.startSourceSHA256=await sourceHashes();
 await mkdir(root,{recursive:true});const assets=new Map();
 for(const fixture of fixtures){
  const pngFile=path.join(root,`compressed-fixture-${fixture.name}.png`);let png;
  try{png=await readFile(pngFile);}catch(error){
   if(error.code!=='ENOENT')throw error;
   const response=await fetch(`https://content.overte.org/Bazaar/Worlds/HQ_HiFi/content/${fixture.asset}/baked/${fixture.png}`,{redirect:'error',signal:AbortSignal.timeout(30000)});
   assert(response.ok,'The fixed public original PNG is unavailable');assert(Number(response.headers.get('content-length')||0)<=4*1024*1024,'Original image exceeds fixture byte bound');
   const reader=response.body.getReader(),chunks=[];let bytes=0;try{while(true){const next=await reader.read();if(next.done)break;bytes+=next.value.byteLength;assert(bytes<=4*1024*1024,'Original image exceeds fixture byte bound');chunks.push(next.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   png=Buffer.concat(chunks);assert.equal(digest(png),fixture.pngSHA,'The fixed original public PNG changed');await writeFile(pngFile,png,{mode:0o600,flag:'wx'});
  }
  const ktx=await readFile(path.join(root,`${fixture.asset}.ktx`));assert.equal(digest(png),fixture.pngSHA);assert.equal(digest(ktx),fixture.ktxSHA);
  assets.set(`fixture:${fixture.name}.png`,{bytes:png,type:'image/png'});assets.set(`fixture:${fixture.name}.ktx`,{bytes:ktx,type:'image/ktx'});
  report.inputs.push({name:fixture.name,pngSHA256:digest(png),pngBytes:png.length,ktxSHA256:digest(ktx),ktxBytes:ktx.length});
 }
  for(const fixture of fixtures){
  const base='https://image-fixture.invalid/';
  assets.set(base+fixture.name+'.png',assets.get(`fixture:${fixture.name}.png`));assets.set(base+fixture.name+'.ktx',assets.get(`fixture:${fixture.name}.ktx`));
  const compressedName=fixture.name==='opaque'?'COMPRESSED_SRGB_S3TC_DXT1_EXT':'COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT';
  assets.set(base+fixture.name+'.texmeta.json',{bytes:Buffer.from(JSON.stringify({version:1,original:fixture.name+'.png',compressed:{[compressedName]:fixture.name+'.ktx'}})),type:'application/json'});
  assets.set(base+fixture.name+'-original.texmeta.json',{bytes:Buffer.from(JSON.stringify({version:1,original:fixture.name+'.png',compressed:{COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:'not-selected.ktx'}})),type:'application/json'});
 }
 const base='https://image-fixture.invalid/';assets.set(base+'delayed.texmeta.json',{bytes:Buffer.from(JSON.stringify({version:1,original:'mask.png',compressed:{COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT:'delayed.ktx'}})),type:'application/json'});assets.set(base+'delayed.ktx',{...assets.get('fixture:mask.ktx'),delay:300});
 const token=randomBytes(32).toString('hex');
 server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port:Number(process.env.OVERTE_IMAGE_COLOR_FIXTURE_PORT||5197),strictPort:true},plugins:[{name:'fixed-image-world-fixture',configureServer(vite){vite.middlewares.use((request,response,next)=>{
  const address=new URL(request.url||'/',`http://127.0.0.1`);
  if(address.pathname==='/__image-fixture/bootstrap'){response.setHeader('Set-Cookie',`image-fixture=${token}; HttpOnly; SameSite=Strict; Path=/`);response.end('ready');return;}
  if(address.pathname!=='/api/assets/image-fixture'){next();return;}
  if(request.method!=='GET'||!(request.headers.cookie||'').split(';').map(s=>s.trim()).includes(`image-fixture=${token}`)||address.searchParams.size!==1){response.statusCode=403;response.end();return;}
  const asset=assets.get(address.searchParams.get('url'));if(!asset){response.statusCode=404;response.end();return;}
  response.setHeader('Content-Type',asset.type);response.setHeader('Content-Length',asset.bytes.length);response.setHeader('Cache-Control','private, no-store');response.setHeader('X-Content-Type-Options','nosniff');if(asset.delay){const timer=setTimeout(()=>{if(!response.destroyed)response.end(asset.bytes);},asset.delay);response.once('close',()=>clearTimeout(timer));}else response.end(asset.bytes);
 });}}]});
 await server.listen();const address=server.httpServer.address();assert(address&&typeof address==='object');
 const env={...process.env,...(display?{DISPLAY:display}:{})};
 if(engine==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else {assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');browser=await chromium.launch({executablePath:process.env.OVERTE_LAB_CHROMIUM,headless:!display,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();
 const errors=[];page.on('pageerror',error=>errors.push(String(error.message).slice(0,1024)));
 await page.goto(`http://127.0.0.1:${address.port}/tests/fixtures/image-compressed-world.html`);await page.waitForFunction(()=>typeof window.runImageCompressedWorldFixture==='function',undefined,{timeout:10000});
 report.gpu=await page.evaluate(()=>window.runImageCompressedWorldFixture());assert.equal(report.gpu.completed,true);assert.deepEqual(errors,[]);report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{
 await browser?.close();await server?.close();report.finishedAt=new Date().toISOString();report.sourceSHA256=await sourceHashes();
 report.sourceCoherent=JSON.stringify(report.sourceSHA256)===JSON.stringify(report.startSourceSHA256);if(!report.sourceCoherent){report.completed=false;report.error=report.error||'Source changed during the actual Image pixel proof';process.exitCode=1;}
 const output=path.join(repo,'build/browser-hub-lab/evidence');await mkdir(output,{recursive:true});await writeFile(path.join(output,`image-compressed-world-${engine}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
