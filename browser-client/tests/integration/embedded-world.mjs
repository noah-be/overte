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
 assert.deepEqual(Object.keys(value).sort(),['contextStates','decodedRGBA','frames','lifecycle','phase','version']);assert.equal(value.version,4);
 assert(['model-await','gpu-loop','gpu-upload-check','post-gpu-resources','model-cancellation','complete'].includes(value.phase));
 assert(Array.isArray(value.decodedRGBA)&&[0,4].includes(value.decodedRGBA.length));
 assert(value.decodedRGBA.every(n=>Number.isInteger(n)&&n>=0&&n<=255));assert(Array.isArray(value.frames)&&value.frames.length<=20);
 for(let i=0;i<value.frames.length;i++){const row=value.frames[i];assert(Array.isArray(row)&&row.length===11);assert.equal(row[0],i);
  for(let j=1;j<5;j++)assert(Number.isInteger(row[j])&&row[j]>=0&&row[j]<=255);
  for(let j=5;j<11;j++)assert(Number.isSafeInteger(row[j])&&row[j]>=0&&row[j]<=1000000);
 }
 assert(Array.isArray(value.contextStates)&&value.contextStates.length===value.frames.length&&value.contextStates.length<=20);
 for(let i=0;i<value.contextStates.length;i++){const row=value.contextStates[i];assert(Array.isArray(row)&&row.length===5);assert.equal(row[0],i);
  for(let j=1;j<3;j++)assert(Number.isSafeInteger(row[j])&&row[j]>=0&&row[j]<=1000000);
  for(let j=3;j<5;j++)assert(row[j]===0||row[j]===1);
 }
 validateEmbeddedLifecycle(value.lifecycle);
 return value;
}
function validateEmbeddedLifecycle(value){
 assert(value&&typeof value==='object'&&!Array.isArray(value));assert.deepEqual(Object.keys(value).sort(),['backend','backendSource','dropped','eventTimings','events','observerRefused','phase','prepareCalls','resizeCalls','timingRefused']);
 for(const name of ['prepareCalls','resizeCalls','dropped'])assert(Number.isSafeInteger(value[name])&&value[name]>=0&&value[name]<=1000000);
 assert(Number.isInteger(value.phase)&&value.phase>=1&&value.phase<=10);assert(Number.isInteger(value.backend)&&value.backend>=0&&value.backend<=4);assert(Number.isInteger(value.backendSource)&&value.backendSource>=0&&value.backendSource<=2);assert(value.observerRefused===0||value.observerRefused===1);
 assert(Array.isArray(value.events)&&value.events.length<=16);for(const row of value.events){assert(Array.isArray(row)&&row.length===6);assert(Number.isInteger(row[0])&&row[0]>=0&&row[0]<=10);assert(Number.isInteger(row[1])&&row[1]>=1&&row[1]<=10);for(const j of [2,5])assert(Number.isSafeInteger(row[j])&&row[j]>=0&&row[j]<=1000000);for(const j of [3,4])assert(row[j]===0||row[j]===1);}
 assert(value.timingRefused===0||value.timingRefused===1);assert(Array.isArray(value.eventTimings)&&value.eventTimings.length===value.events.length&&value.eventTimings.length<=16);
 let previous=0;for(let i=0;i<value.eventTimings.length;i++){const row=value.eventTimings[i];assert(Array.isArray(row)&&row.length===3&&row[0]===i);
  if(row[1]===null)assert.equal(value.timingRefused,1);else{assert(Number.isSafeInteger(row[1])&&row[1]>=previous&&row[1]<=60000);previous=row[1];}
  if(row[2]===null)assert.equal(value.timingRefused,1);else assert(Number.isSafeInteger(row[2])&&row[2]>=0&&row[2]<=1000000);
 }
 return value;
}
function createEmbeddedBrowserObserver(){
 const state={consoleCounts:[0,0,0,0,0],consoleDropped:0,observerRefused:0,pageCrashed:0,pageClosedBeforeCleanup:0,browserDisconnectedBeforeCleanup:0};let active=false,browser,page;
 const bounded=name=>{state[name]=Math.min(1000000,state[name]+1);};
 const consoleMessage=message=>{if(!active)return;try{const text=message.text();if(typeof text!=='string'||text.length>4096){bounded('consoleDropped');return;}let kind=-1;
  if(text==='THREE.WebGLRenderer: Context Lost.')kind=0;else if(text==='THREE.WebGLRenderer: Context Restored.')kind=1;else if(/^THREE\.WebGLRenderer: Error creating WebGL context(?:\.| with your selected attributes\.)$/.test(text))kind=2;else if(text.startsWith('THREE.WebGLProgram: Shader Error '))kind=3;else if(/^(?:WebGL|WebGL2): CONTEXT_LOST_WEBGL\b/.test(text))kind=4;
  if(kind>=0)state.consoleCounts[kind]=Math.min(1000000,state.consoleCounts[kind]+1);
 }catch{state.observerRefused=1;}};
 const crashed=()=>{if(active)state.pageCrashed=1;},closed=()=>{if(active)state.pageClosedBeforeCleanup=1;},disconnected=()=>{if(active)state.browserDisconnectedBeforeCleanup=1;};
 return {attach(b,p){if(active){state.observerRefused=1;return;}browser=b;page=p;active=true;try{browser.on('disconnected',disconnected);page.on('crash',crashed);page.on('close',closed);page.on('console',consoleMessage);}catch{state.observerRefused=1;}},snapshot(){return {...state,consoleCounts:state.consoleCounts.slice()};},retire(){active=false;for(const[target,event,handler]of [[browser,'disconnected',disconnected],[page,'crash',crashed],[page,'close',closed],[page,'console',consoleMessage]])try{target?.off(event,handler);}catch{state.observerRefused=1;}}};
}
function projectEmbeddedGpuProcess(value){
 const count=value?.gpu?.auxAttributes?.processCrashCount;
 return {processCrashCount:Number.isSafeInteger(count)&&count>=0&&count<=1000000?count:null};
}
async function readEmbeddedGpuProcess(browser){
 if(!browser)return {processCrashCount:null};let session;
 try{session=await browser.newBrowserCDPSession();return projectEmbeddedGpuProcess(await session.send('SystemInfo.getInfo'));}
 catch{return {processCrashCount:null};}
 finally{if(session)try{await session.detach();}catch{}}
}
async function boundedEmbeddedDiagnosticRead(read){
 let timer;
 try{return await Promise.race([Promise.resolve().then(read),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('bounded-diagnostic-unavailable')),500);})]);}
 finally{clearTimeout(timer);}
}
async function collectEmbeddedFailureDiagnostic(page,primaryMessage,browser){
 if(primaryMessage==='Embedded World fixture exceeded 30 seconds')return {pixelDiagnosticRefusal:'original-fixture-deadline'};
 let pixel,gpu={processCrashCount:null};
 try{await boundedEmbeddedDiagnosticRead(()=>Promise.allSettled([Promise.resolve().then(()=>page?.evaluate(()=>window.__embeddedWorldDiagnostic)).then(value=>{pixel=validateEmbeddedDiagnostic(value);}),readEmbeddedGpuProcess(browser).then(value=>{gpu=value;})]));}catch{}
 return {...(pixel?{pixelDiagnostic:pixel}:{pixelDiagnosticRefusal:'unavailable-or-invalid'}),gpuProcessDiagnostic:gpu};
}
// END strict fixed-field diagnostic consumer.
// BEGIN explicit embedded ANGLE request.
function embeddedGraphicsLaunchOptions(value,engine){
 assert(value===undefined||value===''||value==='0'||value==='1','Embedded ANGLE request refused');
 const selected=value==='1';assert(!selected||engine==='chrome','Embedded ANGLE request requires Google Chrome');
 return {args:selected?['--mute-audio','--use-angle=swiftshader']:['--mute-audio'],requestedAngleMode:selected?'swiftshader-requested':'default'};
}
// END explicit embedded ANGLE request.
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER||'chrome',display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['chrome','chromium','firefox','system-chromium','system-firefox'].includes(engine));
const graphicsLaunch=embeddedGraphicsLaunchOptions(process.env.OVERTE_EMBEDDED_USE_SWANGLE,engine);
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const report={startedAt:new Date().toISOString(),completed:false,engine,requestedAngleMode:graphicsLaunch.requestedAngleMode,domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,scope:'Actual BrowserWorld.loadModel, production-built worker and ordinary embedded PNG fixture; no public/native whole-world or speed claim',requests:0};
let server,browser,page;const browserObserver=createEmbeddedBrowserObserver();
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
 else {if(engine==='system-chromium')assert(process.env.OVERTE_LAB_CHROMIUM,'Stock Chromium executable must be explicit');browser=await chromium.launch({...(engine==='chrome'?googleChromeLaunchOptions():{}),...(engine==='system-chromium'?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{}),headless:!display,env:{...env,...(engine==='system-chromium'&&process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:graphicsLaunch.args});}
 report.browserVersion=await browser.version();const context=await browser.newContext({viewport:{width:1280,height:800}}),errors=[];page=await context.newPage();browserObserver.attach(browser,page);
 page.on('pageerror',error=>errors.push(String(error.message).slice(0,1024)));
 await page.goto(`http://127.0.0.1:${address.port}/tests/fixtures/embedded-world.html`);await page.waitForFunction(()=>typeof window.runEmbeddedWorldFixture==='function',undefined,{timeout:10000});
 // The existing 30-second model texture/worker deadlines are unchanged. This
 // outer fixture bound allows owned cleanup without changing either gate.
 report.world=await Promise.race([page.evaluate(()=>window.runEmbeddedWorldFixture()),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('Embedded World fixture exceeded 30 seconds')),30000);timer.unref();})]);
 assert.equal(report.world.completed,true);assert.equal(report.requests,1,'Actual prepared cache must avoid duplicate upstream model fetches');assert.deepEqual(errors,[]);report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;
 Object.assign(report,await collectEmbeddedFailureDiagnostic(page,report.error,browser));report.browserDiagnostic=browserObserver.snapshot();
}
finally{
 browserObserver.retire();await browser?.close();await server?.close();report.finishedAt=new Date().toISOString();report.sourceSHA256={};
 for(const name of ['tests/google-chrome-selection.mjs','tests/integration/embedded-world.mjs','tests/fixtures/embedded-world.ts','vite.embedded-world.config.mjs','package-lock.json','src/world.ts','src/baked-fbx.ts','src/model-fbx-worker.ts','src/model-fbx-pool.ts','src/prepared-fbx-cache.ts','src/embedded-fbx-images.ts','src/embedded-fbx-protocol.ts','src/world-image-cache.ts'])report.sourceSHA256[name]=digest(await readFile(path.join(client,name)));
 report.bundleSHA256={};for(const name of await readdir(path.join(client,'build-embedded-world'),{recursive:true})){if(/\.js$/.test(name))report.bundleSHA256[name]=digest(await readFile(path.join(client,'build-embedded-world',name)));}
 const output=process.env.OVERTE_EMBEDDED_EVIDENCE||path.join(client,'build-embedded-evidence');await mkdir(output,{recursive:true});await writeFile(path.join(output,`embedded-world-${engine}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
