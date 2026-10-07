// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Owned DOM-worker timing only. It does not join a domain, use WebGL, record
// audio or establish renderer/native texture parity.
import {createHash} from 'node:crypto';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from '@playwright/test';
import {launchSystemFirefox} from './system-firefox.mjs';
const option=name=>{const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];};
const kind=option('--browser')||'chromium';
if(!['chromium','firefox'].includes(kind))throw Error('Choose chromium or firefox');
const output=option('--output');
const source=`self.onmessage=async()=>{
 try{
 const workerStartedAt=new Date().toISOString(),results=[];
 for(let trial=0;trial<3;trial++)for(const mode of ['timer','channel']){
   const started=performance.now(),delays=[];let channel,continuation;
   if(mode==='channel'){channel=new MessageChannel();channel.port1.onmessage=()=>continuation();}
   try{
     for(let at=0;at<256;at++){
       const before=performance.now();
       await new Promise(resolve=>{if(mode==='timer')setTimeout(resolve,0);else{continuation=resolve;channel.port2.postMessage(0);}});
       delays.push(performance.now()-before);
     }
   }finally{channel?.port1.close();channel?.port2.close();}
   delays.sort((a,b)=>a-b);
   results.push({trial,mode,yields:256,elapsedMs:performance.now()-started,minYieldMs:delays[0],medianYieldMs:delays[128],p95YieldMs:delays[243],maxYieldMs:delays[255]});
 }
 self.postMessage({workerStartedAt,workerFinishedAt:new Date().toISOString(),results});
 }catch(error){self.postMessage({error:String(error)});}
};`;
const report={startedAt:new Date().toISOString(),browser:kind,browserMode:'headless',domainJoined:false,webGLRequested:false,microphoneRequested:false,
 timerReference:'https://html.spec.whatwg.org/multipage/timers-and-user-prompts.html',
 microtaskReference:'https://chromium.googlesource.com/external/w3c/web-platform-tests/+/refs/tags/merge_pr_55601/html/webappapis/timers/timer-nesting-not-inherited-in-microtask.html',
 workerSourceSHA256:createHash('sha256').update(source).digest('hex')};
let browser,context,page;
try{
 const env={...process.env};
 if(kind==='chromium'&&process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH)env.LD_LIBRARY_PATH=process.env.OVERTE_LAB_CHROMIUM_LIBRARY_PATH;
 browser=kind==='firefox'?await launchSystemFirefox({executablePath:process.env.OVERTE_LAB_FIREFOX||'/usr/bin/firefox',env,headless:true,syntheticMicrophone:false})
   :await chromium.launch({env,headless:true,timeout:15000,args:['--mute-audio'],...(process.env.OVERTE_LAB_CHROMIUM?{executablePath:process.env.OVERTE_LAB_CHROMIUM}:{})});
 report.browserVersion=await browser.version();context=await browser.newContext();page=await context.newPage();
 const result=await page.evaluate(source=>{
   const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));let worker;
   try{worker=new Worker(url);}finally{URL.revokeObjectURL(url);}
   return new Promise((resolve,reject)=>{
     const timer=setTimeout(()=>{worker.terminate();reject(Error('Owned texture-yield worker exceeded 20 seconds'));},20000);
     worker.onerror=event=>{clearTimeout(timer);worker.terminate();reject(Error(event.message));};
     worker.onmessage=event=>{clearTimeout(timer);worker.terminate();if(event.data.error)reject(Error(event.data.error));else resolve(event.data);};
     worker.postMessage(0);
   });
 },source);
 Object.assign(report,result);
}catch(error){
 report.failure={name:error?.name||'Error',stage:browser?'worker':'launch'};process.exitCode=1;
}finally{
 // Context owns every page. The Firefox adapter deliberately does not expose
 // page.close(). Browser cleanup must run even if context cleanup fails.
 try{await context?.close();}catch(error){report.contextCleanupError={name:error?.name||'Error'};process.exitCode=1;}
 finally{try{if(browser){await browser.close();report.ownedBrowserClosed=true;}}catch(error){report.browserCleanupError={name:error?.name||'Error'};process.exitCode=1;}}
}
report.finishedAt=new Date().toISOString();report.ownedBrowserClosed??=false;
if(output){await mkdir(path.dirname(output),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report));
