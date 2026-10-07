// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Parent-owned stock execution: exact original registered expect bodies.
import {chromium} from '@playwright/test';import {createServer} from 'vite';import {launchSystemFirefox} from './system-firefox.mjs';import {registeredBitmapBodies,finishStockBitmapCleanup} from './stock-bitmap-registration.mjs';
import {readFile,writeFile,mkdir,readdir,lstat} from 'node:fs/promises';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';import path from 'node:path';import assert from 'node:assert/strict';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),engine=process.env.OVERTE_LAB_BROWSER,display=process.env.OVERTE_LAB_BROWSER_DISPLAY,port=Number(process.env.OVERTE_BITMAP_FIXTURE_PORT||5196);
assert(['system-chromium','system-firefox'].includes(engine));assert(typeof display==='string'&&/^:[0-9]{1,3}$/.test(display));assert(Number.isInteger(port)&&port>=1024&&port<=65535);
const expectedMajor=engine==='system-chromium'?154:156;
const files=['index.html','vite.config.ts','package.json','package-lock.json','tests/world-bitmap-upload.browser.spec.ts','tests/world-bitmap-integration.browser.spec.ts','tests/fixtures/world-bitmap-upload.ts','tests/fixtures/world-bitmap-integration.ts','tests/integration/stock-bitmap-pixels.mjs','tests/integration/stock-bitmap-registration.mjs','tests/integration/system-firefox.mjs'];
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function sourceHashes(){
 const names=[...files];async function visit(relative){for(const entry of await readdir(path.join(client,relative),{withFileTypes:true})){const name=path.posix.join(relative,entry.name),st=await lstat(path.join(client,name));assert(!st.isSymbolicLink(),'Source attestation refuses symlinks');if(st.isDirectory())await visit(name);else if(st.isFile()&&/\.(?:ts|js|mjs|wasm|css)$/.test(name))names.push(name);else assert(st.isFile(),'Source attestation requires regular files');}}
 await visit('src');assert(names.length<=1024);let total=0;const rows={};for(const name of names.sort()){const bytes=await readFile(path.join(client,name));total+=bytes.length;assert(total<=32*1024*1024,'Source attestation byte budget');rows[name]=sha(bytes);}return rows;
}
const report={schemaVersion:1,startedAt:new Date().toISOString(),engine,completed:false,scope:'Two unchanged authored registered bitmap test bodies; twelve literal variants and actual 4096 World Image samplers',publicDomainJoined:false,microphoneRequested:false,externalImageFetchRequested:false,embeddedFbxGpuCoverage:false,records:[],cleanup:{contextsClosed:0,browser:'not-created',server:'not-created'}};
let server,browser,context,timer,phase='source-attestation';
try{
 report.sourceStart=await sourceHashes();phase='register-original-assertions';const registered=await registeredBitmapBodies(client);
 phase='owned-vite';server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port,strictPort:true}});await server.listen();const base=`http://127.0.0.1:${port}/`,env={...process.env,DISPLAY:display};
 phase='stock-browser';if(engine==='system-firefox'){assert(process.env.OVERTE_LAB_FIREFOX,'Explicit stock Firefox executable required');browser=await launchSystemFirefox({executablePath:process.env.OVERTE_LAB_FIREFOX,headless:false,env,syntheticMicrophone:false});}
 else{assert(process.env.OVERTE_LAB_CHROMIUM,'Explicit stock Chromium executable required');browser=await chromium.launch({headless:false,executablePath:process.env.OVERTE_LAB_CHROMIUM,env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();assert(new RegExp('(?:^|/)'+expectedMajor+'\\.').test(report.browserVersion),'Exact requested stock major version required');
 timer=setTimeout(()=>{report.ownerDeadlineExceeded=true;void Promise.resolve().then(()=>browser.close()).catch(()=>{});},180000);
 for(const test of registered){
  const row={variant:test.variant,passed:false,attachmentReceived:false};report.records.push(row);phase='fresh-context';context=await browser.newContext({viewport:{width:1280,height:800}});const raw=await context.newPage();
  const page={on:(...args)=>raw.on(...args),goto:(target,...args)=>raw.goto(new URL(target,base).href,...args),evaluate:(...args)=>raw.evaluate(...args),context:()=>({browser:()=>({version:()=>report.browserVersion})})};
  phase='unchanged-registered-test';await test.callback({page},{project:{name:engine},attach:async(name,value)=>{assert.equal(name,test.attachment);assert.equal(value.contentType,'application/json');assert(!row.attachmentReceived);const bytes=Buffer.from(value.body);assert(bytes.length<=256*1024,'Original fixed-scalar attachment bound');row.actual=JSON.parse(bytes);row.attachmentReceived=true;}});assert(row.attachmentReceived);row.passed=true;
  phase='context-cleanup';await context.close();report.cleanup.contextsClosed++;context=undefined;
 }
 assert(!report.ownerDeadlineExceeded,'Owned bitmap fixture deadline exceeded');report.completed=true;
}catch(error){report.failure='actual-stock-registered-bitmap-proof-refused';report.failurePhase=phase;report.privateError=String(error?.stack||error).slice(0,8192);process.exitCode=1;}
finally{
 clearTimeout(timer);await finishStockBitmapCleanup({context,browser,server},report);
 try{report.sourceEnd=await sourceHashes();report.sourceCoherent=!!report.sourceStart&&JSON.stringify(report.sourceStart)===JSON.stringify(report.sourceEnd);if(!report.sourceCoherent){report.completed=false;process.exitCode=1;}}
 catch{report.sourceCoherent=false;report.completed=false;report.sourceAttestationFailure=true;process.exitCode=1;}
 report.finishedAt=new Date().toISOString();const directory=path.join(client,'build','stock-bitmap-registered');await mkdir(directory,{recursive:true,mode:0o700});const bytes=JSON.stringify(report,null,2)+'\n';await writeFile(path.join(directory,engine+'.private.json'),bytes,{flag:'wx',mode:0o600});console.log(JSON.stringify({engine,browserVersion:report.browserVersion,completed:report.completed,sourceCoherent:report.sourceCoherent,records:report.records.length,contextsClosed:report.cleanup.contextsClosed,browserClosed:report.cleanup.browser==='closed',serverClosed:report.cleanup.server==='closed',reportSHA256:sha(bytes)}));
}
