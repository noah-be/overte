// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Parent-owned execution only. Unchanged six registered tests and actual expect.
// Authored exact assets; no native/public domain, microphone or quality setters.
import {createServer}from'vite';import{chromium}from'@playwright/test';
import puppeteer from'puppeteer-core';import{sizeSystemFirefoxWindow}from'./system-firefox.mjs';
import{registeredCloneBodies}from'./replacement-material-clones-registration.mjs';
import{cloneBidiArguments}from'./replacement-material-clones-bidi-arguments.mjs';
import{cloneFailureDiagnostic,privateCloneException,privateCloneMessage,observeCloneDriver,evaluateCloneFixture,persistCloneAttempt}from'./replacement-material-clones-diagnostics.mjs';
import{readFile}from'node:fs/promises';import{createHash}from'node:crypto';import{fileURLToPath}from'node:url';import path from'node:path';import assert from'node:assert/strict';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER,display=process.env.OVERTE_LAB_BROWSER_DISPLAY,port=Number(process.env.OVERTE_REPLACEMENT_CLONE_FIXTURE_PORT||5194);
assert(['system-chromium','system-firefox'].includes(engine));assert(typeof display==='string'&&/^:[0-9]{1,3}$/.test(display));assert(Number.isInteger(port)&&port>=1024&&port<=65535);
const files=['src/world.ts','src/replacement-material-clones.ts','src/native-render-state.ts','src/native-alpha-material.ts','src/native-zero-lights.ts','src/model-resources.ts','src/static-model-batch.ts','src/model-textures.ts','src/model-fbx-pool.ts','src/model-fbx-worker.ts','src/baked-fbx.ts','tests/replacement-material-clones-fixture.ts','tests/replacement-material-clones.browser.spec.ts','tests/fixtures/replacement-material-fbx.ts','tests/integration/replacement-material-clones.mjs','tests/integration/replacement-material-clones-registration.mjs','tests/integration/replacement-material-clones-bidi-arguments.mjs','tests/integration/replacement-material-clones-diagnostics.mjs','tests/integration/system-firefox.mjs','package-lock.json'];
const sha=value=>createHash('sha256').update(value).digest('hex');async function hashes(){return Object.fromEntries(await Promise.all(files.map(async file=>[file,sha(await readFile(path.join(client,file)))])));}
const report={schemaVersion:3,startedAt:new Date().toISOString(),completed:false,engine,scope:'Unchanged six registered authored BrowserWorld/FST/FBXLoader tests with actual Playwright expect; no native-domain, Hub or speed claim',microphoneRequested:false,publicDomainJoined:false,records:[],cleanup:{browser:'not-created',server:'not-created',contextsClosed:0}};
let server,browser,context,timer;let phase='source-pins',variant=null,currentRecord,observer;
try{
 report.sourceStart=await hashes();phase='register-unchanged-tests';const registered=await registeredCloneBodies(path.join(client,'tests/replacement-material-clones.browser.spec.ts'));
 phase='owned-server';server=await createServer({root:client,configFile:path.join(client,'vite.config.ts'),server:{host:'127.0.0.1',port,strictPort:true}});await server.listen();const baseURL=`http://127.0.0.1:${port}/`,env={...process.env,DISPLAY:display};
 phase='stock-browser';if(engine==='system-firefox')browser=await puppeteer.launch({browser:'firefox',protocol:'webDriverBiDi',executablePath:'/usr/bin/firefox',headless:false,defaultViewport:null,env,extraPrefsFirefox:{'media.navigator.streams.fake':false,'media.navigator.permission.disabled':true}});
 else{assert(process.env.OVERTE_LAB_CHROMIUM,'Explicit stock Chromium executable required');browser=await chromium.launch({headless:false,executablePath:process.env.OVERTE_LAB_CHROMIUM,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();timer=setTimeout(()=>{report.deadlineExceeded=true;void Promise.resolve().then(()=>browser.close()).catch(()=>{});},180000);
 for(const entry of registered){
  variant=entry.variant;phase='fresh-context';let rejectRoute;const routeFailure=new Promise((_,reject)=>{rejectRoute=reject;});void routeFailure.catch(()=>{});
  const record={variant,attachmentReceived:false,passed:false};report.records.push(record);currentRecord=record;
  context=engine==='system-firefox'?await browser.createBrowserContext():await browser.newContext({viewport:{width:1280,height:800}});const raw=await context.newPage();observer=observeCloneDriver(raw);
  let page;
  if(engine==='system-firefox'){
   await sizeSystemFirefoxWindow(browser,raw,{width:1280,height:800});const routes=[];await raw.setRequestInterception(true);
   raw.on('request',request=>{void(async()=>{
    const href=request.url(),matching=routes.findLast(route=>route.match(href));if(!matching){await request.continue();return;}
    let fulfilled=false;await matching.handler({request:()=>({url:()=>href}),fulfill:async({status=200,headers={},body='',contentType}={})=>{assert(!fulfilled,'Fixture request fulfilled once');fulfilled=true;await request.respond({status,headers,body,...(contentType?{contentType}:{})});}});assert(fulfilled,'Registered fixture route must fulfill');
   })().catch(error=>{rejectRoute(error);void request.abort().catch(()=>{});});});
   page={on:(...args)=>raw.on(...args),route:async(pattern,handler)=>{
    // Exact two patterns used by the unchanged spec; no generic routing rewrite.
    let match;if(pattern instanceof RegExp||Object.prototype.toString.call(pattern)==='[object RegExp]'){assert.equal(pattern.source,'^http:\\/\\/127\\.0\\.0\\.1:\\d+\\/$');assert.equal(pattern.flags,'');match=url=>pattern.test(url);}
    else{assert.equal(pattern,'**/replacement-clone-assets/**');match=url=>new URL(url).pathname.includes('/replacement-clone-assets/');}
    routes.push({match,handler});},goto:(target,...args)=>raw.goto(new URL(target,baseURL).href,...args),evaluate:(...args)=>evaluateCloneFixture(raw,cloneBidiArguments(args),record),context:()=>({browser:()=>({version:()=>report.browserVersion})})};
  }else page={on:(...args)=>raw.on(...args),route:(...args)=>raw.route(...args),goto:(target,...args)=>raw.goto(new URL(target,baseURL).href,...args),evaluate:(...args)=>evaluateCloneFixture(raw,args,record),context:()=>({browser:()=>({version:()=>report.browserVersion})})};
  phase='registered-test';try{await Promise.race([entry.callback({page},{project:{name:engine},attach:async(name,value)=>{assert.equal(name,'replacement-clone-strict-source-proof');assert.equal(value.contentType,'application/json');assert(!record.attachmentReceived);record.actual=JSON.parse(value.body);record.attachmentReceived=true;}}),routeFailure]);assert(record.attachmentReceived);record.passed=true;}
  finally{observer.close();record.driverEvents=observer.read();observer=undefined;phase=record.passed?'context-cleanup':'registered-test';try{await context.close();report.cleanup.contextsClosed++;}finally{context=undefined;}}
 }
 report.completed=true;
}catch(error){report.failure='owned-registered-replacement-clone-proof-failed';report.failurePhase=phase;report.failureVariant=variant;report.failureDiagnostic=cloneFailureDiagnostic(error);report.privateException=privateCloneException(error);report.privateMessage=privateCloneMessage(error);if(currentRecord?.failureOperation)report.failureOperation=currentRecord.failureOperation;process.exitCode=1;}
finally{
 clearTimeout(timer);if(observer){observer.close();currentRecord.driverEvents=observer.read();observer=undefined;}
 try{if(context){try{await context.close();report.cleanup.contextsClosed++;}catch{report.cleanup.contextFailed=true;report.completed=false;process.exitCode=1;}}}
 finally{try{if(browser){try{await browser.close();report.cleanup.browser='closed';}catch{report.cleanup.browser='failed';report.completed=false;process.exitCode=1;}}}
 finally{if(server){try{await server.close();report.cleanup.server='closed';}catch{report.cleanup.server='failed';report.completed=false;process.exitCode=1;}}}}
 try{report.sourceEnd=await hashes();report.sourceCoherent=!!report.sourceStart&&JSON.stringify(report.sourceStart)===JSON.stringify(report.sourceEnd);if(!report.sourceCoherent){report.completed=false;process.exitCode=1;}}
 catch{report.sourceCoherent=false;report.sourceHashFailure=true;report.completed=false;process.exitCode=1;}
 report.finishedAt=new Date().toISOString();const directory=path.join(client,'build','replacement-material-clones-stock');let bytes;try{bytes=await persistCloneAttempt(directory,engine,report);}catch{console.log(JSON.stringify({completed:false,engine,privatePersistenceFailed:true}));process.exitCode=1;}
 if(bytes)console.log(JSON.stringify({completed:report.completed,engine,sourceCoherent:report.sourceCoherent,browserClosed:report.cleanup.browser==='closed',serverClosed:report.cleanup.server==='closed',records:report.records.length,reportSHA256:sha(bytes)}));
}
