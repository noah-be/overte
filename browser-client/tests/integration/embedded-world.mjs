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
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER||'system-chromium',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['chromium','firefox','system-chromium','system-firefox'].includes(engine));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const report={startedAt:new Date().toISOString(),completed:false,engine,domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,scope:'Actual BrowserWorld.loadModel, production-built worker and ordinary embedded PNG fixture; no public/native whole-world or speed claim',requests:0};
let server,browser;
try{
 const {embeddedFbx}=await import('../../build-embedded/entry.js'),bytes=new Uint8Array(embeddedFbx());report.assetSHA256=digest(bytes);
 server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port:Number(process.env.OVERTE_EMBEDDED_FIXTURE_PORT||5192),strictPort:true},plugins:[{name:'owned-embedded-world',configureServer(vite){vite.middlewares.use((request,response,next)=>{
  if(new URL(request.url||'/', 'http://127.0.0.1').pathname!=='/__embedded/model.fbx'){next();return;}
  if(request.method!=='GET'){response.statusCode=405;response.end();return;}
  report.requests++;response.setHeader('Content-Type','application/octet-stream');response.setHeader('Content-Length',bytes.length);response.setHeader('Cache-Control','private, no-store');response.setHeader('X-Content-Type-Options','nosniff');response.end(bytes);
 });}}]});await server.listen();const address=server.httpServer.address();assert(address&&typeof address==='object');
 const env={...process.env,...(display?{DISPLAY:display}:{})};
 if(engine==='system-firefox')browser=await launchSystemFirefox({executablePath:'/usr/bin/firefox',headless:!display,env,syntheticMicrophone:false});
 else if(engine==='firefox')browser=await firefox.launch({headless:!display,env});
 else {if(engine==='system-chromium')assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');browser=await chromium.launch({executablePath:engine==='system-chromium'?process.env.OVERTE_LAB_CHROMIUM:undefined,headless:!display,env:{...env,...(engine==='system-chromium'&&process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(String(error.message).slice(0,1024)));
 await page.goto(`http://127.0.0.1:${address.port}/tests/fixtures/embedded-world.html`);await page.waitForFunction(()=>typeof window.runEmbeddedWorldFixture==='function',undefined,{timeout:10000});
 // The existing 30-second model texture/worker deadlines are unchanged. This
 // outer fixture bound allows owned cleanup without changing either gate.
 report.world=await Promise.race([page.evaluate(()=>window.runEmbeddedWorldFixture()),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('Embedded World fixture exceeded 30 seconds')),30000);timer.unref();})]);
 assert.equal(report.world.completed,true);assert.equal(report.requests,1,'Actual prepared cache must avoid duplicate upstream model fetches');assert.deepEqual(errors,[]);report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{
 await browser?.close();await server?.close();report.finishedAt=new Date().toISOString();report.sourceSHA256={};
 for(const name of ['tests/integration/embedded-world.mjs','tests/fixtures/embedded-world.ts','vite.embedded-world.config.mjs','package-lock.json','src/world.ts','src/baked-fbx.ts','src/model-fbx-worker.ts','src/model-fbx-pool.ts','src/prepared-fbx-cache.ts','src/embedded-fbx-images.ts','src/embedded-fbx-protocol.ts','src/world-image-cache.ts'])report.sourceSHA256[name]=digest(await readFile(path.join(client,name)));
 report.bundleSHA256={};for(const name of await readdir(path.join(client,'build-embedded-world'),{recursive:true})){if(/\.js$/.test(name))report.bundleSHA256[name]=digest(await readFile(path.join(client,'build-embedded-world',name)));}
 const output=process.env.OVERTE_EMBEDDED_EVIDENCE||path.join(client,'build-embedded-evidence');await mkdir(output,{recursive:true});await writeFile(path.join(output,`embedded-world-${engine}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
