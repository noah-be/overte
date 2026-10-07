// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Execute the exact registered authored World test with stock browser drivers.
// No assertion substitution, domain admission, microphone or native setters.
import {chromium,expect} from '@playwright/test';
import {createServer,transformWithOxc} from 'vite';
import {launchSystemFirefox} from './system-firefox.mjs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const engine=process.env.OVERTE_LAB_BROWSER,display=process.env.OVERTE_LAB_BROWSER_DISPLAY;
assert(['system-chromium','system-firefox'].includes(engine));
assert(typeof display==='string'&&/^:[0-9]{1,3}$/.test(display));
const files=['src/world.ts','src/main.ts','src/render-cpu-breakdown.ts','src/render-dispatch-attribution.ts',
 'tests/render-cpu-breakdown-fixture.ts','tests/render-dispatch-attribution.browser.spec.ts',
 'tests/integration/render-dispatch-pixels.mjs','tests/integration/system-firefox.mjs','package-lock.json'];
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
async function hashes(){return Object.fromEntries(await Promise.all(files.map(async file=>[file,digest(await readFile(path.join(client,file)))])));}
const report={schemaVersion:1,startedAt:new Date().toISOString(),engine,completed:false,
 scope:'Exact registered authored World dispatch test in a stock browser; no Hub/native/optimization-gain claim',
 domainConnected:false,microphoneRequested:false,worldInteractionsSent:0,startSourceSHA256:await hashes()};
let server,browser,context;
try{
 const file='tests/render-dispatch-attribution.browser.spec.ts',source=await readFile(path.join(client,file),'utf8');
 const marker="import {expect,test} from '@playwright/test';";
 assert.equal(source.split(marker).length,2,'Only the exact reviewed assertion registration is adapted');
 const compiled=await transformWithOxc(source.replace(marker,'const expect=injectedExpect,test=injectedTest;'),file);
 let registered;
 vm.runInNewContext(compiled.code,{injectedExpect:expect,injectedTest:(name,callback)=>{
  assert.equal(name,'actual World dispatch attribution preserves exact rendered pixels and program-call boundaries');
  assert.equal(registered,undefined);assert.equal(typeof callback,'function');registered=callback;
 }},{timeout:1000});assert(registered);
 server=await createServer({root:client,configFile:false,server:{host:'127.0.0.1',port:5194,strictPort:true}});await server.listen();
 const address=server.httpServer.address();assert(address&&typeof address==='object');const url=`http://127.0.0.1:${address.port}/`;
 const env={...process.env,DISPLAY:display};
 if(engine==='system-firefox')browser=await launchSystemFirefox({headless:false,env,syntheticMicrophone:false});
 else {assert(process.env.OVERTE_LAB_CHROMIUM);browser=await chromium.launch({headless:false,executablePath:process.env.OVERTE_LAB_CHROMIUM,
  env:{...env,...(process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH?{LD_LIBRARY_PATH:process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH}:{})},args:['--mute-audio']});}
 report.browserVersion=await browser.version();context=await browser.newContext({viewport:{width:1280,height:800}});
 const driver=await context.newPage(),page={on:(...args)=>driver.on(...args),goto:(target,...args)=>driver.goto(new URL(target,url).href,...args),
  evaluate:(...args)=>driver.evaluate(...args),context:()=>({browser:()=>browser})};
 await registered({page},{project:{name:engine},attach:async(name,value)=>{
  assert.equal(name,'actual-world-dispatch-attribution-boundaries');assert.equal(value.contentType,'application/json');
  const data=JSON.parse(value.body);assert.equal(data.schemaVersion,1);report.actual=data;
 }});
 report.completed=true;
}catch(error){report.errorCategory='actual-registered-pixel-test-refused';report.privateError=String(error?.stack||error).slice(0,8192);process.exitCode=1;}
finally{
 try{await context?.close();}catch{report.contextCleanupFailed=true;report.completed=false;process.exitCode=1;}
 try{await browser?.close();report.browserClosed=!!browser;}catch{report.browserClosed=false;report.completed=false;process.exitCode=1;}
 finally{try{await server?.close();report.serverClosed=!!server;}catch{report.serverClosed=false;report.completed=false;process.exitCode=1;}}
 try{report.endSourceSHA256=await hashes();report.sourceCoherent=JSON.stringify(report.startSourceSHA256)===JSON.stringify(report.endSourceSHA256);
  if(!report.sourceCoherent){report.completed=false;process.exitCode=1;}}
 catch{report.sourceCoherent=false;report.completed=false;process.exitCode=1;}
 report.finishedAt=new Date().toISOString();
 const output=path.join(client,'build','render-dispatch-pixels');await mkdir(output,{recursive:true,mode:0o700});
 const bytes=JSON.stringify(report,null,2)+'\n';await writeFile(path.join(output,engine+'.private.json'),bytes,{flag:'wx',mode:0o600});
 console.log(JSON.stringify({engine,completed:report.completed,browserVersion:report.browserVersion,
  sourceCoherent:report.sourceCoherent,browserClosed:report.browserClosed,serverClosed:report.serverClosed,rawReportSHA256:digest(bytes)}));
}
