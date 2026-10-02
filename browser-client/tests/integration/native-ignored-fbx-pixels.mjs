// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Root-owned real browser invocation. Run with node --import tsx after the
// dedicated production-worker build. Fixed authored source, no domain writes.
import {createServer} from 'vite';
import {chromium,firefox} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {fstTextureAdmissionFbx} from '../fixtures/fst-texture-admission.ts';
import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER||'system-chromium',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['chromium','firefox','system-chromium','system-firefox'].includes(engine));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const sourceFiles=['src/baked-fbx.ts','src/model-fbx-worker.ts','src/model-fbx-pool.ts','src/embedded-fbx-images.ts','src/embedded-fbx-protocol.ts','tests/fixtures/fst-texture-admission.ts','tests/fixtures/native-ignored-fbx-pixels.ts','tests/integration/native-ignored-fbx-pixels.mjs','tests/integration/system-firefox.mjs','vite.native-ignored-fbx.config.mjs','package-lock.json'];
async function hashes(){const result={};for(const file of sourceFiles)result[file]=digest(await readFile(path.join(client,file)));return result;}
const report={startedAt:new Date().toISOString(),completed:false,engine,scope:'Actual production preparation worker + FBXLoader pixel control on authored source; no native/public Hub or loading-gain claim',domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,modelRequests:0,unusedDDSRequests:0,sourceStart:await hashes()};
let server,browser,timer;
try{
 const bytes=new Uint8Array(fstTextureAdmissionFbx({embedded:true,ignoredDDS:true,ignoredSlot:'Maya|TEX_global_specular_cube'}));report.fixtureSHA256=digest(bytes);
 server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port:Number(process.env.OVERTE_IGNORED_FBX_FIXTURE_PORT||5193),strictPort:true},plugins:[{name:'owned-native-ignored-fbx',configureServer(vite){vite.middlewares.use((request,response,next)=>{
  const pathname=new URL(request.url||'/','http://127.0.0.1').pathname;if(!pathname.startsWith('/__native_ignored/')){next();return;}
  response.setHeader('Cache-Control','private, no-store');response.setHeader('X-Content-Type-Options','nosniff');
  if(request.method!=='GET'){response.statusCode=405;response.end();return;}
  if(pathname==='/__native_ignored/model.fbx'){report.modelRequests++;response.setHeader('Content-Type','application/octet-stream');response.setHeader('Content-Length',bytes.length);response.end(bytes);return;}
  if(pathname==='/__native_ignored/unused-a.dds'){report.unusedDDSRequests++;response.statusCode=404;response.setHeader('Content-Type','text/plain');response.end('Owned unused dependency negative control');return;}
  response.statusCode=403;response.end('Refused nonfixture source');
 });}}]});await server.listen();const address=server.httpServer.address();assert(address&&typeof address==='object');
 const env={...process.env,...(display?{DISPLAY:display}:{})};
 if(engine==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else if(engine==='firefox')browser=await firefox.launch({headless:!display,env});
 else {if(engine==='system-chromium')assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');browser=await chromium.launch({executablePath:engine==='system-chromium'?process.env.OVERTE_LAB_CHROMIUM:undefined,headless:!display,env:{...env,...(engine==='system-chromium'&&process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(String(error.message).slice(0,1024)));
 await page.goto(`http://127.0.0.1:${address.port}/tests/fixtures/native-ignored-fbx-pixels.html`);await page.waitForFunction(()=>typeof window.runNativeIgnoredFbxPixels==='function',undefined,{timeout:10000});
 report.pixels=await Promise.race([page.evaluate(()=>window.runNativeIgnoredFbxPixels()),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Native ignored FBX pixel fixture exceeded 30 seconds')),30000);timer.unref();})]);
 assert.equal(report.pixels.completed,true);assert.equal(report.modelRequests,1);assert.equal(report.unusedDDSRequests,1,'Only the original unpruned control may request its unused DDS');assert.deepEqual(errors,[]);report.completed=true;
}catch(error){report.error=String(error.message).slice(0,1024);process.exitCode=1;}
finally{
 clearTimeout(timer);await browser?.close();await server?.close();report.finishedAt=new Date().toISOString();report.sourceEnd=await hashes();report.sourceCoherent=JSON.stringify(report.sourceStart)===JSON.stringify(report.sourceEnd);if(!report.sourceCoherent){report.completed=false;process.exitCode=1;}
 report.bundleSHA256={};for(const name of await readdir(path.join(client,'build-native-ignored-fbx'),{recursive:true})){if(/\.js$/.test(name))report.bundleSHA256[name]=digest(await readFile(path.join(client,'build-native-ignored-fbx',name)));}
 const output=process.env.OVERTE_IGNORED_FBX_EVIDENCE||path.join(client,'build-native-ignored-fbx-evidence');await mkdir(output,{recursive:true,mode:0o700});await writeFile(path.join(output,`native-ignored-fbx-pixels-${engine}.json`),JSON.stringify(report,null,2)+'\n',{mode:0o600});console.log(JSON.stringify(report));
}
