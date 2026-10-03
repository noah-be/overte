import {googleChromeLaunchOptions} from '../google-chrome-selection.mjs';
// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Controlled authored fixture; no domain connection, account or microphone.
import {createServer} from 'vite';
import {chromium,firefox} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
// BEGIN strict fixed-field diagnostic consumer.
function validateEmbeddedDiagnostic(value){
 assert(value&&typeof value==='object'&&!Array.isArray(value));
 assert.deepEqual(Object.keys(value).sort(),['decodedRGBA','frames','phase','version']);assert.equal(value.version,1);
 assert(['model-await','gpu-loop','gpu-upload-check','post-gpu-resources','model-cancellation','complete'].includes(value.phase));
 assert(Array.isArray(value.decodedRGBA)&&[0,4].includes(value.decodedRGBA.length));
 assert(value.decodedRGBA.every(n=>Number.isInteger(n)&&n>=0&&n<=255));assert(Array.isArray(value.frames)&&value.frames.length<=20);
 for(let i=0;i<value.frames.length;i++){const row=value.frames[i];assert(Array.isArray(row)&&row.length===11);assert.equal(row[0],i);
  for(let j=1;j<5;j++)assert(Number.isInteger(row[j])&&row[j]>=0&&row[j]<=255);
  for(let j=5;j<11;j++)assert(Number.isSafeInteger(row[j])&&row[j]>=0&&row[j]<=1000000);
 }
 return value;
}
async function boundedEmbeddedDiagnosticRead(read){
 let timer;
 try{return await Promise.race([Promise.resolve().then(read),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('bounded-diagnostic-unavailable')),500);})]);}
 finally{clearTimeout(timer);}
}
async function collectEmbeddedFailureDiagnostic(page,primaryMessage){
 if(primaryMessage==='Embedded World fixture exceeded 30 seconds')return {pixelDiagnosticRefusal:'original-fixture-deadline'};
 try{return {pixelDiagnostic:validateEmbeddedDiagnostic(await boundedEmbeddedDiagnosticRead(()=>page?.evaluate(()=>window.__embeddedWorldDiagnostic)))};}
 catch{return {pixelDiagnosticRefusal:'unavailable-or-invalid'};}
}
// END strict fixed-field diagnostic consumer.
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER||'chrome',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['chrome','chromium','firefox','system-chromium','system-firefox'].includes(engine));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const report={startedAt:new Date().toISOString(),completed:false,engine,domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,scope:'Actual BrowserWorld.loadModel, production-built worker and ordinary embedded PNG fixture; no public/native whole-world or speed claim',requests:0};
let server,browser,page;
try{
 const {embeddedFbx}=await import('../../build-embedded/entry.js'),bytes=new Uint8Array(embeddedFbx());report.assetSHA256=digest(bytes);
 server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port:Number(process.env.OVERTE_EMBEDDED_FIXTURE_PORT||5192),strictPort:true},plugins:[{name:'owned-embedded-world',configureServer(vite){vite.middlewares.use((request,response,next)=>{
  if(new URL(request.url||'/', 'http://127.0.0.1').pathname!=='/__embedded/model.fbx'){next();return;}
  if(request.method!=='GET'){response.statusCode=405;response.end();return;}
  report.requests++;response.setHeader('Content-Type','application/octet-stream');response.setHeader('Content-Length',bytes.length);response.setHeader('Cache-Control','private, no-store');response.setHeader('X-Content-Type-Options','nosniff');response.end(bytes);
 });}}]});await server.listen();const address=server.httpServer.address();assert(address&&typeof address==='object');
 const env={...process.env,...(display?{DISPLAY:display}:{})};
 if(engine==='chrome')delete env.LD_LIBRARY_PATH;
 if(engine==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else if(engine==='firefox')browser=await firefox.launch({headless:!display,env});
 else {if(engine==='system-chromium')assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');browser=await chromium.launch({...(engine==='chrome'?googleChromeLaunchOptions():{}),...(engine==='system-chromium'?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{}),headless:!display,env:{...env,...(engine==='system-chromium'&&process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}}),errors=[];page=await context.newPage();
 page.on('pageerror',error=>errors.push(String(error.message).slice(0,1024)));
 await page.goto(`http://127.0.0.1:${address.port}/tests/fixtures/embedded-world.html`);await page.waitForFunction(()=>typeof window.runEmbeddedWorldFixture==='function',undefined,{timeout:10000});
 // The existing 30-second model texture/worker deadlines are unchanged. This
 // outer fixture bound allows owned cleanup without changing either gate.
 report.world=await Promise.race([page.evaluate(()=>window.runEmbeddedWorldFixture()),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('Embedded World fixture exceeded 30 seconds')),30000);timer.unref();})]);
 assert.equal(report.world.completed,true);assert.equal(report.requests,1,'Actual prepared cache must avoid duplicate upstream model fetches');assert.deepEqual(errors,[]);report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;
 Object.assign(report,await collectEmbeddedFailureDiagnostic(page,report.error));
}
finally{
 await browser?.close();await server?.close();report.finishedAt=new Date().toISOString();report.sourceSHA256={};
 for(const name of ['tests/google-chrome-selection.mjs','tests/integration/embedded-world.mjs','tests/fixtures/embedded-world.ts','vite.embedded-world.config.mjs','package-lock.json','src/world.ts','src/baked-fbx.ts','src/model-fbx-worker.ts','src/model-fbx-pool.ts','src/prepared-fbx-cache.ts','src/embedded-fbx-images.ts','src/embedded-fbx-protocol.ts','src/world-image-cache.ts'])report.sourceSHA256[name]=digest(await readFile(path.join(client,name)));
 report.bundleSHA256={};for(const name of await readdir(path.join(client,'build-embedded-world'),{recursive:true})){if(/\.js$/.test(name))report.bundleSHA256[name]=digest(await readFile(path.join(client,'build-embedded-world',name)));}
 const output=process.env.OVERTE_EMBEDDED_EVIDENCE||path.join(client,'build-embedded-evidence');await mkdir(output,{recursive:true});await writeFile(path.join(output,`embedded-world-${engine}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
