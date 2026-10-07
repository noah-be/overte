// SPDX-License-Identifier: Apache-2.0
// Focused actual native public FBX regression; no domain connection or writes.
import {chromium,firefox} from '@playwright/test';import {spawn} from 'node:child_process';
import {readFile,mkdir,writeFile} from 'node:fs/promises';import {createHash} from 'node:crypto';import path from 'node:path';import {fileURLToPath} from 'node:url';import assert from 'node:assert/strict';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..'),origin='http://127.0.0.1:5184',output=path.join(repo,'build/browser-hub-lab/batch-inventory');
const useFirefox=process.env.OVERTE_LAB_BROWSER==='firefox';
const report={startedAt:new Date().toISOString(),completed:false,actualNativeAsset:true,domainConnected:false,diagnosticTexture:true};let vite,browser;
try{
 try{await fetch(origin,{signal:AbortSignal.timeout(300)});throw Error('Refusing occupied proof port');}catch(error){if(error.message==='Refusing occupied proof port')throw error;}
 let bytes;
 const assetPath=path.join(repo,'build/browser-hub-lab/hub/Small-Island-v4l.baked.fbx');
 try{bytes=await readFile(assetPath);}catch(error){
  if(error.code!=='ENOENT')throw error;
  const response=await fetch('https://content.overte.org/Bazaar/Worlds/HQ_HiFi/content/Small-Island-v4l/baked/Small-Island-v4l.baked.fbx',{signal:AbortSignal.timeout(15000)});assert.equal(response.status,200);
  const chunks=[];let total=0;for await(const chunk of response.body){total+=chunk.length;assert(total<=32*1024*1024,'Pinned native FBX response exceeds32MiB');chunks.push(chunk);}bytes=Buffer.concat(chunks,total);
  assert.equal(createHash('sha256').update(bytes).digest('hex'),'1b2053e7ed90d2a2ea4811c1a8938602e7e9a876edbc2c9fc1a369b728894ef9');await mkdir(path.dirname(assetPath),{recursive:true});await writeFile(assetPath,bytes);
 }
 report.assetSHA256=createHash('sha256').update(bytes).digest('hex');
 assert.equal(report.assetSHA256,'1b2053e7ed90d2a2ea4811c1a8938602e7e9a876edbc2c9fc1a369b728894ef9');
 vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5184','--strictPort'],{cwd:path.join(repo,'browser-client'),stdio:'ignore'});
 for(let i=0;i<50;i++){try{if((await fetch(origin)).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
 browser=useFirefox?await firefox.launch({headless:true,env:{...process.env,LIBGL_ALWAYS_SOFTWARE:'1',MOZ_WEBRENDER_SOFTWARE:'1'},firefoxUserPrefs:{'webgl.force-enabled':true}}):await chromium.launch({headless:true,args:['--use-angle=swiftshader','--disable-dev-shm-usage']});report.browserVersion=browser.version();const page=await browser.newPage();
 await page.route(origin+'/',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
 await page.route(origin+'/actual-island.fbx',route=>route.fulfill({contentType:'application/octet-stream',body:bytes}));await page.goto(origin);
 report.result=await Promise.race([page.evaluate(async()=>{const path='/tests/static-model-batch-fixture.ts';return(await import(path)).auditActualIslandBatch();}),new Promise((_,reject)=>setTimeout(()=>reject(Error('Actual native mixed geometry audit exceeded30seconds')),30000).unref())]);
 const result=report.result;assert.equal(result.before.draws,1190);assert(result.saved>1000);assert.equal(result.before.triangles,result.after.triangles);assert(result.visible>10000);assert(result.different<=12,'At most12 edge pixels may differ from Float32 transform rounding');assert.equal(result.restoredDifferences,0);assert(result.originalGeometryRestored&&result.materialsUnchanged);assert(result.residualGroups.every(group=>group.idUnchanged));report.completed=true;
}catch(error){report.error=error.message;process.exitCode=1;}
finally{await browser?.close();if(vite){vite.kill('SIGTERM');await new Promise(resolve=>{if(vite.exitCode!==null)resolve();else vite.once('exit',resolve);});}report.finishedAt=new Date().toISOString();await mkdir(output,{recursive:true});await writeFile(path.join(output,useFirefox?'native-mixed-material-pixels-firefox.json':'native-mixed-material-pixels.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
